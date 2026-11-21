#!/usr/bin/env python3
"""test_score101.py: scripts/queue-scores/score101.py's five readings on a fixture row tree laid out as queue101 writes it (queue92's f92-c layout, five boots, and the
drafter/dscores proof files).

Run from the top-level shell: python scripts/tests/test_score101.py
SCORE101=<path> points the tests at a copy of the scorer (scripts/tests/mutants_score101.py runs them against each mutant that way).

The rows are written by test_score91.py's put(), COLD, TURNS and DEC (queue91's row shape, one owner), with the two fields chaindec reads added to the chain rows and a facts
row per boot carrying prompt_cache_budget_bytes. The drafter line is the engine's own (dflash_load.zig: "dflash2: drafter from {s} (Apache-2.0), linears at {d} bits,
{d:.2} GiB on the device"), as queue92.sh line 105 already stores it. ut1's two proof files are optional (queue96 predates them and queue101 does not re-run it); the four
ut2 boots must have theirs, and the fixture's ut1_proofs switch writes ut1 without them.
"""
import importlib.util
import json
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


_OVER = os.environ.get("SCORE101")
SCORER = pathlib.Path(_OVER) if _OVER else ROOT / "scripts/queue-scores/score101.py"
s101 = load("score101", SCORER)
T91 = load("test_score91", ROOT / "scripts/tests/test_score91.py")  # its put(), COLD, TURNS and DEC: queue91's row shape, one owner
put = T91.put
COLD = T91.COLD
TURNS = T91.TURNS
DEC = T91.DEC
LEVELS = s101.S91.LEVELS
ALL = s101.ALL
UT1, UT2, SPLIT, DSC = s101.UT1, s101.UT2, s101.SPLIT, s101.DSC

DRAFTER_STOCK = "dflash2: drafter from /models/dflash2 (Apache-2.0), linears at 4 bits, 0.93 GiB on the device"
DRAFTER_SPLIT = "dflash2: drafter from /models/dflash2 (Apache-2.0), linears at 4 bits, 0.44 GiB on the device"
DSC0 = "TF_GLM_DSCORES=0: a decode window's index scores keep tf_glm_scores"
DSCFAIL = "TF_GLM_DSCORES: glm_index is not loaded (build without it); decode windows keep tf_glm_scores"
NOTE = "note: ut1 ran in queue96, hours before these boots; a difference between boots of different sessions that is not larger than the ut2 group's own spread cannot be told from a change"


def wboot(d, label, cold=1.0, warm=1.0, dec=1.0, per=None, digest="a", rate=70.0, cached=100000, budget=6924583936,
          drafter=DRAFTER_STOCK, dscores="NONE", only=None, proofs=True):
    """One boot's rows and proof files: latencies scaled by `cold` and `warm`, decode throughputs by `dec` or by (kind, level) in `per`, every reply digest `digest`, the
    resumed chain turns at `rate` tok/s with `cached` rows, a facts row with `budget` bytes, and the two proof files (skipped when `proofs` is false)."""
    d = pathlib.Path(d)
    if only in (None, "cold"):
        for size, ms in COLD.items():
            for rep in (1, 2):
                put(d / "rows.jsonl", [{"tag": label, "case": "cold", "target_tokens": size, "rep": rep, "ttft_ms": ms * cold, "token_sha": f"{digest}{size}{rep}"}])
    if only in (None, "chain"):
        for t, ms in enumerate(TURNS, 1):
            r = {"tag": "c74", "turn": t, "ttft_ms": ms * (warm if t > 1 else 1.0), "token_sha": f"{digest}t{t}", "completion_tokens": 128}
            r.update({"decode_tok_s": rate, "cached_tokens": cached, "prompt_tokens": 114000} if t > 1 else {"decode_tok_s": None, "cached_tokens": 0, "prompt_tokens": 112702})
            put(d / label / "chain.jsonl", [r])
    if only in (None, "dec"):
        for kind, base in DEC.items():
            for n in LEVELS:
                s = (per or {}).get((kind, n), dec)
                put(d / f"dec-{label}" / f"{kind}{n}.jsonl", [{"agg_tok_s": base * n ** 0.5 * s, "sha": [f"{digest}{kind}{n}x", f"{digest}{kind}{n}y"]}] * 3)
        put(d / f"dec-{label}" / "pp.jsonl", [{"name": f"p{i}", "sha12": f"{digest}pp{i}"} for i in range(3)])
    if budget is not None:
        put(d / "rows.jsonl", [{"tag": label, "case": "boot", "n": 4, "ctx": 1048576, "boot_rc": 0, "metrics": {"prompt_cache_budget_bytes": budget}}])
    if proofs:
        (d / f"{label}-drafter.txt").write_text(drafter + "\n", encoding="utf-8", newline="\n")
        (d / f"{label}-dscores.txt").write_text(dscores + "\n", encoding="utf-8", newline="\n")


