#!/usr/bin/env python3
"""score74.py [ROWS_DIR] - queue74.

C1: boots f1 rs1 rs2 f2 (A B B A), rs = TF_GLM_REQUEST_STARTS=1: cold first token at 8k / 32k / 120k (two requests a boot, one seed on every boot), a
    growing conversation (one salt, so every arm's turns are the same prompts) and greedy decode at 1 / 2 / 4 clients.
E:  the disk tier with request starts (disktier-f74/table.md, printed as it is).
C2: candidates mw sp p4 lr2 all against the recipe, f2 and f3 and f4 beside f1 as the controls; every candidate boots twice (forward and reversed order):
    cold first token and greedy decode at 1 / 2 / 4 clients; the reply digests of every boot are compared.
"""
import json
import math
import os
import statistics as st
import sys

D = sys.argv[1] if len(sys.argv) > 1 else "docs/audit-2026-11-12/queue-rows/queue74"
CONTROLS = ("f1", "f2", "f3", "f4")
PAIRS = {"rs": ("rs1", "rs2"), "mw": ("mw", "mw2"), "sp": ("sp", "sp2"), "p4": ("p4", "p42"), "lr2": ("lr2", "lr22"), "all": ("all", "all2")}


def rows(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


def pct(a, b):
    return f"{a / b - 1:+.2%}"


def lc():
    return rows(f"{D}/f74-c/rows.jsonl")


def cold_ms(rs, arm, size):
    v = [r["ttft_ms"] for r in rs if r.get("case") == "cold" and r["tag"] == arm and r["target_tokens"] == size]
    return st.mean(v) if v else None


def secC():
    rs = lc()
    if not rs:
        return
    boots = [r for r in rs if r.get("case") == "boot"]
    print("== boots: " + ", ".join(f"{b['tag']} rc {b.get('boot_rc')}" for b in boots))
    cold = [r for r in rs if r.get("case") == "cold"]
    sizes = sorted({r["target_tokens"] for r in cold})
    arms = [a for a in dict.fromkeys(r["tag"] for r in cold)]
    print("-- cold first token, ms (the mean of a boot's two requests); % against the controls' mean (f1 f2 f3 f4 where they ran)")
    for size in sizes:
        ctl = [cold_ms(rs, a, size) for a in CONTROLS]
        ctl = [x for x in ctl if x is not None]
        ref = st.mean(ctl) if ctl else None
        spread = f"controls {' '.join(f'{x:.0f}' for x in ctl)} (spread {(max(ctl) / min(ctl) - 1):.2%})" if len(ctl) > 1 else ""
        line = f"{size // 1000}k: {spread};"
        for a in arms:
            x = cold_ms(rs, a, size)
            if x is not None and a not in CONTROLS:
                line += f" {a} {x:.0f} ({pct(x, ref)});"
        print(line)
    print("-- candidates: the two boots' mean against the controls' mean, and whether the two boots agree in sign")
    for name, (a, b) in PAIRS.items():
        line = f"{name}:"
        for size in sizes:
            ctl = [cold_ms(rs, c, size) for c in CONTROLS]
            ctl = [x for x in ctl if x is not None]
            x, y = cold_ms(rs, a, size), cold_ms(rs, b, size)
            if not ctl or x is None or y is None:
                continue
            ref = st.mean(ctl)
            agree = (x < ref) == (y < ref)
            line += f" {size // 1000}k {pct(st.mean([x, y]), ref)} ({pct(x, ref)} {pct(y, ref)}{'' if agree else ', SIGNS DIFFER'});"
        print(line)
    print("-- replies: every (size, request) across the arms")
    for size in sizes:
        for rep in sorted({r["rep"] for r in cold}):
            got = {r["tag"]: r["token_sha"] for r in cold if r["target_tokens"] == size and r["rep"] == rep}
            ref = got.get("f1")
            odd = sorted(t for t, s in got.items() if s != ref)
            print(f"{size // 1000}k request {rep}: {len(got)} arms, {len(set(got.values()))} digest(s)" + (f"; differ from f1: {odd}" if odd else ""))


def secChain():
    tab = {}
    for a in ("f1", "rs1", "rs2", "f2"):
        c = [r for r in rows(f"{D}/f74-c/{a}/chain.jsonl") if r["tag"] == "c74"]
        if c:
            tab[a] = c
    if not tab:
        return
    print("== growing conversations (one salt: the same prompts in every arm), first token ms by turn")
    for a, c in tab.items():
        print(f"{a}: first turn {c[0]['ttft_ms']} ms ({c[0]['prompt_tokens']} tokens); turns 2+: {' '.join(str(x['ttft_ms']) for x in c[1:])}"
              f" | mean {st.mean(x['ttft_ms'] for x in c[1:]):.0f} ms | cached {' '.join(str(x.get('cached_tokens') or 0) for x in c[1:])}")
    n = min(len(c) for c in tab.values())
    for t in range(n):
        got = {a: c[t]["token_sha"] for a, c in tab.items()}
        pt = {a: c[t]["prompt_tokens"] for a, c in tab.items()}
        print(f"turn {t + 1}: {len(set(got.values()))} reply digest(s) over {len(got)} arms, {len(set(pt.values()))} prompt length(s)"
              + ("" if len(set(got.values())) == 1 else f" {got}"))
    ctl = [tab[a] for a in ("f1", "f2") if a in tab]
    rs = [tab[a] for a in ("rs1", "rs2") if a in tab]
    if ctl and rs:
        first = lambda cs: st.mean(c[0]["ttft_ms"] for c in cs)
        warm = lambda cs: st.mean(st.mean(x["ttft_ms"] for x in c[1:]) for c in cs)
        print(f"request starts over the recipe: first turn {first(rs) / first(ctl):.3f}, turns 2+ {warm(rs) / warm(ctl):.3f}")


def cell(arm, kind, n):
    r = rows(f"{D}/f74-c/dec-{arm}/{kind}{n}.jsonl")
    if not r:
        return None
    return {"agg": st.mean(x["agg_tok_s"] for x in r), "sha": tuple(sorted({tuple(x["sha"]) for x in r}))}


def secDec():
    print("== greedy decode at 1 / 2 / 4 clients (--parallel 4, context 1,048,576): each boot against the controls' mean (f1 f2 f3 f4)")
    arms = [a for a in ("rs1", "rs2", "mw", "sp", "p4", "lr2", "all", "all2", "lr22", "p42", "sp2", "mw2") if cell(a, "P", 1)]
    for kind, label in (("P", "prose"), ("C", "code")):
        for n in (1, 2, 4):
            ctl = {a: cell(a, kind, n) for a in CONTROLS}
            ctl = {a: c for a, c in ctl.items() if c}
            if not ctl:
                continue
            m = st.mean(c["agg"] for c in ctl.values())
            shas = {c["sha"] for c in ctl.values()}
            line = f"{label} {n}: controls " + " ".join(f"{a} {c['agg']:.2f}" for a, c in ctl.items()) + f" (spread {(max(c['agg'] for c in ctl.values()) / min(c['agg'] for c in ctl.values()) - 1):.2%}); reply sets {len(shas)} |"
            for a in arms:
                c = cell(a, kind, n)
                if c:
                    line += f" {a} {c['agg']:.2f} ({pct(c['agg'], m)}{'' if c['sha'] in shas else ', REPLIES DIFFER'})"
            print(line)
    print("-- candidates: the two boots' mean decode against the controls' mean, per cell")
    for name, (a, b) in PAIRS.items():
        line = f"{name}:"
        for kind, label in (("P", "prose"), ("C", "code")):
            for n in (1, 2, 4):
                ctl = [cell(c, kind, n) for c in CONTROLS]
                ctl = [c["agg"] for c in ctl if c]
                x, y = cell(a, kind, n), cell(b, kind, n)
                if ctl and x and y:
                    line += f" {label}{n} {pct(st.mean([x['agg'], y['agg']]), st.mean(ctl))};"
        print(line)


def secE():
    p = f"{D}/disktier-f74/table.md"
    if os.path.exists(p):
        print("== E. disk tier with request starts (patches/learn-starts and patches/disk-any-position)")
        print(open(p).read())


if __name__ == "__main__":
    secC()
    secChain()
    secDec()
    secE()
