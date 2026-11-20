#!/usr/bin/env python3
"""score95.py [--q91 DIR] [--q95 DIR] [--old DIR] - queue95 (scripts/queues/queue95.sh): the T/X split of dev.env's ten candidates on the stack re-seated on upstream main, against the
groups queue91 and queue77 measured.

Each DIR holds rows.jsonl, <label>/chain.jsonl and dec-<label>/{P,C,SP,SC}<clients>.jsonl in queue91's row format, and score91.py's own readers, imported below, parse them: --q91
is queue91's f91-c (default work/pp91/f91-c), --q95 queue95's f95-c (default work/pp95/f95-c), --old queue77's f77-c (default docs/audit-2026-11-12/queue-rows/queue77/f77-c).

GROUPS. N, the stack on main as committed: mn1 mn2 (q91) and mn3 (q95). O, the old stack: P1 P2 (--old), mo3 (q91) and mo4 (q95). D, all ten candidates: md1 md2 (q91). T, the
four that can touch decode: mt1 mt2 (q95). X, the six prompt-only ones: mx1 mx2 (q95). A group's value for a cell is the mean of its boots. A cell is exactly score91's: the cold
first token at 8k, 32k and 120k, the mean first token of the growing conversation's turns 2 to 8, and the aggregate tokens a second of greedy and of sampled prose and code at 1, 2,
4, 6 and 8 clients. "Slower" is a fraction of the reference group's mean.

THE RULES BELOW ARE FIXED BY THE PARENT, WRITTEN BEFORE ANY ROW EXISTED, and quoted here as given:
  K1 SYNC, re-run with the larger groups: score91's sync rule exactly (no cell more than 1.0% slower, every reply digest one digest across all boots), N against O. Print every
     cell's two groups' values and the cells over the limit, naming the group ranges. Verdict ACCEPTED or NOT ACCEPTED (and the cells), or NOT DECIDED.
  K2 DECODE ATTRIBUTION: the 12 decode cells (greedy and sampled prose and code at 1, 2 and 4 clients). For each arm A in {D, T, X}: change per cell = A's mean over N's mean
     minus one; the arm CARRIES THE LOSS when the mean of its 12 changes is at most -0.5% AND at least 9 of the 12 are negative; it is CLEAN when that mean is at least -0.3%;
     otherwise UNCLEAR. Print the 12 changes and the mean for each arm.
  K3 PROMPT GAINS: for each arm in {D, T, X}: the cold 8k, 32k, 120k and the conversation's warm turns, as the fraction faster than N; print them. An arm GAINS when at least one
     of the four is faster by 1.0% or more and none is slower by more than 1.0%.
  K4 DIGESTS: every reply digest of T and X equals N's (cold requests, each conversation turn, each decode cell, the 24 prompts), as score91 reads them; a difference FAILS the
     arm.
  K5 PROMOTION READING: for each of T and X print PROMOTABLE (CLEAN on K2, GAINS on K3, digests equal), HOLD BACK (CARRIES THE LOSS, or K4 differs), or UNCLEAR, and then one
     line stating whether X's and T's gains add up to D's: D's gain and the sum of T's and X's for each of the four cells, nothing beyond the numbers.
A missing boot or report is NOT DECIDED for the clause that needs it, never a pass. Exit code 1 only when a K4 digest differs; everything else prints and exits 0.
"""
import argparse
import importlib.util
import pathlib
import statistics as st
import sys

_S91 = None


def s91():
    """score91.py, whose rows(), boot(), group(), slower() and name() are the one owner of queue91's row format (found above this file, so a scratch copy still finds it)."""
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
            raise SystemExit("score95: scripts/queue-scores/score91.py not found above this file")
    return _S91


LIMIT = s91().LIMIT  # K1: a cell more than this much slower than the old group's mean is a regression
SIZES = s91().SIZES
LEVELS = s91().LEVELS
KINDS = s91().KINDS
DEC_LEVELS = (1, 2, 4)  # K2: the 12 decode cells
DEC_LIMIT = 0.005  # K2: the arm carries the loss at or below this mean change
DEC_CLEAN = 0.003  # K2: the arm is clean at or above minus this mean change
DEC_NEG = 9  # K2: and with at least this many of the 12 changes negative
GAIN = 0.010  # K3: a gain this large is a gain, a loss larger than this is no gain
CELLS = [("cold", s) for s in SIZES] + [("warm",)] + [("dec", k, n) for k, _ in KINDS for n in LEVELS]
PROMPT_CELLS = [("cold", 8000), ("cold", 32000), ("cold", 120000), ("warm",)]
DEC_CELLS = [("dec", k, n) for k, _ in KINDS for n in DEC_LEVELS]


