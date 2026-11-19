#!/usr/bin/env python3
"""score73.py [ROWS_DIR] - queue73.

E: the disk tier with TF_GLM_REQUEST_STARTS=1 on the image without solo-cuts (disktier-f73/table.md, printed as it is).
A: boots a73-R1 a73-F2 a73-F3 a73-R4 at --parallel 4 --context 1048576 (R the recipe before 2026-11-19, F the committed recipe): greedy and sampled
   aggregate tok/s at 1 / 2 / 4 clients in the pairs (R1, F2) and (R4, F3), reply sets, and the 24 prompts one at a time.
C: cold first token at 8k / 32k / 120k (two requests a boot, one seed on every boot) per arm against the recipe's mean (f1, f2), the reply digest of
   every (size, request) across all arms, and the growing conversations (longctx.py chain) of the arms that ran one.
B: boots b73-R1-P6 b73-F2-P6 b73-F3-P6 b73-R4-P6 (and P8): the same pairs as A at 6 and 8 clients on a serve booted with that --parallel.
"""
import json
import math
import os
import random
import statistics as st
import sys

D = sys.argv[1] if len(sys.argv) > 1 else "docs/audit-2026-11-12/queue-rows/queue73"
CODE = ["code", "code2", "code3", "code4", "rust", "go", "json", "shell", "math"]


