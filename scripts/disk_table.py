#!/usr/bin/env python3
"""disk_table.py ROWS.jsonl [...] [--ranks 3] - the disk tier window's table: GLM's conversation states on disk
(--learn-conversations, PR #1411) on the TP=3 serve, every resumed turn against a cold server's reply (stdlib only).

Reads the rows disk.py writes and prints:
  1. rejected rows: requests that cannot stand as the measurement they claim (instrument checks, below);
  2. boots: each boot's arm, store line (directory, states, MiB, ranks' parts, staging permit), /stats' disk block and
     MemAvailable on every node;
  3. turns: each conversation's turns with what they expected to resume from and what they did (cold, RAM, disk), the
     cached tokens against the newest kept state, first token, the disk read and the saves, and the correctness gate:
     the reply's token_sha and text hash against the cold server's reply to the same prompt;
  4. the long conversation beside production's tier_chain turns (server prefill seconds) and our earlier window;
  5. a save beside decoding streams: the other streams' decode gaps before, during the prefill, during the reply and
     until the save is written;
  6. the rank logs' disk tier lines.
Instrument checks (verify(), the one owner; disk.py flags rows with it): ERR the request failed; NOUSAGE no usage
prompt_tokens; TOK usage differs from the /tokenize count the prompt was recorded with; NOCACHE no cached_tokens;
NOTTFT no first token; NOLOAD a loaded turn sent with fewer streams decoding than asked; NOTCOLD a cold reference
that resumed (the reference server must keep nothing).
Disk tier checks (failures(), results, not instrument faults): GATE a reply differs from its cold reference; SOURCE a
turn did not resume from what it expected (cold, RAM, disk); SHORT a resume below the newest kept state; SAVE a save
skipped, failed or still queued after the drain; STORE a later boot of the disk arm found another store, no states,
another rank count than --ranks, or refused the store (RanksDiffer, DiskWorld, DiskLayout).
Exit 0: no row rejected and no disk tier check failed. 1: a row was rejected. 2: no rows or bad input. 3: a disk tier
check failed (named at the top).
"""
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

COLD_MAX = 0.05  # a cold prompt: at most 5% of it from kept states (production ttft.py's NOTCOLD)
WARM_MIN = 0.50  # a resumed turn: at least half of it from kept states (production ttft.py's NOTWARM)
TURNS = ("turn", "ref")
# production/SPEED-TARGET.md section 3 (tier_chain.sh / chainturn.py, server prefill seconds), --parallel 4 at 1,048,576
PROD_CHAIN = {1: ("cold at ~596k tokens", 224.68), 2: ("from the pool", 12.54),
              3: ("after every rank was SIGKILLed, from the spill tier (619,392 cached)", 12.80),
              4: ("after a clean restart", 12.90)}
# docs/OVERNIGHT-2026-11-12.md section 29: this serve without a disk tier (image rs2x3, the deployed shape)
LC1_CHAIN = {1: 346.04, 2: 14.78, 3: 377.76}
LABELS = {"cold": "cold", "ram": "from RAM", "evicted": "after eviction", "kill": "after SIGKILL of every rank",
          "restart": "after a clean restart", "quote": "quote probe"}


def verify(row):
    """The reasons `row` cannot stand as the measurement it claims ([] when it can). Recomputed from raw fields."""
    if row.get("case") not in TURNS:
        return []
    out = []
    if row.get("error"):
        out.append("ERR")
    p = row.get("prompt_tokens")
    if isinstance(p, bool) or not isinstance(p, int) or p <= 0:
        out.append("NOUSAGE")
        return out
    k = row.get("tokenized_tokens")
    if k is not None and k != p:
        out.append("TOK")
    cached = row.get("cached_tokens")
    if cached is None:
        out.append("NOCACHE")
    elif row.get("case") == "ref" and (cached > COLD_MAX * p or (row.get("resumed_at") or 0) > 0):
        out.append("NOTCOLD")
    load = row.get("load") or 0
    if load and (row.get("others") or 0) < load:
        out.append("NOLOAD")
    if row.get("ttft_ms") is None:
        out.append("NOTTFT")
    return out


