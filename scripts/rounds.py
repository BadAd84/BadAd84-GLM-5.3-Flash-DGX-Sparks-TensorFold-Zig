#!/usr/bin/env python3
"""rounds.py [-P N] TAG... - the last three rounds of ~/bench/TAG/P<N>.jsonl, one line a cell.

Per round: stream 0's decode tok/s, ms a round, tokens a round, acceptance, first-token ms; and the cold pass's
first-token ms where the instrument recorded it (cold_ttft_ms on round 0).
"""
import json
import os
import sys


def main() -> int:
    args = sys.argv[1:]
    p = "1"
    if args and args[0] == "-P":
        p = args[1]
        args = args[2:]
    for tag in args:
        path = os.path.expanduser(f"~/bench/{tag}/P{p}.jsonl")
        if not os.path.exists(path):
            print(f"{tag:22s} no P{p}.jsonl")
            continue
        rows = [json.loads(line) for line in open(path) if line.strip()]
        rows = [r for r in rows if isinstance(r.get("round"), int)][-3:]
        cold = next((r["cold_ttft_ms"] for r in rows if "cold_ttft_ms" in r), None)
        print(f"{tag:22s} tok/s {[r['per_stream'][0] for r in rows]} ms/round {[r['ms_per_round'] for r in rows]} "
              f"tok/round {[r['tok_per_round'] for r in rows]} acc {[r['acceptance'] for r in rows]} "
              f"ttft {[r['ttft_ms'][0] for r in rows]} cold {cold} sha {sorted({s for r in rows for s in r['sha']})}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
