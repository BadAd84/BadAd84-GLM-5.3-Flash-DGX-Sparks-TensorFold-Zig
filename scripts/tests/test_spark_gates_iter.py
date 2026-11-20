#!/usr/bin/env python3
"""test_spark_gates_iter.py: which step names scripts/spark-gates.py iter accepts, and what the host-side script does with a zig:STEP one.

The step names are substituted into a shell `for` line on the gate host, so a name that is not a plain build-step name must be refused before anything is shipped.
Run from the top-level shell: python scripts/tests/test_spark_gates_iter.py
"""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("spark_gates", ROOT / "scripts/spark-gates.py")
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)


class IterSteps(unittest.TestCase):
    def test_the_named_steps_are_accepted(self):
        for s in sg.ITER_STEPS:
            self.assertTrue(sg.valid_step(s), s)

    def test_a_build_step_of_the_tree_is_accepted(self):
        for s in ("zig:test-glm-keep-seqs-host", "zig:test-rows-host", "zig:a", "zig:0x"):
            self.assertTrue(sg.valid_step(s), s)

    def test_anything_that_is_not_a_plain_step_name_is_refused(self):
        for s in ("zig:", "zig:-x", "zig:Test", "zig:a b", "zig:a;touch x", "zig:a;id", "zig:a$IFS", "zig:a*", "zig:$(id)", "zig:a`id`", "zig:../x", "zig:a\nb", "zig:a&b", "zig:a|b", "zig:a>b", "zig:a'b",
                  "zig :a", "ZIG:a", " zig:a", "zig:a ", "bogus", "", "test;id"):
            self.assertFalse(sg.valid_step(s), repr(s))

    def test_the_host_script_runs_zig_build_for_a_zig_step_and_logs_it_by_name(self):
        t = sg.ITER_RUN
        self.assertIn("zig:*)", t)
        self.assertIn('st=${s#zig:}', t)
        self.assertIn('"$Z" build "$st" -j@JOBS@', t)
        self.assertIn('"$IT/zig-$st.log"', t)
        branch = t[t.index("zig:*)"):t.index("lean)", t.index("zig:*)"))]
        self.assertIn("rc=$?", branch)


if __name__ == "__main__":
    unittest.main(verbosity=1)
