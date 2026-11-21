"""test_chaindec.py - chaindec.py's turn selection, boot lookup and group arithmetic on chain rows in longctx.py's format (fields built here)."""
import importlib.util
import json
import pathlib
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("chaindec", HERE.parent / "queue-scores" / "chaindec.py")
cd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cd)


def row(rate, cached, completion=128, prompt=114000):
    return {"decode_tok_s": rate, "cached_tokens": cached, "completion_tokens": completion, "prompt_tokens": prompt}


def boot(root, tag, rows):
    d = pathlib.Path(root) / tag
    d.mkdir(parents=True)
    (d / "chain.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


class Selection(unittest.TestCase):
    def test_only_resumed_full_replies_with_a_rate_count(self):
        with tempfile.TemporaryDirectory() as t:
            boot(t, "a", [row(10.0, 0), row(70.0, 100000), row(80.0, 100000, completion=16), row(None, 100000), row(90.0, 100000, prompt=120000), row(50.0, 50000)])
            got = cd.resumed_turns(pathlib.Path(t) / "a" / "chain.jsonl")
            self.assertEqual(got, [(70.0, 114000), (90.0, 120000)])

    def test_boot_rate_gives_turns_mean_min_max_and_context_range(self):
        with tempfile.TemporaryDirectory() as t:
            boot(t, "a", [row(70.0, 100000, prompt=114000), row(90.0, 100000, prompt=120000), row(80.0, 100000, prompt=117000)])
            self.assertEqual(cd.boot_rate([t], "a"), (3, 80.0, 70.0, 90.0, 114000, 120000))

    def test_boot_rate_finds_a_tag_in_the_second_directory_and_none_when_absent(self):
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            boot(t2, "b", [row(60.0, 100000)])
            self.assertEqual(cd.boot_rate([t1, t2], "b")[1], 60.0)
            self.assertIsNone(cd.boot_rate([t1, t2], "zz"))


class Groups(unittest.TestCase):
    def test_group_line_reports_the_mean_of_means_and_the_spread_between_boots(self):
        line = cd.group_line("g", [70.0, 77.0])
        self.assertIn("2 boot(s)", line)
        self.assertIn("mean of means 73.50 tok/s", line)
        self.assertIn("spread between boots 10.00%", line)

    def test_a_group_of_one_boot_has_no_spread(self):
        self.assertIn("one boot, no spread", cd.group_line("g", [73.24]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
