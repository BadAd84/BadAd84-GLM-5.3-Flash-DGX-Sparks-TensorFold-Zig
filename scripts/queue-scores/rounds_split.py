#!/usr/bin/env python3
"""rounds_split.py --dir DIR [--ref UNIT] [--cells C1 P1 ...] UNIT... - a decode cell's rate split into tokens a round and ms a round.

DIR holds dec-<UNIT>/<CELL>.jsonl as the queues write them (scripts/streams.py rows: agg_tok_s, tok_per_round, ms_per_round, acceptance, one row a round
of the cell). A cell is a letter and a client count: C1 is greedy code at one client, P4 greedy prose at four. Per unit and cell the script prints the means of
those four fields over the cell's rows; with --ref it also prints each unit's change against the reference unit's, in percent, for the rate, the tokens a
round and the ms a round, so a decode gap reads as "acceptance" (tokens a round moved) or "step time" (ms a round moved). A report only: it decides nothing.
"""
import argparse
import json
import os
import statistics as st
import sys

FIELDS = ("agg_tok_s", "tok_per_round", "ms_per_round", "acceptance")
DEFAULT_CELLS = ("C1", "C2", "C4", "P1", "P2", "P4")


def load(d, unit, cell):
    """{field: mean over the cell's rows} of dec-UNIT/CELL.jsonl, or None when the file is absent or no row carries a field."""
    path = os.path.join(d, f"dec-{unit}", f"{cell}.jsonl")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    out = {}
    for f in FIELDS:
        v = [r[f] for r in rows if r.get(f) is not None]
        if not v:
            return None
        out[f] = st.mean(v)
    out["rows"] = len(rows)
    return out


def change(new, old):
    """Percent by which new is above old."""
    return (new / old - 1) * 100


def report(d, units, cells, ref):
    lines = []
    for cell in cells:
        base = load(d, ref, cell) if ref else None
        for unit in units:
            m = load(d, unit, cell)
            if m is None:
                lines.append(f"{cell:3} {unit:5} no rows")
                continue
            line = f"{cell:3} {unit:5} {m['agg_tok_s']:8.1f} tok/s {m['tok_per_round']:6.2f} tok/round {m['ms_per_round']:6.1f} ms/round accept {m['acceptance']:.3f} ({m['rows']} rows)"
            if base is not None and unit != ref:
                line += (f"  vs {ref}: rate {change(m['agg_tok_s'], base['agg_tok_s']):+.1f}%, tok/round {change(m['tok_per_round'], base['tok_per_round']):+.1f}%,"
                         f" ms/round {change(m['ms_per_round'], base['ms_per_round']):+.1f}%")
            lines.append(line)
        lines.append("")
    return lines


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", required=True)
    p.add_argument("--ref")
    p.add_argument("--cells", nargs="+", default=list(DEFAULT_CELLS))
    p.add_argument("units", nargs="+")
    a = p.parse_args(argv)
    print("\n".join(report(a.dir, a.units, a.cells, a.ref)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
