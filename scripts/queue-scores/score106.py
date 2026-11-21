#!/usr/bin/env python3
"""score106.py [--q106 DIR] - queue106 (scripts/queues/queue106.sh): the cells `TF_GLM_OVN_DRAFT_NOISE=1` never had, sampled decode at 6 and 8 clients.

The knob is in scripts/env/prod.env and its own row in docs/KNOBS.md says its 6 and 8 stream sampled cells are open, against the rule that a knob ships only on cells at 1, 2, 4,
6 and 8. DIR holds dec-<label>/{SP6,SC6,SP8,SC8}.jsonl in queue91's row shape, labels on1 on2 on3 on4 (the recipe as committed, the knob on by default) and off1 off2 off3 off4
(`-e TF_GLM_OVN_DRAFT_NOISE=0`). Rows and digests come from score91.py's own `boot()`.

RULES, FIXED BY THE PARENT AND WRITTEN BEFORE ANY ROW EXISTED:
  D1 BOOTS: four boots a group. A missing boot or cell makes every clause that needs it NOT DECIDED, never a pass.
  D2 DIGESTS: each of the four cells carries one digest across all eight boots (sampled decode at a fixed seed; the knob changes drafting, not the tokens it verifies). A
     difference FAILS and the program exits 1.
  D3 THE FOUR CELLS: sampled prose and sampled code at 6 and 8 clients. A group's value is the mean of its four boots. Change = on over off minus one, so positive means keeping
     the knob is faster. KEEP when the mean of the four is at least +1.0% and no cell is more than 1.0% slower than off. REMOVE when the mean is at or below 0.0%: a knob with no
     measured benefit leaves the recipe, which is the class the provenance audit calls A. Otherwise HOLD, which is not a verdict to act on.
  D4 VERDICT: one line, KEEP THE KNOB, REMOVE IT, or NOT DECIDED. Exit code 1 only on a D2 difference.
"""
import argparse
import importlib.util
import pathlib
import statistics as st
import sys

CELLS = [("SP", 6, "sampled prose"), ("SC", 6, "sampled code"), ("SP", 8, "sampled prose"), ("SC", 8, "sampled code")]
ON, OFF = ("on1", "on2", "on3", "on4"), ("off1", "off2", "off3", "off4")
KEEP_MEAN, LIMIT = 0.010, 0.010
EPS = 1e-9

_S91 = None


def s91():
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
            raise SystemExit("score106: scripts/queue-scores/score91.py not found above this file")
    return _S91


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q106", default="work/pp106/f106-c")
    a = ap.parse_args()
    d = pathlib.Path(a.q106)
    b91 = s91().boot
    print(f"== score106: q106 {d}")
    val, dig, missing = {}, {}, []
    for label in ON + OFF:
        if not all((d / f"dec-{label}" / f"{k}{n}.jsonl").exists() for k, n, _ in CELLS):
            missing.append(label)
            continue
        v, g = b91(str(d), label)
        val[label], dig[label] = v, g
    print(f"== D1 boots: 4 on and 4 off expected; missing: {missing or 'none'}")
    if missing:
        print(f"D4 VERDICT: NOT DECIDED: boot(s) {missing} have no four cells")
        return 0
    differ = []
    for kind, n, name in CELLS:
        key = ("dec", kind, n)
        uniq = {dig[b].get(key) for b in ON + OFF}
        if len(uniq) != 1 or None in uniq:
            differ.append(name)
    print(f"== D2 digests: {len(differ)} cell(s) whose eight boots are not one value{f' ({chr(44).join(differ)})' if differ else ''}")
    print("== D3 sampled cells: change is on over off minus one, so positive means keeping the knob is faster")
    bad, changes = [], []
    for kind, n, name in CELLS:
        key = ("dec", kind, n)
        on_b = [val[b][key] for b in ON]
        off_b = [val[b][key] for b in OFF]
        ch = st.mean(on_b) / st.mean(off_b) - 1
        changes.append(ch)
        if ch < -LIMIT - EPS:
            bad.append(name)
        print(f"{name} at {n} clients: off {st.mean(off_b):.2f} (boots {' '.join(f'{x:.1f}' for x in off_b)}) | on {st.mean(on_b):.2f} "
              f"(boots {' '.join(f'{x:.1f}' for x in on_b)}) | {ch:+.2%} faster with the knob")
    mean = st.mean(changes)
    print("== D4 verdict")
    if differ:
        print(f"D4 VERDICT: DIGESTS DIFFER at {len(differ)} cell(s): hold the knob and investigate, it is not bit-exact as claimed")
        return 1
    if bad:
        print(f"D4 VERDICT: HOLD: {len(bad)} cell(s) more than {LIMIT:.0%} slower with the knob ({chr(44).join(bad)}), mean {mean:+.2%}")
        return 0
    if mean >= KEEP_MEAN - EPS:
        print(f"D4 VERDICT: KEEP THE KNOB: mean {mean:+.2%} faster across the four sampled cells, none more than {LIMIT:.0%} slower")
        return 0
    if mean <= EPS:
        print(f"D4 VERDICT: REMOVE IT: mean {mean:+.2%} across the four sampled cells, no measured benefit to the recipe")
        return 0
    print(f"D4 VERDICT: NOT DECIDED: mean {mean:+.2%} sits between no benefit and the {KEEP_MEAN:.0%} a keep needs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
