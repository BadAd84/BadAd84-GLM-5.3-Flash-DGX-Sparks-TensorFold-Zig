#!/usr/bin/env python3
"""score75.py [ROWS75_DIR [ROWS74_DIR]] - queue75 against the request-starts controls rs1 rs2 (queue74) and rs3 rs4 (queue75).

E:  the disk tier with request starts and the unaligned-state fix (disktier-f75/table.md, printed as it is).
B:  warm turns against the exchanges' row pieces: w1 w2 w3 w6 (TF_GLM_OVERLAP_PIECES) and nr (TF_GLM_ROCE_MULTI=0), chain and greedy decode.
A:  prompt-pass candidates mw sp p4 lr2 all, each booted twice (forward and reversed order): cold first token at 8k / 32k / 120k, chain, decode.
Every arm runs with TF_GLM_REQUEST_STARTS=1; the chain uses one salt (c74), so every arm's turns are the same prompts and the replies must be
the same digests. A candidate is read against the controls' mean and only when its two boots agree in sign.
"""
import json
import os
import statistics as st
import sys

D75 = sys.argv[1] if len(sys.argv) > 1 else "docs/audit-2026-11-12/queue-rows/queue75"
D74 = sys.argv[2] if len(sys.argv) > 2 else "docs/audit-2026-11-12/queue-rows/queue74"
CONTROLS = ("rs1", "rs2", "rs3", "rs4")
NO_STARTS = ("f1", "f2")
PAIRS = {"mw": ("mw", "mw2"), "sp": ("sp", "sp2"), "p4": ("p4", "p42"), "lr2": ("lr2", "lr22"), "all": ("all", "all2")}
WARM = ("w1", "w2", "w3", "w6", "nr")
DIRS = (f"{D75}/f75-c", f"{D74}/f74-c")


