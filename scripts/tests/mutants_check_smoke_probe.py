#!/usr/bin/env python3
"""mutants_check_smoke_probe.py CHECKER TEST - one-line mutants of scripts/tests/check_smoke_probe.py, each killed by a named test.

Every mutant is a single string replacement asserted to match its anchor exactly once, written to a scratch copy under work/ and run against the whole test file with
CHECK_SMOKE_PROBE pointing at the copy; the checker itself is never edited. The unmutated copy runs first and must pass, or the batch is void. A kill is a NAMED test FAILING by
assertion (unittest's `FAIL: test_...`), and the mutant's own `expect` test must be among the failures. The checker's sha256 is printed before and after and must be unchanged:

  python scripts/tests/mutants_check_smoke_probe.py scripts/tests/check_smoke_probe.py scripts/tests/test_check_smoke_probe.py
"""
import argparse
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
FAIL = re.compile(r"^FAIL: (\w+)")
ERROR = re.compile(r"^ERROR: (\w+)")
MUTANTS = [
    {"name": "seed-comparison-dropped", "old": "if sseed == useed and ssizes & usizes:", "new": "if ssizes & usizes:",
     "expect": "test_a_different_seed_with_the_same_sizes_is_fine"},
    {"name": "size-comparison-dropped", "old": "if sseed == useed and ssizes & usizes:", "new": "if sseed == useed:",
     "expect": "test_the_same_seed_with_no_common_size_is_fine"},
    {"name": "default-seed-wrong", "old": 'DEFAULT_SEED = "lc1"', "new": 'DEFAULT_SEED = "pf74"',
     "expect": "test_a_default_smoke_against_a_named_seed_is_fine"},
    {"name": "default-sizes-wrong", "old": 'DEFAULT_SIZES = "1000,8000,32000,120000"', "new": 'DEFAULT_SIZES = "1000"',
     "expect": "test_a_probe_without_flags_uses_the_probes_own_defaults"},
    {"name": "smoke-never-ends", "old": '            if re.match(r"\\}\\s*$", line):', "new": "            if False:",
     "expect": "test_a_shared_seed_and_size_is_found_with_both_line_numbers"},
    {"name": "probe-compared-with-itself", "old": "for un, (useed, usizes) in (p for p in probes if p[0] not in smoke):", "new": "for un, (useed, usizes) in probes:",
     "expect": "test_a_different_seed_with_the_same_sizes_is_fine"},
    {"name": "unit-probes-held-against-each-other", "old": "for sn, (sseed, ssizes) in (p for p in probes if p[0] in smoke):", "new": "for sn, (sseed, ssizes) in probes:",
     "expect": "test_two_unit_probes_that_share_a_seed_and_size_are_not_a_finding"},
    {"name": "comments-counted", "old": ' and not l.lstrip().startswith("#")', "new": "",
     "expect": "test_a_commented_probe_is_not_a_probe"},
    {"name": "allowlist-for-every-name", "old": "allowed = name in ALLOW", "new": "allowed = True",
     "expect": "test_the_same_text_under_another_name_still_fails"},
    {"name": "findings-do-not-count", "old": "bad += 0 if allowed else 1", "new": "bad += 0",
     "expect": "test_exit_one_and_a_FAIL_line_naming_the_file_and_both_lines"},
    {"name": "exit-always-zero", "old": "return 1 if bad else 0", "new": "return 0",
     "expect": "test_exit_one_and_a_FAIL_line_naming_the_file_and_both_lines"},
]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def run(test, checker, timeout=1800):
    env = dict(os.environ, CHECK_SMOKE_PROBE=str(checker))
    r = subprocess.run([sys.executable, str(test)], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=timeout)
    out = r.stdout + r.stderr
    failed = list(dict.fromkeys(m[1] for line in out.splitlines() if (m := FAIL.match(line))))
    errored = list(dict.fromkeys(m[1] for line in out.splitlines() if (m := ERROR.match(line))))
    return r.returncode, failed, errored, out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("checker")
    ap.add_argument("test")
    a = ap.parse_args(argv)
    checker, test = pathlib.Path(a.checker).resolve(), pathlib.Path(a.test).resolve()
    src = checker.read_text(encoding="utf-8")
    before = sha(checker)
    print(f"check_smoke_probe.py sha256 before the batch: {before}")
    (ROOT / "work").mkdir(exist_ok=True)
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutantschk-", dir=ROOT / "work"))
    try:
        control = scratch / "control.py"
        control.write_text(src, encoding="utf-8", newline="\n")
        rc, failed, errored, out = run(test, control)
        print(f"control (unmutated copy): rc {rc}, {len(failed)} failing test(s)")
        if rc != 0:
            print(out[-4000:])
            print("CONTROL FAILED: the batch is void, nothing above it proves anything")
            return 1
        rows, bad = [], 0
        for i, m in enumerate(MUTANTS, 1):
            n = src.count(m["old"])
            if n != 1:
                rows.append((i, m["name"], m["expect"], "-", "-", f"NOT RUN (anchor matched {n} times)"))
                bad += 1
                continue
            text = src.replace(m["old"], m["new"])
            path = scratch / f"m{i:02d}.py"
            try:
                compile(text, str(path), "exec")
            except SyntaxError as exc:
                rows.append((i, m["name"], m["expect"], "-", "-", f"NOT RUN (syntax: {exc})"))
                bad += 1
                continue
            path.write_text(text, encoding="utf-8", newline="\n")
            rc, failed, errored, out = run(test, path)
            hit = [t for t in failed if m["expect"] in t]
            killed = rc != 0 and bool(hit)
            verdict = "KILLED" if killed else "SURVIVED"
            if killed and errored:
                verdict = "KILLED (an unrelated ERROR ran beside it)"
            rows.append((i, m["name"], m["expect"], ",".join(hit) or "-", ",".join(errored) or "-", verdict))
            bad += 0 if killed else 1
            print(f"  mutant {i:02d} {m['name']}: {verdict} by {rows[-1][3]}")
        print(f"\n{'#':>3}  {'mutant':40} {'expected test':84} verdict")
        for i, name, expect, hit, errored, verdict in rows:
            print(f"{i:>3}  {name:40} {expect:84} {verdict}")
        after = sha(checker)
        print(f"\ncheck_smoke_probe.py sha256 after the batch:  {after}" + (" (unchanged)" if after == before else " (CHANGED: the batch edited the checker)"))
        print(f"\n{len(MUTANTS)} mutants, {len(MUTANTS) - bad} killed, {bad} not killed; control passed")
        return 0 if bad == 0 and after == before else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
