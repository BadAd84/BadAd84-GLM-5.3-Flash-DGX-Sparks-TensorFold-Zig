#!/usr/bin/env python3
"""check-upstream-links.py: every patch in the series has a row in docs/UPSTREAM-LINKS.md, and every row a patch.

The repo's main accumulates levers as numbered patches; a lever also goes upstream as one branch a pull request. The
table is what ties the two together, and it is the place a retirement is recorded when upstream lands one. A patch with
no row is a lever nobody knows the upstream state of; a row with no patch is a retirement that was never finished.

Run: python scripts/check-upstream-links.py [--root REPO]
"""
import argparse
import pathlib
import re
import sys


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parents[1]))
    args = ap.parse_args(argv[1:])
    root = pathlib.Path(args.root)
    patches = sorted(p.name.split("-")[0] for p in (root / "patches" / "engine").glob("*.patch"))
    doc = root / "docs" / "UPSTREAM-LINKS.md"
    if not doc.exists():
        print(f"missing {doc}")
        return 1
    rows = re.findall(r"^\|\s*`(\d{4})`\s*\|", doc.read_text(encoding="utf-8"), re.M)
    problems = []
    for num in patches:
        if num not in rows:
            problems.append(f"NOROW {num}: a patch with no upstream link row")
    for num in rows:
        if num not in patches:
            problems.append(f"NOPATCH {num}: a row for a patch the series no longer has (a retirement to finish)")
    dupes = {n for n in rows if rows.count(n) > 1}
    for n in sorted(dupes):
        problems.append(f"DUPLICATE {n}: two rows for one patch")
    print(f"upstream links: {len(patches)} patches, {len(rows)} rows, {len(problems)} problems")
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