def jl(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


def pct(a, b):
    return f"{a / b - 1:+.2%}"


def cold_rows():
    return [r for d in DIRS for r in jl(f"{d}/rows.jsonl") if r.get("case") == "cold"]


def cold_ms(rs, arm, size):
    v = [r["ttft_ms"] for r in rs if r["tag"] == arm and r["target_tokens"] == size]
    return st.mean(v) if v else None


def ctl_list(f, arms=CONTROLS):
    return [x for x in (f(a) for a in arms) if x is not None]


def secE():
    p = f"{D75}/disktier-f75/table.md"
    if os.path.exists(p):
        print("== E. disk tier with request starts, patches/learn-starts and patches/disk-any-position")
        print(open(p).read())


def secCold():
    rs = cold_rows()
    if not rs:
        return
    sizes = sorted({r["target_tokens"] for r in rs})
    arms = list(dict.fromkeys(r["tag"] for r in rs))
    print("== cold first token, ms (the mean of a boot's two requests, one seed on every boot); % against the controls' mean (rs1 rs2 rs3 rs4)")
    for size in sizes:
        ctl = ctl_list(lambda a: cold_ms(rs, a, size))
        ref = st.mean(ctl) if ctl else None
        line = f"{size // 1000}k: controls {' '.join(f'{x:.0f}' for x in ctl)} (spread {max(ctl) / min(ctl) - 1:.2%})" if len(ctl) > 1 else f"{size // 1000}k:"
        for a in arms:
            x = cold_ms(rs, a, size)
            if x is not None and a not in CONTROLS and ref:
                line += f"; {a} {x:.0f} ({pct(x, ref)})"
        print(line)
    print("-- candidates: the two boots' mean against the controls' mean, and whether the two boots agree in sign")
    for name, (a, b) in PAIRS.items():
        line = f"{name}:"
        for size in sizes:
            ctl = ctl_list(lambda c: cold_ms(rs, c, size))
            x, y = cold_ms(rs, a, size), cold_ms(rs, b, size)
            if not ctl or x is None or y is None:
                continue
            ref = st.mean(ctl)
            agree = (x < ref) == (y < ref)
            line += f" {size // 1000}k {pct(st.mean([x, y]), ref)} ({pct(x, ref)} {pct(y, ref)}{'' if agree else ', SIGNS DIFFER'});"
        print(line)
    print("-- replies: every (size, request) across the arms")
    for size in sizes:
        for rep in sorted({r["rep"] for r in rs if r["target_tokens"] == size}):
            got = {r["tag"]: r["token_sha"] for r in rs if r["target_tokens"] == size and r["rep"] == rep}
            ref = got.get("rs1") or next(iter(got.values()))
            odd = sorted(t for t, s in got.items() if s != ref)
            print(f"{size // 1000}k request {rep}: {len(got)} arms, {len(set(got.values()))} digest(s)" + (f"; differ from rs1: {odd}" if odd else ""))


def chain_of(arm):
    for d in DIRS:
        c = [r for r in jl(f"{d}/{arm}/chain.jsonl") if r["tag"] == "c74"]
        if c:
            return c
    return None


def secChain():
    arms = [a for a in (*NO_STARTS, *CONTROLS, *WARM, *[x for p in PAIRS.values() for x in p]) if chain_of(a)]
    if not arms:
        return
    tab = {a: chain_of(a) for a in arms}
    print("== growing conversations (salt c74, the same prompts in every arm), first token ms by turn")
    for a, c in tab.items():
        print(f"{a}: first turn {c[0]['ttft_ms']} ms ({c[0]['prompt_tokens']} tokens); turns 2+: {' '.join(str(x['ttft_ms']) for x in c[1:])}"
              f" | mean {st.mean(x['ttft_ms'] for x in c[1:]):.0f} ms")
    n = min(len(c) for c in tab.values())
    for t in range(n):
        got = {a: c[t]["token_sha"] for a, c in tab.items()}
        pt = {a: c[t]["prompt_tokens"] for a, c in tab.items()}
        print(f"turn {t + 1}: {len(set(got.values()))} reply digest(s) over {len(got)} arms, {len(set(pt.values()))} prompt length(s)"
              + ("" if len(set(got.values())) == 1 else f" {got}"))
    ctl = [tab[a] for a in CONTROLS if a in tab]
    if not ctl:
        return
    first = st.mean(c[0]["ttft_ms"] for c in ctl)
    warm = st.mean(st.mean(x["ttft_ms"] for x in c[1:]) for c in ctl)
    print(f"-- against the controls ({len(ctl)} boots: first turn {first:.0f} ms, turns 2+ mean {warm:.0f} ms)")
    for a, c in tab.items():
        if a in CONTROLS:
            continue
        print(f"{a}: first turn {pct(c[0]['ttft_ms'], first)}, turns 2+ {pct(st.mean(x['ttft_ms'] for x in c[1:]), warm)}")


def cell(arm, kind, n):
    for d in DIRS:
        r = jl(f"{d}/dec-{arm}/{kind}{n}.jsonl")
        if r:
            return {"agg": st.mean(x["agg_tok_s"] for x in r), "sha": tuple(sorted({tuple(x["sha"]) for x in r}))}
    return None


def secDec():
    arms = [a for a in (*WARM, *[x for p in PAIRS.values() for x in p]) if cell(a, "P", 1)]
    if not arms:
        return
    print("== greedy decode at 1 / 2 / 4 clients (--parallel 4, context 1,048,576): each boot against the controls' mean (rs1 rs2 rs3 rs4)")
    for kind, label in (("P", "prose"), ("C", "code")):
        for n in (1, 2, 4):
            ctl = {a: cell(a, kind, n) for a in CONTROLS}
            ctl = {a: c for a, c in ctl.items() if c}
            if not ctl:
                continue
            m = st.mean(c["agg"] for c in ctl.values())
            shas = {c["sha"] for c in ctl.values()}
            line = (f"{label} {n}: controls " + " ".join(f"{a} {c['agg']:.2f}" for a, c in ctl.items())
                    + f" (spread {max(c['agg'] for c in ctl.values()) / min(c['agg'] for c in ctl.values()) - 1:.2%});")
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


if __name__ == "__main__":
    secE()
    secCold()
    secChain()
    secDec()
