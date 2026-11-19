#!/usr/bin/env python3
"""score71.py [ROWS_DIR] - queue71's runs.

A: cold first token at 8k / 32k / 120k, two requests a boot, one seed on every boot; boots rec1 ps1 psx1 pipe1 solo1 psx2 ps2 rec2:
   each arm's mean against the recipe's, and the reply digest of every (size, request) across all eight boots (one seed: equal is exact).
B: decode at depth (longdec_ids.json through per_prompt.py, 2 reps) and the greedy ids at 1 / 2 / 4; boots rec1 all1 split1 win1 win2
   split2 all2 rec2. Decode at depth = tokens / span (first to last chunk) per prompt and rep; replies compared by sha12 across arms.
C: the draft rule, greedy and sampled ids at 1 / 2 / 4; boots rec1 marg1 noise1 noise2 marg2 rec2.
Production: its longdec and sampled cells beside the recipe's.
"""
import json
import os
import statistics as st
import sys

D = sys.argv[1] if len(sys.argv) > 1 else "docs/audit-2026-11-12/queue-rows/queue71"


def rows(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


def cell(path):
    rs = rows(path)
    if not rs:
        return None
    return {"agg": st.mean(r["agg_tok_s"] for r in rs), "rounds": sum((r.get("draft_rounds") or 0) for r in rs),
            "sha": tuple(sorted({tuple(r["sha"]) for r in rs}))}


def pct(a, b):
    return f"{a / b - 1:+.2%}"


def part_a():
    arms = {"rec": ("rec1", "rec2"), "pipe": ("pipe1",), "solo": ("solo1",), "ps": ("ps1", "ps2"), "psx": ("psx1", "psx2")}
    cold = [r for r in rows(f"{D}/pf71/rows.jsonl") if r.get("case") == "cold"]
    boots = [r for r in rows(f"{D}/pf71/rows.jsonl") if r.get("case") == "boot"]
    print("== A boots: " + ", ".join(f"{b['tag']} rc {b.get('boot_rc')} up {b.get('up_s')} s" for b in boots))
    print("== A cold first token, ms (each boot: the mean of its two requests)")
    for size in sorted({r["target_tokens"] for r in cold}):
        by = {a: [st.mean([r["ttft_ms"] for r in cold if r["tag"] == b and r["target_tokens"] == size] or [float("nan")]) for b in bs]
              for a, bs in arms.items()}
        rec = st.mean(by["rec"])
        print(f"{size // 1000}k: " + " | ".join(f"{a} {' '.join(f'{x:.0f}' for x in v)}" + ("" if a == "rec" else f" = {pct(st.mean(v), rec)}")
                                                for a, v in by.items()))
    print("== A replies: every (size, request) across the eight boots")
    for size in sorted({r["target_tokens"] for r in cold}):
        for rep in sorted({r["rep"] for r in cold}):
            got = {r["tag"]: r["token_sha"] for r in cold if r["target_tokens"] == size and r["rep"] == rep}
            ref = got.get("rec1")
            odd = sorted(t for t, s in got.items() if s != ref)
            print(f"{size // 1000}k request {rep}: {len(got)} boots, {len(set(got.values()))} digest(s)" + (f"; differ from rec1: {odd}" if odd else ""))


def ld(label):
    out = {}
    for r in rows(f"{D}/ld71-{label}/pp.jsonl"):
        out[(r["name"], r["rep"])] = r
    return out


def part_b():
    arms = {"rec": ("rec1", "rec2"), "all": ("all1", "all2"), "split": ("split1", "split2"), "win": ("win1", "win2")}
    data = {b: ld(b) for bs in arms.values() for b in bs}
    prod = ld("prod")
    keys = sorted(set().union(*[set(v) for v in data.values()]))
    print("== B decode at depth, tok/s (tokens / first-to-last-chunk span), each arm's two boots")
    for k in keys:
        line = f"{k[0]} rep {k[1]}:"
        rec = None
        for a, bs in arms.items():
            v = [data[b][k]["tokens"] / data[b][k]["span_s"] for b in bs if k in data[b]]
            if not v:
                continue
            m = st.mean(v)
            rec = m if a == "rec" else rec
            line += f" {a} {' '.join(f'{x:.1f}' for x in v)}" + ("" if a == "rec" or rec is None else f" ({pct(m, rec)})") + ";"
        if k in prod:
            p = prod[k]["tokens"] / prod[k]["span_s"]
            line += f" production {p:.1f}" + (f" (recipe/production {rec / p:.3f})" if rec else "")
        shas = {data[b][k]["sha12"] for bs in arms.values() for b in bs if k in data[b]}
        line += f" | replies {len(shas)} digest(s)"
        print(line)
    print("== B first token at depth, s (rep 0: the prompt's first sight on that boot)")
    for k in keys:
        if k[1] != 0:
            continue
        v = {b: data[b][k]["ttft_s"] for bs in arms.values() for b in bs if k in data[b]}
        print(f"{k[0]}: " + " ".join(f"{b} {x:.1f}" for b, x in v.items()) + (f" | production {prod[k]['ttft_s']:.1f}" if k in prod else ""))
    for kind, label in (("P", "prose"), ("C", "code")):
        print(f"== B greedy {label} at 1 / 2 / 4 clients")
        for n in (1, 2, 4):
            c = {b: cell(f"{D}/ld71-{b}/{kind}{n}.jsonl") for bs in arms.values() for b in bs}
            if not any(c[b] for b in arms["rec"]):
                continue
            rec = st.mean(c[b]["agg"] for b in arms["rec"] if c[b])
            line = f"{n}:"
            for a, bs in arms.items():
                v = [c[b]["agg"] for b in bs if c[b]]
                if v:
                    line += f" {a} {' '.join(f'{x:.2f}' for x in v)}" + ("" if a == "rec" else f" ({pct(st.mean(v), rec)})") + ";"
            line += f" rounds {sorted({c[b]['rounds'] for b in c if c[b]})} replies {len({c[b]['sha'] for b in c if c[b]})} set(s)"
            print(line)


def part_c():
    arms = {"rec": ("rec1", "rec2"), "marg": ("marg1", "marg2"), "noise": ("noise1", "noise2")}
    for kind, label in (("P", "greedy prose"), ("C", "greedy code"), ("SP", "sampled prose"), ("SC", "sampled code")):
        print(f"== C {label} at 1 / 2 / 4 clients")
        for n in (1, 2, 4):
            c = {b: cell(f"{D}/dr71-{b}/{kind}{n}.jsonl") for bs in arms.values() for b in bs}
            if not c["rec1"]:
                continue
            rec = st.mean(c[b]["agg"] for b in arms["rec"] if c[b])
            line = f"{n}:"
            for a, bs in arms.items():
                v = [c[b]["agg"] for b in bs if c[b]]
                line += f" {a} {' '.join(f'{x:.2f}' for x in v)}" + ("" if a == "rec" else f" ({pct(st.mean(v), rec)})")
                line += f" r{sorted({c[b]['rounds'] for b in bs if c[b]})};"
            line += f" replies {len({c[b]['sha'] for b in c if c[b]})} set(s)"
            if kind.startswith("S"):
                p = cell(f"{D}/s71-prod/{kind}{n}.jsonl")
                if p:
                    line += f" | production {p['agg']:.2f} (recipe/production {rec / p['agg']:.3f})"
            print(line)


if __name__ == "__main__":
    part_a()
    part_b()
    part_c()
