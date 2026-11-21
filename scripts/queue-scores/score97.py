#!/usr/bin/env python3
"""score97.py [--q91 DIR] [--q92 DIR] [--q95 DIR] - queue97 (scripts/queues/queue97.sh): the 47-patch series re-seated on upstream main's tip 46c6ee229 (image m140a) against the
stack on the pin, and what each stack still buys over stock upstream.

DIR holds rows.jsonl, <label>/chain.jsonl and dec-<label>/{P,C,SP,SC}<clients>.jsonl as the queues write them, and score91.py's own readers, imported below, parse them: --q91 is
queue91's f91-c (default docs/audit-2026-11-12/queue-rows/queue91/f91-c); --q92 the folder where queue92, queue96 and queue97 wrote their rows (default work/pp92/f92-c: all three
write labels into f92-c); --q95 queue95's f95-c (default work/pp95/f95-c).

GROUPS. N, the stack on the pin: mn1 mn2 (q91) and mn3 (q95). T, the stack on the tip: tn1 tn2 (q92). S0, stock main at the pin: mps (q91), sm2 sm3 (q92). S1, stock main at the
tip: ut1 (q92). A group's value for a cell is the mean of its boots. A cell is score91's: the cold first token at 8k, 32k and 120k, the mean first token of the growing
conversation's turns 2 to 8, and the aggregate tokens a second of greedy and of sampled prose and code at 1, 2, 4, 6 and 8 clients. "Slower" is a fraction of the reference group's mean.

THE RULES BELOW ARE FIXED BY THE PARENT, WRITTEN BEFORE ANY ROW EXISTED, and quoted here as given:
  U1 RE-SEAT SYNC: score91's sync rule exactly, T as the new group against N as the old: no cell more than 1.0% slower, and every reply digest of every cell one digest across all
     boots of N and T. Print every cell's two group values and the cells over the limit with the groups' ranges; verdict ACCEPTED, NOT ACCEPTED (cells and/or digests named) or NOT
     DECIDED.
  U2 WHAT THE SERIES BUYS: report only, no verdict. For every cell print S0, S1 and T and two fractions, faster positive: T against S1 (what the series still buys at the tip) and
     S1 against S0 (what upstream's merges since the pin gave a stock user, the number the owner asked about). If ut1 or any S0 boot is missing print "no rows" for those columns,
     never zeros.
  U3 DIGESTS BETWEEN STOCK AND STACK: print whether T's reply digests equal S1's (they will not, the recipe changes numerics) as one line per cell kind, never as a verdict.
A missing boot or report is NOT DECIDED for the clause that needs it, never a pass. Exit code 1 only when U1 is NOT ACCEPTED by a digest difference; everything else exits 0.
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
            raise SystemExit("score97: scripts/queue-scores/score91.py not found above this file")
    return _S91


LIMIT = s91().LIMIT  # U1: score91's limit, a cell more than this much slower than N's mean is a regression
SIZES = s91().SIZES
LEVELS = s91().LEVELS
KINDS = s91().KINDS
CELLS = [("cold", s) for s in SIZES] + [("warm",)] + [("dec", k, n) for k, _ in KINDS for n in LEVELS]
DIG_KINDS = (("cold", "cold first token"), ("chain", "conversation"), ("P", KINDS[0][1]), ("C", KINDS[1][1]), ("SP", KINDS[2][1]), ("SC", KINDS[3][1]), ("pp", "24 prompts"))


def groups(q91, q92, q95):
    """{arm: [(DIR, label)]}: the four groups the rules name, each boot from the DIR the queue that made it wrote."""
    return {
        "N": [(q91, "mn1"), (q91, "mn2"), (q95, "mn3")],
        "T": [(q92, "tn1"), (q92, "tn2")],
        "S0": [(q91, "mps"), (q92, "sm2"), (q92, "sm3")],
        "S1": [(q92, "ut1")],
    }


def load(boots):
    """(labels with no rows, per-cell boot values, reply digests by key) of one group, score91.py's group()."""
    return s91().group(boots)


def name(m):
    return s91().name(m)


def labels(boots):
    return " ".join(label for _, label in boots)


