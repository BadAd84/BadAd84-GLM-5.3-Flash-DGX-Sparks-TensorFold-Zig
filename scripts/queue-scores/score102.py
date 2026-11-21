#!/usr/bin/env python3
"""score102.py [--q102 DIR] [--q91 DIR] [--q99 DIR] [--q95 DIR] - queue102 (scripts/queues/queue102.sh): the 120k arms for TF_GLM_OVN_INDEX_SCHED with TF_GLM_OVN_POOLS32
(patch 0012, the DSA indexer's prompt scoring) and TF_GLM_OVN_ABSORB_VEC (its rows in patch 0020, its code in 0023), on the stack on the pin (image m130a).

Each DIR holds rows.jsonl, <label>/chain.jsonl and dec-<label>/{P,C,SP,SC}<clients>.jsonl in queue91's row layout, and --q102 also holds each unit's <label>-env.txt readback proof;
score91.py's own readers are imported below and nothing here re-parses that layout. --q102 is queue102's f102-c (default work/pp102/f102-c), --q91 queue91's f91-c,
--q95 queue95's f95-c, --q99 queue99's f99-c.

GROUPS. C, the control (KNOBS=prod, no XENV): lc1 lc2. S, the indexer's prompt-scoring pair: ls1 ls2. V, the vector loads: lv1 lv2. A group's value for a cell is the mean of its
boots. A cell is exactly score91's: the cold first token at 8k, 32k and 120k (a row the instrument flagged NOTCOLD is left out of it - score91's rule, inherited, not re-made
here), the mean first token of the growing conversation's turns 2 to 8, and the aggregate tokens a second of greedy and of sampled prose and code at 1, 2, 4, 6 and 8 clients.

THE RULES BELOW ARE FIXED BY THE PARENT, WRITTEN BEFORE ANY ROW EXISTED, and quoted as given:
  L0 QUALIFIED: each unit's readback proof present and one image id; a unit without it is VOID.
  L1 DIGESTS: every reply digest of S and V equals the control's, as score91 reads them; a difference FAILS the arm and the program exits 1.
  L2 LONG-PROMPT GAIN for each arm: the cells are cold first token at 8k / 32k / 120k and the mean first token of the conversation's turns 2 to 8; change is the control's mean
     over the arm's mean minus one (positive = arm faster). GAINS when the 120k cold change is at least +0.5% and both of the arm's boots beat both control boots at 120k.
  L3 DECODE COST: the 12 cells at 1, 2 and 4 clients; an arm CARRIES A LOSS when the mean of its 12 changes is at most -0.5% with at least 9 negative, CLEAN at or above -0.3%,
     else UNCLEAR.
  L4 VERDICT: S: RETIRE (no L2 gain) | KEEP, SPLIT NEXT (gain; run the two knobs apart) | NOT DECIDED. V: RETIRE | BUILD THE PROMPT-ONLY GATE (gain and L3 loss) | PROMOTION
     CANDIDATE, FIVE LEVELS NEXT (gain and L3 clean) | NOT DECIDED. A L1 difference overrides both and exits 1.
Printed as information only, and never changing a verdict: the 6 and 8 client cells, and the 120k cold first token of every other boot of the same image the given directories
hold (queue91's mn1 mn2, queue95's mn3, queue99's ca1 ca2), with "skipped: DIR absent" for each directory that is not there. A missing boot is NOT DECIDED, never a pass.

WHERE THE RULES LEAVE A CHOICE, THIS FILE MAKES IT HERE:
  - "one image id" is read twice: on a unit's three rank lines (one rank on another image voids the unit) and across the six units (a unit whose image is not the one the other
    units ran voids that unit), so a box that drifted between boots cannot hand its arm a gain.
  - a unit's proof must carry exactly the three variables its arm's XENV names, unset where XENV does not name one: a proof that shows something else is evidence the boot was not
    the boot the rules name, so the unit is VOID.
  - L3's change is the arm's mean over the control's mean minus one, so negative is slower - the direction its own -0.5% and -0.3% thresholds are written in. L2's is the
    control's over the arm's, as the rule states, so positive is faster on both.
  - "a L1 difference overrides both" is applied literally: one arm's differing digest sets BOTH verdicts to NOT DECIDED and the program exits 1, with L2's and L3's numbers still
    printed above it as information.
  - V's RETIRE reads the L2 gain alone: an arm with no gain retires even when its decode cells are NOT DECIDED, because the gain is the thing the arm is for. Every reading that
    needs a decode verdict (the gate, the promotion) is NOT DECIDED when L3 is.
  - a limit is inclusive, and a mean cannot be made to land on one exactly in doubles: the nearest double to -0.5% can sit 1e-17 either side, so the comparisons allow EPS.
"""
import argparse
import collections
import importlib.util
import pathlib
import re
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
            raise SystemExit("score102: scripts/queue-scores/score91.py not found above this file")
    return _S91


