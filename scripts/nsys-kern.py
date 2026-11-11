#!/usr/bin/env python3
"""nsys-kern.py CSV [TOP] - rank Nsight's cuda_gpu_kern_sum rows by total GPU time.

Prints, per kernel: share of all kernel time, total ms, launches, mean and median microseconds.
The table covers the whole trace (boot warm-up, the prompt and the decode rounds), so a decode
figure is read from launches times the median, not from the total alone.
"""
import csv
import sys


def col(row: dict, *names: str) -> str:
    for n in names:
        for k in row:
            if k.strip().lower().startswith(n):
                return row[k]
    raise KeyError(names)


def main() -> int:
    path = sys.argv[1]
    top = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("no kernel rows")
        return 1
    out = []
    for r in rows:
        out.append((float(col(r, "total time")), int(float(col(r, "instances"))), float(col(r, "avg")),
                    float(col(r, "med")), col(r, "name")))
    out.sort(reverse=True)
    total = sum(t for t, *_ in out)
    print(f"{len(out)} kernels, {total / 1e6:.1f} ms of kernel time, {sum(n for _, n, *_ in out)} launches")
    print(f"{'share':>6} {'total ms':>10} {'launches':>9} {'mean us':>9} {'med us':>8}  name")
    for t, n, avg, med, name in out[:top]:
        print(f"{100 * t / total:5.1f}% {t / 1e6:10.1f} {n:9d} {avg / 1e3:9.1f} {med / 1e3:8.1f}  {name[:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
