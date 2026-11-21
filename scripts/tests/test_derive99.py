"""test_derive99.py - derive99.py's parsers and arithmetic on score99-format lines and on a fixture row directory built here (a report script: these tests pin its parsing and sums)."""
import contextlib
import importlib.util
import io
import json
import pathlib
import shutil
import statistics
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("derive99", ROOT / "scripts/queue-scores/derive99.py")
d99 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d99)

C1_DEC = "greedy code at 8 clients: CA mean 176.9 (boots 180.0 173.9) | CE mean 174.3 (boots 173.3 175.3) | +1.49% slower  <- over the limit (CE 173.3..175.3)"
C1_FAST = "greedy prose at 6 clients: CA mean 118.3 (boots 111.6 125.1) | CE mean 122.6 (boots 121.8 123.3) | -3.55% slower"
C1_COLD = "cold 8k first token: CA mean 4052.5 (boots 4087.0 4018.0) | CE mean 3995.2 (boots 3991.5 3999.0) | -1.41% slower"
C1_ONE = "greedy prose at 1 clients: CA mean 82.7 (boots 82.6 82.7) | CE mean 82.2 (boots 82.8 81.5) | +0.59% slower"
SCORE = ["== score99: q99 x", "== C1 sync: CE against CA", C1_COLD, C1_ONE, C1_FAST, C1_DEC, "C1 SYNC: NOT ACCEPTED", "== C2 prompt cells: x", "ignored line",
         "== C3 boot noise: x", "greedy prose at 1 clients: CA spread 0.12% of mean | CE spread 1.55% of mean", "greedy prose at 6 clients: CA spread 11.47% of mean | CE spread 1.29% of mean",
         "cold 8k first token: CA spread 1.70% of mean | CE spread 0.19% of mean", "== C4 digests: x"]
LOG = ("info: prompt cache: 525 tokens, resumed at 0, kept 0; 1 states, 168 MiB and 7738 MiB spare of 7906 MiB (hits 0, misses 2, evicted 0, refused 0, failed 0, trimmed 0)\n"
       "info: prompt cache: 69644 tokens, resumed at 32768, kept 2; 11 states, 7262 MiB and 600 MiB spare of 7906 MiB (hits 7, misses 368, evicted 3, refused 0, failed 0, trimmed 1)\n")


class Parsing(unittest.TestCase):
    def test_c1_lines_give_the_four_boots_and_the_printed_percent(self):
        rows = d99.parse_c1(SCORE)
        self.assertEqual([r["cell"] for r in rows], ["cold 8k first token", "greedy prose at 1 clients", "greedy prose at 6 clients", "greedy code at 8 clients"])
        r = rows[-1]
        self.assertEqual((r["ca1"], r["ca2"], r["ce1"], r["ce2"], r["slower"]), (180.0, 173.9, 173.3, 175.3, 1.49))
        self.assertEqual(rows[2]["slower"], -3.55)

    def test_only_the_c1_block_is_read_for_c1_and_only_the_c3_block_for_spreads(self):
        self.assertEqual(len(d99.parse_c1(SCORE)), 4)
        self.assertEqual(d99.parse_c3(SCORE), [(1, 0.12), (1, 1.55), (6, 11.47), (6, 1.29)])  # the cold cell has no client count and is not a decode spread

    def test_clients_reads_the_level_or_none(self):
        self.assertEqual(d99.clients("sampled code at 6 clients"), 6)
        self.assertIsNone(d99.clients("cold 32k first token"))


class Arithmetic(unittest.TestCase):
    def test_group_stats_counts_slower_and_over_the_limit(self):
        n, lo, hi, mean, slower, over = d99.group_stats([-4.74, 0.5, 1.49, 2.41, -0.2])
        self.assertEqual((n, lo, hi, slower, over), (5, -4.74, 2.41, 3, 2))
        self.assertAlmostEqual(mean, statistics.mean([-4.74, 0.5, 1.49, 2.41, -0.2]))

    def test_a_value_exactly_at_the_limit_is_slower_but_not_over(self):
        self.assertEqual(d99.group_stats([1.0])[4:], (1, 0))

    def test_pair_changes_compare_the_adjacent_boots_of_the_abba_order(self):
        r = {"ca1": 180.0, "ce1": 173.3, "ce2": 175.3, "ca2": 173.9}
        p1, p2 = d99.pair_changes(r)
        self.assertAlmostEqual(p1, (180.0 / 173.3 - 1) * 100)
        self.assertAlmostEqual(p2, (173.9 / 175.3 - 1) * 100)
        self.assertGreater(p1, 0)
        self.assertLess(p2, 0)  # the second pair reverses: the policy arm is faster there


class Counters(unittest.TestCase):
    def test_counters_read_the_last_cache_line_and_the_facts_budget(self):
        (ROOT / "work").mkdir(exist_ok=True)
        d = pathlib.Path(tempfile.mkdtemp(prefix="derive99-", dir=ROOT / "work"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        (d / "rows.jsonl").write_text("".join(json.dumps({"tag": t, "case": "boot", "metrics": {"prompt_cache_budget_bytes": b}}) + "\n" for t, b in
                                              (("ca1", 8000), ("ce1", 8100), ("ce2", 8200), ("ca2", 8050))), encoding="utf-8")
        for tag in d99.BOOTS:
            (d / f"r0-{tag}.log").write_text(LOG, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            d99.print_counters(d, d99.load_d98())
        lines = buf.getvalue().splitlines()
        self.assertEqual(len(lines), 6)  # the header, four boots and the budget line
        for tag, line in zip(d99.BOOTS, lines[1:5]):
            f = line.split()
            self.assertEqual(f[0], tag)
            self.assertEqual([int(x) for x in f[2:]], [2, 11, 7262, 7, 368, 3, 1])  # log lines, then the last line's states, MiB held, hits, misses, evicted, trimmed
        self.assertEqual([line.split()[1] for line in lines[1:5]], ["8000", "8100", "8200", "8050"])
        self.assertIn("spread 2.50%", lines[5])  # 8200 over 8000


if __name__ == "__main__":
    unittest.main(verbosity=1)
