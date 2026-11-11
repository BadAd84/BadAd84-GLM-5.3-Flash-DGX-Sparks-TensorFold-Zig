#!/usr/bin/env python3
"""cells.py [--base TAG] [--root DIR] TAG... - tabulate bench-arm.sh cells as Markdown.

One row per arm: the mean aggregate tok/s over a cell's rounds at P=1,2,4,6,8 (with the delta against --base
when given), then the one-stream round accounting (tokens a round, ms a round, acceptance) and whether every
reply digest equals the base arm's at the same level and stream. A missing cell prints as "-".
"""
import argparse
import json
import os
import statistics

LEVELS = (1, 2, 4, 6, 8)


def cell(root: str, tag: str, p: int):
    path = os.path.join(root, tag, f"P{p}.jsonl")
    if not os.path.exists(path):
        return None
    rows = [json.loads(line) for line in open(path) if line.strip()]
    return rows or None


def digests(rows) -> set:
    """The distinct per-round digest tuples: rounds repeat the same prompts, so an arm's file may hold more runs."""
    return {tuple(r.get("sha", [])) for r in rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base")
    ap.add_argument("--root", default=os.path.expanduser("~/bench"))
    ap.add_argument("tags", nargs="+")
    a = ap.parse_args()
    base = {p: cell(a.root, a.base, p) for p in LEVELS} if a.base else {}
    print("| arm | " + " | ".join(f"P{p}" for p in LEVELS) + " | tok/round | ms/round | accept | digests |")
    print("|---|" + "---:|" * len(LEVELS) + "---:|---:|---:|---|")
    for tag in a.tags:
        out, same = [], []
        for p in LEVELS:
            rows = cell(a.root, tag, p)
            if not rows:
                out.append("-")
                continue
            v = statistics.mean(r["agg_tok_s"] for r in rows)
            s = f"{v:.2f}"
            b = base.get(p)
            if b and tag != a.base:
                bv = statistics.mean(r["agg_tok_s"] for r in b)
                s += f" ({100 * (v / bv - 1):+.1f}%)"
                same.append(digests(rows) == digests(b))
            out.append(s)
        one = cell(a.root, tag, 1) or []
        acct = [r for r in one if "tok_per_round" in r]
        tpr = f"{statistics.mean(r['tok_per_round'] for r in acct):.2f}" if acct else "-"
        mpr = f"{statistics.mean(r['ms_per_round'] for r in acct):.1f}" if acct else "-"
        acc = f"{statistics.mean(r['acceptance'] for r in acct):.3f}" if acct else "-"
        dig = "-" if not same else ("equal" if all(same) else "DIFFER")
        print(f"| {tag} | " + " | ".join(out) + f" | {tpr} | {mpr} | {acc} | {dig} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
