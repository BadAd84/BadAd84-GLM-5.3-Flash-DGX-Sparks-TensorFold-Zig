#!/usr/bin/env python3
"""test_score100.py: scripts/queue-scores/score100.py's C5 adoption reading, and its reuse of score99's C1-C4, on a fixture row tree laid out as queue100 writes it
(queue91's f91-c layout, one directory, four boots labelled ca1 ce1 ce2 ca2).

Run from the top-level shell: python scripts/tests/test_score100.py
SCORE100=<path> points the tests at a copy of the scorer (scripts/tests/mutants_score100.py runs them against each mutant that way).

The fixtures are test_score99.py's own builder (its Fixture and wboot, imported from that file so the row shape has one owner). The 5.0% threshold is probed directly at
enough(THRESHOLD) and bracketed through the fixtures at 4.9% and 5.1%: an exact 5.0% cannot be built by scaling in doubles (as score99's docstring notes for its 1.0% limit),
so a fixture at "exactly 5.0%" would pin the rounding of one multiplication, not the rule.
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_OVER = os.environ.get("SCORE100")
SCORER = pathlib.Path(_OVER) if _OVER else ROOT / "scripts/queue-scores/score100.py"
s100 = load("score100", SCORER)
T99 = load("test_score99", ROOT / "scripts/tests/test_score99.py")  # its Fixture and wboot: queue100's row shape, one owner
s99 = T99.s99
put = T99.put
LABELS = T99.LABELS
ACCEPTED = T99.ACCEPTED
NOT_WORTH = "NOT WORTH A SWITCH: warm turns only 4.9% faster"


class Fx(T99.Fixture):
    """queue100's one row directory: test_score99's fixture, with its report pointed at score100."""

    def report(self):
        self.write()
        return s100.report(str(self.q99))

    def text(self):
        return "\n".join(self.report()[0])

    def verdicts(self):
        return self.report()[1]


def trim_cold(d, label, keep):
    """Rewrite rows.jsonl so `label`'s cold rows are only the `keep` target: C1 reads that cell from 1 of its 2 boots while C4 (anchored on ca1) still holds."""
    p = pathlib.Path(d) / "rows.jsonl"
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept = [r for r in rows if not (r.get("tag") == label and r.get("case") == "cold" and r.get("target_tokens") != keep)]
    p.write_text("".join(json.dumps(r) + "\n" for r in kept), encoding="utf-8", newline="\n")


def trim_pp(d, label, drop):
    """Drop one 24-prompt digest row from `label`, so C1 reads a digest key with a boot's report missing."""
    p = pathlib.Path(d) / f"dec-{label}" / "pp.jsonl"
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept = [r for r in rows if r.get("name") != drop]
    p.write_text("".join(json.dumps(r) + "\n" for r in kept), encoding="utf-8", newline="\n")


class Base(unittest.TestCase):
    def fx(self):
        f = Fx()
        self.addCleanup(f.close)
        return f

    def run_main(self, *args):
        r = subprocess.run([sys.executable, str(SCORER), *args], capture_output=True, text=True, timeout=900)
        return r.returncode, r.stdout


class Adoption(Base):
    def test_adopt_when_c1_accepted_c4_equal_and_the_warm_turns_are_well_faster(self):
        lines, v, failed = self.fx().set_all(("ce1", "ce2"), warm=0.90).report()
        self.assertEqual(v["C5"], "ADOPT")
        self.assertFalse(failed)
        self.assertIn(ACCEPTED, "\n".join(lines))
        self.assertTrue(lines[-1].startswith("C5 ADOPTION: ADOPT: warm turns 10.0% faster for CE than CA"), lines[-1])

    def test_adopt_at_five_point_one_percent(self):
        lines, v, _ = self.fx().set_all(("ce1", "ce2"), warm=0.949).report()
        self.assertEqual(v["C5"], "ADOPT")
        self.assertIn("5.1% faster", lines[-1])

    def test_not_worth_a_switch_at_four_point_nine_percent(self):
        lines, v, failed = self.fx().set_all(("ce1", "ce2"), warm=0.951).report()
        self.assertEqual(v["C5"], "NOT WORTH A SWITCH")
        self.assertFalse(failed)
        self.assertIn(NOT_WORTH, lines[-1])
        self.assertTrue(lines[-1].startswith("C5 ADOPTION: "), lines[-1])

    def test_the_threshold_is_five_percent_and_a_gain_at_it_adopts(self):
        self.assertEqual(s100.THRESHOLD, 0.050)
        self.assertTrue(s100.enough(s100.THRESHOLD))
        self.assertFalse(s100.enough(s100.THRESHOLD - 1e-12))
        self.assertTrue(s100.enough(s100.THRESHOLD + 1e-12))
        self.assertFalse(s100.enough(0.049))
        self.assertTrue(s100.enough(0.051))

    def test_the_warm_cell_is_the_conversation_turns_two_plus_not_a_cold_cell(self):
        lines, v, _ = self.fx().set_all(("ce1", "ce2"), cold=0.90).report()  # the cold cells 10% faster, the warm turns level
        self.assertEqual(v["C5"], "NOT WORTH A SWITCH")
        self.assertIn("warm turns only 0.0% faster", lines[-1])

    def test_the_warm_gain_is_the_mean_of_both_control_boots(self):
        f = self.fx().set("ca2", warm=1.10).set_all(("ce1", "ce2"), warm=0.97)  # CA boots 1.00 and 1.10, mean 1.05; CE 0.97: 7.6% faster, but 3.0% against ca1 alone
        self.assertEqual(f.verdicts()["C5"], "ADOPT")

    def test_the_warm_gain_is_the_mean_of_both_policy_boots(self):
        f = self.fx().set("ce1", warm=0.96).set("ce2", warm=0.90)  # CE mean 0.93: 7.0% faster, but 4.0% against ce1 alone
        self.assertEqual(f.verdicts()["C5"], "ADOPT")


