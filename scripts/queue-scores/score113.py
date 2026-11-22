#!/usr/bin/env python3
"""score113.py [--q113 DIR] - queue113 (scripts/queues/queue113.sh): the T/X split that queue105's HOLD asks for.

DIR holds, in queue91's row layout, rows.jsonl (the cold requests: case "cold", tag <label>, target_tokens 8000 or 32000, ttft_ms, token_sha) and
dec-<label>/{P,C,SP,SC}{4,8}.jsonl (agg_tok_s a row, sha a row). The rows and the digests are read with score91.py's own boot(), which is the one
owner of that layout. Labels: the control c1..c8 (the recipe with neither T nor X), arm T t1..t4, arm X x1..x4 - sixteen boots, each one measuring
BOTH client levels and the cold prompt, mirrored c1 t1 x1 c2 c3 x2 t2 c4 t3 x3 c5 c6 x4 t4 c7 c8 so drift lands on every group.

THE RULES BELOW ARE FIXED BY THE PARENT, WRITTEN BEFORE ANY ROW EXISTED:
  Q1 BOOTS: eight control and four a arm. A missing or unreadable boot, or a boot with no row for a cell, makes every clause that needs it NOT
     DECIDED, never a pass.
  Q2 DIGESTS: for each of the ten cells (cold 8k, cold 32k, and the four decode kinds at each of 4 and 8 clients) the sixteen boots' reply
     digests are ONE value. A boot whose value differs FAILS and the program exits 1: the arms are claimed bit-exact against the recipe and this is
     the check of that claim.
  Q3 CHANGES: an arm's value for a cell is the mean over its boots of that cell's value; the control's is the mean over the eight control boots.
     change = arm / control - 1 for a decode cell's tokens a second (positive is slower) and for a cold cell's first token (positive is slower):
     one sign, positive means the arm is worse. A cell is over the limit when change > 1.0% (a cell exactly at the limit is not over it). Each
     cell prints both groups' boots and each group's spread (max - min over mean).
  Q4 DECISION, per arm, independently:
     ADOPT  when no decode cell at either level is more than 1.0% slower AND the mean of the two cold cells is at least 1.0% FASTER
            (cold mean <= -1.0% in Q3's sign: the arm's first token is 1.0% or more lower).
     HOLD   when some decode cell is more than 1.0% slower (its cold mean may be anything positive or better than nothing) or when nothing is over
            the limit but the cold mean is under the 1.0% bar (positive, but not the 1.0% that adoption needs).
     REJECT when the cold mean is not positive (the arm's first token is not faster at all).
     A digest difference overrides every verdict: DIGESTS DIFFER, exit 1.
  Q5 BUNDLE: T and X are decided independently; the ten candidate lines move into scripts/env/prod.env only when BOTH arms ADOPT. One ADOPT and one
     not is a HOLD of the bundle naming the arm that fell short.

Exit code 1 only on a Q2 difference; everything else prints and exits 0.
"""
import argparse
import importlib.util
import pathlib
import statistics as st
import sys

KINDS = (("P", "greedy prose"), ("C", "greedy code"), ("SP", "sampled prose"), ("SC", "sampled code"))
LEVELS = (4, 8)
COLD = (8000, 32000)
LIMIT = 0.010   # a decode cell more than 1.0% slower is over the limit
BAR = 0.010     # the cold mean an ADOPT needs, 1.0% faster
EPS = 1e-9      # exactly at a limit is not over it; 101.0/100.0-1 is 1.0000000000000009e-2 in doubles
CTL = tuple(f"c{i}" for i in range(1, 9))
ARMS = {"T": ("t1", "t2", "t3", "t4"), "X": ("x1", "x2", "x3", "x4")}

_S91 = None


def s91():
    """score91.py, whose boot() owns queue91's row layout (found above this file, so a scratch copy still finds it)."""
    global _S91
    if _S91 is None:
        for p in pathlib.Path(__file__).resolve().parents:
            f = p / "scripts/queue-scores/score91.py"
            if f.exists():
                spec = importlib.util.spec_from_file_location("score91", f)
                _S91 = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(_S91)
                break
        else:
            raise SystemExit("score113: scripts/queue-scores/score91.py not found above this file")
    return _S91


def slower(cell, arm, ctl):
    """How much slower the arm is, positive in one sign for both kinds: a first token up by that much, or tokens a second down by that much of the
    control's rate."""
    return arm / ctl - 1 if cell[0] == "cold" else 1 - arm / ctl


def spread(v):
    return (max(v) - min(v)) / st.mean(v) * 100 if len(v) > 1 else 0.0


def decode_cells():
    return [(k, name, n) for n in LEVELS for k, name in KINDS]


def digest_of(dig, cell):
    """One cell's reply digest as a boot measured it: cold keys carry a row a rep, so the cell's value is the sorted tuple of its reps."""
    if cell[0] == "cold":
        reps = sorted(k[2] for k in dig if k[0] == "cold" and k[1] == cell[1] and k[2] is not None)
        return tuple(dig[("cold", cell[1], r)] for r in reps)
    return dig.get(cell)