def mean_of(vals, boots, m):
    """The group's cell value, the mean of its boots, or None when a boot of the group did not report it: a partial group is no rows, never a number."""
    return st.mean(vals[m]) if boots and len(vals.get(m, [])) == len(boots) else None


def gain(m, new, ref):
    """Fraction by which `new` is faster than `ref`: latency down by that much, or throughput up by that much of the reference rate; a zero is +0.00%, never -0.00%."""
    return -s91().slower(m, new, ref) + 0.0


def fmt(x):
    return "no rows" if x is None else f"{x:.1f}"


def frac(x):
    return "no rows" if x is None else f"{x:+.2%}"


def dig_kind(k):
    """The cell kind a reply digest key belongs to: score91's keys are ('cold', size, rep), ('chain', turn), ('dec', a KINDS tag, clients) and ('pp', name)."""
    return k[1] if k[0] == "dec" else k[0]


# ---------------------------------------------------------------- U1 re-seat sync

def u1(g):
    """(lines, verdict, digest_failed): score91's sync rule, T as the new group against N as the old, with the enlarged groups."""
    out, flagged, absent = [], [], []
    n_missing, nv, nd = load(g["N"])
    t_missing, tv, td = load(g["T"])
    if n_missing or t_missing:
        return out, f"U1 SYNC: NOT DECIDED: no rows for {', '.join(n_missing + t_missing)}", False
    out.append(f"== U1 re-seat sync: T ({labels(g['T'])}) against N ({labels(g['N'])}); slower is positive, a cell is the mean of its group's boots")
    for m in CELLS:
        n_have, t_have = len(nv.get(m, [])), len(tv.get(m, []))
        if not n_have or not t_have:
            side = "N" if not n_have else "T"
            absent.append(f"{name(m)} (no {side} rows)")
            out.append(f"{name(m)}: MISSING in {side}")
            continue
        if n_have != len(g["N"]) or t_have != len(g["T"]):
            absent.append(f"{name(m)} ({t_have} of {len(g['T'])} T boots, {n_have} of {len(g['N'])} N boots)")
            out.append(f"{name(m)}: T measured on {t_have} of {len(g['T'])} boots, N on {n_have} of {len(g['N'])}: NOT DECIDED")
            continue
        s = s91().slower(m, st.mean(tv[m]), st.mean(nv[m]))
        inside = min(nv[m]) <= min(tv[m]) and max(tv[m]) <= max(nv[m])
        line = f"{name(m)}: N {' '.join(f'{x:.1f}' for x in nv[m])} | T {' '.join(f'{x:.1f}' for x in tv[m])} | {s:+.2%} slower"
        if s > LIMIT:
            line += f"  <- over the limit (T {min(tv[m]):.1f}..{max(tv[m]):.1f}" + (f" inside N {min(nv[m]):.1f}..{max(nv[m]):.1f})" if inside else ")")
            flagged.append((m, inside))
        out.append(line)
    boots = len(g["N"]) + len(g["T"])
    keys = sorted(set(nd) | set(td), key=str)
    holes = [k for k in keys if len(nd.get(k, [])) + len(td.get(k, [])) != boots]
    differ = [k for k in keys if k not in holes and len({*nd.get(k, []), *td.get(k, [])}) != 1]
    out.append(f"reply digests: {len(keys)} keys over {boots} boots, {len(holes)} key(s) missing a boot's report, {len(differ)} with more than one digest across N and T")
    for k in (holes + differ)[:12]:
        out.append(f"  {'missing' if k in holes else 'differs'}: {k}")
    if absent or holes:
        why = absent + [f"digest {k} missing a boot's report" for k in holes]
        return out, f"U1 SYNC: NOT DECIDED: {len(why)} cell(s) or digest key(s) have no report: {'; '.join(why[:6])}", False
    if differ:
        return out, f"U1 SYNC: NOT ACCEPTED: reply digests differ at {len(differ)} key(s) (and {len(flagged)} cell(s) over the speed limit)", True
    if flagged:
        inside = sum(1 for _, i in flagged if i)
        names = "; ".join(name(m) for m, _ in flagged)
        return out, f"U1 SYNC: NOT ACCEPTED: {len(flagged)} cell(s) more than {LIMIT:.1%} slower ({inside} inside N's boots' range): {names}", False
    return out, f"U1 SYNC: ACCEPTED, no cell more than {LIMIT:.1%} slower and every reply digest equal", False


