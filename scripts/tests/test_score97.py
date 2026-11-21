#!/usr/bin/env python3
"""test_score97.py: scripts/queue-scores/score97.py's three clauses on fixture row trees laid out as queue91 writes them.

Run from the top-level shell: python scripts/tests/test_score97.py
SCORE97=<path> points the tests at a copy of the scorer (scripts/tests/mutants_score97.py runs them against each mutant that way).

The rows are written by test_score91.py's put(), in its row format, and wboot() here adds the per-(kind, level) decode scale the reference checks need. An exact 1.0% slower cell
cannot be built by division (the nearest double to 1.01 is 1.010000000000000009), so the U1 limit is bracketed at 0.99% accepted and 1.01% flagged.
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


_OVER = os.environ.get("SCORE97")
SCORER = pathlib.Path(_OVER) if _OVER else ROOT / "scripts/queue-scores/score97.py"
s97 = load("score97", SCORER)
T91 = load("test_score91", ROOT / "scripts/tests/test_score91.py")  # its put(), COLD, TURNS, DEC and LEVELS: queue91's row shape, one owner
put = T91.put
COLD = T91.COLD
TURNS = T91.TURNS
DEC = T91.DEC
LEVELS = T91.s91.LEVELS

Q91_LABELS = ("mn1", "mn2", "mps")
Q92_LABELS = ("tn1", "tn2", "sm2", "sm3", "ut1")
Q95_LABELS = ("mn3",)
ALL = Q91_LABELS + Q92_LABELS + Q95_LABELS
N_LABELS = ("mn1", "mn2", "mn3")


def wboot(d, label, cold=1.0, warm=1.0, dec=1.0, per=None, digest="a", only=None):
    """One boot's rows in queue91's format: test_score91.write_boot's shape, plus a per-(kind, level) decode scale so one decode cell can move on its own."""
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
            for n in LEVELS:
                s = (per or {}).get((kind, n), dec)
                put(d / f"dec-{label}" / f"{kind}{n}.jsonl", [{"agg_tok_s": base * n ** 0.5 * s, "sha": [f"{digest}{kind}{n}x", f"{digest}{kind}{n}y"]}] * 3)
        put(d / f"dec-{label}" / "pp.jsonl", [{"name": f"p{i}", "sha12": f"{digest}pp{i}"} for i in range(3)])


class Fixture:
    """The three queues' row trees: every boot at its default keyword, then the test's own, rewritten whole from scratch on demand."""

    def __init__(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="score97-", dir=ROOT / "work"))
        self.q91, self.q92, self.q95 = self.root / "q91", self.root / "q92", self.root / "q95"
        self.kw = {label: {} for label in ALL}
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

    def dir(self, label):
        return self.q91 if label in Q91_LABELS else self.q92 if label in Q92_LABELS else self.q95

    def write(self):
        shutil.rmtree(self.root, ignore_errors=True)
        for label in ALL:
            if label not in self.out:
                wboot(self.dir(label), label, **self.kw[label])
        return self

    def report(self):
        self.write()
        return s97.report(str(self.q91), str(self.q92), str(self.q95))

    def verdict(self):
        return self.report()[1]

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Base(unittest.TestCase):
    def fx(self):
        f = Fixture()
        self.addCleanup(f.close)
        return f

    def lines(self, f):
        return f.report()[0]

    def text(self, f):
        return "\n".join(self.lines(f))

    def cell(self, lines, prefix):
        return next(l for l in lines if l.startswith(prefix))

    def u2cell(self, lines, prefix):
        return next(l for l in self.u2_lines(lines) if l.startswith(prefix))

    def u2_lines(self, lines):
        start = next(i for i, l in enumerate(lines) if l.startswith("== U2"))
        end = next(i for i, l in enumerate(lines) if l.startswith("== U3"))
        return lines[start + 1:end]

    def u3_lines(self, lines):
        return [l for l in lines if l.startswith("U3 ")]


