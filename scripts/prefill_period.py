#!/usr/bin/env python3
"""prefill_period.py CAPTURE.sqlite PASS N [REQUEST] - one layer period of a warmed prompt pass, every kernel on both streams in time order.

Reads an Nsight Systems database of rank 0 (scripts/nsys-prefill.sh) with scripts/prefill_stages.py's loader and pass finder. REQUEST is the 1-based request whose full-size
passes are read (default 2: the 32k prompt); PASS is the 0-based index among its 4,096-row passes after the first. A period runs from the end of the N-th routed-experts down
kernel (tf_exl3_prompt_down) of that pass to the end of the next, so it holds one MoE layer's tail, the next layer's mixer and the next router and experts. Each line is
the kernel's start in us from the period's start, its duration in us, M (main stream) or S (the NCCL side stream, which carries the glue kernels once a schedule moves
them there) and its name. It works where prefill_stages.py's layer cut does not (a pass whose ffn glue runs on the side stream).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefill_stages as ps  # noqa: E402


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    path, which, nth = argv[0], int(argv[1]), int(argv[2])
    request = int(argv[3]) if len(argv) > 3 else 2
    ks, _, _ = ps.load(path)
    res = ps.analyse(path)
    main_id, side = res["main_stream"], set(res["side_streams"])
    full = [p for p in res["requests"][request - 1][1:] if p["rows"] == 4096]
    if which >= len(full):
        raise SystemExit(f"{path}: request {request} has {len(full)} full-size passes after its first, no pass {which}")
    p = full[which]
    down = [k for k in ks if k[2] == main_id and k[3] == "tf_exl3_prompt_down" and p["t0"] <= k[0] <= p["t1"]]
    if nth + 1 >= len(down):
        raise SystemExit(f"{path}: the pass has {len(down)} experts down kernels, no period {nth}")
    t0, t1 = down[nth][1], down[nth + 1][1]
    print(f"one layer period: from the end of down #{nth} to the end of down #{nth + 1}: {(t1 - t0) / 1e3:.0f} us")
    for k in sorted(k for k in ks if (k[2] == main_id or k[2] in side) and t0 <= k[0] < t1):
        print(f"{(k[0] - t0) / 1e3:9.1f} {(k[1] - k[0]) / 1e3:8.1f} {'M' if k[2] == main_id else 'S'}  {k[3][:60]}")


if __name__ == "__main__":
    main(sys.argv[1:])
