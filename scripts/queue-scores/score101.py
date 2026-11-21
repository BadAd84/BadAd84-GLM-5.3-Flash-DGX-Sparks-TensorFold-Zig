#!/usr/bin/env python3
"""score101.py [--q101 DIR] [--dir DIR] - queue101 (scripts/queues/queue101.sh): the stock-upstream rung at the new upstream main fa13df5dd, four fresh boots of one image
(glm53-zig:ut2, pristine upstream, KNOBS=off, the deployed shape), and the two switches the tip carries beside the rung's own two boots.

DIR holds rows.jsonl, <label>/chain.jsonl, dec-<label>/{P,C,SP,SC}<clients>.jsonl, dec-<label>/pp.jsonl (queue92's layout) and, for every label, <label>-drafter.txt and
<label>-dscores.txt (queue101's two effect-proof files). --q101 is queue101's f92-c (default docs/audit-2026-11-12/queue-rows/queue92/f92-c). The boots are ut2a ut2b (the
stock rung), ut2s (stock with TF_GLM_DRAFT_SPLIT=1, upstream #3616), ut2d (stock with TF_GLM_DSCORES=0, the default decode share switched off), and ut1 (the previous tip
46c6ee229, one boot, already in the directory).

THE RULES ARE FIXED BY THE PARENT, WRITTEN BEFORE ANY ut2 ROW EXISTED, and quoted as given:
  U0 QUALIFIED: all four boots present with every cell, else the whole verdict is NOT DECIDED and names what is missing. Effect proof of the arms from the boots' own logs: rank
  0's line "dflash2: drafter from ... linears at N bits, X GiB on the device" is read from the first lines of the boot (queue101 stores it in LABEL-drafter.txt) and printed
  for every boot; the proof FAILS (verdict line "U0 ARM DID NOT TAKE EFFECT") when ut2s's X is not below 0.6 or when ut2a/ut2b/ut2d are not all equal to each other. Missing
  file = NOT DECIDED, not a pass. The amendment adds the DSCORES proof from LABEL-dscores.txt: the proof also FAILS when ut2d's file has no line containing
  "TF_GLM_DSCORES=0", or when ut2a, ut2b or ut2s has any line containing TF_GLM_DSCORES at all; a missing dscores file is NOT DECIDED.
  U1 TIP RUNG (descriptive, no verdict word beyond CLEAR flags): the ut2 group (ut2a, ut2b) against ut1, every cell, using s92.arm's per-cell lines against ref [ut1] plus
  s92.group for digests. A cell is CLEAR gain/loss only when BOTH ut2 boots lie beyond ut1's value in the same direction by more than the larger of 1.0% and that cell's own
  ut2a-vs-ut2b difference. Print counts of CLEAR gains/losses per cell group (prompt cells; decode at 1/2/4; decode at 6/8, as derive92.cell_group groups them) and the list
  of digest keys that differ between the ut2 group and ut1 (an empty list is the expected case: nothing may change an output byte).
  U2 DRAFT_SPLIT: ut2s against the ut2 group (ref [ut2a, ut2b]) with s92.arm's rule as it stands (CANDIDATE / NOT A CANDIDATE / NOT DECIDED). Print its per-cell lines.
  U3 DSCORES: ut2d against the ut2 group: attribution report (the share DSCORES gives is the negative of these cells), no verdict word; PLUS the long-context decode share =
  (ut2 group mean chain decode rate / ut2d chain decode rate) - 1 from chaindec, CLEAR gain when it exceeds both 1.0% and the ut2 group's own boot spread of chain decode
  rate, CLEAR loss when it is below -1.0% and its magnitude exceeds that spread (chaindec.group_line style spread), symmetric as amended before any ut2 row existed.
  U4 LONG-CONTEXT DECODE report: chaindec per-boot means for ut1, ut2a, ut2b, ut2s, ut2d and the group lines (ut2 group, ut1).
  U5 CACHE BUDGET report: each boot's prompt_cache_budget_bytes from its facts row in rows.jsonl for ut1, ut2a, ut2b, ut2s, ut2d, and the percent each differs from ut1.
  FINAL line: "U-VERDICT: ..." that states, in one line each, U0 qualified or not, whether U2 reads CANDIDATE, and the U1 CLEAR counts. It never says "adopt": whether
  anything is carried is the owner's call. When the effect proof fails the line is "U-VERDICT: U0 ARM DID NOT TAKE EFFECT (<reasons>): the U1, U2 and U3 readings above
  are void" and carries neither the U2 word nor the counts, because a reading from an arm that did not take effect must not summarise.

READINGS THIS FILE MAKES WHERE THE RULES LEAVE A CHOICE (stated here, never silent):
  - U0's completeness covers ut1 as well as the four ut2 boots: U1, U4 and U5 compare against it, so a missing ut1 is named and the verdict is NOT DECIDED. The two proof
    files are required of the four ut2 boots only: ut1 ran in queue96, before they existed, and queue101 does not re-run it, so its files are printed when present and never
    affect U0.
  - "that cell's own ut2a-vs-ut2b difference" is (max - min) / mean of the cell's two boot values, score99.py's boot-spread measure; a max/min - 1 convention would move
    the bound by under 1% of itself.
  - A proof file that exists but holds MISSING (queue101's marker for a line that could not be found) is NOT DECIDED, like a missing file: no value is read from it.
  - U1's digest reading prints differing keys and one-side-only keys separately, so a report missing on one side is visible rather than silently equal.
  - The exit code is 0: this is a report (the rules name no failing clause), unlike score99's digest exit.
"""
import argparse
import importlib.util
import pathlib
import re
import statistics as st
import sys

