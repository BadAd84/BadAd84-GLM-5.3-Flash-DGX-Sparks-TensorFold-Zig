#!/usr/bin/env python3
"""prefill_gaps.py CAPTURE.sqlite [REQUEST] - where the main stream idles in a prompt pass, by the kernels on either side of each gap.

Reads an Nsight Systems database of rank 0 (scripts/nsys-prefill.sh) with scripts/prefill_stages.py's loader and pass finder. REQUEST is the 1-based request whose full-size passes
are read (default 2: the 32k prompt, whose passes after the first are warmed 4,096-row passes). For every pass of exactly 4,096 rows but its first, the main stream's gaps over 2 us are
summed by (kernel before, kernel after); the table is the mean over those passes, in ms a pass, with the number and mean length of the gaps.
A gap is time the stream's own kernels leave empty: it says where the stream waits, not what it waits for (the side stream's kernels are in prefill_stages.py's table).
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefill_stages as ps  # noqa: E402

GAP_NS = 2000
FULL_ROWS = 4096


def gaps(path, request=2):
    """(passes read, {(before, after): [total ns a pass, gaps a pass]}) for the full-size passes of a request after its first pass."""
    ks, _, _ = ps.load(path)
    res = ps.analyse(path)
    main = [k for k in ks if k[2] == res["main_stream"]]
    reqs = res["requests"]
    if request > len(reqs):
        raise SystemExit(f"{path}: {len(reqs)} requests, no request {request}")
    sel = [p for p in reqs[request - 1][1:] if p["rows"] == FULL_ROWS]
    if not sel:
        raise SystemExit(f"{path}: request {request} has no pass of {FULL_ROWS} rows after its first")
    total, count = collections.Counter(), collections.Counter()
    for p in sel:
        inside = [k for k in main if p["t0"] <= k[0] <= p["t1"]]
        for a, b in zip(inside, inside[1:]):
            if b[0] - a[1] > GAP_NS:
                key = (a[3][:34], b[3][:34])
                total[key] += b[0] - a[1]
                count[key] += 1
    n = len(sel)
    return n, {key: [total[key] / n, count[key] / n] for key in total}


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    request = int(argv[1]) if len(argv) > 1 else 2
    n, table = gaps(argv[0], request)
    whole = sum(v[0] for v in table.values())
    print(f"{n} warmed {FULL_ROWS}-row passes of request {request}; main-stream gaps over {GAP_NS // 1000} us: {whole / 1e6:.1f} ms a pass")
    print(f"{'ms a pass':>10} {'gaps':>7} {'mean us':>8}  kernel before -> kernel after")
    for key, (ns, c) in sorted(table.items(), key=lambda kv: -kv[1][0])[:14]:
        print(f"{ns / 1e6:10.2f} {c:7.1f} {ns / c / 1e3:8.1f}  {key[0]} -> {key[1]}")


if __name__ == "__main__":
    main(sys.argv[1:])