SIZES = s91().SIZES
KINDS = s91().KINDS
LEVELS = s91().LEVELS
GAIN = 0.005  # L2: the 120k cold change at or above this is the gain the arm needs
DEC_LEVELS = (1, 2, 4)  # L3: the 12 decode cells
DEC_LIMIT = 0.005  # L3: the arm carries the loss at or below this mean change
DEC_CLEAN = 0.003  # L3: the arm is clean at or above minus this mean change
DEC_NEG = 9  # L3: and with at least this many of the 12 changes negative
EPS = 1e-9  # a value exactly at a limit is at it, not past it: the nearest double to a limit can sit 1e-17 either side
L2_CELLS = [("cold", 8000), ("cold", 32000), ("cold", 120000), ("warm",)]
GAIN_CELL = ("cold", 120000)  # L2: the cell the gain is read on and the one the four boots are ordered on
DEC_CELLS = [("dec", k, n) for k, _ in KINDS for n in DEC_LEVELS]
INFO_CELLS = [("dec", k, n) for k, _ in KINDS for n in (6, 8)]  # information only
CONTROL = ("lc1", "lc2")
ARMS = (("S", ("ls1", "ls2"), "TF_GLM_OVN_INDEX_SCHED=1 and TF_GLM_OVN_POOLS32=1"),
        ("V", ("lv1", "lv2"), "TF_GLM_OVN_ABSORB_VEC=1"))
UNITS = ("lc1", "ls1", "lv1", "lv2", "ls2", "lc2")
OTHER = (("q91", "mn1 mn2"), ("q95", "mn3"), ("q99", "ca1 ca2"))  # information only: the image's other boots at 120k
VARS = ("TF_GLM_OVN_INDEX_SCHED", "TF_GLM_OVN_POOLS32", "TF_GLM_OVN_ABSORB_VEC")
WANT = {"lc": {}, "ls": {"TF_GLM_OVN_INDEX_SCHED": "1", "TF_GLM_OVN_POOLS32": "1"}, "lv": {"TF_GLM_OVN_ABSORB_VEC": "1"}}
PROOF = re.compile(r"^rank(\d) container=(\S+) image=(\S+) TF_GLM_OVN_INDEX_SCHED=(\S+) TF_GLM_OVN_POOLS32=(\S+) TF_GLM_OVN_ABSORB_VEC=(\S+)$")


def show(vals):
    """The three variables as one phrase, an unset one named unset."""
    return ", ".join(f"{n}={vals.get(n, 'unset')}" for n in VARS)


