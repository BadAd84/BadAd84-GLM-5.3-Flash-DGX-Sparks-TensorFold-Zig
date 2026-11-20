#!/usr/bin/env python3
"""decide81.py [--rows81 DIR] [--rows82 DIR] [--apply ENVFILE...] - queue81 and queue82: which exchange-wire settings join the final recipe N.

Rows (scripts/queues/queue81.sh and queue82.sh, the same instrument): DIR/rows.jsonl (case cold: tag, target_tokens, rep, ttft_ms, token_sha), DIR/<arm>/chain.jsonl (tag c74),
DIR/dec-<arm>/{P,C}<clients>.jsonl. Every arm is N with request starts plus one setting, one boot; the controls are c1 c2 c3 (queue81) and c4 c5 (queue82), the same recipe, pooled.
Two kinds of setting, each with its own rule, written before the rows were read:

  NCCL settings (q4 n8 ch bf qn n2 pp p8: they change how the prompt exchanges move). Joins only when all of these hold:
    1. replies: every cold request, conversation turn and decode cell has the controls' digests;
    2. cold: at least 1.0% under the controls' mean at two of the three sizes (8k, 32k, 120k) and never over the slowest control;
    3. warm: the growing conversation's turns 2 to 8 and its first turn are not over the controls' slowest;
    4. decode (the cells it has, prose and code at 1 and 4 clients): none under the controls' slowest boot.
  Wire settings (mb: TF_TP_MAILBOX_MAX_KB=1024, rf: TF_TP_ROCE_FAST=1, mf: both; they change the decode all-gathers). Joins only when all of these hold:
    1. replies as above;
    2. cold and warm as 3 above (the cold prompt must not get slower: never over the slowest control at any size, turns 2 to 8 and first turn not over the slowest control);
    3. decode, ten cells (prose and code at 1, 2, 4, 6 and 8 clients): the mean over the cells of the arm over the controls' mean is at least +1.0%, at least seven cells read above
       the controls' mean, and no cell is under the controls' slowest boot.
At most one NCCL setting (the largest mean cold gain) and one wire setting (the largest mean decode gain) join, so that a joint effect nobody measured is two settings and not
more; queue77's final confirmation measures the whole of N against the committed recipe at every level. With --apply, each ENVFILE's NEWX line gains the flags once.
"""
import json
import os
import re
import statistics as st
import sys

FLAGS = {
    "q4": "-e NCCL_IB_QPS_PER_CONNECTION=4",
    "n8": "-e NCCL_MIN_NCHANNELS=8 -e NCCL_MAX_NCHANNELS=8",
    "ch": "-e NCCL_P2P_NET_CHUNKSIZE=524288",
    "bf": "-e NCCL_BUFFSIZE=16777216",
    "qn": "-e NCCL_IB_QPS_PER_CONNECTION=4 -e NCCL_MIN_NCHANNELS=8 -e NCCL_MAX_NCHANNELS=8",
    "n2": "-e NCCL_MIN_NCHANNELS=2 -e NCCL_MAX_NCHANNELS=2",
    "pp": "-e NCCL_NCHANNELS_PER_NET_PEER=4",
    "p8": "-e NCCL_MIN_NCHANNELS=8 -e NCCL_MAX_NCHANNELS=8 -e NCCL_NCHANNELS_PER_NET_PEER=8",
    "mb": "-e TF_TP_MAILBOX_MAX_KB=1024",
    "rf": "-e TF_TP_ROCE_FAST=1",
    "mf": "-e TF_TP_MAILBOX_MAX_KB=1024 -e TF_TP_ROCE_FAST=1",
}
NCCL = ("q4", "n8", "ch", "bf", "qn", "n2", "pp", "p8")
WIRE = ("mb", "rf", "mf")
CONTROLS = {"c1": "81", "c2": "81", "c3": "81", "c4": "82", "c5": "82"}
ARMS = {a: "81" for a in ("mb", "q4", "n8", "ch", "bf", "qn", "n2", "pp", "p8")}
ARMS.update({"rf": "82", "mf": "82"})
SIZES = (8000, 32000, 120000)
KINDS = ("P", "C")
LEVELS = (1, 2, 4, 6, 8)

args = sys.argv[1:]
apply_to = []
if "--apply" in args:
    cut = args.index("--apply")
    apply_to = args[cut + 1:]
    args = args[:cut]
DIRS = {"81": os.path.expanduser("~/bench/f81-c"), "82": os.path.expanduser("~/bench/f82-c")}
for i, a in enumerate(args):
    if a == "--rows81":
        DIRS["81"] = args[i + 1]
    if a == "--rows82":
        DIRS["82"] = args[i + 1]


