#!/usr/bin/env python3
"""score92.py [--q91 DIR] [--q92 DIR] - queue92 (scripts/queues/queue92.sh): did anyone else's work speed the serve up, measured on the same boxes and instrument.

DIR holds rows.jsonl, <label>/chain.jsonl and dec-<label>/{P,C,SP,SC}<clients>.jsonl as the queues write them: --q91 is queue91's f91-c (stock main `mps`, our stack `mn1` `mn2`),
--q92 queue92's f92-c. Every arm here but the stack runs KNOBS=off (the runtime section of scripts/env/prod.env alone, no knob of ours), so a rung is what a user of upstream gets.

THE LADDER (what upstream's merged work gave us). Rungs in time order, each the mean of its boots: v1.2.9 (s9a s9b), v1.2.10 (s10a), v1.3.0 (s13a s13b), the main commit
3661a4281 that has the dependent launches (PDL) and not the 16-pair item plan (ud1), the main commit 32c361db9 that has the item plan and not the lanes' draft-depth hold (ui1),
and main 1ece6e6 (mps of --q91, sm2 sm3). smz (stock main with TF_GLM_PDL=0) is printed beside it as the PDL attribution row. For every cell (the cold first token at 8k, 32k and 120k, the mean first token of the growing conversation's turns 2 to 8, the aggregate tokens a second of
greedy and of sampled prose and code at 1, 2, 4, 6 and 8 clients) a rung's change against the rung before and against v1.2.9 is printed, faster positive. A step is CLEAR when every
boot of the rung lies beyond every boot of the rung before it (faster or slower), and the line says so; a step inside the boots' spread is printed as a number and not called a gain.
A reply digest that differs between two rungs is a numerics change by upstream and is listed.

THE PR RULE, written before queue92's rows existed. An arm of an open pull request (smr: request starts on main; pd: #3616, the drafter's MLP split; pm: #3659, MoE without row
copies) is a CANDIDATE against the main group (mps, sm2, sm3) when
  - no cell reads more than 1.0% slower than the main group's mean, and
  - at least one cell of the cold first tokens, the conversation's warm turns or the decode at 1, 2 and 4 clients is faster than the main group's best boot by more than 1.0%, and
  - every reply digest equals the main group's one digest.
Anything else is NOT A CANDIDATE, with the cells or the digests that decided it. A missing boot or cell is NOT DECIDED. Whether a candidate is carried is the owner's call.

THE STACK. Our stack on main (mn1 mn2 of --q91) against the main group, faster positive: what the series still buys over upstream's own code.
"""
import argparse
import importlib.util
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("score91", os.path.join(HERE, "score91.py"))
s91 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s91)

LIMIT = 0.010  # more than this slower on any cell, or a gain smaller than this beyond the best reference boot, is not counted
GAIN_LEVELS = (1, 2, 4)
METRICS = [("cold", s) for s in s91.SIZES] + [("warm",)] + [("dec", k, n) for k, _ in s91.KINDS for n in s91.LEVELS]
GAIN_METRICS = [("cold", s) for s in s91.SIZES] + [("warm",)] + [("dec", k, n) for k, _ in s91.KINDS for n in GAIN_LEVELS]


def rungs(q91, q92):
    return [("v1.2.9", [(q92, "s9a"), (q92, "s9b")]), ("v1.2.10", [(q92, "s10a")]), ("v1.3.0", [(q92, "s13a"), (q92, "s13b")]),
            ("PDL in (3661a4281)", [(q92, "ud1")]), ("item plan in (32c361db9)", [(q92, "ui1")]), ("main 1ece6e6", main_boots(q91, q92))]


def main_boots(q91, q92):
    return [(q91, "mps"), (q92, "sm2"), (q92, "sm3")]


def gain(metric, new, ref):
    """Fraction by which `new` is faster than `ref`: latency down by that much, or throughput up by that much of the reference rate."""
    return -s91.slower(metric, new, ref)


def beyond(metric, new_boots, ref_boots):
    """+1 when every new boot is faster than every reference boot, -1 when every new boot is slower, else 0."""
    lower_is_better = metric[0] in ("cold", "warm")
    if lower_is_better:
        if max(new_boots) < min(ref_boots):
            return 1
        if min(new_boots) > max(ref_boots):
            return -1
    else:
        if min(new_boots) > max(ref_boots):
            return 1
        if max(new_boots) < min(ref_boots):
            return -1
    return 0


