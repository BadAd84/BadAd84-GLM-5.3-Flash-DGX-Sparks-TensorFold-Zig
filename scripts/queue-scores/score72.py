#!/usr/bin/env python3
"""score72.py [ROWS_DIR] - queue72: the six wins together (z1, z3) against the recipe (z0, z0b) in adjacent pairs (z1,z0) (z0b,z3), and the Zig
serve against production (p1 before the window, p2 after it) at production's deployed shape on every leg.
Sections: 1 greedy cells 1/2/4/6/8 candidate vs recipe; 2 the 24 prompts; 3 Zig vs production greedy and sampled; 4 cold prompts;
5 warm turns; 6 growing conversations; 7 decode at depth.
"""
import json
import math
import os
import random
import statistics as st
import sys

D = sys.argv[1] if len(sys.argv) > 1 else "docs/audit-2026-11-12/queue-rows/queue72"
CODE = ["code", "code2", "code3", "code4", "rust", "go", "json", "shell", "math"]


def rows(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


def cell(arm, kind, n):
    rs = rows(f"{D}/f72-{arm}/{kind}{n}.jsonl")
    if not rs:
        return None
    return {"agg": st.mean(r["agg_tok_s"] for r in rs), "rounds": sum((r.get("draft_rounds") or 0) for r in rs),
            "sha": tuple(sorted({tuple(r["sha"]) for r in rs}))}


def pct(a, b):
    return f"{a / b - 1:+.2%}"


def sec1():
    print("== 1. candidate (z1, z3) against the recipe (z0, z0b), greedy, deployed shape: --parallel 4 --context 1048576 (6 and 8 clients queue)")
    for kind, label in (("P", "prose"), ("C", "code")):
        for n in (1, 2, 4, 6, 8):
            c = {a: cell(a, kind, n) for a in ("z0", "z1", "z0b", "z3")}
            if not all(c.values()):
                continue
            pairs = [("z0", "z1"), ("z0b", "z3")]
            ratios = [c[b]["agg"] / c[a]["agg"] - 1 for a, b in pairs]
            both = min(c["z1"]["agg"], c["z3"]["agg"]) > max(c["z0"]["agg"], c["z0b"]["agg"])
            under = max(c["z1"]["agg"], c["z3"]["agg"]) < min(c["z0"]["agg"], c["z0b"]["agg"])
            print(f"{label} {n}: recipe {c['z0']['agg']:.2f} {c['z0b']['agg']:.2f} | candidate {c['z1']['agg']:.2f} {c['z3']['agg']:.2f} | pairs "
                  + " ".join(f"{x:+.2%}" for x in ratios) + f" mean {st.mean(ratios):+.2%} | both candidate boots above both recipe boots: {both}, both under: {under}"
                  + f" | rounds recipe {c['z0']['rounds']} {c['z0b']['rounds']} candidate {c['z1']['rounds']} {c['z3']['rounds']}"
                  + f" | reply sets {len({c[a]['sha'] for a in c})}")


def geo(xs):
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def boot(xs, n=10000, seed=1):
    rnd = random.Random(seed)
    m = sorted(geo([rnd.choice(xs) for _ in xs]) for _ in range(n))
    return m[int(0.025 * n)], m[int(0.975 * n)]


def pp(arm):
    out = {}
    for r in rows(f"{D}/f72-{arm}/pp.jsonl"):
        out[r["name"]] = r
    return out


def sec2():
    arms = {a: pp(a) for a in ("p1", "p2", "z0", "z0b", "z1", "z3")}
    if not all(arms.values()):
        return
    names = list(arms["z0"])
    same_zig = all(len({arms[a][n]["sha12"] for a in ("z0", "z0b", "z1", "z3")}) == 1 for n in names)
    same_prod = all(len({arms[a][n]["sha12"] for a in ("p1", "p2")}) == 1 for n in names)
    same_all = all(len({arms[a][n]["sha12"] for a in arms}) == 1 for n in names)
    print(f"== 2. the 24 prompts one at a time: replies equal across the four Zig boots {same_zig}, across production's two runs {same_prod}, Zig against production {same_all}")
    t = {a: {n: arms[a][n]["span_s"] for n in names} for a in arms}
    avg = lambda arm_list, n: st.mean(t[a][n] for a in arm_list)
    for label, ns in (("all 24", names), ("code-like 9", [n for n in names if n in CODE]), ("prose-like 15", [n for n in names if n not in CODE])):
        row = f"{label}:"
        for name, a, b in (("candidate over recipe", ("z0", "z0b"), ("z1", "z3")), ("candidate over production", ("p1", "p2"), ("z1", "z3")),
                           ("recipe over production", ("p1", "p2"), ("z0", "z0b"))):
            xs = [avg(a, n) / avg(b, n) for n in ns]
            lo, hi = boot(xs)
            row += f" {name} {geo(xs):.4f} ({lo:.4f} to {hi:.4f}, faster on {sum(x > 1 for x in xs)} of {len(xs)});"
        print(row)
    for a in arms:
        print(f"   {a}: decode s {sum(t[a].values()):.1f}, rounds {sum(arms[a][n]['rounds'] for n in names)}, first token mean {1000 * st.mean(arms[a][n]['ttft_s'] for n in names):.0f} ms")


def sec3():
    print("== 3. Zig candidate (mean of z1, z3) against production (mean of p1, p2), aggregate tok/s, deployed shape")
    for kind, label in (("P", "greedy prose"), ("C", "greedy code"), ("SP", "sampled prose"), ("SC", "sampled code")):
        for n in (1, 2, 4, 6, 8):
            z = [cell(a, kind, n) for a in ("z1", "z3")]
            p = [cell(a, kind, n) for a in ("p1", "p2")]
            if not all(z) or not all(p):
                continue
            zm, pm = st.mean(x["agg"] for x in z), st.mean(x["agg"] for x in p)
            print(f"{label} {n}: production {p[0]['agg']:.2f} {p[1]['agg']:.2f} | candidate {z[0]['agg']:.2f} {z[1]['agg']:.2f} | candidate/production {zm / pm:.3f}"
                  + (f" | rounds production {p[0]['rounds']} {p[1]['rounds']} candidate {z[0]['rounds']} {z[1]['rounds']}" if p[0]["rounds"] else ""))
    print("-- the recipe (z0, z0b) against production")
    for kind, label in (("P", "greedy prose"), ("C", "greedy code")):
        for n in (1, 2, 4, 6, 8):
            z = [cell(a, kind, n) for a in ("z0", "z0b")]
            p = [cell(a, kind, n) for a in ("p1", "p2")]
            if all(z) and all(p):
                print(f"{label} {n}: recipe/production {st.mean(x['agg'] for x in z) / st.mean(x['agg'] for x in p):.3f}")


def lc(arm):
    return rows(f"{D}/f72-{arm}/lc.jsonl")


def sec4():
    print("== 4. cold prompts, first token ms (two requests each)")
    for size in (8000, 32000, 120000):
        line = f"{size // 1000}k:"
        for arm in ("p1", "p2", "z1", "z2"):
            v = [r["ttft_ms"] for r in lc(arm) if r["case"] == "cold" and r["target_tokens"] == size]
            line += f" {arm} {' '.join(str(x) for x in v)};"
        print(line)


def sec5():
    print("== 5. warm turns (ttft.py's method), first token ms, with the tokens resumed")
    for tagpart, label in (("wt100", "~100k +2,000 idle"), ("wt250", "~250k +600 idle"), ("wt250L", "~250k +600 beside 3 streams")):
        line = f"{label}:"
        for arm in ("p1", "p2", "z1", "z2"):
            w = [r for r in lc(arm) if r["case"] == "warm" and r["tag"].endswith("-" + tagpart)]
            line += f" {arm} {' '.join(str(r['ttft_ms']) for r in w)} (new {st.mean(r['prompt_tokens'] - (r.get('cached_tokens') or 0) for r in w):.0f});" if w else f" {arm} -;"
        print(line)


def chain(arm, tag):
    return [r for r in rows(f"{D}/f72-{arm}/chain.jsonl") if r["tag"] == tag]


def sec6():
    print("== 6. growing conversations (a message of ~1,000 tokens and a 128-token reply a turn), first token ms by turn; new = prompt tokens not cached")
    for c, label in (("c100", "~100k first turn, 7 more turns"), ("c250", "~250k first turn, 5 more turns")):
        print(f"-- {label}")
        tab = {}
        for arm, pre in (("p1", "f72p1"), ("p2", "f72p2"), ("z1", "f72z1"), ("z2", "f72z2")):
            tab[arm] = chain(arm, f"{pre}-{c}")
            r = tab[arm]
            print(f"{arm}: first turn {r[0]['ttft_ms']} ms ({r[0]['prompt_tokens']} tokens); turns 2+: {' '.join(str(x['ttft_ms']) for x in r[1:])} | mean {st.mean(x['ttft_ms'] for x in r[1:]):.0f} ms"
                  f" | new tokens {' '.join(str(x['prompt_tokens'] - (x.get('cached_tokens') or 0)) for x in r[1:])}")
        pm = st.mean(x["ttft_ms"] for a in ("p1", "p2") for x in tab[a][1:])
        for a in ("z1", "z2"):
            zm = st.mean(x["ttft_ms"] for x in tab[a][1:])
            print(f"{a} turns 2+ over production {zm / pm:.3f}")
        print(f"z2 (request starts) over z1 (without): {st.mean(x['ttft_ms'] for x in tab['z2'][1:]) / st.mean(x['ttft_ms'] for x in tab['z1'][1:]):.3f}")


def sec7():
    print("== 7. decode at depth (tokens / first-to-last-chunk span) and first token, production vs the candidate")
    for arm in ("p1", "p2", "z1"):
        rs = rows(f"{D}/f72-{arm}/ld.jsonl")
        print(f"{arm}: " + "; ".join(f"{r['name']}/{r['rep']}: {r['tokens'] / r['span_s']:.1f} tok/s, ttft {r['ttft_s']:.1f}s, rounds {r['rounds']}" for r in rs))

def md():
    """The tables the docs quote, from the same rows (markdown): production = mean of p1 and p2, Zig = mean of z1 and z3."""
    print("\n== 8. tables for the docs")
    print("| decode, aggregate tok/s | production | Zig | Zig over production |\n|---|---:|---:|---:|")
    for kind, label in (("P", "greedy prose"), ("C", "greedy code"), ("SP", "sampled prose"), ("SC", "sampled code")):
        for n in (1, 2, 4, 6, 8):
            z = [cell(a, kind, n) for a in ("z1", "z3")]
            p = [cell(a, kind, n) for a in ("p1", "p2")]
            if all(z) and all(p):
                zm, pm = st.mean(x["agg"] for x in z), st.mean(x["agg"] for x in p)
                print(f"| {label}, {n} streams | {pm:.2f} | {zm:.2f} | {zm / pm:.3f} |")
    print("\n| cold first token | production ms (4 requests) | Zig ms (2 requests) | Zig over production |\n|---|---:|---:|---:|")
    for size in (8000, 32000, 120000):
        p = [r["ttft_ms"] for a in ("p1", "p2") for r in lc(a) if r["case"] == "cold" and r["target_tokens"] == size]
        z = [r["ttft_ms"] for r in lc("z1") if r["case"] == "cold" and r["target_tokens"] == size]
        print(f"| {size // 1000}k | {st.mean(p):.0f} | {st.mean(z):.0f} | {st.mean(z) / st.mean(p):.3f}x |")
    print("\n| growing conversation, turns 2 and later (mean first token ms) | production | Zig without request starts | Zig with request starts |\n|---|---:|---:|---:|")
    for c, label in (("c100", "~113k tokens, 7 turns"), ("c250", "~284k tokens, 5 turns")):
        pm = st.mean(x["ttft_ms"] for a, pre in (("p1", "f72p1"), ("p2", "f72p2")) for x in chain(a, f"{pre}-{c}")[1:])
        z1 = st.mean(x["ttft_ms"] for x in chain("z1", f"f72z1-{c}")[1:])
        z2 = st.mean(x["ttft_ms"] for x in chain("z2", f"f72z2-{c}")[1:])
        print(f"| {label} | {pm:.0f} | {z1:.0f} ({z1 / pm:.2f}x) | {z2:.0f} ({z2 / pm:.2f}x) |")


if __name__ == "__main__":
    sec1()
    sec2()
    sec3()
    sec4()
    sec5()
    sec6()
    sec7()
    md()