_MODS = {}


def load(name):
    """scripts/queue-scores/<name>.py from the first parent that holds it (the walk score99.py and score100.py use), so a scratch copy still finds the real modules."""
    if name not in _MODS:
        for p in pathlib.Path(__file__).resolve().parents:
            f = p / "scripts/queue-scores" / f"{name}.py"
            if f.exists():
                spec = importlib.util.spec_from_file_location(name, f)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _MODS[name] = mod
                break
        else:
            raise SystemExit(f"score101: scripts/queue-scores/{name}.py not found above this file")
    return _MODS[name]


S91 = load("score91")  # rows(), boot(), group(), name(): the one owner of the row format
S92 = load("score92")  # METRICS, LIMIT, gain(), arm(): the cells and the PR rule, used as they stand
CD = load("chaindec")  # boot_rate(), group_line(): the long-context decode rate
D92 = load("derive92")  # cell_group(): PROMPT / D124 / D68

UT1 = "ut1"
UT2 = ("ut2a", "ut2b")  # the rung's own two boots; their difference is the noise floor U1 reads against
SPLIT = "ut2s"
DSC = "ut2d"
ALL = (UT1,) + UT2 + (SPLIT, DSC)
SPLIT_MAX = 0.6  # the split drafter must be below this many GiB (the stock three are equal to each other)
DRAFTER = re.compile(r"linears at \d+ bits, ([0-9]+(?:\.[0-9]+)?) GiB on the device")
DSCORES_OFF = "TF_GLM_DSCORES=0"


# ---------------------------------------------------------------- the effects' own proofs (U0)

def drafter_value(line):
    """The X of 'linears at N bits, X GiB on the device', or None when the line does not carry it."""
    m = DRAFTER.search(line or "")
    return float(m.group(1)) if m else None


def drafter(q, tag):
    """(value, line or reason) of one boot's drafter file; value is None when the file or the line is missing."""
    f = pathlib.Path(q) / f"{tag}-drafter.txt"
    if not f.exists():
        return None, "missing file " + f.name
    line = f.read_text(encoding="utf-8").strip()
    if not line or line == "MISSING":
        return None, "no drafter line in " + f.name
    v = drafter_value(line)
    return (v, line) if v is not None else (None, "unparsed " + f.name)


