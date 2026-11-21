#!/usr/bin/env python3
"""derive92.py --q91 DIR --q92 DIR --score92 FILE [--sections ...] - the numbers OVERNIGHT section 73 quotes, derived from queue91's and queue92's rows and score92.py's printed output. A report: it decides nothing.

Sections (default all):
  ladder     per rung of score92's ladder: the mean step and cumulative change (faster positive) over the 4 prompt cells, the 12 decode cells at 1, 2 and 4 clients and all 20
             decode cells, and the count of steps score92 marked CLEAR.
  arms       the means of score92's attribution rows (smr, smz, the stack on main) over the same cell groups.
  mainboots  the item plan rung (ui1) beside the three boots of score92's main group (mps of queue91, sm2 and sm3 of queue92) at the 12 decode cells, and the step ui1 -> main
             with the scorer's group and with queue92's two boots only. The scorer's group is the verdict; the second reading is its sensitivity to the one boot from another queue.
  spread     the main group's boots at the cells score92's PR rule flagged for smr, with the group's spread.
  mr1        mr1 (md with TF_GLM_REQUEST_STARTS=1) against the md group (md1 md2) over all 24 cells of queue91, with the control's own spread.
  cold       per rung of score92's ladder (its own rung definitions), the group mean cold first token at 8k, 32k and 120k and the conversation's warm turns, in ms, beside the stack's.
"""
import argparse
import importlib.util
import pathlib
import re
import statistics as st
import sys


