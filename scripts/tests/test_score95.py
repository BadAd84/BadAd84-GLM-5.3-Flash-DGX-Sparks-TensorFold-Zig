#!/usr/bin/env python3
"""test_score95.py: scripts/queue-scores/score95.py's five clauses on fixture row trees laid out as queue91 writes them.

Run from the top-level shell: python scripts/tests/test_score95.py
SCORE95=<path> points the tests at a copy of the scorer (scripts/tests/mutants_score95.py runs them against each mutant that way).

The rows are written by test_score91.py's put(), in its row format, and one builder here adds the per-cell decode scale the attribution rule needs. An exact 1.0% slower cell
cannot be built by division (the nearest double to 1.01 is 1.010000000000000009), so the K1 limit is bracketed at 0.99% accepted and 1.01% flagged, and the K2 mean boundary
at -0.5% IS built exactly: 9 decode cells at 0.99 and 3 at 1.01 give a mean of -0.50000000000000044%, at or below -0.5%, with exactly 9 negative.
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


_OVER = os.environ.get("SCORE95")
SCORER = pathlib.Path(_OVER) if _OVER else ROOT / "scripts/queue-scores/score95.py"
s95 = load("score95", SCORER)
T91 = load("test_score91", ROOT / "scripts/tests/test_score91.py")  # its put(), COLD, TURNS and DEC: queue91's row shape, one owner
put = T91.put
COLD = T91.COLD
TURNS = T91.TURNS
DEC = T91.DEC
CELLS12 = [(k, n) for k in ("P", "C", "SP", "SC") for n in (1, 2, 4)]

Q91_LABELS = ("mn1", "mn2", "md1", "md2", "mo3")
Q95_LABELS = ("mn3", "mt1", "mt2", "mx1", "mx2", "mo4")
OLD_LABELS = ("P1", "P2")
ALL = Q91_LABELS + Q95_LABELS + OLD_LABELS
N_LABELS = ("mn1", "mn2", "mn3")


def wboot(d, label, cold=1.0, warm=1.0, dec=1.0, per=None, digest="a", only=None):
    """One boot's rows in queue91's format: test_score91.write_boot's shape, plus a per-(kind, level) decode scale so one K2 cell can move on its own."""
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
            for n in s95.LEVELS:
                s = (per or {}).get((kind, n), dec)
                put(d / f"dec-{label}" / f"{kind}{n}.jsonl", [{"agg_tok_s": base * n ** 0.5 * s, "sha": [f"{digest}{kind}{n}x", f"{digest}{kind}{n}y"]}] * 3)
        put(d / f"dec-{label}" / "pp.jsonl", [{"name": f"p{i}", "sha12": f"{digest}pp{i}"} for i in range(3)])


class Fixture:
    """The three queues' row trees: every boot at its default keyword, then the test's own, rewritten whole from scratch on demand."""

    def __init__(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="score95-", dir=ROOT / "work"))
        self.q91, self.q95, self.old = self.root / "q91", self.root / "q95", self.root / "old"
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
        return self.q91 if label in Q91_LABELS else self.q95 if label in Q95_LABELS else self.old

    def write(self):
        shutil.rmtree(self.root, ignore_errors=True)
        for label in ALL:
            if label not in self.out:
                wboot(self.dir(label), label, **self.kw[label])
        return self

    def report(self):
        self.write()
        return s95.report(str(self.q91), str(self.q95), str(self.old))

    def verdicts(self):
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


