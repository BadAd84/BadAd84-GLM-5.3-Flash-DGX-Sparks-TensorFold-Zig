#!/usr/bin/env python3
"""score105.py [--q105 DIR] - queue105 (scripts/queues/queue105.sh): the 8-client confirmation that decides whether queue95's T and X candidate sets enter
scripts/env/prod.env.

DIR holds dec-<label>/{P,C,SP,SC}8.jsonl (and rows.jsonl) in queue91's row layout, labels ca1 ca2 ca3 ca4 (the control, the recipe as committed) and tx1
tx2 tx3 tx4 (T and X together, dev.env's ten candidate lines). The rows and the digests are read with score91.py's own `boot()`, which is the one owner
of that layout: a cell's digest is the sorted set of its rows' `sha` tuples, one value a boot. Queue95 measured both sets PROMOTABLE on the 12 decode
cells at 1, 2 and 4 clients, on the four prompt cells and on the digests, and positive at 6 clients in all four cells; at 8 clients both were bimodal
inside one arm, which is the only thing this queue settles.

THE RULES BELOW ARE FIXED BY THE PARENT, WRITTEN BEFORE ANY ROW EXISTED:
  Q1 BOOTS: four boots a group. A missing or unreadable boot makes every clause that needs it NOT DECIDED, never a pass.
  Q2 DIGESTS: the eight boots' digests for each of the four cells are ONE value (score91's per-cell digest, which is the set of that cell's reply
     hashes). A boot whose value differs from the others FAILS and the program exits 1; the switch set is claimed bit-exact and queue95's K4 read EQUAL.
  Q3 EIGHT-CLIENT CELLS: greedy prose, greedy code, sampled prose, sampled code at 8 clients. A group's value is the mean over its four boots of that
     cell's value. Change = tx mean over ca mean minus one, so positive is slower. PASS when no cell is more than 1.0% slower (a cell exactly at the
     limit is not over it). Print each cell with both groups' boots and each group's spread (max - min over mean), because these cells have run 10%
     spreads before.
  Q4 VERDICT, one line and nothing else:
     PROMOTE T AND X into scripts/env/prod.env (ten lines moved from dev.env's candidates section in the same commit as these rows) when Q1 is
     satisfied, Q2 is one value and Q3 PASSES.
     HOLD when Q3 fails: name the cells over the limit.
     NOT DECIDED when a boot or a cell is missing.
     A Q2 difference overrides: DIGESTS DIFFER, exit 1.
Exit code 1 only on a Q2 difference; everything else prints and exits 0.
"""
import argparse
import importlib.util
import pathlib
import statistics as st
import sys

CELLS = [("P", "greedy prose"), ("C", "greedy code"), ("SP", "sampled prose"), ("SC", "sampled code")]
LIMIT = 0.010
EPS = 1e-9  # a cell exactly at the limit is not over it, and 101.0/100.0-1 is 1.0000000000000009e-2 in doubles
CA, TX = ("ca1", "ca2", "ca3", "ca4"), ("tx1", "tx2", "tx3", "tx4")

_S91 = None


def s91():
    """score91.py, whose boot() is the one owner of queue91's row layout (found above this file, so a scratch copy still finds it)."""
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
            raise SystemExit("score105: scripts/queue-scores/score91.py not found above this file")
    return _S91


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q105", default="work/pp105/f105-c")
    a = ap.parse_args()
    d = pathlib.Path(a.q105)
    b91 = s91().boot
    print(f"== score105: q105 {d}")
    val, dig, missing = {}, {}, []
    for label in CA + TX:
        if not all((d / f"dec-{label}" / f"{k}8.jsonl").exists() for k, _ in CELLS):
            missing.append(label)
            continue
        v, g = b91(str(d), label)
        val[label], dig[label] = v, g
    print(f"== Q1 boots: {len(CA)} ca and {len(TX)} tx expected; missing: {missing or 'none'}")
    if missing:
        print("== Q2 digests: NOT DECIDED (a group has no rows to compare)")
        print(f"Q4 VERDICT: NOT DECIDED: boot(s) {missing} have no four cells")
        return 0
    differ = []
    for kind, name in CELLS:
        key = ("dec", kind, 8)
        vals = {b: dig[b].get(key) for b in CA + TX}
        uniq = {v for v in vals.values()}
        if len(uniq) != 1 or None in uniq:
            differ.append(f"{name}: " + ", ".join(f"{b}={str(vals[b])[:40]}" for b in CA + TX))
    print(f"== Q2 digests: {len(differ)} cell(s) whose eight boots are not one value")
    for x in differ[:4]:
        print("   ", x)
    print("== Q3 eight-client cells: change is tx over ca minus one, so positive is slower, the limit 1.0%")
    slower = []
    for kind, name in CELLS:
        key = ("dec", kind, 8)
        ca_b = [val[b][key] for b in CA]
        tx_b = [val[b][key] for b in TX]
        ca_m, tx_m = st.mean(ca_b), st.mean(tx_b)
        ch = tx_m / ca_m - 1

        def spread(v):
            return (max(v) - min(v)) / st.mean(v) * 100

        print(f"{name} at 8 clients: ca {ca_m:.2f} (boots {' '.join(f'{x:.1f}' for x in ca_b)}, spread {spread(ca_b):.2f}%) | "
              f"tx {tx_m:.2f} (boots {' '.join(f'{x:.1f}' for x in tx_b)}, spread {spread(tx_b):.2f}%) | {ch:+.2%} slower")
        if ch > LIMIT + EPS:
            slower.append(name)
    print("== Q4 verdict")
    if differ:
        print(f"Q4 VERDICT: DIGESTS DIFFER ({len(differ)} cell(s)): the switch set is not bit-exact, hold and investigate")
        return 1
    if slower:
        print(f"Q4 VERDICT: HOLD: {len(slower)} cell(s) more than {LIMIT:.0%} slower at 8 clients ({', '.join(slower)})")
        return 0
    print("Q4 VERDICT: PROMOTE T AND X into scripts/env/prod.env (ten lines from dev.env's candidates section, in the same commit as these rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
