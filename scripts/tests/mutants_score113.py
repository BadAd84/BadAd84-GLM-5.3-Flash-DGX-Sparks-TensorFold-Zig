#!/usr/bin/env python3
"""mutants_score113.py SCORER TEST - one-line mutants of scripts/queue-scores/score113.py, each killed by a named test.

Every mutant is a single string replacement asserted to match its anchor exactly once, written to a scratch copy under work/ and run against the whole
test file with SCORE113 pointing at the copy; the scorer itself is never edited. The unmutated copy runs first and must pass, or the batch is void. A
kill is a NAMED test FAILING by assertion (unittest's `FAIL: test_...`), and the mutant's own `expect` test must be among the failures: a mutant that
dies of an unrelated error or on some other test is reported and fails the batch. Run from the top-level shell:

  python scripts/tests/mutants_score113.py scripts/queue-scores/score113.py scripts/tests/test_score113.py
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
FAIL = re.compile(r"^FAIL: (\w+)")
ERROR = re.compile(r"^ERROR: (\w+)")
MUTANTS = [
    # the decode limit, its sign and its inclusive boundary
    {"name": "dec-limit-to-2pct", "old": "LIMIT = 0.010", "new": "LIMIT = 0.020",
     "expect": "test_one_cell_over_the_limit_holds_that_arm_and_the_bundle"},
    {"name": "dec-limit-not-inclusive", "old": "ch > LIMIT + EPS", "new": "ch > LIMIT - EPS",
     "expect": "test_the_limit_is_inclusive"},
    {"name": "ratio-args-swapped", "old": "changes[cell] = slower(cell, a, c)", "new": "changes[cell] = slower(cell, c, a)",
     "expect": "test_one_cell_over_the_limit_holds_that_arm_and_the_bundle"},
    # the cold bar, its sign, its mean and the HOLD branch under it
    {"name": "cold-bar-to-zero", "old": "BAR = 0.010", "new": "BAR = 0.000",
     "expect": "test_a_positive_cold_mean_under_the_bar_holds"},
    {"name": "cold-bar-sign", "old": "cold_mean <= -BAR + EPS", "new": "cold_mean >= -BAR + EPS",
     "expect": "test_both_arms_adopt_when_cold_is_over_the_bar_and_no_cell_is_slower"},
    {"name": "cold-mean-to-sum", "old": 'cold_mean = st.mean(changes[("cold", s)] for s in COLD)',
     "new": 'cold_mean = sum(changes[("cold", s)] for s in COLD)', "expect": "test_a_positive_cold_mean_under_the_bar_holds"},
    {"name": "hold-under-bar-rejects", "old": '        elif cold_mean < -EPS:\n            verdict = "HOLD"', "new": '        elif False:\n            verdict = "HOLD"',
     "expect": "test_a_positive_cold_mean_under_the_bar_holds"},
    {"name": "not-positive-not-reject", "old": '            verdict = "REJECT"', "new": '            verdict = "HOLD"',
     "expect": "test_a_cold_mean_that_is_not_positive_rejects"},
    # the arms, the bundle and the cells read
    {"name": "bundle-adopts-on-either", "old": "all(a[\"verdict\"] == \"ADOPT\" for a in arms.values())",
     "new": "any(a[\"verdict\"] == \"ADOPT\" for a in arms.values())", "expect": "test_the_bundle_needs_both_arms"},
    {"name": "arms-share-the-t-boots", "old": "ARMS = {\"T\": (\"t1\", \"t2\", \"t3\", \"t4\"), \"X\": (\"x1\", \"x2\", \"x3\", \"x4\")}",
     "new": "ARMS = {\"T\": (\"t1\", \"t2\", \"t3\", \"t4\"), \"X\": (\"t1\", \"t2\", \"t3\", \"t4\")}", "expect": "test_the_bundle_needs_both_arms"},
    {"name": "levels-drop-8", "old": "LEVELS = (4, 8)", "new": "LEVELS = (4,)", "expect": "test_every_cell_is_read_at_both_levels"},
    {"name": "cold-drop-32k", "old": "COLD = (8000, 32000)", "new": "COLD = (8000,)", "expect": "test_every_cell_is_read_at_both_levels"},
    # the digests, the missing boot and the exit code
    {"name": "digest-threshold", "old": "if len(uniq) != 1 or None in uniq:", "new": "if len(uniq) > 2 or None in uniq:",
     "expect": "test_a_different_digest_overrides_and_exits_one"},
    {"name": "cold-digest-first-rep-only", "old": '        return tuple(dig[("cold", cell[1], r)] for r in reps)',
     "new": '        return tuple([dig[("cold", cell[1], 0)]])', "expect": "test_a_cold_digest_difference_exits_one"},
    {"name": "digest-override-off", "old": "        if differ:\n            verdict = \"NOT DECIDED (digests)\"",
     "new": "        if False:\n            verdict = \"NOT DECIDED (digests)\"", "expect": "test_a_different_digest_overrides_and_exits_one"},
    {"name": "missing-not-decided-off", "old": '                "bundle": "Q5 BUNDLE: NOT DECIDED: boot(s) "', "new": '                "bundle": "Q5 BUNDLE: ADOPTED: boot(s) "',
     "expect": "test_a_missing_boot_is_not_decided"},
    {"name": "exit-always-zero", "old": '"rc": 1 if differ else 0', "new": '"rc": 0', "expect": "test_a_different_digest_overrides_and_exits_one"},
]


def run(test, scorer, timeout=1800):
    env = dict(os.environ, SCORE113=str(scorer))
    r = subprocess.run([sys.executable, str(test)], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=timeout)
    out = r.stdout + r.stderr
    failed = list(dict.fromkeys(m[1] for line in out.splitlines() if (m := FAIL.match(line))))
    errored = list(dict.fromkeys(m[1] for line in out.splitlines() if (m := ERROR.match(line))))
    return r.returncode, failed, errored, out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("scorer")
    ap.add_argument("test")
    a = ap.parse_args(argv)
    scorer, test = pathlib.Path(a.scorer).resolve(), pathlib.Path(a.test).resolve()
    src = scorer.read_text(encoding="utf-8")
    (ROOT / "work").mkdir(exist_ok=True)
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutants113-", dir=ROOT / "work"))
    try:
        control = scratch / "control.py"
        control.write_text(src, encoding="utf-8", newline="\n")
        rc, failed, errored, out = run(test, control)
        print(f"control (unmutated copy): rc {rc}, {len(failed)} failing test(s)")
        if rc != 0:
            print(out[-6000:])
            print("CONTROL FAILED: the batch is void, nothing above it proves anything")
            return 1
        rows, bad = [], 0
        for i, m in enumerate(MUTANTS, 1):
            n = src.count(m["old"])
            if n != 1:
                rows.append((i, m["name"], m["expect"], "-", "-", f"NOT RUN (anchor matched {n} times)"))
                bad += 1
                print(f"  mutant {i:02d} {m['name']}: NOT RUN (anchor matched {n} times)")
                continue
            text = src.replace(m["old"], m["new"])
            path = scratch / f"m{i:02d}.py"
            try:
                compile(text, str(path), "exec")
            except SyntaxError as exc:
                rows.append((i, m["name"], m["expect"], "-", "-", f"NOT RUN (syntax: {exc})"))
                bad += 1
                print(f"  mutant {i:02d} {m['name']}: NOT RUN (syntax)")
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
        print(f"\n{'#':>3}  {'mutant':28} {'expected test':62} {'failing tests':44} {'errors':16} verdict")
        for i, name, expect, hit, errored, verdict in rows:
            print(f"{i:>3}  {name:28} {expect:62} {hit:44} {errored:16} {verdict}")
        print(f"\n{len(MUTANTS)} mutants, {len(MUTANTS) - bad} killed, {bad} not killed; control passed")
        return 0 if bad == 0 else 1
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