class U1Sync(Base):
    def test_u1_accepted_when_every_cell_and_digest_agrees(self):
        f = self.fx()
        lines, v, failed = f.report()
        self.assertEqual(v, "U1 SYNC: ACCEPTED, no cell more than 1.0% slower and every reply digest equal")
        self.assertFalse(failed)
        self.assertEqual(lines[0], f"== score97: q91 {f.q91}, q92 {f.q92}, q95 {f.q95}")

    def test_u1_prints_every_cell_with_both_groups_boots(self):
        lines = self.lines(self.fx())
        self.assertIn("== U1 re-seat sync: T (tn1 tn2) against N (mn1 mn2 mn3); slower is positive, a cell is the mean of its group's boots", lines)
        self.assertEqual(self.cell(lines, "cold 8k first token: "), "cold 8k first token: N 3600.0 3600.0 3600.0 | T 3600.0 3600.0 | +0.00% slower")
        self.assertEqual(self.cell(lines, "conversation turns 2+ first token: "),
                         "conversation turns 2+ first token: N 811.4 811.4 811.4 | T 811.4 811.4 | +0.00% slower")
        self.assertEqual(sum(1 for l in lines if l.endswith(" slower")), 24)

    def test_u1_a_cell_slower_is_flagged_and_a_faster_one_is_not(self):
        lines, v, _ = self.fx().set_all(("tn1", "tn2"), dec=0.98).report()
        self.assertTrue(v.startswith("U1 SYNC: NOT ACCEPTED: 20 cell(s) more than 1.0% slower (0 inside N's boots' range): greedy prose at 1 clients"), v)
        self.assertEqual(self.cell(lines, "greedy prose at 1 clients: "),
                         "greedy prose at 1 clients: N 80.0 80.0 80.0 | T 78.4 78.4 | +2.00% slower  <- over the limit (T 78.4..78.4)")
        self.assertTrue(self.fx().set_all(("tn1", "tn2"), dec=1.02).verdict().startswith("U1 SYNC: ACCEPTED"))

    def test_u1_a_latency_cell_up_is_slower_and_down_is_not(self):
        v = self.fx().set_all(("tn1", "tn2"), warm=1.02).verdict()
        self.assertTrue(v.startswith("U1 SYNC: NOT ACCEPTED: 1 cell(s) more than 1.0% slower"), v)
        self.assertIn("conversation turns 2+ first token", v)
        self.assertTrue(self.fx().set_all(("tn1", "tn2"), warm=0.98).verdict().startswith("U1 SYNC: ACCEPTED"))

    def test_u1_the_limit_is_one_percent(self):
        self.assertTrue(self.fx().set_all(("tn1", "tn2"), cold=1.0099).verdict().startswith("U1 SYNC: ACCEPTED"))
        v = self.fx().set_all(("tn1", "tn2"), cold=1.0101).verdict()
        self.assertTrue(v.startswith("U1 SYNC: NOT ACCEPTED"), v)
        self.assertIn("more than 1.0% slower", v)
        self.assertIn("cold 8k first token", v)
        self.assertIn("cold 120k first token", v)

    def test_u1_a_cell_1_2_percent_slower_flips_only_its_own_clause(self):
        lines, v, failed = self.fx().set_all(("tn1", "tn2"), warm=1.012).report()
        self.assertTrue(v.startswith("U1 SYNC: NOT ACCEPTED: 1 cell(s) more than 1.0% slower (0 inside N's boots' range): conversation turns 2+ first token"), v)
        self.assertFalse(failed)
        self.assertTrue(all("| T against S1 " in l for l in self.u2_lines(lines)))
        self.assertTrue(all("EQUAL at" in l for l in self.u3_lines(lines)))

    def test_u1_the_group_value_is_the_mean_not_the_minimum(self):
        f = self.fx().set("mn3", warm=1.02).set_all(("tn1", "tn2"), warm=1.015)  # N mean 0.83% up, N minimum at par
        self.assertTrue(f.verdict().startswith("U1 SYNC: ACCEPTED"), f.verdict())

    def test_u1_the_group_value_is_the_mean_not_the_worst_boot(self):
        f = self.fx().set("tn2", cold=1.015)  # T mean 0.75% slower, the worst boot 1.5% slower
        self.assertTrue(f.verdict().startswith("U1 SYNC: ACCEPTED"), f.verdict())

    def test_u1_a_different_reply_digest_is_not_accepted(self):
        f = self.fx()
        f.write()
        put(f.q92 / "dec-tn1" / "pp.jsonl", [{"name": "p1", "sha12": "changed"}])
        lines, v, failed = s97.report(str(f.q91), str(f.q92), str(f.q95))
        self.assertEqual(v, "U1 SYNC: NOT ACCEPTED: reply digests differ at 1 key(s) (and 0 cell(s) over the speed limit)")
        self.assertTrue(failed)
        self.assertIn("  differs: ('pp', 'p1')", lines)

    def test_u1_a_missing_boot_is_not_decided_naming_it(self):
        self.assertEqual(self.fx().skip("mn3").verdict(), "U1 SYNC: NOT DECIDED: no rows for mn3")
        self.assertEqual(self.fx().skip("tn2").verdict(), "U1 SYNC: NOT DECIDED: no rows for tn2")
        self.assertEqual(self.fx().skip("tn1", "tn2").verdict(), "U1 SYNC: NOT DECIDED: no rows for tn1, tn2")

    def test_u1_a_cell_not_reported_by_every_boot_is_not_decided(self):
        lines, v, failed = self.fx().set("tn1", only="cold").report()
        self.assertTrue(v.startswith("U1 SYNC: NOT DECIDED"), v)
        self.assertIn("conversation turns 2+ first token", v)
        self.assertFalse(failed)
        self.assertIn("conversation turns 2+ first token: T measured on 1 of 2 boots, N on 3 of 3: NOT DECIDED", lines)

    def test_u1_a_missing_digest_report_is_not_decided(self):
        f = self.fx()
        f.write()
        (f.q92 / "dec-tn2" / "pp.jsonl").unlink()
        lines, v, failed = s97.report(str(f.q91), str(f.q92), str(f.q95))
        self.assertTrue(v.startswith("U1 SYNC: NOT DECIDED"), v)
        self.assertIn("digest", v)
        self.assertFalse(failed)
        self.assertIn("  missing: ('pp', 'p0')", lines)

    def test_u1_a_loss_inside_the_range_is_marked(self):
        f = self.fx().set("mn1", warm=0.90).set("mn2", warm=1.10).set("mn3", warm=0.90)  # N mean 0.9667, range 0.90 to 1.10
        lines, v, _ = f.report()
        self.assertTrue(v.startswith("U1 SYNC: NOT ACCEPTED: 1 cell(s) more than 1.0% slower (1 inside N's boots' range)"), v)
        line = self.cell(lines, "conversation turns 2+ first token: ")
        self.assertIn("<- over the limit", line)
        self.assertIn("inside N ", line)

    def test_u1_a_loss_above_every_boot_is_not_marked_inside(self):
        f = self.fx().set("mn1", warm=0.95).set("mn2", warm=1.00).set("mn3", warm=1.05).set_all(("tn1", "tn2"), warm=1.10)
        lines, v, _ = f.report()
        self.assertTrue(v.startswith("U1 SYNC: NOT ACCEPTED: 1 cell(s) more than 1.0% slower (0 inside N's boots' range)"), v)
        line = self.cell(lines, "conversation turns 2+ first token: ")
        self.assertIn("<- over the limit", line)
        self.assertNotIn("inside N ", line)


