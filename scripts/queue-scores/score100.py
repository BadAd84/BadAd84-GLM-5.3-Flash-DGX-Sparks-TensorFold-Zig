#!/usr/bin/env python3
"""score100.py [--q100 DIR] - queue100 (scripts/queues/queue100.sh): the five-level reading of TF_GLM_REQUEST_STARTS=1 against the recipe as committed (KNOBS=prod), on the stack
on the pin (image m130a), on the cells queue95 and queue91 measured.

DIR holds rows.jsonl, <label>/chain.jsonl, dec-<label>/{P,C,SP,SC}<clients>.jsonl and dec-<label>/pp.jsonl in queue91's row format, as queue100's cells write them: --q100 is
queue100's f100-c (default work/pp100/f100-c). The queue's labels are score99's (ca1 ca2 the control, ce1 ce2 the change under test), so score99.py's own readers, clauses and
rules are imported below and their lines are printed unchanged; this file adds one clause, C5.

GROUPS. CA, the control, the recipe as committed: ca1 ca2. CE, the change under test: ce1 ce2. The queue boots them ABBA (ca1, ce1, ce2, ca2), so a box that drifts shows as a
ca/ce difference that reverses between the pairs. A group's value for a cell is the mean of its boots, as score91.py's readers compute it.

C5 THE RULE, FIXED BY THE PARENT AND WRITTEN BEFORE ANY ROW EXISTED, quoted as given:
  C5 ADOPTION READING for TF_GLM_REQUEST_STARTS=1 in scripts/env/prod.env, the fleet rule applied: ADOPT when C1 reads ACCEPTED (no cell, cold first token and decode at all five
  levels included, more than 1.0% slower than the control's mean, and one reply digest across the four boots) AND C4 reads EQUAL AND the growing conversation's warm turns (the C2
  'conversation turns 2+ first token' cell) are faster by at least 5.0% for CE than CA. HOLD BACK when C1 reads NOT ACCEPTED (name the cells and say which are inside the control's
  boots' range, as score99's own flag lines do) or C4 reads DIFFERS. NOT DECIDED when any clause that the reading needs is NOT DECIDED (a missing boot or cell), or when C1 and C4
  allow ADOPT but the warm-turn cell is below the 5.0% (then print `NOT WORTH A SWITCH: warm turns only X% faster` instead of ADOPT, and exit 0). Print one final line
  `C5 ADOPTION: <word>` plus the one-line reason. Exit code 1 only when C4 digests differ (inherit score99's rule); everything else exits 0.

PRECEDENCE, as the rule orders its sentences: a definite refusal (C1 NOT ACCEPTED or C4 DIFFERS) is HOLD BACK even when another clause is NOT DECIDED; then NOT DECIDED (a clause
the reading needs has no answer); then the warm turns decide ADOPT or NOT WORTH A SWITCH. The threshold is inclusive: a gain at exactly 5.0% adopts, a value at C1's 1.0% limit is
not over it (score99's own rule), and an exact 5.0% cannot be built by scaling in doubles anyway (the nearest doubles land either side), so this file's tests probe `enough(THRESHOLD)`
directly and bracket it with fixtures at 4.9% and 5.1%.
"""
import argparse
import importlib.util
import pathlib
import statistics as st
import sys

_S99 = None


def s99():
    """score99.py, whose rows(), group(), name(), over() and C1-C4 report are the one owner of queue100's rows and clauses (found above this file, so a scratch copy still finds it)."""
    global _S99
    if _S99 is None:
        for p in pathlib.Path(__file__).resolve().parents:
            f = p / "scripts/queue-scores/score99.py"
            if f.exists():
                spec = importlib.util.spec_from_file_location("score99", f)
                _S99 = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(_S99)
                break
        else:
            raise SystemExit("score100: scripts/queue-scores/score99.py not found above this file")
    return _S99


THRESHOLD = 0.050  # the warm turns must be at least this much faster for CE than CA; a gain at exactly this value adopts
WARM = ("warm",)  # score91.py's cell for the growing conversation's mean first token over turns 2 to 8


def warm_gain(cav, cev):
    """The fraction faster the warm turns are for CE than CA: 1 - CE mean / CA mean, each the mean of its group's boots; positive is faster."""
    ca = st.mean(cav[WARM])
    ce = st.mean(cev[WARM])
    return 1 - ce / ca


def enough(gain):
    """True when the warm-turn gain reaches the threshold. A gain at exactly the threshold adopts; a 5.0% ratio cannot be built by scaling in doubles (as score99's
    docstring notes for its 1.0% limit), so the tests probe this function at THRESHOLD and bracket it with 4.9% and 5.1% fixtures."""
    return gain >= THRESHOLD


def c1_state(v1):
    """'accepted', 'rejected' or 'undecided' from score99's own C1 verdict line."""
    if v1.startswith("C1 SYNC: ACCEPTED"):
        return "accepted"
    if v1.startswith("C1 SYNC: NOT ACCEPTED"):
        return "rejected"
    return "undecided"


