#!/usr/bin/env python3
"""score77.py [ROWS_DIR] - queue77, the final confirmation (scripts/queues/queue77.sh).

A: boots P1 N1 N2 P2 at --parallel 4 --context 1048576 (P the recipe as committed, N the recipe plus the switches queue75 and queue76 settled): greedy and
   sampled aggregate tok/s at 1 / 2 / 4 clients in the pairs (P1, N1) and (P2, N2), reply sets, the 24 prompts one at a time, cold first token at
   8k / 32k / 120k (one seed on every boot) and the growing conversation (salt c74).
R: boots R1 R2 (N plus TF_GLM_REQUEST_STARTS=1) against the mean of N1 and N2 on the same cells.
B: boots P1 N2 N3 P4 at --parallel 6 and --parallel 8: the same pairs at 6 and 8 clients.
E: the disk tier with N and request starts (disktier-f77/table.md, printed as it is).
"""
import json
import math
import os
import random
import statistics as st
import sys

D = sys.argv[1] if len(sys.argv) > 1 else "docs/audit-2026-11-12/queue-rows/queue77"
KINDS = (("P", "greedy prose"), ("C", "greedy code"), ("SP", "sampled prose"), ("SC", "sampled code"))
CODE = ["code", "code2", "code3", "code4", "rust", "go", "json", "shell", "math"]


