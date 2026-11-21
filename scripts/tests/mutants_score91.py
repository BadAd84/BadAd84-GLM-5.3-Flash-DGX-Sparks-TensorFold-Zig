#!/usr/bin/env python3
"""mutants_score91.py SCORER TEST - one-line mutants of the NOTCOLD rule in scripts/queue-scores/score91.py (a cold row the instrument flagged NOTCOLD is left out of its cell's mean, its
reply digest is kept, and a cell whose rows are all flagged has no value), each killed by a named test.

Every mutant is a single string replacement asserted to match its anchor exactly once, written to a scratch copy under work/ and run against the whole test file with SCORE91 pointing
at the copy; the scorer itself is never edited. The unmutated copy runs first and must pass, or the batch is void. A kill is a NAMED test FAILING by assertion (unittest's
`FAIL: test_...`), and the mutant's own `expect` test must be among the failures: a mutant that dies of an unrelated error or on some other test is reported and fails the batch.
The scorer's sha256 is printed before and after the batch and must be unchanged. Run from the top-level shell:

  python scripts/tests/mutants_score91.py scripts/queue-scores/score91.py scripts/tests/test_score91.py
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
    {"name": "notcold-rows-counted", "old": '"NOTCOLD" not in (r.get("flags") or [])', "new": "True",
     "expect": "test_a_notcold_row_is_left_out_of_its_cells_mean_and_its_digest_is_kept"},
    {"name": "flag-name-misspelt", "old": '"NOTCOLD" not in (r.get("flags") or [])', "new": '"NOT_COLD" not in (r.get("flags") or [])',
     "expect": "test_a_notcold_row_is_left_out_of_its_cells_mean_and_its_digest_is_kept"},
    {"name": "only-flagged-rows-kept", "old": '"NOTCOLD" not in (r.get("flags") or [])', "new": '"NOTCOLD" in (r.get("flags") or [])',
     "expect": "test_a_notcold_row_is_left_out_of_its_cells_mean_and_its_digest_is_kept"},
    {"name": "flagged-digest-dropped", "old": '        for r in c:\n            dig[("cold", size, r.get("rep"))]', "new": '        for r in cold:\n            dig[("cold", size, r.get("rep"))]',
     "expect": "test_a_notcold_row_is_left_out_of_its_cells_mean_and_its_digest_is_kept"},
    {"name": "all-flagged-cell-falls-back-to-every-row", "old": '        if cold:\n            val[("cold", size)] = st.mean(r["ttft_ms"] for r in cold)',
     "new": '        if c:\n            val[("cold", size)] = st.mean(r["ttft_ms"] for r in (cold or c))',
     "expect": "test_a_cell_whose_requests_are_all_notcold_has_no_value_but_keeps_its_digests"},
    {"name": "all-flagged-cell-digests-lost", "old": "        if cold:\n            val[", "new": "        if not cold:\n            continue\n        if cold:\n            val[",
     "expect": "test_a_cell_whose_requests_are_all_notcold_has_no_value_but_keeps_its_digests"},
    {"name": "mean-over-every-row-while-the-guard-uses-cold", "old": 'st.mean(r["ttft_ms"] for r in cold)', "new": 'st.mean(r["ttft_ms"] for r in c)',
     "expect": "test_a_notcold_control_boot_does_not_make_the_new_stack_look_slower"},
]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def run(test, scorer, timeout=1800):
    env = dict(os.environ, SCORE91=str(scorer))
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
    print(f"score91.py sha256 before the batch: {before}")
    (ROOT / "work").mkdir(exist_ok=True)
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutants91-", dir=ROOT / "work"))
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
        print(f"\n{'#':>3}  {'mutant':42} {'expected test':84} verdict")
        for i, name, expect, hit, errored, verdict in rows:
            print(f"{i:>3}  {name:42} {expect:84} {verdict}")
        after = sha(scorer)
        print(f"\nscore91.py sha256 after the batch:  {after}" + (" (unchanged)" if after == before else " (CHANGED: the batch edited the scorer)"))
        print(f"\n{len(MUTANTS)} mutants, {len(MUTANTS) - bad} killed, {bad} not killed; control passed")
        return 0 if bad == 0 and after == before else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
