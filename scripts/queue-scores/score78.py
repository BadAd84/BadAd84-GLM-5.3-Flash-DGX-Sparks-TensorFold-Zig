#!/usr/bin/env python3
"""score78.py [ROWS_DIR] - queue78, the screen of the registered prompt-side switches on top of the final recipe (scripts/queues/queue78.sh).

Boots C0 .. C3 are the final recipe alone (the controls: first, last and after every third screen); every other boot is the recipe plus one switch, labelled
"<n>-<name>". Cold first token at 8k / 32k / 120k (two requests a boot, one seed on every boot) and the growing conversation (salt c74) are read against the
controls' mean, with the controls' own spread beside them; every reply digest must be the same across all boots. A screen below the controls' fastest boot at
two of the three sizes is a lead for a second boot (and a decode screen where the switch can touch decode).
"""
import json
import os
import statistics as st
import sys

D = sys.argv[1] if len(sys.argv) > 1 else "docs/audit-2026-11-12/queue-rows/queue78"
F = f"{D}/f78-c"


def rows(p):
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


def pct(a, b):
    return f"{a / b - 1:+.2%}"


cold = [r for r in rows(f"{F}/rows.jsonl") if r.get("case") == "cold"]
tags = list(dict.fromkeys(r["tag"] for r in cold))
ctl = [t for t in tags if t.startswith("C") and t[1:].isdigit()]
scr = [t for t in tags if t not in ctl]
sizes = sorted({r["target_tokens"] for r in cold})


def ms(tag, size):
    v = [r["ttft_ms"] for r in cold if r["tag"] == tag and r["target_tokens"] == size]
    return st.mean(v) if v else None


def chain(tag):
    c = [r for r in rows(f"{F}/{tag}/chain.jsonl") if r["tag"] == "c74"]
    return c or None


print(f"controls: {ctl}")
for s in sizes:
    xs = [ms(t, s) for t in ctl if ms(t, s) is not None]
    if len(xs) > 1:
        print(f"  controls {s // 1000}k: {' '.join(f'{x:.0f}' for x in xs)} (mean {st.mean(xs):.0f}, spread {max(xs) / min(xs) - 1:.2%})")
cc = [chain(t) for t in ctl if chain(t)]
if cc:
    f0 = st.mean(c[0]["ttft_ms"] for c in cc)
    w0 = st.mean(st.mean(x["ttft_ms"] for x in c[1:]) for c in cc)
    print(f"  controls chain: first turn {f0:.0f} ms, turns 2 to 8 {w0:.0f} ms")
print("screen | cold 8k / 32k / 120k against the controls' mean | boots below the controls' fastest | chain first turn / turns 2+")
for t in scr:
    line, wins = [], 0
    for s in sizes:
        xs = [ms(c, s) for c in ctl if ms(c, s) is not None]
        x = ms(t, s)
        if not xs or x is None:
            line.append("-")
            continue
        line.append(pct(x, st.mean(xs)))
        wins += x < min(xs)
    ch = chain(t)
    chs = f"{pct(ch[0]['ttft_ms'], f0)} / {pct(st.mean(x['ttft_ms'] for x in ch[1:]), w0)}" if ch and cc else "-"
    print(f"{t} | {' / '.join(line)} | {wins} of {len(sizes)} sizes | {chs}")
print("replies: every (size, request) across all boots")
for s in sizes:
    for rep in sorted({r["rep"] for r in cold if r["target_tokens"] == s}):
        got = {r["tag"]: r["token_sha"] for r in cold if r["target_tokens"] == s and r["rep"] == rep}
        print(f"  {s // 1000}k request {rep}: {len(got)} boots, {len(set(got.values()))} digest(s)")
allc = {t: chain(t) for t in tags if chain(t)}
for k in range(min((len(c) for c in allc.values()), default=0)):
    print(f"  chain turn {k + 1}: {len({c[k]['token_sha'] for c in allc.values()})} reply digest(s) over {len(allc)} boots")
