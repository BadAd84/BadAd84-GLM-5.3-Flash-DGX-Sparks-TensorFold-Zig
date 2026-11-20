#!/usr/bin/env python3
"""score93.py [--dir DIR] - queue93 (scripts/queues/queue93.sh): the receipts of the two pilot levers, main against the branch, read from upstream's own bench tools' reports.

DIR holds one folder a boot, <label>/concurrent.json (tools/bench_concurrent.py --alone --serial), <label>/decode.json (tools/bench_openai.py) and <label>/cache-<N>.json
(tools/bench_cache.py --require-cold), the way queue93 writes them. A cell is (prompt, temperature, streams); its rate is the tool's own aggregate_tps (the median of the cell's reps).

THE KEEP_SEQS RULE, written before queue93's rows existed. Contexts 262144 and 1048576, boots A (main, TF_GLM_KEEP_SEQS unset: A1 A2), B1 (the branch with TF_GLM_KEEP_SEQS=1: B1a B1b), and at
1048576 B0 (the branch, switch unset). Labels ks262-A1 ks262-B1a ks262-B1b ks262-A2 and ks1m-A1 ks1m-B1a ks1m-B1b ks1m-A2 ks1m-B0. The receipt holds when, at both contexts,
  - every boot's own checks are clean (alone and serial: no unequal, no failed reply) and every cell's reply digests are the same set in every boot (the switch changes no token),
  - no greedy cell at 1 or 4 streams reads more than 1.0% slower in B1 than in A (the mean of each group's boots),
  - and at 1048576, where the removed cost is largest, every greedy cell at 4 streams has both B1 boots above both A boots by a mean of at least 1.0%;
  and at 1048576 the default path holds: no greedy cell of B0 differs from A's mean by more than 1.0%. A missing boot or report is NOT DECIDED.

THE NO_COPY RULE, written first as well. Context 1048576, boots A (main: A1 A2), B1 (the branch with TF_GLM_NO_COPY=1: B1a B1b), B0 (the branch, switch unset): labels nc-A1 nc-B1a nc-B0 nc-B1b nc-A2.
The receipt holds when
  - every boot's own checks are clean and every cell's reply digests (greedy and sampled) are the same set in every boot, B1 and B0 included,
  - no cell at 1, 2 or 4 streams reads more than 1.0% slower in B1 than in A,
  - the code prompt at one stream, greedy, has both B1 boots above both A boots and B0 by a mean of at least 1.0%,
  - and B0 is within 1.0% of A's mean on every cell.
A missing boot or report is NOT DECIDED. Whether a verdict is a trade is the owner's call.
"""
import argparse
import json
import os
import statistics as st
import sys

LIMIT = 0.010
KEEP_CTX = (("ks262", 262144), ("ks1m", 1048576))
KEEP_BOOTS = {"A": ("A1", "A2"), "B1": ("B1a", "B1b"), "B0": ("B0",)}
NC_BOOTS = {"A": ("nc-A1", "nc-A2"), "B1": ("nc-B1a", "nc-B1b"), "B0": ("nc-B0",)}


