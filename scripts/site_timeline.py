#!/usr/bin/env python3
"""site_timeline.py SQLITE PASS LAYER [--site mixer|ffn] - one layer's kernels on the main and the side stream, in time order, from an Nsight Systems
export of the GLM Zig serve (read-only; stdlib only; the loader is prefill_stages.py's).

A pass is a run of kernels between two tf_glm_put_words; layer boundaries are the main stream's hc glue runs (tf_glm_hc_post then hc_pre, two a layer).
The listing prints, for the chosen pass and layer, every kernel with its start (us from the layer's first kernel), duration, stream (M main, S side) and name,
then the main stream's idle gaps. It is the picture behind prefill_stages.py's wait rows: which side-stream kernel the main stream waits for, and how much of the
side stream's chain (partials exchange, glue, share) hides under the main stream's fills.
"""
import argparse
import collections
import sys

import prefill_stages as ps


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("sqlite")
    ap.add_argument("pass_index", type=int, help="index of the put_words-delimited pass (0 is the first)")
    ap.add_argument("layer", type=int)
    ap.add_argument("--max-rows", type=int, default=400)
    a = ap.parse_args()
    ks, copies, _ = ps.load(a.sqlite)
    puts = collections.Counter(k[2] for k in ks if k[3] == "tf_glm_put_words")
    if not puts:
        print("no put_words kernel: not a GLM serve capture")
        return 1
    main_id = puts.most_common(1)[0][0]
    mk = [k for k in ks if k[2] == main_id]
    starts = [i for i, k in enumerate(mk) if k[3] == "tf_glm_put_words"]
    if a.pass_index >= len(starts):
        print(f"only {len(starts)} passes")
        return 1
    lo_i = starts[a.pass_index]
    hi_i = starts[a.pass_index + 1] if a.pass_index + 1 < len(starts) else len(mk)
    seg = mk[lo_i:hi_i]
    posts = [i for i, k in enumerate(seg) if k[3] == "tf_glm_hc_post"]
    print(f"pass {a.pass_index}: {len(seg)} main-stream kernels, {len(posts)} hc_post launches")
    # a layer's two glue runs: pieces of hc_post per site; the site boundaries are the gaps between runs of hc_post launches
    runs, cur = [], [posts[0]] if posts else []
    for i in posts[1:]:
        if i - cur[-1] > 40:
            runs.append(cur)
            cur = [i]
        else:
            cur.append(i)
    if cur:
        runs.append(cur)
    print(f"{len(runs)} glue runs (two a layer)")
    site = 2 * a.layer
    if site + 1 >= len(runs):
        print("layer out of range")
        return 1
    start_i = runs[site - 1][-1] + 1 if site > 0 else 0
    end_i = runs[site + 1][-1] + 1
    t0 = seg[start_i][0]
    t1 = max(k[1] for k in seg[start_i:end_i])
    rows = [("M", k) for k in seg[start_i:end_i]]
    rows += [("S", k) for k in ks if k[2] != main_id and k[0] < t1 and k[1] > t0 and ps.category(k[3]) == "nccl"]
    rows.sort(key=lambda r: r[1][0])
    print(f"layer {a.layer}: {(t1 - t0) / 1e6:.2f} ms, {len(rows)} kernels (M main, S side-stream NCCL)")
    for who, k in rows[: a.max_rows]:
        print(f"{(k[0] - t0) / 1e3:10.1f} us {(k[1] - k[0]) / 1e3:9.1f} us {who} {k[3][:70]}")
    idle = []
    last = seg[start_i][1]
    for k in seg[start_i + 1:end_i]:
        if k[0] - last > 20_000:
            idle.append(((last - t0) / 1e3, (k[0] - last) / 1e3, k[3][:50]))
        last = max(last, k[1])
    print("main-stream idle gaps over 20 us (start us, length us, next kernel):")
    for g in idle:
        print(f"{g[0]:10.1f} {g[1]:9.1f} {g[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