class HoldBack(Base):
    def test_hold_back_on_a_cold_cell_one_and_a_half_percent_slower(self):
        lines, v, failed = self.fx().set_all(("ce1", "ce2"), cold=1.015).report()
        self.assertTrue(v["C1"].startswith("C1 SYNC: NOT ACCEPTED"), v["C1"])
        self.assertEqual(v["C5"], "HOLD BACK")
        self.assertFalse(failed)
        self.assertIn("C1 not accepted: 3 cell(s) more than 1% slower (0 inside CA's boots' range): cold 8k first token", lines[-1])
        self.assertTrue(any(l.startswith("  over C1's limit: cold 8k first token: ") for l in lines), lines)

    def test_hold_back_on_a_sampled_code_8_client_cell_1_5_percent_slower(self):
        lines, v, _ = self.fx().set_all(("ce1", "ce2"), per={("SC", 8): 0.985}).report()
        self.assertEqual(v["C5"], "HOLD BACK")
        self.assertIn("sampled code at 8 clients", lines[-1])
        self.assertIn("1 cell(s) more than 1% slower (0 inside CA's boots' range)", lines[-1])

    def test_hold_back_names_a_cell_inside_the_controls_range(self):
        f = self.fx().set("ca1", per={("P", 8): 0.98}).set("ca2", per={("P", 8): 1.02}).set_all(("ce1", "ce2"), per={("P", 8): 0.985})
        lines, v, _ = f.report()
        self.assertTrue(v["C1"].startswith("C1 SYNC: NOT ACCEPTED: 1 cell(s) more than 1% slower (1 inside CA's boots' range)"), v["C1"])
        self.assertEqual(v["C5"], "HOLD BACK")
        self.assertIn("C1 not accepted: 1 cell(s) more than 1% slower (1 inside CA's boots' range): greedy prose at 8 clients", lines[-1])
        self.assertTrue(any("<- inside CA's boots' range" in l for l in lines), lines)

    def test_hold_back_on_a_digest_difference_exits_one(self):
        f = self.fx()
        f.write()
        put(f.q99 / "dec-ce1" / "P1.jsonl", [{"agg_tok_s": 80.0, "sha": ["zzz"]}])
        lines, v, failed = s100.report(str(f.q99))
        self.assertEqual(v["C4"], {"ce1": "DIFFERS", "ce2": "EQUAL"})
        self.assertEqual(v["C5"], "HOLD BACK")
        self.assertTrue(failed)
        self.assertIn("C4 digests differ at ce1", lines[-1])
        rc, out = self.run_main("--q100", str(f.q99))
        self.assertEqual(rc, 1)
        self.assertIn("C5 ADOPTION: HOLD BACK: ", out)

    def test_hold_back_when_c4_differs_even_with_c1_undecided(self):
        f = self.fx()
        f.write()
        trim_pp(f.q99, "ca2", "p2")  # C1: one digest key with a boot's report missing, so NOT DECIDED
        put(f.q99 / "dec-ce1" / "P1.jsonl", [{"agg_tok_s": 80.0, "sha": ["zzz"]}])  # C4: ce1 differs from ca1
        lines, v, failed = s100.report(str(f.q99))
        self.assertTrue(v["C1"].startswith("C1 SYNC: NOT DECIDED"), v["C1"])
        self.assertEqual(v["C4"], {"ce1": "DIFFERS", "ce2": "EQUAL"})
        self.assertEqual(v["C5"], "HOLD BACK")
        self.assertTrue(failed)


