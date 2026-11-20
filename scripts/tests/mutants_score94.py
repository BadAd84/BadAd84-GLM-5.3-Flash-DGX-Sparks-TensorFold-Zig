#!/usr/bin/env python3
"""mutants_score94.py SCORER TEST - one-line mutants of scripts/queue-scores/score94.py, each killed by a named test.

Every mutant is a single string replacement asserted to match its anchor exactly once, written to a scratch copy under work/ and run against the whole test file with
SCORE94 pointing at the copy; the scorer itself is never edited. The unmutated copy runs first and must pass, or the batch is void. A kill is a NAMED test FAILING by
assertion (unittest's `FAIL: test_...`), and the mutant's own `expect` test must be among the failures: a mutant that dies of an unrelated error or on some other test
is reported and fails the batch. Run from the top-level shell:

  python scripts/tests/mutants_score94.py scripts/queue-scores/score94.py scripts/tests/test_score94.py
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
    # thresholds
    {"name": "limit-to-5pct", "old": "LIMIT = 0.010", "new": "LIMIT = 0.050", "expect": "test_a_slower_decode_cell_fails"},
    {"name": "cold-tol-to-1pct", "old": "COLD_TOL = 0.020", "new": "COLD_TOL = 0.010", "expect": "test_b0_cold_one_and_a_half_percent_off_holds"},
    {"name": "keep-tol-to-1pct", "old": "KEEP_TOL = 0.001", "new": "KEEP_TOL = 0.010", "expect": "test_b0_kept_state_off_by_more_than_a_tenth_fails"},
    {"name": "hold-sizes-drop-32k", "old": "HK_HOLD_SIZES = (8192, 32768)", "new": "HK_HOLD_SIZES = (8192,)", "expect": "test_a_gain_at_8k_only_is_neutral"},
    # label tuples
    {"name": "hk-a-b1-swapped", "old": '"A": ("hk-A1", "hk-A2"), "B1": ("hk-B1a", "hk-B1b"), "B0": ("hk-B0",)',
     "new": '"A": ("hk-B1a", "hk-B1b"), "B1": ("hk-A1", "hk-A2"), "B0": ("hk-B0",)', "expect": "test_holds_when_every_clause_holds"},
    {"name": "st-b1x-reads-b0", "old": '"B1x": ("st-B1x",)', "new": '"B1x": ("st-B0",)', "expect": "test_b1x_decode_off_by_more_than_one_percent_fails"},
    # H/S clauses
    {"name": "h2-b1-two-lines-allowed", "old": "elif counts.get(label) is not None and counts[label] > 1:",
     "new": "elif counts.get(label) is not None and counts[label] > 2:", "expect": "test_two_switch_lines_fail"},
    {"name": "h2-b0-line-ignored", "old": "        if counts.get(label):", "new": "        if counts.get(label) is None:",
     "expect": "test_a_switch_line_on_the_default_boot_fails"},
    {"name": "h1-digest-set-size", "old": "if len(s) != 1", "new": "if len(s) > 2", "expect": "test_one_differing_reply_digest_in_one_cell_fails"},
    {"name": "h1-clean-inverted", "old": 'if not v["clean"]', "new": 'if v["clean"]', "expect": "test_holds_when_every_clause_holds"},
    {"name": "h3-b1-direction", "old": 'if g < -LIMIT:\n            reasons.append(f"H3: {name(k)} is {-g:.2%} slower in B1")',
     "new": 'if g > LIMIT:\n            reasons.append(f"H3: {name(k)} is {-g:.2%} slower in B1")', "expect": "test_a_slower_decode_cell_fails"},
    {"name": "h3-b0-tolerance", "old": "        if abs(d0) > LIMIT:\n            reasons.append(f\"H3:", "new": "        if abs(d0) > COLD_TOL:\n            reasons.append(f\"H3:",
     "expect": "test_b0_off_the_default_path_on_decode_fails"},
    {"name": "h4-b1-tolerance", "old": "        if s > LIMIT:\n            reasons.append(f\"H4:", "new": "        if s > COLD_TOL:\n            reasons.append(f\"H4:",
     "expect": "test_a_slower_cold_first_token_fails"},
    {"name": "h4-b0-tolerance", "old": "        if abs(d0) > COLD_TOL:\n            reasons.append(f\"H4:", "new": "        if abs(d0) > LIMIT:\n            reasons.append(f\"H4:",
     "expect": "test_b0_cold_one_and_a_half_percent_off_holds"},
    {"name": "h5-strict-to-equal", "old": "if per[label] >= per[x]", "new": "if per[label] > per[x]", "expect": "test_a_kept_state_not_strictly_smaller_fails"},
    {"name": "h5-b0-tolerance", "old": "if abs(d0) > KEEP_TOL:", "new": "if abs(d0) > LIMIT:", "expect": "test_b0_kept_state_off_by_more_than_a_tenth_fails"},
    {"name": "h5-bytes-over-states-inverted", "old": 'g["prompt_cache_bytes"] / g["prompt_cache_states"]',
     "new": 'g["prompt_cache_states"] / g["prompt_cache_bytes"]', "expect": "test_holds_when_every_clause_holds"},
    {"name": "h6-half-to-all", "old": "if p1[1] < p0[1] / 2", "new": "if p1[1] < p0[1]", "expect": "test_the_profile_pair_is_printed_and_does_not_decide"},
    {"name": "s1-ours-digest-set-size", "old": "if len(set(use)) != 1:", "new": "if len(set(use)) > 2:", "expect": "test_a_differing_ours_reply_hash_in_one_cell_fails"},
    {"name": "s2-b1x-unguarded", "old": '        for arm, x in (("B0", d0), ("B1x", dx)):\n            if abs(x) > LIMIT:',
     "new": '        for arm, x in (("B0", d0),):\n            if abs(x) > LIMIT:', "expect": "test_b1x_decode_off_by_more_than_one_percent_fails"},
    {"name": "s3-b1x-tolerance", "old": '        for arm, x in (("B0", d0), ("B1x", dx)):\n            if abs(x) > COLD_TOL:',
     "new": '        for arm, x in (("B0", d0), ("B1x", dx)):\n            if abs(x) > LIMIT:', "expect": "test_b1x_cold_off_by_one_and_a_half_percent_holds"},
    {"name": "s4-gain-drops-both-below", "old": "gain3k_ok = both_below(b1, a) and gain3k >= LIMIT", "new": "gain3k_ok = gain3k >= LIMIT",
     "expect": "test_one_b1_boot_not_below_every_a_boot_is_neutral"},
    {"name": "s4-turn2-direction", "old": "        if g2 > LIMIT:", "new": "        if g2 < -LIMIT:", "expect": "test_c3k_turn_2_slower_by_more_than_one_percent_fails"},
    {"name": "s4-c74-tolerance", "old": "        if g74 > LIMIT:", "new": "        if g74 > COLD_TOL:", "expect": "test_c74_turns_slower_by_more_than_one_percent_fails"},
    {"name": "s5-fail-line-ignored", "old": "if fails or not passes_:", "new": "if not passes_:", "expect": "test_s5_a_fail_line_fails"},
    {"name": "s5-no-pass-ignored", "old": "if fails or not passes_:", "new": "if fails:", "expect": "test_s5_a_log_without_a_pass_fails"},
    {"name": "mean-inverted", "old": "return s93().diff(new, old)", "new": "return s93().diff(old, new)",
     "expect": "test_holds_when_every_clause_holds"},
    {"name": "both-below-weakened", "old": "return max(new) < min(old)", "new": "return min(new) < max(old)", "expect": "test_one_b1_boot_not_below_every_a_boot_is_neutral"},
    # control flow and the exit code
    {"name": "hk-undecided-ignored", "old": '    if undecided:\n        return out, "HEAD SKIP: NOT DECIDED: ',
     "new": '    if 0:\n        return out, "HEAD SKIP: NOT DECIDED: ', "expect": "test_a_missing_cache_report_is_not_decided"},
    {"name": "exit-always-zero", "old": "return 1 if failed else 0", "new": "return 0", "expect": "test_the_exit_code_is_one_when_a_lever_fails"},
    {"name": "exit-last-lever-only", "old": "failed = failed or bad", "new": "failed = bad", "expect": "test_the_exit_code_is_one_when_a_lever_fails"},
    # the warm-turn report block
    {"name": "warm-reference-group", "old": '        base = timings["A"]', "new": '        base = timings["B1"]',
     "expect": "test_prints_each_boot_s_figures_and_the_widths_per_arm"},
    {"name": "warm-sign", "old": "{1 - st.mean(v) / st.mean(base):+.2%}", "new": "{st.mean(v) / st.mean(base) - 1:+.2%}",
     "expect": "test_prints_each_boot_s_figures_and_the_widths_per_arm"},
    {"name": "warm-sizes-drop-120k", "old": 'WARM = (("8k", 8192), ("32k", 32768), ("120k", 122880))', "new": 'WARM = (("8k", 8192), ("32k", 32768))',
     "expect": "test_prints_each_boot_s_figures_and_the_widths_per_arm"},
    {"name": "warm-widths-last-boot-only", "old": "widths[arm].add(w)", "new": "widths[arm] = {w}",
     "expect": "test_the_widths_keep_every_boot_s_distinct_set"},
    {"name": "warm-missing-silent", "old": '                    out.append(f"{label}: no warm-{size}.json")\n                    continue',
     "new": "                    continue", "expect": "test_a_missing_report_prints_no_numbers"},
    {"name": "warm-missing-numbers", "old": "    if not isinstance(rep, dict):\n        return None",
     "new": "    if not isinstance(rep, dict):\n        return (0.0, 0.0, None, False, None)", "expect": "test_a_missing_report_prints_no_numbers"},
    {"name": "warm-verdict-leak", "old": '    print("\\n".join(warm_report(a.dir)))',
     "new": '    failed = failed or any("no warm-" in x for x in warm_report(a.dir))\n    print("\\n".join(warm_report(a.dir)))',
     "expect": "test_the_block_decides_nothing_with_no_warm_files"},
]


def run(test, scorer, timeout=1800):
    env = dict(os.environ, SCORE94=str(scorer))
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
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutants94-", dir=ROOT / "work"))
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
        print(f"\n{'#':>3}  {'mutant':32} {'expected test':58} {'failing tests':58} {'errors':16} verdict")
        for i, name, expect, hit, errored, verdict in rows:
            print(f"{i:>3}  {name:32} {expect:58} {hit:58} {errored:16} {verdict}")
        print(f"\n{len(MUTANTS)} mutants, {len(MUTANTS) - bad} killed, {bad} not killed; control passed")
        return 0 if bad == 0 else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