class Fixture:
    """queue101's one row directory: every boot at its defaults (stock drafter, no dscores line; ut2s split, ut2d the DSCORES=0 line), then the test's own. ut1_proofs writes
    ut1's two proof files or leaves them out, as queue96's real boot does."""

    def __init__(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="score101-", dir=ROOT / "work"))
        self.q = self.root / "q101"
        self.kw = {label: {} for label in ALL}
        self.drafter = {SPLIT: DRAFTER_SPLIT}
        self.dscores = {DSC: DSC0}
        self.ut1_proofs = True
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
        shutil.rmtree(self.q, ignore_errors=True)
        for label in ALL:
            if label in self.out:
                continue
            kw = dict(self.kw[label])
            kw.setdefault("drafter", self.drafter.get(label, DRAFTER_STOCK))
            kw.setdefault("dscores", self.dscores.get(label, "NONE"))
            if label == UT1:
                kw.setdefault("proofs", self.ut1_proofs)
            wboot(self.q, label, **kw)
        return self

    def report(self):
        self.write()
        return s101.report(str(self.q))

    def text(self):
        return "\n".join(self.report()[0])

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Base(unittest.TestCase):
    def fx(self):
        f = Fixture()
        self.addCleanup(f.close)
        return f

    def run_main(self, *args):
        r = subprocess.run([sys.executable, str(SCORER), *args], capture_output=True, text=True, timeout=900)
        return r.returncode, r.stdout

    def block(self, text, head, tail):
        return text.split(head)[1].split(tail)[0]

    def assert_void(self, lines):
        last = lines[-1]
        self.assertTrue(last.startswith("U-VERDICT: U0 ARM DID NOT TAKE EFFECT ("), last)
        self.assertTrue(last.endswith("): the U1, U2 and U3 readings above are void"), last)
        self.assertNotIn("CANDIDATE", last)
        self.assertNotIn("gain(s)", last)


class Parser(Base):
    def test_the_drafter_line_parser_reads_the_gib_value(self):
        self.assertEqual(s101.drafter_value(DRAFTER_STOCK), 0.93)
        self.assertEqual(s101.drafter_value(DRAFTER_SPLIT), 0.44)
        self.assertEqual(s101.drafter_value("dflash2: drafter from /m (Apache-2.0), linears at 16 bits, 1.00 GiB on the device"), 1.00)

    def test_the_parser_rejects_a_line_without_the_phrase(self):
        self.assertIsNone(s101.drafter_value("dflash2: drafter from /m (Apache-2.0)"))
        self.assertIsNone(s101.drafter_value(""))
        self.assertIsNone(s101.drafter_value(None))