class U2Buys(Base):
    def test_u2_every_cell_prints_s0_s1_t_and_two_fractions(self):
        lines = self.lines(self.fx())
        self.assertIn("== U2 what the series buys: T (tn1 tn2) against S1 (ut1) is what the series still buys at the tip; S1 against S0 (mps sm2 sm3) is what upstream's merges since the pin gave a"
                      " stock user; faster is positive, a column of a group that did not report is no rows, never zero", lines)
        self.assertEqual(self.u2cell(lines, "cold 8k first token: "),
                         "cold 8k first token: S0 3600.0 | S1 3600.0 | T 3600.0 | T against S1 +0.00% | S1 against S0 +0.00%")
        self.assertEqual(len(self.u2_lines(lines)), 24)

    def test_u2_t_against_s1_is_faster_positive(self):
        lines = self.lines(self.fx().set_all(("tn1", "tn2"), cold=0.95))
        self.assertIn("T against S1 +5.00% | S1 against S0 +0.00%", self.u2cell(lines, "cold 8k first token: "))

    def test_u2_s1_against_s0_is_the_upstream_gain(self):
        lines = self.lines(self.fx().set("ut1", cold=0.96).set_all(("tn1", "tn2"), cold=0.96))
        self.assertEqual(self.u2cell(lines, "cold 8k first token: "), "cold 8k first token: S0 3600.0 | S1 3456.0 | T 3456.0 | T against S1 +0.00% | S1 against S0 +4.00%")

    def test_u2_the_two_fractions_have_their_own_references(self):
        lines = self.lines(self.fx().set_all(("tn1", "tn2"), dec=1.05).set_all(("mps", "sm2", "sm3"), dec=1.02))
        self.assertEqual(self.u2cell(lines, "greedy prose at 1 clients: "),
                         "greedy prose at 1 clients: S0 81.6 | S1 80.0 | T 84.0 | T against S1 +5.00% | S1 against S0 -1.96%")

    def test_u2_a_missing_boot_prints_no_rows_not_zeros(self):
        lines = self.lines(self.fx().skip("ut1"))
        self.assertIn("no rows for ut1", lines)
        self.assertIn("S1 no rows | T 3600.0 | T against S1 no rows", self.u2cell(lines, "cold 8k first token: "))
        lines = self.lines(self.fx().skip("sm2"))
        self.assertIn("no rows for sm2", lines)
        self.assertIn("S0 no rows | S1 3600.0 | T 3600.0", self.u2cell(lines, "cold 8k first token: "))
        self.assertIn("S1 against S0 no rows", self.u2cell(lines, "cold 8k first token: "))
        lines = self.lines(self.fx().skip("tn1"))
        self.assertIn("S0 3600.0 | S1 3600.0 | T no rows | T against S1 no rows | S1 against S0 +0.00%", self.u2cell(lines, "cold 8k first token: "))

    def test_u2_a_boot_without_a_cell_prints_no_rows(self):
        lines = self.lines(self.fx().set("ut1", only="cold"))
        self.assertIn("S1 3600.0", self.u2cell(lines, "cold 8k first token: "))
        self.assertIn("S1 no rows | T 811.4 | T against S1 no rows", self.u2cell(lines, "conversation turns 2+ first token: "))

    def test_u2_is_report_only(self):
        lines = self.lines(self.fx().set_all(("tn1", "tn2"), dec=0.98))
        for line in self.u2_lines(lines):
            for word in ("ACCEPTED", "DECIDED", "DIFFER", "EQUAL"):
                self.assertNotIn(word, line)


