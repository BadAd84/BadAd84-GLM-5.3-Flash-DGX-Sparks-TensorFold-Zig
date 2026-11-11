#!/usr/bin/env python3
"""patch-removals.py [--show N] PATCH... - the upstream lines each patch takes away.

A patch that only adds code cannot change what the pin already does. One that removes or rewrites pin lines
can, so this lists, per patch and file, the removed lines that the same file's hunks do not add back verbatim
(a moved line is not counted). Blank lines and comment-only lines are left out. With --show N it prints up to
N of those lines per file, for reading against the pin.
"""
import argparse
import os
import re


def files(path: str):
    """(file, removed lines, added lines) per file section of a unified diff."""
    name, minus, plus = None, [], []
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        m = re.match(r"^diff --git a/(\S+) b/", line)
        if m:
            if name:
                yield name, minus, plus
            name, minus, plus = m.group(1), [], []
        elif name and line.startswith("-") and not line.startswith("---"):
            minus.append(line[1:])
        elif name and line.startswith("+") and not line.startswith("+++"):
            plus.append(line[1:])
    if name:
        yield name, minus, plus


def code(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith(("//", "#", "*", "/*"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("patches", nargs="+")
    a = ap.parse_args()
    for path in a.patches:
        rows, total = [], 0
        for name, minus, plus in files(path):
            added = {p.strip() for p in plus}
            gone = [m for m in minus if code(m) and m.strip() not in added]
            if gone:
                rows.append((name, gone))
                total += len(gone)
        print(f"{os.path.basename(path)}: {total} pin lines removed or rewritten in {len(rows)} files")
        for name, gone in rows:
            print(f"    {len(gone):4d}  {name}")
            for g in gone[: a.show]:
                print(f"            - {g.strip()[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
