#!/usr/bin/env python3
"""test_score99.py: scripts/queue-scores/score99.py's four clauses on a fixture row tree laid out as queue99 writes it (queue91's f91-c layout, one directory, four boots).

Run from the top-level shell: python scripts/tests/test_score99.py
SCORE99=<path> points the tests at a copy of the scorer (scripts/tests/mutants_score99.py runs them against each mutant that way).

The rows are written by test_score91.py's put(), in its row format; wboot here adds the per-cell decode scale and the `only` limit that test_score95.py uses, replicated so this
file does not import another scorer's test module. An exact 1.0% slower cell cannot be built by division (the nearest double to 1.01 is 1.010000000000000009, and any ratio
lands a double above or below the limit's own double), so the C1 limit is probed directly at over(LIMIT) and bracketed through the fixture at 0.99% accepted and 1.01% flagged.
"""
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_OVER = os.environ.get("SCORE99")
SCORER = pathlib.Path(_OVER) if _OVER else ROOT / "scripts/queue-scores/score99.py"
s99 = load("score99", SCORER)
T91 = load("test_score91", ROOT / "scripts/tests/test_score91.py")  # its put(), COLD, TURNS and DEC: queue91's row shape, one owner
put = T91.put
COLD = T91.COLD
TURNS = T91.TURNS
DEC = T91.DEC
LABELS = ("ca1", "ce1", "ce2", "ca2")
CELLS12 = [(k, n) for k in ("P", "C", "SP", "SC") for n in (1, 2, 4)]
ACCEPTED = "C1 SYNC: ACCEPTED, no cell more than 1% slower and every reply digest equal"


def wboot(d, label, cold=1.0, warm=1.0, dec=1.0, per=None, digest="a", only=None):
    """One boot's rows in queue91's format, with a per-(kind, level) decode scale so one cell can move on its own and `only` limiting what is written."""
    d = pathlib.Path(d)
    if only in (None, "cold"):
        for size, ms in COLD.items():
            for rep in (1, 2):
                put(d / "rows.jsonl", [{"tag": label, "case": "cold", "target_tokens": size, "rep": rep, "ttft_ms": ms * cold, "token_sha": f"{digest}{size}{rep}"}])
    if only in (None, "chain"):
        put(d / label / "chain.jsonl", [{"tag": "c74", "turn": t, "ttft_ms": ms * (warm if t > 1 else 1.0), "token_sha": f"{digest}t{t}"}
                                        for t, ms in enumerate(TURNS, 1)])
    if only in (None, "dec"):
        for kind, base in DEC.items():
            for n in s99.LEVELS:
                s = (per or {}).get((kind, n), dec)
                put(d / f"dec-{label}" / f"{kind}{n}.jsonl", [{"agg_tok_s": base * n ** 0.5 * s, "sha": [f"{digest}{kind}{n}x", f"{digest}{kind}{n}y"]}] * 3)
        put(d / f"dec-{label}" / "pp.jsonl", [{"name": f"p{i}", "sha12": f"{digest}pp{i}"} for i in range(3)])


class Fixture:
    """queue99's one row directory: every boot at its default keyword, then the test's own, rewritten whole from scratch on demand."""

    def __init__(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="score99-", dir=ROOT / "work"))
        self.q99 = self.root / "q99"
        self.kw = {label: {} for label in LABELS}
        self.out = set()

    def set(self, label, **kw):
        self.kw[label].update(kw)
        return self

    def set_all(self, labels, **kw):
        for label in labels:
            self.set(label, **kw)
        return self

    def skip(self, *labels):
        self.out.update(labels)
        return self

    def write(self):
        shutil.rmtree(self.q99, ignore_errors=True)
        for label in LABELS:
            if label not in self.out:
                wboot(self.q99, label, **self.kw[label])
        return self

    def report(self):
        self.write()
        return s99.report(str(self.q99))

    def verdicts(self):
        return self.report()[1]

    def text(self):
        return "\n".join(self.report()[0])

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Base(unittest.TestCase):
    def fx(self):
        f = Fixture()
        self.addCleanup(f.close)
        return f


