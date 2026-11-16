"""prod_table.py ARM... - the mean of agg_tok_s and of decode_agg_tok_s over each cell's rounds, from ~/bench/ARM/P<N>.jsonl.

cells.py's table, for cells whose rows may lack the draft counters (production's); FIELD=decode_agg_tok_s selects the other statistic.
agg_tok_s is tokens over the round's wall time (the column production's SPEED-TARGET.md leads with), decode_agg_tok_s first to last chunk.
"""
import json, os, statistics as st, sys
FIELD = os.environ.get("FIELD", "agg_tok_s")
base = os.path.expanduser("~/bench")
arms = sys.argv[1:]
levels = [1, 2, 4, 6, 8]
rows = {}
for a in arms:
    row = []
    for n in levels:
        p = f"{base}/{a}/P{n}.jsonl"
        if not os.path.exists(p):
            row.append(None); continue
        v = [json.loads(l).get(FIELD) for l in open(p)]
        v = [x for x in v if x is not None]
        row.append((st.mean(v), len(v), sorted({s for l in open(p) for s in json.loads(l).get("sha", [])})))
    rows[a] = row
print("arm        " + "".join(f"{n:>12}" for n in levels))
for a, row in rows.items():
    print(f"{a:<10} " + "".join(f"{(c[0] if c else float('nan')):>12.2f}" for c in row))
print("rounds a cell:", {a: [c[1] if c else 0 for c in r] for a, r in rows.items()})
print("reply digests:")
for a, row in rows.items():
    print(f"  {a}: {[c[2] if c else None for c in row][:2]} ...")
