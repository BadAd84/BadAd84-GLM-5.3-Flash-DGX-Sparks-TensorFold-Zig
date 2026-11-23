#!/usr/bin/env python3
"""check-env.py [--env-dir DIR] [--tree GITDIR:TREEISH] - the two environment files of the serve are consistent, and (with --tree) every setting is one the engine reads.

scripts/env/prod.env is the production environment: a `# --- runtime` section, then a `# --- recipe` section. scripts/env/dev.env is the development environment:
the same two sections, then a `# --- candidates` section. Rules, each a finding when broken:
  1. every line is blank, a # comment, a section marker or NAME=value (no space in the value); a section marker comes once, in order; prod.env has no candidates section
  2. a name appears once in a section; dev.env's candidates section may repeat a RECIPE name (an override: serve.sh applies the recipe, then
     the candidates, so the later -e is the value a KNOBS=dev boot runs), and nothing else repeats: not a runtime name, not a second line
     in one section
  3. dev.env's runtime and recipe sections are prod.env's, line for line (names, values and order): dev differs from production only by its candidates
  4. a candidate is a setting prod.env does not carry, or an override of a recipe line whose value differs; check-env-coverage.py refuses an
     override of a measured recipe line (a candidate upgrades an engine default, never silently rewrites a measured value: that is XENV's job)
  5. with --tree GITDIR:TREEISH (a git directory and a commit or tree in it, the tree the series makes): every name outside NCCL_* and HF_HUB_OFFLINE, which NCCL
     and the Hugging Face client read, appears as a quoted string "NAME" somewhere under zig/src of that tree, so a setting the engine no longer reads, or that
     a retired patch added, is found here and not at boot
Rule 5 reads text, not syntax: a quoted name in a comment line counts as read, and a name the engine builds from pieces (cuda.ovn.on("SOLO_TO_START") builds
TF_GLM_OVN_SOLO_TO_START) is found through its registry row, which every such setting has.
Exit 0 with no findings, 1 otherwise; one line a finding.
"""
import argparse
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=([^\s]*)$")
MARK = re.compile(r"^# --- (runtime|recipe|candidates)\s*$")
EXTERNAL = re.compile(r"^(NCCL_|HF_HUB_OFFLINE$)")


def parse(path, order):
    """{section: [(name, value, lineno)]} and the findings of rule 1 and 2 for one file."""
    out, bad, seen = {}, [], {}
    sec = None
    expect = list(order)
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        m = MARK.match(line)
        if m:
            if not expect or m.group(1) != expect[0]:
                bad.append(f"{path.name}:{n}: section '{m.group(1)}' out of order (expected {expect[0] if expect else 'none'})")
            else:
                expect.pop(0)
            sec = m.group(1)
            out.setdefault(sec, [])
            continue
        if not line or line.startswith("#"):
            continue
        line = re.split(r"\s#", line)[0].strip()
        m = LINE.match(line)
        if not m:
            bad.append(f"{path.name}:{n}: not NAME=value: {raw.strip()[:80]}")
            continue
        if sec is None:
            bad.append(f"{path.name}:{n}: a setting before the first section marker: {m.group(1)}")
            continue
        if m.group(1) in seen:
            prev_sec, prev = seen[m.group(1)]
            if prev_sec == sec:
                bad.append(f"{path.name}:{n}: {m.group(1)} again in the {sec} section (first at line {prev})")
            elif prev_sec != "recipe" or sec != "candidates":
                bad.append(f"{path.name}:{n}: {m.group(1)} again (first in {prev_sec} at line {prev}); only a candidates line may "
                           f"repeat a recipe name")
        seen[m.group(1)] = (sec, n)
        out[sec].append((m.group(1), m.group(2), n))
    for s in expect:
        bad.append(f"{path.name}: no '# --- {s}' section")
    return out, bad


def tree_has(gitdir, tree, name):
    r = subprocess.run(["git", "-C", gitdir, "grep", "-q", "-F", f'"{name}"', tree, "--", "zig/src"], capture_output=True)
    if r.returncode not in (0, 1):
        raise SystemExit(f"git grep in {gitdir}:{tree} failed: {r.stderr.decode('utf-8', 'replace')[:200]}")
    return r.returncode == 0


def check(env_dir, tree=None):
    findings = []
    prod, bad = parse(env_dir / "prod.env", ["runtime", "recipe"])
    findings += bad
    dev, bad = parse(env_dir / "dev.env", ["runtime", "recipe", "candidates"])
    findings += bad
    for s in ("runtime", "recipe"):
        a = [(n, v) for n, v, _ in prod.get(s, [])]
        b = [(n, v) for n, v, _ in dev.get(s, [])]
        if a != b:
            gone = [x for x in a if x not in b]
            extra = [x for x in b if x not in a]
            findings.append(f"dev.env's {s} section is not prod.env's: missing {gone[:4]}, extra {extra[:4]}" + ("" if set(a) != set(b) else ", same lines in another order"))
    prod_names = {n for s in prod.values() for n, _, _ in s}
    runtime_names = {n for n, _, _ in prod.get("runtime", [])}
    prod_value = {n: v for s in prod.values() for n, v, _ in s}
    for n, v, ln in dev.get("candidates", []):
        if n in runtime_names:
            findings.append(f"dev.env:{ln}: candidate {n} overrides a runtime setting; a runtime line is not a candidate")
        elif n in prod_names and prod_value.get(n) == v:
            findings.append(f"dev.env:{ln}: candidate {n}={v} repeats prod.env's value: an override must differ")
    if tree:
        gitdir, treeish = tree.rsplit(":", 1)
        names = sorted({n for f in (prod, dev) for s in f.values() for n, _, _ in s})
        for n in names:
            if EXTERNAL.match(n):
                continue
            if not tree_has(gitdir, treeish, n):
                findings.append(f"{n}: not read anywhere under zig/src of {treeish[:12]}")
    return findings


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--env-dir", default=str(HERE / "env"))
    ap.add_argument("--tree", default=None, help="GITDIR:TREEISH")
    a = ap.parse_args()
    f = check(pathlib.Path(a.env_dir), a.tree)
    for line in f:
        print(line)
    print(f"check-env: {'CLEAN' if not f else f'{len(f)} finding(s)'}")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
