#!/usr/bin/env python3
"""score91.py [--new DIR] [--old DIR] - queue91 (scripts/queues/queue91.sh): the stack re-seated on upstream main against the v1.2.9 stack, and the arms beside it.

DIR holds rows.jsonl, <label>/chain.jsonl and dec-<label>/{P,C,SP,SC}<clients>.jsonl as the queues write them: --new is queue91's f91-c, --old queue77's f77-c.

THE SYNC RULE, written before queue91's rows existed. The re-seated stack on main (boots mn1 and mn2, the recipe as committed) is accepted against the v1.2.9 stack
(queue77's P1 and P2 from --old and queue91's mo3, the same recipe on the old image) when
  - no cell reads more than 1.0% slower, a cell being the cold first token at 8k, 32k and 120k, the mean first token of the growing conversation's turns 2 to 8, and the
    aggregate tokens a second of greedy and of sampled prose and code at 1, 2, 4, 6 and 8 clients (each the mean of a group's boots, the new group's against the old's), and
  - every reply digest is one digest across all five boots: the cold requests, each turn of the conversation, each decode cell's reply set and the 24 prompts one at a time.
A cell more than 1.0% slower is named with the two groups' ranges (boot to boot the warm turns spread about 1.8%, so a cell whose new boots lie inside the old boots' range is
marked as inside it); whether a loss is a trade is the owner's call, never this script's. A missing boot is NOT DECIDED. The other arms are reports against the mean of mn1 and
mn2 (md: dev.env, mz: TF_GLM_PDL=0, mps: the stock main) and mr (md with request starts) against md; they never change the verdict.
"""
import argparse
import json
import os
import statistics as st
import sys

LIMIT = 0.010  # a cell more than this much slower than the old group's mean is a regression
SIZES = (8000, 32000, 120000)
LEVELS = (1, 2, 4, 6, 8)
KINDS = (("P", "greedy prose"), ("C", "greedy code"), ("SP", "sampled prose"), ("SC", "sampled code"))
NEW_PROD = ("mn1", "mn2")
OLD_NEW_DIR = ("mo3",)  # the old stack's boot of queue91 itself (in --new); queue77's P1 and P2 (in --old) are the rest of the old group
OLD_OLD_DIR = ("P1", "P2")


def rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def boot(d, label):
    """What one boot of directory d measured: dict of metric -> value (ms or tokens a second), and dict of metric -> reply digest (hashable)."""
    val, dig = {}, {}
    allrows = rows(f"{d}/rows.jsonl")
    for size in SIZES:
        c = [r for r in allrows if r.get("case") == "cold" and r.get("tag") == label and r.get("target_tokens") == size]
        if c:
            val[("cold", size)] = st.mean(r["ttft_ms"] for r in c)
            for r in c:
                dig[("cold", size, r.get("rep"))] = r.get("token_sha")
    ch = [r for r in rows(f"{d}/{label}/chain.jsonl") if r.get("tag") == "c74"]
    if len(ch) > 1:
        val[("warm",)] = st.mean(r["ttft_ms"] for r in ch[1:])
        for t, r in enumerate(ch, 1):
            dig[("chain", t)] = r.get("token_sha")
    for kind, _ in KINDS:
        for n in LEVELS:
            rs = rows(f"{d}/dec-{label}/{kind}{n}.jsonl")
            if rs:
                val[("dec", kind, n)] = st.mean(r["agg_tok_s"] for r in rs)
                dig[("dec", kind, n)] = tuple(sorted({tuple(r["sha"]) for r in rs}))
    for r in rows(f"{d}/dec-{label}/pp.jsonl"):
        dig[("pp", r.get("name"))] = r.get("sha12")
    return val, dig


def slower(metric, new, old):
    """Fraction by which `new` is slower than `old`: latency up by that much, or throughput down by that much of the old rate."""
    return new / old - 1 if metric[0] in ("cold", "warm") else 1 - new / old


def name(metric):
    if metric[0] == "cold":
        return f"cold {metric[1] // 1000}k first token"
    if metric[0] == "warm":
        return "conversation turns 2+ first token"
    return f"{dict(KINDS)[metric[1]]} at {metric[2]} clients"


def group(boots):
    """boots: [(dir, label)]. Returns (labels missing, per-metric list of boot values, digests by key)."""
    vals, digs, missing = {}, {}, []
    for d, label in boots:
        v, g = boot(d, label)
        if not v:
            missing.append(label)
            continue
        for m, x in v.items():
            vals.setdefault(m, []).append(x)
        for k, x in g.items():
            digs.setdefault(k, []).append(x)
    return missing, vals, digs