class C1Sync(Base):
    def test_c1_accepted_when_every_cell_and_digest_agrees(self):
        lines, v, failed = self.fx().report()
        self.assertEqual(v["C1"], ACCEPTED)
        self.assertEqual(v["C4"], {"ce1": "EQUAL", "ce2": "EQUAL"})
        self.assertFalse(failed)

    def test_c1_prints_both_group_means_and_their_boots(self):
        text = self.fx().text()
        self.assertIn("== C1 sync: CE (ce1 ce2) against CA (ca1 ca2); slower is positive, the limit 1.0%", text)
        line = next(l for l in text.splitlines() if l.startswith("cold 8k first token: "))
        self.assertEqual(line, f"cold 8k first token: CA mean {COLD[8000]:.1f} (boots {COLD[8000]:.1f} {COLD[8000]:.1f}) | "
                               f"CE mean {COLD[8000]:.1f} (boots {COLD[8000]:.1f} {COLD[8000]:.1f}) | +0.00% slower")

    def test_c1_a_cell_over_the_limit_is_named(self):
        f = self.fx().set("ce1", per={("P", 8): 0.95}).set("ce2", per={("P", 8): 0.95})  # the policy 5% down at greedy prose 8 clients
        lines, v, _ = f.report()
        self.assertTrue(v["C1"].startswith("C1 SYNC: NOT ACCEPTED: 1 cell(s) more than 1% slower"), v["C1"])
        self.assertIn("greedy prose at 8 clients", v["C1"])
        self.assertTrue(any("<- over the limit" in l and l.startswith("greedy prose at 8 clients: CA mean ") for l in lines), [l for l in lines if "8 clients" in l])

    def test_the_limit_is_one_percent_and_a_value_at_it_is_not_over(self):
        self.assertEqual(s99.LIMIT, 0.010)
        self.assertFalse(s99.over(s99.LIMIT))
        self.assertTrue(s99.over(s99.LIMIT + 1e-9))
        self.assertTrue(self.fx().set_all(("ce1", "ce2"), cold=1.0101).verdicts()["C1"].startswith("C1 SYNC: NOT ACCEPTED"))
        self.assertEqual(self.fx().set_all(("ce1", "ce2"), cold=1.0099).verdicts()["C1"], ACCEPTED)

    def test_c1_a_latency_cell_up_is_slower_and_down_is_not(self):
        v = self.fx().set_all(("ce1", "ce2"), warm=1.02).verdicts()["C1"]
        self.assertIn("conversation turns 2+ first token", v)
        self.assertEqual(self.fx().set_all(("ce1", "ce2"), warm=0.98).verdicts()["C1"], ACCEPTED)

    def test_c1_throughput_down_is_slower_and_up_is_not(self):
        v = self.fx().set_all(("ce1", "ce2"), dec=0.98).verdicts()["C1"]
        self.assertIn("sampled code at 8 clients", v)
        self.assertEqual(self.fx().set_all(("ce1", "ce2"), dec=1.05).verdicts()["C1"], ACCEPTED)

    def test_c1_a_different_reply_digest_is_not_accepted(self):
        f = self.fx()
        f.write()
        put(f.q99 / "dec-ce2" / "P1.jsonl", [{"agg_tok_s": 80.0, "sha": ["zzz"]}])
        v = s99.report(str(f.q99))[1]["C1"]
        self.assertTrue(v.startswith("C1 SYNC: NOT ACCEPTED: reply digests differ at 1 key(s)"), v)

    def test_c1_a_missing_boot_is_not_decided_for_each_of_the_four(self):
        for label in LABELS:
            with self.subTest(missing=label):
                v = self.fx().skip(label).verdicts()["C1"]
                self.assertEqual(v, f"C1 SYNC: NOT DECIDED: no rows for {label}")

    def test_c1_a_cell_not_reported_by_every_boot_is_not_decided(self):
        lines, v, _ = self.fx().set("ce1", only="cold").report()
        self.assertTrue(v["C1"].startswith("C1 SYNC: NOT DECIDED"), v["C1"])
        self.assertIn("conversation turns 2+ first token", v["C1"])
        self.assertIn("conversation turns 2+ first token: CA measured on 2 of 2 boots, CE on 1 of 2: NOT DECIDED", "\n".join(lines))

    def test_c1_a_missing_digest_report_is_not_decided(self):
        f = self.fx()
        f.write()
        (f.q99 / "dec-ce1" / "pp.jsonl").unlink()
        lines, v, _ = s99.report(str(f.q99))
        self.assertTrue(v["C1"].startswith("C1 SYNC: NOT DECIDED"), v["C1"])
        self.assertIn("digest", v["C1"])
        self.assertTrue(any("missing: ('pp', 'p0')" in l for l in lines), lines)