def c4_state(v4):
    """'equal', 'differs' or 'undecided' from score99's per-arm C4 verdicts."""
    if any(v == "DIFFERS" for v in v4.values()):
        return "differs"
    if all(v == "EQUAL" for v in v4.values()):
        return "equal"
    return "undecided"


def flags(g):
    """[(cell, inside, line)]: the cells score99's C1 limit flags, CE against CA, with the range sentence C1 prints, so C5 can name them itself. It reads score99's own
    CELLS, over() and readers, and the tests check its count and names against score99's C1 verdict line on the same rows."""
    _, cav, _ = s99().load(g["CA"])
    _, cev, _ = s99().load(g["CE"])
    out = []
    for m in s99().CELLS:
        if len(cav.get(m, [])) != len(g["CA"]) or len(cev.get(m, [])) != len(g["CE"]):
            continue
        ca, ce = st.mean(cav[m]), st.mean(cev[m])
        if s99().over(s99().s91().slower(m, ce, ca)):
            inside = min(cav[m]) <= min(cev[m]) and max(cev[m]) <= max(cav[m])
            span = f"CE {min(cev[m]):.1f}..{max(cev[m]):.1f}" + (f" inside CA {min(cav[m]):.1f}..{max(cav[m]):.1f}" if inside else f", CA {min(cav[m]):.1f}..{max(cav[m]):.1f}")
            out.append((m, inside, f"{s99().name(m)}: {span}"))
    return out


def c5(g, v1, v4):
    """(lines, word, reason): the adoption reading, the parent's rule applied literally, in its own order: HOLD BACK on a definite refusal, then NOT DECIDED, then the warm turns."""
    out = [f"== C5 adoption: TF_GLM_REQUEST_STARTS=1 against the recipe; the gain read is C2's 'conversation turns 2+ first token' cell and the threshold is {THRESHOLD:.1%} faster for CE than CA"]
    s1, s4 = c1_state(v1), c4_state(v4)
    ca_missing, cav, _ = s99().load(g["CA"])
    ce_missing, cev, _ = s99().load(g["CE"])
    gain = None
    if g["CA"] and g["CE"] and len(cav.get(WARM, [])) == len(g["CA"]) and len(cev.get(WARM, [])) == len(g["CE"]):
        gain = warm_gain(cav, cev)
        out.append(f"warm turns: CA mean {st.mean(cav[WARM]):.1f} (boots {s99().boots_line(cav[WARM])}) | CE mean {st.mean(cev[WARM]):.1f} (boots {s99().boots_line(cev[WARM])}) | {gain:+.2%} faster for CE than CA")
    else:
        missing = [label for label in (ca_missing + ce_missing)]
        out.append(f"warm turns: NOT REPORTED on every boot of both groups" + (f" (no rows for {', '.join(missing)})" if missing else ""))
    fl = flags(g)
    for m, inside, line in fl:
        out.append(f"  over C1's limit: {line}" + ("  <- inside CA's boots' range" if inside else ""))
    if s1 == "rejected" or s4 == "differs":
        parts = []
        if s1 == "rejected":
            if fl:
                inside = sum(1 for _, i, _ in fl if i)
                names = "; ".join(s99().name(m) for m, _, _ in fl)
                parts.append(f"C1 not accepted: {len(fl)} cell(s) more than {s99().LIMIT:.0%} slower ({inside} inside CA's boots' range): {names}")
            else:
                parts.append(f"C1 not accepted: {v1}")
        if s4 == "differs":
            parts.append("C4 digests differ at " + ", ".join(a for a, v in v4.items() if v == "DIFFERS"))
        return out, "HOLD BACK", "; ".join(parts)
    if s1 == "undecided" or s4 == "undecided":
        parts = []
        if s1 == "undecided":
            parts.append(f"C1: {v1}")
        if s4 == "undecided":
            parts.append("C4: NOT DECIDED for " + ", ".join(a for a, v in v4.items() if v != "EQUAL"))
        return out, "NOT DECIDED", "; ".join(parts)
    if gain is None:
        return out, "NOT DECIDED", "the warm-turn cell is not reported on every boot of both groups"
    if enough(gain):
        return out, "ADOPT", f"warm turns {gain:.1%} faster for CE than CA, C1 accepted and C4 equal"
    return out, "NOT WORTH A SWITCH", f"warm turns only {gain:.1%} faster"


# ---------------------------------------------------------------- report and exit code

def report(q100):
    """(lines, {clause: verdicts}, failed): score100's header, score99's C1-C4 lines unchanged, then C5; failed when a C4 digest differs (score99's exit rule)."""
    lines99, v, failed = s99().report(q100)
    g = s99().groups(q100)
    l5, word, reason = c5(g, v["C1"], v["C4"])
    lines = [f"== score100: q100 {q100}"] + lines99[1:] + l5 + [f"C5 ADOPTION: {word}: {reason}"]
    return lines, {"C1": v["C1"], "C4": v["C4"], "C5": word}, failed


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--q100", default="work/pp100/f100-c", help="queue100's f100-c (default work/pp100/f100-c)")
    ap.add_argument("--dir", dest="q100", help="alias of --q100, queue98's and queue99's flag name")
    a = ap.parse_args(argv)
    lines, verdicts, failed = report(a.q100)
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
