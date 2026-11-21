#!/usr/bin/env python3
"""mutants_score97.py SCORER TEST - one-line mutants of scripts/queue-scores/score97.py, each killed by a named test.

Every mutant is a single string replacement asserted to match its anchor exactly once, written to a scratch copy under work/ and run against the whole test file with
SCORE97 pointing at the copy; the scorer itself is never edited. The unmutated copy runs first and must pass, or the batch is void. A kill is a NAMED test FAILING by
assertion (unittest's `FAIL: test_...`), and the mutant's own `expect` test must be among the failures: a mutant that dies of an unrelated error or on some other test
is reported and fails the batch. Run from the top-level shell:

  python scripts/tests/mutants_score97.py scripts/queue-scores/score97.py scripts/tests/test_score97.py
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
    # U1: the threshold, the comparison, the group tuples, the means, the range, the sign, the digest checks and the verdict word
    {"name": "u1-limit-to-5pct", "old": "LIMIT = s91().LIMIT", "new": "LIMIT = 0.050", "expect": "test_u1_the_limit_is_one_percent"},
    {"name": "u1-slower-direction", "old": "        if s > LIMIT:\n", "new": "        if s < -LIMIT:\n", "expect": "test_u1_a_cell_slower_is_flagged_and_a_faster_one_is_not"},
    {"name": "u1-partial-cell-guard", "old": 'if n_have != len(g["N"]) or t_have != len(g["T"]):', "new": 'if n_have > len(g["N"]) or t_have > len(g["T"]):',
     "expect": "test_u1_a_cell_not_reported_by_every_boot_is_not_decided"},
    {"name": "u1-digest-threshold", "old": "and len({*nd.get(k, []), *td.get(k, [])}) != 1", "new": "and len({*nd.get(k, []), *td.get(k, [])}) > 2",
     "expect": "test_u1_a_different_reply_digest_is_not_accepted"},
    {"name": "u1-digest-hole-threshold", "old": "len(nd.get(k, [])) + len(td.get(k, [])) != boots", "new": "len(nd.get(k, [])) + len(td.get(k, [])) > boots",
     "expect": "test_u1_a_missing_digest_report_is_not_decided"},
    {"name": "u1-n-group-drops-mn3", "old": '"N": [(q91, "mn1"), (q91, "mn2"), (q95, "mn3")],', "new": '"N": [(q91, "mn1"), (q91, "mn2"), (q91, "mps")],',
     "expect": "test_group_membership_mn3_is_in_n"},
    {"name": "u1-t-group-drops-tn2", "old": '"T": [(q92, "tn1"), (q92, "tn2")],', "new": '"T": [(q92, "tn1"), (q92, "ut1")],', "expect": "test_group_membership_tn_arms_are_t"},
    {"name": "u2-s0-group-drops-sm3", "old": '"S0": [(q91, "mps"), (q92, "sm2"), (q92, "sm3")],', "new": '"S0": [(q91, "mps"), (q92, "sm2"), (q92, "sm2")],',
     "expect": "test_group_membership_s0_has_all_three_boots"},
    {"name": "u2-s1-group-reads-sm3", "old": '"S1": [(q92, "ut1")],', "new": '"S1": [(q92, "sm3")],', "expect": "test_group_membership_ut1_is_s1"},
    {"name": "u1-t-mean-to-max", "old": "st.mean(tv[m]), st.mean(nv[m]))", "new": "max(tv[m]), st.mean(nv[m]))", "expect": "test_u1_the_group_value_is_the_mean_not_the_worst_boot"},
    {"name": "u1-n-mean-to-min", "old": "st.mean(tv[m]), st.mean(nv[m]))", "new": "st.mean(tv[m]), min(nv[m]))", "expect": "test_u1_the_group_value_is_the_mean_not_the_minimum"},
    {"name": "u1-inside-and-to-or", "old": "inside = min(nv[m]) <= min(tv[m]) and max(tv[m]) <= max(nv[m])", "new": "inside = min(nv[m]) <= min(tv[m]) or max(tv[m]) <= max(nv[m])",
     "expect": "test_u1_a_loss_above_every_boot_is_not_marked_inside"},
    {"name": "u1-print-sign", "old": "| {s:+.2%} slower", "new": "| {-s:+.2%} slower", "expect": "test_u1_a_cell_slower_is_flagged_and_a_faster_one_is_not"},
    {"name": "u1-accept-word", "old": 'f"U1 SYNC: ACCEPTED, no cell more than {LIMIT:.1%} slower and every reply digest equal"',
     "new": 'f"U1 SYNC: NOT ACCEPTED, no cell more than {LIMIT:.1%} slower and every reply digest equal"', "expect": "test_u1_accepted_when_every_cell_and_digest_agrees"},
    # U2: the sign, the two references and the no-rows guard
    {"name": "u2-gain-sign", "old": "return -s91().slower(m, new, ref) + 0.0", "new": "return s91().slower(m, new, ref) + 0.0", "expect": "test_u2_t_against_s1_is_faster_positive"},
    {"name": "u2-t-reference", "old": "ts1 = None if t is None or s1 is None else gain(m, t, s1)", "new": "ts1 = None if t is None or s0 is None else gain(m, t, s0)",
     "expect": "test_u2_the_two_fractions_have_their_own_references"},
    {"name": "u2-s0-reference", "old": "s1s0 = None if s1 is None or s0 is None else gain(m, s1, s0)", "new": "s1s0 = None if s1 is None or s0 is None else gain(m, s0, s1)",
     "expect": "test_u2_s1_against_s0_is_the_upstream_gain"},
    {"name": "u2-no-rows-guard", "old": "return st.mean(vals[m]) if boots and len(vals.get(m, [])) == len(boots) else None",
     "new": "return st.mean(vals[m]) if boots and len(vals.get(m, [])) > 0 else None", "expect": "test_u2_a_missing_boot_prints_no_rows_not_zeros"},
    # U3: the digest comparison, the reference and the cell-kind key
    {"name": "u3-differ-threshold", "old": "differ = [k for k in keys if k not in holes and len({*dt.get(k, []), *d1.get(k, [])}) != 1]",
     "new": "differ = [k for k in keys if k not in holes and len({*dt.get(k, []), *d1.get(k, [])}) > 2]", "expect": "test_u3_a_differing_reply_is_differ"},
    {"name": "u3-s1-reads-s0", "old": 's1_missing, _, d1 = load(g["S1"])', "new": 's1_missing, _, d1 = load(g["S0"])', "expect": "test_u3_a_differing_reply_is_differ"},
    {"name": "u3-dec-kind-to-p", "old": 'return k[1] if k[0] == "dec" else k[0]', "new": 'return "P" if k[0] == "dec" else k[0]', "expect": "test_u3_one_line_per_cell_kind"},
    # the exit code
    {"name": "exit-always-zero", "old": "return 1 if failed else 0", "new": "return 0", "expect": "test_the_exit_code_is_one_when_u1_digests_differ"},
    {"name": "exit-digest-flag-clear", "old": 'over the speed limit)", True', "new": 'over the speed limit)", False', "expect": "test_the_exit_code_is_one_when_u1_digests_differ"},
]


def run(test, scorer, timeout=1800):
    env = dict(os.environ, SCORE97=str(scorer))
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
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutants97-", dir=ROOT / "work"))
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
        print(f"\n{len(MUTANTS)} mutants, {len(MUTANTS) - bad} killed, {bad} not killed; control passed")
        return 0 if bad == 0 else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
