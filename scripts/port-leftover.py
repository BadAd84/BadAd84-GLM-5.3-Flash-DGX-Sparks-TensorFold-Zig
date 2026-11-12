#!/usr/bin/env python3
"""port-leftover.py FORK_REPO BASE_REF FORK_REF OUR_TREE [--all] [--show FILE] - the fork's changes our port lacks.

patch-removals.py reads the port in one direction (the pin's lines a patch takes away). This is the other one. The
fork's own work is diff(BASE_REF -> FORK_REF), BASE_REF being the upstream commit the fork last merged. For every
file of that diff that our patch stack also touches (OUR_TREE differs from the pin there is not needed: the file
list comes from --files or defaults to every changed file our tree has), each hunk the fork changed is checked
against OUR_TREE:

  missing   code lines the fork added that our file does not contain
  kept      code lines the fork removed that our file still contains

A hunk with both is a place the fork rewrote and the port left as upstream wrote it. That is how 0007 took
cuda_prompt_pair.zig's mark rules and left ringsAgree at the pin's form, which let a paired step write past the
index rings. A hunk with only `missing` lines is usually an unported feature (a knob's code); it is listed too.

Default output: a line a file, files with rewritten-and-left hunks first. --show FILE prints that file's hunks
(suffix match). --all includes files our tree does not have. Blank lines and whole-line comments are not counted.
Run with the Git that can read FORK_REPO (on this workstation: Windows Python, so git.exe).
"""
import difflib
import os
import subprocess
import sys


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout


def blob(repo: str, ref: str, path: str) -> list[str]:
    try:
        return git(repo, "show", f"{ref}:{path}").splitlines()
    except subprocess.CalledProcessError:
        return []


def code(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith("//")


def main() -> int:
    args = sys.argv[1:]
    show = None
    every = "--all" in args
    if every:
        args.remove("--all")
    if "--show" in args:
        k = args.index("--show")
        show = args[k + 1]
        del args[k:k + 2]
    repo, base, fork, ours = args[:4]
    names = [n for n in git(repo, "diff", "--name-only", base, fork, "--", "zig").splitlines() if n.endswith((".zig", ".cu", ".cuh"))]
    rows = []
    for rel in names:
        op = os.path.join(ours, rel)
        if not os.path.exists(op):
            if every:
                rows.append((0, 0, 0, 0, rel + " (not in our tree)", []))
            continue
        with open(op, encoding="utf-8", errors="replace", newline="") as f:
            our = {line.rstrip("\r\n").strip() for line in f}
        b, fk = blob(repo, base, rel), blob(repo, fork, rel)
        sm = difflib.SequenceMatcher(None, b, fk, autojunk=False)
        hunks = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            missing = [x for x in fk[j1:j2] if code(x) and x.strip() not in our]
            kept = [x for x in b[i1:i2] if code(x) and x.strip() in our and x not in fk[j1:j2]]
            if missing or kept:
                hunks.append((j1 + 1, missing, kept))
        if not hunks:
            continue
        both = sum(1 for _, m, k in hunks if m and k)
        rows.append((both, sum(len(m) for _, m, _ in hunks), sum(len(k) for _, _, k in hunks), len(hunks), rel, hunks))
    rows.sort(key=lambda r: (-r[0], -r[1], r[4]))
    if show is None:
        for both, m, k, n, rel, _ in rows:
            print(f"{rel}: rewritten-and-left hunks {both}, hunks {n}, missing lines {m}, kept lines {k}")
        print(f"TOTAL files {len(rows)}, rewritten-and-left hunks {sum(r[0] for r in rows)}, missing lines {sum(r[1] for r in rows)}, kept lines {sum(r[2] for r in rows)}")
        return 0
    for _, _, _, _, rel, hunks in rows:
        if not rel.endswith(show):
            continue
        for at, missing, kept in hunks:
            kind = "REWRITTEN-AND-LEFT" if missing and kept else ("missing" if missing else "kept")
            print(f"--- {rel}:{at} (fork line) {kind}")
            for x in kept:
                print(f"  ours still has | {x}")
            for x in missing:
                print(f"  fork adds      | {x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