def groups(q91, q95, old):
    """{arm: [(DIR, label)]}: the five groups the rules name, each boot from the DIR the queue that made it wrote."""
    return {
        "N": [(q91, "mn1"), (q91, "mn2"), (q95, "mn3")],
        "O": [(old, "P1"), (old, "P2"), (q91, "mo3"), (q95, "mo4")],
        "D": [(q91, "md1"), (q91, "md2")],
        "T": [(q95, "mt1"), (q95, "mt2")],
        "X": [(q95, "mx1"), (q95, "mx2")],
    }


def load(boots):
    """(labels with no rows, per-cell boot values, reply digests by key) of one group, score91.py's group()."""
    return s91().group(boots)


def name(m):
    return s91().name(m)


def labels(boots):
    return " ".join(label for _, label in boots)


def short_cells(vals, boots, cells):
    """[(cell, boots that measured it, boots in the group)] of cells a group did not report on every boot: a cell read from fewer boots than the group has is NOT DECIDED."""
    return [(m, len(vals.get(m, [])), len(boots)) for m in cells if len(vals.get(m, [])) != len(boots)]


# ---------------------------------------------------------------- K1 sync

def k1(g):
    """(lines, verdict): score91's sync rule, N against O, on the enlarged groups."""
    out, flagged, absent, holes = [], [], [], []
    n_missing, nv, nd = load(g["N"])
    o_missing, ov, od = load(g["O"])
    if n_missing or o_missing:
        return out, f"K1 SYNC: NOT DECIDED: no rows for {', '.join(n_missing + o_missing)}"
    out.append(f"== K1 sync: N ({labels(g['N'])}) against O ({labels(g['O'])}); slower is positive")
    for m in CELLS:
        n_have, o_have = len(nv.get(m, [])), len(ov.get(m, []))
        if not n_have or not o_have:
            side = "N" if not n_have else "O"
            absent.append(f"{name(m)} (no {side} rows)")
            out.append(f"{name(m)}: MISSING in {side}")
            continue
        if n_have != len(g["N"]) or o_have != len(g["O"]):
            absent.append(f"{name(m)} ({n_have} of {len(g['N'])} N boots, {o_have} of {len(g['O'])} O boots)")
            out.append(f"{name(m)}: N measured on {n_have} of {len(g['N'])} boots, O on {o_have} of {len(g['O'])}: NOT DECIDED")
            continue
        s = s91().slower(m, st.mean(nv[m]), st.mean(ov[m]))
        inside = min(ov[m]) <= min(nv[m]) and max(nv[m]) <= max(ov[m])
        line = (f"{name(m)}: N {' '.join(f'{x:.1f}' for x in nv[m])} | O {' '.join(f'{x:.1f}' for x in ov[m])} | {s:+.2%} slower")
        if s > LIMIT:
            line += f"  <- over the limit (N {min(nv[m]):.1f}..{max(nv[m]):.1f}" + (f" inside O {min(ov[m]):.1f}..{max(ov[m]):.1f})" if inside else ")")
            flagged.append((m, inside))
        out.append(line)
    boots = len(g["N"]) + len(g["O"])
    keys = sorted(set(nd) | set(od), key=str)
    holes = [k for k in keys if len(nd.get(k, [])) + len(od.get(k, [])) != boots]
    differ = [k for k in keys if k not in holes and len({*nd.get(k, []), *od.get(k, [])}) != 1]
    out.append(f"reply digests: {len(keys)} keys over {boots} boots, {len(holes)} key(s) missing a boot's report, {len(differ)} with more than one digest across the boots")
    for k in (holes + differ)[:12]:
        out.append(f"  {'missing' if k in holes else 'differs'}: {k}")
    if absent or holes:
        why = absent + [f"digest {k} missing a boot's report" for k in holes]
        return out, f"K1 SYNC: NOT DECIDED: {len(why)} cell(s) or digest key(s) have no report: {'; '.join(why[:6])}"
    if differ:
        return out, f"K1 SYNC: NOT ACCEPTED: reply digests differ at {len(differ)} key(s) (and {len(flagged)} cell(s) over the speed limit)"
    if flagged:
        inside = sum(1 for _, i in flagged if i)
        names = "; ".join(name(m) for m, _ in flagged)
        return out, f"K1 SYNC: NOT ACCEPTED: {len(flagged)} cell(s) more than {LIMIT:.0%} slower ({inside} inside O's boots' range): {names}"
    return out, f"K1 SYNC: ACCEPTED, no cell more than {LIMIT:.0%} slower and every reply digest equal"