def read(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def cells(report):
    """{(prompt, temperature, streams): {tps, shas, clean}} of one concurrent.json; clean is False when the tool's own alone or serial check found a difference or a failure."""
    out = {}
    for c in report.get("cells", []):
        shas = set()
        missing = False
        for rep in c.get("reps", []):
            for ev in rep.get("evidence", []):
                v = ev.get("token_sha256")
                if v is None:
                    missing = True
                else:
                    shas.add(v)
        bad = False
        for key in ("alone", "serial"):
            if key in c and (c[key].get("unequal", 0) or c[key].get("failed", 0)):
                bad = True
        out[(c["prompt"], float(c["temperature"]), int(c["streams"]))] = {"tps": float(c["aggregate_tps"]), "shas": tuple(sorted(shas)), "clean": not bad and not missing}
    return out


def boot(d, label):
    rep = read(f"{d}/{label}/concurrent.json")
    return cells(rep) if rep is not None else None


def group(d, labels):
    """(missing labels, per cell list of rates, per cell set of digest tuples, every boot clean)."""
    miss, rates, digs, clean = [], {}, {}, True
    for label in labels:
        c = boot(d, label)
        if c is None:
            miss.append(label)
            continue
        for k, v in c.items():
            rates.setdefault(k, []).append(v["tps"])
            digs.setdefault(k, set()).add(v["shas"])
            clean = clean and v["clean"]
    return miss, rates, digs, clean


def diff(new, old):
    """Fraction by which the mean of `new` is above the mean of `old`."""
    return st.mean(new) / st.mean(old) - 1


def both_above(new, old):
    return min(new) > max(old)


def name(k):
    return f"{k[0]} at {k[1]:g} with {k[2]} stream(s)"


def keep_ctx(d, prefix, ctx):
    labels = {arm: tuple(f"{prefix}-{x}" for x in xs) for arm, xs in KEEP_BOOTS.items()}
    need = ("A", "B1") + (("B0",) if prefix == "ks1m" else ())
    out, reasons = [], []
    groups = {}
    for arm in need:
        miss, rates, digs, clean = group(d, labels[arm])
        if miss:
            return out, [f"no rows for {', '.join(miss)}"], True
        groups[arm] = (rates, digs, clean)
    out.append(f"== keep-seqs at --context {ctx}: A {labels['A']}, B1 {labels['B1']}" + (f", B0 {labels['B0']}" if "B0" in groups else ""))
    union = {}
    for arm, (rates, digs, clean) in groups.items():
        if not clean:
            reasons.append(f"{arm}: a boot's own alone or serial check found a difference or failed")
        for k, v in digs.items():
            union.setdefault(k, set()).update(v)
    differing = sorted(k for k, v in union.items() if len(v) != 1)
    if differing:
        reasons.append(f"{len(differing)} cell(s) with more than one reply digest: {'; '.join(name(k) for k in differing[:4])}")
    arates = groups["A"][0]
    for k in sorted(arates):
        if k[1] != 0 or k[2] not in (1, 4):
            continue
        b1 = groups["B1"][0].get(k)
        if b1 is None:
            reasons.append(f"no B1 cell for {name(k)}")
            continue
        g = diff(b1, arates[k])
        line = f"{name(k)}: B1 {g:+.2%} against A (A {' '.join(f'{x:.1f}' for x in arates[k])} | B1 {' '.join(f'{x:.1f}' for x in b1)})"
        if g < -LIMIT:
            reasons.append(f"{name(k)} is {-g:.2%} slower in B1")
            line += "  <- over the limit"
        if prefix == "ks1m" and k[2] == 4 and not (both_above(b1, arates[k]) and g >= LIMIT):
            reasons.append(f"{name(k)}: B1 is not above A on both boots by {LIMIT:.0%}")
            line += "  <- no gain"
        out.append(line)
        if "B0" in groups and k in groups["B0"][0]:
            d0 = diff(groups["B0"][0][k], arates[k])
            out.append(f"  default path {name(k)}: B0 {d0:+.2%} against A")
            if abs(d0) > LIMIT:
                reasons.append(f"{name(k)}: B0 differs from A by {d0:+.2%}")
    return out, reasons, False


def keep(d):
    lines, reasons, undecided = [], [], False
    for prefix, ctx in KEEP_CTX:
        o, r, u = keep_ctx(d, prefix, ctx)
        lines += o
        reasons += r
        undecided = undecided or u
    if undecided:
        return lines, "KEEP_SEQS: NOT DECIDED: " + "; ".join(reasons)
    if reasons:
        return lines, "KEEP_SEQS: RECEIPT FAILS: " + "; ".join(reasons)
    return lines, "KEEP_SEQS: RECEIPT HOLDS at both contexts"


def nocopy(d):
    out, reasons = [], []
    groups = {}
    for arm in ("A", "B1", "B0"):
        miss, rates, digs, clean = group(d, NC_BOOTS[arm])
        if miss:
            return out, f"NO_COPY: NOT DECIDED: no rows for {', '.join(miss)}"
        groups[arm] = (rates, digs, clean)
    out.append(f"== no-copy at --context 1048576: A {NC_BOOTS['A']}, B1 {NC_BOOTS['B1']}, B0 {NC_BOOTS['B0']}")
    union = {}
    for arm, (rates, digs, clean) in groups.items():
        if not clean:
            reasons.append(f"{arm}: a boot's own alone or serial check found a difference or failed")
        for k, v in digs.items():
            union.setdefault(k, set()).update(v)
    differing = sorted(k for k, v in union.items() if len(v) != 1)
    if differing:
        reasons.append(f"{len(differing)} cell(s) with more than one reply digest: {'; '.join(name(k) for k in differing[:4])}")
    arates = groups["A"][0]
    for k in sorted(arates):
        if k[2] not in (1, 2, 4):
            continue
        b1, b0 = groups["B1"][0].get(k), groups["B0"][0].get(k)
        if b1 is None or b0 is None:
            reasons.append(f"no B1 or B0 cell for {name(k)}")
            continue
        g, d0 = diff(b1, arates[k]), diff(b0, arates[k])
        out.append(f"{name(k)}: B1 {g:+.2%}, B0 {d0:+.2%} against A (A {' '.join(f'{x:.1f}' for x in arates[k])} | B1 {' '.join(f'{x:.1f}' for x in b1)} | B0 {b0[0]:.1f})")
        if g < -LIMIT:
            reasons.append(f"{name(k)} is {-g:.2%} slower in B1")
        if abs(d0) > LIMIT:
            reasons.append(f"{name(k)}: B0 differs from A by {d0:+.2%}")
    key = ("code", 0.0, 1)
    if key in arates and key in groups["B1"][0] and key in groups["B0"][0]:
        refs = arates[key] + groups["B0"][0][key]
        if not (both_above(groups["B1"][0][key], refs) and diff(groups["B1"][0][key], arates[key]) >= LIMIT):
            reasons.append(f"{name(key)}: B1 is not above A and B0 on every boot by {LIMIT:.0%}")
    else:
        reasons.append(f"no {name(key)} cell in every group")
    if reasons:
        return out, "NO_COPY: RECEIPT FAILS: " + "; ".join(reasons)
    return out, "NO_COPY: RECEIPT HOLDS"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default="docs/audit-2026-11-12/queue-rows/queue93/f93-c")
    a = ap.parse_args(argv)
    for fn in (keep, nocopy):
        lines, verdict = fn(a.dir)
        print("\n".join(lines))
        print(verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
