#!/usr/bin/env python3
"""test_rounds_split.py: scripts/queue-scores/rounds_split.py on fixture rows shaped like scripts/streams.py's.

Run from the top-level shell: python scripts/tests/test_rounds_split.py
"""
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("rounds_split", ROOT / "scripts/queue-scores/rounds_split.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)


def write(d, unit, cell, rows):
    p = pathlib.Path(d) / f"dec-{unit}"
    p.mkdir(parents=True, exist_ok=True)
    with open(p / f"{cell}.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def row(rate, tpr, mpr, acc):
    return {"agg_tok_s": rate, "tok_per_round": tpr, "ms_per_round": mpr, "acceptance": acc}


class RoundsSplit(unittest.TestCase):
    def test_means_over_a_cells_rows(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "a", "C1", [row(100.0, 6.0, 50.0, 0.8), row(110.0, 6.2, 52.0, 0.9)])
            m = rs.load(d, "a", "C1")
            self.assertAlmostEqual(m["agg_tok_s"], 105.0)
            self.assertAlmostEqual(m["tok_per_round"], 6.1)
            self.assertAlmostEqual(m["ms_per_round"], 51.0)
            self.assertAlmostEqual(m["acceptance"], 0.85)
            self.assertEqual(m["rows"], 2)

    def test_absent_file_or_missing_field_is_none_never_zero(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(rs.load(d, "a", "C1"))
            write(d, "a", "C1", [{"agg_tok_s": 100.0, "tok_per_round": None, "ms_per_round": 50.0, "acceptance": 0.8}])
            self.assertIsNone(rs.load(d, "a", "C1"))

    def test_change_against_the_reference_names_which_factor_moved(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "ref", "C1", [row(100.0, 6.0, 50.0, 0.8)])
            write(d, "slow", "C1", [row(98.0, 6.0, 51.0, 0.8)])  # same tokens a round, longer rounds
            text = "\n".join(rs.report(d, ["ref", "slow"], ["C1"], "ref"))
            self.assertIn("rate -2.0%", text)
            self.assertIn("tok/round +0.0%", text)
            self.assertIn("ms/round +2.0%", text)
            self.assertNotIn("vs ref", text.splitlines()[0])  # the reference line carries no change against itself

    def test_a_unit_without_rows_is_reported_not_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "ref", "C1", [row(100.0, 6.0, 50.0, 0.8)])
            text = "\n".join(rs.report(d, ["ref", "gone"], ["C1"], "ref"))
            self.assertIn("gone  no rows", text)


if __name__ == "__main__":
    unittest.main()