def load_s91():
    for p in pathlib.Path(__file__).resolve().parents:
        f = p / "scripts" / "queue-scores" / "score91.py"
        if f.exists():
            spec = importlib.util.spec_from_file_location("score91", f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise SystemExit("derive92: scripts/queue-scores/score91.py not found above this file")


def load_s92():
    spec = importlib.util.spec_from_file_location("score92", pathlib.Path(__file__).resolve().parent / "score92.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S91 = load_s91()
LADDER_LINE = re.compile(r"^(?P<cell>[a-z0-9 +]+?): (?P<step>[+-][\d.]+)% \(cumulative (?P<cum>[+-][\d.]+)%\)(?:  CLEAR (?P<clear>gain|loss))?$")
RUNG_LINE = re.compile(r"^-- (?P<name>.+?) against (?P<ref>.+?) \(and against v1\.2\.9\)$")
ARM_SECTION = re.compile(r"^== (?P<key>smr|smz|pd|pm|ut1|the stack on main)\b")
ARM_LINE = re.compile(r"^(?P<cell>[a-z0-9 +]+?): (?P<mean>[+-][\d.]+)%(?: against the mean, (?P<best>[+-][\d.]+)% against the best boot)?$")


def cell_group(cell):
    """PROMPT (cold and warm cells), D124 (decode at 1, 2, 4 clients) or D68 (decode at 6 and 8 clients), from a printed cell name."""
    if cell.startswith(("cold", "conversation")):
        return "PROMPT"
    n = int(re.search(r"at (\d+) clients", cell).group(1))
    return "D124" if n in (1, 2, 4) else "D68"


def parse_ladder(lines):
    """{rung name: [(cell, step, cumulative, clear or None, group)]} from score92's printed ladder."""
    rungs, cur = {}, None
    for line in lines:
        line = line.rstrip("\n")
        m = RUNG_LINE.match(line)
        if m:
            cur = m.group("name")
            rungs[cur] = []
            continue
        m = LADDER_LINE.match(line)
        if m and cur:
            rungs[cur].append((m.group("cell"), float(m.group("step")), float(m.group("cum")), m.group("clear"), cell_group(m.group("cell"))))
    return rungs


def ladder_means(cells):
    """(prompt step, prompt cum, d124 step, d124 cum, all-decode step, all-decode cum, clear gains, clear losses) of one rung."""
    def mean(sel, i):
        v = [c[i] for c in cells if sel(c)]
        return st.mean(v) if v else float("nan")
    prompt = lambda c: c[4] == "PROMPT"
    d124 = lambda c: c[4] == "D124"
    dall = lambda c: c[4] in ("D124", "D68")
    return (mean(prompt, 1), mean(prompt, 2), mean(d124, 1), mean(d124, 2), mean(dall, 1), mean(dall, 2),
            sum(1 for c in cells if c[3] == "gain"), sum(1 for c in cells if c[3] == "loss"))


def parse_arms(lines):
    """{arm: [(cell, change against the mean, change against the best boot or None, group)]} from score92's attribution rows."""
    arms, cur = {}, None
    for line in lines:
        line = line.rstrip("\n")
        m = ARM_SECTION.match(line)
        if m:
            cur = m.group("key")
            arms[cur] = []
            continue
        if line.startswith("== "):
            cur = None
            continue
        m = ARM_LINE.match(line)
        if m and cur:
            arms[cur].append((m.group("cell"), float(m.group("mean")), float(m.group("best")) if m.group("best") else None, cell_group(m.group("cell"))))
    return arms


def print_ladder(lines):
    print(f"{'rung':28s} {'cells':>5s} | prompt step / cum | decode 1/2/4 step / cum | all decode step / cum | clear gain / loss")
    for name, cells in parse_ladder(lines).items():
        ps, pc, ds, dc, as_, ac, g, l = ladder_means(cells)
        print(f"{name:28s} {len(cells):5d} | {ps:+7.2f}% {pc:+7.2f}% | {ds:+7.2f}% {dc:+7.2f}% | {as_:+7.2f}% {ac:+7.2f}% | {g} / {l}")


def print_arms(lines):
    for arm, cells in parse_arms(lines).items():
        if not cells:
            continue
        print(f"== {arm}: {len(cells)} cells")
        for g in ("PROMPT", "D124", "D68"):
            sel = [c for c in cells if c[3] == g]
            if not sel:
                continue
            best = [c[2] for c in sel if c[2] is not None]
            extra = f", against the best boot {st.mean(best):+.2f}%" if best else ""
            print(f"   {g:7s} {len(sel):2d} cells: mean against the mean {st.mean(c[1] for c in sel):+.2f}%{extra}; "
                  f"{sum(1 for c in sel if c[1] < 0)} of {len(sel)} negative; min {min(c[1] for c in sel):+.2f}% max {max(c[1] for c in sel):+.2f}%")


def print_mainboots(q91, q92):
    ui1, mps, sm2, sm3 = S91.boot(q92, "ui1")[0], S91.boot(q91, "mps")[0], S91.boot(q92, "sm2")[0], S91.boot(q92, "sm3")[0]
    cells = [("dec", k, n) for k, _ in S91.KINDS for n in (1, 2, 4)]
    with3, without, off = [], [], []
    for c in cells:
        with3.append(-S91.slower(c, st.mean([mps[c], sm2[c], sm3[c]]), ui1[c]))
        without.append(-S91.slower(c, st.mean([sm2[c], sm3[c]]), ui1[c]))
        off.append(mps[c] / st.mean([sm2[c], sm3[c]]) - 1)
        print(f"{S91.name(c):26s} ui1 {ui1[c]:7.1f} | mps {mps[c]:7.1f} sm2 {sm2[c]:7.1f} sm3 {sm3[c]:7.1f} | step with mps {with3[-1]:+6.2%}  without {without[-1]:+6.2%}")
    print(f"step ui1 -> main, 12 cells: scorer's group (mps sm2 sm3) mean {st.mean(with3):+.2%}; queue92's two boots only (sm2 sm3) mean {st.mean(without):+.2%}")
    print(f"mps against the mean of sm2 and sm3, 12 cells: mean {st.mean(off):+.2%}, {sum(1 for x in off if x < 0)} of 12 below")


def print_spread(q91, q92):
    boots = [(q91, "mps"), (q92, "sm2"), (q92, "sm3")]
    vals = {label: S91.boot(d, label)[0] for d, label in boots}
    smr = S91.boot(q92, "smr")[0]
    for cell in (("dec", "P", 6), ("dec", "C", 8), ("dec", "SC", 6)):
        xs = [vals[label][cell] for _, label in boots]
        mean = st.mean(xs)
        print(f"{S91.name(cell):28s} main boots {' '.join(f'{x:.1f}' for x in xs)} mean {mean:.1f} spread {(max(xs) - min(xs)) / mean:.2%} | "
              f"smr {smr[cell]:.1f} ({smr[cell] / mean - 1:+.2%} against the mean)")


def print_mr1(q91):
    md = [S91.boot(q91, "md1")[0], S91.boot(q91, "md2")[0]]
    mr = S91.boot(q91, "mr1")[0]
    cells = [("cold", s) for s in S91.SIZES] + [("warm",)] + [("dec", k, n) for k, _ in S91.KINDS for n in S91.LEVELS]
    rows = []
    for c in cells:
        xs = [b[c] for b in md if c in b]
        if len(xs) != 2 or c not in mr:
            print(f"{S91.name(c)}: missing")
            continue
        mean = st.mean(xs)
        rows.append((c, -S91.slower(c, mr[c], mean), (max(xs) - min(xs)) / mean))
        print(f"{S91.name(c):34s} md {xs[0]:9.1f} {xs[1]:9.1f} spread {rows[-1][2]:5.2%} | mr1 {mr[c]:9.1f} | {rows[-1][1]:+7.2%} faster")
    for label, sel in (("decode 1/2/4", lambda r: r[0][0] == "dec" and r[0][2] in (1, 2, 4)), ("decode 6/8", lambda r: r[0][0] == "dec" and r[0][2] in (6, 8))):
        g = [r for r in rows if sel(r)]
        print(f"{label}: {len(g)} cells, mean {st.mean(r[1] for r in g):+.2%}, {sum(1 for r in g if r[1] < 0)} negative, min {min(r[1] for r in g):+.2%}, max {max(r[1] for r in g):+.2%}")


def print_cold(q91, q92):
    s92 = load_s92()
    groups = list(s92.rungs(q91, q92)) + [("our stack on main (mn1 mn2)", [(q91, "mn1"), (q91, "mn2")])]
    print(f"{'rung':30s} {'boots':>5s} | cold 8k ms | cold 32k ms | cold 120k ms | warm turns ms")
    for name, boots in groups:
        missing, vals, _ = S91.group(boots)
        cells = [("cold", 8000), ("cold", 32000), ("cold", 120000), ("warm",)]
        got = [st.mean(vals[c]) if vals.get(c) else float("nan") for c in cells]
        print(f"{name:30s} {len(boots) - len(missing):5d} | {got[0]:10.0f} | {got[1]:11.0f} | {got[2]:12.0f} | {got[3]:13.0f}")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--q91", default="docs/audit-2026-11-12/queue-rows/queue91/f91-c")
    ap.add_argument("--q92", default="docs/audit-2026-11-12/queue-rows/queue92/f92-c")
    ap.add_argument("--score92", help="score92.py's printed output (needed by ladder and arms)")
    ap.add_argument("--sections", nargs="+", default=["ladder", "arms", "cold", "mainboots", "spread", "mr1"],
                    choices=["ladder", "arms", "cold", "mainboots", "spread", "mr1"])
    a = ap.parse_args(argv)
    text = open(a.score92, encoding="utf-8").read().splitlines() if a.score92 else []
    for sec in a.sections:
        print(f"##### {sec}")
        if sec == "ladder":
            print_ladder(text)
        elif sec == "arms":
            print_arms(text)
        elif sec == "cold":
            print_cold(a.q91, a.q92)
        elif sec == "mainboots":
            print_mainboots(a.q91, a.q92)
        elif sec == "spread":
            print_spread(a.q91, a.q92)
        else:
            print_mr1(a.q91)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