def proof(q102, label):
    """(image, variables, reason): one unit's readback proof as queue102.sh writes it; reason names why the unit is VOID."""
    f = pathlib.Path(q102) / f"{label}-env.txt"
    if not f.exists():
        return None, None, f"no readback proof ({f.name})"
    ranks = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        m = PROOF.match(line.strip())
        if m:
            ranks[int(m.group(1))] = (m.group(2), m.group(3), dict(zip(VARS, m.group(4, 5, 6))))
    if sorted(ranks) != [0, 1, 2]:
        return None, None, f"the proof carries rank(s) {', '.join(str(r) for r in sorted(ranks)) or 'none'}, not 0, 1 and 2"
    for r in (0, 1, 2):
        if ranks[r][0] != f"glm53-zig-r{r}":
            return None, None, f"rank {r}'s line names container {ranks[r][0]}, not glm53-zig-r{r}"
    ids = {ranks[r][1] for r in (0, 1, 2)}
    if len(ids) != 1:
        return None, None, f"the three ranks carry {len(ids)} image ids ({', '.join(sorted(ids))})"
    want = WANT[label[:2]]
    for r in (0, 1, 2):
        got = {n: v for n, v in ranks[r][2].items() if v != "unset"}
        if got != want:
            return None, None, f"rank {r} carries {show(got)} but the arm needs {show(want)}"
    return ids.pop(), {n: ranks[0][2][n] for n in VARS}, None


def short_cells(vals, boots, cells):
    """[(cell, boots that measured it, boots in the group)] of cells a group did not report on every boot: a cell read from fewer boots is NOT DECIDED."""
    return [(m, len(vals.get(m, [])), len(boots)) for m in cells if len(vals.get(m, [])) != len(boots)]


def name(m):
    return s91().name(m)


def labels(boots):
    return " ".join(label for _, label in boots)


# ---------------------------------------------------------------- L0 qualification

def l0(q102):
    """(lines, {label: image or None}, verdict): each unit's readback proof, its one image id, and the units that are VOID."""
    out = ["== L0 qualified: each unit's readback proof, its one image id, and the three variables its arm's XENV names"]
    state, ids, common = {}, {}, None
    for label in UNITS:
        image, _, why = proof(q102, label)
        state[label] = image
        out.append(f"{label}: " + (f"proof present, ranks 0, 1 and 2 on image {image}; {show(WANT[label[:2]])}" if image else f"VOID: {why}"))
        if image:
            ids[label] = image
    if ids:
        counts = collections.Counter(ids.values()).most_common()
        common = counts[0][0] if len(counts) == 1 or counts[0][1] > counts[1][1] else None
        if common is None:
            out.append(f"the units' proofs carry {len(counts)} image ids and no one of them on the most units: every unit is VOID")
            for label in ids:
                state[label] = None
        else:
            for label in ids:
                if ids[label] != common:
                    out.append(f"{label}: VOID: its proof's image {ids[label]} is not the image the other units ran ({common})")
                    state[label] = None
    void = [l for l in UNITS if not state[l]]
    if void:
        return out, state, f"L0 VOID: {', '.join(void)}"
    return out, state, f"L0 QUALIFIED: six proofs, one image id ({common}), and each unit's three variables exactly as its XENV names them"


# ---------------------------------------------------------------- L1 digests