def dscores(q, tag):
    """(evidence lines, reason): the boot's dscores file lines that contain TF_GLM_DSCORES; ([], None) when it says NONE; (None, reason) when unreadable."""
    f = pathlib.Path(q) / f"{tag}-dscores.txt"
    if not f.exists():
        return None, "missing file " + f.name
    text = f.read_text(encoding="utf-8").strip()
    if not text or text == "MISSING":
        return None, "no dscores report in " + f.name
    return [l for l in text.splitlines() if "TF_GLM_DSCORES" in l], None


def completeness(q):
    """(labels with no rows, 'label:cell' of every cell a boot did not report) over all five boots."""
    missing, short = [], []
    for tag in ALL:
        v, _ = S91.boot(q, tag)
        if not v:
            missing.append(tag)
            continue
        short += [f"{tag}:{S91.name(m)}" for m in S92.METRICS if m not in v]
    return missing, short


def u0(q):
    """(lines, state, reason): QUALIFIED, ARM DID NOT TAKE EFFECT or NOT DECIDED, with the proofs of every boot printed."""
    out = ["== U0 qualified: the five boots (ut1 and the four ut2 boots) present with every score92 cell, then each arm's own effect proof"]
    missing, short = completeness(q)
    if missing or short:
        why = []
        if missing:
            why.append("no rows for " + ", ".join(missing))
        if short:
            why.append(f"{len(short)} cell(s) not reported: " + "; ".join(short[:8]) + (" ..." if len(short) > 8 else ""))
        out.append("U0: NOT DECIDED: " + "; ".join(why))
        return out, "NOT DECIDED", "; ".join(why)
    out.append(f"every cell of all {len(ALL)} boots: {len(S92.METRICS)} cell(s) each")
    dv, ds, unread = {}, {}, []
    for tag in ALL:
        dfile = pathlib.Path(q) / f"{tag}-drafter.txt"
        sfile = pathlib.Path(q) / f"{tag}-dscores.txt"
        v, line = drafter(q, tag)
        dv[tag] = v
        ev, why = dscores(q, tag)
        ds[tag] = ev
        if tag == UT1:
            # ut1 ran in queue96, before the proof files existed, and queue101 does not re-run it: its two files are information only, never a requirement.
            out.append(f"drafter {UT1}: " + (line if dfile.exists() else "not recorded (queue96 predates the proof files)"))
            out.append(f"dscores {UT1}: " + (("none" if ev == [] else why if why else " | ".join(ev)) if sfile.exists() else "not recorded (queue96 predates the proof files)"))
        else:
            out.append(f"drafter {tag}: {line}")
            out.append(f"dscores {tag}: " + ("none" if ev == [] else why if why else " | ".join(ev)))
        if v is None and tag != UT1:
            unread.append(f"{tag}: {line}")
        if ev is None and tag != UT1:
            unread.append(f"{tag}: {why}")
    if unread:
        out.append("U0: NOT DECIDED: a proof file is missing or carries no line: " + "; ".join(unread))
        return out, "NOT DECIDED", "a proof file is missing or carries no line: " + "; ".join(unread)
    out.append("U0 drafter GiB: " + ", ".join(f"{tag} {dv[tag]:.2f}" for tag in UT2 + (SPLIT, DSC) + ((UT1,) if dv.get(UT1) is not None else ())))
    fails = []
    if not dv[SPLIT] < SPLIT_MAX:
        fails.append(f"{SPLIT}'s drafter {dv[SPLIT]:.2f} GiB is not below {SPLIT_MAX}")
    if not dv[UT2[0]] == dv[UT2[1]] == dv[DSC]:
        fails.append(f"the stock drafter differs: ut2a {dv[UT2[0]]:.2f}, ut2b {dv[UT2[1]]:.2f}, ut2d {dv[DSC]:.2f} GiB")
    if not any(DSCORES_OFF in l for l in ds[DSC]):
        fails.append(f"{DSC} carries no line with {DSCORES_OFF}" + (f" (it has {ds[DSC][0]})" if ds[DSC] else " (it says NONE)"))
    for tag in UT2 + (SPLIT,):
        if ds[tag]:
            fails.append(f"{tag} is a default boot but carries {ds[tag][0]}")
    if fails:
        out.append("U0 ARM DID NOT TAKE EFFECT: " + "; ".join(fails))
        return out, "ARM DID NOT TAKE EFFECT", "; ".join(fails)
    out.append(f"U0: QUALIFIED: {SPLIT}'s drafter {dv[SPLIT]:.2f} GiB is below {SPLIT_MAX}, the stock three are equal at {dv[UT2[0]]:.2f} GiB, and only {DSC} carries {DSCORES_OFF}")
    return out, "QUALIFIED", f"drafter {dv[SPLIT]:.2f} GiB on the split arm, the stock three equal; only {DSC} carries {DSCORES_OFF}"