# ---------------------------------------------------------------- U2 what the series buys

def u2(g):
    """lines: for every cell S0, S1 and T and the two fractions, faster positive; a report only, no verdict."""
    out = [f"== U2 what the series buys: T ({labels(g['T'])}) against S1 ({labels(g['S1'])}) is what the series still buys at the tip; S1 against S0 ({labels(g['S0'])}) is what upstream's"
           " merges since the pin gave a stock user; faster is positive, a column of a group that did not report is no rows, never zero"]
    s0_missing, s0v, _ = load(g["S0"])
    s1_missing, s1v, _ = load(g["S1"])
    t_missing, tv, _ = load(g["T"])
    if s0_missing or s1_missing or t_missing:
        out.append(f"no rows for {', '.join(s0_missing + s1_missing + t_missing)}")
    for m in CELLS:
        s0, s1, t = mean_of(s0v, g["S0"], m), mean_of(s1v, g["S1"], m), mean_of(tv, g["T"], m)
        ts1 = None if t is None or s1 is None else gain(m, t, s1)
        s1s0 = None if s1 is None or s0 is None else gain(m, s1, s0)
        out.append(f"{name(m)}: S0 {fmt(s0)} | S1 {fmt(s1)} | T {fmt(t)} | T against S1 {frac(ts1)} | S1 against S0 {frac(s1s0)}")
    return out


# ---------------------------------------------------------------- U3 digests between stock and stack

def u3(g):
    """lines: T's reply digests against S1's, one line per cell kind; a report, never a verdict."""
    out = [f"== U3 digests T ({labels(g['T'])}) against S1 ({labels(g['S1'])}): one line per cell kind, a report and never a verdict"]
    s1_missing, _, d1 = load(g["S1"])
    t_missing, _, dt = load(g["T"])
    for prefix, kind in DIG_KINDS:
        keys = sorted({k for k in set(dt) | set(d1) if dig_kind(k) == prefix}, key=str)
        if not keys:
            out.append(f"U3 {kind}: no rows")
            continue
        if t_missing or s1_missing:
            out.append(f"U3 {kind}: no rows for " + ("T (" + labels(g["T"]) + ")" if t_missing else "S1 (" + labels(g["S1"]) + ")"))
            continue
        holes = [k for k in keys if len(dt.get(k, [])) != len(g["T"]) or len(d1.get(k, [])) != len(g["S1"])]
        differ = [k for k in keys if k not in holes and len({*dt.get(k, []), *d1.get(k, [])}) != 1]
        if holes:
            out.append(f"U3 {kind}: NOT COMPARABLE, {len(holes)} of {len(keys)} key(s) missing a side's report, {len(differ)} differ")
        elif differ:
            out.append(f"U3 {kind}: DIFFER at {len(differ)} of {len(keys)} key(s): {'; '.join(str(k) for k in differ[:3])}")
        else:
            out.append(f"U3 {kind}: EQUAL at {len(keys)} key(s)")
    return out


# ---------------------------------------------------------------- report and exit code

def report(q91, q92, q95):
    """(lines, U1 verdict, failed): the whole report; failed only when U1 is NOT ACCEPTED by a digest difference."""
    g = groups(q91, q92, q95)
    l1, v1, digest_failed = u1(g)
    lines = [f"== score97: q91 {q91}, q92 {q92}, q95 {q95}"] + l1 + [v1] + u2(g) + u3(g)
    return lines, v1, digest_failed


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--q91", default="docs/audit-2026-11-12/queue-rows/queue91/f91-c", help="queue91's f91-c (default docs/audit-2026-11-12/queue-rows/queue91/f91-c)")
    ap.add_argument("--q92", default="work/pp92/f92-c", help="where queue92, queue96 and queue97 wrote their rows (default work/pp92/f92-c)")
    ap.add_argument("--q95", default="work/pp95/f95-c", help="queue95's f95-c (default work/pp95/f95-c)")
    a = ap.parse_args(argv)
    lines, _, failed = report(a.q91, a.q92, a.q95)
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