# ---------------------------------------------------------------- K2 decode attribution

def k2(g):
    """(lines, {arm: verdict}): each arm's 12 decode changes against N, and which arm carries queue91's loss."""
    out, verdicts = [], {}
    n_missing, nv, _ = load(g["N"])
    out.append(f"== K2 decode attribution against N ({labels(g['N'])}); change is the arm's mean over N's mean minus one, so negative is slower")
    for arm in ("D", "T", "X"):
        a_missing, av, _ = load(g[arm])
        miss = n_missing + a_missing
        if miss:
            verdicts[arm] = "NOT DECIDED"
            out.append(f"{arm} ({labels(g[arm])}): NOT DECIDED: no rows for {', '.join(miss)}")
            continue
        short = short_cells(nv, g["N"], DEC_CELLS) + short_cells(av, g[arm], DEC_CELLS)
        if short:
            verdicts[arm] = "NOT DECIDED"
            out.append(f"{arm} ({labels(g[arm])}): NOT DECIDED: {len(short)} decode cell(s) missing a boot's report: "
                       + "; ".join(f"{name(m)} ({a} of {b} boots)" for m, a, b in short[:6]))
            continue
        changes = [st.mean(av[m]) / st.mean(nv[m]) - 1 for m in DEC_CELLS]
        mean = st.mean(changes)
        neg = sum(1 for c in changes if c < 0)
        if mean <= -DEC_LIMIT and neg >= DEC_NEG:
            verdict = "CARRIES THE LOSS"
        elif mean >= -DEC_CLEAN:
            verdict = "CLEAN"
        else:
            verdict = "UNCLEAR"
        verdicts[arm] = verdict
        out.append(f"{arm} ({labels(g[arm])}): " + ", ".join(f"{name(m)} {c:+.2%}" for m, c in zip(DEC_CELLS, changes))
                   + f" | mean {mean:+.2%} of 12 cells, {neg} negative: {verdict}")
    return out, verdicts


# ---------------------------------------------------------------- K3 prompt gains

def gains(g, arm):
    """({cell: fraction faster than N} or None, missing labels): one arm's four K3 cells against N."""
    n_missing, nv, _ = load(g["N"])
    a_missing, av, _ = load(g[arm])
    miss = n_missing + a_missing
    if miss:
        return None, miss
    short = short_cells(nv, g["N"], PROMPT_CELLS) + short_cells(av, g[arm], PROMPT_CELLS)
    if short:
        return None, [f"{name(m)} ({a} of {b} boots)" for m, a, b in short]
    return {m: 1 - st.mean(av[m]) / st.mean(nv[m]) for m in PROMPT_CELLS}, []


def k3(g):
    """(lines, {arm: verdict}): the four prompt cells as the fraction faster than N."""
    out, verdicts = [], {}
    out.append(f"== K3 prompt gains against N ({labels(g['N'])}); faster is positive, a latency cell's fraction saved")
    for arm in ("D", "T", "X"):
        table, miss = gains(g, arm)
        if table is None:
            verdicts[arm] = "NOT DECIDED"
            out.append(f"{arm} ({labels(g[arm])}): NOT DECIDED: no rows for {', '.join(miss)}")
            continue
        fast = max(table.values()) >= GAIN
        slow = min(table.values()) < -GAIN
        verdict = "NO GAIN" if slow or not fast else "GAINS"
        verdicts[arm] = verdict
        out.append(f"{arm} ({labels(g[arm])}): " + ", ".join(f"{name(m)} {x:+.2%}" for m, x in table.items())
                   + f" | largest {max(table.values()):+.2%}, smallest {min(table.values()):+.2%}: {verdict}")
    return out, verdicts


# ---------------------------------------------------------------- K4 digests

