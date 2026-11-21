#!/usr/bin/env python3
"""mutants_score102.py SCORER TEST - one-line mutants of scripts/queue-scores/score102.py, each killed by a named test.

Every mutant is a single string replacement asserted to match its anchor exactly once, written to a scratch copy under work/ and run against the whole test file with SCORE102
pointing at the copy; the scorer itself is never edited. The unmutated copy runs first and must pass, or the batch is void. A kill is a NAMED test FAILING by assertion
(unittest's `FAIL: test_...`), and the mutant's own `expect` test must be among the failures: a mutant that dies of an unrelated error or on some other test is reported and
fails the batch. Run from the top-level shell:

  python scripts/tests/mutants_score102.py scripts/queue-scores/score102.py scripts/tests/test_score102.py
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
    # L0: the proof's name, its absence, the three variables, one rank's image and the units' one image
    {"name": "l0-proof-filename", "old": 'f"{label}-env.txt"', "new": 'f"{label}-env.log"', "expect": "test_l0_all_six_proofs_are_qualified"},
    {"name": "l0-absence-not-void", "old": '        return None, None, f"no readback proof ({f.name})"', "new": '        return "an-image", {n: "unset" for n in VARS}, None',
     "expect": "test_l0_a_missing_proof_voids_its_unit"},
    {"name": "l0-variable-check-off", "old": "        if got != want:", "new": "        if False:", "expect": "test_l0_a_rank_with_the_wrong_variable_voids_the_unit"},
    {"name": "l0-rank-image-only-from-rank-0", "old": "    ids = {ranks[r][1] for r in (0, 1, 2)}", "new": "    ids = {ranks[0][1]}", "expect": "test_l0_one_rank_on_another_image_voids_the_unit"},
    {"name": "l0-cross-image-off", "old": "                if ids[label] != common:", "new": "                if False:", "expect": "test_l0_a_second_image_id_voids_the_only_unit_on_it"},
    # L1: the digest comparison, a missing report, the equal word and the exit code
    {"name": "l1-differ-threshold", "old": "if len({*cd[k], *ad[k]}) != 1", "new": "if len({*cd[k], *ad[k]}) > 2", "expect": "test_l1_a_different_reply_digest_fails_both_verdicts_and_exits_one"},
    {"name": "l1-hole-not-decided", "old": "        if holes or only:", "new": "        if 0:", "expect": "test_l1_a_key_missing_on_one_side_is_not_decided"},
    {"name": "l1-equal-word", "old": '            words[arm] = "EQUAL"', "new": '            words[arm] = "DIFFERS"', "expect": "test_l1_equal_digests_pass"},
    {"name": "l1-override-off", "old": '    failed = any(w == "DIFFERS" for w in l1w.values())', "new": "    failed = False",
     "expect": "test_l1_a_different_reply_digest_fails_both_verdicts_and_exits_one"},
    {"name": "exit-always-zero", "old": "    return 1 if failed else 0", "new": "    return 0", "expect": "test_l1_a_different_reply_digest_fails_both_verdicts_and_exits_one"},
    # L2: the gain, its cell, the inclusive boundary, the ratio, the ordering and the per-boot coverage
    {"name": "l2-gain-threshold", "old": "GAIN = 0.005", "new": "GAIN = 0.010", "expect": "test_l2_gains_at_six_tenths_of_a_percent"},
    {"name": "l2-gain-not-inclusive", "old": "    word = \"GAINS\" if (g >= GAIN - EPS and beat) else \"NO GAIN\"", "new": "    word = \"GAINS\" if (g >= GAIN + EPS and beat) else \"NO GAIN\"",
     "expect": "test_l2_the_half_percent_is_inclusive"},
    {"name": "l2-gain-cell-is-8k", "old": "    g = changes[GAIN_CELL]", "new": '    g = changes[("cold", 8000)]', "expect": "test_l2_reads_the_120k_cell_only"},
    {"name": "l2-ratio-flip", "old": "    changes = {m: st.mean(cv[m]) / st.mean(av[m]) - 1 for m in L2_CELLS}", "new": "    changes = {m: 1 - st.mean(av[m]) / st.mean(cv[m]) for m in L2_CELLS}",
     "expect": "test_l2_accounts_by_the_control_over_the_arm_ratio"},
    {"name": "l2-order-guard", "old": "    beat = max(av[GAIN_CELL]) < min(cv[GAIN_CELL])", "new": "    beat = min(av[GAIN_CELL]) < min(cv[GAIN_CELL])",
     "expect": "test_l2_one_boot_of_two_beating_the_controls_is_not_a_gain"},
    {"name": "l2-coverage-guard", "old": "if len(vals.get(m, [])) != len(boots)]", "new": "if len(vals.get(m, [])) != 1]",
     "expect": "test_l2_not_decided_when_a_boot_reports_no_conversation"},
    # L3: the two limits, the negative count, the mean, the cell set, the directions and the per-boot coverage
    {"name": "l3-limit-to-1pct", "old": "DEC_LIMIT = 0.005", "new": "DEC_LIMIT = 0.010", "expect": "test_l3_carries_the_loss_at_the_boundary"},
    {"name": "l3-decneg-to-8", "old": "DEC_NEG = 9", "new": "DEC_NEG = 8", "expect": "test_l3_eight_negative_cells_do_not_carry"},
    {"name": "l3-clean-to-3pct", "old": "DEC_CLEAN = 0.003", "new": "DEC_CLEAN = 0.030", "expect": "test_l3_the_band_between_the_two_limits_is_unclear"},
    {"name": "l3-clean-sign", "old": "    elif mean >= -DEC_CLEAN - EPS:", "new": "    elif mean >= DEC_CLEAN - EPS:", "expect": "test_l3_clean_at_the_minus_three_tenths_boundary"},
    {"name": "l3-negative-direction", "old": "    neg = sum(1 for c in changes if c < 0)", "new": "    neg = sum(1 for c in changes if c > 0)", "expect": "test_l3_carries_the_loss_at_the_boundary"},
    {"name": "l3-mean-to-sum", "old": "    mean = st.mean(changes)", "new": "    mean = sum(changes)", "expect": "test_l3_clean_at_the_minus_three_tenths_boundary"},
    {"name": "l3-levels-add-6", "old": "DEC_LEVELS = (1, 2, 4)", "new": "DEC_LEVELS = (1, 2, 4, 6)", "expect": "test_l3_carries_the_loss_at_the_boundary"},
    {"name": "l3-coverage-guard", "old": "    short = short_cells(cv, CONTROL, DEC_CELLS) + short_cells(av, arm_labels, DEC_CELLS)\n    if short:",
     "new": "    short = short_cells(cv, CONTROL, DEC_CELLS) + short_cells(av, arm_labels, DEC_CELLS)\n    if 0:",
     "expect": "test_l3_not_decided_when_a_boot_reports_no_decode_cell"},
    # L4: S's retirement, V's three readings and the L1 override's word
    {"name": "l4-s-never-retires", "old": '            verdict = "KEEP, SPLIT NEXT" if gain == "GAINS" else "RETIRE" if gain == "NO GAIN" else "NOT DECIDED"',
     "new": '            verdict = "KEEP, SPLIT NEXT"', "expect": "test_verdict_s_retires_without_a_gain"},
    {"name": "l4-s-gain-retires", "old": '            verdict = "KEEP, SPLIT NEXT" if gain == "GAINS" else "RETIRE" if gain == "NO GAIN" else "NOT DECIDED"',
     "new": '            verdict = "RETIRE" if gain == "GAINS" else "KEEP, SPLIT NEXT" if gain == "NO GAIN" else "NOT DECIDED"',
     "expect": "test_verdict_s_keeps_and_splits_next_with_a_gain"},
    {"name": "l4-v-no-gain-promotes", "old": '        elif gain == "NO GAIN":\n            verdict = "RETIRE"',
     "new": '        elif gain == "NO GAIN":\n            verdict = "PROMOTION CANDIDATE, FIVE LEVELS NEXT"', "expect": "test_verdict_v_retires_without_a_gain"},
    {"name": "l4-v-gate-wants-clean", "old": '        elif gain == "GAINS" and cost == "CARRIES A LOSS":', "new": '        elif gain == "GAINS" and cost == "CLEAN":',
     "expect": "test_verdict_v_builds_the_prompt_only_gate_on_a_gain_and_a_loss"},
    {"name": "l4-v-promotion-wants-loss", "old": '        elif gain == "GAINS" and cost == "CLEAN":', "new": '        elif gain == "GAINS" and cost == "CARRIES A LOSS":',
     "expect": "test_verdict_v_is_a_promotion_candidate_on_a_gain_and_a_clean_decode"},
    {"name": "l4-v-unclear-to-promotion", "old": '            verdict = "NOT DECIDED"', "new": '            verdict = "PROMOTION CANDIDATE, FIVE LEVELS NEXT"',
     "expect": "test_verdict_v_is_not_decided_when_decode_is_unclear"},
    # the information block
    {"name": "info-drop-8-clients", "old": 'INFO_CELLS = [("dec", k, n) for k, _ in KINDS for n in (6, 8)]', "new": 'INFO_CELLS = [("dec", k, n) for k, _ in KINDS for n in (6,)]',
     "expect": "test_info_prints_the_six_and_eight_client_cells"},
    {"name": "info-no-skip-line", "old": '            out.append(f"the image\'s other boots at 120k in {d}: skipped: DIR absent")', "new": "            pass",
     "expect": "test_info_prints_the_other_boots_and_skips_an_absent_directory"},
]


def run(test, scorer, timeout=1800):
    env = dict(os.environ, SCORE102=str(scorer))
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
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutants102-", dir=ROOT / "work"))
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
        print(f"\n{'#':>3}  {'mutant':28} {'expected test':60} {'failing tests':60} {'errors':16} verdict")
        for i, name, expect, hit, errored, verdict in rows:
            print(f"{i:>3}  {name:28} {expect:60} {hit:60} {errored:16} {verdict}")
        print(f"\n{len(MUTANTS)} mutants, {len(MUTANTS) - bad} killed, {bad} not killed; control passed")
        return 0 if bad == 0 else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