# ---------------------------------------------------------------- U1: the tip rung, descriptive

def spread(values):
    """A cell's ut2a-vs-ut2b difference as a fraction of their mean (score99.py's boot-spread measure)."""
    return (max(values) - min(values)) / st.mean(values)


def clear(metric, a, b, ref):
    """(kind, gaps, bound): CLEAR gain/loss only when BOTH ut2 boots lie beyond ut1's value in the same direction by more than the larger of score92's 1.0% limit and
    the cell's own ut2a-vs-ut2b difference; gaps are score92.gain() of each boot against ut1, positive faster."""
    gaps = [S92.gain(metric, a, ref), S92.gain(metric, b, ref)]
    bound = max(S92.LIMIT, spread([a, b]))
    if min(gaps) > bound:
        return "gain", gaps, bound
    if max(gaps) < -bound:
        return "loss", gaps, bound
    return None, gaps, bound


GROUPS = (("PROMPT", "prompt cells"), ("D124", "decode 1/2/4"), ("D68", "decode 6/8"))


def counts_line(counts):
    """The CLEAR counts, per cell group, in the one format the U1 line and the final line both use."""
    return ", ".join(f"{label} {counts[('gain', g)]} gain(s) / {counts[('loss', g)]} loss(es)" for g, label in GROUPS)


def u1(q):
    """(lines, counts): the ut2 group against ut1, s92.arm's per-cell lines with a CLEAR tag, the counts per cell group, and the digest keys that differ."""
    out = ["== U1 tip rung: the ut2 group (ut2a ut2b) against ut1, every cell; faster is positive, and a cell is CLEAR only when both boots lie beyond ut1 by more than the larger of 1.0% and their own difference",
           "note: ut1 ran in queue96, hours before these boots; a difference between boots of different sessions that is not larger than the ut2 group's own spread cannot be told from a change"]
    counts = {(k, g): 0 for k in ("gain", "loss") for g, _ in GROUPS}
    missing, v2, _ = S91.group([(q, UT2[0]), (q, UT2[1])])
    rmissing, v1, _ = S91.group([(q, UT1)])
    arm_lines, _ = S92.arm([(q, UT2[0]), (q, UT2[1])], [(q, UT1)])
    have = [m for m in S92.METRICS if len(v2.get(m, [])) == len(UT2) and len(v1.get(m, [])) == 1]
    if missing or rmissing or not have:
        out.append(f"U1: not read: no rows for {', '.join(missing + rmissing) if missing or rmissing else 'the cells'}")
        return out, counts
    if len(arm_lines) != len(have):
        out.append(f"U1: not read: s92.arm printed {len(arm_lines)} line(s) for {len(have)} cell(s)")
        return out, counts
    for m, line in zip(have, arm_lines):
        kind, gaps, bound = clear(m, v2[m][0], v2[m][1], v1[m][0])
        tag = (f"CLEAR {kind}" if kind else "no CLEAR") + f" (ut2a {gaps[0]:+.2%}, ut2b {gaps[1]:+.2%}, bound {bound:.2%})"
        if kind:
            counts[(kind, D92.cell_group(S91.name(m)))] += 1
        out.append(f"{line}  {tag}")
    out.append("CLEAR counts: " + counts_line(counts))
    _, _, a = S91.group([(q, UT2[0]), (q, UT2[1])])
    _, _, r = S91.group([(q, UT1)])
    both = set(a) & set(r)
    differ = sorted({k for k in both if len({*a[k], *r[k]}) != 1}, key=str)
    only = sorted(set(a) ^ set(r), key=str)
    out.append(f"digest keys differing between the ut2 group and ut1: {len(differ)}" + ("".join(f"\n  differs: {k}" for k in differ[:12]) if differ else " (nothing may change an output byte)"))
    out.append(f"digest keys reported on one side only: {len(only)}" + ("".join(f"\n  one side only: {k}" for k in only[:12]) if only else ""))
    return out, counts


