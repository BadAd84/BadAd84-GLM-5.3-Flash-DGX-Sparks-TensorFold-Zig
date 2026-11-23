#!/usr/bin/env python3
"""check-dev-packages.py: every patch package is either in the dev union or excluded with a verdict.

The dev engine is the union of every beneficial candidate (scripts/dev-packages.list). A package that is neither listed
nor excluded is a lever nobody is testing together with the others; a listed package that has no directory is a manifest
typo; an exclusion without a verdict and a cell in it is a package parked by memory rather than by evidence.

Run: python scripts/check-dev-packages.py [--root REPO]
"""
import argparse
import pathlib
import re
import sys

VERDICT = re.compile(r"a trade|rejected|superseded|unmeasured|withdrawn", re.I)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parents[1]))
    args = ap.parse_args(argv[1:])
    root = pathlib.Path(args.root)
    packages_dir = root / "patches"
    manifest = root / "scripts" / "dev-packages.list"
    if not manifest.exists():
        print(f"missing {manifest}")
        return 1
    listed, excluded = [], {}
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            m = re.match(r"#\s*([a-z0-9][a-z0-9-]+)\s+(.*)", line)
            if m and (packages_dir / m.group(1)).is_dir():
                excluded[m.group(1)] = m.group(2)
            continue
        listed.append(line)
    problems = []
    for name in listed:
        if not (packages_dir / name).is_dir():
            problems.append(f"LISTED {name}: no such package under patches/")
    for d in sorted(p for p in packages_dir.iterdir() if p.is_dir()):
        name = d.name
        if name == "engine" or name in listed:
            continue
        why = excluded.get(name)
        if why is None:
            problems.append(f"UNLISTED {name}: neither in the dev union nor excluded with a verdict")
        elif not VERDICT.search(why):
            problems.append(f"EXCLUSION {name}: names no verdict ({why[:60]})")
    for name in excluded:
        if name in listed:
            problems.append(f"BOTH {name}: listed in the union and excluded")
    print(f"dev packages: {len(listed)} applied, {len(excluded)} excluded, {len(problems)} problems")
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
