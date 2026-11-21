"""test_derive92.py - derive92.py's parsers and means on lines in score92.py's printed format, built here (a report script: these tests pin its arithmetic and parsing only)."""
import importlib.util
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("derive92", HERE.parent / "queue-scores" / "derive92.py")
d92 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d92)

LADDER = """\
== the ladder: stock upstream at four points
-- v1.2.10 against v1.2.9 (and against v1.2.9)
cold 8k first token: +1.00% (cumulative +1.00%)  CLEAR gain
conversation turns 2+ first token: +3.00% (cumulative +3.00%)
greedy prose at 1 clients: +2.00% (cumulative +2.00%)  CLEAR gain
greedy prose at 6 clients: -4.00% (cumulative -4.00%)  CLEAR loss
sampled code at 8 clients: +0.50% (cumulative +0.50%)
reply digests v1.2.9 -> v1.2.10: 0 key(s) with more than one digest
-- v1.3.0 against v1.2.10 (and against v1.2.9)
cold 8k first token: -2.00% (cumulative -1.00%)  CLEAR loss
greedy prose at 1 clients: +1.00% (cumulative +3.00%)
LADDER: complete
"""

ARMS = """\
== smr: request starts on stock main against the main group; faster is positive
cold 8k first token: -0.10% against the mean, -1.00% against the best boot
conversation turns 2+ first token: +36.00% against the mean, +35.00% against the best boot
greedy prose at 1 clients: +2.00% against the mean, +0.00% against the best boot
greedy prose at 6 clients: -1.00% against the mean, -3.00% against the best boot
smr: NOT A CANDIDATE: 1 cell(s) more than 1% slower
== the stack on main (mn1 mn2) against the main group; faster is positive
cold 8k first token: +24.00%
greedy prose at 8 clients: +40.00%
"""


class Parsing(unittest.TestCase):
    def test_cell_group_names_the_three_groups_from_a_printed_cell(self):
        self.assertEqual(d92.cell_group("cold 120k first token"), "PROMPT")
        self.assertEqual(d92.cell_group("conversation turns 2+ first token"), "PROMPT")
        self.assertEqual(d92.cell_group("sampled code at 4 clients"), "D124")
        self.assertEqual(d92.cell_group("greedy prose at 6 clients"), "D68")
        self.assertEqual(d92.cell_group("greedy code at 8 clients"), "D68")

    def test_the_ladder_parser_keeps_each_rung_its_own_cells_and_marks(self):
        rungs = d92.parse_ladder(LADDER.splitlines())
        self.assertEqual(list(rungs), ["v1.2.10", "v1.3.0"])
        self.assertEqual(len(rungs["v1.2.10"]), 5)
        self.assertEqual(len(rungs["v1.3.0"]), 2)
        marks = [c[3] for c in rungs["v1.2.10"]]
        self.assertEqual(marks, ["gain", None, "gain", "loss", None])

    def test_ladder_means_are_per_group_and_count_clear_marks(self):
        ps, pc, ds, dc, as_, ac, gains, losses = d92.ladder_means(d92.parse_ladder(LADDER.splitlines())["v1.2.10"])
        self.assertAlmostEqual(ps, 2.0)
        self.assertAlmostEqual(ds, 2.0)
        self.assertAlmostEqual(as_, (2.0 - 4.0 + 0.5) / 3)
        self.assertEqual((gains, losses), (2, 1))

    def test_the_arm_parser_reads_both_line_shapes_and_stops_at_the_next_section(self):
        arms = d92.parse_arms(ARMS.splitlines())
        self.assertEqual(sorted(arms), ["smr", "the stack on main"])
        self.assertEqual([c[1] for c in arms["smr"]], [-0.10, 36.00, 2.00, -1.00])
        self.assertEqual([c[2] for c in arms["smr"]], [-1.00, 35.00, 0.00, -3.00])
        self.assertEqual([c[1] for c in arms["the stack on main"]], [24.00, 40.00])
        self.assertTrue(all(c[2] is None for c in arms["the stack on main"]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
