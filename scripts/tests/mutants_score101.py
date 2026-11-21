#!/usr/bin/env python3
"""mutants_score101.py SCORER TEST - one-line mutants of scripts/queue-scores/score101.py, each killed by a named test.

Every mutant is a single string replacement asserted to match its anchor exactly once, written to a scratch copy under work/ and run against the whole test file with
SCORE101 pointing at the copy; the scorer itself is never edited. The unmutated copy runs first and must pass, or the batch is void. A kill is a NAMED test FAILING by
assertion (unittest's `FAIL: test_...`), and the mutant's own `expect` test must be among the failures: a mutant that dies of an unrelated error, or that fails some other
test, is reported and fails the batch. The scorer's sha256 is printed before and after the batch and must be unchanged. Run from the top-level shell:

  python scripts/tests/mutants_score101.py scripts/queue-scores/score101.py scripts/tests/test_score101.py
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
    # U0: the drafter's own proof (the 0.6 bound, its direction, the stock three's equality, the parser, the missing markers)
    {"name": "split-max-04", "old": "SPLIT_MAX = 0.6", "new": "SPLIT_MAX = 0.4",
     "expect": "test_u0_qualified_when_both_proofs_hold"},
    {"name": "split-direction", "old": "    if not dv[SPLIT] < SPLIT_MAX:", "new": "    if not dv[SPLIT] > SPLIT_MAX:",
     "expect": "test_u0_qualified_when_both_proofs_hold"},
    {"name": "stock-equality-drops-ut2d", "old": "    if not dv[UT2[0]] == dv[UT2[1]] == dv[DSC]:", "new": "    if not dv[UT2[0]] == dv[UT2[1]]:",
     "expect": "test_u0_the_stock_three_must_be_equal"},
    {"name": "drafter-parser-drops-value", "old": "    return float(m.group(1)) if m else None", "new": "    return None",
     "expect": "test_the_drafter_line_parser_reads_the_gib_value"},
    {"name": "missing-drafter-as-zero", "old": '    if not f.exists():\n        return None, "missing file " + f.name\n    line = f.read_text(encoding="utf-8").strip()',
     "new": '    if not f.exists():\n        return 0.0, ""\n    line = f.read_text(encoding="utf-8").strip()',
     "expect": "test_u0_a_missing_drafter_file_is_not_decided"},
    {"name": "missing-dscores-as-none", "old": '    if not f.exists():\n        return None, "missing file " + f.name\n    text = f.read_text(encoding="utf-8").strip()',
     "new": '    if not f.exists():\n        return [], None\n    text = f.read_text(encoding="utf-8").strip()',
     "expect": "test_u0_a_missing_dscores_file_is_not_decided"},
    {"name": "drafter-MISSING-as-a-line", "old": '    if not line or line == "MISSING":', "new": "    if not line:",
     "expect": "test_u0_a_drafter_file_saying_missing_is_not_decided"},
    # U0: the DSCORES proof (the four branches the amendment names)
    {"name": "dscores-zero-line-not-required", "old": "    if not any(DSCORES_OFF in l for l in ds[DSC]):", "new": "    if False:",
     "expect": "test_u0_ut2d_without_the_dscores_zero_line_fails"},
    {"name": "dscores-zero-line-rejected", "old": "    if not any(DSCORES_OFF in l for l in ds[DSC]):", "new": "    if any(DSCORES_OFF in l for l in ds[DSC]):",
     "expect": "test_u0_qualified_when_both_proofs_hold"},
    {"name": "default-boot-dscores-ignored", "old": "        if ds[tag]:", "new": "        if False:",
     "expect": "test_u0_a_default_boot_with_a_dscores_line_fails"},
    {"name": "dscores-MISSING-as-no-lines", "old": '    if not text or text == "MISSING":', "new": "    if not text:",
     "expect": "test_u0_a_dscores_file_saying_missing_is_not_decided"},
    # U0: ut1's proof files are information only (the amendment)
    {"name": "ut1-drafter-required", "old": "        if v is None and tag != UT1:", "new": "        if v is None:",
     "expect": "test_u0_qualified_without_ut1s_proof_files"},
    {"name": "ut1-dscores-required", "old": "        if ev is None and tag != UT1:", "new": "        if ev is None:",
     "expect": "test_u0_qualified_without_ut1s_proof_files"},
    {"name": "ut1-present-proof-fails", "old": "    for tag in UT2 + (SPLIT,):", "new": "    for tag in (UT1,) + UT2 + (SPLIT,):",
     "expect": "test_u0_ignores_ut1s_proof_files_when_present"},
    # U0 completeness
    {"name": "missing-label-dropped", "old": "            missing.append(tag)", "new": "            continue",
     "expect": "test_a_missing_ut2_boot_is_not_decided"},
    {"name": "short-cells-dropped", "old": '        short += [f"{tag}:{S91.name(m)}" for m in S92.METRICS if m not in v]', "new": "        short += []",
     "expect": "test_a_cell_missing_from_a_boot_is_not_decided"},
    # U1: the session caveat line, then the larger-of bound, the both-boots rule, the two directions, the spread's own definition
    {"name": "u1-note-removed", "old": '    out = ["== U1 tip rung: the ut2 group (ut2a ut2b) against ut1, every cell; faster is positive, and a cell is CLEAR only when both boots lie beyond ut1 by more than the larger of 1.0% and their own difference",\n           "note: ut1 ran in queue96, hours before these boots; a difference between boots of different sessions that is not larger than the ut2 group\'s own spread cannot be told from a change"]',
     "new": '    out = ["== U1 tip rung: the ut2 group (ut2a ut2b) against ut1, every cell; faster is positive, and a cell is CLEAR only when both boots lie beyond ut1 by more than the larger of 1.0% and their own difference"]',
     "expect": "test_the_u1_caveat_line_is_present_and_not_in_u2"},
    {"name": "clear-bound-drops-spread", "old": "    bound = max(S92.LIMIT, spread([a, b]))", "new": "    bound = S92.LIMIT",
     "expect": "test_u1_the_spread_is_the_larger_bound_when_it_exceeds_one_percent"},
    {"name": "clear-bound-min", "old": "    bound = max(S92.LIMIT, spread([a, b]))", "new": "    bound = min(S92.LIMIT, spread([a, b]))",
     "expect": "test_u1_the_spread_is_the_larger_bound_when_it_exceeds_one_percent"},
    {"name": "clear-one-boot-enough", "old": "    if min(gaps) > bound:", "new": "    if max(gaps) > bound:",
     "expect": "test_u1_the_spread_is_the_larger_bound_when_it_exceeds_one_percent"},
    {"name": "clear-loss-dropped", "old": "    if max(gaps) < -bound:", "new": "    if False:",
     "expect": "test_u1_clear_loss_for_latency"},
    {"name": "spread-not-normalised", "old": "    return (max(values) - min(values)) / st.mean(values)", "new": "    return (max(values) - min(values))",
     "expect": "test_u1_the_one_percent_limit_is_the_larger_bound_when_the_spread_is_smaller"},
    {"name": "spread-max-over-min", "old": "    return (max(values) - min(values)) / st.mean(values)", "new": "    return max(values) / min(values) - 1",
     "expect": "test_u1_the_spread_is_the_larger_bound_when_it_exceeds_one_percent"},
    {"name": "digest-differ-ignored", "old": "    differ = sorted({k for k in both if len({*a[k], *r[k]}) != 1}, key=str)", "new": "    differ = []",
     "expect": "test_u1_digest_differences_are_listed"},
    {"name": "counts-all-prompt", "old": '            counts[(kind, D92.cell_group(S91.name(m)))] += 1', "new": '            counts[(kind, "PROMPT")] += 1',
     "expect": "test_u1_counts_are_per_cell_group"},
    {"name": "u1-group-reads-ut1", "old": "    missing, v2, _ = S91.group([(q, UT2[0]), (q, UT2[1])])", "new": "    missing, v2, _ = S91.group([(q, UT1)])",
     "expect": "test_u1_the_one_percent_limit_is_the_larger_bound_when_the_spread_is_smaller"},
    # U2: score92's rule passed through, against the ut2 group
    {"name": "u2-reference-is-ut1", "old": "    lines, verdict = S92.arm([(q, SPLIT)], [(q, UT2[0]), (q, UT2[1])])", "new": "    lines, verdict = S92.arm([(q, SPLIT)], [(q, UT1)])",
     "expect": "test_u2_passes_s92_arm_through_unchanged"},
    {"name": "u2-verdict-forced", "old": "    return out, verdict", "new": '    return out, "CANDIDATE"',
     "expect": "test_u2_not_a_candidate_on_the_flat_rung"},
    # U3: the share's direction, its two bounds, and its block carrying no verdict word
    {"name": "share-inverted", "old": "    share = mean / d[1] - 1", "new": "    share = d[1] / mean - 1",
     "expect": "test_u3_share_arithmetic"},
    {"name": "share-clear-drops-spread", "old": "    if share > S92.LIMIT and share > spread_ut2:", "new": "    if share > S92.LIMIT:",
     "expect": "test_u3_share_blocked_by_the_ut2_spread"},
    {"name": "share-clear-drops-limit", "old": "    if share > S92.LIMIT and share > spread_ut2:", "new": "    if share > spread_ut2:",
     "expect": "test_u3_share_below_one_percent_is_not_clear"},
    {"name": "u3-prints-the-verdict", "old": '    out = [f"== U3 DSCORES: {DSC} (TF_GLM_DSCORES=0) against the ut2 group (ut2a ut2b); each cell is DSCORES switched off, so the share DSCORES gives is the negative of it"]\n    out += lines if lines else [verdict]',
     "new": '    out = [f"== U3 DSCORES: {DSC} (TF_GLM_DSCORES=0) against the ut2 group (ut2a ut2b); each cell is DSCORES switched off, so the share DSCORES gives is the negative of it"]\n    out += [verdict]',
     "expect": "test_u3_has_no_verdict_word"},
    # U3: the amended symmetric share (its loss branch and both bounds)
    {"name": "u3-loss-branch-dropped", "old": "    elif share < -S92.LIMIT and -share > spread_ut2:", "new": "    elif False:",
     "expect": "test_u3_clear_loss_when_dscores_is_slower_beyond_both_bounds"},
    {"name": "u3-loss-drops-spread", "old": "    elif share < -S92.LIMIT and -share > spread_ut2:", "new": "    elif share < -S92.LIMIT:",
     "expect": "test_u3_a_loss_blocked_by_the_ut2_spread_is_not_clear"},
    {"name": "u3-loss-drops-limit", "old": "    elif share < -S92.LIMIT and -share > spread_ut2:", "new": "    elif -share > spread_ut2:",
     "expect": "test_u3_a_loss_below_one_percent_is_not_clear"},
    {"name": "u3-loss-sign-swapped", "old": "    elif share < -S92.LIMIT and -share > spread_ut2:", "new": "    elif share < -S92.LIMIT and share > spread_ut2:",
     "expect": "test_u3_clear_loss_when_dscores_is_slower_beyond_both_bounds"},
    # U4: the group lines' members and shape
    {"name": "u4-ut1-group-is-ut2", "old": '    for name, tags in (("ut2", UT2), ("ut1", (UT1,))):', "new": '    for name, tags in (("ut2", UT2), ("ut1", UT2)):',
     "expect": "test_u4_prints_each_boot_and_the_group_lines"},
    {"name": "u4-group-line-short", "old": '        out.append(CD.group_line(name, got) if got else f"group {name}: no boot")', "new": '        out.append(f"group {name}: {len(got)} boot(s)")',
     "expect": "test_u4_prints_each_boot_and_the_group_lines"},
    # U5: the percent's direction and the facts row's selection
    {"name": "u5-percent-inverted", "old": '            out.append(f"{tag:6s} {b} bytes ({b / base - 1:+.2%} against ut1 {base})")', "new": '            out.append(f"{tag:6s} {b} bytes ({base / b - 1:+.2%} against ut1 {base})")',
     "expect": "test_u5_percentages"},
    {"name": "u5-any-row", "old": '        if r.get("tag") == tag and r.get("case") == "boot":', "new": '        if r.get("tag") == tag:',
     "expect": "test_u5_percentages"},
    # the final line: its U2 word and its not-decided branch, and the void shape on a failed proof
    {"name": "final-u2-word-candidate", "old": '        return "NOT A CANDIDATE"', "new": '        return "CANDIDATE"',
     "expect": "test_the_final_line_states_u0_u2_and_the_clear_counts"},
    {"name": "final-keeps-the-old-format", "old": '        return f"U-VERDICT: U0 ARM DID NOT TAKE EFFECT ({u0_reason}): the U1, U2 and U3 readings above are void"',
     "new": '        return f"U-VERDICT: U0 ARM DID NOT TAKE EFFECT ({u0_reason}); U2 {u2_word(u2v)}; U1 CLEAR: {counts_line(counts)}"',
     "expect": "test_a_failed_proof_final_line_is_void_and_carries_no_u2_word"},
    {"name": "final-prints-u2-on-failure", "old": '        return f"U-VERDICT: U0 ARM DID NOT TAKE EFFECT ({u0_reason}): the U1, U2 and U3 readings above are void"',
     "new": '        return f"U-VERDICT: U0 ARM DID NOT TAKE EFFECT ({u0_reason}): U2 {u2_word(u2v)}; the U1, U2 and U3 readings above are void"',
     "expect": "test_a_failed_proof_final_line_is_void_and_carries_no_u2_word"},
    {"name": "final-not-decided-falls-through", "old": '    if u0_state == "NOT DECIDED":\n        return f"U-VERDICT: NOT DECIDED: {u0_reason}"',
     "new": '    if False:\n        return f"U-VERDICT: NOT DECIDED: {u0_reason}"',
     "expect": "test_a_missing_ut2_boot_is_not_decided"},
]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def run(test, scorer, timeout=1800):
    env = dict(os.environ, SCORE101=str(scorer))
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
    print(f"score101.py sha256 before the batch: {before}")
    (ROOT / "work").mkdir(exist_ok=True)
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutants101-", dir=ROOT / "work"))
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
        print(f"\nscore101.py sha256 after the batch:  {after}" + (" (unchanged)" if after == before else " (CHANGED: the batch edited the scorer)"))
        print(f"\n{len(MUTANTS)} mutants, {len(MUTANTS) - bad} killed, {bad} not killed; control passed")
        return 0 if bad == 0 and after == before else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
