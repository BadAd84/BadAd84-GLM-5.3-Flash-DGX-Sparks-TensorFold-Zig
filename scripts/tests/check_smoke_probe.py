#!/usr/bin/env python3
"""check_smoke_probe.py [FILE...] - a queue script's first-boot smoke must not send the cold prompts its units measure.

longctx.py probe sends the same prompts for the same --seed and --cold-sizes, so a smoke() probe that shares a seed and a size with a unit probe leaves that prompt's rows in the prompt
cache and the unit's first cold request on that boot is no cold first token (queue99's ca1 read 986 ms for an 8k prompt that takes about 4,000 ms; the instrument flagged it NOTCOLD).
For every FILE (default scripts/queues/queue*.sh) it reads the `longctx.py probe` lines inside smoke() and the ones outside it, with the probe's own defaults for a flag that is not
given (--seed lc1, --cold-sizes 1000,8000,32000,120000), and reports every smoke probe that shares a seed AND at least one size with a unit probe. Exit 1 when any is found.

ALLOW names a script that ran with the defect before this gate existed: it is reported and does not fail the gate. Run from the repo root:  python scripts/tests/check_smoke_probe.py
"""
import glob
import pathlib
import re
import sys

DEFAULT_SEED = "lc1"
DEFAULT_SIZES = "1000,8000,32000,120000"
ALLOW = {"queue99.sh": "ran with the shared probe seed before this gate existed; OVERNIGHT section 77 records it and score91 leaves its NOTCOLD row out of the cell's mean"}


def probe_of(line):
    """(seed, set of sizes) of one `longctx.py probe` line, with the probe's defaults for what it does not name."""
    seed = re.search(r"--seed\s+(\S+)", line)
    sizes = re.search(r"--cold-sizes\s+([0-9,]+)", line)
    return (seed.group(1) if seed else DEFAULT_SEED), {int(s) for s in (sizes.group(1) if sizes else DEFAULT_SIZES).split(",") if s}


def smoke_lines(lines):
    """The 1-based numbers of the lines inside smoke() { ... } (the function ends at the first line that is a lone closing brace)."""
    inside, out = False, set()
    for n, line in enumerate(lines, 1):
        if re.match(r"smoke\(\)\s*\{", line):
            inside = True
        if inside:
            out.add(n)
            if re.match(r"\}\s*$", line):
                inside = False
    return out


def findings(text):
    """[(smoke line number, unit line number, seed, shared sizes)] for one script's text."""
    lines = text.splitlines()
    smoke = smoke_lines(lines)
    probes = [(n, probe_of(l)) for n, l in enumerate(lines, 1) if "longctx.py probe" in l and not l.lstrip().startswith("#")]
    out = []
    for sn, (sseed, ssizes) in (p for p in probes if p[0] in smoke):
        for un, (useed, usizes) in (p for p in probes if p[0] not in smoke):
            if sseed == useed and ssizes & usizes:
                out.append((sn, un, sseed, sorted(ssizes & usizes)))
    return out


def main(argv):
    files = argv or sorted(glob.glob("scripts/queues/queue*.sh"))
    bad = 0
    for f in files:
        name = pathlib.Path(f).name
        found = findings(pathlib.Path(f).read_text(encoding="utf-8"))
        for sn, un, seed, sizes in found:
            allowed = name in ALLOW
            print(f"{'allowed' if allowed else 'FAIL'}: {f}:{sn} the smoke probe shares seed {seed} and sizes {sizes} with the unit probe at line {un}" + (f" ({ALLOW[name]})" if allowed else ""))
            bad += 0 if allowed else 1
        if not found:
            print(f"ok: {f}")
    print(f"{len(files)} script(s), {bad} finding(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
