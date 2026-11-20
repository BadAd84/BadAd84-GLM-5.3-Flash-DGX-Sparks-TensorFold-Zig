#!/usr/bin/env python3
"""prefill_passes.py CAPTURE.sqlite [passes | copies | diff A B [C ...]] - the prompt passes of an nsys capture of rank 0, one by one.

A pass is the span from one tf_glm_embed_b16 launch to the next (the embedding runs once a forward, prompt pass or decode window alike), or to the first gap of 20 ms
with no kernel. Time is in seconds from the capture's first device-to-device copy.
  passes  every forward of 10 ms or more: its start, its wall time, its kernels, and the gap to the forward before it when that is over a second (a new request).
  copies  runs of device-to-device copies of 32 MiB or more (a kept state's copy into the snapshot pages, or a restore out of them): copies, MiB, wall ms, GiB/s.
  diff    the passes numbered A, B, ... in `passes`' list, kernel by kernel: launches and summed ms in each, sorted by the first pass's time, with the main stream's
          busy and idle time. Names the rows of each pass with A:ROWS to add ms a 1,000 rows.
It needs no engine log: scripts/prefill_stages.py reads TF_GLM_PROF's stage lines, which a pass under that switch prints and which turn the solo step off.
"""
import bisect
import collections
import sqlite3
import sys

GAP_NS = 20_000_000
MIN_PASS_MS = 10.0
BIG_COPY = 32 * 2**20


def load(path):
    db = sqlite3.connect(path)
    names = dict(db.execute("select id, value from StringIds"))
    kernels = db.execute("select start, end, shortName, streamId from CUPTI_ACTIVITY_KIND_KERNEL order by start").fetchall()
    copies = db.execute("select start, end, bytes from CUPTI_ACTIVITY_KIND_MEMCPY where copyKind = 8 order by start").fetchall()
    return names, kernels, copies


def forwards(names, kernels):
    """[(start, end, first kernel index, kernel count)] of every forward: an embed launch to the next, cut at the first 20 ms gap."""
    embed = {i for i, v in names.items() if v.startswith("tf_glm_embed")}
    at = [k for k, (s, e, n, st) in enumerate(kernels) if n in embed]
    out = []
    for j, lo in enumerate(at):
        hi = at[j + 1] if j + 1 < len(at) else len(kernels)
        end, count = kernels[lo][1], 0
        for k in range(lo, hi):
            if kernels[k][0] - end > GAP_NS:
                break
            end = max(end, kernels[k][1])
            count += 1
        out.append((kernels[lo][0], end, lo, count))
    return out


def passes(names, kernels):
    return [f for f in forwards(names, kernels) if (f[1] - f[0]) / 1e6 >= MIN_PASS_MS]


def copy_runs(copies):
    """Runs of device-to-device copies less than 2 ms apart: [start, end, bytes, count]."""
    runs = []
    for s, e, b in copies:
        if runs and s - runs[-1][1] < 2_000_000:
            runs[-1][1], runs[-1][2], runs[-1][3] = e, runs[-1][2] + b, runs[-1][3] + 1
        else:
            runs.append([s, e, b, 1])
    return runs


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    names, kernels, copies = load(argv[1])
    t0 = copies[0][0] if copies else kernels[0][0]
    what = argv[2] if len(argv) > 2 else "passes"
    ps = passes(names, kernels)
    if what == "passes":
        print("  #   start s    wall ms  kernels")
        for i, (s, e, lo, n) in enumerate(ps):
            gap = (s - ps[i - 1][1]) / 1e9 if i else 0.0
            print(f"{i:3d} {(s - t0) / 1e9:9.3f} {(e - s) / 1e6:10.1f} {n:8d}" + (f"   {gap:.1f} s after the forward before it" if gap > 1.0 else ""))
    elif what == "copies":
        print("  start s  copies      MiB  wall ms  GiB/s")
        for s, e, b, n in copy_runs(copies):
            if b >= BIG_COPY:
                print(f"{(s - t0) / 1e9:9.3f} {n:7d} {b / 2**20:8.1f} {(e - s) / 1e6:8.1f} {b / 2**30 / ((e - s) / 1e9):6.1f}")
    elif what == "diff":
        picks = [(int(a.split(":")[0]), int(a.split(":")[1]) if ":" in a else 0) for a in argv[3:]]
        if not picks:
            print("diff needs pass numbers")
            return 2
        cols = []
        for i, rows in picks:
            s, e, lo, n = ps[i]
            ks = kernels[lo:lo + n]
            main_stream = collections.Counter(st for _, _, _, st in ks).most_common(1)[0][0]
            mk = [(a, b) for a, b, _, st in ks if st == main_stream]
            idle = sum(max(0, mk[j + 1][0] - mk[j][1]) for j in range(len(mk) - 1))
            by = collections.defaultdict(lambda: [0, 0])
            for a, b, name, _ in ks:
                by[names[name]][0] += 1
                by[names[name]][1] += b - a
            cols.append((i, rows, (e - s) / 1e6, sum(b - a for a, b in mk) / 1e6, idle / 1e6, by))
        for i, rows, wall, busy, idle, _ in cols:
            print(f"pass {i}" + (f" ({rows} rows)" if rows else "") + f": wall {wall:.1f} ms, main stream busy {busy:.1f} ms, idle between its kernels {idle:.1f} ms")
        order = sorted(set().union(*(c[5].keys() for c in cols)), key=lambda k: -cols[0][5].get(k, [0, 0])[1])
        head = "kernel".ljust(40) + "".join(f"  launches {c[0]:>3d}   ms" + ("  ms/1k rows" if c[1] else "") for c in cols)
        print(head)
        for k in order[:30]:
            line = k[:39].ljust(40)
            for _, rows, _, _, _, by in cols:
                n, t = by.get(k, [0, 0])
                line += f"  {n:12d} {t / 1e6:7.1f}" + (f" {t / 1e6 / rows * 1000:11.1f}" if rows else "")
            print(line)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
