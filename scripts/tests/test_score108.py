"""test_score108.py - score108.py's rules on fixtures in the real report shape (a concurrent.json with `cells`, each carrying streams, aggregate_tps, ttft_s_max,
failed and reps[].requests[].prompt_tokens). Run: python scripts/tests/test_score108.py"""
import contextlib
import importlib.util
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("score108", ROOT / "scripts/queue-scores/score108.py")
s108 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s108)
ARMS = {a: list(l) for a, l in s108.ARMS.items()}


def build(dirp, c=(100.0, 10.0), arms=None, long_prompt=14336, failed=False, missing=None):
    """Every boot gets levels 4 and 8; `c` is the control's (aggregate_tps, ttft_s_max); `arms` maps an arm to its own pair."""
    arms = arms or {}
    for arm, labels in ARMS.items():
        pair = c if arm == "control" else arms.get(arm, c)
        for label in labels:
            if missing == label:
                continue
            d = pathlib.Path(dirp) / label
            d.mkdir(parents=True, exist_ok=True)
            cells = []
            for n in (4, 8):
                cells.append({"prompt": "mixed", "temperature": 1.0, "streams": n, "aggregate_tps": pair[0], "ttft_s_max": pair[1],
                              "failed": 1 if failed else 0,
                              "reps": [{"requests": [{"prompt_tokens": long_prompt if n == 8 else 2048, "ttft_s": pair[1]}]}]})
            (d / "concurrent.json").write_text(json.dumps({"cells": cells}), encoding="utf-8")


class Rules(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="score108-", dir=ROOT / "work")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_score(self):
        buf, old = io.StringIO(), sys.argv
        sys.argv = ["score108.py", "--q108", self.d]
        try:
            with contextlib.redirect_stdout(buf):
                rc = s108.main()
        finally:
            sys.argv = old
        return rc, buf.getvalue()

    def test_a_setting_that_holds_decode_and_cuts_the_wait_is_adopted(self):
        build(self.d, arms={"b512": (100.0, 6.0)})
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("ADOPT b512", out)

    def test_a_wait_gain_that_costs_decode_is_not_adopted(self):
        build(self.d, arms={"b2048": (97.0, 3.0)})  # 3% slower decode, 70% better wait
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("VERDICT: NONE", out)
        self.assertIn("decode -3.00%", out)

    def test_a_wait_gain_under_the_threshold_is_not_enough(self):
        build(self.d, arms={"s50": (100.0, 9.5)})  # only 5% better wait
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("VERDICT: NONE", out)

    def test_a_probe_that_never_mixed_a_long_prompt_is_not_decided(self):
        build(self.d, arms={"b512": (100.0, 6.0)}, long_prompt=4096)
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("NOT DECIDED", out)
        self.assertNotIn("ADOPT", out)

    def test_a_failed_cell_is_reported_and_blocks_nothing_silently(self):
        build(self.d, arms={"b512": (100.0, 6.0)}, failed=True)
        rc, out = self.run_score()
        self.assertIn("W1 clean", out)
        self.assertIn("c1@4", out)

    def test_a_missing_boot_is_not_decided(self):
        build(self.d, arms={"b512": (100.0, 6.0)}, missing="s50b")
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("NOT DECIDED", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
