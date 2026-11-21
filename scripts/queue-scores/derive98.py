#!/usr/bin/env python3
"""derive98.py [--dir DIR] - the aggregates OVERNIGHT section 75 quotes for queue98 (E3, TF_CACHE_EVICT unset against decayed_resume), derived from the rows. A report: it decides nothing.

DIR holds ce-A/ and ce-B/ (trace.json, r0-after.log) and queue98.log's lines are read from DIR/../queue98.log when it exists. Sections printed:
  split     per arm, the agent turns and the one-off prompts apart: requests, rebuilt rows (prompt_tokens - cached_tokens, as the client's own summary sums them), TTFT sum; then the
            change from A to B of each; and score98.py's P2 reading (the agent turns that did not resume the previous turn's prompt) on BOTH arms.
  counters   per arm, from the engine's own `prompt cache:` log lines (r0-after.log): the budget, the states and bytes held at the end, the cumulative hits, misses, evicted, refused,
            failed and trimmed, and the rows resumed by the requests that resumed at all.
  walls      the client's wall seconds per arm, from queue98.log.
"""
import argparse
import importlib.util
import json
import pathlib
import re
import statistics as st
import sys

CACHE_LINE = re.compile(r"prompt cache: (\d+) tokens, resumed at (\d+), kept (\d+); (\d+) states, (\d+) MiB and (\d+) MiB spare of (\d+) MiB "
                        r"\(hits (\d+), misses (\d+), evicted (\d+), refused (\d+), failed (\d+), trimmed (\d+)\)")
WALL = re.compile(r"(ce-[AB]) E3 trace .*? rc=(\d+) wall=(\d+)s")
FIELDS = ("tokens", "resumed_at", "kept", "states", "held_mib", "spare_mib", "budget_mib", "hits", "misses", "evicted", "refused", "failed", "trimmed")


def load_s98():
    spec = importlib.util.spec_from_file_location("score98", pathlib.Path(__file__).resolve().parent / "score98.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_cache_line(line):
    """{field: int} of one engine `prompt cache:` log line, or None when the line is not one."""
    m = CACHE_LINE.search(line)
    return dict(zip(FIELDS, (int(x) for x in m.groups()))) if m else None


def cache_rows(lines):
    return [r for r in (parse_cache_line(l) for l in lines) if r]


def split_rows(report):
    """{kind: (requests, rebuilt rows, ttft sum)} for the agent turns and the one-off prompts of a client report."""
    out = {}
    for kind in ("agent", "one_off"):
        rows = [r for r in report["rows"] if r["kind"] == kind]
        out[kind] = (len(rows), sum(r["prompt_tokens"] - r["cached_tokens"] for r in rows), sum(r["ttft_s"] for r in rows))
    return out


def walls(lines):
    """{arm: (client rc, wall seconds)} from queue98.log's E3 trace lines."""
    out = {}
    for line in lines:
        m = WALL.search(line)
        if m:
            out[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    return out


def change(a, b):
    """The fraction by which B is lower than A, a positive number being less."""
    return 1 - b / a


def print_split(d):
    s98 = load_s98()
    reports = {arm: json.load(open(d / arm / "trace.json", encoding="utf-8")) for arm in ("ce-A", "ce-B")}
    parts = {arm: split_rows(rep) for arm, rep in reports.items()}
    for arm in ("ce-A", "ce-B"):
        for kind, label in (("agent", "agent turns"), ("one_off", "one-off prompts")):
            n, rows, ttft = parts[arm][kind]
            print(f"{arm} {label:15s} {n:4d} requests, rebuilt {rows:>10,d} rows, TTFT sum {ttft:8.1f} s")
    for kind, label in (("agent", "agent turns"), ("one_off", "one-off prompts")):
        a, b = parts["ce-A"][kind], parts["ce-B"][kind]
        print(f"{label:15s} A to B: rebuilt rows {change(a[1], b[1]):.2%} lower, TTFT sum {change(a[2], b[2]):.2%} lower")
    for arm in ("ce-A", "ce-B"):
        lines, _, _ = s98.p2(reports[arm])
        print(f"P2 reading on {arm}: " + " | ".join(l for l in lines if l.startswith(("gaps", "chunk", "A's agent"))).replace("A's", f"{arm[-1]}'s").replace("counts in A", f"counts in {arm[-1]}"))


def print_counters(d):
    for arm in ("ce-A", "ce-B"):
        rows = cache_rows(open(d / arm / "r0-after.log", encoding="utf-8", errors="replace").read().splitlines())
        last = rows[-1]
        deep = [r["resumed_at"] for r in rows if r["resumed_at"] > 0]
        print(f"{arm}: {len(rows)} log lines; budget {last['budget_mib']} MiB; end: {last['states']} states, {last['held_mib']} MiB held; hits {last['hits']}, misses {last['misses']}, "
              f"evicted {last['evicted']}, refused {last['refused']}, failed {last['failed']}, trimmed {last['trimmed']}")
        print(f"   requests that resumed at all: {len(deep)} of {len(rows)}; mean rows resumed over those {st.mean(deep):.0f}, median {st.median(deep):.0f}")


def print_walls(d):
    log = d.parent / "queue98.log"
    if not log.exists():
        print("queue98.log not beside the rows directory")
        return
    w = walls(log.read_text(encoding="utf-8", errors="replace").splitlines())
    for arm in ("ce-A", "ce-B"):
        print(f"{arm}: client rc {w[arm][0]}, wall {w[arm][1]} s ({w[arm][1] // 3600} h {w[arm][1] % 3600 // 60:02d} min {w[arm][1] % 60:02d} s)")
    print(f"wall A to B: {change(w['ce-A'][1], w['ce-B'][1]):.2%} lower")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default="docs/audit-2026-11-12/queue-rows/queue98/f98-c")
    ap.add_argument("--sections", nargs="+", default=["split", "counters", "walls"], choices=["split", "counters", "walls"])
    a = ap.parse_args(argv)
    d = pathlib.Path(a.dir)
    for sec in a.sections:
        print(f"##### {sec}")
        {"split": print_split, "counters": print_counters, "walls": print_walls}[sec](d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
