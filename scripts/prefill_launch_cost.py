#!/usr/bin/env python3
"""prefill_launch_cost.py CAPTURE.sqlite [COLD_REQUEST [WARM_REQUEST]] - what a kernel launch costs whatever its rows, from one capture's cold passes and one warm turn.

Reads an Nsight Systems database of rank 0 (scripts/nsys-prefill.sh) with scripts/prefill_stages.py's loader and pass finder. COLD_REQUEST (default 2: the 32k prompt) gives the
warmed 4,096-row passes (every full pass but its first); WARM_REQUEST (default 4: the second warm turn of the growing conversation) gives one pass of about 1,300 rows. Both run the
same number of row pieces, so a kernel launched once a piece sees about 1,024 rows in the cold pass and a quarter of the warm pass's rows in the warm one. For each kernel name the
table has its launches and mean time a launch in both, and the two-point line through them: the time a row and the fixed time a launch (what a launch costs at zero rows).
It is crude on purpose: one name serves several matrices and the mix of launches differs between the two passes, so the fixed cost is an estimate of size, not a measurement.
The side stream's NCCL SendRecv kernels are the last line.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefill_stages as ps  # noqa: E402

FULL_ROWS = 4096


def launches(ks, streams, p):
    """{name: [total ns, launches]} of the kernels of `streams` inside pass `p`."""
    out = collections.defaultdict(lambda: [0, 0])
    for k in ks:
        if k[2] in streams and p["t0"] <= k[0] <= p["t1"]:
            name = "ncclDevKernel_SendRecv" if k[3].startswith("ncclDevKernel_SendRecv") else k[3][:34]
            out[name][0] += k[1] - k[0]
            out[name][1] += 1
    return out


def line(cold_us, cold_rows, warm_us, warm_rows):
    """(us a row, fixed us a launch) of the line through the two points."""
    slope = (cold_us - warm_us) / (cold_rows - warm_rows)
    return slope, warm_us - slope * warm_rows


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    cold_request = int(argv[1]) if len(argv) > 1 else 2
    warm_request = int(argv[2]) if len(argv) > 2 else 4
    ks, _, _ = ps.load(argv[0])
    res = ps.analyse(argv[0])
    main_id, side = {res["main_stream"]}, set(res["side_streams"])
    cold = [p for p in res["requests"][cold_request - 1][1:] if p["rows"] == FULL_ROWS]
    warm = max(res["requests"][warm_request - 1], key=lambda p: p["rows"])
    if not cold:
        raise SystemExit(f"{argv[0]}: request {cold_request} has no pass of {FULL_ROWS} rows after its first")
    exchanges = launches(ks, side, warm).get("ncclDevKernel_SendRecv", [0, 0])[1]
    pieces = exchanges // 180 or 4  # 45 layers, two sites a layer, an exchange and a share a piece: 180 launches a piece
    cold_rows, warm_rows = FULL_ROWS / pieces, warm["rows"] / pieces
    print(f"cold: {len(cold)} warmed {FULL_ROWS}-row passes of request {cold_request}; warm: the {warm['rows']}-row pass of request {warm_request}; {pieces} row pieces, so {cold_rows:.0f} and {warm_rows:.0f} rows a piece")
    print(f"{'kernel':36s} {'cold n':>7} {'us each':>8} {'warm n':>7} {'us each':>8} {'us a row':>9} {'fixed us':>9} {'fixed ms a warm pass':>21}")
    for streams, names in ((main_id, None), (side, ("ncclDevKernel_SendRecv",))):
        c = collections.defaultdict(lambda: [0, 0])
        for p in cold:
            for name, (ns, n) in launches(ks, streams, p).items():
                c[name][0] += ns
                c[name][1] += n
        w = launches(ks, streams, warm)
        rows = sorted((name for name in w if name in c and (names is None or name in names)), key=lambda name: -w[name][0])
        for name in rows[:12] if names is None else rows:
            cold_us, warm_us = c[name][0] / c[name][1] / 1e3, w[name][0] / w[name][1] / 1e3
            slope, fixed = line(cold_us, cold_rows, warm_us, warm_rows)
            print(f"{name:36s} {c[name][1] / len(cold):7.0f} {cold_us:8.1f} {w[name][1]:7d} {warm_us:8.1f} {slope:9.3f} {fixed:9.1f} {fixed * w[name][1] / 1e3:21.1f}")


if __name__ == "__main__":
    main(sys.argv[1:])
