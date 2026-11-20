#!/usr/bin/env python3
"""decide79.py [ROWS_DIR] [--apply ENVFILE...] - queue79's decode screens: the table, and the rule that decides what joins the final recipe N.

Rows: ROWS_DIR/dec-<boot>/{P,C}<clients>.jsonl for the boots n1 n2 (N alone) and k1 k2 of each candidate k (x: TF_GLM_OVN_X3_NC=2, i: TF_GLM_INDEX_CUDA=all,
d: TF_GLM_OVN_DECODE_INDEX=33, u: TF_GLM_OVN_DRAFT_CUTS=1:0.15, the draft chain's cut below the recipe's 0.3), greedy decode at 1, 2, 4, 6 and 8 clients on prose and
code (ten cells), as written by scripts/queues/queue79.sh. A candidate is decided on its own two boots and the two n boots; a missing boot leaves only that candidate
undecided.

The rule (written before the rows were read). A candidate joins N only when all of these hold, against the mean of the two n boots:
  1. replies: every cell's reply digests are the same set in the candidate's two boots and the two n boots (greedy replies never depend on the drafts);
  2. the mean over the ten cells of the candidate's pair mean over the controls' mean is at least +1.0%, and each of its two boots alone is at or above the controls' mean;
  3. at least seven of the ten cells read above the controls' mean, and no cell's pair mean is below the controls' slower boot.
With --apply, each ENVFILE (queue77.env, queue78.env) gets the winners' "-e NAME=VALUE" appended to its NEWX line; the final confirmation of queue77 then measures N
with them against the committed recipe, so a wrong adoption shows there at every level.
"""
import json
import os
import re
import statistics as st
import sys

CANDIDATES = {"x": "-e TF_GLM_OVN_X3_NC=2", "i": "-e TF_GLM_INDEX_CUDA=all", "d": "-e TF_GLM_OVN_DECODE_INDEX=33", "u": "-e TF_GLM_OVN_DRAFT_CUTS=1:0.15"}
LEVELS = (1, 2, 4, 6, 8)
args = [a for a in sys.argv[1:] if a != "--apply"]
apply_to = []
if "--apply" in sys.argv[1:]:
    cut = sys.argv.index("--apply")
    apply_to = sys.argv[cut + 1:]
    args = [a for a in sys.argv[1:cut]]
D = args[0] if args else os.path.expanduser("~/bench/f79-d")


def rows(p):
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


def cell(boot, kind, n):
    r = rows(f"{D}/dec-{boot}/{kind}{n}.jsonl")
    if not r:
        return None
    return {"agg": st.mean(x["agg_tok_s"] for x in r), "sha": tuple(sorted({tuple(x["sha"]) for x in r}))}


CELLS = [(k, n) for k in ("P", "C") for n in LEVELS]
CONTROLS = ("n1", "n2")
data = {b: {c: cell(b, *c) for c in CELLS} for b in CONTROLS + tuple(k + s for k in CANDIDATES for s in "12")}


def have(boots, c):
    return all(data[b][c] for b in boots)


print("cell | n1 n2 | candidates' two boots | candidates' pair mean over the n mean")
for c in CELLS:
    if not have(CONTROLS, c):
        print(f"{c[0]}{c[1]} | controls missing")
        continue
    nm = st.mean(data[b][c]["agg"] for b in CONTROLS)
    parts = [" ".join(f"{data[b][c]['agg']:.2f}" for b in CONTROLS)]
    rel = []
    for k in CANDIDATES:
        boots = (k + "1", k + "2")
        if have(boots, c):
            parts.append(" ".join(f"{data[b][c]['agg']:.2f}" for b in boots))
            rel.append(f"{k} {st.mean(data[b][c]['agg'] for b in boots) / nm - 1:+.2%}")
        else:
            parts.append(f"{k} missing")
    print(f"{c[0]}{c[1]} | " + " | ".join(parts) + " | " + " ".join(rel))

adopt = []
for k, flag in CANDIDATES.items():
    mine = (k + "1", k + "2")
    needed = CONTROLS + mine
    missing = [c for c in CELLS if not have(needed, c)]
    if missing:
        print(f"{k}: NOT DECIDED, {len(missing)} cells have a missing boot")
        continue
    same = all(len({data[b][c]["sha"] for b in needed}) == 1 for c in CELLS)
    rel, below_slow, above = [], 0, 0
    boots = {b: [] for b in mine}
    for c in CELLS:
        nvals = [data[b][c]["agg"] for b in CONTROLS]
        nm = st.mean(nvals)
        pair = st.mean(data[b][c]["agg"] for b in mine)
        rel.append(pair / nm - 1)
        above += pair > nm
        below_slow += pair < min(nvals)
        for b in boots:
            boots[b].append(data[b][c]["agg"] / nm - 1)
    mean_rel = st.mean(rel)
    each_ok = all(st.mean(v) >= 0 for v in boots.values())
    ok = same and mean_rel >= 0.01 and each_ok and above >= 7 and below_slow == 0
    print(f"{k} ({flag}): {'ADOPT' if ok else 'no'} | replies equal {same} | mean over cells {mean_rel:+.2%} | each boot at or above {each_ok} | cells above {above}/10 | "
          f"cells below the slower control {below_slow}")
    if ok:
        adopt.append(flag)

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
