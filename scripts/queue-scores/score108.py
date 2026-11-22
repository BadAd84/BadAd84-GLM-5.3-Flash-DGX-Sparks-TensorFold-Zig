#!/usr/bin/env python3
"""score108.py [--q108 DIR] - queue108 (scripts/queues/queue108.sh): upstream's prompt-behind-decode controls at 4 and 8 streams, on the recipe.

DIR holds one folder a boot, `<label>/concurrent.json` (tools/bench_concurrent.py --levels 4,8 --mixed) and `<label>/cache-8192.json`. Labels: c1 c2 the control
(the recipe as committed), and two boots each of b512 (`TENSORFOLD_PREFILL_BUDGET=512`), b2048 (`=2048`) and s50 (`TENSORFOLD_PREFILL_SHARE=0.5`). A cell is
(prompt, temperature, streams) with `aggregate_tps`, `ttft_s_max` and `failed`.

RULES, FIXED BY THE PARENT AND WRITTEN BEFORE ANY ROW EXISTED:
  W0 QUALIFIED: every boot has both levels, and the 8-stream cell actually mixed a long prompt (some request of a rep carries prompt_tokens >= 8000). Without
     that the trade this queue exists for is not happening, and the arm is NOT DECIDED rather than level. (queue94's lesson: a clause whose condition never
     occurs reads NOT DECIDED, not a result.)
  W1 CLEAN: the cells used report failed 0 and no `errors`.
  W2 DECODE: at each level, an arm's aggregate_tps is not more than 1.0% slower than the control's mean.
  W3 WAIT: at each level, an arm's ttft_s_max is at least 10.0% lower than the control's mean. The two are a trade: W3 without W2 is the cost moving, not the
     lever.
  W4 VERDICT: an arm WINS at a level when W2 and W3 both hold there. ADOPT the arm that wins at BOTH levels, naming the largest mean wait reduction; else NONE,
     and print every arm's numbers so a near miss is visible. A missing boot or cell is NOT DECIDED, never a pass.
Exit code 1 only on a W1 violation in the control itself; everything else prints and exits 0.
"""
import argparse
import json
import pathlib
import statistics as st
import sys

LEVELS = (4, 8)
ARMS = {"control": ("c1", "c2"), "b512": ("b512a", "b512b"), "b2048": ("b2048a", "b2048b"), "s50": ("s50a", "s50b")}
DEC_LIMIT = 0.010
WAIT_GAIN = 0.100
EPS = 1e-9
MIX_MIN_TOKENS = 8000


def cells(d, label):
    f = d / label / "concurrent.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8")).get("cells", [])


def level_cell(cs, n):
    return [c for c in cs if c.get("streams") == n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q108", default="work/pp108/f108-c")
    a = ap.parse_args()
    d = pathlib.Path(a.q108)
    print(f"== score108: q108 {d}")
    val, missing, mixed, unclean = {}, [], {}, []
    for arm, labels in ARMS.items():
        for label in labels:
            cs = cells(d, label)
            if cs is None:
                missing.append(label)
                continue
            for n in LEVELS:
                got = level_cell(cs, n)
                if not got:
                    missing.append(f"{label}@{n}")
                    continue
                c = got[0]
                val[(label, n)] = (c.get("aggregate_tps"), c.get("ttft_s_max"))
                if c.get("failed") or c.get("errors"):
                    unclean.append(f"{label}@{n}")
                if n == 8:
                    longest = max((q.get("prompt_tokens") or 0 for r in c.get("reps", []) for q in r.get("requests", [])), default=0)
                    mixed[(label, n)] = longest
    print(f"== W0 boots: missing {missing or 'none'}; longest prompt in the 8-stream cell per boot: " +
          (", ".join(f"{k[0]}={v}" for k, v in sorted(mixed.items())) or "none"))
    not_mixed = [k[0] for k, v in mixed.items() if v < MIX_MIN_TOKENS]
    if missing or not_mixed:
        why = []
        if missing:
            why.append(f"boots/cells {missing}")
        if not_mixed:
            why.append(f"no request above {MIX_MIN_TOKENS} prompt tokens in {not_mixed}")
        print(f"W4 VERDICT: NOT DECIDED: {'; '.join(why)}")
        return 0
    print(f"== W1 clean: {unclean or 'every cell reports 0 failed and no errors'}")
    for arm, labels in ARMS.items():
        if arm == "control":
            continue
        wins = 0
        line = []
        for n in LEVELS:
            ca = st.mean(val[(c, n)][0] for c in ARMS["control"])
            cw = st.mean(val[(c, n)][1] for c in ARMS["control"])
            aa = st.mean(val[(c, n)][0] for c in labels)
            aw = st.mean(val[(c, n)][1] for c in labels)
            dec = aa / ca - 1
            wait = 1 - aw / cw
            ok = dec >= -DEC_LIMIT - EPS and wait >= WAIT_GAIN - EPS
            wins += 1 if ok else 0
            line.append(f"{n} streams: decode {dec:+.2%} (limit -1.0%), worst wait {wait:+.2%} (needs +10.0%){' WINS' if ok else ''}")
        print(f"== {arm}: " + " | ".join(line))
        val[(arm, "wins")] = wins
    print("== W4 verdict")
    if val.get(("b512", "wins")) is None:
        print("W4 VERDICT: NOT DECIDED")
        return 0
    both = [arm for arm in ("b512", "b2048", "s50") if val.get((arm, "wins")) == len(LEVELS)]
    if not both:
        print("W4 VERDICT: NONE: no setting holds decode within 1.0% and cuts the worst wait by 10% at both levels; the numbers above show how near each came")
        return 0
    def gain(arm):
        g = []
        for n in LEVELS:
            cw = st.mean(val[(c, n)][1] for c in ARMS["control"])
            aw = st.mean(val[(c, n)][1] for c in ARMS[arm])
            g.append(1 - aw / cw)
        return st.mean(g)
    best = max(both, key=gain)
    print(f"W4 VERDICT: ADOPT {best}: decode within 1.0% and the worst wait {gain(best):+.2%} lower on average at 4 and 8 streams")
    return 0


if __name__ == "__main__":
    sys.exit(main())