class NotDecided(Base):
    def test_not_decided_with_a_boot_missing_for_each_of_the_four(self):
        for label in LABELS:
            with self.subTest(missing=label):
                lines, v, failed = self.fx().skip(label).report()
                self.assertEqual(v["C5"], "NOT DECIDED")
                self.assertIn("C5 ADOPTION: NOT DECIDED", lines[-1])
                self.assertFalse(failed)

    def test_not_decided_when_c1_is_undecided_but_c4_is_equal(self):
        f = self.fx()
        f.write()
        trim_cold(f.q99, "ca2", 8000)  # the cold 32k and 120k cells read from 1 of CA's 2 boots; C4 anchors ca1, so it holds
        lines, v, failed = s100.report(str(f.q99))
        self.assertTrue(v["C1"].startswith("C1 SYNC: NOT DECIDED"), v["C1"])
        self.assertEqual(v["C4"], {"ce1": "EQUAL", "ce2": "EQUAL"})
        self.assertEqual(v["C5"], "NOT DECIDED")
        self.assertIn("C5 ADOPTION: NOT DECIDED: C1: C1 SYNC: NOT DECIDED", lines[-1])
        self.assertFalse(failed)

    def test_an_absent_directory_is_not_decided_and_names_the_missing_boots(self):
        rc, out = self.run_main("--q100", str(ROOT / "work" / "pp100-absent"))
        self.assertEqual(rc, 0)
        self.assertIn("C1 SYNC: NOT DECIDED: no rows for ca1, ca2, ce1, ce2", out)
        self.assertIn("C4 DIGESTS: NOT DECIDED: ca1 has no rows", out)
        self.assertIn("C5 ADOPTION: NOT DECIDED", out)
        self.assertIn("no rows for ca1, ca2, ce1, ce2", out.split("C5 ADOPTION:")[-1])


class Report(Base):
    def test_the_report_opens_with_score100s_header_and_ends_with_the_c5_line(self):
        f = self.fx()
        lines, _, _ = f.report()
        self.assertEqual(lines[0], f"== score100: q100 {f.q99}")
        self.assertTrue(lines[-1].startswith("C5 ADOPTION: "), lines[-1])
        self.assertIn("== C5 adoption: ", "\n".join(lines))

    def test_c1_c2_c3_c4_are_score99s_own_lines(self):
        f = self.fx()
        f.write()
        a = s100.report(str(f.q99))[0]
        b = s99.report(str(f.q99))[0]
        self.assertEqual(a[1:len(b)], b[1:])  # every score99 clause line, verbatim, between score100's header and C5

    def test_the_verdict_text_never_names_the_other_switch(self):
        for kw in ({}, {"warm": 0.90}, {"warm": 0.951}):
            with self.subTest(**kw):
                text = self.fx().set_all(("ce1", "ce2"), **kw).text()
                self.assertNotIn("TF_CACHE_EVICT", text)
                self.assertNotIn("decayed_resume", text)


class ExitCode(Base):
    def test_the_exit_code_is_zero_on_adopt(self):
        f = self.fx().set_all(("ce1", "ce2"), warm=0.90)
        f.write()
        rc, out = self.run_main("--q100", str(f.q99))
        self.assertEqual(rc, 0)
        self.assertIn("C5 ADOPTION: ADOPT", out)

    def test_the_exit_code_is_zero_on_hold_back(self):
        f = self.fx().set_all(("ce1", "ce2"), cold=1.015)
        f.write()
        rc, out = self.run_main("--q100", str(f.q99))
        self.assertEqual(rc, 0)
        self.assertIn("C5 ADOPTION: HOLD BACK", out)

    def test_the_exit_code_is_zero_on_not_worth_a_switch(self):
        f = self.fx().set_all(("ce1", "ce2"), warm=0.951)
        f.write()
        rc, out = self.run_main("--q100", str(f.q99))
        self.assertEqual(rc, 0)
        self.assertIn(NOT_WORTH, out)

    def test_the_exit_code_is_zero_when_a_clause_is_not_decided(self):
        f = self.fx().skip("ce2")
        f.write()
        rc, out = self.run_main("--q100", str(f.q99))
        self.assertEqual(rc, 0)
        self.assertIn("C1 SYNC: NOT DECIDED: no rows for ce2", out)
        self.assertIn("C5 ADOPTION: NOT DECIDED", out)

    def test_the_exit_code_is_one_on_a_digest_difference(self):
        f = self.fx()
        f.write()
        put(f.q99 / "dec-ce2" / "pp.jsonl", [{"name": "p1", "sha12": "changed"}])
        rc, out = self.run_main("--q100", str(f.q99))
        self.assertEqual(rc, 1)
        self.assertIn("C4 DIGESTS: DIFFERS at 1 arm(s): ce2", out)
        self.assertIn("C5 ADOPTION: HOLD BACK", out)

    def test_dir_is_an_alias_of_q100_and_the_default_is_work_pp100_f100_c(self):
        r = subprocess.run([sys.executable, str(SCORER), "--help"], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0)
        self.assertIn("work/pp100/f100-c", r.stdout)
        self.assertIn("--dir", r.stdout)
        rc, out = self.run_main("--dir", str(ROOT / "work" / "pp100-absent"))
        self.assertEqual(rc, 0)
        self.assertIn("C1 SYNC: NOT DECIDED: no rows for ca1, ca2, ce1, ce2", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