def rows(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


def pct(a, b):
    return f"{a / b - 1:+.2%}"


def cell(d, kind, n):
    rs = rows(f"{d}/{kind}{n}.jsonl")
    if not rs:
        return None
    return {"agg": st.mean(r["agg_tok_s"] for r in rs), "rounds": sum((r.get("draft_rounds") or 0) for r in rs),
            "sha": tuple(sorted({tuple(r["sha"]) for r in rs}))}


def pairs(dirs, levels, title):
    """dirs: (P first, N first, N second, P second); the pairs are (P first, N first) and (P second, N second)."""
    print(title)
    for kind, label in KINDS:
        for n in levels:
            c = [cell(d, kind, n) for d in dirs]
            if not all(c):
                continue
            p1, n1, n2, p2 = c
            ratios = [n1["agg"] / p1["agg"] - 1, n2["agg"] / p2["agg"] - 1]
            both = min(n1["agg"], n2["agg"]) > max(p1["agg"], p2["agg"])
            under = max(n1["agg"], n2["agg"]) < min(p1["agg"], p2["agg"])
            print(f"{label} {n}: recipe {p1['agg']:.2f} {p2['agg']:.2f} | new {n1['agg']:.2f} {n2['agg']:.2f} | pairs "
                  + " ".join(f"{x:+.2%}" for x in ratios) + f" mean {st.mean(ratios):+.2%} | both new above both old: {both}, both under: {under}"
                  + f" | rounds old {p1['rounds']} {p2['rounds']} new {n1['rounds']} {n2['rounds']} | reply sets {len({x['sha'] for x in c})}")


def geo(xs):
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def boot_ci(xs, n=10000, seed=1):
    rnd = random.Random(seed)
    m = sorted(geo([rnd.choice(xs) for _ in xs]) for _ in range(n))
    return m[int(0.025 * n)], m[int(0.975 * n)]


def pp(label):
    return {r["name"]: r for r in rows(f"{D}/f77-c/dec-{label}/pp.jsonl")}


def secA():
    dirs = [f"{D}/f77-c/dec-{l}" for l in ("P1", "N1", "N2", "P2")]
    pairs(dirs, (1, 2, 4, 6, 8), "== A. the final recipe (N) against the committed one (P), --parallel 4 --context 1048576 (6 and 8 clients queue on this boot)")
    arms = {l: pp(l) for l in ("P1", "N1", "N2", "P2")}
    if all(arms.values()):
        names = list(arms["P1"])
        same = all(len({arms[l][n]["sha12"] for l in arms}) == 1 for n in names)
        print(f"-- the 24 prompts one at a time: replies equal across the four boots {same}")
        t = {l: {n: arms[l][n]["span_s"] for n in names} for l in arms}
        avg = lambda ls, n: st.mean(t[l][n] for l in ls)
        for label, ns in (("all 24", names), ("code-like 9", [n for n in names if n in CODE]), ("prose-like 15", [n for n in names if n not in CODE])):
            xs = [avg(("P1", "P2"), n) / avg(("N1", "N2"), n) for n in ns]
            lo, hi = boot_ci(xs)
            print(f"{label}: N over P {geo(xs):.4f} ({lo:.4f} to {hi:.4f}, faster on {sum(x > 1 for x in xs)} of {len(xs)})")


def secR():
    print("== R and V: request starts (R1 R2) and MM_WIDE=2 (V1) against N (the mean of N1 and N2), the same cells")
    for kind, label in KINDS:
        for n in (1, 2, 4, 6, 8):
            nn = [cell(f"{D}/f77-c/dec-{l}", kind, n) for l in ("N1", "N2")]
            rr = [cell(f"{D}/f77-c/dec-{l}", kind, n) for l in ("R1", "R2")]
            vv = cell(f"{D}/f77-c/dec-V1", kind, n)
            if not all(nn):
                continue
            m = st.mean(x["agg"] for x in nn)
            if all(rr):
                inside = all(min(x["agg"] for x in nn) <= r["agg"] <= max(x["agg"] for x in nn) for r in rr)
                print(f"{label} {n}: N {nn[0]['agg']:.2f} {nn[1]['agg']:.2f} | R {rr[0]['agg']:.2f} {rr[1]['agg']:.2f} ({pct(rr[0]['agg'], m)} {pct(rr[1]['agg'], m)}) "
                      f"| both R inside N's range: {inside} | reply sets {len({x['sha'] for x in nn + rr})}")
            if vv:
                print(f"{label} {n}: V1 {vv['agg']:.2f} ({pct(vv['agg'], m)}) | reply sets {len({x['sha'] for x in nn + [vv]})}")


def cold_ms(rs, arm, size):
    v = [r["ttft_ms"] for r in rs if r.get("case") == "cold" and r["tag"] == arm and r["target_tokens"] == size]
    return st.mean(v) if v else None


def secCold():
    rs = rows(f"{D}/f77-c/rows.jsonl")
    cold = [r for r in rs if r.get("case") == "cold"]
    if not cold:
        return
    print("== cold first token, ms (the mean of a boot's two requests, one seed on every boot); % against the recipe (the mean of P1 and P2)")
    for size in sorted({r["target_tokens"] for r in cold}):
        base = [cold_ms(rs, a, size) for a in ("P1", "P2")]
        base = [x for x in base if x is not None]
        ref = st.mean(base) if base else None
        line = f"{size // 1000}k:"
        for a in ("P1", "N1", "N2", "P2", "V1", "X1", "X2", "Y1", "Y2", "R1", "R2"):
            x = cold_ms(rs, a, size)
            if x is not None:
                line += f" {a} {x:.0f}" + (f" ({pct(x, ref)})" if ref and a not in ("P1", "P2") else "")
        print(line)
    print("-- replies: every (size, request) across the arms")
    for size in sorted({r["target_tokens"] for r in cold}):
        for rep in sorted({r["rep"] for r in cold if r["target_tokens"] == size}):
            got = {r["tag"]: r["token_sha"] for r in cold if r["target_tokens"] == size and r["rep"] == rep}
            print(f"{size // 1000}k request {rep}: {len(got)} arms, {len(set(got.values()))} digest(s)")


def chain_of(label):
    c = [r for r in rows(f"{D}/f77-c/{label}/chain.jsonl") if r["tag"] == "c74"]
    return c or None


def secChain():
    tab = {l: chain_of(l) for l in ("P1", "N1", "N2", "P2", "V1", "X1", "X2", "Y1", "Y2", "R1", "R2")}
    tab = {l: c for l, c in tab.items() if c}
    if not tab:
        return
    print("== growing conversations (salt c74), first token ms by turn")
    for l, c in tab.items():
        print(f"{l}: first turn {c[0]['ttft_ms']} ms ({c[0]['prompt_tokens']} tokens); turns 2+: {' '.join(str(x['ttft_ms']) for x in c[1:])}"
              f" | mean {st.mean(x['ttft_ms'] for x in c[1:]):.0f} ms | cached {' '.join(str(x.get('cached_tokens') or 0) for x in c[1:])}")
    n = min(len(c) for c in tab.values())
    for t in range(n):
        got = {l: c[t]["token_sha"] for l, c in tab.items()}
        pt = {l: c[t]["prompt_tokens"] for l, c in tab.items()}
        print(f"turn {t + 1}: {len(set(got.values()))} reply digest(s) over {len(got)} arms, {len(set(pt.values()))} prompt length(s)")
    if all(l in tab for l in ("P1", "P2")):
        first = st.mean(tab[l][0]["ttft_ms"] for l in ("P1", "P2"))
        warm = st.mean(st.mean(x["ttft_ms"] for x in tab[l][1:]) for l in ("P1", "P2"))
        for grp in (("N1", "N2"), ("V1",), ("X1",), ("X2",), ("Y1",), ("Y2",), ("R1", "R2")):
            if all(l in tab for l in grp):
                print(f"{'/'.join(grp)} over the recipe: first turn {st.mean(tab[l][0]['ttft_ms'] for l in grp) / first:.3f}, "
                      f"turns 2+ {st.mean(st.mean(x['ttft_ms'] for x in tab[l][1:]) for l in grp) / warm:.3f}")


def secB():
    for P in (6, 8):
        dirs = [f"{D}/f77-b/b77-{l}-P{P}" for l in ("P1", "N2", "N3", "P4")]
        pairs(dirs, (P,), f"== B. --parallel {P}, {P} clients")


def secE():
    p = f"{D}/disktier-f77/table.md"
    if os.path.exists(p):
        print("== E. the disk tier with N and request starts")
        print(open(p).read())


if __name__ == "__main__":
    secA()
    secR()
    secCold()
    secChain()
    secB()
    secE()
