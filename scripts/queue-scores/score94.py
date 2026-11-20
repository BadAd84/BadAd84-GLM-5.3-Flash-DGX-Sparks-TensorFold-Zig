#!/usr/bin/env python3
"""score94.py [--dir DIR] - queue94 (scripts/queues/queue94.sh): the GPU receipts of two upstream levers, TF_GLM_HEAD_SKIP and TF_GLM_SOLO_TO_START, main against each branch on all three ranks.

DIR holds one folder a boot, <label>/concurrent.json (tools/bench_concurrent.py --alone --serial), <label>/decode.json (tools/bench_openai.py), <label>/cache-<N>.json
(tools/bench_cache.py --require-cold), and the lever's own cells: <label>/metrics-after.txt (the prompt cache's gauges), <label>/head-skip-line.txt (rank 0's log lines that name the
switch), <label>/ours-rows.jsonl (longctx.py's rows: the cold chat cells and both conversations), <label>/prof.txt (TF_GLM_PROF's prompt chunk and stage lines), the way queue94 writes
them. A cell of concurrent.json is (prompt, temperature, streams) and its rate is the tool's own aggregate_tps, read by score93.py's cells(), which this file imports.

LABELS. Head skip: hk-A1 hk-A2 (A, main), hk-B1a hk-B1b (B1, the branch with TF_GLM_HEAD_SKIP=1), hk-B0 (B0, the branch with the switch unset); the profile pair hk-P0 hk-P1 (the
branch with TF_GLM_PROF=1, without and with the switch). Solo to start: st-A1 st-A2 (A, main), st-B1a st-B1b (B1, the branch with TF_GLM_SOLO_TO_START=1), st-B0 (B0, the branch,
switch unset), st-B1x (the branch with TF_GLM_CHUNK_SOLO=4096 and the switch, request starts off). All boots: --parallel 4 --context 1048576, KNOBS=off, fresh, the same environment
on all three ranks; the solo-to-start arms also carry TF_GLM_CHUNK_SOLO=4096 and TF_GLM_REQUEST_STARTS=1, except st-B1x, which simply omits the starts flag (KNOBS=off's runtime
section names neither setting, so there is nothing to unset).

THE HEAD SKIP RULE, written before queue94's rows existed.
  H1 every boot's own alone and serial checks are clean and every cell of concurrent.json has ONE reply-digest set across all five boots (greedy and sampled alike);
  H2 the boot log: each B1 boot has exactly one line containing `TF_GLM_HEAD_SKIP=1: the MTP head absorbs no prompt rows`; the A and B0 boots have none (a violation FAILS);
  H3 decode: no cell (any prompt, either temperature, 1, 2 or 4 streams) is more than 1.0% slower in B1 than in A (the mean of each group's boots); and B0 is within 1.0% of A on
     every cell (the default path);
  H4 cold: for each of 2,048 / 8,192 / 32,768 / 65,536 the first request's ttft_s (cache-N.json, rows[0]) in B1 is not more than 1.0% slower than A's mean; B0 is within 2.0% of A
     at every size (cold first tokens spread more across boots);
  H5 kept state: bytes per kept state (prompt_cache_bytes / prompt_cache_states, states > 0 required) is strictly smaller in both B1 boots than in B0 and in both A boots, and B0
     equals A within 0.1%;
  H6 the profile pair, when present: hk-P1's mtp section is below hk-P0's by at least half (the parsed numbers are printed; when the files are absent it prints "not run", which does
     not stop a HOLDS).
  Verdict: FAILS if H1, H2, H3 (either clause) or H5 is violated or H4's no-slower clause is violated; else HOLDS when at 8,192 AND 32,768 both B1 boots' ttft are below both A
  boots' by a mean of at least 1.0%; else NEUTRAL (printing the gains, which may be under 1.0%). H6 never enters the verdict: the rule's list names H1, H2, H3, H5 and H4's no-slower
  clause only.

THE SOLO TO START RULE, written before queue94's rows existed.
  S1 every boot's own checks are clean; every concurrent.json cell has one digest set across all six boots; the ours-rows' reply hashes (the cold cells and every turn of both
     conversations) are one set per cell and turn across all six boots. A reply hash is the server's token_sha when every boot's row of that key carries one, else the client's sha;
  S2 decode (concurrent.json, 1, 2 and 4 streams, both temperatures): no cell is more than 1.0% slower in B1 than in A; B0 and B1x are within 1.0% of A on every cell;
  S3 cold chat first token (ours-rows, longctx.py probe) at 8k, 32k and 120k: B1 is not more than 1.0% slower than A's mean at any size; B0 and B1x are within 2.0% of A at every
     size;
  S4 the ~3,000-row conversation (chain tag c3k): the mean first-token time over turns 3 to 10 is lower in B1 than in A by at least 1.0% with both B1 boots below both A boots; c3k
     turn 2 and the ~113k conversation (tag c74, turns 2 to 8) are not more than 1.0% slower in B1 than in A;
  S5 device checks: every psts check log under DIR/checks has a PASS line and no FAIL; none found is NOT DECIDED for this clause only (named).
  Verdict: FAILS if S1, S2, S3's no-slower clause, S4's no-slower clauses or S5 is violated; HOLDS when the cold 8k mean is faster in B1 by at least 1.0% (both B1 boots below both A
  boots) AND S4's gain clause holds; else NEUTRAL. A missing boot or report is NOT DECIDED for that lever, never a pass.

WARM TURNS, a REPORT and nothing more. The st boots also run upstream's tools/bench_warm_turns.py --phase cold at about 8,192, 32,768 and 122,880 prompt tokens (warm-8k.json,
warm-32k.json, warm-120k.json): one chat turn, the shape whose message structure carries the request starts this lever cuts, plus a short continuation. This block prints, per boot,
first_turn.client_ttft_seconds, first_turn.engine_time_to_first_token_seconds, first_turn.prefill_widths (the chunk widths the lever changes, straight from the server) and the report's
qualified flag; then each arm's mean engine time to first token against A's (faster positive) and the distinct prefill_widths per arm, so A's widths against B1's are visible. It changes
NO verdict and NO exit code: the lever's verdict is the S1-S5 rules above, written before the rows existed, and this block is upstream-tool evidence for the pull request, not a sixth
rule. A missing or unreadable report prints "no warm-8k.json" and no number.
"""
import argparse
import importlib.util
import json
import os
import pathlib
import re
import statistics as st
import sys