def rows(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


def pct(a, b):
    return f"{a / b - 1:+.2%}"


def cell(boot, kind, n):
    rs = rows(f"{D}/{boot}/{kind}{n}.jsonl")
    if not rs:
        return None
    return {"agg": st.mean(r["agg_tok_s"] for r in rs), "rounds": sum((r.get("draft_rounds") or 0) for r in rs),
            "sha": tuple(sorted({tuple(r["sha"]) for r in rs}))}


def pairs(boots, levels, title):
    """boots: (R first, F first, F second, R second); pairs are (R first, F first) and (R second, F second)."""
    print(title)
    for kind, label in (("P", "greedy prose"), ("C", "greedy code"), ("SP", "sampled prose"), ("SC", "sampled code")):
        for n in levels:
            c = [cell(b, kind, n) for b in boots]
            if not all(c):
                continue
            r1, f1, f2, r2 = c
            ratios = [f1["agg"] / r1["agg"] - 1, f2["agg"] / r2["agg"] - 1]
            both = min(f1["agg"], f2["agg"]) > max(r1["agg"], r2["agg"])
            under = max(f1["agg"], f2["agg"]) < min(r1["agg"], r2["agg"])
            print(f"{label} {n}: recipe-old {r1['agg']:.2f} {r2['agg']:.2f} | recipe {f1['agg']:.2f} {f2['agg']:.2f} | pairs "
                  + " ".join(f"{x:+.2%}" for x in ratios) + f" mean {st.mean(ratios):+.2%} | both new above both old: {both}, both under: {under}"
                  + f" | rounds old {r1['rounds']} {r2['rounds']} new {f1['rounds']} {f2['rounds']} | reply sets {len({x['sha'] for x in c})}")


def geo(xs):
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def boot_ci(xs, n=10000, seed=1):
    rnd = random.Random(seed)
    m = sorted(geo([rnd.choice(xs) for _ in xs]) for _ in range(n))
    return m[int(0.025 * n)], m[int(0.975 * n)]


def pp(boot):
    return {r["name"]: r for r in rows(f"{D}/{boot}/pp.jsonl")}


def secA():
    boots = ["a73-R1", "a73-F2", "a73-F3", "a73-R4"]
    pairs(boots, (1, 2, 4), "== A. the committed recipe (F) against the recipe before 2026-11-19 (R), --parallel 4 --context 1048576")
    arms = {b: pp(b) for b in boots}
    if not all(arms.values()):
        return
    names = list(arms[boots[0]])
    same = all(len({arms[b][n]["sha12"] for b in boots}) == 1 for n in names)
    print(f"-- the 24 prompts one at a time: replies equal across the four boots {same}")
    t = {b: {n: arms[b][n]["span_s"] for n in names} for b in boots}
    avg = lambda bs, n: st.mean(t[b][n] for b in bs)
    for label, ns in (("all 24", names), ("code-like 9", [n for n in names if n in CODE]), ("prose-like 15", [n for n in names if n not in CODE])):
        xs = [avg(("a73-R1", "a73-R4"), n) / avg(("a73-F2", "a73-F3"), n) for n in ns]
        lo, hi = boot_ci(xs)
        print(f"{label}: F over R {geo(xs):.4f} ({lo:.4f} to {hi:.4f}, faster on {sum(x > 1 for x in xs)} of {len(xs)})")


def secB():
    for P in (6, 8):
        boots = [f"b73-{l}-P{P}" for l in ("R1", "F2", "F3", "R4")]
        pairs(boots, (P,), f"== B. --parallel {P}, {P} clients")


def lc():
    return rows(f"{D}/f73-c/rows.jsonl")


def secC():
    rs = lc()
    if not rs:
        return
    boots = [r for r in rs if r.get("case") == "boot"]
    print("== C boots: " + ", ".join(f"{b['tag']} rc {b.get('boot_rc')} up {b.get('up_s')} s" for b in boots))
    cold = [r for r in rs if r.get("case") == "cold"]
    arms = sorted({r["tag"] for r in cold}, key=lambda a: (a not in ("f1", "f2"), a))
    print("-- cold first token, ms (the mean of a boot's two requests); % against the recipe (mean of f1 and f2)")
    for size in sorted({r["target_tokens"] for r in cold}):
        def m(a):
            v = [r["ttft_ms"] for r in cold if r["tag"] == a and r["target_tokens"] == size]
            return st.mean(v) if v else None
        base = [m(a) for a in ("f1", "f2") if m(a) is not None]
        ref = st.mean(base) if base else None
        line = f"{size // 1000}k:"
        for a in arms:
            x = m(a)
            if x is None:
                continue
            line += f" {a} {x:.0f}" + (f" ({pct(x, ref)})" if ref and a not in ("f1", "f2") else "") + ";"
        print(line)
    print("-- replies: every (size, request) across the arms")
    for size in sorted({r["target_tokens"] for r in cold}):
        for rep in sorted({r["rep"] for r in cold}):
            got = {r["tag"]: r["token_sha"] for r in cold if r["target_tokens"] == size and r["rep"] == rep}
            ref = got.get("f1")
            odd = sorted(t for t, s in got.items() if s != ref)
            print(f"{size // 1000}k request {rep}: {len(got)} arms, {len(set(got.values()))} digest(s)" + (f"; differ from f1: {odd}" if odd else ""))
    print("-- growing conversations, first token ms by turn (new = prompt tokens not cached)")
    tab = {}
    for a in ("f1", "rs", "rs0"):
        c = [r for r in rows(f"{D}/f73-c/{a}/chain.jsonl") if r["tag"] == f"c73{a}"]
        if not c:
            continue
        tab[a] = c
        print(f"{a}: first turn {c[0]['ttft_ms']} ms ({c[0]['prompt_tokens']} tokens); turns 2+: {' '.join(str(x['ttft_ms']) for x in c[1:])} | mean {st.mean(x['ttft_ms'] for x in c[1:]):.0f} ms"
              f" | new tokens {' '.join(str(x['prompt_tokens'] - (x.get('cached_tokens') or 0)) for x in c[1:])}")
    if "f1" in tab:
        for a in ("rs", "rs0"):
            if a in tab:
                print(f"{a} over f1: first turn {tab[a][0]['ttft_ms'] / tab['f1'][0]['ttft_ms']:.3f}, turns 2+ {st.mean(x['ttft_ms'] for x in tab[a][1:]) / st.mean(x['ttft_ms'] for x in tab['f1'][1:]):.3f}")
    if "rs" in tab and "rs0" in tab:
        print(f"rs over rs0 (solo between starts): first turn {tab['rs'][0]['ttft_ms'] / tab['rs0'][0]['ttft_ms']:.3f}, turns 2+ "
              f"{st.mean(x['ttft_ms'] for x in tab['rs'][1:]) / st.mean(x['ttft_ms'] for x in tab['rs0'][1:]):.3f}")


def secE():
    p = f"{D}/disktier-f73/table.md"
    if os.path.exists(p):
        print("== E. disk tier with request starts (image without solo-cuts)")
        print(open(p).read())


def secLR():
    fs = ["a73-F2", "a73-F3"]
    for arm in ("lr2", "lr4", "sp"):
        printed = False
        for kind, label in (("P", "greedy prose"), ("C", "greedy code")):
            for n in (1, 2, 4):
                c = cell(f"f73-c/dec-{arm}", kind, n)
                f = [cell(b, kind, n) for b in fs]
                if not c or not all(f):
                    continue
                if not printed:
                    print(f"== decode with {arm} (lr2 and lr4: TF_GLM_OVN_LATENT_ROWS; sp: TF_GLM_OVN_SIDE_PRIO) against the recipe's two boots of block A (a73-F2, a73-F3)")
                    printed = True
                m = st.mean(x["agg"] for x in f)
                print(f"{label} {n}: {arm} {c['agg']:.2f} | recipe {f[0]['agg']:.2f} {f[1]['agg']:.2f} = {pct(c['agg'], m)} | reply set equals both recipe boots': {c['sha'] == f[0]['sha'] == f[1]['sha']}")


if __name__ == "__main__":
    secE()
    secA()
    secC()
    secLR()
    secB()