class U0(Base):
    def test_u0_qualified_when_both_proofs_hold(self):
        lines, v = self.fx().report()
        self.assertEqual(v["U0"], "QUALIFIED")
        text = "\n".join(lines)
        self.assertIn("U0: QUALIFIED: ut2s's drafter 0.44 GiB is below 0.6, the stock three are equal at 0.93 GiB, and only ut2d carries TF_GLM_DSCORES=0", text)
        self.assertIn("U0 drafter GiB: ut2a 0.93, ut2b 0.93, ut2s 0.44, ut2d 0.93, ut1 0.93", text)

    def test_u0_qualified_without_ut1s_proof_files(self):
        f = self.fx()
        f.ut1_proofs = False
        lines, v = f.report()
        self.assertEqual(v["U0"], "QUALIFIED")
        text = "\n".join(lines)
        self.assertIn("drafter ut1: not recorded (queue96 predates the proof files)", text)
        self.assertIn("dscores ut1: not recorded (queue96 predates the proof files)", text)
        self.assertIn("U0 drafter GiB: ut2a 0.93, ut2b 0.93, ut2s 0.44, ut2d 0.93\n", text)
        self.assertTrue(lines[-1].startswith("U-VERDICT: U0 QUALIFIED;"), lines[-1])

    def test_u0_ignores_ut1s_proof_files_when_present(self):
        f = self.fx()
        f.drafter[UT1] = DRAFTER_SPLIT
        f.dscores[UT1] = DSCFAIL
        lines, v = f.report()
        self.assertEqual(v["U0"], "QUALIFIED")
        text = "\n".join(lines)
        self.assertIn("U0 drafter GiB: ut2a 0.93, ut2b 0.93, ut2s 0.44, ut2d 0.93, ut1 0.44", text)
        self.assertIn(f"dscores ut1: {DSCFAIL}", text)

    def test_u0_a_split_arm_that_did_not_split_fails(self):
        f = self.fx()
        f.drafter["ut2s"] = DRAFTER_STOCK
        lines, v = f.report()
        self.assertEqual(v["U0"], "ARM DID NOT TAKE EFFECT")
        text = "\n".join(lines)
        self.assertIn("U0 ARM DID NOT TAKE EFFECT: ut2s's drafter 0.93 GiB is not below 0.6", text)
        self.assertIn("U-VERDICT: U0 ARM DID NOT TAKE EFFECT (ut2s's drafter 0.93 GiB is not below 0.6)", lines[-1])
        self.assert_void(lines)

    def test_u0_the_stock_three_must_be_equal(self):
        f = self.fx()
        f.drafter["ut2d"] = DRAFTER_STOCK.replace("0.93", "0.94")
        lines, v = f.report()
        self.assertEqual(v["U0"], "ARM DID NOT TAKE EFFECT")
        self.assertIn("the stock drafter differs: ut2a 0.93, ut2b 0.93, ut2d 0.94 GiB", "\n".join(lines))
        self.assert_void(lines)

    def test_u0_ut2d_without_the_dscores_zero_line_fails(self):
        f = self.fx()
        f.dscores[DSC] = "NONE"
        lines, v = f.report()
        self.assertEqual(v["U0"], "ARM DID NOT TAKE EFFECT")
        self.assertIn("ut2d carries no line with TF_GLM_DSCORES=0 (it says NONE)", "\n".join(lines))
        self.assert_void(lines)

    def test_u0_a_default_boot_with_a_dscores_line_fails(self):
        f = self.fx()
        f.dscores["ut2a"] = DSCFAIL
        lines, v = f.report()
        self.assertEqual(v["U0"], "ARM DID NOT TAKE EFFECT")
        self.assertIn("ut2a is a default boot but carries TF_GLM_DSCORES: glm_index is not loaded", "\n".join(lines))
        self.assert_void(lines)

    def test_u0_a_missing_dscores_file_is_not_decided(self):
        f = self.fx()
        f.write()
        (f.q / "ut2s-dscores.txt").unlink()
        lines, v = s101.report(str(f.q))
        self.assertEqual(v["U0"], "NOT DECIDED")
        self.assertIn("ut2s: missing file ut2s-dscores.txt", "\n".join(lines))
        self.assertTrue(lines[-1].startswith("U-VERDICT: NOT DECIDED: "), lines[-1])

    def test_u0_a_dscores_file_saying_missing_is_not_decided(self):
        f = self.fx()
        f.dscores["ut2b"] = "MISSING"
        lines, v = f.report()
        self.assertEqual(v["U0"], "NOT DECIDED")
        self.assertIn("ut2b: no dscores report in ut2b-dscores.txt", "\n".join(lines))

    def test_u0_a_missing_drafter_file_is_not_decided(self):
        f = self.fx()
        f.write()
        (f.q / "ut2b-drafter.txt").unlink()
        lines, v = s101.report(str(f.q))
        self.assertEqual(v["U0"], "NOT DECIDED")
        self.assertIn("ut2b: missing file ut2b-drafter.txt", "\n".join(lines))
        self.assertTrue(lines[-1].startswith("U-VERDICT: NOT DECIDED: "), lines[-1])

    def test_u0_a_drafter_file_saying_missing_is_not_decided(self):
        f = self.fx()
        f.drafter["ut2d"] = "MISSING"
        lines, v = f.report()
        self.assertEqual(v["U0"], "NOT DECIDED")
        self.assertIn("ut2d: no drafter line in ut2d-drafter.txt", "\n".join(lines))

    def test_u0_prints_the_drafter_and_dscores_lines_of_every_boot(self):
        text = self.fx().text()
        self.assertIn(f"drafter ut2s: {DRAFTER_SPLIT}", text)
        self.assertIn("drafter ut1: dflash2: drafter from /models/dflash2 (Apache-2.0), linears at 4 bits, 0.93 GiB on the device", text)
        self.assertIn(f"dscores ut2d: {DSC0}", text)
        for label in ("ut1", "ut2a", "ut2b", "ut2s"):
            self.assertIn(f"dscores {label}: none", text)