def ladder(q91, q92):
    """(lines, verdict)."""
    out, groups, missing = [], [], []
    for label, boots in rungs(q91, q92):
        miss, vals, digs = s91.group(boots)
        missing += [f"{label}:{m}" for m in miss]
        groups.append((label, vals, digs))
    if missing:
        return out, f"NOT DECIDED: no rows for {', '.join(missing)}"
    out.append("== the ladder: stock upstream at four points, KNOBS=off, the same boxes and instrument; faster is positive")
    for i in range(1, len(groups)):
        (pl, pv, pd), (nl, nv, nd) = groups[i - 1], groups[i]
        first = groups[0][1]
        out.append(f"-- {nl} against {pl} (and against {groups[0][0]})")
        for m in METRICS:
            if m not in pv or m not in nv:
                out.append(f"{s91.name(m)}: MISSING")
                continue
            g = gain(m, st.mean(nv[m]), st.mean(pv[m]))
            cum = gain(m, st.mean(nv[m]), st.mean(first[m])) if m in first else float("nan")
            b = beyond(m, nv[m], pv[m])
            tag = {1: "  CLEAR gain", -1: "  CLEAR loss", 0: ""}[b]
            out.append(f"{s91.name(m)}: {g:+.2%} (cumulative {cum:+.2%}){tag}")
        differ = sorted({k for k in set(pd) | set(nd) if len({*pd.get(k, []), *nd.get(k, [])}) != 1}, key=str)
        out.append(f"reply digests {pl} -> {nl}: {len(differ)} key(s) with more than one digest")
    return out, "LADDER: complete"


def arm(label_boots, ref_boots):
    """(lines, verdict) of one PR arm against the reference group."""
    miss, v, dg = s91.group(label_boots)
    rmiss, ref, rdg = s91.group(ref_boots)
    if miss or rmiss:
        return [], f"NOT DECIDED: no rows for {', '.join(miss + rmiss)}"
    lines, slow_cells, gain_cells, absent = [], [], [], []
    for m in METRICS:
        if m not in v or m not in ref:
            absent.append(s91.name(m))
            continue
        g = gain(m, st.mean(v[m]), st.mean(ref[m]))
        best = max(ref[m]) if m[0] == "dec" else min(ref[m])
        gb = gain(m, st.mean(v[m]), best)
        lines.append(f"{s91.name(m)}: {g:+.2%} against the mean, {gb:+.2%} against the best boot")
        if -g > LIMIT:
            slow_cells.append(f"{s91.name(m)} {g:+.2%}")
        if m in GAIN_METRICS and gb > LIMIT:
            gain_cells.append(f"{s91.name(m)} {gb:+.2%}")
    if absent:
        return lines, f"NOT DECIDED: {len(absent)} cell(s) have no rows: {'; '.join(absent[:6])}"
    differ = sorted({k for k in dg if k in rdg and len({*dg[k], *rdg[k]}) != 1}, key=str)
    reasons = []
    if slow_cells:
        reasons.append(f"{len(slow_cells)} cell(s) more than {LIMIT:.0%} slower: {'; '.join(slow_cells[:6])}")
    if not gain_cells:
        reasons.append(f"no cell faster than the best reference boot by more than {LIMIT:.0%}")
    if differ:
        reasons.append(f"{len(differ)} reply digest(s) differ from the reference's")
    if reasons:
        return lines, "NOT A CANDIDATE: " + "; ".join(reasons)
    return lines, f"CANDIDATE: faster than the best reference boot by more than {LIMIT:.0%} on {len(gain_cells)} cell(s) ({'; '.join(gain_cells[:6])}), no cell slower, every digest equal"


ARMS = (("smr", "request starts on stock main (TF_GLM_REQUEST_STARTS=1)"), ("pd", "#3616 TF_GLM_DRAFT_SPLIT=1"), ("pm", "#3659 TF_GLM_MOE_DIRECT=1"))
ATTRIBUTION = (("smz", "stock main with TF_GLM_PDL=0: the dependent launches off, so PDL's share is the negative of these cells"),
               ("ut1", "the main tip 46c6ee229, KNOBS=off, what upstream merged after our pin 1ece6e6db (the KDA padding at TP=3, a default decode share for long fills, the sampler's small top_k); a report beside the ladder"))


def stack(q91):
    miss, v, _ = s91.group([(q91, "mn1"), (q91, "mn2")])
    return miss, v


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--q91", default="docs/audit-2026-11-12/queue-rows/queue91/f91-c")
    ap.add_argument("--q92", default="docs/audit-2026-11-12/queue-rows/queue92/f92-c")
    a = ap.parse_args(argv)
    lines, verdict = ladder(a.q91, a.q92)
    print("\n".join(lines))
    print(verdict)
    ref = main_boots(a.q91, a.q92)
    for label, text in ARMS:
        lines, v = arm([(a.q92, label)], ref)
        print(f"== {label}: {text} against the main group (mps sm2 sm3); faster is positive")
        print("\n".join(lines))
        print(f"{label}: {v}")
    for label, text in ATTRIBUTION:
        lines, v = arm([(a.q92, label)], ref)
        print(f"== {label}: {text}; against the main group, faster positive")
        print("\n".join(lines) if lines else v)
    sm, sv = stack(a.q91)
    _, mv, _ = s91.group(ref)
    if sm or not mv:
        print(f"== the stack: NOT DECIDED, no rows for {', '.join(sm)}")
    else:
        print("== the stack on main (mn1 mn2) against the main group; faster is positive")
        print("\n".join(f"{s91.name(m)}: {gain(m, st.mean(sv[m]), st.mean(mv[m])):+.2%}" for m in METRICS if m in sv and m in mv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