def score(new_dir, old_dir):
    """(lines, verdict): the report and one verdict line."""
    out = []
    new_missing, new, new_dig = group([(new_dir, l) for l in NEW_PROD])
    old_missing, old, old_dig = group([(old_dir, l) for l in OLD_OLD_DIR] + [(new_dir, l) for l in OLD_NEW_DIR])
    miss = new_missing + old_missing
    if miss:
        return out, f"NOT DECIDED: no rows for {', '.join(miss)}"
    out.append(f"== the stack on main ({', '.join(NEW_PROD)}) against the v1.2.9 stack ({', '.join(OLD_OLD_DIR + OLD_NEW_DIR)}); slower is positive")
    flagged, absent = [], []
    metrics = [("cold", s) for s in SIZES] + [("warm",)] + [("dec", k, n) for k, _ in KINDS for n in LEVELS]
    for m in metrics:
        if m not in new or m not in old:
            absent.append(f"{name(m)} (no {'new' if m not in new else 'old'} rows)")
            out.append(f"{name(m)}: MISSING in {'new' if m not in new else 'old'}")
            continue
        s = slower(m, st.mean(new[m]), st.mean(old[m]))
        inside = min(old[m]) <= min(new[m]) and max(new[m]) <= max(old[m])
        out.append(f"{name(m)}: old {' '.join(f'{x:.1f}' for x in old[m])} | new {' '.join(f'{x:.1f}' for x in new[m])} | {s:+.2%} slower"
                   + ("  <- over the limit" + (" (the new boots lie inside the old boots' range)" if inside else "") if s > LIMIT else ""))
        if s > LIMIT:
            flagged.append((m, inside))
    if absent:
        return out, f"NOT DECIDED: {len(absent)} cell(s) have no rows: {'; '.join(absent[:6])}"
    differ = sorted({k for k in set(new_dig) | set(old_dig) if len({x for x in new_dig.get(k, []) + old_dig.get(k, [])}) != 1}, key=str)
    out.append(f"reply digests: {len(set(new_dig) | set(old_dig))} keys, {len(differ)} with more than one digest across the boots")
    for k in differ[:12]:
        out.append(f"  differs: {k}")
    if differ:
        return out, f"REPLIES DIFFER at {len(differ)} key(s): the numerics changed, the owner's call (and {len(flagged)} cell(s) over the speed limit)"
    if flagged:
        inside = sum(1 for _, i in flagged if i)
        names = "; ".join(name(m) for m, _ in flagged)
        return out, f"SYNC: {len(flagged)} cell(s) more than {LIMIT:.0%} slower ({inside} inside the old boots' range): {names}"
    return out, f"SYNC: ACCEPTED, no cell more than {LIMIT:.0%} slower and every reply digest equal"


def arms(new_dir):
    out = ["== the other arms against the mean of mn1 and mn2 (faster is positive); mr against md"]
    _, base, base_dig = group([(new_dir, l) for l in NEW_PROD])
    _, dev, dev_dig = group([(new_dir, l) for l in ("md1", "md2")])
    for label, ref_name, ref, ref_dig in (("md1 md2", "mn", base, base_dig), ("mz1", "mn", base, base_dig), ("mps", "mn", base, base_dig), ("mr1", "md", dev, dev_dig)):
        _, v, dg = group([(new_dir, l) for l in label.split()])
        if not v or not ref:
            out.append(f"{label}: no rows")
            continue
        cells = [(m, -slower(m, st.mean(v[m]), st.mean(ref[m]))) for m in v if m in ref]
        out.append(f"{label} against {ref_name}: " + "; ".join(f"{name(m)} {x:+.2%}" for m, x in cells))
        out.append(f"{label}: reply digests equal to {ref_name}'s: {all(len({*dg[k], *ref_dig.get(k, [])}) == 1 for k in dg if k in ref_dig)}")
    return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--new", default="docs/audit-2026-11-12/queue-rows/queue91/f91-c")
    ap.add_argument("--old", default="docs/audit-2026-11-12/queue-rows/queue77/f77-c")
    a = ap.parse_args(argv)
    lines, verdict = score(a.new, a.old)
    print("\n".join(lines))
    print("\n".join(arms(a.new)))
    print(verdict)
    return 0 if verdict.startswith("SYNC: ACCEPTED") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