def source(row):
    """What a turn resumed from, measured: cold, ram, disk or partial (some cached, under half)."""
    p, c = row.get("prompt_tokens") or 0, row.get("cached_tokens") or 0
    d = row.get("disk") or {}
    if c <= COLD_MAX * p and not (row.get("resumed_at") or 0):
        return "cold"
    if c < WARM_MIN * p:
        return "partial"
    if (d.get("reads") or 0) >= 1 and (d.get("read_bytes") or 0) > 0:
        return "disk"
    if any(0 < (x.get("at") or 0) <= c for x in (row.get("log_reads") or [])):
        return "disk"
    return "ram"


def gate(rows):
    """{case_id: (verdict, ref row)} for every disk-arm turn: equal, DIFFERS, or no reference."""
    refs = {}
    for r in rows:
        if r.get("case") == "ref" and not verify(r) and r.get("case_id"):
            refs[r["case_id"]] = r
    out = {}
    for r in rows:
        if r.get("case") != "turn" or not r.get("case_id"):
            continue
        ref = refs.get(r["case_id"])
        if ref is None:
            out[id(r)] = ("no reference", None)
        elif (r.get("token_sha") == ref.get("token_sha") and r.get("sha") == ref.get("sha")
              and r.get("completion_tokens") == ref.get("completion_tokens")):
            out[id(r)] = ("equal", ref)
        else:
            out[id(r)] = ("DIFFERS", ref)
    return out


def boot_failures(rows, ranks):
    """(boot row, reason) for each disk-arm boot whose store does not stand: the first finds a fresh store, the rest
    the same directory with states in it, every one with `ranks` ranks' parts and no store refusal."""
    out = []
    learn = [r for r in rows if r.get("case") == "boot" and r.get("arm", "learn") == "learn" and r.get("ok")]
    first = None
    for r in learn:
        st = r.get("store")
        if r.get("store_errors"):
            out.append((r, "STORE refused: " + ", ".join(r["store_errors"])))
        if not st:
            out.append((r, "STORE no store line"))
            continue
        if st.get("ranks") != ranks:
            out.append((r, f"STORE {st.get('ranks')} ranks' parts, not {ranks}"))
        if first is None:
            first = st
            continue
        if st.get("dir") != first.get("dir"):
            out.append((r, f"STORE another directory ({st.get('dir')}, first {first.get('dir')})"))
        if not st.get("states"):
            out.append((r, "STORE no states found"))
    return out


def failures(rows, ranks=3):
    """Every disk tier check that failed, as (row, reason)."""
    g = gate(rows)
    out = list(boot_failures(rows, ranks))
    for r in rows:
        if r.get("case") != "turn" or verify(r):
            continue
        verdict, _ = g.get(id(r), ("no reference", None))
        if verdict == "DIFFERS":
            out.append((r, "GATE the reply differs from the cold server's"))
        src = source(r)
        if r.get("expect") and src != r["expect"]:
            out.append((r, f"SOURCE expected {r['expect']}, resumed from {src}"))
        ec = r.get("expect_cached")
        if r.get("expect") in ("ram", "disk") and isinstance(ec, int) and ec > 0 and (r.get("cached_tokens") or 0) < ec:
            out.append((r, f"SHORT cached {r.get('cached_tokens')} below the newest kept state {ec}"))
        d = r.get("disk") or {}
        dr = r.get("drain") or {}
        if (d.get("skipped") or 0) > 0 or (d.get("failed") or 0) > 0:
            out.append((r, f"SAVE {d.get('skipped') or 0} skipped, {d.get('failed') or 0} failed"))
        if dr.get("timed_out"):
            out.append((r, f"SAVE still queued after {dr.get('wait_s')} s"))
    for r in rows:
        if r.get("case") == "drain" and (r.get("drain") or {}).get("timed_out"):
            out.append((r, f"SAVE the store did not drain before {r.get('label') or 'the next step'}"))
    return out


def fmt(v, digits=2):
    if v is None:
        return "-"
    if isinstance(v, int) and not isinstance(v, bool):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.{digits}f}"
    return str(v)


def mib(b):
    return None if b is None else b / (1 << 20)


def gib_kib(k):
    return None if k is None else k / (1 << 20)


def load_rows(paths):
    rows = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError as exc:
                    raise ValueError(f"{path}:{n}: not JSON ({exc})") from None
                if not isinstance(obj, dict):
                    raise ValueError(f"{path}:{n}: not a JSON object")
                rows.append(obj)
    return rows


