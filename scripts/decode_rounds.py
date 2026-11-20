#!/usr/bin/env python3
"""decode_rounds.py SQLITE [--top N] [--min-kernels K] [--min-wall MS] [--range LO-HI] [--json OUT] - rank 0's decode rounds, round by round, from an Nsight Systems export of the
GLM Zig serve (read-only on the export; stdlib only; the categories and the loader are prefill_stages.py's).

The main stream is the one carrying tf_glm_put_words, which starts every lane step. A decode round is one lane step (from a put_words to the next one
on the main stream) whose kernels hold no EXL3 prompt experts and at least --min-kernels kernels (a step that only gates or syncs is not a round).
Per round: wall time (first kernel start to the last kernel end), the main stream's busy time (the union of its kernels, copies and memsets), the
idle, the time in each kernel category, and the NCCL time of every other stream. The tables give the mean over rounds of the same shape (the same
number of main-stream kernels, which separates a 1-stream window from a 4-stream one), the ranked kernels a round, and the idle gaps named by the
kernel that follows them.
"""
import argparse
import collections
import json
import statistics as st
import sys

import prefill_stages as ps


def rounds(ks, copies):
    """[(lo, hi, kernels of the main stream, other streams' kernels)] for every decode round."""
    puts = collections.Counter(k[2] for k in ks if k[3] == "tf_glm_put_words")
    if not puts:
        return []
    main_id = puts.most_common(1)[0][0]
    main = [k for k in ks if k[2] == main_id]
    others = [k for k in ks if k[2] != main_id]
    idx = [i for i, k in enumerate(main) if k[3] == "tf_glm_put_words"]
    out = []
    for n, i in enumerate(idx):
        j = idx[n + 1] if n + 1 < len(idx) else len(main)
        seg = main[i:j]
        if any(k[3] in ps.EXPERTS for k in seg):
            continue
        lo, hi = seg[0][0], max(k[1] for k in seg)
        out.append((lo, hi, seg, [k for k in others if k[0] < hi and k[1] > lo and ps.category(k[3]) == "nccl"]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("sqlite")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--min-kernels", type=int, default=200)
    ap.add_argument("--min-wall", type=float, default=0.0, help="drop rounds shorter than this many ms (20 keeps the verify windows and drops the drafter passes)")
    ap.add_argument("--json")
    ap.add_argument("--range", help="LO-HI: one detail block over every round whose rows lie in LO..HI (instead of the four commonest row counts)")
    a = ap.parse_args()
    ks, copies, _ = ps.load(a.sqlite)
    rs = [r for r in rounds(ks, copies) if len(r[2]) >= a.min_kernels and (r[1] - r[0]) / 1e6 >= a.min_wall]
    if not rs:
        print("no decode rounds")
        return 1
    shapes = collections.defaultdict(list)
    for r in rs:
        shapes[next((k[4] for k in r[2] if k[3] == "tf_glm_embed_b16"), 0)].append(r)
    print(f"{len(rs)} decode rounds; rows a round (the embed kernel's grid): rounds")
    print("  " + ", ".join(f"{n}: {len(v)}" for n, v in sorted(shapes.items(), key=lambda kv: -len(kv[1]))[:16]))
    print("rows | rounds | wall ms | busy ms | idle ms | ms a row")
    for n, group in sorted(shapes.items()):
        if len(group) < 3:
            continue
        w = st.mean((r[1] - r[0]) / 1e6 for r in group)
        b = st.mean(ps.union_len([(k[0], k[1]) for k in r[2]]) / 1e6 for r in group)
        print(f"{n:4d} | {len(group):6d} | {w:7.2f} | {b:7.2f} | {w - b:7.2f} | {w / max(n, 1):7.2f}")
    out = {}
    pick = sorted(shapes.items(), key=lambda kv: -len(kv[1]))[:4]
    if a.range:
        lo_r, hi_r = (int(x) for x in a.range.split("-"))
        every = [r for n, g in shapes.items() if lo_r <= n <= hi_r for r in g]
        pick = [(f"{lo_r} to {hi_r}", every)] if every else []
    for n, group in pick:
        if len(group) < 3:
            continue
        wall, busy, side = [], [], []
        cats = collections.defaultdict(list)
        kern = collections.defaultdict(float)
        gaps = collections.defaultdict(float)
        for lo, hi, seg, nc in group:
            iv = [(k[0], k[1]) for k in seg]
            b = ps.union_len(iv)
            wall.append((hi - lo) / 1e6)
            busy.append(b / 1e6)
            side.append(sum(k[1] - k[0] for k in nc) / 1e6)
            c = collections.defaultdict(float)
            for k in seg:
                c[ps.category(k[3])] += (k[1] - k[0]) / 1e6
                kern[k[3]] += (k[1] - k[0]) / 1e6
            for cat, v in c.items():
                cats[cat].append(v)
            m = ps.merged(iv)
            for (s0, e0), (s1, _) in zip(m, m[1:]):
                nxt = next((k[3] for k in seg if k[0] >= s1), "?")
                gaps[nxt] += (s1 - e0) / 1e6
        R = len(group)
        print(f"\n== rounds of {n} rows: {R} rounds, wall {st.mean(wall):.2f} ms (min {min(wall):.2f}, max {max(wall):.2f}), busy {st.mean(busy):.2f} ms "
              f"({st.mean(busy) / st.mean(wall):.1%}), idle {st.mean(wall) - st.mean(busy):.2f} ms, side-stream NCCL {st.mean(side):.2f} ms")
        print("category ms a round: " + ", ".join(f"{c} {sum(v) / R:.2f}" for c, v in sorted(cats.items(), key=lambda kv: -sum(kv[1]))))
        print("ranked kernels, ms a round (launches a round):")
        cnt = collections.Counter(k[3] for _, _, seg, _ in group for k in seg)
        for name, v in sorted(kern.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {v / R:8.3f} ms  x{cnt[name] / R:6.1f}  {name[:100]}")
        print("idle ms a round by the kernel that follows the gap:")
        for name, v in sorted(gaps.items(), key=lambda kv: -kv[1])[:10]:
            print(f"  {v / R:8.3f} ms  {name[:100]}")
        out[n] = {"rounds": R, "wall_ms": st.mean(wall), "busy_ms": st.mean(busy), "categories": {c: sum(v) / R for c, v in cats.items()}}
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