def k4(g):
    """(lines, {arm: verdict}): every reply digest of T and X against N's, the arms' cold requests, turns, decode cells and the 24 prompts."""
    out, verdicts = [], {}
    n_missing, _, nd = load(g["N"])
    out.append(f"== K4 digests against N ({labels(g['N'])}): cold requests, every conversation turn, every decode cell and the prompts")
    for arm in ("T", "X"):
        a_missing, _, ad = load(g[arm])
        miss = n_missing + a_missing
        if miss:
            verdicts[arm] = "NOT DECIDED"
            out.append(f"{arm} ({labels(g[arm])}): NOT DECIDED: no rows for {', '.join(miss)}")
            continue
        holes = [(side, k) for side, d, bs in (("N", nd, g["N"]), (arm, ad, g[arm])) for k in sorted(d, key=str) if len(d[k]) != len(bs)]
        only = sorted(set(nd) ^ set(ad), key=str)
        differ = sorted((k for k in set(nd) & set(ad) if len(set(nd[k] + ad[k])) != 1), key=str)
        out.append(f"{arm} ({labels(g[arm])}): {len(set(nd) | set(ad))} digest key(s), {len(holes)} with a boot's report missing, {len(only)} on one side only, {len(differ)} differing")
        for side, k in holes[:6]:
            out.append(f"  missing: {side} {k}")
        for k in only[:6]:
            out.append(f"  one side only: {k}")
        for k in differ[:6]:
            out.append(f"  differs: {k}")
        if holes or only:
            verdicts[arm] = "NOT DECIDED"
            out.append(f"{arm}: NOT DECIDED: a report is missing (never a pass)")
        elif differ:
            verdicts[arm] = "DIFFERS"
            out.append(f"{arm}: DIFFERS at {len(differ)} key(s)")
        else:
            verdicts[arm] = "EQUAL"
            out.append(f"{arm}: EQUAL to N at every key")
    return out, verdicts


# ---------------------------------------------------------------- K5 promotion reading

def k5(g, v2, v3, v4):
    """(lines, {arm: reading}): the two arms' readings and the numbers of the additivity question, nothing beyond them."""
    out = []
    readings = {}
    out.append("== K5 promotion reading: PROMOTABLE is CLEAN on K2, GAINS on K3 and digests equal; HOLD BACK is CARRIES THE LOSS or a K4 difference")
    for arm in ("T", "X"):
        if v4.get(arm) == "DIFFERS" or v2.get(arm) == "CARRIES THE LOSS":
            reading = "HOLD BACK"
        elif v2.get(arm) == "CLEAN" and v3.get(arm) == "GAINS" and v4.get(arm) == "EQUAL":
            reading = "PROMOTABLE"
        else:
            reading = "UNCLEAR"
        readings[arm] = reading
        out.append(f"{arm}: {reading} (K2 {v2.get(arm)}, K3 {v3.get(arm)}, K4 {v4.get(arm)})")
    tab = {arm: gains(g, arm)[0] for arm in ("D", "T", "X")}
    out.append("K5 additivity, the four K3 cells as the fraction faster than N: D's gain, T's, X's, and T's plus X's")
    for m in PROMPT_CELLS:
        cells = [tab[arm][m] if tab[arm] else None for arm in ("D", "T", "X")]
        if any(x is None for x in cells):
            out.append(f"  {name(m)}: no rows")
            continue
        d, t, x = cells
        out.append(f"  {name(m)}: D {d:+.2%}, T {t:+.2%}, X {x:+.2%}, T+X {t + x:+.2%}")
    return out, readings


# ---------------------------------------------------------------- report and exit code

def report(q91, q95, old):
    """(lines, {clause: verdicts}, failed): the whole report; failed when a K4 digest differs."""
    g = groups(q91, q95, old)
    l1, v1 = k1(g)
    l2, v2 = k2(g)
    l3, v3 = k3(g)
    l4, v4 = k4(g)
    l5, v5 = k5(g, v2, v3, v4)
    lines = [f"== score95: q91 {q91}, q95 {q95}, old {old}"] + l1 + [v1] + l2 + l3 + l4 + l5
    failed = any(v == "DIFFERS" for v in v4.values())
    return lines, {"K1": v1, "K2": v2, "K3": v3, "K4": v4, "K5": v5}, failed


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--q91", default="work/pp91/f91-c", help="queue91's f91-c (default work/pp91/f91-c)")
    ap.add_argument("--q95", default="work/pp95/f95-c", help="queue95's f95-c (default work/pp95/f95-c)")
    ap.add_argument("--old", default="docs/audit-2026-11-12/queue-rows/queue77/f77-c", help="queue77's f77-c (default docs/audit-2026-11-12/queue-rows/queue77/f77-c)")
    a = ap.parse_args(argv)
    lines, _, failed = report(a.q91, a.q95, a.old)
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