class Completeness(Base):
    def test_a_missing_ut2_boot_is_not_decided(self):
        lines, v = self.fx().skip("ut2d").report()
        self.assertEqual(v["U0"], "NOT DECIDED")
        self.assertEqual(lines[-1], "U-VERDICT: NOT DECIDED: no rows for ut2d")

    def test_a_missing_ut1_is_not_decided(self):
        lines, v = self.fx().skip(UT1).report()
        self.assertEqual(v["U0"], "NOT DECIDED")
        self.assertIn("no rows for ut1", lines[-1])

    def test_a_cell_missing_from_a_boot_is_not_decided(self):
        lines, v = self.fx().set("ut2a", only="cold").report()
        self.assertEqual(v["U0"], "NOT DECIDED")
        text = "\n".join(lines)
        self.assertIn("ut2a:conversation turns 2+ first token", text)
        self.assertTrue(lines[-1].startswith("U-VERDICT: NOT DECIDED: "), lines[-1])


class U1(Base):
    def test_the_u1_caveat_line_is_present_and_not_in_u2(self):
        text = self.fx().text()
        self.assertIn(NOTE, self.block(text, "== U1 tip rung", "== U2 DRAFT_SPLIT"))
        self.assertNotIn("note:", self.block(text, "== U2 DRAFT_SPLIT", "== U3 DSCORES"))

    def test_u1_the_spread_is_the_larger_bound_when_it_exceeds_one_percent(self):
        f = self.fx().set("ut2a", per={("P", 1): 1.04}).set("ut2b", per={("P", 1): 1.10})
        text = f.text()
        line = next(l for l in text.splitlines() if l.startswith("greedy prose at 1 clients: "))
        self.assertIn("no CLEAR (ut2a +4.00%, ut2b +10.00%, bound 5.61%)", line)
        self.assertIn("CLEAR counts: prompt cells 0 gain(s) / 0 loss(es), decode 1/2/4 0 gain(s) / 0 loss(es), decode 6/8 0 gain(s) / 0 loss(es)", text)

    def test_u1_the_one_percent_limit_is_the_larger_bound_when_the_spread_is_smaller(self):
        f = self.fx().set("ut2a", per={("P", 1): 1.04}).set("ut2b", per={("P", 1): 1.045})
        line = next(l for l in f.text().splitlines() if l.startswith("greedy prose at 1 clients: "))
        self.assertIn("CLEAR gain (ut2a +4.00%, ut2b +4.50%, bound 1.00%)", line)

    def test_u1_clear_gain_when_both_boots_are_beyond_the_spread(self):
        f = self.fx().set("ut2a", per={("C", 8): 1.10}).set("ut2b", per={("C", 8): 1.14})
        line = next(l for l in f.text().splitlines() if l.startswith("greedy code at 8 clients: "))
        self.assertIn("CLEAR gain (ut2a +10.00%, ut2b +14.00%, bound 3.57%)", line)

    def test_u1_clear_loss_for_latency(self):
        f = self.fx().set("ut2a", cold=1.04).set("ut2b", cold=1.05)
        text = f.text()
        line = next(l for l in text.splitlines() if l.startswith("cold 8k first token: "))
        self.assertIn("CLEAR loss (ut2a -4.00%, ut2b -5.00%, bound 1.00%)", line)
        self.assertIn("prompt cells 0 gain(s) / 3 loss(es)", text)

    def test_u1_counts_are_per_cell_group(self):
        f = self.fx().set("ut2a", per={("P", 1): 1.04}).set("ut2b", per={("P", 1): 1.045})
        self.assertIn("decode 1/2/4 1 gain(s) / 0 loss(es)", f.text())

    def test_u1_digest_differences_are_listed(self):
        f = self.fx().set("ut2b", digest="b")
        text = f.text()
        self.assertIn("digest keys differing between the ut2 group and ut1: 37", text)
        self.assertIn("differs: ('chain', 1)", text)

    def test_u1_an_empty_digest_list_says_nothing_may_change_a_byte(self):
        text = self.fx().text()
        self.assertIn("digest keys differing between the ut2 group and ut1: 0 (nothing may change an output byte)", text)
        self.assertIn("digest keys reported on one side only: 0", text)


