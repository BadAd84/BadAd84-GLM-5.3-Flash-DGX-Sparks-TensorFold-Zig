"""check-spark-sync.py: a file the box holds differently, or lacks, fails the gate; a file the repo does not author is ignored."""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("check_spark_sync", os.path.join(os.path.dirname(HERE), "check-spark-sync.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CompareTest(unittest.TestCase):
    def test_equal_files_pass(self):
        lines, ok = mod.compare({"serve.sh": "aaaa"}, {"serve.sh": "aaaa"})
        self.assertTrue(ok)
        self.assertEqual(lines, ["same   serve.sh aaaa"])

    def test_a_stale_copy_fails(self):
        lines, ok = mod.compare({"serve.sh": "aaaa"}, {"serve.sh": "bbbb"})
        self.assertFalse(ok)
        self.assertEqual(lines, ["STALE  serve.sh: box bbbb, repo aaaa"])

    def test_a_missing_file_fails(self):
        lines, ok = mod.compare({"serve.sh": "aaaa"}, {})
        self.assertFalse(ok)
        self.assertIn("not on the box", lines[0])

    def test_a_file_the_repo_does_not_author_is_ignored(self):
        lines, ok = mod.compare({}, {"serve.sh": "bbbb"})
        self.assertTrue(ok)
        self.assertEqual(lines, [])

    def test_line_endings_do_not_matter(self):
        self.assertEqual(mod.digest(b"a\r\nb\r\n"), mod.digest(b"a\nb\n"))


if __name__ == "__main__":
    unittest.main()
