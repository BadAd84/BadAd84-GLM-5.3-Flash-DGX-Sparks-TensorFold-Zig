#!/usr/bin/env python3
"""mutants_score115.py SCORER TEST - one-line mutants of scripts/queue-scores/score115.py, each killed by a named test.

Every mutant is a single string replacement asserted to match its anchor exactly once, written to a scratch copy under work/ and run against the whole test
file with SCORE115 pointing at the copy; the scorer itself is never edited. The unmutated copy runs first and must pass, or the batch is void. A kill is a
NAMED test FAILING by assertion (unittest's `FAIL: test_...`), and the mutant's own `expect` test must be among the failures: a mutant that dies of an
unrelated error or on some other test is reported and fails the batch. The NOISE clause has three mutants of its own: one that removes it, one that moves
its threshold past the fixture's spread, and one that reads the arms' spread instead of the control's. Run from the top-level shell:

  python scripts/tests/mutants_score115.py scripts/queue-scores/score115.py scripts/tests/test_score115.py
"""
import argparse
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
    # the NOISE clause: present, thresholded at 5%, over the control's boots, its figure printed
    {"name": "noise-clause-off", "old": "if ctl_spread > NOISE + EPS:", "new": "if False:",
     "expect": "test_a_noisy_control_prints_noise_and_no_verdict"},
    {"name": "noise-threshold-25pct", "old": "NOISE = 0.050", "new": "NOISE = 0.250",
     "expect": "test_a_noisy_control_prints_noise_and_no_verdict"},
    {"name": "noise-spread-over-the-arm", "old": "    ctl_spread = spread(ctl)", "new": "    ctl_spread = spread([val[l] for l in ARMS[\"T\"]])",
     "expect": "test_the_control_spread_uses_the_control_boots_only"},
    {"name": "noise-drops-the-arm-spreads", "old": '"noise": ctl_spread, "arms": arms, "rc": 0,', "new": '"noise": ctl_spread, "arms": {}, "rc": 0,',
     "expect": "test_a_noisy_control_prints_noise_and_no_verdict"},
    {"name": "noise-figure-dropped", "old": 'f"Q5 BUNDLE: NOT DECIDED: NOISE: the control\'s six-boot spread is {ctl_spread:.2%}, above {NOISE:.0%}, so the cell has no verdict"',
     "new": '"Q5 BUNDLE: NOT DECIDED: NOISE"', "expect": "test_a_noisy_control_prints_noise_and_no_verdict"},
    # the 1% limit, its sign and its inclusive boundary
    {"name": "dec-limit-to-2pct", "old": "LIMIT = 0.010", "new": "LIMIT = 0.020", "expect": "test_a_cell_past_the_limit_holds_that_arm"},
    {"name": "hold-not-inclusive", "old": '"HOLD" if r["change"] > LIMIT + EPS else "ADOPT"', "new": '"HOLD" if r["change"] > LIMIT - EPS else "ADOPT"',
     "expect": "test_the_limit_is_inclusive"},
    {"name": "ratio-args-swapped", "old": "ch = 1 - a / c", "new": "ch = 1 - c / a", "expect": "test_a_cell_past_the_limit_holds_that_arm"},
    # the arms, the bundle, the cell's file
    {"name": "bundle-adopts-on-either", "old": "if all(a[\"verdict\"] == \"ADOPT\" for a in arms.values()):", "new": "if any(a[\"verdict\"] == \"ADOPT\" for a in arms.values()):",
     "expect": "test_the_arms_are_decided_independently"},
    {"name": "x-reads-the-control-boots", "old": 'ARMS = {"T": ("t1", "t2", "t3", "t4", "t5", "t6"), "X": ("x1", "x2", "x3", "x4", "x5", "x6")}',
     "new": 'ARMS = {"T": ("t1", "t2", "t3", "t4", "t5", "t6"), "X": ("c1", "c2", "c3", "c4", "c5", "c6")}', "expect": "test_the_arms_are_decided_independently"},
    {"name": "missing-cell-read-as-a-value", "old": "    if not rs:\n        return None, None", "new": "    if not rs:\n        return 0.0, (\"missing\",)",
     "expect": "test_a_missing_boot_is_not_decided"},
    # the digests, the missing boot and the exit code
    {"name": "digest-threshold", "old": "if len(uniq) != 1 or None in uniq:", "new": "if len(uniq) > 2 or None in uniq:",
     "expect": "test_a_different_digest_exits_one_and_dominates_the_verdict"},
    {"name": "digest-line-reads-as-noise", "old": '"bundle": "Q5 BUNDLE: DIGESTS DIFFER, exit 1: no verdict on either arm"}',
     "new": '"bundle": "Q5 BUNDLE: NOT DECIDED: NOISE"}', "expect": "test_a_different_digest_dominates_noise"},
    {"name": "missing-boot-adopts", "old": '"bundle": "Q5 BUNDLE: NOT DECIDED: boot(s) " + ", ".join(missing) + " have no cell"}',
     "new": '"bundle": "Q5 BUNDLE: ADOPTED" + ", ".join(missing)}', "expect": "test_a_missing_boot_is_not_decided"},
    {"name": "exit-always-zero", "old": '"noise": None, "arms": {}, "rc": 1,', "new": '"noise": None, "arms": {}, "rc": 0,',
     "expect": "test_a_different_digest_exits_one_and_dominates_the_verdict"},
]


def run(test, scorer, timeout=1800):
    env = dict(os.environ, SCORE115=str(scorer))
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
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutants115-", dir=ROOT / "work"))
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
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