# ---------------------------------------------------------------- U2: DRAFT_SPLIT, score92's rule as it stands

def u2(q):
    """(lines, verdict): ut2s against the ut2 group, passed through s92.arm unchanged."""
    lines, verdict = S92.arm([(q, SPLIT)], [(q, UT2[0]), (q, UT2[1])])
    out = [f"== U2 DRAFT_SPLIT: {SPLIT} (TF_GLM_DRAFT_SPLIT=1) against the ut2 group (ut2a ut2b); score92.py's PR rule as it stands, faster is positive"]
    out += lines if lines else [verdict]
    out.append(f"U2 DRAFT_SPLIT: {verdict}")
    return out, verdict


# ---------------------------------------------------------------- U3: DSCORES attribution, and the long-context share

def chain_rate(q, tag):
    """(turns, mean) of the boot's counted chain turns, or None."""
    r = CD.boot_rate([q], tag)
    return None if r is None else (r[0], r[1])


def u3(q):
    """(lines): ut2d (DSCORES off) against the ut2 group, no verdict word; and the long-context decode share, CLEAR only beyond both bounds."""
    lines, verdict = S92.arm([(q, DSC)], [(q, UT2[0]), (q, UT2[1])])
    out = [f"== U3 DSCORES: {DSC} (TF_GLM_DSCORES=0) against the ut2 group (ut2a ut2b); each cell is DSCORES switched off, so the share DSCORES gives is the negative of it"]
    out += lines if lines else [verdict]
    a, b, d = chain_rate(q, UT2[0]), chain_rate(q, UT2[1]), chain_rate(q, DSC)
    if a is None or b is None or d is None:
        out.append("long-context decode share: not read: no counted chain turn for " + ", ".join(t for t, r in ((UT2[0], a), (UT2[1], b), (DSC, d)) if r is None))
        return out
    mean = st.mean([a[1], b[1]])
    spread_ut2 = max(a[1], b[1]) / min(a[1], b[1]) - 1
    share = mean / d[1] - 1
    if share > S92.LIMIT and share > spread_ut2:
        tag = f"CLEAR gain (DSCORES faster: beyond both 1.0% and the ut2 group's {spread_ut2:.2%} spread)"
    elif share < -S92.LIMIT and -share > spread_ut2:
        tag = f"CLEAR loss (DSCORES slower: beyond both 1.0% and the ut2 group's {spread_ut2:.2%} spread)"
    else:
        tag = f"not CLEAR (needs more than 1.0% and more than the ut2 group's {spread_ut2:.2%} spread, in either direction)"
    out.append(f"long-context decode: ut2 group mean {mean:.2f} tok/s (boots {a[1]:.2f} {b[1]:.2f}, spread {spread_ut2:.2%}), {DSC} {d[1]:.2f} tok/s, share {share:+.2%}  {tag}")
    return out


# ---------------------------------------------------------------- U4: the long-context decode report

