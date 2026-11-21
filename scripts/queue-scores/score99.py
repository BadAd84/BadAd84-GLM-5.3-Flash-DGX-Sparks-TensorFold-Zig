#!/usr/bin/env python3
"""score99.py [--q99 DIR] - queue99 (scripts/queues/queue99.sh): the five-level no-regression check of TF_CACHE_EVICT=decayed_resume against unset, on the stack on the pin
(image m130a), on the cells queue95 and queue91 measured.

DIR holds rows.jsonl, <label>/chain.jsonl, dec-<label>/{P,C,SP,SC}<clients>.jsonl and dec-<label>/pp.jsonl in queue91's row format, as queue95's cells write them: --q99 is
queue99's f99-c (default work/pp99/f99-c). score91.py's own readers, imported below, parse them, so a cell is exactly score91's.

GROUPS. CA, the control, the recipe as committed: ca1 ca2. CE, the policy: ce1 ce2. The queue boots them ABBA (ca1, ce1, ce2, ca2), so a box that drifts shows as a ca/ce
difference that reverses between the pairs. A group's value for a cell is the mean of its boots. A cell is the cold first token at 8k, 32k and 120k, the mean first token of the
growing conversation's turns 2 to 8, and the aggregate tokens a second of greedy and of sampled prose and code at 1, 2, 4, 6 and 8 clients. "Slower" is a fraction of the
reference (CA) mean.

THE RULES BELOW ARE FIXED BY THE PARENT, WRITTEN BEFORE ANY ROW EXISTED, and quoted here as given:
  C1 SYNC: score91's sync rule exactly (no cell more than 1.0% slower, every reply digest one digest across all four boots), CE against CA. Print every cell's two group values
     and the cells over the limit. Verdict ACCEPTED or NOT ACCEPTED (and the cells) or NOT DECIDED (a missing boot or report).
  C2 PROMPT CELLS (report only, no verdict): the cold 8k/32k/120k and the warm turns, the fraction faster for CE than CA.
  C3 BOOT NOISE (report only): for every cell the two CA boots' spread and the two CE boots' spread (as a fraction of the group mean), so a flagged cell can be read against
     the box's own noise.
  C4 DIGESTS: every reply digest of ce1 and ce2 equals ca1's (cold requests, each conversation turn, each decode cell, the 24 prompts), as score91 reads them; a difference
     FAILS.
  Exit code 1 only when a C4 digest differs; everything else exits 0. Missing boots/reports are NOT DECIDED for the clause that needs them, never a pass.

A cell at exactly the limit is not over it: C1 flags when `over(s)`, that is strictly above 1.0%, and an exact 1.0% cannot be built by division in doubles anyway (the nearest
double to 1.01 is 1.010000000000000009), so the tests bracket the limit at 0.99% accepted and 1.01% flagged and probe `over(LIMIT)` directly.
"""
import argparse
import importlib.util
import pathlib
import statistics as st
import sys

_S91 = None


def s91():
    """score91.py, whose rows(), boot(), group(), slower() and name() are the one owner of queue91's row format (found above this file, so a scratch copy still finds it)."""
    global _S91
    if _S91 is None:
        for p in pathlib.Path(__file__).resolve().parents:
            f = p / "scripts/queue-scores/score91.py"
            if f.exists():
                spec = importlib.util.spec_from_file_location("score91", f)
                _S91 = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(_S91)
                break
        else:
            raise SystemExit("score99: scripts/queue-scores/score91.py not found above this file")
    return _S91


LIMIT = s91().LIMIT  # C1: score91's limit, a cell more than this much slower than the control's mean is a regression
SIZES = s91().SIZES
LEVELS = s91().LEVELS
KINDS = s91().KINDS
CELLS = [("cold", s) for s in SIZES] + [("warm",)] + [("dec", k, n) for k, _ in KINDS for n in LEVELS]
PROMPT_CELLS = [("cold", 8000), ("cold", 32000), ("cold", 120000), ("warm",)]


def groups(q99):
    """{group: [(DIR, label)]}: the control's two boots and the policy's two, as the queue's ABBA order writes them."""
    return {"CA": [(q99, "ca1"), (q99, "ca2")], "CE": [(q99, "ce1"), (q99, "ce2")]}


def over(s):
    """True when a cell's slower fraction is over the limit; a value at exactly the limit is not over it."""
    return s > LIMIT


def load(boots):
    """(labels with no rows, per-cell boot values, reply digests by key) of one group, score91.py's group()."""
    return s91().group(boots)


def name(m):
    return s91().name(m)


def labels(boots):
    return " ".join(label for _, label in boots)


def short_cells(vals, boots, cells):
    """[(cell, boots that measured it, boots in the group)] of cells a group did not report on every boot: a cell read from fewer boots than the group has is NOT DECIDED."""
    return [(m, len(vals.get(m, [])), len(boots)) for m in cells if len(vals.get(m, [])) != len(boots)]


