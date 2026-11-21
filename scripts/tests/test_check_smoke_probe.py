#!/usr/bin/env python3
"""test_check_smoke_probe.py: check_smoke_probe.py on scripts written here in queue92.sh's shape, and on the real queue scripts (run from the top-level shell)."""
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
_OVER = os.environ.get("CHECK_SMOKE_PROBE")
CHECKER = pathlib.Path(_OVER) if _OVER else ROOT / "scripts/tests/check_smoke_probe.py"
spec = importlib.util.spec_from_file_location("check_smoke_probe", CHECKER)
chk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chk)

SMOKE = "smoke() {{ # the first boot only\n  python3 longctx.py probe 8300 --tag smoke --seed {seed} --cold-sizes {sizes} --reps 1\n  python3 longctx.py chain 8300 x --salt smk\n}}\n"
UNIT = "unit() {{\n  python3 longctx.py probe 8300 --tag \"$label\" --seed {seed} --cold-sizes {sizes} --reps 2\n}}\n"


def script(smoke=("pf74", "8000"), unit=("pf74", "8000,32000,120000")):
    return (SMOKE.format(seed=smoke[0], sizes=smoke[1]) if smoke else "") + (UNIT.format(seed=unit[0], sizes=unit[1]) if unit else "")


class Findings(unittest.TestCase):
    def test_a_shared_seed_and_size_is_found_with_both_line_numbers(self):
        f = chk.findings(script())
        self.assertEqual(f, [(2, 6, "pf74", [8000])])

    def test_the_same_seed_with_no_common_size_is_fine(self):
        self.assertEqual(chk.findings(script(smoke=("pf74", "4000"))), [])

    def test_a_different_seed_with_the_same_sizes_is_fine(self):
        self.assertEqual(chk.findings(script(smoke=("smk", "8000"))), [])

    def test_a_probe_without_flags_uses_the_probes_own_defaults(self):
        text = "smoke() {\n  python3 longctx.py probe 8300 --tag smoke\n}\nunit() {\n  python3 longctx.py probe 8300 --tag u --reps 2\n}\n"
        f = chk.findings(text)
        self.assertEqual([(a, b, c) for a, b, c, _ in f], [(2, 5, "lc1")])
        self.assertEqual(f[0][3], [1000, 8000, 32000, 120000])

    def test_a_default_smoke_against_a_named_seed_is_fine(self):
        text = "smoke() {\n  python3 longctx.py probe 8300 --tag smoke\n}\nunit() {\n  python3 longctx.py probe 8300 --tag u --seed pf74\n}\n"
        self.assertEqual(chk.findings(text), [])

    def test_two_unit_probes_that_share_a_seed_and_size_are_not_a_finding(self):
        text = script(smoke=("smk", "8000"), unit=("pf74", "8000")) + UNIT.format(seed="pf74", sizes="8000")
        self.assertEqual(chk.findings(text), [])  # only a probe inside smoke() is held against the others

    def test_every_overlapping_unit_probe_is_reported(self):
        text = SMOKE.format(seed="pf74", sizes="8000,32000") + UNIT.format(seed="pf74", sizes="32000") + UNIT.format(seed="pf74", sizes="8000") + UNIT.format(seed="x", sizes="8000")
        self.assertEqual([(a, c) for a, _, c, _ in chk.findings(text)], [(2, "pf74"), (2, "pf74")])
        self.assertEqual([b for _, b, _, _ in chk.findings(text)], [6, 9])

    def test_a_commented_probe_is_not_a_probe(self):
        text = "smoke() {\n  python3 longctx.py probe 8300 --seed smk --cold-sizes 8000\n}\n# python3 longctx.py probe 8300 --seed smk --cold-sizes 8000\n"
        self.assertEqual(chk.findings(text), [])

    def test_a_script_without_a_smoke_has_no_findings(self):
        self.assertEqual(chk.findings(script(smoke=None)), [])


class Cli(unittest.TestCase):
    def run_on(self, name, text):
        d = pathlib.Path(tempfile.mkdtemp(prefix="chk-smoke-", dir=ROOT / "work"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        (d / name).write_text(text, encoding="utf-8", newline="\n")
        r = subprocess.run([sys.executable, str(CHECKER), str(d / name)], capture_output=True, text=True, cwd=str(ROOT))
        return r.returncode, r.stdout

    def setUp(self):
        (ROOT / "work").mkdir(exist_ok=True)

    def test_exit_one_and_a_FAIL_line_naming_the_file_and_both_lines(self):
        rc, out = self.run_on("queueXX.sh", script())
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: ", out)
        self.assertIn("queueXX.sh:2 the smoke probe shares seed pf74 and sizes [8000] with the unit probe at line 6", out)

    def test_exit_zero_when_nothing_is_shared(self):
        rc, out = self.run_on("queueXX.sh", script(smoke=("smk", "8000")))
        self.assertEqual(rc, 0, out)
        self.assertIn("ok: ", out)

    def test_the_allowlisted_script_is_reported_and_does_not_fail(self):
        rc, out = self.run_on("queue99.sh", script())
        self.assertEqual(rc, 0, out)
        self.assertIn("allowed: ", out)
        self.assertIn("score91 leaves its NOTCOLD row out", out)

    def test_the_same_text_under_another_name_still_fails(self):
        rc, out = self.run_on("queue98.sh", script())
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: ", out)
        self.assertNotIn("allowed", out)

    def test_the_real_queue_scripts_pass(self):
        r = subprocess.run([sys.executable, str(CHECKER)], capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertRegex(r.stdout, r"allowed: scripts[/\\]queues[/\\]queue99\.sh")


if __name__ == "__main__":
    unittest.main(verbosity=2)