def l1(q102, state):
    """(lines, {arm: word}): every reply digest of S and V against the control's, as score91's group() collects them."""
    out = ["== L1 digests: every reply digest of S and V against the control's (cold requests, every conversation turn, every decode cell and the 24 prompts)"]
    words = {}
    bad = [l for l in CONTROL if not state[l]]
    c_missing, _, cd = s91().group([(q102, l) for l in CONTROL])
    if bad or c_missing:
        parts = []
        if bad:
            parts.append(f"the control is VOID ({', '.join(bad)})")
        if c_missing:
            parts.append(f"no rows for {', '.join(c_missing)}")
        why = "; ".join(parts)
        for arm, arm_labels, _ in ARMS:
            words[arm] = "NOT DECIDED"
            out.append(f"{arm} ({labels([(q102, l) for l in arm_labels])}): NOT DECIDED: {why}")
        return out, words
    for arm, arm_labels, xenv in ARMS:
        bad = [l for l in arm_labels if not state[l]]
        if bad:
            words[arm] = "NOT DECIDED"
            out.append(f"{arm} ({' '.join(arm_labels)}, {xenv}): NOT DECIDED: VOID unit(s) {', '.join(bad)}")
            continue
        a_missing, _, ad = s91().group([(q102, l) for l in arm_labels])
        miss = c_missing + a_missing
        if miss:
            words[arm] = "NOT DECIDED"
            out.append(f"{arm} ({' '.join(arm_labels)}, {xenv}): NOT DECIDED: no rows for {', '.join(miss)}")
            continue
        boots = len(CONTROL) + len(arm_labels)
        keys = sorted(set(cd) | set(ad), key=str)
        holes = [k for k in keys if len(cd.get(k, [])) + len(ad.get(k, [])) != boots]
        only = sorted(set(cd) ^ set(ad), key=str)
        differ = sorted((k for k in set(cd) & set(ad) if len({*cd[k], *ad[k]}) != 1), key=str)
        out.append(f"{arm} ({' '.join(arm_labels)}, {xenv}): {len(keys)} digest key(s) over {boots} boots, {len(holes)} missing a boot's report, {len(only)} on one side only, {len(differ)} differing")
        for k in (holes + only + differ)[:8]:
            out.append(f"  {'missing' if k in holes else 'one side only' if k in only else 'differs'}: {k}")
        if holes or only:
            words[arm] = "NOT DECIDED"
            out.append(f"{arm}: NOT DECIDED: a report is missing (never a pass)")
        elif differ:
            words[arm] = "DIFFERS"
            out.append(f"{arm}: DIFFERS at {len(differ)} key(s)")
        else:
            words[arm] = "EQUAL"
            out.append(f"{arm}: EQUAL to the control at every key")
    return out, words


# ---------------------------------------------------------------- L2 long-prompt gain

def l2(q102, state, arm, arm_labels, xenv):
    """(lines, word): one arm's four long-prompt cells against the control, and its 120k ordering against the two control boots."""
    out = [f"== L2 long-prompt gain, {arm} ({' '.join(arm_labels)}, {xenv}) against the control ({' '.join(CONTROL)}); change is the control's mean over the arm's mean minus one, so positive is the arm faster"]
    bad = [l for l in CONTROL + arm_labels if not state[l]]
    if bad:
        out.append(f"{arm}: NOT DECIDED: VOID unit(s) {', '.join(bad)}")
        return out, "NOT DECIDED"
    c_missing, cv, _ = s91().group([(q102, l) for l in CONTROL])
    a_missing, av, _ = s91().group([(q102, l) for l in arm_labels])
    miss = c_missing + a_missing
    if miss:
        out.append(f"{arm}: NOT DECIDED: no rows for {', '.join(miss)}")
        return out, "NOT DECIDED"
    short = short_cells(cv, CONTROL, L2_CELLS) + short_cells(av, arm_labels, L2_CELLS)
    if short:
        out.append(f"{arm}: NOT DECIDED: {len(short)} cell(s) missing a boot's report: " + "; ".join(f"{name(m)} ({x} of {y} boots)" for m, x, y in short[:6]))
        return out, "NOT DECIDED"
    changes = {m: st.mean(cv[m]) / st.mean(av[m]) - 1 for m in L2_CELLS}
    for m in L2_CELLS:
        out.append(f"{name(m)}: control {' '.join(f'{x:.1f}' for x in cv[m])} | {arm} {' '.join(f'{x:.1f}' for x in av[m])} | {changes[m]:+.2%} faster")
    g = changes[GAIN_CELL]
    beat = max(av[GAIN_CELL]) < min(cv[GAIN_CELL])
    out.append(f"{name(GAIN_CELL)}: change {g:+.2%} (the gain needs at least +{GAIN:.1%}); the arm's slower boot {max(av[GAIN_CELL]):.1f} ms against the control's faster {min(cv[GAIN_CELL]):.1f} ms: "
               + ("both of the arm's boots beat both control boots" if beat else "NOT both of the arm's boots beat both control boots"))
    word = "GAINS" if (g >= GAIN - EPS and beat) else "NO GAIN"
    out.append(f"{arm}: {word} (the 8k, 32k and warm cells above are information; the rule reads the 120k change and the four boots' order)")
    return out, word


