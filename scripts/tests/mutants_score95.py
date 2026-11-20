#!/usr/bin/env python3
"""mutants_score95.py SCORER TEST - one-line mutants of scripts/queue-scores/score95.py, each killed by a named test.

Every mutant is a single string replacement asserted to match its anchor exactly once, written to a scratch copy under work/ and run against the whole test file with
SCORE95 pointing at the copy; the scorer itself is never edited. The unmutated copy runs first and must pass, or the batch is void. A kill is a NAMED test FAILING by
assertion (unittest's `FAIL: test_...`), and the mutant's own `expect` test must be among the failures: a mutant that dies of an unrelated error or on some other test
is reported and fails the batch. Run from the top-level shell:

  python scripts/tests/mutants_score95.py scripts/queue-scores/score95.py scripts/tests/test_score95.py
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
    # K1: the thresholds, the comparisons, the group tuples and the digest checks
    {"name": "k1-limit-to-5pct", "old": "LIMIT = s91().LIMIT", "new": "LIMIT = 0.050", "expect": "test_k1_a_cell_over_the_limit_is_named"},
    {"name": "k1-slower-direction", "old": "        if s > LIMIT:\n", "new": "        if s < -LIMIT:\n", "expect": "test_k1_a_latency_cell_up_is_slower_and_down_is_not"},
    {"name": "k1-digest-threshold", "old": "and len({*nd.get(k, []), *od.get(k, [])}) != 1", "new": "and len({*nd.get(k, []), *od.get(k, [])}) > 2",
     "expect": "test_k1_a_different_reply_digest_is_not_accepted"},
    {"name": "k1-digest-hole-threshold", "old": "len(nd.get(k, [])) + len(od.get(k, [])) != boots", "new": "len(nd.get(k, [])) + len(od.get(k, [])) > boots",
     "expect": "test_k1_a_missing_digest_report_is_not_decided"},
    {"name": "k1-partial-cell-guard", "old": '        if n_have != len(g["N"]) or o_have != len(g["O"]):', "new": '        if n_have > len(g["N"]) or o_have > len(g["O"]):',
     "expect": "test_k1_a_cell_not_reported_by_every_boot_is_not_decided"},
    {"name": "k1-n-group-drops-mn3", "old": '"N": [(q91, "mn1"), (q91, "mn2"), (q95, "mn3")],', "new": '"N": [(q91, "mn1"), (q91, "mn2"), (q91, "mo3")],',
     "expect": "test_group_membership_mn3_is_in_n"},
    {"name": "k1-o-group-drops-mo4", "old": '"O": [(old, "P1"), (old, "P2"), (q91, "mo3"), (q95, "mo4")],', "new": '"O": [(old, "P1"), (old, "P2"), (q91, "mo3"), (q91, "mo3")],',
     "expect": "test_group_membership_mo4_is_in_o"},
    {"name": "k1-new-mean-to-max", "old": "s = s91().slower(m, st.mean(nv[m]), st.mean(ov[m]))", "new": "s = s91().slower(m, max(nv[m]), st.mean(ov[m]))",
     "expect": "test_k1_a_cell_over_the_limit_is_named"},
    # K2: the three thresholds, the negative count, the mean, the cell set and the per-boot coverage
    {"name": "k2-declimit-to-1pct", "old": "DEC_LIMIT = 0.005", "new": "DEC_LIMIT = 0.010", "expect": "test_k2_carries_the_loss_at_the_boundary"},
    {"name": "k2-decneg-to-8", "old": "DEC_NEG = 9", "new": "DEC_NEG = 8", "expect": "test_k2_eight_negative_cells_do_not_carry"},
    {"name": "k2-decclean-to-3pct", "old": "DEC_CLEAN = 0.003", "new": "DEC_CLEAN = 0.030", "expect": "test_k2_a_mid_band_mean_is_unclear_and_the_edges_are_not"},
    {"name": "k2-negative-count-direction", "old": "neg = sum(1 for c in changes if c < 0)", "new": "neg = sum(1 for c in changes if c > 0)",
     "expect": "test_k2_carries_the_loss_at_the_boundary"},
    {"name": "k2-mean-to-sum", "old": "mean = st.mean(changes)", "new": "mean = sum(changes)", "expect": "test_k2_a_mid_band_mean_is_unclear_and_the_edges_are_not"},
    {"name": "k2-levels-add-6", "old": "DEC_LEVELS = (1, 2, 4)", "new": "DEC_LEVELS = (1, 2, 4, 6)", "expect": "test_k2_carries_the_loss_at_the_boundary"},
    {"name": "k2-coverage-guard", "old": "        short = short_cells(nv, g[\"N\"], DEC_CELLS) + short_cells(av, g[arm], DEC_CELLS)\n        if short:",
     "new": "        short = short_cells(nv, g[\"N\"], DEC_CELLS) + short_cells(av, g[arm], DEC_CELLS)\n        if 0:",
     "expect": "test_k2_not_decided_when_a_boot_reports_no_decode"},
    {"name": "k2-clean-comparison", "old": "        elif mean >= -DEC_CLEAN:", "new": "        elif mean <= -DEC_CLEAN:", "expect": "test_k2_clean_when_no_cell_moves"},
    # K3: the gain, the no-loss guard, the max/min and the sign
    {"name": "k3-gain-to-5pct", "old": "GAIN = 0.010", "new": "GAIN = 0.050", "expect": "test_k3_gains_at_the_inclusive_one_percent"},
    {"name": "k3-slow-limit-sign", "old": "slow = min(table.values()) < -GAIN", "new": "slow = min(table.values()) < GAIN", "expect": "test_k3_gains_at_the_inclusive_one_percent"},
    {"name": "k3-fast-max-to-min", "old": "fast = max(table.values()) >= GAIN", "new": "fast = min(table.values()) >= GAIN", "expect": "test_k3_gains_at_the_inclusive_one_percent"},
    {"name": "k3-gain-sign", "old": "return {m: 1 - st.mean(av[m]) / st.mean(nv[m]) for m in PROMPT_CELLS}, []",
     "new": "return {m: st.mean(av[m]) / st.mean(nv[m]) - 1 for m in PROMPT_CELLS}, []", "expect": "test_k3_gains_at_the_inclusive_one_percent"},
    {"name": "k3-coverage-guard", "old": "    short = short_cells(nv, g[\"N\"], PROMPT_CELLS) + short_cells(av, g[arm], PROMPT_CELLS)\n    if short:",
     "new": "    short = short_cells(nv, g[\"N\"], PROMPT_CELLS) + short_cells(av, g[arm], PROMPT_CELLS)\n    if 0:",
     "expect": "test_k3_not_decided_when_a_boot_reports_no_conversation"},
    # K4: the per-boot coverage and the digest comparison
    {"name": "k4-hole-threshold", "old": "for k in sorted(d, key=str) if len(d[k]) != len(bs)]", "new": "for k in sorted(d, key=str) if len(d[k]) > len(bs)]",
     "expect": "test_k4_a_missing_report_is_not_decided_and_does_not_fail"},
    {"name": "k4-differ-threshold", "old": "if len(set(nd[k] + ad[k])) != 1", "new": "if len(set(nd[k] + ad[k])) > 2", "expect": "test_k4_one_differing_decode_cell_fails_the_arm"},
    {"name": "k4-equal-word", "old": '            verdicts[arm] = "EQUAL"', "new": '            verdicts[arm] = "DIFFERS"', "expect": "test_k4_equal_when_every_digest_agrees"},
    # K5: the and/or of the reading and the additivity numbers
    {"name": "k5-holdback-or-to-and", "old": 'if v4.get(arm) == "DIFFERS" or v2.get(arm) == "CARRIES THE LOSS":', "new": 'if v4.get(arm) == "DIFFERS" and v2.get(arm) == "CARRIES THE LOSS":',
     "expect": "test_k5_hold_back_on_a_k4_difference"},
    {"name": "k5-promotable-and-to-or", "old": 'elif v2.get(arm) == "CLEAN" and v3.get(arm) == "GAINS" and v4.get(arm) == "EQUAL":',
     "new": 'elif v2.get(arm) == "CLEAN" or v3.get(arm) == "GAINS" or v4.get(arm) == "EQUAL":', "expect": "test_k5_unclear_between_the_clauses"},
    {"name": "k5-additivity-sign", "old": "T+X {t + x:+.2%}", "new": "T+X {t - x:+.2%}", "expect": "test_k5_the_additivity_line_carries_d_t_x_and_their_sum"},
    # the exit code
    {"name": "exit-always-zero", "old": "return 1 if failed else 0", "new": "return 0", "expect": "test_the_exit_code_is_one_when_a_k4_digest_differs"},
    {"name": "exit-on-not-decided", "old": 'failed = any(v == "DIFFERS" for v in v4.values())', "new": 'failed = any(v != "EQUAL" for v in v4.values())',
     "expect": "test_the_exit_code_is_zero_when_clauses_are_not_decided"},
]


def run(test, scorer, timeout=1800):
    env = dict(os.environ, SCORE95=str(scorer))
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
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutants95-", dir=ROOT / "work"))
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