class Groups(Base):
    def test_the_group_value_is_the_mean_of_its_boots(self):
        f = self.fx().set("ce1", cold=1.0).set("ce2", cold=1.05)  # the CE mean is 1.025, so every cold cell is 2.5% slower
        self.assertTrue(f.verdicts()["C1"].startswith("C1 SYNC: NOT ACCEPTED"), f.verdicts()["C1"])
        self.assertIn("cold 8k first token", f.verdicts()["C1"])

    def test_the_control_is_ca1_and_ca2(self):
        f = self.fx().set("ca2", per={("P", 8): 1.06})  # the control's second boot 6% up: its mean is 3% up and the policy reads 2.9% slower
        self.assertTrue(f.verdicts()["C1"].startswith("C1 SYNC: NOT ACCEPTED"), f.verdicts()["C1"])
        self.assertIn("greedy prose at 8 clients", f.verdicts()["C1"])

    def test_ce1_is_the_policy_not_the_control(self):
        f = self.fx().set_all(("ce1", "ce2"), cold=1.02)
        self.assertTrue(f.verdicts()["C1"].startswith("C1 SYNC: NOT ACCEPTED"), f.verdicts()["C1"])
        self.assertIn("cold 8k first token", f.verdicts()["C1"])


class C2Prompt(Base):
    def test_c2_reports_the_four_prompt_cells_with_known_numbers(self):
        full = self.fx().set_all(("ce1", "ce2"), cold=0.99).set_all(("ce1", "ce2"), warm=1.02).text()
        self.assertIn("== C2 prompt cells: the fraction faster for CE than CA (report only, no verdict)", full)
        text = full.split("== C2 prompt cells")[1].split("== C3")[0]
        for size in (8000, 32000, 120000):
            line = next(l for l in text.splitlines() if l.startswith(f"cold {size // 1000}k first token: CA mean "))
            self.assertTrue(line.endswith("+1.00% faster"), line)
        warm = next(l for l in text.splitlines() if l.startswith("conversation turns 2+ first token: CA mean "))
        self.assertTrue(warm.endswith("-2.00% faster"), warm)

    def test_c2_has_no_verdict_of_its_own(self):
        _, v, _ = self.fx().report()
        self.assertEqual(sorted(v), ["C1", "C4"])

    def test_c2_reports_not_decided_when_a_boot_is_missing(self):
        text = self.fx().skip("ce2").text()
        self.assertIn("C2: NOT DECIDED: no rows for ce2", text)

    def test_c2_a_cell_a_boot_did_not_report_is_not_decided(self):
        text = self.fx().set("ce1", only="cold").text()
        self.assertIn("conversation turns 2+ first token: NOT DECIDED: CA measured on 2 of 2 boots, CE on 1 of 2", text)


class C3BootNoise(Base):
    def test_c3_reports_the_spread_with_known_numbers(self):
        text = self.fx().set("ca2", cold=1.018).text()
        line = next(l for l in text.splitlines() if l.startswith("cold 8k first token: CA spread "))
        self.assertEqual(line, "cold 8k first token: CA spread 1.78% of mean | CE spread 0.00% of mean")
        self.assertIn("== C3 boot noise: (max - min) of a group's boots over its mean, per cell (report only, no verdict)", text)

    def test_c3_the_policy_spread_is_its_own_boots(self):
        text = self.fx().set("ce2", cold=1.018).text()
        line = next(l for l in text.splitlines() if l.startswith("cold 8k first token: CA spread "))
        self.assertEqual(line, "cold 8k first token: CA spread 0.00% of mean | CE spread 1.78% of mean")

    def test_c3_reports_not_decided_for_a_missing_boot(self):
        text = self.fx().skip("ca2").text()
        self.assertIn("C3: NOT DECIDED for the boots with no rows: ca2", text)

    def test_c3_a_cell_with_one_boot_says_so(self):
        text = self.fx().set_all(("ce1", "ce2"), only="cold").text()
        self.assertIn("conversation turns 2+ first token: CA spread 0.00% of mean | CE no rows", text)


