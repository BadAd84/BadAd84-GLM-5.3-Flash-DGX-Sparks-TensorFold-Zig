"""test_score105.py - score105.py's rules on fixtures built in the real row layout (dec-<label>/<KIND>8.jsonl rows with agg_tok_s and a sha list), read through
score91's own boot(), so a fixture shape that differs from the queue's cannot pass here and fail there. Run: python scripts/tests/test_score105.py"""
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
spec = importlib.util.spec_from_file_location("score105", ROOT / "scripts/queue-scores/score105.py")
s105 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s105)
CELLS = ("P", "C", "SP", "SC")
CA = [f"ca{i}" for i in range(1, 5)]
TX = [f"tx{i}" for i in range(1, 5)]


def build(dirp, slow=None, sha_override=None, missing=None):
    """Four boots a group at 100 tok/s. `slow` = (label, kind, value) moves ONE boot of one cell, so a four-boot mean moves a quarter of the way.
    `sha_override` = (label, kind, digest list). `missing` = (label, kind) leaves that file out."""
    for label in CA + TX:
        d = pathlib.Path(dirp) / f"dec-{label}"
        d.mkdir(parents=True, exist_ok=True)
        for kind in CELLS:
            if missing == (label, kind):
                continue
            v = 100.0
            if slow and label == slow[0] and kind == slow[1]:
                v = slow[2]
            sha = ["aa"]
            if sha_override and label == sha_override[0] and kind == sha_override[1]:
                sha = sha_override[2]
            (d / f"{kind}8.jsonl").write_text(json.dumps({"tag": f"{label}-{kind}8", "round": 0, "agg_tok_s": v, "sha": sha}) + "\n", encoding="utf-8")


class Rules(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="score105-", dir=ROOT / "work")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_score(self):
        buf = io.StringIO()
        old = sys.argv
        sys.argv = ["score105.py", "--q105", self.d]
        try:
            with contextlib.redirect_stdout(buf):
                rc = s105.main()
        finally:
            sys.argv = old
        return rc, buf.getvalue()

    def test_a_clean_run_promotes(self):
        build(self.d)
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("Q4 VERDICT: PROMOTE T AND X", out)
        self.assertIn("missing: none", out)
        self.assertIn("Q2 digests: 0 cell(s)", out)

    def test_one_cell_past_the_limit_holds_and_names_it(self):
        build(self.d, slow=("tx3", "SC", 106.0))  # the four-boot mean moves to 101.5, +1.5% slower
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("Q4 VERDICT: HOLD", out)
        self.assertIn("sampled code", out)
        self.assertNotIn("PROMOTE", out)

    def test_a_cell_exactly_at_the_limit_is_not_over_it(self):
        build(self.d, slow=("tx1", "P", 104.0))  # the mean moves to 101.0, exactly +1.0%
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("Q4 VERDICT: PROMOTE T AND X", out)

    def test_a_differing_digest_fails_with_exit_1(self):
        build(self.d, sha_override=("tx2", "C", ["different"]))
        rc, out = self.run_score()
        self.assertEqual(rc, 1)
        self.assertIn("DIGESTS DIFFER", out)

    def test_a_missing_boot_is_not_decided(self):
        build(self.d, missing=("tx4", "SP"))
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("NOT DECIDED", out)
        self.assertNotIn("PROMOTE", out)

    def test_equal_digest_lists_compare_equal(self):
        build(self.d)
        for kind in CELLS:
            for label in CA + TX:
                p = pathlib.Path(self.d) / f"dec-{label}" / f"{kind}8.jsonl"
                row = json.loads(p.read_text(encoding="utf-8"))
                row["sha"] = ["ab", "cd"]
                p.write_text(json.dumps(row) + "\n", encoding="utf-8")
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("Q2 digests: 0 cell(s)", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
