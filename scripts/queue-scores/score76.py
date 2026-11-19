#!/usr/bin/env python3
"""score76.py [ROWS_DIR] - queue76 block D: greedy decode at 1 / 2 / 4 clients on eight fresh boots, f5 rs5 rs6 f6 f7 rs7 rs8 f8.

f is the final recipe N (the four prompt-pass switches of queue75 block A on the recipe), rs is N with TF_GLM_REQUEST_STARTS=1. For each cell: the eight boots'
aggregate tok/s, the mean of the four f boots and of the four rs boots, rs over f, the spread of the f boots (max over min) and whether the rs mean lies inside
the f boots' range; and whether every boot's reply set is the same. Rounds and tokens a round are compared as well.
"""
import json
import os
import statistics as st
import sys

D = sys.argv[1] if len(sys.argv) > 1 else "docs/audit-2026-11-12/queue-rows/queue76"
BOOTS = ("f5", "rs5", "rs6", "f6", "f7", "rs7", "rs8", "f8")


def rows(p):
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


def cell(boot, kind, n):
    r = rows(f"{D}/f76-d/dec-{boot}/{kind}{n}.jsonl")
    if not r:
        return None
    return {"agg": st.mean(x["agg_tok_s"] for x in r), "rounds": sum(x.get("draft_rounds") or 0 for x in r),
            "ms": st.mean(x["ms_per_round"] for x in r if x.get("ms_per_round")), "sha": tuple(sorted({tuple(x["sha"]) for x in r}))}


print("cell | boots " + " ".join(BOOTS) + " | f mean | rs mean | rs over f | f spread | rs mean inside the f range | rounds f / rs | ms a round f / rs | reply sets")
for kind, label in (("P", "prose"), ("C", "code")):
    for n in (1, 2, 4):
        c = {b: cell(b, kind, n) for b in BOOTS}
        if not all(c.values()):
            continue
        f = [c[b]["agg"] for b in BOOTS if b.startswith("f")]
        r = [c[b]["agg"] for b in BOOTS if b.startswith("rs")]
        inside = min(f) <= st.mean(r) <= max(f)
        rf = [c[b]["rounds"] for b in BOOTS if b.startswith("f")]
        rr = [c[b]["rounds"] for b in BOOTS if b.startswith("rs")]
        mf = st.mean(c[b]["ms"] for b in BOOTS if b.startswith("f"))
        mr = st.mean(c[b]["ms"] for b in BOOTS if b.startswith("rs"))
        sets = len({c[b]["sha"] for b in BOOTS})
        print(f"{label} {n} | " + " ".join(f"{c[b]['agg']:.2f}" for b in BOOTS) + f" | {st.mean(f):.2f} | {st.mean(r):.2f} | {st.mean(r) / st.mean(f) - 1:+.2%} | "
              f"{max(f) / min(f) - 1:.2%} | {inside} | {st.mean(rf):.0f} / {st.mean(rr):.0f} | {mf:.2f} / {mr:.2f} | {sets}")
