#!/usr/bin/env python3
"""catalog-check.py --base PIN_TREE [--fix] TREE... - every kernel an arm's build catalog adds has its source.

zig/build/cuda_kernels.zig lists `.{ .name = "x", ... [.src = "y"] }`; the build opens kernels/cuda/<src or name>.cu
for most of them. An arm tree cut from the middle of the patch stack can name a kernel a later patch adds, and its
image build then fails on the missing file. The pin's own catalog has entries this rule does not resolve (they build
from other directories), so those are the baseline: only an entry the pin does not have and whose source is absent
is reported. --fix deletes those catalog lines. Exit 1 if any are reported and not fixed.
"""
import os
import re
import sys


def entries(tree: str):
    """(line index, name, source exists) for each catalog entry, and the file's lines."""
    cat = os.path.join(tree, "zig/build/cuda_kernels.zig")
    lines = open(cat, encoding="utf-8", newline="").read().split("\n")
    out = []
    for i, line in enumerate(lines):
        m = re.search(r'\.name = "([A-Za-z0-9_]+)"', line)
        if not m:
            continue
        s = re.search(r'\.src = "([A-Za-z0-9_]+)"', line)
        stem = s.group(1) if s else m.group(1)
        out.append((i, m.group(1), os.path.exists(os.path.join(tree, "zig/kernels/cuda", stem + ".cu"))))
    return cat, lines, out


def main() -> int:
    args = sys.argv[1:]
    fix = "--fix" in args
    base = args[args.index("--base") + 1]
    trees = [a for i, a in enumerate(args) if a not in ("--fix", "--base") and (i == 0 or args[i - 1] != "--base")]
    known = {name for _, name, _ in entries(base)[2]}
    bad = 0
    for tree in trees:
        cat, lines, ents = entries(tree)
        missing = [(i, name) for i, name, ok in ents if not ok and name not in known]
        note = ""
        if missing and fix:
            drop = {i for i, _ in missing}
            open(cat, "w", encoding="utf-8", newline="").write("\n".join(l for i, l in enumerate(lines) if i not in drop))
            note = " (removed)"
        elif missing:
            bad = 1
        print(f"{tree}: {len(ents)} catalog entries, {len(ents) - len(known & {n for _, n, _ in ents})} beyond the pin's, "
              f"without a source: {' '.join(n for _, n in missing) or 'none'}{note}")
    return bad


if __name__ == "__main__":
    sys.exit(main())