# ---------------------------------------------------------------- L3 decode cost

def l3(q102, state, arm, arm_labels, xenv):
    """(lines, word): one arm's 12 decode changes at 1, 2 and 4 clients against the control."""
    out = [f"== L3 decode cost, {arm} ({' '.join(arm_labels)}, {xenv}) against the control ({' '.join(CONTROL)}); change is the arm's mean over the control's mean minus one, so negative is slower"]
    bad = [l for l in CONTROL + arm_labels if not state[l]]
    if bad:
        out.append(f"{arm}: NOT DECIDED: VOID unit(s) {', '.join(bad)}")
        return out, "NOT DECIDED"
    c_missing, cv, _ = s91().group([(q102, l) for l in CONTROL])
    a_missing, av, _ = s91().group([(q102, l) for l in arm_labels])
    miss = c_missing + a_missing
    if miss:
        out.append(f"{arm}: NOT DECIDED: no rows for {', '.join(miss)}")
        return out, "NOT DECIDED"
    short = short_cells(cv, CONTROL, DEC_CELLS) + short_cells(av, arm_labels, DEC_CELLS)
    if short:
        out.append(f"{arm}: NOT DECIDED: {len(short)} decode cell(s) missing a boot's report: " + "; ".join(f"{name(m)} ({x} of {y} boots)" for m, x, y in short[:6]))
        return out, "NOT DECIDED"
    changes = [st.mean(av[m]) / st.mean(cv[m]) - 1 for m in DEC_CELLS]
    for m, c in zip(DEC_CELLS, changes):
        out.append(f"{name(m)}: control {' '.join(f'{x:.1f}' for x in cv[m])} | {arm} {' '.join(f'{x:.1f}' for x in av[m])} | {c:+.2%}")
    mean = st.mean(changes)
    neg = sum(1 for c in changes if c < 0)
    if mean <= -DEC_LIMIT + EPS and neg >= DEC_NEG:
        word = "CARRIES A LOSS"
    elif mean >= -DEC_CLEAN - EPS:
        word = "CLEAN"
    else:
        word = "UNCLEAR"
    out.append(f"{arm}: mean {mean:+.2%} of 12 cells, {neg} negative: {word}")
    return out, word


# ---------------------------------------------------------------- information only

def info(q102, q91, q95, q99, state):
    """(lines): the 6 and 8 client cells of each arm, and the 120k cold first token of the image's other boots. Never a verdict."""
    out = ["== information only (it never changes a verdict): the 6 and 8 client cells, and the image's other boots at 120k"]
    c_missing, cv, _ = s91().group([(q102, l) for l in CONTROL])
    if c_missing or any(not state[l] for l in CONTROL):
        out.append("6 and 8 clients: no control rows for that")
    else:
        for arm, arm_labels, _ in ARMS:
            a_missing, av, _ = s91().group([(q102, l) for l in arm_labels])
            if a_missing:
                out.append(f"6 and 8 clients, {arm}: no rows for {', '.join(a_missing)}")
                continue
            cells = [m for m in INFO_CELLS if len(cv.get(m, [])) == len(CONTROL) and len(av.get(m, [])) == len(arm_labels)]
            out.append(f"6 and 8 clients, {arm} ({' '.join(arm_labels)}): " + ("; ".join(f"{name(m)} {st.mean(av[m]) / st.mean(cv[m]) - 1:+.2%}" for m in cells) or "no cell on every boot"))
    for key, other_labels in OTHER:
        d = {"q91": q91, "q95": q95, "q99": q99}[key]
        if not pathlib.Path(d).is_dir():
            out.append(f"the image's other boots at 120k in {d}: skipped: DIR absent")
            continue
        parts = []
        for label in other_labels.split():
            v, _ = s91().boot(d, label)
            parts.append(f"{label} {v[('cold', 120000)]:.1f} ms" if ("cold", 120000) in v else f"{label} no rows")
        out.append(f"the image's other boots at 120k in {d}: " + "; ".join(parts))
    return out