class U2(Base):
    def test_u2_passes_s92_arm_through_unchanged(self):
        f = self.fx().set(UT1, dec=0.98).set(SPLIT, dec=1.05)  # ut1 slower than the ut2 group, so a reference of ut1 gives different numbers
        f.write()
        lines, verdict = s101.u2(str(f.q))
        expected = s101.S92.arm([(str(f.q), SPLIT)], [(str(f.q), UT2[0]), (str(f.q), UT2[1])])[1]
        self.assertEqual(verdict, expected)
        self.assertTrue(verdict.startswith("CANDIDATE"), verdict)
        self.assertEqual(lines[-1], f"U2 DRAFT_SPLIT: {expected}")

    def test_u2_not_a_candidate_on_the_flat_rung(self):
        _, verdict = s101.u2(str(self.fx().write().q))
        self.assertTrue(verdict.startswith("NOT A CANDIDATE"), verdict)
        self.assertIn("no cell faster than the best reference boot", verdict)


class U3(Base):
    def test_u3_share_arithmetic(self):
        f = self.fx().set("ut2a", rate=75.5).set("ut2b", rate=75.5).set("ut2d", rate=70.0)
        text = f.text()
        self.assertIn("ut2 group mean 75.50 tok/s (boots 75.50 75.50, spread 0.00%), ut2d 70.00 tok/s, share +7.86%  CLEAR gain (DSCORES faster: beyond both 1.0% and the ut2 group's 0.00% spread)", text)

    def test_u3_clear_loss_when_dscores_is_slower_beyond_both_bounds(self):
        f = self.fx().set("ut2a", rate=70.0).set("ut2b", rate=70.0).set("ut2d", rate=75.5)
        text = f.text()
        self.assertIn("ut2 group mean 70.00 tok/s (boots 70.00 70.00, spread 0.00%), ut2d 75.50 tok/s, share -7.28%  CLEAR loss (DSCORES slower: beyond both 1.0% and the ut2 group's 0.00% spread)", text)

    def test_u3_share_blocked_by_the_ut2_spread(self):
        f = self.fx().set("ut2a", rate=74.0).set("ut2b", rate=80.0).set("ut2d", rate=76.0)
        text = f.text()
        self.assertIn("share +1.32%", text)
        self.assertIn("not CLEAR (needs more than 1.0% and more than the ut2 group's 8.11% spread, in either direction)", text)

    def test_u3_a_loss_blocked_by_the_ut2_spread_is_not_clear(self):
        f = self.fx().set("ut2a", rate=74.0).set("ut2b", rate=80.0).set("ut2d", rate=78.5)
        text = f.text()
        self.assertIn("share -1.91%", text)
        self.assertIn("not CLEAR (needs more than 1.0% and more than the ut2 group's 8.11% spread, in either direction)", text)

    def test_u3_share_below_one_percent_is_not_clear(self):
        f = self.fx().set("ut2a", rate=70.5).set("ut2b", rate=70.5).set("ut2d", rate=70.0)
        text = f.text()
        self.assertIn("share +0.71%", text)
        self.assertIn("not CLEAR (needs more than 1.0% and more than the ut2 group's 0.00% spread, in either direction)", text)

    def test_u3_a_loss_below_one_percent_is_not_clear(self):
        f = self.fx().set("ut2a", rate=70.5).set("ut2b", rate=70.5).set("ut2d", rate=70.9)
        text = f.text()
        self.assertIn("share -0.56%", text)
        self.assertIn("not CLEAR (needs more than 1.0% and more than the ut2 group's 0.00% spread, in either direction)", text)

    def test_u3_has_no_verdict_word(self):
        block = self.block(self.fx().text(), "== U3 DSCORES", "== U4")
        self.assertNotIn("CANDIDATE", block)