def boot_section(rows):
    out = ["## Boots", "", "| boot | arm | P | context | image | boot s | store: states, MiB of cap | ranks' parts | "
           "a save stages up to | store directory | MemAvailable GiB spark1 / 2 / 3 |", "|---|---|---:|---:|---|---:|---|---:|---:|---|---|"]
    for r in rows:
        if r.get("case") != "boot":
            continue
        st = r.get("store") or {}
        mem = r.get("mem_after_boot_kib") or {}
        mems = " / ".join(fmt(gib_kib(mem.get(k)), 1) for k in ("spark1", "spark2", "spark3"))
        if not r.get("ok"):
            out.append(f"| {r.get('tag')} | {r.get('arm', '-')} | {r.get('n')} | {fmt(r.get('ctx'))} | {r.get('image') or '-'} | "
                       f"BOOT FAILED: {str(r.get('error'))[:160]} | | | | | {mems} |")
            continue
        states = f"{fmt(st.get('states'))}, {fmt(st.get('held_mib'))} of {fmt(st.get('cap_mib'))}" if st else "-"
        out.append(f"| {r.get('tag')} | {r.get('arm', '-')} | {r.get('n')} | {fmt(r.get('ctx'))} | {r.get('image') or '-'} | "
                   f"{fmt(r.get('boot_s'), 1)} | {states} | {fmt(st.get('ranks')) if st else '-'} | "
                   f"{fmt(st.get('staging_mib')) + ' MiB' if st else '-'} | {st.get('dir', '-') if st else '-'} | {mems} |")
    out.append("")
    return out


def turn_section(rows):
    g = gate(rows)
    out = ["## Turns: what each resumed from, and its reply against a cold server's", "",
           "| boot | turn | case | expected | resumed from | prompt tokens | cached | newest kept | first token s | "
           "server prefill s | disk read MiB in ms | saves written (MiB, write ms, drain s) | token_sha | cold reference | gate |",
           "|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|"]
    for r in rows:
        if r.get("case") != "turn":
            continue
        d = r.get("disk") or {}
        dr = r.get("drain") or {}
        read = (f"{fmt(mib(d.get('read_bytes')), 0)} in {fmt(d.get('read_ms_last'), 0)}"
                if (d.get("reads") or 0) > 0 else "-")
        saves = (f"{fmt(d.get('writes'))} ({fmt(mib(d.get('written_bytes')), 0)}, {fmt(d.get('write_ms_last'), 0)}, "
                 f"{fmt(dr.get('wait_s'), 1)})" if d else "-")
        verdict, ref = g.get(id(r), ("no reference", None))
        label = LABELS.get(r.get("label"), r.get("label") or "-")
        out.append(f"| {r.get('tag')} | {r.get('case_id')} | {label} | {r.get('expect')} | {source(r)} | "
                   f"{fmt(r.get('prompt_tokens'))} | {fmt(r.get('cached_tokens'))} | {fmt(r.get('expect_cached'))} | "
                   f"{fmt((r.get('ttft_ms') or 0) / 1000 or None)} | {fmt(r.get('prefill_s'))} | {read} | {saves} | "
                   f"{r.get('token_sha') or '-'} | {(ref or {}).get('token_sha') or '-'} | {verdict} |")
    refs = [r for r in rows if r.get("case") == "ref"]
    if refs:
        out += ["", "Cold references (a boot without the disk tier and with --prompt-cache-gib 0, the same messages):", "",
                "| case | prompt tokens | cached | first token s | token_sha | reply sha |", "|---|---:|---:|---:|---|---|"]
        for r in refs:
            out.append(f"| {r.get('case_id')} | {fmt(r.get('prompt_tokens'))} | {fmt(r.get('cached_tokens'))} | "
                       f"{fmt((r.get('ttft_ms') or 0) / 1000 or None)} | {r.get('token_sha') or '-'} | {r.get('sha') or '-'} |")
    out.append("")
    return out