class K1Sync(Base):
    def test_k1_accepted_when_every_cell_and_digest_agrees(self):
        v = self.fx().verdicts()
        self.assertEqual(v["K1"], "K1 SYNC: ACCEPTED, no cell more than 1% slower and every reply digest equal")

    def test_k1_prints_both_groups_boots_and_every_cells_values(self):
        text = self.text(self.fx())
        self.assertIn("== K1 sync: N (mn1 mn2 mn3) against O (P1 P2 mo3 mo4)", text)
        line = next(l for l in text.splitlines() if l.startswith("cold 8k first token: "))
        self.assertEqual(line, f"cold 8k first token: N {COLD[8000]:.1f} {COLD[8000]:.1f} {COLD[8000]:.1f} | O {COLD[8000]:.1f} {COLD[8000]:.1f} {COLD[8000]:.1f} {COLD[8000]:.1f} | +0.00% slower")

    def test_k1_a_cell_over_the_limit_is_named(self):
        f = self.fx().set("mn3", per={("P", 8): 0.95})  # one N boot 5% down at greedy prose 8 clients: the group mean 1.67% down
        lines, v, _ = f.report()
        self.assertTrue(v["K1"].startswith("K1 SYNC: NOT ACCEPTED: 1 cell(s) more than 1% slower"), v["K1"])
        self.assertIn("greedy prose at 8 clients", v["K1"])
        self.assertTrue(any("<- over the limit" in l and l.startswith("greedy prose at 8 clients: N ") for l in lines), [l for l in lines if "8 clients" in l])

    def test_k1_the_limit_is_one_percent(self):
        self.assertTrue(self.fx().set_all(N_LABELS, cold=1.0099).verdicts()["K1"].startswith("K1 SYNC: ACCEPTED"))
        v = self.fx().set_all(N_LABELS, cold=1.0101).verdicts()["K1"]
        self.assertTrue(v.startswith("K1 SYNC: NOT ACCEPTED"), v)
        self.assertIn("cold 8k first token", v)
        self.assertIn("cold 120k first token", v)

    def test_k1_a_latency_cell_up_is_slower_and_down_is_not(self):
        v = self.fx().set_all(N_LABELS, warm=1.02).verdicts()["K1"]
        self.assertIn("conversation turns 2+ first token", v)
        self.assertTrue(self.fx().set_all(N_LABELS, warm=0.98).verdicts()["K1"].startswith("K1 SYNC: ACCEPTED"))

    def test_k1_throughput_up_is_not_slower(self):
        self.assertTrue(self.fx().set_all(N_LABELS, dec=1.05).verdicts()["K1"].startswith("K1 SYNC: ACCEPTED"))

    def test_k1_a_different_reply_digest_is_not_accepted(self):
        f = self.fx()
        f.write()
        put(f.q95 / "dec-mn3" / "pp.jsonl", [{"name": "p1", "sha12": "changed"}])
        v = s95.report(str(f.q91), str(f.q95), str(f.old))[1]["K1"]
        self.assertTrue(v.startswith("K1 SYNC: NOT ACCEPTED: reply digests differ at 1 key(s)"), v)

    def test_k1_a_missing_boot_is_not_decided(self):
        v = self.fx().skip("mn3").verdicts()["K1"]
        self.assertEqual(v, "K1 SYNC: NOT DECIDED: no rows for mn3")

    def test_k1_a_cell_not_reported_by_every_boot_is_not_decided(self):
        lines, v, _ = self.fx().set("mn3", only="cold").report()
        self.assertTrue(v["K1"].startswith("K1 SYNC: NOT DECIDED"), v["K1"])
        self.assertIn("conversation turns 2+ first token", v["K1"])
        self.assertIn("conversation turns 2+ first token: N measured on 2 of 3 boots, O on 4 of 4: NOT DECIDED", "\n".join(lines))

    def test_k1_a_missing_digest_report_is_not_decided(self):
        f = self.fx()
        f.write()
        (f.q95 / "dec-mn3" / "pp.jsonl").unlink()
        lines, v, _ = s95.report(str(f.q91), str(f.q95), str(f.old))
        self.assertTrue(v["K1"].startswith("K1 SYNC: NOT DECIDED"), v["K1"])
        self.assertIn("digest", v["K1"])
        self.assertTrue(any("missing: ('pp'" in l for l in lines) or any("('pp', 'p0')" in l and "missing" in l for l in lines), lines)