class U4(Base):
    def test_u4_prints_each_boot_and_the_group_lines(self):
        f = self.fx().set("ut1", rate=70.0).set("ut2a", rate=72.0).set("ut2b", rate=74.0).set("ut2s", rate=75.0).set("ut2d", rate=71.0)
        text = f.text()
        self.assertIn("ut2a   7 resumed turns, mean   72.00 tok/s (min 72.00, max 72.00), context 114000 to 114000 rows", text)
        self.assertIn("ut2s   7 resumed turns, mean   75.00 tok/s", text)
        self.assertIn("group ut2: 2 boot(s), mean of means 73.00 tok/s, spread between boots 2.78%", text)
        self.assertIn("group ut1: 1 boot(s), mean of means 70.00 tok/s, one boot, no spread", text)

    def test_u4_a_boot_with_no_counted_turn_says_so(self):
        text = self.fx().set("ut2d", cached=0).text()
        self.assertIn("ut2d   no counted chain turn found", text)


class U5(Base):
    def test_u5_percentages(self):
        f = self.fx().set("ut1", budget=1000).set("ut2a", budget=1000).set("ut2b", budget=2000).set("ut2s", budget=1000).set("ut2d", budget=500)
        text = f.text()
        self.assertIn("ut1    1000 bytes (the reference)", text)
        self.assertIn("ut2a   1000 bytes (+0.00% against ut1 1000)", text)
        self.assertIn("ut2b   2000 bytes (+100.00% against ut1 1000)", text)
        self.assertIn("ut2d   500 bytes (-50.00% against ut1 1000)", text)

    def test_u5_a_boot_without_a_facts_row_says_so(self):
        text = self.fx().set("ut2d", budget=None).text()
        self.assertIn("ut2d   no facts row with prompt_cache_budget_bytes", text)


class Final(Base):
    def test_the_final_line_states_u0_u2_and_the_clear_counts(self):
        lines, v = self.fx().report()
        self.assertEqual(v["U2"], "NOT A CANDIDATE")
        self.assertEqual(lines[-1], "U-VERDICT: U0 QUALIFIED; U2 NOT A CANDIDATE; U1 CLEAR: prompt cells 0 gain(s) / 0 loss(es), decode 1/2/4 0 gain(s) / 0 loss(es), decode 6/8 0 gain(s) / 0 loss(es)")

    def test_a_failed_proof_final_line_is_void_and_carries_no_u2_word(self):
        f = self.fx()
        f.drafter[SPLIT] = DRAFTER_STOCK
        f.set(SPLIT, dec=1.05)  # U2 would read CANDIDATE on its own, and must not reach the summary
        lines, v = f.report()
        self.assertEqual(v["U0"], "ARM DID NOT TAKE EFFECT")
        self.assertIn("U2 DRAFT_SPLIT: CANDIDATE", "\n".join(lines))
        self.assert_void(lines)

    def test_the_report_never_says_adopt(self):
        self.assertNotIn("adopt", self.fx().text().lower())
        f = self.fx()
        f.drafter["ut2s"] = DRAFTER_STOCK
        self.assertNotIn("adopt", f.text().lower())


class Cli(Base):
    def test_the_default_directory_and_dir_alias(self):
        r = subprocess.run([sys.executable, str(SCORER), "--help"], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0)
        self.assertIn("docs/audit-2026-11-12/queue-rows/queue92/f92-c", "".join(r.stdout.split()))
        self.assertIn("--dir", r.stdout)
        rc, out = self.run_main("--dir", str(ROOT / "work" / "score101-absent"))
        self.assertEqual(rc, 0)
        self.assertIn("U-VERDICT: NOT DECIDED: no rows for ut1, ut2a, ut2b, ut2s, ut2d", out)

    def test_an_absent_directory_is_not_decided(self):
        rc, out = self.run_main("--q101", str(ROOT / "work" / "score101-absent"))
        self.assertEqual(rc, 0)
        self.assertIn("U0: NOT DECIDED: no rows for ut1, ut2a, ut2b, ut2s, ut2d", out)
        self.assertIn("U-VERDICT: NOT DECIDED: no rows for ut1, ut2a, ut2b, ut2s, ut2d", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