LIMIT = 0.010  # a cell more than this much slower is a regression
COLD_TOL = 0.020  # H4 and S3: the default path's cold first tokens spread more across boots
KEEP_TOL = 0.001  # H5: B0's bytes per kept state against A's
HK = {"A": ("hk-A1", "hk-A2"), "B1": ("hk-B1a", "hk-B1b"), "B0": ("hk-B0",)}
ST = {"A": ("st-A1", "st-A2"), "B1": ("st-B1a", "st-B1b"), "B0": ("st-B0",), "B1x": ("st-B1x",)}
HK_CACHE = (2048, 8192, 32768, 65536)
HK_HOLD_SIZES = (8192, 32768)
ST_COLD = (8000, 32000, 120000)
C3K, C74 = "c3k", "c74"  # the ~3,000-row-turn conversation and the ~113k one (~1,290 rows a turn), queue89's salts
WARM = (("8k", 8192), ("32k", 32768), ("120k", 122880))  # queue94's warm-<size>.json, upstream's bench_warm_turns.py, and the prompt-token target of each
HEAD_LINE = "TF_GLM_HEAD_SKIP=1: the MTP head absorbs no prompt rows"
CHUNK = re.compile(r"glm prompt chunk rank=\d+ slot=\d+ start=\d+ rows=\d+ wall_ms=[\d.]+ spans=\d+")
MTP = re.compile(r"glm prompt stage rank=\d+ slot=\d+ start=\d+ rows=\d+ layer=\S+ piece=\S+ site=\S+ stage=mtp stream=\S+ ms=([\d.]+)")
GAUGE = re.compile(r"^(?:tensorfold:)?(prompt_cache_states|prompt_cache_bytes) ([\d.]+)$")


_S93 = None


def s93():
    """score93.py, whose cells(), boot() and diff() read concurrent.json: the one owner of that format (found above this file, so a scratch copy of this scorer still finds it)."""
    global _S93
    if _S93 is None:
        for p in pathlib.Path(__file__).resolve().parents:
            f = p / "scripts/queue-scores/score93.py"
            if f.exists():
                spec = importlib.util.spec_from_file_location("score93", f)
                _S93 = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(_S93)
                break
        else:
            raise SystemExit("score94: scripts/queue-scores/score93.py not found above this file")
    return _S93


def rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def text(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def cells_by_boot(d, labels):
    """({label: cells}, labels with no concurrent.json)."""
    s, out, miss = s93(), {}, []
    for label in labels:
        c = s.boot(d, label)
        if c is None:
            miss.append(label)
        else:
            out[label] = c
    return out, miss


def decode_keys(cb):
    """Every (prompt, temperature, streams) at 1, 2 or 4 streams, whichever boots carry it."""
    return sorted({k for cs in cb.values() for k in cs if k[2] in (1, 2, 4)})


def unclean(cb):
    """[(label, cell)] whose own alone or serial check found a difference or a failure."""
    return sorted((label, k) for label, cs in cb.items() for k, v in cs.items() if not v["clean"])


def digests(cb):
    """Cells whose reply-digest tuple is not one set across the boots given."""
    seen = {}
    for cs in cb.values():
        for k, v in cs.items():
            seen.setdefault(k, set()).add(v["shas"])
    return sorted(k for k, s in seen.items() if len(s) != 1)


def rates(cb, labels, key):
    return [cb[label][key]["tps"] for label in labels if label in cb and key in cb[label]]


def cold(d, label, n):
    """The first request's ttft_s of one cold bench_cache cell, or None."""
    rep = s93().read(f"{d}/{label}/cache-{n}.json")
    try:
        return float(rep["rows"][0]["ttft_s"])
    except (TypeError, KeyError, IndexError, ValueError):
        return None


def gauges(d, label):
    """{prompt_cache_states, prompt_cache_bytes} of metrics-after.txt, or None."""
    body = text(f"{d}/{label}/metrics-after.txt")
    if body is None:
        return None
    out = {}
    for line in body.splitlines():
        m = GAUGE.match(line.strip())
        if m:
            out[m[1]] = int(float(m[2]))
    return out


def per_state(d, label):
    """bytes per kept state of one boot, or (None, why)."""
    g = gauges(d, label)
    if g is None:
        return None, "no metrics-after.txt"
    if "prompt_cache_states" not in g or "prompt_cache_bytes" not in g:
        return None, "metrics-after.txt has no prompt_cache_states or no prompt_cache_bytes"
    if g["prompt_cache_states"] <= 0:
        return None, f"prompt_cache_states is {g['prompt_cache_states']}"
    return g["prompt_cache_bytes"] / g["prompt_cache_states"], f"{g['prompt_cache_bytes']} B over {g['prompt_cache_states']} states"


def head_count(d, label):
    """Lines naming the switch's boot line in one boot's rank 0 log, or None when no log was kept."""
    for name in ("head-skip-line.txt", "r0-boot.log"):
        body = text(f"{d}/{label}/{name}")
        if body is not None:
            return sum(1 for line in body.splitlines() if HEAD_LINE in line)
    return None


def ours(d, label):
    return rows(f"{d}/{label}/ours-rows.jsonl")


def ours_cold(d, label, size):
    """(mean ttft_ms of the cold rows at `size`, [(rep, token_sha, sha)]) of one boot, or (None, [])."""
    rs = [r for r in ours(d, label) if r.get("case") == "cold" and r.get("target_tokens") == size]
    if not rs or any(r.get("ttft_ms") is None for r in rs):
        return None, []
    return st.mean(r["ttft_ms"] for r in rs), [(r.get("rep"), r.get("token_sha"), r.get("sha")) for r in rs]


def ours_chain(d, label, tag):
    """{turn: row} of one conversation in one boot's ours-rows."""
    return {r.get("turn"): r for r in ours(d, label) if r.get("case") == "chain" and r.get("tag") == tag}


def chain_turn_time(d, labels, tag, turns):
    """per boot: the mean ttft_ms over `turns` of one conversation, or (None, why)."""
    out = {}
    for label in labels:
        conv = ours_chain(d, label, tag)
        miss = [t for t in turns if t not in conv or conv[t].get("ttft_ms") is None]
        if miss:
            out[label] = (None, f"no {tag} turn(s) {miss}")
        else:
            out[label] = (st.mean(conv[t]["ttft_ms"] for t in turns), "")
    return out


def profile(d, label):
    """(chunk lines, mtp ms summed) of one boot's prof.txt, or None."""
    body = text(f"{d}/{label}/prof.txt")
    if body is None:
        return None
    chunks, ms = 0, 0.0
    for line in body.splitlines():
        if CHUNK.search(line):
            chunks += 1
            continue
        m = MTP.search(line)
        if m:
            ms += float(m[1])
    return chunks, ms


def name(k):
    return f"{k[0]} at {k[1]:g} with {k[2]} stream(s)"


def mean_gain(new, old):
    """Fraction by which the mean of `new` is above the mean of `old` (a rate: positive is faster; a latency: positive is slower): score93.py's diff, the one owner of the mean."""
    return s93().diff(new, old)


def both_below(new, old):
    return max(new) < min(old)


# ---------------------------------------------------------------- head skip

def head_skip(d):
    out, reasons, undecided, gains = [], [], [], {}
    cb, miss = cells_by_boot(d, [x for a in ("A", "B1", "B0") for x in HK[a]])
    if miss:
        return out, f"HEAD SKIP: NOT DECIDED: no concurrent.json for {', '.join(miss)}", False
    out.append(f"== head skip: A {HK['A']}, B1 {HK['B1']}, B0 {HK['B0']}, at --parallel 4 --context 1048576 with KNOBS=off")
    bad = unclean(cb)
    for label, k in bad:
        reasons.append(f"H1: {label}'s own alone or serial check found a difference or failed at {name(k)}")
    differ = digests(cb)
    if differ:
        reasons.append(f"H1: {len(differ)} cell(s) with more than one reply digest across the five boots: {'; '.join(name(k) for k in differ[:4])}")
    out.append(f"H1: {len(bad)} boot cell(s) unclean, {len(differ)} cell(s) with more than one reply digest")
    counts = {label: head_count(d, label) for label in cb}
    missing_log = [label for label, n in counts.items() if n is None]
    if missing_log:
        undecided.append(f"H2: no rank 0 log for {', '.join(missing_log)}")
    for label in HK["B1"]:
        if counts.get(label) == 0:
            reasons.append(f"H2: {label} logged no '{HEAD_LINE}' line: the engine did not take the skip")
        elif counts.get(label) is not None and counts[label] > 1:
            reasons.append(f"H2: {label} logged the line {counts[label]} times")
    for label in HK["A"] + HK["B0"]:
        if counts.get(label):
            reasons.append(f"H2: {label} logged the skip's line {counts[label]} time(s) with the switch unset or on main")
    out.append("H2: switch lines " + ", ".join(f"{label} {counts[label]}" for label in sorted(counts)))
    for k in decode_keys(cb):
        a, b1, b0 = rates(cb, HK["A"], k), rates(cb, HK["B1"], k), rates(cb, HK["B0"], k)
        if not (a and b1 and b0):
            undecided.append(f"H3: no A, B1 or B0 cell for {name(k)}")
            continue
        g, d0 = mean_gain(b1, a), mean_gain(b0, a)
        line = f"H3 {name(k)}: B1 {g:+.2%} against A (A {' '.join(f'{x:.1f}' for x in a)} | B1 {' '.join(f'{x:.1f}' for x in b1)}), B0 {d0:+.2%}"
        if g < -LIMIT:
            reasons.append(f"H3: {name(k)} is {-g:.2%} slower in B1")
            line += "  <- B1 over the limit"
        if abs(d0) > LIMIT:
            reasons.append(f"H3: {name(k)}: B0 differs from A by {d0:+.2%} (the default path)")
            line += "  <- B0 off the default path"
        out.append(line)
    for n in HK_CACHE:
        a = [cold(d, label, n) for label in HK["A"]]
        b1 = [cold(d, label, n) for label in HK["B1"]]
        b0 = [cold(d, label, n) for label in HK["B0"]]
        if any(x is None for x in a + b1 + b0):
            undecided.append(f"H4: no first cold request at {n} in {', '.join(label for label, x in zip(HK['A'] + HK['B1'] + HK['B0'], a + b1 + b0) if x is None)}")
            continue
        s = mean_gain(b1, a)
        d0 = mean_gain(b0, a)
        gains[n] = s
        out.append(f"H4 cold {n}: A {' '.join(f'{x * 1000:.1f}' for x in a)} ms | B1 {' '.join(f'{x * 1000:.1f}' for x in b1)} ms, {s:+.2%} | B0 {b0[0] * 1000:.1f} ms, {d0:+.2%}")
        if s > LIMIT:
            reasons.append(f"H4: the cold first token at {n} is {s:.2%} slower in B1")
        if abs(d0) > COLD_TOL:
            reasons.append(f"H4: B0's cold first token at {n} differs from A by {d0:+.2%}")
    per, why = {}, {}
    for label in HK["A"] + HK["B1"] + HK["B0"]:
        per[label], why[label] = per_state(d, label)
    absent = [label for label in per if per[label] is None]
    if absent:
        undecided.append("H5: " + "; ".join(f"{label} ({why[label]})" for label in absent))
    else:
        a = [per[label] for label in HK["A"]]
        for label in HK["B1"]:
            over = [f"{label} {per[label]:.0f} B/state against {x} {per[x]:.0f}" for x in HK["A"] + HK["B0"] if per[label] >= per[x]]
            if over:
                reasons.append(f"H5: {label}'s kept state is not strictly smaller: {'; '.join(over)}")
        d0 = mean_gain([per[label] for label in HK["B0"]], a)
        out.append("H5 bytes per kept state: " + ", ".join(f"{label} {per[label]:.0f}" for label in sorted(per)) + f"; B0 against A {d0:+.2%} ({why['hk-B0']} against {why['hk-A1']})")
        if abs(d0) > KEEP_TOL:
            reasons.append(f"H5: B0's bytes per kept state differ from A by {d0:+.2%}")
    p0, p1 = profile(d, "hk-P0"), profile(d, "hk-P1")
    if p0 is None or p1 is None or p0[0] == 0 or p1[0] == 0:
        out.append(f"H6: not run (profile pair {'absent' if p0 is None or p1 is None else 'without a prompt chunk'})")
    else:
        out.append(f"H6 mtp section: hk-P0 {p0[1]:.2f} ms over {p0[0]} chunk line(s) | hk-P1 {p1[1]:.2f} ms over {p1[0]} chunk line(s)" +
                   (" (below half: the head ran no prompt pass)" if p1[1] < p0[1] / 2 else "  <- not below half"))
    if undecided:
        return out, "HEAD SKIP: NOT DECIDED: " + "; ".join(undecided), False
    if reasons:
        return out, "HEAD SKIP: FAILS: " + "; ".join(reasons), True
    hold = ", ".join(f"{n:,}" for n in HK_HOLD_SIZES)
    if all(n in gains and both_below([cold(d, label, n) for label in HK["B1"]], [cold(d, label, n) for label in HK["A"]]) and gains[n] <= -LIMIT
           for n in HK_HOLD_SIZES):
        return out, f"HEAD SKIP: HOLDS: at {hold} both B1 boots' first cold token is below both A boots' by " + \
            " and ".join(f"{-gains[n]:.2%}" for n in HK_HOLD_SIZES), False
    return out, "HEAD SKIP: NEUTRAL: " + ", ".join(f"cold {n} B1 {gains[n]:+.2%}" for n in sorted(gains)), False


# ---------------------------------------------------------------- solo to start

def ours_key_digests(d, labels):
    """({key: [(token_sha, sha)] of each boot's rows}, boots or keys with no row) for the cold cells and every turn of both conversations."""
    out, miss = {}, []
    have = [label for label in labels if ours(d, label)]
    for label in labels:
        rs = ours(d, label)
        if not rs:
            miss.append(f"{label} (no ours-rows.jsonl)")
            continue
        for n in ST_COLD:
            cell = [r for r in rs if r.get("case") == "cold" and r.get("target_tokens") == n]
            if not cell:
                miss.append(f"{label} (no cold {n})")
            for r in cell:
                out.setdefault(("cold", n, r.get("rep")), []).append((r.get("token_sha"), r.get("sha")))
        for tag, turns in ((C3K, range(1, 11)), (C74, range(1, 9))):
            conv = ours_chain(d, label, tag)
            for t in turns:
                if t not in conv:
                    miss.append(f"{label} ({tag} turn {t})")
                else:
                    out.setdefault(("chain", tag, t), []).append((conv[t].get("token_sha"), conv[t].get("sha")))
    miss += [f"{k} not in every boot" for k, v in sorted(out.items()) if len(have) > 1 and len(v) != len(have)]
    return out, miss


def ours_differ(d, labels):
    """keys whose reply hash is not one value across the boots: token_sha when every boot's row carries one, else sha."""
    table, miss = ours_key_digests(d, labels)
    differ = []
    for k, vals in table.items():
        use = [v[0] if all(x[0] for x in vals) else v[1] for v in vals]
        if len(set(use)) != 1:
            differ.append(k)
    return sorted(differ), miss


def checks(d):
    """[(path, PASS lines, FAIL lines)] of every psts check log under DIR/checks."""
    root = f"{d}/checks"
    out = []
    if not os.path.isdir(root):
        return out
    for entry in sorted(os.listdir(root)):
        path = f"{root}/{entry}"
        if "psts" not in entry:
            continue
        if os.path.isdir(path):
            logs = [f"{path}/{f}" for f in sorted(os.listdir(path)) if f.startswith("r") and f.endswith(".log")]
        elif entry.endswith(".log"):
            logs = [path]
        else:
            logs = []
        for log in logs:
            lines = (text(log) or "").splitlines()
            out.append((log, sum(1 for line in lines if line.startswith("PASS")), sum(1 for line in lines if "FAIL" in line)))
    return out


def warm(d, label, size):
    """(client ttft s, engine ttft s, prefill widths tuple, qualified, prompt tokens) of one boot's warm-<size>.json, or None when it is missing or unreadable."""
    try:
        rep = s93().read(f"{d}/{label}/warm-{size}.json")
    except (OSError, ValueError):
        return None
    if not isinstance(rep, dict):
        return None
    first = rep.get("first_turn")
    first = first if isinstance(first, dict) else {}
    widths = first.get("prefill_widths")
    return (first.get("client_ttft_seconds"), first.get("engine_time_to_first_token_seconds"),
            tuple(widths) if isinstance(widths, list) else None, rep.get("qualified"),
            rep.get("first_prompt_tokens_tokenizer"))


def warm_report(d):
    """The st boots' upstream bench_warm_turns.py reports: printed only, never a verdict (the lever's verdict is the S1-S5 rules)."""
    out = ["== warm turns: upstream's tools/bench_warm_turns.py --phase cold, one chat turn a size (REPORT ONLY: no verdict and no exit code depends on this block; the solo lever's verdict is S1-S5's)"]
    for size, target in WARM:
        timings = {arm: [] for arm in ST}
        widths = {arm: set() for arm in ST}
        for arm in ST:
            for label in ST[arm]:
                got = warm(d, label, size)
                if got is None:
                    out.append(f"{label}: no warm-{size}.json")
                    continue
                client, engine, w, qual, tokens = got
                if isinstance(engine, (int, float)):
                    timings[arm].append(engine)
                widths[arm].add(w)
                out.append(f"{label} warm-{size}: client_ttft_s {client}, engine_ttft_s {engine}, "
                           f"prefill_widths {list(w) if w is not None else None}, qualified {qual}, prompt_tokens {tokens} (target {target})")
        base = timings["A"]
        parts = []
        for arm in ST:
            v = timings[arm]
            if not v:
                parts.append(f"{arm} no numbers")
            elif base:
                parts.append(f"{arm} mean {st.mean(v):.3f} s, {1 - st.mean(v) / st.mean(base):+.2%} against A (faster positive)")
            else:
                parts.append(f"{arm} mean {st.mean(v):.3f} s (A has no numbers)")
        out.append(f"== warm {size} (target {target}) engine TTFT: " + "; ".join(parts))
        for arm in ST:
            seen = sorted((w for w in widths[arm] if w is not None), key=lambda w: (len(w), w))
            gone = sum(1 for w in widths[arm] if w is None)
            out.append(f"   {arm} prefill_widths: " + (", ".join(str(list(w)) for w in seen) if seen else "none")
                       + (f" ({gone} boot(s) without widths)" if gone else ""))
    return out


def solo(d):
    out, reasons, undecided = [], [], []
    cb, miss = cells_by_boot(d, [x for a in ("A", "B1", "B0", "B1x") for x in ST[a]])
    if miss:
        return out, f"SOLO TO START: NOT DECIDED: no concurrent.json for {', '.join(miss)}", False
    out.append(f"== solo to start: A {ST['A']}, B1 {ST['B1']}, B0 {ST['B0']}, B1x {ST['B1x']}, at --parallel 4 --context 1048576 with KNOBS=off and CHUNK_SOLO=4096 (request starts on every arm but B1x)")
    bad = unclean(cb)
    for label, k in bad:
        reasons.append(f"S1: {label}'s own alone or serial check found a difference or failed at {name(k)}")
    differ = digests(cb)
    if differ:
        reasons.append(f"S1: {len(differ)} concurrent cell(s) with more than one reply digest across the six boots: {'; '.join(name(k) for k in differ[:4])}")
    ours_diff, ours_miss = ours_differ(d, [x for a in ("A", "B1", "B0", "B1x") for x in ST[a]])
    if ours_miss:
        undecided.append(f"S1: ours-rows missing rows: {', '.join(ours_miss[:6])}")
    if ours_diff:
        reasons.append(f"S1: {len(ours_diff)} ours-rows cell(s) or turn(s) with more than one reply hash: {'; '.join(str(k) for k in ours_diff[:4])}")
    out.append(f"S1: {len(bad)} boot cell(s) unclean, {len(differ)} concurrent cell(s) and {len(ours_diff)} ours-rows key(s) with more than one reply digest")
    for k in decode_keys(cb):
        a, b1, b0, b1x = (rates(cb, ST[arm], k) for arm in ("A", "B1", "B0", "B1x"))
        if not (a and b1 and b0 and b1x):
            undecided.append(f"S2: no A, B1, B0 or B1x cell for {name(k)}")
            continue
        g, d0, dx = mean_gain(b1, a), mean_gain(b0, a), mean_gain(b1x, a)
        line = f"S2 {name(k)}: B1 {g:+.2%}, B0 {d0:+.2%}, B1x {dx:+.2%} against A (A {' '.join(f'{x:.1f}' for x in a)} | B1 {' '.join(f'{x:.1f}' for x in b1)})"
        if g < -LIMIT:
            reasons.append(f"S2: {name(k)} is {-g:.2%} slower in B1")
            line += "  <- B1 over the limit"
        for arm, x in (("B0", d0), ("B1x", dx)):
            if abs(x) > LIMIT:
                reasons.append(f"S2: {name(k)}: {arm} differs from A by {x:+.2%}")
                line += f"  <- {arm} off the default path"
        out.append(line)
    cold_gain = {}
    for n in ST_COLD:
        a = [ours_cold(d, label, n)[0] for label in ST["A"]]
        b1 = [ours_cold(d, label, n)[0] for label in ST["B1"]]
        b0 = [ours_cold(d, label, n)[0] for label in ST["B0"]]
        b1x = [ours_cold(d, label, n)[0] for label in ST["B1x"]]
        if any(x is None for x in a + b1 + b0 + b1x):
            undecided.append(f"S3: no cold {n} rows in {', '.join(label for label, x in zip(ST['A'] + ST['B1'] + ST['B0'] + ST['B1x'], a + b1 + b0 + b1x) if x is None)}")
            continue
        s, d0, dx = mean_gain(b1, a), mean_gain(b0, a), mean_gain(b1x, a)
        cold_gain[n] = s
        out.append(f"S3 cold chat {n}: A {' '.join(f'{x:.0f}' for x in a)} ms | B1 {' '.join(f'{x:.0f}' for x in b1)} ms, {s:+.2%} | B0 {b0[0]:.0f} ms {d0:+.2%} | B1x {b1x[0]:.0f} ms {dx:+.2%}")
        if s > LIMIT:
            reasons.append(f"S3: the cold chat first token at {n} is {s:.2%} slower in B1")
        for arm, x in (("B0", d0), ("B1x", dx)):
            if abs(x) > COLD_TOL:
                reasons.append(f"S3: {arm}'s cold chat first token at {n} differs from A by {x:+.2%}")
    gain3k = None
    gain3k_ok = False
    c3k = chain_turn_time(d, [x for a in ("A", "B1", "B0", "B1x") for x in ST[a]], C3K, tuple(range(3, 11)))
    c3k2 = chain_turn_time(d, [x for a in ("A", "B1", "B0", "B1x") for x in ST[a]], C3K, (2,))
    c74 = chain_turn_time(d, [x for a in ("A", "B1", "B0", "B1x") for x in ST[a]], C74, tuple(range(2, 9)))
    s4_missing = []
    for tag, table in ((f"{C3K} turns 3 to 10", c3k), (f"{C3K} turn 2", c3k2), (f"{C74} turns 2 to 8", c74)):
        absent = [f"{label} ({why})" for label, (v, why) in table.items() if v is None]
        if absent:
            s4_missing.append(f"S4: no {tag} rows: {', '.join(absent[:4])}")
    undecided += s4_missing
    if not s4_missing:
        a = [c3k[label][0] for label in ST["A"]]
        b1 = [c3k[label][0] for label in ST["B1"]]
        gain3k = 1 - st.mean(b1) / st.mean(a)
        gain3k_ok = both_below(b1, a) and gain3k >= LIMIT
        out.append(f"S4 {C3K} turns 3 to 10: A {' '.join(f'{x:.0f}' for x in a)} ms | B1 {' '.join(f'{x:.0f}' for x in b1)} ms, {gain3k:+.2%} faster"
                   + ("" if both_below(b1, a) else "  <- not every B1 boot below every A boot"))
        a2 = [c3k2[label][0] for label in ST["A"]]
        b12 = [c3k2[label][0] for label in ST["B1"]]
        g2 = mean_gain(b12, a2)
        out.append(f"S4 {C3K} turn 2: A {' '.join(f'{x:.1f}' for x in a2)} ms | B1 {' '.join(f'{x:.1f}' for x in b12)} ms, {g2:+.2%}")
        if g2 > LIMIT:
            reasons.append(f"S4: {C3K} turn 2 is {g2:.2%} slower in B1")
        a74 = [c74[label][0] for label in ST["A"]]
        b74 = [c74[label][0] for label in ST["B1"]]
        g74 = mean_gain(b74, a74)
        out.append(f"S4 {C74} turns 2 to 8: A {' '.join(f'{x:.1f}' for x in a74)} ms | B1 {' '.join(f'{x:.1f}' for x in b74)} ms, {g74:+.2%}")
        if g74 > LIMIT:
            reasons.append(f"S4: {C74} turns 2 to 8 are {g74:.2%} slower in B1")
    ck = checks(d)
    if not ck:
        out.append("S5: not decided (no psts check log under DIR/checks)")
    else:
        out.append("S5 device checks: " + ", ".join(f"{os.path.relpath(p, d + '/checks')} {p_} PASS {f} FAIL" for p, p_, f in ck))
        for path, passes_, fails in ck:
            if fails or not passes_:
                reasons.append(f"S5: {os.path.basename(path)} has {passes_} PASS and {fails} FAIL line(s)")
    if undecided:
        return out, "SOLO TO START: NOT DECIDED: " + "; ".join(undecided), False
    if reasons:
        return out, "SOLO TO START: FAILS: " + "; ".join(reasons), True
    faster8k = (8000 in cold_gain and cold_gain[8000] <= -LIMIT
                and both_below([ours_cold(d, label, 8000)[0] for label in ST["B1"]], [ours_cold(d, label, 8000)[0] for label in ST["A"]]))
    if faster8k and gain3k_ok:
        return out, f"SOLO TO START: HOLDS: cold chat 8k {-cold_gain[8000]:.2%} faster in B1 with every B1 boot below every A boot, {C3K} turns 3 to 10 {gain3k:.2%} faster", False
    return out, "SOLO TO START: NEUTRAL: " + ", ".join(f"cold {n} B1 {g:+.2%}" for n, g in sorted(cold_gain.items())) + (f", {C3K} turns 3 to 10 {gain3k:+.2%} faster" if gain3k is not None else ""), False


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default="docs/audit-2026-11-12/queue-rows/queue94/f94-c")
    a = ap.parse_args(argv)
    failed = False
    for fn in (head_skip, solo):
        lines, verdict, bad = fn(a.dir)
        print("\n".join(lines))
        print(verdict)
        failed = failed or bad
    print("\n".join(warm_report(a.dir)))  # a report: it decides nothing and never touches `failed`
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