class K2Decode(Base):
    def k2(self, f):
        return f.verdicts()["K2"]

    def test_k2_clean_when_no_cell_moves(self):
        self.assertEqual(self.k2(self.fx()), {"D": "CLEAN", "T": "CLEAN", "X": "CLEAN"})

    def test_k2_carries_the_loss_at_the_boundary(self):
        per = {c: (0.99 if i < 9 else 1.01) for i, c in enumerate(CELLS12)}
        f = self.fx().set("mt1", per=per).set("mt2", per=per)  # mean -0.50000000000000044%, 9 of 12 negative
        lines, v, _ = f.report()
        self.assertEqual(v["K2"]["T"], "CARRIES THE LOSS")
        self.assertTrue(any("mean -0.50% of 12 cells, 9 negative: CARRIES THE LOSS" in l for l in lines), [l for l in lines if l.startswith("T (")])
        self.assertEqual(v["K2"]["X"], "CLEAN")

    def test_k2_eight_negative_cells_do_not_carry(self):
        per = {c: (0.98 if i < 8 else 1.02) for i, c in enumerate(CELLS12)}  # mean -0.67%, only 8 negative
        f = self.fx().set("mt1", per=per).set("mt2", per=per)
        lines, v, _ = f.report()
        self.assertEqual(v["K2"]["T"], "UNCLEAR")
        self.assertTrue(any("mean -0.67% of 12 cells, 8 negative: UNCLEAR" in l for l in lines), [l for l in lines if l.startswith("T (")])

    def test_k2_a_mid_band_mean_is_unclear_and_the_edges_are_not(self):
        per = {c: 0.996 for c in CELLS12}  # mean -0.40%: not at or below -0.5%, not at or above -0.3%
        f = self.fx().set("mt1", per=per).set("mt2", per=per)
        self.assertEqual(self.k2(f)["T"], "UNCLEAR")
        g = self.fx().set("mt1", per={c: 0.9985 for c in CELLS12}).set("mt2", per={c: 0.9985 for c in CELLS12})
        self.assertEqual(self.k2(g)["T"], "CLEAN")  # mean -0.15%

    def test_k2_not_decided_when_a_boot_reports_no_decode(self):
        v = self.k2(self.fx().set("mt1", only="cold"))
        self.assertEqual(v["T"], "NOT DECIDED")
        self.assertEqual(v["D"], "CLEAN")

    def test_k2_d_not_decided_when_its_own_boot_is_missing(self):
        v = self.k2(self.fx().skip("md2"))
        self.assertEqual(v["D"], "NOT DECIDED")
        self.assertEqual(v["T"], "CLEAN")
        self.assertEqual(v["X"], "CLEAN")

    def test_k2_all_arms_not_decided_when_n_is_missing(self):
        v = self.k2(self.fx().skip("mn3"))
        self.assertEqual(v, {"D": "NOT DECIDED", "T": "NOT DECIDED", "X": "NOT DECIDED"})

    def test_k2_prints_the_twelve_changes_and_the_mean(self):
        text = self.text(self.fx())
        for kind in ("greedy prose", "greedy code", "sampled prose", "sampled code"):
            for n in (1, 2, 4):
                self.assertIn(f"{kind} at {n} clients", text)
        self.assertEqual(text.count("mean +0.00% of 12 cells, 0 negative: CLEAN"), 3)


class K3Prompt(Base):
    def k3(self, f):
        return f.verdicts()["K3"]

    def test_k3_gains_at_the_inclusive_one_percent(self):
        f = self.fx().set("mt1", cold=0.99).set("mt2", cold=0.99)  # 1.0000000000000009% faster at every cold size
        lines, v, _ = f.report()
        self.assertEqual(v["K3"]["T"], "GAINS")
        self.assertTrue(any(l.startswith("T (") and "cold 8k first token +1.00%" in l for l in lines), [l for l in lines if l.startswith("T (")])

    def test_k3_a_cell_slower_by_more_than_one_percent_is_no_gain(self):
        f = self.fx().set("mt1", cold=0.98, warm=1.02).set("mt2", cold=0.98, warm=1.02)
        self.assertEqual(self.k3(f)["T"], "NO GAIN")

    def test_k3_not_decided_when_a_boot_reports_no_conversation(self):
        v = self.k3(self.fx().set("mx1", only="cold"))
        self.assertEqual(v["X"], "NOT DECIDED")
        self.assertEqual(v["T"], "NO GAIN")

    def test_k3_a_faster_cell_under_one_percent_is_no_gain(self):
        f = self.fx().set("mt1", cold=0.995).set("mt2", cold=0.995)
        self.assertEqual(self.k3(f)["T"], "NO GAIN")

    def test_k3_x_not_decided_without_its_boot_while_t_is(self):
        lines, v, _ = self.fx().skip("mx2").report()
        self.assertEqual(v["K3"]["X"], "NOT DECIDED")
        self.assertEqual(v["K3"]["T"], "NO GAIN")
        self.assertTrue(any("X (mx1 mx2): NOT DECIDED: no rows for mx2" in l for l in lines), lines)