def chain_section(rows, conv):
    turns = [r for r in rows if r.get("case") == "turn" and r.get("conv") == conv and not str(r.get("case_id", "")).endswith("q")]
    if not turns:
        return []
    out = [f"## The long conversation ({conv}, production's tier_chain text) beside production and our earlier window", "",
           "| turn | case | prompt tokens | cached | server prefill s | production (how) | production prefill s | "
           "ours / production | this serve without a disk tier (section 29) |", "|---:|---|---:|---:|---:|---|---:|---:|---:|"]
    for r in turns:
        t = r.get("turn")
        how, prod = PROD_CHAIN.get(t, ("-", None))
        pre = r.get("prefill_s")
        ratio = f"{pre / prod:.2f}x" if prod and pre else "-"
        label = LABELS.get(r.get("label"), r.get("label") or "-") + (f", beside {r['load']} decoding streams" if r.get("load") else "")
        out.append(f"| {t} | {label} | {fmt(r.get('prompt_tokens'))} | {fmt(r.get('cached_tokens'))} | {fmt(pre)} | {how} | "
                   f"{fmt(prod)} | {ratio} | {fmt(LC1_CHAIN.get(t))} |")
    out += ["", "Production's turn 3 follows a SIGKILL and turn 4 a clean restart; this window keeps that order.", ""]
    return out


