#!/usr/bin/env python3
"""mutants_score99.py SCORER TEST - one-line mutants of scripts/queue-scores/score99.py, each killed by a named test.

Every mutant is a single string replacement asserted to match its anchor exactly once, written to a scratch copy under work/ and run against the whole test file with
SCORE99 pointing at the copy; the scorer itself is never edited. The unmutated copy runs first and must pass, or the batch is void. A kill is a NAMED test FAILING by
assertion (unittest's `FAIL: test_...`), and the mutant's own `expect` test must be among the failures: a mutant that dies of an unrelated error or on some other test
is reported and fails the batch. The scorer's sha256 is printed before and after the batch and must be unchanged. Run from the top-level shell:

  python scripts/tests/mutants_score99.py scripts/queue-scores/score99.py scripts/tests/test_score99.py
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
    # C1: the limit, the two comparisons, the group means, the group membership, the cell set, the digest rules and the not-decided guard
    {"name": "c1-limit-to-5pct", "old": "LIMIT = s91().LIMIT", "new": "LIMIT = 0.050",
     "expect": "test_the_limit_is_one_percent_and_a_value_at_it_is_not_over"},
    {"name": "c1-over-direction", "old": "    return s > LIMIT", "new": "    return s < -LIMIT",
     "expect": "test_c1_a_latency_cell_up_is_slower_and_down_is_not"},
    {"name": "c1-reference-swap", "old": "        s = s91().slower(m, ce, ca)", "new": "        s = s91().slower(m, ca, ce)",
     "expect": "test_c1_a_latency_cell_up_is_slower_and_down_is_not"},
    {"name": "c1-ce-mean-to-first-boot", "old": "        s = s91().slower(m, ce, ca)", "new": "        s = s91().slower(m, cev[m][0], ca)",
     "expect": "test_the_group_value_is_the_mean_of_its_boots"},
    {"name": "c1-ca-mean-to-first-boot", "old": "        ca, ce = st.mean(cav[m]), st.mean(cev[m])", "new": "        ca, ce = cav[m][0], st.mean(cev[m])",
     "expect": "test_the_control_is_ca1_and_ca2"},
    {"name": "c1-digest-threshold", "old": "and len({*cad.get(k, []), *ced.get(k, [])}) != 1", "new": "and len({*cad.get(k, []), *ced.get(k, [])}) > 2",
     "expect": "test_c1_a_different_reply_digest_is_not_accepted"},
    {"name": "c1-digest-hole-threshold", "old": "len(cad.get(k, [])) + len(ced.get(k, [])) != boots", "new": "len(cad.get(k, [])) + len(ced.get(k, [])) > boots",
     "expect": "test_c1_a_missing_digest_report_is_not_decided"},
    {"name": "c1-partial-cell-guard", "old": '        if ca_have != len(g["CA"]) or ce_have != len(g["CE"]):', "new": '        if ca_have > len(g["CA"]) or ce_have > len(g["CE"]):',
     "expect": "test_c1_a_cell_not_reported_by_every_boot_is_not_decided"},
    {"name": "c1-ca-group-uses-ce1", "old": '"CA": [(q99, "ca1"), (q99, "ca2")]', "new": '"CA": [(q99, "ce1"), (q99, "ca2")]',
     "expect": "test_ce1_is_the_policy_not_the_control"},
    {"name": "c1-ce-group-uses-ce1-twice", "old": '"CE": [(q99, "ce1"), (q99, "ce2")]', "new": '"CE": [(q99, "ce1"), (q99, "ce1")]',
     "expect": "test_the_group_value_is_the_mean_of_its_boots"},
    {"name": "c1-ca-group-drops-ca2", "old": '[(q99, "ca1"), (q99, "ca2")]', "new": '[(q99, "ca1"), (q99, "ca1")]',
     "expect": "test_the_control_is_ca1_and_ca2"},
    {"name": "c1-not-decided-and-to-or", "old": "    if absent or holes:", "new": "    if absent and holes:",
     "expect": "test_c1_a_missing_digest_report_is_not_decided"},
    {"name": "c1-levels-drop-8", "old": "LEVELS = s91().LEVELS", "new": "LEVELS = (1, 2, 4)",
     "expect": "test_c1_a_cell_over_the_limit_is_named"},
    # C4: the anchor, the digest comparison, the not-decided shape, the EQUAL word and the summary's priority
    {"name": "c4-anchor-ca2", "old": '    ca_val, ca_dig = s91().boot(d, "ca1")', "new": '    ca_val, ca_dig = s91().boot(d, "ca2")',
     "expect": "test_c4_compares_against_ca1_not_ca2"},
    {"name": "c4-differ-threshold", "old": "        differ = sorted((k for k in set(ca_dig) & set(dig) if ca_dig[k] != dig[k]), key=str)",
     "new": "        differ = sorted((k for k in set(ca_dig) & set(dig) if len({ca_dig[k], dig[k]}) > 2), key=str)",
     "expect": "test_c4_one_differing_decode_cell_fails_the_arm"},
    {"name": "c4-one-side-only-dropped", "old": "        only = sorted(set(ca_dig) ^ set(dig), key=str)", "new": "        only = []",
     "expect": "test_c4_a_missing_report_is_not_decided_and_does_not_fail"},
    {"name": "c4-equal-word", "old": '            verdicts[arm] = "EQUAL"', "new": '            verdicts[arm] = "DIFFERS"',
     "expect": "test_c4_equal_when_every_digest_agrees"},
    {"name": "c4-summary-and-to-and", "old": "    if differ_arms:", "new": "    if undecided:",
     "expect": "test_c4_one_differing_decode_cell_fails_the_arm"},
    # the exit code: always zero, on any non-EQUAL, and on a C1 not-accepted
    {"name": "exit-always-zero", "old": "    return 1 if failed else 0", "new": "    return 0",
     "expect": "test_the_exit_code_is_one_when_a_c4_digest_differs"},
    {"name": "exit-on-not-decided", "old": '    failed = any(v == "DIFFERS" for v in v4.values())', "new": '    failed = any(v != "EQUAL" for v in v4.values())',
     "expect": "test_the_exit_code_is_zero_when_a_clause_is_not_decided"},
    {"name": "exit-on-c1", "old": '    failed = any(v == "DIFFERS" for v in v4.values())',
     "new": '    failed = any(v == "DIFFERS" for v in v4.values()) or v1.startswith("C1 SYNC: NOT")',
     "expect": "test_the_exit_code_is_zero_when_c1_is_not_accepted_but_the_digests_are_equal"},
    # C2 and C3: the report-only signs and the spread's definition and groups
    {"name": "c2-sign", "old": "| {1 - ce_mean / ca_mean:+.2%} faster", "new": "| {ce_mean / ca_mean - 1:+.2%} faster",
     "expect": "test_c2_reports_the_four_prompt_cells_with_known_numbers"},
    {"name": "c3-spread-not-normalised", "old": "    return (max(v) - min(v)) / st.mean(v)", "new": "    return (max(v) - min(v))",
     "expect": "test_c3_reports_the_spread_with_known_numbers"},
    {"name": "c3-ce-spread-uses-ca", "old": '    for tag, vals in (("CA", cav), ("CE", cev)):', "new": '    for tag, vals in (("CA", cav), ("CE", cav)):',
     "expect": "test_c3_the_policy_spread_is_its_own_boots"},
]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def run(test, scorer, timeout=1800):
    env = dict(os.environ, SCORE99=str(scorer))
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
    print(f"score99.py sha256 before the batch: {before}")
    (ROOT / "work").mkdir(exist_ok=True)
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutants99-", dir=ROOT / "work"))
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
        print(f"\n{'#':>3}  {'mutant':32} {'expected test':62} {'failing tests':62} {'errors':16} verdict")
        for i, name, expect, hit, errored, verdict in rows:
            print(f"{i:>3}  {name:32} {expect:62} {hit:62} {errored:16} {verdict}")
        after = sha(scorer)
        print(f"\nscore99.py sha256 after the batch:  {after}" + (" (unchanged)" if after == before else " (CHANGED: the batch edited the scorer)"))
        print(f"\n{len(MUTANTS)} mutants, {len(MUTANTS) - bad} killed, {bad} not killed; control passed")
        return 0 if bad == 0 and after == before else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
