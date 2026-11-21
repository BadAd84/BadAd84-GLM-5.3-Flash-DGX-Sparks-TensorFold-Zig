#!/usr/bin/env python3
"""mutants_score98.py SCORER TEST - one-line mutants of scripts/queue-scores/score98.py, each killed by a named test.

Every mutant is a single string replacement asserted to match its anchor exactly once, written to a scratch copy under work/ and run against the whole test file with
SCORE98 pointing at the copy; the scorer itself is never edited. The unmutated copy runs first and must pass, or the batch is void. A kill is a NAMED test FAILING by
assertion (unittest's `FAIL: test_...`), and the mutant's own `expect` test must be among the failures: a mutant that dies of an unrelated error or on some other test
is reported and fails the batch. Run from the top-level shell:

  python scripts/tests/mutants_score98.py scripts/queue-scores/score98.py scripts/tests/test_score98.py
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
    # P0: the two flags
    {"name": "p0-qualified-not-true", "old": "        if qualified is not True:", "new": "        if qualified is False:",
     "expect": "test_p0_not_decided_when_qualified_is_not_true"},
    {"name": "p0-completed-not-true", "old": "        if completed is not True:", "new": "        if completed is False:",
     "expect": "test_p0_not_decided_when_completed_schedule_is_missing"},
    # P1: the tool's verdict and the rows' own comparison
    {"name": "p1-tool-false-to-none", "old": "    if tool is False:", "new": "    if tool is None:",
     "expect": "test_p1_fails_when_the_tools_verdict_is_false"},
    {"name": "p1-tool-false-to-not-true", "old": "    if tool is False:", "new": "    if tool is not True:",
     "expect": "test_p1_not_decided_when_the_tools_verdict_is_none_but_the_rows_agree"},
    {"name": "p1-fingerprint-direction", "old": '        if x.get("request_sha256") != y.get("request_sha256"):',
     "new": '        if x.get("request_sha256") == y.get("request_sha256"):', "expect": "test_p1_fails_when_a_request_fingerprint_differs"},
    {"name": "p1-token-check-off", "old": "        elif not identical(x, y):", "new": "        elif False:",
     "expect": "test_p1_fails_when_a_token_hash_differs_even_if_the_tool_says_exact"},
    # P2: the threshold, the pairing, the amended allowance, the chunk and the comparison
    {"name": "p2-threshold-to-20pct", "old": "OVERSUSCRIBED = Fraction(1, 10)", "new": "OVERSUSCRIBED = Fraction(2, 10)",
     "expect": "test_p2_exactly_ten_percent_is_oversubscribed"},
    {"name": "p2-pairing-one-bucket", "old": "        conv.setdefault(c, []).append(r)", "new": "        conv.setdefault(0, []).append(r)",
     "expect": "test_p2_pairs_each_conversation_with_its_own_previous_turn"},
    {"name": "p2-template-rows-zero", "old": "TEMPLATE_ROWS = 8", "new": "TEMPLATE_ROWS = 0",
     "expect": "test_p2_gap_2056_is_not_a_miss_and_2057_is"},
    {"name": "p2-chunk-2047", "old": "RESUME_CHUNK = 2048", "new": "RESUME_CHUNK = 2047",
     "expect": "test_p2_gap_2056_is_not_a_miss_and_2057_is"},
    {"name": "p2-chunk-2049", "old": "RESUME_CHUNK = 2048", "new": "RESUME_CHUNK = 2049",
     "expect": "test_p2_gap_2056_is_not_a_miss_and_2057_is"},
    {"name": "p2-old-rule", "old": "RESUME_ALLOWANCE = RESUME_CHUNK + TEMPLATE_ROWS  # P2:", "new": "RESUME_ALLOWANCE = TEMPLATE_ROWS  # P2:",
     "expect": "test_p2_chunk_aligned_resumption_with_nothing_evicted_is_not_oversubscribed"},
    {"name": "p2-allowance-sign", "old": '                    if r["cached_tokens"] < prev["prompt_tokens"] - RESUME_ALLOWANCE:',
     "new": '                    if r["cached_tokens"] < prev["prompt_tokens"] + RESUME_ALLOWANCE:',
     "expect": "test_p2_chunk_aligned_resumption_with_nothing_evicted_is_not_oversubscribed"},
    {"name": "p2-miss-comparison-inclusive", "old": '                    if r["cached_tokens"] < prev["prompt_tokens"] - RESUME_ALLOWANCE:',
     "new": '                    if r["cached_tokens"] <= prev["prompt_tokens"] - RESUME_ALLOWANCE:',
     "expect": "test_p2_gap_2056_is_not_a_miss_and_2057_is"},
    {"name": "p2-miss-direction", "old": '                    if r["cached_tokens"] < prev["prompt_tokens"] - RESUME_ALLOWANCE:',
     "new": '                    if r["cached_tokens"] > prev["prompt_tokens"] - RESUME_ALLOWANCE:',
     "expect": "test_p2_chunk_aligned_resumption_with_nothing_evicted_is_not_oversubscribed"},
    # P3: the threshold, the comparison, the reference arm and the receipt check
    {"name": "p3-gain-to-11pct", "old": "GAIN = Fraction(1, 10)", "new": "GAIN = Fraction(11, 100)", "expect": "test_r_exactly_ten_percent_holds"},
    {"name": "p3-gain-comparison-inclusive", "old": "    elif r < GAIN:", "new": "    elif r <= GAIN:", "expect": "test_r_exactly_ten_percent_holds"},
    {"name": "p3-verdict-gain-inclusive", "old": "    if r < GAIN:", "new": "    if r <= GAIN:", "expect": "test_r_exactly_ten_percent_holds"},
    {"name": "p3-r-sign", "old": "    r = Fraction(A - B, A)", "new": "    r = Fraction(B - A, A)",
     "expect": "test_holds_when_the_policy_rebuilds_fewer_rows"},
    {"name": "p3-reference-arm", "old": '    A = trace_side(cmp, "a").get("rebuilt_rows")', "new": '    A = trace_side(cmp, "b").get("rebuilt_rows")',
     "expect": "test_holds_when_the_policy_rebuilds_fewer_rows"},
    {"name": "p3-zero-is-a-failure", "old": "    if r < 0:", "new": "    if r <= 0:", "expect": "test_neutral_when_r_is_exactly_zero"},
    {"name": "p3-receipt-check-off", "old": "    if A != ra:", "new": "    if A == ra:", "expect": "test_p3_not_decided_when_compare_contradicts_the_traces"},
    # P4: the allowance, the boundaries and which number gates
    {"name": "p4-slack-to-tenth", "old": "SLOW = Fraction(1, 100)", "new": "SLOW = Fraction(1, 1000)", "expect": "test_exactly_one_percent_slower_still_holds"},
    {"name": "p4-strict-boundary", "old": "    slower = Fraction(B) - Fraction(A) > Fraction(A) * SLOW",
     "new": "    slower = Fraction(B) - Fraction(A) >= Fraction(A) * SLOW", "expect": "test_exactly_one_percent_slower_still_holds"},
    {"name": "p4-sign", "old": "    slower = Fraction(B) - Fraction(A) > Fraction(A) * SLOW",
     "new": "    slower = Fraction(A) - Fraction(B) > Fraction(A) * SLOW", "expect": "test_over_the_one_percent_allowance_is_neutral_with_the_reason"},
    {"name": "p4-gate-on-the-agent-mean", "old": "    slower = Fraction(B) - Fraction(A) > Fraction(A) * SLOW",
     "new": "    slower = (Fraction(mb) - Fraction(ma)) / Fraction(ma) > SLOW", "expect": "test_the_gate_is_the_sum_and_the_agent_mean_is_reported"},
    # P5: the range and its two ends
    {"name": "p5-high-bound-dropped", "old": '        where = "within" if low <= r <= high else "below" if r < low else "above"',
     "new": '        where = "within" if low <= r else "below" if r < low else "above"', "expect": "test_above_the_range"},
    {"name": "p5-low-bound-40", "old": "PREDICTED = (Fraction(44, 100), Fraction(50, 100))", "new": "PREDICTED = (Fraction(40, 100), Fraction(50, 100))",
     "expect": "test_below_the_range"},
    # the CACHE block's budget comparison
    {"name": "cache-budget-comparison", "old": '("equal" if budget == PREDICTION_BUDGET else "different")',
     "new": '("equal" if budget != PREDICTION_BUDGET else "different")', "expect": "test_the_budget_line_reads_equal"},
    # the exit code and the failed flag
    {"name": "exit-always-zero", "old": "    return 1 if failed else 0", "new": "    return 0", "expect": "test_one_only_when_p1_fails"},
    {"name": "failed-flag-false", "old": "    return lines, states, p1state is False", "new": "    return lines, states, False", "expect": "test_one_only_when_p1_fails"},
]


def run(test, scorer, timeout=1800):
    env = dict(os.environ, SCORE98=str(scorer))
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
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutants98-", dir=ROOT / "work"))
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
        print(f"\n{'#':>3}  {'mutant':30} {'expected test':64} {'failing tests':64} {'errors':16} verdict")
        for i, name, expect, hit, errored, verdict in rows:
            print(f"{i:>3}  {name:30} {expect:64} {hit:64} {errored:16} {verdict}")
        print(f"\n{len(MUTANTS)} mutants, {len(MUTANTS) - bad} killed, {bad} not killed; control passed")
        return 0 if bad == 0 else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