class C4Digests(Base):
    def test_c4_equal_when_every_digest_agrees(self):
        _, v, failed = self.fx().report()
        self.assertEqual(v["C4"], {"ce1": "EQUAL", "ce2": "EQUAL"})
        self.assertFalse(failed)

    def test_c4_one_differing_decode_cell_fails_the_arm(self):
        f = self.fx()
        f.write()
        put(f.q99 / "dec-ce1" / "P1.jsonl", [{"agg_tok_s": 80.0, "sha": ["zzz"]}])
        lines, v, failed = s99.report(str(f.q99))
        self.assertEqual(v["C4"], {"ce1": "DIFFERS", "ce2": "EQUAL"})
        self.assertTrue(failed)
        self.assertIn("ce1: DIFFERS at 1 key(s)", "\n".join(lines))
        self.assertIn("C4 DIGESTS: DIFFERS at 1 arm(s): ce1", "\n".join(lines))
        self.assertTrue(any("differs: ('dec', 'P', 1)" in l for l in lines), lines)

    def test_c4_a_differing_digest_in_the_second_boot_fails_too(self):
        f = self.fx()
        f.write()
        put(f.q99 / "dec-ce2" / "pp.jsonl", [{"name": "p1", "sha12": "changed"}])
        _, v, failed = s99.report(str(f.q99))
        self.assertEqual(v["C4"], {"ce1": "EQUAL", "ce2": "DIFFERS"})
        self.assertTrue(failed)

    def test_c4_a_missing_report_is_not_decided_and_does_not_fail(self):
        f = self.fx()
        f.write()
        (f.q99 / "dec-ce1" / "P1.jsonl").unlink()
        lines, v, failed = s99.report(str(f.q99))
        self.assertEqual(v["C4"]["ce1"], "NOT DECIDED")
        self.assertEqual(v["C4"]["ce2"], "EQUAL")
        self.assertFalse(failed)
        self.assertTrue(any("ce1: NOT DECIDED: a report is missing on one side (never a pass)" in l for l in lines), lines)

    def test_c4_compares_against_ca1_not_ca2(self):
        f = self.fx().set("ca2", digest="b")  # the control's second boot differs from ca1; the C4 anchor is ca1, so C4 holds and only C1 sees it
        f.write()
        _, v, failed = s99.report(str(f.q99))
        self.assertEqual(v["C4"], {"ce1": "EQUAL", "ce2": "EQUAL"})
        self.assertFalse(failed)
        self.assertTrue(v["C1"].startswith("C1 SYNC: NOT ACCEPTED: reply digests differ"), v["C1"])

    def test_c4_a_missing_ca1_is_not_decided(self):
        _, v, failed = self.fx().skip("ca1").report()
        self.assertEqual(v["C4"], {"ce1": "NOT DECIDED", "ce2": "NOT DECIDED"})
        self.assertFalse(failed)

    def test_c4_a_missing_policy_boot_is_not_decided_on_that_boot_only(self):
        _, v, failed = self.fx().skip("ce2").report()
        self.assertEqual(v["C4"], {"ce1": "EQUAL", "ce2": "NOT DECIDED"})
        self.assertFalse(failed)