class K4Digests(Base):
    def test_k4_equal_when_every_digest_agrees(self):
        _, v, failed = self.fx().report()
        self.assertEqual(v["K4"], {"T": "EQUAL", "X": "EQUAL"})
        self.assertFalse(failed)

    def test_k4_one_differing_decode_cell_fails_the_arm(self):
        f = self.fx()
        f.write()
        put(f.q95 / "dec-mt1" / "P1.jsonl", [{"agg_tok_s": 80.0, "sha": ["zzz"]}])
        lines, v, failed = s95.report(str(f.q91), str(f.q95), str(f.old))
        self.assertEqual(v["K4"]["T"], "DIFFERS")
        self.assertEqual(v["K4"]["X"], "EQUAL")
        self.assertTrue(failed)
        self.assertTrue(any("differs: ('dec', 'P', 1)" in l for l in lines), lines)

    def test_k4_a_differing_prompt_digest_fails_the_arm(self):
        f = self.fx()
        f.write()
        put(f.q95 / "dec-mx1" / "pp.jsonl", [{"name": "p1", "sha12": "changed"}])
        v = s95.report(str(f.q91), str(f.q95), str(f.old))[1]
        self.assertEqual(v["K4"]["X"], "DIFFERS")
        self.assertEqual(v["K4"]["T"], "EQUAL")

    def test_k4_a_missing_report_is_not_decided_and_does_not_fail(self):
        f = self.fx()
        f.write()
        (f.q95 / "dec-mx2" / "P1.jsonl").unlink()
        lines, v, failed = s95.report(str(f.q91), str(f.q95), str(f.old))
        self.assertEqual(v["K4"]["X"], "NOT DECIDED")
        self.assertFalse(failed)
        self.assertTrue(any("missing: X ('dec', 'P', 1)" in l for l in lines), lines)


class K5Promotion(Base):
    def test_k5_promotable(self):
        f = self.fx().set("mt1", cold=0.99).set("mt2", cold=0.99)  # clean decode, a prompt gain, equal digests
        _, v, _ = f.report()
        self.assertEqual(v["K5"]["T"], "PROMOTABLE")
        self.assertEqual(v["K5"]["X"], "UNCLEAR")

    def test_k5_hold_back_when_the_arm_carries_the_loss(self):
        per = {c: (0.99 if i < 9 else 1.01) for i, c in enumerate(CELLS12)}
        f = self.fx().set("mt1", per=per).set("mt2", per=per)
        self.assertEqual(f.verdicts()["K5"]["T"], "HOLD BACK")

    def test_k5_hold_back_on_a_k4_difference(self):
        f = self.fx().set("mt1", cold=0.99).set("mt2", cold=0.99)
        f.write()
        put(f.q95 / "dec-mt1" / "P1.jsonl", [{"agg_tok_s": 80.0, "sha": ["zzz"]}])
        _, v, _ = s95.report(str(f.q91), str(f.q95), str(f.old))
        self.assertEqual(v["K2"]["T"], "CLEAN")
        self.assertEqual(v["K3"]["T"], "GAINS")
        self.assertEqual(v["K4"]["T"], "DIFFERS")
        self.assertEqual(v["K5"]["T"], "HOLD BACK")

    def test_k5_unclear_between_the_clauses(self):
        self.assertEqual(self.fx().verdicts()["K5"]["T"], "UNCLEAR")  # clean decode, no prompt gain

    def test_k5_the_additivity_line_carries_d_t_x_and_their_sum(self):
        f = self.fx().set_all(("md1", "md2", "mt1", "mt2", "mx1", "mx2"), cold=0.99)
        lines, v, _ = f.report()
        self.assertEqual(v["K3"]["D"], "GAINS")
        line = next(l for l in lines if l.startswith("  cold 8k first token: D "))
        self.assertEqual(line, "  cold 8k first token: D +1.00%, T +1.00%, X +1.00%, T+X +2.00%")