def jl(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


COLD = {q: [r for r in jl(f"{d}/rows.jsonl") if r.get("case") == "cold"] for q, d in DIRS.items()}


def where(arm):
    return ARMS.get(arm) or CONTROLS[arm]


def cold(arm, size):
    v = [r["ttft_ms"] for r in COLD[where(arm)] if r["tag"] == arm and r["target_tokens"] == size]
    return st.mean(v) if v else None


def cold_sha(arm, size):
    return {(r["rep"], r["token_sha"]) for r in COLD[where(arm)] if r["tag"] == arm and r["target_tokens"] == size}


def chain(arm):
    return [r for r in jl(f"{DIRS[where(arm)]}/{arm}/chain.jsonl") if r.get("tag") == "c74"]


def dec(arm, kind, n):
    r = jl(f"{DIRS[where(arm)]}/dec-{arm}/{kind}{n}.jsonl")
    if not r:
        return None
    return {"agg": st.mean(x["agg_tok_s"] for x in r), "sha": tuple(sorted({tuple(x["sha"]) for x in r}))}


ctl = [c for c in CONTROLS if cold(c, SIZES[0]) is not None]
print("controls with rows:", " ".join(ctl))
if len(ctl) < 2:
    print("NOT DECIDED: fewer than two controls")
    sys.exit(0)


def pooled_cold(size):
    v = [cold(c, size) for c in ctl]
    return st.mean(v), min(v), max(v)


ctl_chain = {c: chain(c) for c in ctl if chain(c)}
first_c = [c[0]["ttft_ms"] for c in ctl_chain.values()]
warm_c = [st.mean(x["ttft_ms"] for x in c[1:]) for c in ctl_chain.values()]


def verdict(arm):
    notes = []
    sizes_ok = [cold(arm, s) is not None for s in SIZES]
    if not all(sizes_ok) or not chain(arm):
        return None, ["rows missing"], 0.0
    # replies
    same = True
    for s in SIZES:
        ref = {c: cold_sha(c, s) for c in ctl}
        if len({frozenset(v) for v in ref.values()}) != 1 or cold_sha(arm, s) != next(iter(ref.values())):
            same = False
    base = next(iter(ctl_chain.values()))
    ch = chain(arm)
    n = min(len(ch), len(base))
    same = same and n > 0 and all(ch[k]["token_sha"] == base[k]["token_sha"] for k in range(n))
    for kind in KINDS:
        for lv in LEVELS:
            d = dec(arm, kind, lv)
            if d is None:
                continue
            refs = {dec(c, kind, lv)["sha"] for c in ctl if dec(c, kind, lv)}
            if len(refs) > 1 or (refs and d["sha"] not in refs):
                same = False
    notes.append(f"replies equal {same}")
    # cold
    gains, never_over = [], True
    for s in SIZES:
        mean, lo, hi = pooled_cold(s)
        gains.append(1 - cold(arm, s) / mean)
        never_over = never_over and cold(arm, s) <= hi
    wins = sum(g >= 0.01 for g in gains)
    notes.append("cold " + " ".join(f"{g:+.2%}" for g in gains) + f" (at least 1.0% at {wins} of 3 sizes, never over the slowest control {never_over})")
    # warm
    first_ok = ch[0]["ttft_ms"] <= max(first_c)
    warm = st.mean(x["ttft_ms"] for x in ch[1:])
    warm_ok = warm <= max(warm_c)
    notes.append(f"first turn {ch[0]['ttft_ms']} ms (controls {min(first_c)} to {max(first_c)}), turns 2+ {warm:.0f} ms (controls {min(warm_c):.0f} to {max(warm_c):.0f})")
    # decode
    rel, above, under = [], 0, 0
    cells = 0
    for kind in KINDS:
        for lv in LEVELS:
            d = dec(arm, kind, lv)
            cs = [dec(c, kind, lv)["agg"] for c in ctl if dec(c, kind, lv)]
            if d is None or not cs:
                continue
            cells += 1
            m = st.mean(cs)
            rel.append(d["agg"] / m - 1)
            above += d["agg"] > m
            under += d["agg"] < min(cs)
    notes.append(f"decode {cells} cells: mean {st.mean(rel):+.2%}, above the controls' mean in {above}, under the slowest control in {under}" if rel else "decode: no cells")
    if arm in NCCL:
        ok = same and wins >= 2 and never_over and first_ok and warm_ok and under == 0
        return ok, notes, st.mean(gains)
    ok = same and never_over and first_ok and warm_ok and cells >= 10 and st.mean(rel) >= 0.01 and above >= 7 and under == 0
    return ok, notes, st.mean(rel) if rel else 0.0


winners = {"nccl": None, "wire": None}
for arm in list(NCCL) + list(WIRE):
    ok, notes, score = verdict(arm)
    if ok is None:
        print(f"{arm}: NOT DECIDED ({'; '.join(notes)})")
        continue
    print(f"{arm} ({FLAGS[arm]}): {'PASSES' if ok else 'no'} | " + " | ".join(notes))
    if ok:
        kind = "nccl" if arm in NCCL else "wire"
        if winners[kind] is None or score > winners[kind][1]:
            winners[kind] = (arm, score)

adopt = [FLAGS[w[0]] for w in winners.values() if w]
if adopt:
    print("ADD " + " ".join(adopt))
for path in apply_to:
    text = open(path, encoding="utf-8").read()
    m = re.search(r'^NEWX="([^"]*)"', text, re.M)
    if not m or not adopt:
        continue
    add = " ".join(f for f in adopt if f not in m.group(1))
    if add:
        open(path, "w", encoding="utf-8", newline="\n").write(text[:m.end(1)] + " " + add + text[m.end(1):])
        print(f"{path}: NEWX gains {add}")
