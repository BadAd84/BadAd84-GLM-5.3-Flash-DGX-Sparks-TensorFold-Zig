#!/usr/bin/env python3
"""test_score92.py: scripts/queue-scores/score92.py's ladder, PR-candidate rule and stack comparison on fixture row directories laid out as the queues write them.

Run from the top-level shell: python scripts/tests/test_score92.py
"""
import importlib.util
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


t91 = load("test_score91", "scripts/tests/test_score91.py")
s92 = load("score92", "scripts/queue-scores/score92.py")

LADDER = ("s9a", "s9b", "s10a", "s13a", "s13b", "ud1", "ui1", "sm2", "sm3")
MAIN = ("sm2", "sm3")


class Fixture:
    def __init__(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="score92-", dir=ROOT / "work"))
        self.q91, self.q92 = self.root / "q91", self.root / "q92"

    def boot(self, where, label, **kw):
        t91.write_boot(where, label, **kw)
        return self

    def base(self, **over):
        """Every ladder boot at scale 1, mps in q91, mn1 and mn2 (the stack) too; `over` maps a label to write_boot kwargs."""
        self.boot(self.q91, "mps", **over.get("mps", {}))
        for label in LADDER:
            self.boot(self.q92, label, **over.get(label, {}))
        for label in ("mn1", "mn2"):
            self.boot(self.q91, label, **over.get(label, {"dec": 1.10, "cold": 0.90, "warm": 0.60}))
        for label, _ in s92.ARMS + s92.ATTRIBUTION:
            if label in over:
                self.boot(self.q92, label, **over[label])
        return self

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Score92(unittest.TestCase):
    def fx(self, **over):
        f = Fixture().base(**over)
        self.addCleanup(f.close)
        return f

    def ladder(self, f):
        return s92.ladder(str(f.q91), str(f.q92))

    def arm(self, f, label="pd"):
        return s92.arm([(str(f.q92), label)], s92.main_boots(str(f.q91), str(f.q92)))

    def text(self, lines):
        return "\n".join(lines)

    # the ladder
    def test_clear_gain_when_every_boot_is_beyond_the_rung_before(self):
        f = self.fx(s9a={"dec": 1.00}, s9b={"dec": 1.01}, s10a={"dec": 1.03})
        lines, verdict = self.ladder(f)
        self.assertEqual(verdict, "LADDER: complete")
        row = [l for l in lines if l.startswith("greedy prose at 1 clients") and "CLEAR gain" in l]
        self.assertTrue(row, self.text(lines))

    def test_a_step_inside_the_spread_is_a_number_and_not_a_gain(self):
        f = self.fx(s9a={"dec": 1.00}, s9b={"dec": 1.02}, s10a={"dec": 1.015})
        lines, _ = self.ladder(f)
        first = [l for l in lines if l.startswith("-- v1.2.10")][0]
        block = lines[lines.index(first) + 1:]
        row = [l for l in block if l.startswith("greedy prose at 1 clients")][0]
        self.assertNotIn("CLEAR", row)
        self.assertIn("+0.5", row.split(":")[1])

    def test_a_clear_loss_is_named_for_latency_too(self):
        f = self.fx(s13a={"cold": 1.04}, s13b={"cold": 1.05}, s10a={"cold": 1.00})
        lines, _ = self.ladder(f)
        start = lines.index([l for l in lines if l.startswith("-- v1.3.0")][0])
        row = [l for l in lines[start:] if l.startswith("cold 8k")][0]
        self.assertIn("CLEAR loss", row)
        self.assertIn("-4.5", row)

    def test_a_clear_gain_in_latency_is_named(self):
        f = self.fx(s10a={"cold": 1.00}, s13a={"cold": 0.95}, s13b={"cold": 0.96})
        lines, _ = self.ladder(f)
        start = lines.index([l for l in lines if l.startswith("-- v1.3.0")][0])
        row = [l for l in lines[start:] if l.startswith("cold 8k")][0]
        self.assertIn("CLEAR gain", row)
        self.assertIn("+4.5", row)

    def test_the_pdl_and_item_plan_rungs_sit_between_v130_and_main(self):
        f = self.fx(s13a={"dec": 1.00}, s13b={"dec": 1.00}, ud1={"dec": 1.06}, ui1={"dec": 1.09}, sm2={"dec": 1.09}, sm3={"dec": 1.09}, mps={"dec": 1.09})
        lines, _ = self.ladder(f)
        heads = [l for l in lines if l.startswith("-- ")]
        self.assertEqual([h.split(" against ")[0] for h in heads], ["-- v1.2.10", "-- v1.3.0", "-- PDL in (3661a4281)", "-- item plan in (32c361db9)", "-- main 1ece6e6"])
        start = lines.index([l for l in lines if l.startswith("-- PDL in")][0])
        row = [l for l in lines[start:] if l.startswith("greedy prose at 1 clients")][0]
        self.assertIn("+6.00% (cumulative +6.00%)", row)

    def test_the_pdl_attribution_arm_is_read_against_the_main_group(self):
        f = self.fx(smz={"dec": 0.90})
        lines, verdict = s92.arm([(str(f.q92), "smz")], s92.main_boots(str(f.q91), str(f.q92)))
        self.assertIn("greedy prose at 1 clients: -10.00% against the mean", " ".join(lines))

    def test_missing_rung_is_not_decided(self):
        f = Fixture()
        self.addCleanup(f.close)
        f.boot(f.q91, "mps")
        for label in LADDER:
            if label != "s13b":
                f.boot(f.q92, label)
        _, verdict = self.ladder(f)
        self.assertTrue(verdict.startswith("NOT DECIDED"), verdict)
        self.assertIn("s13b", verdict)

    def test_digest_change_between_rungs_is_counted(self):
        f = self.fx(s13a={"digest": "b"}, s13b={"digest": "b"}, sm2={"digest": "b"}, sm3={"digest": "b"}, mps={"digest": "b"})
        lines, _ = self.ladder(f)
        row = [l for l in lines if l.startswith("reply digests v1.2.10 -> v1.3.0")][0]
        self.assertNotIn(": 0 key", row)
        same = [l for l in lines if l.startswith("reply digests v1.2.9 -> v1.2.10")][0]
        self.assertIn(": 0 key", same)

    def test_main_group_takes_mps_from_the_queue91_rows(self):
        f = self.fx(mps={"dec": 1.00}, sm2={"dec": 1.00}, sm3={"dec": 1.00}, s13a={"dec": 1.00}, s13b={"dec": 1.00})
        self.assertEqual([lab for _, lab in s92.main_boots("a", "b")], ["mps", "sm2", "sm3"])
        self.assertEqual(s92.main_boots("a", "b")[0][0], "a")
        lines, verdict = self.ladder(f)
        self.assertEqual(verdict, "LADDER: complete")

    def test_cumulative_is_against_v129_and_the_step_against_the_rung_before(self):
        f = self.fx(s9a={"dec": 1.00}, s9b={"dec": 1.00}, s10a={"dec": 1.02}, s13a={"dec": 1.04}, s13b={"dec": 1.04}, sm2={"dec": 1.04}, sm3={"dec": 1.04}, mps={"dec": 1.04})
        lines, _ = self.ladder(f)
        start = lines.index([l for l in lines if l.startswith("-- v1.3.0")][0])
        row = [l for l in lines[start:] if l.startswith("greedy prose at 1 clients")][0]
        self.assertIn("+1.96% (cumulative +4.00%)", row)

    # the pull request rule
    def test_candidate_when_faster_than_the_best_boot_and_nothing_slower(self):
        f = self.fx(sm2={"dec": 1.000}, sm3={"dec": 1.004}, mps={"dec": 0.998}, pd={"dec": 1.03})
        _, verdict = self.arm(f)
        self.assertTrue(verdict.startswith("CANDIDATE"), verdict)

    def test_one_slow_cell_makes_it_not_a_candidate_and_names_it(self):
        f = self.fx(pd={"dec": 1.03, "cold": 1.02})
        _, verdict = self.arm(f)
        self.assertTrue(verdict.startswith("NOT A CANDIDATE"), verdict)
        self.assertIn("cold 8k first token -2.00%", verdict)

    def test_equal_to_main_is_not_a_candidate(self):
        f = self.fx(pd={})
        _, verdict = self.arm(f)
        self.assertIn("no cell faster than the best reference boot", verdict)

    def test_a_gain_inside_the_main_groups_spread_is_not_a_gain(self):
        f = self.fx(sm2={"dec": 1.00}, sm3={"dec": 1.03}, mps={"dec": 0.99}, pd={"dec": 1.02})
        _, verdict = self.arm(f)
        self.assertTrue(verdict.startswith("NOT A CANDIDATE"), verdict)
        self.assertIn("no cell faster", verdict)

    def test_a_different_reply_digest_is_not_a_candidate(self):
        f = self.fx(pd={"dec": 1.03, "digest": "z"})
        _, verdict = self.arm(f)
        self.assertTrue(verdict.startswith("NOT A CANDIDATE"), verdict)
        self.assertIn("reply digest", verdict)

    def test_a_gain_only_at_six_and_eight_clients_does_not_count(self):
        f = self.fx(pd={"dec": 1.00})
        for kind in t91.DEC:
            for n in (6, 8):
                p = f.q92 / "dec-pd" / f"{kind}{n}.jsonl"
                lines = [l.replace(f'"agg_tok_s": {t91.DEC[kind] * n ** 0.5}', f'"agg_tok_s": {t91.DEC[kind] * n ** 0.5 * 1.05}') for l in p.read_text().splitlines()]
                p.write_text("\n".join(lines) + "\n")
        _, verdict = self.arm(f)
        self.assertTrue(verdict.startswith("NOT A CANDIDATE"), verdict)
        self.assertIn("no cell faster", verdict)

    def test_missing_arm_rows_are_not_decided(self):
        f = self.fx()
        _, verdict = self.arm(f, "pg")
        self.assertTrue(verdict.startswith("NOT DECIDED"), verdict)

    def test_an_arm_with_only_some_cells_is_not_decided(self):
        f = self.fx()
        f.boot(f.q92, "pd", only="cold", cold=0.90)
        _, verdict = self.arm(f)
        self.assertTrue(verdict.startswith("NOT DECIDED"), verdict)
        self.assertIn("have no rows", verdict)

    def test_a_warm_turn_gain_alone_makes_a_candidate(self):
        f = self.fx(pd={"warm": 0.60})
        _, verdict = self.arm(f)
        self.assertTrue(verdict.startswith("CANDIDATE"), verdict)
        self.assertIn("conversation turns 2+ first token +40.00%", verdict)

    # the stack
    def test_stack_takes_the_mean_of_both_stack_boots(self):
        f = self.fx(mn1={"dec": 1.10}, mn2={"dec": 1.20})
        _, v = s92.stack(str(f.q91))
        self.assertAlmostEqual(s92.gain(("dec", "P", 1), sum(v[("dec", "P", 1)]) / len(v[("dec", "P", 1)]), 80.0), 0.15, places=3)
        self.assertEqual(len(v[("dec", "P", 1)]), 2)

    def test_stack_cells_are_the_stack_against_the_main_group(self):
        f = self.fx()
        miss, v = s92.stack(str(f.q91))
        self.assertEqual(miss, [])
        self.assertAlmostEqual(s92.gain(("dec", "P", 1), sum(v[("dec", "P", 1)]) / 2, 80.0), 0.10, places=3)


if __name__ == "__main__":
    unittest.main(verbosity=1)