class ClauseIsolation(Base):
    """Each clause flips alone: the change moves exactly one verdict, so a broken clause is named by its own test."""

    def test_k1_alone_flips(self):
        f = self.fx().set("mn3", per={("P", 8): 0.94})  # an 8-client cell, outside K2's 1, 2 and 4, and no cold or warm effect
        _, v, _ = f.report()
        self.assertTrue(v["K1"].startswith("K1 SYNC: NOT ACCEPTED"), v["K1"])
        self.assertEqual(v["K2"], {"D": "CLEAN", "T": "CLEAN", "X": "CLEAN"})
        self.assertEqual(v["K3"], {"D": "NO GAIN", "T": "NO GAIN", "X": "NO GAIN"})
        self.assertEqual(v["K4"], {"T": "EQUAL", "X": "EQUAL"})

    def test_k2_alone_flips(self):
        per = {c: 0.98 for c in CELLS12}
        f = self.fx().set("mt1", per=per).set("mt2", per=per)
        _, v, _ = f.report()
        self.assertTrue(v["K1"].startswith("K1 SYNC: ACCEPTED"))
        self.assertEqual(v["K2"]["T"], "CARRIES THE LOSS")
        self.assertEqual(v["K3"]["T"], "NO GAIN")
        self.assertEqual(v["K4"]["T"], "EQUAL")

    def test_k3_alone_flips(self):
        f = self.fx().set("mt1", cold=0.99).set("mt2", cold=0.99)
        _, v, _ = f.report()
        self.assertTrue(v["K1"].startswith("K1 SYNC: ACCEPTED"))
        self.assertEqual(v["K2"]["T"], "CLEAN")
        self.assertEqual(v["K3"]["T"], "GAINS")
        self.assertEqual(v["K4"]["T"], "EQUAL")

    def test_k4_alone_flips(self):
        f = self.fx()
        f.write()
        put(f.q95 / "dec-mt1" / "pp.jsonl", [{"name": "p2", "sha12": "changed"}])
        _, v, _ = s95.report(str(f.q91), str(f.q95), str(f.old))
        self.assertTrue(v["K1"].startswith("K1 SYNC: ACCEPTED"))
        self.assertEqual(v["K2"]["T"], "CLEAN")
        self.assertEqual(v["K3"]["T"], "NO GAIN")
        self.assertEqual(v["K4"]["T"], "DIFFERS")


class Groups(Base):
    def test_group_membership_the_slow_data_is_t_or_x_by_its_label(self):
        per = {c: 0.98 for c in CELLS12}
        t = self.fx().set("mt1", per=per).set("mt2", per=per)
        self.assertEqual(t.verdicts()["K2"], {"D": "CLEAN", "T": "CARRIES THE LOSS", "X": "CLEAN"})
        x = self.fx().set("mx1", per=per).set("mx2", per=per)
        self.assertEqual(x.verdicts()["K2"], {"D": "CLEAN", "T": "CLEAN", "X": "CARRIES THE LOSS"})

    def test_group_membership_mn3_is_in_n(self):
        v = self.fx().set("mn3", per={("P", 8): 0.94}).verdicts()["K1"]
        self.assertIn("greedy prose at 8 clients", v)  # mn3 moves N's mean; were it not read, N would equal O
        self.assertIn("mn3", self.text(self.fx().set("mn3", per={("P", 8): 0.94})))

    def test_group_membership_mo4_is_in_o(self):
        f = self.fx().set("mo4", per={("C", 8): 1.10})  # O's mean up at greedy code 8 clients: N 2.4% slower than O
        self.assertIn("greedy code at 8 clients", f.verdicts()["K1"])


class MissingBoots(Base):
    def test_each_missing_boot_is_not_decided_and_named(self):
        for label in ALL:
            with self.subTest(missing=label):
                lines, v, _ = self.fx().skip(label).report()
                text = "\n".join(lines)
                self.assertIn("NOT DECIDED", text)
                self.assertIn(label, text)
                self.assertNotIn("T: PROMOTABLE", text)
                self.assertNotIn("X: PROMOTABLE", text)


class ExitCode(Base):
    def run_main(self, f):
        r = subprocess.run([sys.executable, str(SCORER), "--q91", str(f.q91), "--q95", str(f.q95), "--old", str(f.old)],
                           capture_output=True, text=True, timeout=900)
        return r.returncode, r.stdout

    def test_the_exit_code_is_one_when_a_k4_digest_differs(self):
        f = self.fx()
        f.write()
        put(f.q95 / "dec-mx2" / "C2.jsonl", [{"agg_tok_s": 90.0, "sha": ["zzz"]}])
        rc, out = self.run_main(f)
        self.assertEqual(rc, 1)
        self.assertIn("X: DIFFERS", out)

    def test_the_exit_code_is_zero_when_clauses_are_not_decided(self):
        f = self.fx().skip("mn3")
        f.write()
        rc, out = self.run_main(f)
        self.assertEqual(rc, 0)
        self.assertIn("K1 SYNC: NOT DECIDED: no rows for mn3", out)
        self.assertIn("T: UNCLEAR", out)

    def test_the_defaults_are_the_three_directories(self):
        r = subprocess.run([sys.executable, str(SCORER), "--help"], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0)
        self.assertIn("work/pp91/f91-c", r.stdout)
        self.assertIn("work/pp95/f95-c", r.stdout)
        self.assertIn("queue77/f77-c", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