class ClauseIsolation(Base):
    """Each clause's own fixture: the change moves that clause's report or verdict, and the others stay where they were."""

    def test_c1_alone_flips(self):
        f = self.fx().set_all(("ce1", "ce2"), per={("P", 8): 0.94})  # an 8-client decode cell: not a prompt cell, not a digest
        _, v, failed = f.report()
        self.assertTrue(v["C1"].startswith("C1 SYNC: NOT ACCEPTED"), v["C1"])
        self.assertEqual(v["C4"], {"ce1": "EQUAL", "ce2": "EQUAL"})
        self.assertFalse(failed)

    def test_c2_alone_moves_and_changes_no_verdict(self):
        f = self.fx().set_all(("ce1", "ce2"), cold=0.995)  # 0.5% faster cold: under the C1 limit
        text = f.text()
        self.assertIn(ACCEPTED, text)
        self.assertIn("cold 8k first token: CA mean 3600.0 (boots 3600.0 3600.0) | CE mean 3582.0 (boots 3582.0 3582.0) | +0.50% faster", text)

    def test_c3_alone_moves_and_changes_no_verdict(self):
        f = self.fx().set("ca2", cold=1.018)
        text = f.text()
        self.assertIn(ACCEPTED, text)
        _, v, failed = f.report()
        self.assertEqual(v["C4"], {"ce1": "EQUAL", "ce2": "EQUAL"})
        self.assertFalse(failed)

    def test_c4_flips_the_exit_flag(self):
        f = self.fx()
        f.write()
        put(f.q99 / "dec-ce1" / "C2.jsonl", [{"agg_tok_s": 90.0, "sha": ["zzz"]}])
        lines, v, failed = s99.report(str(f.q99))
        self.assertEqual(v["C4"]["ce1"], "DIFFERS")
        self.assertTrue(failed)
        self.assertTrue(any("differs: ('dec', 'C', 2)" in l for l in lines), lines)  # C1's digest rule sees it too; C4 is what exits 1


class ExitCode(Base):
    def run_main(self, f):
        r = subprocess.run([sys.executable, str(SCORER), "--q99", str(f.q99)], capture_output=True, text=True, timeout=900)
        return r.returncode, r.stdout

    def test_the_exit_code_is_one_when_a_c4_digest_differs(self):
        f = self.fx()
        f.write()
        put(f.q99 / "dec-ce1" / "P1.jsonl", [{"agg_tok_s": 80.0, "sha": ["zzz"]}])
        rc, out = self.run_main(f)
        self.assertEqual(rc, 1)
        self.assertIn("C4 DIGESTS: DIFFERS at 1 arm(s): ce1", out)

    def test_the_exit_code_is_zero_when_a_clause_is_not_decided(self):
        f = self.fx().skip("ce2")
        f.write()
        rc, out = self.run_main(f)
        self.assertEqual(rc, 0)
        self.assertIn("C1 SYNC: NOT DECIDED: no rows for ce2", out)
        self.assertIn("C4 DIGESTS: NOT DECIDED: ce2", out)

    def test_the_exit_code_is_zero_when_c1_is_not_accepted_but_the_digests_are_equal(self):
        f = self.fx().set_all(("ce1", "ce2"), cold=1.02)
        f.write()
        rc, out = self.run_main(f)
        self.assertEqual(rc, 0)
        self.assertIn("C1 SYNC: NOT ACCEPTED", out)
        self.assertIn("C4 DIGESTS: EQUAL, every reply digest of ce1 and ce2 equals ca1's", out)

    def test_the_default_directory_is_work_pp99_f99_c(self):
        r = subprocess.run([sys.executable, str(SCORER), "--help"], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0)
        self.assertIn("work/pp99/f99-c", r.stdout)
        self.assertIn("--dir", r.stdout)

    def test_dir_is_an_alias_of_q99(self):
        r = subprocess.run([sys.executable, str(SCORER), "--dir", str(ROOT / "work" / "pp99-absent")], capture_output=True, text=True, timeout=900)
        self.assertEqual(r.returncode, 0)
        self.assertIn("C1 SYNC: NOT DECIDED: no rows for ca1, ca2, ce1, ce2", r.stdout)

    def test_an_absent_directory_is_not_decided_and_exits_zero(self):
        r = subprocess.run([sys.executable, str(SCORER), "--q99", str(ROOT / "work" / "pp99-absent")], capture_output=True, text=True, timeout=900)
        self.assertEqual(r.returncode, 0)
        self.assertIn("C1 SYNC: NOT DECIDED: no rows for ca1, ca2, ce1, ce2", r.stdout)
        self.assertIn("C4 DIGESTS: NOT DECIDED: ca1 has no rows", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
