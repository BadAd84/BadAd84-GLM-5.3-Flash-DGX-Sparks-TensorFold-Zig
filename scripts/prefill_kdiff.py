#!/usr/bin/env python3
"""prefill_kdiff.py BEFORE.sqlite AFTER.sqlite [REQUEST] - what a schedule change did to each kernel's time in a prompt pass.

Reads two Nsight Systems databases of rank 0 (scripts/nsys-prefill.sh) with scripts/prefill_stages.py's loader and pass finder. REQUEST is the 1-based request whose full-size passes
are read (default 2: the 32k prompt, whose passes after the first are warmed 4,096-row passes). For every pass of exactly 4,096 rows but its first, each kernel name's time and launch
count on the main stream (and on the NCCL side stream's streams, which also carry the glue kernels once the schedule moves them) are averaged a pass; the table is the difference,
largest increases first, then the largest decreases. A kernel whose launches stay equal and whose time moves is running slower or faster per launch (contention, clocks), not run more often.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefill_stages as ps  # noqa: E402

FULL_ROWS = 4096


def per_kernel(path, request):
    """({name: (ms a pass, launches a pass)} on the main stream, the same on the NCCL streams) over the request's full-size passes after the first."""
    ks, _, _ = ps.load(path)
    res = ps.analyse(path)
    if request > len(res["requests"]):
        raise SystemExit(f"{path}: {len(res['requests'])} requests, no request {request}")
    sel = [p for p in res["requests"][request - 1][1:] if p["rows"] == FULL_ROWS]
    if not sel:
        raise SystemExit(f"{path}: request {request} has no pass of {FULL_ROWS} rows after its first")
    side = set(res["side_streams"])
    tot = {"main": collections.Counter(), "side": collections.Counter()}
    cnt = {"main": collections.Counter(), "side": collections.Counter()}
    for p in sel:
        for k in ks:
            if p["t0"] <= k[0] <= p["t1"]:
                which = "main" if k[2] == res["main_stream"] else ("side" if k[2] in side else None)
                if which:
                    tot[which][k[3][:40]] += k[1] - k[0]
                    cnt[which][k[3][:40]] += 1
    n = len(sel)
    return {w: {k: (v / n / 1e6, cnt[w][k] / n) for k, v in tot[w].items()} for w in tot}, n


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    request = int(argv[2]) if len(argv) > 2 else 2
    (a, na), (b, nb) = per_kernel(argv[0], request), per_kernel(argv[1], request)
    for which in ("main", "side"):
        rows = []
        for k in set(a[which]) | set(b[which]):
            ta, ca = a[which].get(k, (0.0, 0.0))
            tb, cb = b[which].get(k, (0.0, 0.0))
            rows.append((tb - ta, k, ta, tb, ca, cb))
        print(f"{which} stream, ms a pass (before {na} passes, after {nb}): total {sum(r[2] for r in rows):.1f} -> {sum(r[3] for r in rows):.1f}")
        print(f"{'change':>8} {'before':>8} {'after':>8} {'launches':>17}  kernel")
        top = sorted(rows, reverse=True)[:10]
        shown = top + [r for r in sorted(rows)[:6] if r[0] < 0 and r not in top]
        for d, k, ta, tb, ca, cb in shown:
            print(f"{d:+8.2f} {ta:8.2f} {tb:8.2f} {ca:7.1f} ->{cb:7.1f}  {k}")


if __name__ == "__main__":
    main(sys.argv[1:])