def spread(v):
    """A group's boot-to-boot spread of one cell: (max - min) over the group mean, the box's own noise as a fraction of it."""
    return (max(v) - min(v)) / st.mean(v)


def boots_line(v):
    return " ".join(f"{x:.1f}" for x in v)


# ---------------------------------------------------------------- C1 sync

def c1(g):
    """(lines, verdict): score91's sync rule, the policy CE against the control CA, two boots each and four for the digests."""
    out, flagged, absent, holes = [], [], [], []
    ca_missing, cav, cad = load(g["CA"])
    ce_missing, cev, ced = load(g["CE"])
    if ca_missing or ce_missing:
        return out, f"C1 SYNC: NOT DECIDED: no rows for {', '.join(ca_missing + ce_missing)}"
    out.append(f"== C1 sync: CE ({labels(g['CE'])}) against CA ({labels(g['CA'])}); slower is positive, the limit {LIMIT:.1%}")
    for m in CELLS:
        ca_have, ce_have = len(cav.get(m, [])), len(cev.get(m, []))
        if not ca_have or not ce_have:
            side = "CA" if not ca_have else "CE"
            absent.append(f"{name(m)} (no {side} rows)")
            out.append(f"{name(m)}: MISSING in {side}")
            continue
        if ca_have != len(g["CA"]) or ce_have != len(g["CE"]):
            absent.append(f"{name(m)} ({ca_have} of {len(g['CA'])} CA boots, {ce_have} of {len(g['CE'])} CE boots)")
            out.append(f"{name(m)}: CA measured on {ca_have} of {len(g['CA'])} boots, CE on {ce_have} of {len(g['CE'])}: NOT DECIDED")
            continue
        ca, ce = st.mean(cav[m]), st.mean(cev[m])
        s = s91().slower(m, ce, ca)
        inside = min(cav[m]) <= min(cev[m]) and max(cev[m]) <= max(cav[m])
        line = (f"{name(m)}: CA mean {ca:.1f} (boots {boots_line(cav[m])}) | CE mean {ce:.1f} (boots {boots_line(cev[m])}) | {s:+.2%} slower")
        if over(s):
            line += f"  <- over the limit (CE {min(cev[m]):.1f}..{max(cev[m]):.1f}" + (f" inside CA {min(cav[m]):.1f}..{max(cav[m]):.1f})" if inside else ")")
            flagged.append((m, inside))
        out.append(line)
    boots = len(g["CA"]) + len(g["CE"])
    keys = sorted(set(cad) | set(ced), key=str)
    holes = [k for k in keys if len(cad.get(k, [])) + len(ced.get(k, [])) != boots]
    differ = [k for k in keys if k not in holes and len({*cad.get(k, []), *ced.get(k, [])}) != 1]
    out.append(f"reply digests: {len(keys)} keys over {boots} boots, {len(holes)} key(s) missing a boot's report, {len(differ)} with more than one digest across the boots")
    for k in (holes + differ)[:12]:
        out.append(f"  {'missing' if k in holes else 'differs'}: {k}")
    if absent or holes:
        why = absent + [f"digest {k} missing a boot's report" for k in holes]
        return out, f"C1 SYNC: NOT DECIDED: {len(why)} cell(s) or digest key(s) have no report: {'; '.join(why[:6])}"
    if differ:
        return out, f"C1 SYNC: NOT ACCEPTED: reply digests differ at {len(differ)} key(s) (and {len(flagged)} cell(s) over the speed limit)"
    if flagged:
        inside = sum(1 for _, i in flagged if i)
        names = "; ".join(name(m) for m, _ in flagged)
        return out, f"C1 SYNC: NOT ACCEPTED: {len(flagged)} cell(s) more than {LIMIT:.0%} slower ({inside} inside CA's boots' range): {names}"
    return out, f"C1 SYNC: ACCEPTED, no cell more than {LIMIT:.0%} slower and every reply digest equal"


# ---------------------------------------------------------------- C2 prompt cells (report only)

def c2(g):
    """(lines): the four prompt cells as the fraction faster for CE than CA; a report, never a verdict."""
    out = ["== C2 prompt cells: the fraction faster for CE than CA (report only, no verdict)"]
    ca_missing, cav, _ = load(g["CA"])
    ce_missing, cev, _ = load(g["CE"])
    if ca_missing or ce_missing:
        out.append(f"C2: NOT DECIDED: no rows for {', '.join(ca_missing + ce_missing)}")
        return out
    for m in PROMPT_CELLS:
        ca_have, ce_have = len(cav.get(m, [])), len(cev.get(m, []))
        if ce_have != len(g["CE"]) or ca_have != len(g["CA"]):
            out.append(f"{name(m)}: NOT DECIDED: CA measured on {ca_have} of {len(g['CA'])} boots, CE on {ce_have} of {len(g['CE'])}")
            continue
        ca_mean, ce_mean = st.mean(cav[m]), st.mean(cev[m])
        out.append(f"{name(m)}: CA mean {ca_mean:.1f} (boots {boots_line(cav[m])}) | CE mean {ce_mean:.1f} (boots {boots_line(cev[m])}) | {1 - ce_mean / ca_mean:+.2%} faster")
    return out


