#!/usr/bin/env python3
"""derive99.py [--dir DIR] [--score FILE] [--sections ...] - the aggregates OVERNIGHT section 78 quotes for queue99 (TF_CACHE_EVICT unset against decayed_resume, boots ca1 ce1 ce2 ca2). A report: it decides nothing.

DIR is queue99's f99-c (default docs/audit-2026-11-12/queue-rows/queue99/f99-c). FILE is score99.py's printed output; when it is not given, score99.py is run on DIR and its output is read.
Sections printed:
  cells     the C1 cells by group: the 12 decode cells at 1, 2 and 4 clients and the 8 at 6 and 8 (the policy arm's mean slower than the control's, a negative number meaning faster), how many
            are slower and how many are over the 1.0% limit, and the four prompt cells.
  flagged   each cell that C1 flags (more than 1.0% slower): its four boots in run order ca1 ce1 ce2 ca2 and the policy arm's change in each of the two adjacent pairs (ca1 with ce1, ca2 with ce2).
  spreads   the boot-to-boot spread of every group of two boots (C3), by client level.
  counters  per boot, the engine's cumulative prompt-cache counters at the end of its kept log (the last `prompt cache:` line of r0-BOOT.log) and its prompt-cache budget from its facts row,
            and the spread of the budget across the four boots.
"""
import argparse
import importlib.util
import json
import pathlib
import re
import statistics as st
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
BOOTS = ("ca1", "ce1", "ce2", "ca2")
C1_LINE = re.compile(r"^(?P<cell>[a-z0-9 +]+?): CA mean (?P<camean>[\d.]+) \(boots (?P<ca1>[\d.]+) (?P<ca2>[\d.]+)\) \| CE mean (?P<cemean>[\d.]+) \(boots (?P<ce1>[\d.]+) (?P<ce2>[\d.]+)\) \| (?P<d>[+-][\d.]+)% slower")
C3_LINE = re.compile(r"^(?P<cell>(?:greedy|sampled) (?:prose|code) at (?P<n>\d+) clients): CA spread (?P<ca>[\d.]+)% of mean \| CE spread (?P<ce>[\d.]+)% of mean")
LIMIT = 1.0