def decide(dirp):
    """What the rows in `dirp` decide. Returns a dict: missing (labels), digests (per-cell not-one-value list), arms (per-arm numbers and verdict),
    bundle (line), rc (1 only on a digest difference). stdout's wording is main()'s; this is what the tests drive."""
    d = pathlib.Path(dirp)
    b91 = s91().boot
    val, dig, missing = {}, {}, []
    for label in CTL + tuple(l for a in ARMS.values() for l in a):
        if not (d / "rows.jsonl").exists() or not all((d / f"dec-{label}" / f"{k}{n}.jsonl").exists() for k, _, n in decode_cells()):
            missing.append(label)
            continue
        v, g = b91(str(d), label)
        val[label], dig[label] = v, g
    labels = list(val)
    cells = [("cold", s) for s in COLD] + [("dec", k, n) for k, _, n in decode_cells()]
    short = sorted({c for l in labels for c in cells if c not in val[l]}) if not missing else []
    if missing or short:
        return {"missing": missing, "short": short, "digests": [], "arms": {},
                "bundle": "Q5 BUNDLE: NOT DECIDED: boot(s) " + (", ".join(missing) if missing else "a cell") + " missing",
                "rc": 0}
    differ = []
    for cell in cells:
        vals = {l: digest_of(dig[l], cell) for l in labels}
        uniq = {v for v in vals.values()}
        if len(uniq) != 1 or None in uniq:
            differ.append((cell, vals))
    arms = {}
    for arm, arm_labels in ARMS.items():
        changes = {}
        for cell in cells:
            c, a = st.mean(val[l][cell] for l in CTL), st.mean(val[l][cell] for l in arm_labels)
            changes[cell] = slower(cell, a, c)
        over = [cells_ for cells_, ch in changes.items() if ch > LIMIT + EPS]
        cold_mean = st.mean(changes[("cold", s)] for s in COLD)  # positive is slower: the cold mean an ADOPT needs is <= -BAR
        if differ:
            verdict = "NOT DECIDED (digests)"
        elif over:
            verdict = "HOLD"
        elif cold_mean <= -BAR + EPS:
            verdict = "ADOPT"
        elif cold_mean < -EPS:
            verdict = "HOLD"
        else:
            verdict = "REJECT"
        arms[arm] = {"labels": arm_labels, "values": val, "changes": changes, "over": over, "cold_mean": cold_mean, "verdict": verdict}
    if differ:
        bundle = "Q5 BUNDLE: DIGESTS DIFFER, exit 1: no verdict on either arm"
    elif len(arms) == 2 and all(a["verdict"] == "ADOPT" for a in arms.values()):
        bundle = "Q5 BUNDLE: ADOPTED: both arms ADOPT, the ten lines move from dev.env's candidates into prod.env's recipe in the same commit as these rows"
    elif len(arms) == 2 and all(a["verdict"] == "REJECT" for a in arms.values()):
        bundle = "Q5 BUNDLE: REJECTED: neither arm's cold mean is positive"
    else:
        fell = ", ".join(f"{k} {v['verdict']}" for k, v in arms.items())
        bundle = f"Q5 BUNDLE: HELD: {fell}"
    return {"missing": missing, "short": short, "digests": differ, "arms": arms, "bundle": bundle, "rc": 1 if differ else 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q113", default="work/q113/f113-c")
    a = ap.parse_args()
    res = decide(a.q113)
    print(f"== score113: q113 {a.q113}")
    print(f"== Q1 boots: {len(CTL)} control and {len(ARMS['T'])} + {len(ARMS['X'])} arm expected; missing: {res['missing'] or 'none'}"
          + (f"; a boot without every cell: {res['short']}" if res["short"] else ""))
    if res["missing"] or res["short"]:
        print("== Q2 digests: NOT DECIDED (no rows to compare)")
        print(res["bundle"])
        return res["rc"]
    print(f"== Q2 digests: {len(res['digests'])} cell(s) whose sixteen boots are not one value")
    for cell, vals in res["digests"][:4]:
        print("   ", cell, ", ".join(f"{l}={str(v)[:32]}" for l, v in vals.items()))
    print("== Q3 changes: arm over control minus one, positive is slower; the decode limit is 1.0%, the cold bar is -1.0% (a 1.0% faster first token)")
    for arm, r in res["arms"].items():
        for cell, ch in r["changes"].items():
            key = ("cold", cell[1]) if cell[0] == "cold" else cell
            ctl_b = [r["values"][l][key] for l in CTL]
            arm_b = [r["values"][l][key] for l in r["labels"]]
            name = f"cold {cell[1] // 1000}k first token" if cell[0] == "cold" else f"{dict(KINDS)[cell[1]]} at {cell[2]} clients"
            print(f"{arm} {name:34s} ctl {st.mean(ctl_b):8.2f} ({' '.join(f'{x:.1f}' for x in ctl_b)}, spread {spread(ctl_b):5.2f}%) | "
                  f"arm {st.mean(arm_b):8.2f} ({' '.join(f'{x:.1f}' for x in arm_b)}, spread {spread(arm_b):5.2f}%) | {ch:+.2%} slower")
        print(f"{arm} cold mean {r['cold_mean']:+.2%} slower; cells over the 1.0% limit: {[c for c in r['over']] or 'none'}; VERDICT {r['verdict']}")
    print("== Q4 decisions and Q5 bundle")
    print(res["bundle"])
    return res["rc"]


if __name__ == "__main__":
    sys.exit(main())
