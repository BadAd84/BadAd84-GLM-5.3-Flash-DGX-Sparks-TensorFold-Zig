"""test_score106.py - score106.py's rules on fixtures in the real row layout (dec-<label>/<KIND><n>.jsonl with agg_tok_s and a sha list), read through score91's boot().
Run: python scripts/tests/test_score106.py"""
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
spec = importlib.util.spec_from_file_location("score106", ROOT / "scripts/queue-scores/score106.py")
s106 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s106)
CELLS = [("SP", 6), ("SC", 6), ("SP", 8), ("SC", 8)]
ON = [f"on{i}" for i in range(1, 5)]
OFF = [f"off{i}" for i in range(1, 5)]


def build(dirp, off_val=100.0, on_val=100.0, on_cells=None, sha=None, missing=None):
    """Every boot at `off_val`, the on group at `on_val`; `one` = (label, kind, n, value) moves a single boot's cell; `sha` = (label, kind, n, digest)."""
    for label in ON + OFF:
        d = pathlib.Path(dirp) / f"dec-{label}"
        d.mkdir(parents=True, exist_ok=True)
        for kind, n in CELLS:
            if missing == (label, kind, n):
                continue
            v = on_val if label.startswith("on") else off_val
            if on_cells and label.startswith("on") and (kind, n) in on_cells:
                v = on_cells[(kind, n)]
            digest = ["aa"]
            if sha and sha[:3] == (label, kind, n):
                digest = sha[3]
            (d / f"{kind}{n}.jsonl").write_text(json.dumps({"tag": f"{label}-{kind}{n}", "round": 0, "agg_tok_s": v, "sha": digest}) + "\n", encoding="utf-8")


class Rules(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="score106-", dir=ROOT / "work")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_score(self):
        buf, old = io.StringIO(), sys.argv
        sys.argv = ["score106.py", "--q106", self.d]
        try:
            with contextlib.redirect_stdout(buf):
                rc = s106.main()
        finally:
            sys.argv = old
        return rc, buf.getvalue()

    def test_a_clear_gain_keeps_the_knob(self):
        build(self.d, on_val=102.0)
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("KEEP THE KNOB", out)

    def test_no_difference_removes_the_knob(self):
        build(self.d)
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("REMOVE IT", out)

    def test_a_cell_slower_with_the_knob_holds(self):
        build(self.d, on_val=102.0, on_cells={("SP", 8): 96.0})  # the whole on group slower in that cell
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("HOLD", out)
        self.assertIn("sampled prose", out)

    def test_a_small_gain_is_not_decided(self):
        build(self.d, on_val=100.5)
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("NOT DECIDED", out)

    def test_a_digest_difference_exits_one(self):
        build(self.d, on_val=102.0, sha=("off2", "SC", 8, ["different"]))
        rc, out = self.run_score()
        self.assertEqual(rc, 1)
        self.assertIn("DIGESTS DIFFER", out)

    def test_a_missing_boot_is_not_decided(self):
        build(self.d, on_val=102.0, missing=("on4", "SC", 6))
        rc, out = self.run_score()
        self.assertEqual(rc, 0)
        self.assertIn("NOT DECIDED", out)
        self.assertNotIn("KEEP THE KNOB", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