def load_d98():
    spec = importlib.util.spec_from_file_location("derive98", HERE / "derive98.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def block(lines, head, tail):
    """The lines of score99's printed output between the heading starting `head` and the heading starting `tail` (exclusive)."""
    out, inside = [], False
    for line in lines:
        if line.startswith(head):
            inside = True
            continue
        if inside and line.startswith(tail):
            break
        if inside:
            out.append(line)
    return out


def parse_c1(lines):
    """[{cell, ca1, ce1, ce2, ca2 (floats), slower (float, the printed percent)}] from the C1 block."""
    out = []
    for line in block(lines, "== C1", "== C2"):
        m = C1_LINE.match(line)
        if m:
            out.append({"cell": m["cell"], "ca1": float(m["ca1"]), "ca2": float(m["ca2"]), "ce1": float(m["ce1"]), "ce2": float(m["ce2"]), "slower": float(m["d"])})
    return out


def parse_c3(lines):
    """[(clients, spread percent)] for every decode group in the C3 block."""
    out = []
    for line in block(lines, "== C3", "== C4"):
        m = C3_LINE.match(line)
        if m:
            out += [(int(m["n"]), float(m["ca"])), (int(m["n"]), float(m["ce"]))]
    return out


def clients(cell):
    m = re.search(r"at (\d+) clients", cell)
    return int(m.group(1)) if m else None


def group_stats(values):
    """(count, min, max, mean, number slower, number over the limit) of a list of percentages (slower positive)."""
    return len(values), min(values), max(values), st.mean(values), sum(1 for x in values if x > 0), sum(1 for x in values if x > LIMIT)


def pair_changes(r):
    """(pair 1, pair 2): the policy arm's percent slower against the control in the adjacent pairs of the run order ca1 ce1 ce2 ca2, a negative number meaning faster."""
    return (r["ca1"] / r["ce1"] - 1) * 100, (r["ca2"] / r["ce2"] - 1) * 100


def print_cells(c1):
    dec = [r for r in c1 if clients(r["cell"]) is not None]
    for label, levels in (("1, 2, 4", (1, 2, 4)), ("6, 8", (6, 8))):
        n, lo, hi, mean, slower, over = group_stats([r["slower"] for r in dec if clients(r["cell"]) in levels])
        print(f"decode cells at {label} clients: {n} cells, the policy arm slower by {lo:+.2f}% to {hi:+.2f}% (a negative number is faster), mean {mean:+.2f}%, {slower} of {n} slower, {over} over the {LIMIT}% limit")
    print("prompt cells (cold 8k, 32k, 120k, conversation turns 2+): the policy arm slower by " + ", ".join(f"{r['slower']:+.2f}%" for r in c1 if clients(r["cell"]) is None))


def print_flagged(c1):
    flagged = [r for r in c1 if r["slower"] > LIMIT]
    print(f"{len(flagged)} cell(s) over the {LIMIT}% limit; boots in run order ca1 ce1 ce2 ca2, then each adjacent pair's change (policy arm slower, negative faster):")
    for r in flagged:
        p1, p2 = pair_changes(r)
        print(f"  {r['cell']:28s} {r['ca1']:7.1f} {r['ce1']:7.1f} {r['ce2']:7.1f} {r['ca2']:7.1f} | pair ca1-ce1 {p1:+.2f}%, pair ca2-ce2 {p2:+.2f}% | group means {r['slower']:+.2f}%")


def print_spreads(c3):
    for label, levels in (("1, 2, 4", (1, 2, 4)), ("6, 8", (6, 8))):
        v = [s for n, s in c3 if n in levels]
        print(f"decode cells at {label} clients: {len(v)} group spreads (two boots each), from {min(v):.2f}% to {max(v):.2f}% of the mean, median {st.median(v):.2f}%")


def print_counters(d, d98):
    budgets = {}
    for line in (d / "rows.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("case") == "boot":
            budgets[r["tag"]] = (r.get("metrics") or {}).get("prompt_cache_budget_bytes")
    print(f"{'boot':5s} {'budget bytes':>14s} {'log lines':>9s} {'states':>6s} {'held MiB':>8s} {'hits':>5s} {'misses':>6s} {'evicted':>7s} {'trimmed':>7s}")
    for tag in BOOTS:
        log = d / f"r0-{tag}.log"
        rows = d98.cache_rows(log.read_text(encoding="utf-8", errors="replace").splitlines()) if log.exists() else []
        if not rows:
            print(f"{tag:5s} {budgets.get(tag)!s:>14s}  no prompt cache line in r0-{tag}.log")
            continue
        last = rows[-1]
        print(f"{tag:5s} {budgets.get(tag)!s:>14s} {len(rows):>9d} {last['states']:>6d} {last['held_mib']:>8d} {last['hits']:>5d} {last['misses']:>6d} {last['evicted']:>7d} {last['trimmed']:>7d}")
    vals = [v for v in budgets.values() if v]
    if vals:
        print(f"budget across the four boots of one recipe: {min(vals):,} to {max(vals):,} bytes, spread {(max(vals) / min(vals) - 1):.2%}")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default="docs/audit-2026-11-12/queue-rows/queue99/f99-c")
    ap.add_argument("--score", default="")
    ap.add_argument("--sections", nargs="+", default=["cells", "flagged", "spreads", "counters"], choices=["cells", "flagged", "spreads", "counters"])
    a = ap.parse_args(argv)
    d = pathlib.Path(a.dir)
    if a.score:
        text = pathlib.Path(a.score).read_text(encoding="utf-8")
    else:
        text = subprocess.run([sys.executable, str(HERE / "score99.py"), "--q99", str(d)], capture_output=True, text=True, check=True).stdout
    lines = text.splitlines()
    c1, c3 = parse_c1(lines), parse_c3(lines)
    for sec in a.sections:
        print(f"##### {sec}")
        {"cells": lambda: print_cells(c1), "flagged": lambda: print_flagged(c1), "spreads": lambda: print_spreads(c3), "counters": lambda: print_counters(d, load_d98())}[sec]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
