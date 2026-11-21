#!/usr/bin/env python3
"""mutants_score100.py SCORER TEST - one-line mutants of scripts/queue-scores/score100.py, each killed by a named test.

Every mutant is a single string replacement asserted to match its anchor exactly once, written to a scratch copy under work/ and run against the whole test file with
SCORE100 pointing at the copy; the scorer itself is never edited. The unmutated copy runs first and must pass, or the batch is void. A kill is a NAMED test FAILING by
assertion (unittest's `FAIL: test_...`), and the mutant's own `expect` test must be among the failures: a mutant that dies of an unrelated error or on some other test
is reported and fails the batch. The scorer's sha256 is printed before and after the batch and must be unchanged. Run from the top-level shell:

  python scripts/tests/mutants_score100.py scripts/queue-scores/score100.py scripts/tests/test_score100.py
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
    # the 5.0% threshold: its value, its direction, its inclusiveness
    {"name": "threshold-4pct", "old": "THRESHOLD = 0.050", "new": "THRESHOLD = 0.040",
     "expect": "test_not_worth_a_switch_at_four_point_nine_percent"},
    {"name": "threshold-6pct", "old": "THRESHOLD = 0.050", "new": "THRESHOLD = 0.060",
     "expect": "test_adopt_at_five_point_one_percent"},
    {"name": "enough-strict", "old": "    return gain >= THRESHOLD", "new": "    return gain > THRESHOLD",
     "expect": "test_the_threshold_is_five_percent_and_a_gain_at_it_adopts"},
    {"name": "enough-direction", "old": "    return gain >= THRESHOLD", "new": "    return gain <= THRESHOLD",
     "expect": "test_adopt_when_c1_accepted_c4_equal_and_the_warm_turns_are_well_faster"},
    # which cell is the warm-turn cell
    {"name": "warm-cell-cold-8k", "old": 'WARM = ("warm",)', "new": 'WARM = ("cold", 8000)',
     "expect": "test_adopt_when_c1_accepted_c4_equal_and_the_warm_turns_are_well_faster"},
    {"name": "warm-cell-cold-120k", "old": 'WARM = ("warm",)', "new": 'WARM = ("cold", 120000)',
     "expect": "test_adopt_at_five_point_one_percent"},
    # the sign of the gain, and which group is the reference
    {"name": "gain-sign", "old": "    return 1 - ce / ca", "new": "    return ce / ca - 1",
     "expect": "test_adopt_when_c1_accepted_c4_equal_and_the_warm_turns_are_well_faster"},
    {"name": "gain-reference-swap", "old": "    return 1 - ce / ca", "new": "    return 1 - ca / ce",
     "expect": "test_adopt_when_c1_accepted_c4_equal_and_the_warm_turns_are_well_faster"},
    # the group mean: a group's value is the mean of its boots, never its first boot
    {"name": "ca-first-boot-only", "old": "    ca = st.mean(cav[WARM])", "new": "    ca = cav[WARM][0]",
     "expect": "test_the_warm_gain_is_the_mean_of_both_control_boots"},
    {"name": "ce-first-boot-only", "old": "    ce = st.mean(cev[WARM])", "new": "    ce = cev[WARM][0]",
     "expect": "test_the_warm_gain_is_the_mean_of_both_policy_boots"},
    # the ADOPT condition, the HOLD BACK triggers and the NOT DECIDED propagation
    {"name": "adopt-ignores-warm", "old": "    if enough(gain):", "new": "    if True:",
     "expect": "test_not_worth_a_switch_at_four_point_nine_percent"},
    {"name": "holdback-or-to-and", "old": '    if s1 == "rejected" or s4 == "differs":', "new": '    if s1 == "rejected" and s4 == "differs":',
     "expect": "test_hold_back_on_a_cold_cell_one_and_a_half_percent_slower"},
    {"name": "holdback-ignores-c4", "old": '    if s1 == "rejected" or s4 == "differs":', "new": '    if s1 == "rejected":',
     "expect": "test_hold_back_when_c4_differs_even_with_c1_undecided"},
    {"name": "holdback-drops-c4-reason", "old": '        if s4 == "differs":', "new": "        if False:",
     "expect": "test_hold_back_on_a_digest_difference_exits_one"},
    {"name": "notdecided-or-to-and", "old": '    if s1 == "undecided" or s4 == "undecided":', "new": '    if s1 == "undecided" and s4 == "undecided":',
     "expect": "test_not_decided_when_c1_is_undecided_but_c4_is_equal"},
    {"name": "c1-undecided-accepted", "old": '    if v1.startswith("C1 SYNC: ACCEPTED"):', "new": '    if not v1.startswith("C1 SYNC: NOT ACCEPTED"):',
     "expect": "test_not_decided_when_c1_is_undecided_but_c4_is_equal"},
    {"name": "c1-rejected-mapping", "old": '    if v1.startswith("C1 SYNC: NOT ACCEPTED"):', "new": '    if v1.startswith("C1 SYNC: NEVER"):',
     "expect": "test_hold_back_on_a_cold_cell_one_and_a_half_percent_slower"},
    # the word the final line carries
    {"name": "adopt-word", "old": '        return out, "ADOPT", f"warm turns {gain:.1%} faster for CE than CA, C1 accepted and C4 equal"',
     "new": '        return out, "HOLD BACK", f"warm turns {gain:.1%} faster for CE than CA, C1 accepted and C4 equal"',
     "expect": "test_adopt_when_c1_accepted_c4_equal_and_the_warm_turns_are_well_faster"},
    # the exit code: zero unless C4 digests differ
    {"name": "exit-always-zero", "old": "    return 1 if failed else 0", "new": "    return 0",
     "expect": "test_the_exit_code_is_one_on_a_digest_difference"},
    {"name": "exit-inverted", "old": "    return 1 if failed else 0", "new": "    return 0 if failed else 1",
     "expect": "test_the_exit_code_is_one_on_a_digest_difference"},
    {"name": "exit-on-holdback", "old": "    return 1 if failed else 0", "new": '    return 1 if failed or verdicts["C5"] != "ADOPT" else 0',
     "expect": "test_the_exit_code_is_zero_on_hold_back"},
    {"name": "exit-on-not-worth", "old": "    return 1 if failed else 0", "new": '    return 1 if failed or verdicts["C5"] == "NOT WORTH A SWITCH" else 0',
     "expect": "test_the_exit_code_is_zero_on_not_worth_a_switch"},
    {"name": "exit-on-not-decided", "old": "    return 1 if failed else 0", "new": '    return 1 if failed or verdicts["C5"] == "NOT DECIDED" else 0',
     "expect": "test_the_exit_code_is_zero_when_a_clause_is_not_decided"},
]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def run(test, scorer, timeout=1800):
    env = dict(os.environ, SCORE100=str(scorer))
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
    before = sha(scorer)
    print(f"score100.py sha256 before the batch: {before}")
    (ROOT / "work").mkdir(exist_ok=True)
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutants100-", dir=ROOT / "work"))
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
            if rc == 0 or not hit:
                verdict = "SURVIVED"
            elif errored:
                verdict = "NOT A CLEAN KILL (an unrelated ERROR ran beside the expected failure)"
            else:
                verdict = "KILLED"
            killed = verdict == "KILLED"
            rows.append((i, m["name"], m["expect"], ",".join(hit) or "-", ",".join(errored) or "-", verdict))
            bad += 0 if killed else 1
            print(f"  mutant {i:02d} {m['name']}: {verdict} by {rows[-1][3]}")
        print(f"\n{'#':>3}  {'mutant':32} {'expected test':62} {'failing tests':62} {'errors':16} verdict")
        for i, name, expect, hit, errored, verdict in rows:
            print(f"{i:>3}  {name:32} {expect:62} {hit:62} {errored:16} {verdict}")
        after = sha(scorer)
        print(f"\nscore100.py sha256 after the batch:  {after}" + (" (unchanged)" if after == before else " (CHANGED: the batch edited the scorer)"))
        print(f"\n{len(MUTANTS)} mutants, {len(MUTANTS) - bad} killed, {bad} not killed; control passed")
        return 0 if bad == 0 and after == before else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
