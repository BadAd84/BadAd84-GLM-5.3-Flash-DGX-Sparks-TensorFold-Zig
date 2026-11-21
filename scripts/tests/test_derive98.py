"""test_derive98.py - derive98.py's parsers and arithmetic on lines and rows in the formats the engine and the client write (a report script: these pin its parsing and sums)."""
import importlib.util
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("derive98", HERE.parent / "queue-scores" / "derive98.py")
d98 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d98)

LINE_A = "info: prompt cache: 65548 tokens, resumed at 0, kept 3; 4 states, 1448 MiB and 6458 MiB spare of 7906 MiB (hits 0, misses 4, evicted 0, refused 0, failed 0, trimmed 0)"
LINE_B = "info: prompt cache: 69644 tokens, resumed at 32768, kept 2; 10 states, 4398 MiB and 3508 MiB spare of 7906 MiB (hits 1, misses 6, evicted 2, refused 0, failed 0, trimmed 3)"
LOG = ["[q98] 07:02:17 ce-A E3 trace (6 conversations, 24 rounds, prefix 32768, seed 11) rc=0 wall=6709s: qualified True",
       "[q98] 08:04:42 ce-B E3 trace (6 conversations, 24 rounds, prefix 32768, seed 11) rc=0 wall=3591s: qualified True",
       "[q98] 08:04:42 compare rc=0: qualified True"]


def report(rows):
    return {"rows": [{"kind": k, "prompt_tokens": p, "cached_tokens": c, "ttft_s": t} for k, p, c, t in rows]}


class Parsing(unittest.TestCase):
    def test_a_cache_line_gives_every_field_in_order(self):
        r = d98.parse_cache_line(LINE_B)
        self.assertEqual((r["tokens"], r["resumed_at"], r["kept"], r["states"], r["held_mib"], r["spare_mib"], r["budget_mib"]), (69644, 32768, 2, 10, 4398, 3508, 7906))
        self.assertEqual((r["hits"], r["misses"], r["evicted"], r["refused"], r["failed"], r["trimmed"]), (1, 6, 2, 0, 0, 3))

    def test_a_line_that_is_not_a_cache_line_is_none_and_is_dropped_from_the_rows(self):
        self.assertIsNone(d98.parse_cache_line("info: something else entirely"))
        self.assertEqual(len(d98.cache_rows([LINE_A, "info: other", LINE_B])), 2)

    def test_walls_read_each_arms_client_rc_and_seconds(self):
        w = d98.walls(LOG)
        self.assertEqual(w, {"ce-A": (0, 6709), "ce-B": (0, 3591)})

    def test_split_rows_sums_the_rebuilt_rows_and_ttft_of_each_kind_apart(self):
        s = d98.split_rows(report([("agent", 1000, 400, 2.0), ("one_off", 500, 0, 1.5), ("agent", 1200, 1000, 0.5), ("one_off", 300, 0, 1.0)]))
        self.assertEqual(s["agent"], (2, 600 + 200, 2.5))
        self.assertEqual(s["one_off"], (2, 800, 2.5))

    def test_change_is_the_fraction_lower_and_positive_for_less(self):
        self.assertAlmostEqual(d98.change(200, 100), 0.5)
        self.assertAlmostEqual(d98.change(100, 150), -0.5)


if __name__ == "__main__":
    unittest.main(verbosity=1)
