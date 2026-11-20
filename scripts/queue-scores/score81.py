#!/usr/bin/env python3
"""score81.py [ROWS_DIR] - queue81, the NCCL and wire screen: arms mb (TF_TP_MAILBOX_MAX_KB=1024, the decode wire's ceiling), q4 n8 ch bf qn n2 (one NCCL setting each) on the final
recipe with request starts, between controls c1 c2 c3.

Per arm: the cold first token at 8k / 32k / 120k (the mean of two requests on one seed), the growing conversation's first turn and turns 2 to 8, and greedy decode at
1 and 4 clients (prose and code, aggregate tok/s; the controls c1 and c3 and the arm mb also at 2, 6 and 8); each against the mean of the three controls, with the controls' own spread. Replies: every cold request, every conversation
turn and every decode cell must be one digest across all arms (NCCL moves bytes, it never changes a sum). One boot an arm is a screen: a setting is read only against the
spread of the controls, and a gain larger than that goes to a pair of boots.
"""
import json
import os
import statistics as st
import sys

D = sys.argv[1] if len(sys.argv) > 1 else "docs/audit-2026-11-12/queue-rows/queue81/f81-c"
ARMS = ("c1", "mb", "q4", "n8", "ch", "c2", "bf", "qn", "n2", "c3")
CTL = ("c1", "c2", "c3")
CELLS = tuple((k, n) for n in (1, 2, 4, 6, 8) for k in ("P", "C"))


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


rows = [r for r in jl(f"{D}/rows.jsonl") if r.get("case") == "cold"]
sizes = sorted({r["target_tokens"] for r in rows})


def cold(a, s):
    v = [r["ttft_ms"] for r in rows if r["tag"] == a and r["target_tokens"] == s]
    return st.mean(v) if v else None


def chain(a):
    return [r for r in jl(f"{D}/{a}/chain.jsonl") if r.get("tag") == "c74"]


def dec(a, kind, n):
    r = jl(f"{D}/dec-{a}/{kind}{n}.jsonl")
    return (st.mean(x["agg_tok_s"] for x in r), tuple(sorted({tuple(x["sha"]) for x in r}))) if r else None


def pct(x, ref):
    return f"{x / ref - 1:+.2%}"


have = [a for a in ARMS if any(r["tag"] == a for r in rows)]
print("arms with rows:", " ".join(have))
print("== cold first token ms (mean of two requests), % against the mean of the controls (spread of the controls in brackets)")
for s in sizes:
    ctl = [cold(a, s) for a in CTL if cold(a, s)]
    if not ctl:
        continue
    ref = st.mean(ctl)
    line = f"{s // 1000}k: controls {' '.join(f'{x:.0f}' for x in ctl)} (spread {max(ctl) / min(ctl) - 1:.2%}, mean {ref:.0f})"
    for a in have:
        if a not in CTL and cold(a, s):
            line += f"; {a} {cold(a, s):.0f} ({pct(cold(a, s), ref)})"
    print(line)
print("== growing conversation: first turn ms and turns 2 to 8 mean ms")
cc = {a: chain(a) for a in have if chain(a)}
for a, c in cc.items():
    print(f"{a}: first {c[0]['ttft_ms']} | turns 2+ {st.mean(x['ttft_ms'] for x in c[1:]):.0f}")
ctl_c = [cc[a] for a in CTL if a in cc]
if ctl_c:
    f0, w0 = st.mean(c[0]["ttft_ms"] for c in ctl_c), st.mean(st.mean(x["ttft_ms"] for x in c[1:]) for c in ctl_c)
    for a, c in cc.items():
        if a not in CTL:
            print(f"{a} against the controls: first turn {pct(c[0]['ttft_ms'], f0)}, turns 2+ {pct(st.mean(x['ttft_ms'] for x in c[1:]), w0)}")
print("== greedy decode, aggregate tok/s, % against the controls' mean (controls' spread)")
for kind, n in CELLS:
    vals = {a: dec(a, kind, n) for a in have}
    ctl = [vals[a][0] for a in CTL if vals.get(a)]
    if not ctl:
        continue
    ref = st.mean(ctl)
    line = f"{kind}{n}: controls {' '.join(f'{x:.2f}' for x in ctl)} (spread {max(ctl) / min(ctl) - 1:.2%})"
    for a in have:
        if a not in CTL and vals.get(a):
            line += f"; {a} {vals[a][0]:.2f} ({pct(vals[a][0], ref)})"
    print(line)
print("== replies")
for s in sizes:
    for rep in sorted({r["rep"] for r in rows if r["target_tokens"] == s}):
        got = {r["tag"]: r["token_sha"] for r in rows if r["target_tokens"] == s and r["rep"] == rep}
        print(f"{s // 1000}k request {rep}: {len(got)} arms, {len(set(got.values()))} digest(s)")
n = min((len(c) for c in cc.values()), default=0)
for t in range(n):
    got = {a: c[t]["token_sha"] for a, c in cc.items()}
    print(f"turn {t + 1}: {len(got)} arms, {len(set(got.values()))} digest(s)")
for kind, k in CELLS:
    got = {a: dec(a, kind, k)[1] for a in have if dec(a, kind, k)}
    print(f"decode {kind}{k}: {len(got)} arms, {len(set(got.values()))} reply set(s)")
