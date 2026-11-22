#!/usr/bin/env python3
"""score114.py [--q114 DIR] - queue114 (scripts/queues/queue114.sh): the targeted rerun of the one cell queue113 held both arms on.

DIR holds dec-<label>/SC8.jsonl (sampled code at 8 clients), one row a round as the queue writes them: agg_tok_s and sha (the reply hash list). Labels:
the control c1..c6, arm T t1..t6, arm X x1..x6, eighteen boots. This scorer reads that one file itself (score91's boot() wants the full f91-c layout,
and this queue writes no other cell) and uses the same row keys, so a row shape that differs from the queue's cannot pass here.

THE RULES BELOW ARE FIXED BY THE PARENT, WRITTEN BEFORE ANY ROW EXISTED:
  Q1 BOOTS: six control and six a arm. A missing or unreadable boot makes every clause that needs it NOT DECIDED, never a pass.
  Q2 DIGESTS: the eighteen boots' reply digests for the cell are ONE value (the sorted set of every round's sha). A boot whose value differs FAILS
     and the program exits 1, before the noise or the verdict lines: DIGESTS DIFFER dominates both.
  Q3 NOISE: the control's own six-boot spread, max minus min over mean, as a percentage. ABOVE 5% the run prints NOT DECIDED: NOISE with that
     figure and no verdict for either arm, because a 2% delta inside a 10% spread is not a measurement. Exactly 5% is not above it.
  Q4 VERDICT, per arm, independently: change = 1 - arm mean / control mean for this cell's tokens a second (positive is slower). The cold and
     four-client readings are queue113's and are not repeated here: T's cold mean was -7.13% and X's -2.83%, and at four clients every cell was
     inside half a percent, so this run decides only the 1.0% limit of the cell both arms held on. ADOPT when the arm is not more than 1.0% slower
     (exactly 1.0% is not more than it). HOLD when it is.
  Q5 BUNDLE: T and X are decided independently; the T and X lines move from scripts/env/dev.env's candidates into scripts/env/prod.env's recipe
     only when BOTH arms ADOPT.
Exit code 1 only on a Q2 difference; everything else prints and exits 0.
"""
import argparse
import json
import pathlib
import statistics as st
import sys

CELL = ("SC", 8)
LIMIT = 0.010   # more than 1.0% slower is over the limit
NOISE = 0.050   # the control's own spread, max minus min over mean, above which the run has no verdict
EPS = 1e-9      # exactly at a limit is not over it
CTL = tuple(f"c{i}" for i in range(1, 7))
ARMS = {"T": ("t1", "t2", "t3", "t4", "t5", "t6"), "X": ("x1", "x2", "x3", "x4", "x5", "x6")}


def rows(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def boot(d, label):
    """What one boot measured in the cell: mean agg_tok_s over its rounds, and its reply digest (the sorted set of every round's sha)."""
    rs = rows(pathlib.Path(d) / f"dec-{label}" / f"{CELL[0]}{CELL[1]}.jsonl")
    if not rs:
        return None, None
    return st.mean(r["agg_tok_s"] for r in rs), tuple(sorted({tuple(r["sha"]) for r in rs}))


def spread(v):
    return (max(v) - min(v)) / st.mean(v)


def decide(dirp):
    """What the rows in `dirp` decide, as a dict the tests drive: missing, differ, noise (the control's spread or None), arms, bundle, rc."""
    val, dig, missing = {}, {}, []
    for label in CTL + tuple(l for a in ARMS.values() for l in a):
        v, g = boot(dirp, label)
        if v is None:
            missing.append(label)
            continue
        val[label], dig[label] = v, g
    if missing:
        return {"missing": missing, "differ": False, "noise": None, "arms": {}, "rc": 0,
                "bundle": "Q5 BUNDLE: NOT DECIDED: boot(s) " + ", ".join(missing) + " have no cell"}
    uniq = {g for g in dig.values()}
    if len(uniq) != 1 or None in uniq:
        return {"missing": [], "differ": True, "noise": None, "arms": {}, "rc": 1,
                "bundle": "Q5 BUNDLE: DIGESTS DIFFER, exit 1: no verdict on either arm"}
    ctl = [val[l] for l in CTL]
    ctl_spread = spread(ctl)
    if ctl_spread > NOISE + EPS:
        return {"missing": [], "differ": False, "noise": ctl_spread, "arms": {}, "rc": 0,
                "bundle": f"Q5 BUNDLE: NOT DECIDED: NOISE: the control's six-boot spread is {ctl_spread:.2%}, above {NOISE:.0%}, so the cell has no verdict"}
    arms = {}
    for arm, labels in ARMS.items():
        c, a = st.mean(ctl), st.mean(val[l] for l in labels)
        ch = 1 - a / c  # positive is slower for a tokens-a-second cell
        arms[arm] = {"labels": labels, "ctl": ctl, "boots": [val[l] for l in labels], "change": ch,
                     "verdict": "HOLD" if ch > LIMIT + EPS else "ADOPT"}
    if all(a["verdict"] == "ADOPT" for a in arms.values()):
        bundle = "Q5 BUNDLE: ADOPTED: both arms ADOPT, the T and X lines move from dev.env's candidates into prod.env's recipe in the same commit as these rows"
    else:
        bundle = "Q5 BUNDLE: HELD: " + ", ".join(f"{k} {v['verdict']}" for k, v in arms.items())
    return {"missing": [], "differ": False, "noise": None, "arms": arms, "rc": 0, "bundle": bundle}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q114", default="work/q114/f114-c")
    a = ap.parse_args()
    res = decide(a.q114)
    print(f"== score114: q114 {a.q114}, cell sampled code at 8 clients")
    print(f"== Q1 boots: {len(CTL)} control and {len(ARMS['T'])} + {len(ARMS['X'])} arm expected; missing: {res['missing'] or 'none'}")
    if res["missing"]:
        print("== Q3 noise: NOT DECIDED (no control boots to spread)")
    elif res["differ"]:
        print("== Q2 digests: DIFFER, exit 1 (the noise and verdict lines are not computed)")
    elif res["noise"] is not None:
        print(f"== Q3 noise: the control's six boots spread {res['noise']:.2%}, above the {NOISE:.0%} clause")
    else:
        print(f"== Q2 digests: one value across the eighteen boots")
        print(f"== Q3 noise: control spread {spread(res['arms']['T']['ctl']):.2%}, inside the {NOISE:.0%} clause")
        for arm, r in res["arms"].items():
            print(f"{arm} sampled code at 8 clients: ctl {st.mean(r['ctl']):.2f} ({' '.join(f'{x:.1f}' for x in r['ctl'])}, spread {spread(r['ctl']):.2%}) | "
                  f"arm {st.mean(r['boots']):.2f} ({' '.join(f'{x:.1f}' for x in r['boots'])}, spread {spread(r['boots']):.2%}) | {r['change']:+.2%} slower | {r['verdict']}")
    print("== Q4 decisions and Q5 bundle")
    print(res["bundle"])
    return res["rc"]


if __name__ == "__main__":
    sys.exit(main())