def u4(q):
    """(lines): chaindec's per-boot means for the five boots, then the group lines for the ut2 group and ut1."""
    out = ["== U4 long-context decode: chaindec.py's per-boot means over the resumed chain turns (a turn with a decode rate, a reply of 100+ tokens and more than 50,000 cached rows)"]
    means = {}
    for tag in ALL:
        r = CD.boot_rate([q], tag)
        if r is None:
            out.append(f"{tag:6s} no counted chain turn found")
            continue
        means[tag] = r[1]
        out.append(f"{tag:6s} {r[0]} resumed turns, mean {r[1]:7.2f} tok/s (min {r[2]:.2f}, max {r[3]:.2f}), context {r[4]} to {r[5]} rows")
    for name, tags in (("ut2", UT2), ("ut1", (UT1,))):
        got = [means[t] for t in tags if t in means]
        out.append(CD.group_line(name, got) if got else f"group {name}: no boot")
    return out


# ---------------------------------------------------------------- U5: the prompt-cache budget

def budget(q, tag):
    """The boot's prompt_cache_budget_bytes from its facts row (case 'boot'), or None."""
    for r in S91.rows(f"{q}/rows.jsonl"):
        if r.get("tag") == tag and r.get("case") == "boot":
            return (r.get("metrics") or {}).get("prompt_cache_budget_bytes")
    return None


def u5(q):
    """(lines): every boot's prompt_cache_budget_bytes and the percent it differs from ut1 (an upstream commit c896bfc0c caps the unified-memory budget)."""
    out = ["== U5 cache budget: each boot's prompt_cache_budget_bytes from its facts row, and the percent it differs from ut1"]
    base = budget(q, UT1)
    for tag in ALL:
        b = budget(q, tag)
        if b is None:
            out.append(f"{tag:6s} no facts row with prompt_cache_budget_bytes")
        elif base is None or tag == UT1:
            out.append(f"{tag:6s} {b} bytes" + ("" if base is None else " (the reference)"))
        else:
            out.append(f"{tag:6s} {b} bytes ({b / base - 1:+.2%} against ut1 {base})")
    if base is None:
        out.append("U5: ut1 has no facts row, so no boot's budget can be read against it")
    return out


# ---------------------------------------------------------------- report and verdict

def u2_word(verdict):
    """CANDIDATE, NOT A CANDIDATE or NOT DECIDED from s92.arm's verdict line."""
    if verdict.startswith("NOT A CANDIDATE"):
        return "NOT A CANDIDATE"
    if verdict.startswith("CANDIDATE"):
        return "CANDIDATE"
    return "NOT DECIDED"


def final_line(u0_state, u0_reason, u2v, counts):
    """The one line the brief asks for: U0's state, the U2 word and the U1 CLEAR counts; a failed effect proof voids the readings, so that line carries neither."""
    if u0_state == "NOT DECIDED":
        return f"U-VERDICT: NOT DECIDED: {u0_reason}"
    if u0_state == "ARM DID NOT TAKE EFFECT":
        return f"U-VERDICT: U0 ARM DID NOT TAKE EFFECT ({u0_reason}): the U1, U2 and U3 readings above are void"
    return f"U-VERDICT: U0 QUALIFIED; U2 {u2_word(u2v)}; U1 CLEAR: {counts_line(counts)}"


def report(q):
    """(lines, {U0, U2, CLEAR}): the whole report; the exit code is always 0 (this is a report, the rules name no failing clause)."""
    l0, u0_state, u0_reason = u0(q)
    l1, counts = u1(q)
    l2, u2v = u2(q)
    l3 = u3(q)
    l4 = u4(q)
    l5 = u5(q)
    lines = [f"== score101: q101 {q}"] + l0 + l1 + l2 + l3 + l4 + l5 + [final_line(u0_state, u0_reason, u2v, counts)]
    return lines, {"U0": u0_state, "U2": u2_word(u2v), "CLEAR": counts}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--q101", default="docs/audit-2026-11-12/queue-rows/queue92/f92-c", help="queue101's f92-c (default docs/audit-2026-11-12/queue-rows/queue92/f92-c)")
    ap.add_argument("--dir", dest="q101", help="alias of --q101, queue98's, queue99's and queue100's flag name")
    a = ap.parse_args(argv)
    lines, _ = report(a.q101)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