# ---------------------------------------------------------------- C3 boot noise (report only)

def c3(g):
    """(lines): every cell's two CA boots' spread and two CE boots' spread over the group mean; a report, never a verdict."""
    out = ["== C3 boot noise: (max - min) of a group's boots over its mean, per cell (report only, no verdict)"]
    ca_missing, cav, _ = load(g["CA"])
    ce_missing, cev, _ = load(g["CE"])
    if ca_missing or ce_missing:
        out.append(f"C3: NOT DECIDED for the boots with no rows: {', '.join(ca_missing + ce_missing)}")
    for m in CELLS:
        parts = []
        for tag, vals in (("CA", cav), ("CE", cev)):
            v = vals.get(m, [])
            if not v:
                parts.append(f"{tag} no rows")
            elif len(v) < 2:
                parts.append(f"{tag} spread {spread(v):.2%} of mean on {len(v)} boot")
            else:
                parts.append(f"{tag} spread {spread(v):.2%} of mean")
        out.append(f"{name(m)}: " + " | ".join(parts))
    return out


# ---------------------------------------------------------------- C4 digests

def c4(g):
    """(lines, {boot: verdict}): every reply digest of ce1 and ce2 against ca1's, key for key, as score91's reader keys them."""
    out, verdicts = [], {}
    d = g["CA"][0][0]
    ca_val, ca_dig = s91().boot(d, "ca1")
    out.append(f"== C4 digests: ce1 and ce2 against ca1 ({d})")
    if not ca_val:
        out.append("C4 DIGESTS: NOT DECIDED: ca1 has no rows")
        return out, {"ce1": "NOT DECIDED", "ce2": "NOT DECIDED"}
    for arm in ("ce1", "ce2"):
        val, dig = s91().boot(d, arm)
        if not val:
            verdicts[arm] = "NOT DECIDED"
            out.append(f"{arm}: NOT DECIDED: no rows")
            continue
        only = sorted(set(ca_dig) ^ set(dig), key=str)
        differ = sorted((k for k in set(ca_dig) & set(dig) if ca_dig[k] != dig[k]), key=str)
        out.append(f"{arm}: {len(set(ca_dig) | set(dig))} digest key(s), {len(only)} on one side only, {len(differ)} differing")
        for k in only[:6]:
            out.append(f"  one side only: {k}")
        for k in differ[:6]:
            out.append(f"  differs: {k}")
        if only:
            verdicts[arm] = "NOT DECIDED"
            out.append(f"{arm}: NOT DECIDED: a report is missing on one side (never a pass)")
        elif differ:
            verdicts[arm] = "DIFFERS"
            out.append(f"{arm}: DIFFERS at {len(differ)} key(s)")
        else:
            verdicts[arm] = "EQUAL"
            out.append(f"{arm}: EQUAL to ca1 at every key")
    differ_arms = [arm for arm in ("ce1", "ce2") if verdicts[arm] == "DIFFERS"]
    undecided = [arm for arm in ("ce1", "ce2") if verdicts[arm] == "NOT DECIDED"]
    if differ_arms:
        out.append(f"C4 DIGESTS: DIFFERS at {len(differ_arms)} arm(s): {', '.join(differ_arms)}")
    elif undecided:
        out.append(f"C4 DIGESTS: NOT DECIDED: {', '.join(undecided)}")
    else:
        out.append("C4 DIGESTS: EQUAL, every reply digest of ce1 and ce2 equals ca1's")
    return out, verdicts


# ---------------------------------------------------------------- report and exit code

def report(q99):
    """(lines, {clause: verdicts}, failed): the whole report; failed when a C4 digest differs."""
    g = groups(q99)
    l1, v1 = c1(g)
    l2 = c2(g)
    l3 = c3(g)
    l4, v4 = c4(g)
    lines = [f"== score99: q99 {q99}"] + l1 + [v1] + l2 + l3 + l4
    failed = any(v == "DIFFERS" for v in v4.values())
    return lines, {"C1": v1, "C4": v4}, failed


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--q99", default="work/pp99/f99-c", help="queue99's f99-c (default work/pp99/f99-c)")
    ap.add_argument("--dir", dest="q99", help="alias of --q99, queue98's flag name")
    a = ap.parse_args(argv)
    lines, _, failed = report(a.q99)
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