class U3Digests(Base):
    def test_u3_equal_when_every_reply_matches(self):
        lines = self.lines(self.fx())
        u3 = self.u3_lines(lines)
        self.assertIn("== U3 digests T (tn1 tn2) against S1 (ut1): one line per cell kind, a report and never a verdict", lines)
        self.assertIn("U3 cold first token: EQUAL at 6 key(s)", u3)
        self.assertIn("U3 conversation: EQUAL at 8 key(s)", u3)
        self.assertIn("U3 greedy prose: EQUAL at 5 key(s)", u3)
        self.assertIn("U3 greedy code: EQUAL at 5 key(s)", u3)
        self.assertIn("U3 sampled prose: EQUAL at 5 key(s)", u3)
        self.assertIn("U3 sampled code: EQUAL at 5 key(s)", u3)
        self.assertIn("U3 24 prompts: EQUAL at 3 key(s)", u3)

    def test_u3_one_line_per_cell_kind(self):
        self.assertEqual(self.u3_lines(self.lines(self.fx())), [
            "U3 cold first token: EQUAL at 6 key(s)",
            "U3 conversation: EQUAL at 8 key(s)",
            "U3 greedy prose: EQUAL at 5 key(s)",
            "U3 greedy code: EQUAL at 5 key(s)",
            "U3 sampled prose: EQUAL at 5 key(s)",
            "U3 sampled code: EQUAL at 5 key(s)",
            "U3 24 prompts: EQUAL at 3 key(s)"])

    def test_u3_a_differing_reply_is_differ(self):
        lines, v, failed = self.fx().set("ut1", digest="u").report()
        self.assertTrue(v.startswith("U1 SYNC: ACCEPTED"), v)  # the stack's own digests agree across N and T
        self.assertFalse(failed)
        u3 = self.u3_lines(lines)
        self.assertTrue(any(l.startswith("U3 greedy prose: DIFFER at 5 of 5 key(s)") for l in u3), u3)
        self.assertTrue(any(l.startswith("U3 24 prompts: DIFFER at 3 of 3 key(s)") for l in u3), u3)

    def test_u3_a_missing_boot_is_no_rows(self):
        u3 = self.u3_lines(self.lines(self.fx().skip("tn1")))
        self.assertTrue(all(l.endswith("no rows for T (tn1 tn2)") for l in u3), u3)

    def test_u3_a_hole_is_not_comparable(self):
        f = self.fx()
        f.write()
        (f.q92 / "dec-tn2" / "P1.jsonl").unlink()
        u3 = self.u3_lines(s97.report(str(f.q91), str(f.q92), str(f.q95))[0])
        self.assertIn("U3 greedy prose: NOT COMPARABLE, 1 of 5 key(s) missing a side's report, 0 differ", u3)
        self.assertIn("U3 greedy code: EQUAL at 5 key(s)", u3)