def save_section(rows):
    loaded = [r for r in rows if r.get("case") == "turn" and r.get("windows")]
    if not loaded:
        return []
    out = ["## A save beside decoding streams: the other streams' decode in four windows", "",
           "| turn | window | seconds | chunk gap median ms | p99 ms | max ms | deltas a second | saved MiB | write ms |",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in loaded:
        d = r.get("disk") or {}
        for name in ("base", "prefill", "reply", "save"):
            w = (r.get("windows") or {}).get(name)
            if not w:
                out.append(f"| {r.get('case_id')} | {name} | - | | | | | | |")
                continue
            out.append(f"| {r.get('case_id')} | {name} | {fmt(w.get('seconds'))} | {fmt(w.get('gap_median_ms'))} | "
                       f"{fmt(w.get('gap_p99_ms'))} | {fmt(w.get('gap_max_ms'))} | {fmt(w.get('deltas_per_s'))} | "
                       f"{fmt(mib(d.get('written_bytes')), 0) if name == 'save' else ''} | "
                       f"{fmt(d.get('write_ms_last'), 0) if name == 'save' else ''} |")
    out += ["", "The base window is the decode before the request; a pause the save adds shows as a max gap in the reply "
            "or save window well past the base window's.", ""]
    return out


def logs_section(rows):
    logs = [r for r in rows if r.get("case") == "logs"]
    if not logs:
        return []
    keys = ("staging_full", "save_skipped", "write_failed", "restore_failed", "check_failed", "unwritten_at_stop",
            "ranks_differ", "disk_world", "disk_layout", "disk_words", "snapshot_size", "ranks_not_asleep", "error_lines")
    out = ["## Rank logs: the disk tier's lines", "", "| boot | rank | " + " | ".join(keys) + " |",
           "|---|---|" + "---:|" * len(keys)]
    for r in logs:
        for name, c in [("r0", r.get("r0"))] + sorted((r.get("workers") or {}).items()):
            if c is None:
                continue
            out.append(f"| {r.get('label') or r.get('tag')} | {name} | " + " | ".join(fmt(c.get(k)) for k in keys) + " |")
        if r.get("learn"):
            out.append(f"\nThe store on disk after {r.get('label') or r.get('tag')}: {fmt(mib(r['learn'].get('bytes')), 0)} MiB in "
                       f"{fmt(r['learn'].get('files'))} files ({r['learn'].get('dir')}).")
    out.append("")
    return out


def behaviours_section(rows):
    """Production's tier behaviours this engine is asked for: cache_salt, the clean stop's flush, ENOSPC."""
    out = ["## Production's tier behaviours", "", "| behaviour | production | here | evidence |", "|---|---|---|---|"]
    salts = [r for r in rows if r.get("case") == "salt"]
    other = next((r for r in salts if r.get("salt")), None)
    control = next((r for r in salts if not r.get("salt")), None)
    if other:
        here = ("refused the field" if other.get("error") else
                "honoured" if (other.get("cached_tokens") or 0) == 0 and (control or {}).get("cached_tokens") else
                "IGNORED: another salt resumed this conversation's state" if (other.get("cached_tokens") or 0) > 0 else "-")
        out.append(f"| a request of another cache_salt (#144) | resumes nothing of another salt | {here} | salted: "
                   f"cached {fmt(other.get('cached_tokens'))} of {fmt(other.get('prompt_tokens'))}; control without a salt: "
                   f"cached {fmt((control or {}).get('cached_tokens'))} |")
    flushed = [r for r in rows if r.get("case") == "turn" and r.get("label") == "flushed"]
    for r in flushed:
        ok = source(r) == "disk" and (r.get("cached_tokens") or 0) >= (r.get("expect_cached") or 0)
        out.append(f"| a save in flight at a clean stop (SIGTERM, #125) is written | written | "
                   f"{'written: resumed from disk' if ok else 'LOST: ' + source(r)} | {r.get('case_id')} cached "
                   f"{fmt(r.get('cached_tokens'))}, newest kept {fmt(r.get('expect_cached'))} |")
    probe = next((r for r in rows if r.get("case") == "logs" and (r.get("extra") or {}).get("part_files") is not None), None)
    if probe:
        en = next((r for r in rows if r.get("case") == "logs" and r.get("label") == "enospc"), {})
        c = en.get("r0") or {}
        out.append(f"| ENOSPC while a save is written | the save fails cleanly, no temporary file left | "
                   f"{fmt(c.get('write_failed'))} write(s) failed, {fmt(c.get('save_skipped'))} skipped, "
                   f"{probe['extra'].get('part_files')} .part file(s) left | inodes (total used free use%) "
                   f"{probe['extra'].get('inodes')} |")
    out.append("")
    return out if len(out) > 5 else []

def render(rows, ranks=3):
    rejected = [(r, verify(r)) for r in rows]
    rejected = [(r, why) for r, why in rejected if why]
    bad = {id(r) for r, _ in rejected}
    kept = [r for r in rows if id(r) not in bad]
    failed = failures(kept, ranks)
    lines = ["# GLM conversation states on disk at TP=3 (--learn-conversations): resumes against cold replies", ""]
    lines.append(f"## Disk tier checks failed: {len(failed)}")
    lines.append("")
    for r, why in failed:
        lines.append(f"- {r.get('tag')} {r.get('case_id') or r.get('case')} {r.get('label') or ''}: {why}")
    lines.append("")
    lines.append(f"## Rejected rows: {len(rejected)}")
    lines.append("")
    for r, why in rejected:
        lines.append(f"- {r.get('tag')} {r.get('case')} {r.get('case_id') or '-'}: {' '.join(why)} (prompt_tokens "
                     f"{r.get('prompt_tokens')}, tokenized {r.get('tokenized_tokens')}, cached {r.get('cached_tokens')}, "
                     f"error {r.get('error')})")
    lines.append("")
    convs = []
    for r in kept:
        if r.get("case") == "turn" and r.get("conv") and r["conv"] not in convs:
            convs.append(r["conv"])
    chains = [c for c in convs if any(r.get("conv") == c and r.get("kind") == "chain" for r in kept)] or [
        c for c in convs if c.upper().startswith("L")]
    lines += boot_section(kept) + turn_section(kept)
    for c in chains:
        lines += chain_section(kept, c)
    lines += behaviours_section(kept) + save_section(kept) + logs_section(kept)
    return "\n".join(lines), len(rejected), len(failed)


def summary(rows):
    """Median first token by case label over the disk arm's turns (for a one-line report)."""
    by = {}
    for r in rows:
        if r.get("case") == "turn" and not verify(r) and r.get("ttft_ms") is not None:
            by.setdefault(r.get("label"), []).append(r["ttft_ms"] / 1000)
    return {k: round(statistics.median(v), 2) for k, v in by.items()}


def main(argv):
    args = list(argv[1:])
    ranks = 3
    if "--ranks" in args:
        i = args.index("--ranks")
        ranks = int(args[i + 1])
        del args[i:i + 2]
    if not args:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2

    try:
        rows = load_rows(args)
    except (OSError, ValueError) as exc:
        print(f"disk_table: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print("disk_table: no rows", file=sys.stderr)
        return 2
    text, n_rejected, n_failed = render(rows, ranks)
    print(text)
    if n_rejected:
        return 1
    return 3 if n_failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