# ---------------------------------------------------------------- L4 verdicts

def l4(l1w, l2w, l3w):
    """(lines, {arm: verdict}, failed): the two verdicts; a L1 difference overrides both and fails the run."""
    out = ["== L4 verdicts"]
    failed = any(w == "DIFFERS" for w in l1w.values())
    verdicts = {}
    for arm in ("S", "V"):
        if failed:
            verdicts[arm] = "NOT DECIDED"
            out.append(f"{arm}: NOT DECIDED: a L1 digest difference overrides both verdicts")
            continue
        gain, cost = l2w.get(arm, "NOT DECIDED"), l3w.get(arm, "NOT DECIDED")
        if arm == "S":
            verdict = "KEEP, SPLIT NEXT" if gain == "GAINS" else "RETIRE" if gain == "NO GAIN" else "NOT DECIDED"
        elif gain == "GAINS" and cost == "CARRIES A LOSS":
            verdict = "BUILD THE PROMPT-ONLY GATE"
        elif gain == "GAINS" and cost == "CLEAN":
            verdict = "PROMOTION CANDIDATE, FIVE LEVELS NEXT"
        elif gain == "NO GAIN":
            verdict = "RETIRE"
        else:
            verdict = "NOT DECIDED"
        verdicts[arm] = verdict
        out.append(f"{arm}: {verdict} (L2 {gain}" + ("" if arm == "S" else f", L3 {cost}") + ")")
    return out, verdicts, failed


# ---------------------------------------------------------------- report and exit code

def report(q102, q91, q95, q99):
    """(lines, {clause: verdicts}, failed): the whole report; failed when a L1 digest differs."""
    l0_lines, state, v0 = l0(q102)
    l1_lines, v1 = l1(q102, state)
    l2_lines, l3_lines, v2, v3 = [], [], {}, {}
    for arm, arm_labels, xenv in ARMS:
        lines, word = l2(q102, state, arm, arm_labels, xenv)
        l2_lines += lines
        v2[arm] = word
        lines, word = l3(q102, state, arm, arm_labels, xenv)
        l3_lines += lines
        v3[arm] = word
    l4_lines, v4, failed = l4(v1, v2, v3)
    lines = ([f"== score102: q102 {q102}, q91 {q91}, q95 {q95}, q99 {q99}"] + l0_lines + [v0] + l1_lines + l2_lines + l3_lines
             + info(q102, q91, q95, q99, state) + l4_lines + ["L4 VERDICT: " + "; ".join(f"{arm} {word}" for arm, word in v4.items())])
    return lines, {"L0": v0, "L1": v1, "L2": v2, "L3": v3, "L4": v4}, failed


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--q102", default="work/pp102/f102-c", help="queue102's f102-c (default work/pp102/f102-c)")
    ap.add_argument("--q91", default="work/pp91/f91-c", help="queue91's f91-c (default work/pp91/f91-c)")
    ap.add_argument("--q99", default="work/pp99/f99-c", help="queue99's f99-c (default work/pp99/f99-c)")
    ap.add_argument("--q95", default="work/pp95/f95-c", help="queue95's f95-c (default work/pp95/f95-c)")
    a = ap.parse_args(argv)
    lines, _, failed = report(a.q102, a.q91, a.q95, a.q99)
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