class Groups(Base):
    def test_group_membership_mn3_is_in_n(self):
        lines, v, _ = self.fx().set("mn3", dec=1.06).report()  # the third N boot 6% up at decode: N's mean 2% up, T 1.96% slower
        self.assertTrue(v.startswith("U1 SYNC: NOT ACCEPTED: 20 cell(s) more than 1.0% slower"), v)
        self.assertIn("84.8", self.cell(lines, "greedy prose at 1 clients: "))

    def test_group_membership_tn_arms_are_t(self):
        lines, v, _ = self.fx().set("tn2", dec=0.97).report()  # T's mean 1.5% down only if both tn boots are read
        self.assertTrue(v.startswith("U1 SYNC: NOT ACCEPTED: 20 cell(s) more than 1.0% slower"), v)
        self.assertIn("T 80.0 77.6", self.cell(lines, "greedy prose at 1 clients: "))

    def test_group_membership_s0_has_all_three_boots(self):
        lines = self.lines(self.fx().set("sm3", dec=0.90))
        self.assertIn("S1 against S0 +3.45%", self.u2cell(lines, "greedy prose at 1 clients: "))

    def test_group_membership_ut1_is_s1(self):
        lines = self.lines(self.fx().set("ut1", dec=0.96))
        self.assertIn("S1 76.8", self.u2cell(lines, "greedy prose at 1 clients: "))
        self.assertIn("T against S1 +4.17%", self.u2cell(lines, "greedy prose at 1 clients: "))


class MissingBoots(Base):
    def test_a_missing_boot_for_each_group(self):
        cases = (("mn3", "U1 SYNC: NOT DECIDED: no rows for mn3"), ("tn2", "U1 SYNC: NOT DECIDED: no rows for tn2"),
                 ("mps", "U1 SYNC: ACCEPTED"), ("sm2", "U1 SYNC: ACCEPTED"), ("ut1", "U1 SYNC: ACCEPTED"))
        for label, verdict in cases:
            with self.subTest(missing=label):
                lines, v, _ = self.fx().skip(label).report()
                self.assertTrue(v.startswith(verdict), v)
                self.assertIn(label, "\n".join(lines))
        self.assertIn("S0 no rows", self.u2cell(self.lines(self.fx().skip("mps")), "cold 8k first token: "))
        self.assertIn("S1 no rows", self.u2cell(self.lines(self.fx().skip("ut1")), "cold 8k first token: "))


class ExitCode(Base):
    def run_main(self, f):
        r = subprocess.run([sys.executable, str(SCORER), "--q91", str(f.q91), "--q92", str(f.q92), "--q95", str(f.q95)],
                           capture_output=True, text=True, timeout=900)
        return r.returncode, r.stdout

    def test_the_exit_code_is_one_when_u1_digests_differ(self):
        f = self.fx()
        f.write()
        put(f.q92 / "dec-tn2" / "C2.jsonl", [{"agg_tok_s": 90.0, "sha": ["zzz"]}])
        rc, out = self.run_main(f)
        self.assertEqual(rc, 1)
        self.assertIn("U1 SYNC: NOT ACCEPTED: reply digests differ", out)

    def test_the_exit_code_is_zero_for_a_cell_only_failure(self):
        f = self.fx().set_all(("tn1", "tn2"), dec=0.98)
        f.write()
        rc, out = self.run_main(f)
        self.assertEqual(rc, 0)
        self.assertIn("U1 SYNC: NOT ACCEPTED: 20 cell(s) more than 1.0% slower", out)

    def test_the_exit_code_is_zero_when_not_decided(self):
        f = self.fx().skip("tn1")
        f.write()
        rc, out = self.run_main(f)
        self.assertEqual(rc, 0)
        self.assertIn("U1 SYNC: NOT DECIDED: no rows for tn1", out)

    def test_the_defaults_are_the_three_directories(self):
        r = subprocess.run([sys.executable, str(SCORER), "--help"], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0)
        self.assertIn("queue91/f91-c", r.stdout)
        self.assertIn("work/pp92/f92-c", r.stdout)
        self.assertIn("work/pp95/f95-c", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
