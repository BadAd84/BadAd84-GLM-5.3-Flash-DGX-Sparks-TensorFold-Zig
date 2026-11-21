#!/usr/bin/env python3
"""test_score102.py: scripts/queue-scores/score102.py's five clauses on fixture row trees laid out as queue91 writes them.

Run from the top-level shell: python scripts/tests/test_score102.py
SCORE102=<path> points the tests at a copy of the scorer (scripts/tests/mutants_score102.py runs them against each mutant that way).

The rows are written by test_score91.py's put(), COLD, TURNS and DEC - queue91's row shape, one owner - and the chain rows by its write_boot(); the cold rows and the decode
files are written here so one size or one (kind, level) cell can move on its own. Each unit's readback proof is written in the exact shape queue102.sh writes it.

Two boundaries are built exactly rather than bracketed where the arithmetic allows it: the L2 gain at +0.5% is 51000 / 1.005 as the arm's 120k first token (the ratio is 1.005 to
the last bit the format prints), and the L3 thresholds at -0.5% and -0.3% are 9 cells of 0.99 with 3 of 1.01 (mean -0.5000000000000004%) and 12 cells of 0.997 (mean
-0.3000000000000003%), each carried by the scorer's EPS so a limit is inclusive.
"""
import contextlib
import importlib.util
import io
import os
import pathlib
import re
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_OVER = os.environ.get("SCORE102")
SCORER = pathlib.Path(_OVER) if _OVER else ROOT / "scripts/queue-scores/score102.py"
_QUEUE = os.environ.get("QUEUE102")
QUEUE = pathlib.Path(_QUEUE) if _QUEUE else ROOT / "scripts/queues/queue102.sh"
s102 = load("score102", SCORER)
T91 = load("test_score91", ROOT / "scripts/tests/test_score91.py")  # its put(), COLD, TURNS and DEC: queue91's row shape, one owner
put = T91.put
IMAGE = "sha256:6f2a1c9e77b0"  # the one image id every unit's proof carries unless a test says otherwise
IMAGE2 = "sha256:0d4b8f31c2ae"


def wboot(d, label, cold=1.0, cold2=None, cold_per=None, warm=1.0, dec=1.0, per=None, digest="a", only=None, notcold=None):
    """One boot's rows in queue91's format: test_score91.write_boot's shape, plus a per-size cold scale, a per-(kind, level) decode scale and the NOTCOLD flag, so one cell
    can move on its own."""
    d = pathlib.Path(d)
    if only in (None, "cold"):
        for size, ms in T91.COLD.items():
            for rep in (1, 2):
                scale = (cold2 if rep == 2 and cold2 is not None else cold) * (cold_per or {}).get(size, 1.0)
                row = {"tag": label, "case": "cold", "target_tokens": size, "rep": rep, "ttft_ms": ms * scale, "token_sha": f"{digest}{size}{rep}"}
                if (size, rep) in (notcold or {}):
                    row.update({"ttft_ms": notcold[(size, rep)], "cached_tokens": 6144, "flags": ["NOTCOLD"]})
                put(d / "rows.jsonl", [row])
    if only in (None, "chain"):
        T91.write_boot(d, label, warm=warm, digest=digest, only="chain")
    if only in (None, "dec"):
        for kind, base in T91.DEC.items():
            for n in s102.LEVELS:
                scale = dec * (per or {}).get((kind, n), 1.0)
                put(d / f"dec-{label}" / f"{kind}{n}.jsonl", [{"agg_tok_s": base * n ** 0.5 * scale, "sha": [f"{digest}{kind}{n}x", f"{digest}{kind}{n}y"]}] * 3)
        put(d / f"dec-{label}" / "pp.jsonl", [{"name": f"p{i}", "sha12": f"{digest}pp{i}"} for i in range(3)])


def wproof(d, label, image=IMAGE, vars_by_rank=None, ranks=(0, 1, 2), rank_image=None):
    """One unit's readback proof exactly as queue102.sh writes it; `vars_by_rank` overrides one rank's three values, `rank_image` one rank's image id."""
    d = pathlib.Path(d)
    want = dict(s102.WANT[label[:2]])
    lines = []
    for r in ranks:
        v = dict(want)
        v.update((vars_by_rank or {}).get(r, {}))
        vals = [v.get(n, "unset") for n in s102.VARS]
        lines.append(f"rank{r} container=glm53-zig-r{r} image={(rank_image or {}).get(r, image)} " + " ".join(f"{n}={x}" for n, x in zip(s102.VARS, vals)))
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{label}-env.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


class Fixture:
    """queue102's row tree and the other queues' 120k boots: every unit at its default keyword, rewritten whole from scratch on demand. q99's directory is absent by default,
    because a run that finds a directory missing must say so."""

    def __init__(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="score102-", dir=ROOT / "work"))
        self.q102 = self.root / "q102"
        self.q91, self.q95, self.q99 = self.root / "q91", self.root / "q95", self.root / "q99"
        self.kw = {label: {} for label in s102.UNITS}
        self.pf = {label: {} for label in s102.UNITS}
        self.no_rows, self.no_proof, self.drops, self.other_off = set(), set(), set(), {"q99"}

    def set(self, label, **kw):
        self.kw[label].update(kw)
        return self

    def set_all(self, labels, **kw):
        for label in labels:
            self.set(label, **kw)
        return self

    def proof_set(self, label, **kw):
        self.pf[label].update(kw)
        return self

    def rows_off(self, *labels):
        self.no_rows.update(labels)
        return self

    def proof_off(self, *labels):
        self.no_proof.update(labels)
        return self

    def drop(self, label, rel):
        """Remove one file of one unit after its rows are written (a boot that measured no chain or no decode cell)."""
        self.drops.add((label, rel))
        return self

    def other_on(self, name):
        self.other_off.discard(name)
        return self

    def write(self):
        shutil.rmtree(self.root, ignore_errors=True)
        for label in s102.UNITS:
            if label not in self.no_rows:
                wboot(self.q102, label, **self.kw[label])
            if label not in self.no_proof:
                wproof(self.q102, label, **self.pf[label])
        for _, rel in self.drops:
            (self.q102 / rel).unlink()
        for name, labels in (("q91", ("mn1", "mn2")), ("q95", ("mn3",)), ("q99", ("ca1", "ca2"))):
            if name in self.other_off:
                continue
            for label in labels:
                wboot(getattr(self, name), label)
        return self

    def report(self):
        self.write()
        return s102.report(str(self.q102), str(self.q91), str(self.q95), str(self.q99))

    def lines(self):
        return self.report()[0]

    def text(self):
        return "\n".join(self.lines())

    def verdicts(self):
        return self.report()[1]["L4"]

    def clauses(self):
        return self.report()[1]

    def main_now(self):
        """(exit code, printed text) of score102.py's own main() over the tree as it stands, without rewriting it."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = s102.main(["--q102", str(self.q102), "--q91", str(self.q91), "--q95", str(self.q95), "--q99", str(self.q99)])
        return code, buf.getvalue()

    def run_main(self):
        """(exit code, printed text) of score102.py's own main(), which is the exit path the acceptance names."""
        self.write()
        return self.main_now()

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Base(unittest.TestCase):
    def fx(self):
        f = Fixture()
        self.addCleanup(f.close)
        return f

    def assertVerdicts(self, f, s_word, v_word):
        v = f.verdicts()
        self.assertEqual((v["S"], v["V"]), (s_word, v_word), f.text())


# ---------------------------------------------------------------- L0 qualification

class L0Qualification(Base):
    def test_l0_all_six_proofs_are_qualified(self):
        f = self.fx()
        c = f.clauses()
        self.assertTrue(c["L0"].startswith("L0 QUALIFIED: six proofs, one image id"), c["L0"])
        self.assertIn(IMAGE, c["L0"])
        self.assertVerdicts(f, "RETIRE", "RETIRE")

    def test_l0_a_missing_proof_voids_its_unit(self):
        f = self.fx().proof_off("lv1")
        c = f.clauses()
        self.assertEqual(c["L0"], "L0 VOID: lv1", c["L0"])
        self.assertIn("lv1: VOID: no readback proof (lv1-env.txt)", f.text())  # the reason, not just the outcome: a proof invented for a missing file would be caught by the image check and hide this one
        self.assertEqual(c["L1"]["V"], "NOT DECIDED")
        self.assertVerdicts(f, "RETIRE", "NOT DECIDED")

    def test_l0_a_rank_with_the_wrong_variable_voids_the_unit(self):
        f = self.fx().proof_set("lc1", vars_by_rank={1: {"TF_GLM_OVN_ABSORB_VEC": "1"}})
        c = f.clauses()
        self.assertEqual(c["L0"], "L0 VOID: lc1", c["L0"])
        self.assertIn("rank 1 carries TF_GLM_OVN_INDEX_SCHED=unset, TF_GLM_OVN_POOLS32=unset, TF_GLM_OVN_ABSORB_VEC=1 but the arm needs", f.text())
        self.assertVerdicts(f, "NOT DECIDED", "NOT DECIDED")

    def test_l0_one_rank_on_another_image_voids_the_unit(self):
        f = self.fx().proof_set("lv2", rank_image={2: IMAGE2})
        c = f.clauses()
        self.assertEqual(c["L0"], "L0 VOID: lv2", c["L0"])
        self.assertIn("the three ranks carry 2 image ids", f.text())
        self.assertVerdicts(f, "RETIRE", "NOT DECIDED")

    def test_l0_a_second_image_id_voids_the_only_unit_on_it(self):
        f = self.fx().proof_set("ls2", image=IMAGE2)
        c = f.clauses()
        self.assertEqual(c["L0"], "L0 VOID: ls2", c["L0"])
        self.assertIn(f"its proof's image {IMAGE2} is not the image the other units ran", f.text())
        self.assertVerdicts(f, "NOT DECIDED", "RETIRE")

    def test_l0_a_proof_without_three_ranks_is_void(self):
        f = self.fx().proof_set("lc2", ranks=(0, 1))
        c = f.clauses()
        self.assertEqual(c["L0"], "L0 VOID: lc2", c["L0"])
        self.assertIn("not 0, 1 and 2", f.text())


# ---------------------------------------------------------------- L1 digests

class L1Digests(Base):
    def test_l1_equal_digests_pass(self):
        f = self.fx()
        c = f.clauses()
        self.assertEqual((c["L1"]["S"], c["L1"]["V"]), ("EQUAL", "EQUAL"))
        self.assertVerdicts(f, "RETIRE", "RETIRE")

    def test_l1_a_different_reply_digest_fails_both_verdicts_and_exits_one(self):
        f = self.fx().write()
        put(f.q102 / "rows.jsonl", [{"tag": "lv1", "case": "cold", "target_tokens": 120000, "rep": 1, "ttft_ms": 51000.0, "token_sha": "zz"}])
        c = s102.report(str(f.q102), str(f.q91), str(f.q95), str(f.q99))
        self.assertEqual(c[1]["L1"]["V"], "DIFFERS")
        self.assertIn("differs: ('cold', 120000, 1)", "\n".join(c[0]))
        self.assertEqual(c[1]["L4"], {"S": "NOT DECIDED", "V": "NOT DECIDED"})
        self.assertTrue(c[2], "a L1 difference must fail the run")
        code, out = f.main_now()
        self.assertEqual(code, 1, out)
        self.assertIn("a L1 digest difference overrides both verdicts", out)

    def test_l1_a_key_missing_on_one_side_is_not_decided(self):
        f = self.fx().set("lv1", only="dec")
        c = f.clauses()
        self.assertEqual(c["L1"]["V"], "NOT DECIDED")
        self.assertIn("a report is missing (never a pass)", f.text())
        self.assertVerdicts(f, "RETIRE", "NOT DECIDED")


# ---------------------------------------------------------------- L2 long-prompt gain

class L2LongPromptGain(Base):
    def test_l2_gains_at_six_tenths_of_a_percent(self):
        f = self.fx().set_all(("lv1", "lv2"), cold=0.994)
        self.assertEqual(f.clauses()["L2"]["V"], "GAINS")
        self.assertIn("+0.60% faster", f.text())
        self.assertVerdicts(f, "RETIRE", "PROMOTION CANDIDATE, FIVE LEVELS NEXT")

    def test_l2_the_half_percent_is_inclusive(self):
        f = self.fx().set_all(("lv1", "lv2"), cold_per={120000: 50746.268656716418 / 51000.0})
        self.assertEqual(f.clauses()["L2"]["V"], "GAINS")
        self.assertIn("+0.50% faster", f.text())

    def test_l2_four_tenths_of_a_percent_is_not_a_gain(self):
        f = self.fx().set_all(("lv1", "lv2"), cold=0.996)
        self.assertEqual(f.clauses()["L2"]["V"], "NO GAIN")
        self.assertIn("+0.40% faster", f.text())
        self.assertVerdicts(f, "RETIRE", "RETIRE")

    def test_l2_one_boot_of_two_beating_the_controls_is_not_a_gain(self):
        f = self.fx().set("lv1", cold=0.984).set("lv2", cold=1.0005)
        self.assertEqual(f.clauses()["L2"]["V"], "NO GAIN")
        self.assertIn("NOT both of the arm's boots beat both control boots", f.text())
        self.assertIn("+0.78% faster", f.text())
        self.assertVerdicts(f, "RETIRE", "RETIRE")

    def test_l2_accounts_by_the_control_over_the_arm_ratio(self):
        f = self.fx().set_all(("lv1", "lv2"), cold=0.98)
        t = f.text()
        self.assertIn("+2.04% faster", t)  # 51,000 / 49,980 - 1
        self.assertNotIn("+2.00% faster", t)  # 1 - 49,980 / 51,000 would be this

    def test_l2_reads_the_120k_cell_only(self):
        f = self.fx().set_all(("ls1", "ls2"), cold_per={120000: 0.99})
        c = f.clauses()
        self.assertEqual(c["L2"]["S"], "GAINS")
        self.assertEqual(c["L2"]["V"], "NO GAIN")
        self.assertIn("cold 8k first token: control 3600.0 3600.0 | S 3600.0 3600.0 | +0.00% faster", f.text())
        self.assertVerdicts(f, "KEEP, SPLIT NEXT", "RETIRE")

    def test_l2_not_decided_when_a_boot_reports_no_conversation(self):
        f = self.fx().set("lv2", only="dec")
        self.assertEqual(f.clauses()["L2"]["V"], "NOT DECIDED")
        self.assertIn("cell(s) missing a boot's report", f.text())
        self.assertVerdicts(f, "RETIRE", "NOT DECIDED")


# ---------------------------------------------------------------- L3 decode cost

class L3DecodeCost(Base):
    BOUNDARY = {("P", 1): 0.99, ("P", 2): 0.99, ("P", 4): 0.99, ("C", 1): 0.99, ("C", 2): 0.99, ("C", 4): 1.01,
                ("SP", 1): 0.99, ("SP", 2): 0.99, ("SP", 4): 1.01, ("SC", 1): 0.99, ("SC", 2): 0.99, ("SC", 4): 1.01}

    def test_l3_carries_the_loss_at_the_boundary(self):
        f = self.fx().set_all(("lv1", "lv2"), per=self.BOUNDARY)
        self.assertEqual(f.clauses()["L3"]["V"], "CARRIES A LOSS")
        self.assertIn("mean -0.50% of 12 cells, 9 negative: CARRIES A LOSS", f.text())

    def test_l3_eight_negative_cells_do_not_carry(self):
        per = {("P", 1): 0.98, ("P", 2): 0.98, ("P", 4): 0.98, ("C", 1): 0.98, ("C", 2): 0.98, ("C", 4): 0.98,
               ("SP", 1): 0.98, ("SP", 2): 0.98, ("SP", 4): 1.003, ("SC", 1): 1.003, ("SC", 2): 1.003, ("SC", 4): 1.003}
        f = self.fx().set_all(("lv1", "lv2"), per=per)
        self.assertEqual(f.clauses()["L3"]["V"], "UNCLEAR")
        self.assertIn("8 negative: UNCLEAR", f.text())

    def test_l3_clean_at_the_minus_three_tenths_boundary(self):
        f = self.fx().set_all(("lv1", "lv2"), dec=0.997)
        self.assertEqual(f.clauses()["L3"]["V"], "CLEAN")
        self.assertIn("mean -0.30% of 12 cells, 12 negative: CLEAN", f.text())

    def test_l3_the_band_between_the_two_limits_is_unclear(self):
        per = {("P", 1): 0.99, ("P", 2): 0.99, ("P", 4): 0.99, ("C", 1): 0.99, ("C", 2): 0.99, ("C", 4): 0.99,
               ("SP", 1): 1.002, ("SP", 2): 1.002, ("SP", 4): 1.002, ("SC", 1): 1.002, ("SC", 2): 1.002, ("SC", 4): 1.002}
        f = self.fx().set_all(("lv1", "lv2"), per=per)
        self.assertEqual(f.clauses()["L3"]["V"], "UNCLEAR")
        self.assertIn("mean -0.40% of 12 cells, 6 negative: UNCLEAR", f.text())

    def test_l3_not_decided_when_a_boot_reports_no_decode_cell(self):
        f = self.fx().drop("lv2", "dec-lv2/P4.jsonl")
        self.assertEqual(f.clauses()["L3"]["V"], "NOT DECIDED")
        self.assertIn("decode cell(s) missing a boot's report", f.text())
        self.assertVerdicts(f, "RETIRE", "RETIRE")  # no gain retires the arm; the undecided decode is never read as a pass


# ---------------------------------------------------------------- L4 verdicts

class L4Verdicts(Base):
    def test_verdict_s_retires_without_a_gain(self):
        self.assertVerdicts(self.fx(), "RETIRE", "RETIRE")

    def test_verdict_v_retires_without_a_gain(self):
        f = self.fx().set_all(("ls1", "ls2"), cold=0.994)  # S gains, V does not: V's RETIRE is its own branch
        self.assertVerdicts(f, "KEEP, SPLIT NEXT", "RETIRE")

    def test_verdict_s_keeps_and_splits_next_with_a_gain(self):
        f = self.fx().set_all(("ls1", "ls2"), cold=0.994)
        self.assertVerdicts(f, "KEEP, SPLIT NEXT", "RETIRE")
        self.assertIn("S: KEEP, SPLIT NEXT (L2 GAINS)", f.text())

    def test_verdict_v_builds_the_prompt_only_gate_on_a_gain_and_a_loss(self):
        f = self.fx().set_all(("lv1", "lv2"), cold=0.99, per=L3DecodeCost.BOUNDARY)
        self.assertVerdicts(f, "RETIRE", "BUILD THE PROMPT-ONLY GATE")
        self.assertIn("V: BUILD THE PROMPT-ONLY GATE (L2 GAINS, L3 CARRIES A LOSS)", f.text())

    def test_verdict_v_is_a_promotion_candidate_on_a_gain_and_a_clean_decode(self):
        f = self.fx().set_all(("lv1", "lv2"), cold=0.994, dec=0.998)
        self.assertVerdicts(f, "RETIRE", "PROMOTION CANDIDATE, FIVE LEVELS NEXT")

    def test_verdict_v_is_not_decided_when_decode_is_unclear(self):
        per = {("P", 1): 0.99, ("P", 2): 0.99, ("P", 4): 0.99, ("C", 1): 0.99, ("C", 2): 0.99, ("C", 4): 0.99,
               ("SP", 1): 1.002, ("SP", 2): 1.002, ("SP", 4): 1.002, ("SC", 1): 1.002, ("SC", 2): 1.002, ("SC", 4): 1.002}
        f = self.fx().set_all(("lv1", "lv2"), cold=0.99, per=per)
        self.assertVerdicts(f, "RETIRE", "NOT DECIDED")
        self.assertIn("V: NOT DECIDED (L2 GAINS, L3 UNCLEAR)", f.text())

    def test_a_missing_boot_is_not_decided_for_every_verdict(self):
        f = self.fx().rows_off("lc2")
        self.assertIn("no rows for lc2", f.text())
        self.assertVerdicts(f, "NOT DECIDED", "NOT DECIDED")
        g = self.fx().rows_off("lv2")
        self.assertEqual(g.clauses()["L0"], "L0 QUALIFIED: six proofs, one image id (" + IMAGE + "), and each unit's three variables exactly as its XENV names them")
        self.assertVerdicts(g, "RETIRE", "NOT DECIDED")


# ---------------------------------------------------------------- inherited rules and information

class InheritedAndInfo(Base):
    def test_a_notcold_cold_row_is_left_out_of_the_cold_mean(self):
        f = self.fx().set("lc1", notcold={(120000, 2): 1000.0})
        t = f.text()
        self.assertIn("cold 120k first token: control 51000.0 51000.0", t)  # score91 drops the flagged rep, so the mean is the one cold request
        self.assertNotIn("26000", t)  # (51,000 + 1,000) / 2 would be this

    def test_info_prints_the_six_and_eight_client_cells(self):
        t = self.fx().text()
        self.assertIn("6 and 8 clients, S (ls1 ls2):", t)
        self.assertIn("6 and 8 clients, V (lv1 lv2):", t)
        self.assertIn("greedy prose at 6 clients", t)
        self.assertIn("sampled code at 8 clients", t)

    def test_the_six_and_eight_cells_never_change_a_verdict(self):
        base = self.fx()
        per = {("P", 6): 0.5, ("P", 8): 1.5, ("C", 6): 0.5, ("C", 8): 1.5, ("SP", 6): 0.5, ("SP", 8): 1.5, ("SC", 6): 0.5, ("SC", 8): 1.5}
        moved = self.fx().set_all(("lv1", "lv2"), per=per)
        self.assertEqual(base.verdicts(), moved.verdicts())
        self.assertIn("greedy prose at 6 clients -50.00%", moved.text())  # printed, and it moved nothing

    def test_info_prints_the_other_boots_and_skips_an_absent_directory(self):
        t = self.fx().text()
        self.assertIn("mn1 51000.0 ms; mn2 51000.0 ms", t)
        self.assertIn("mn3 51000.0 ms", t)
        self.assertIn("skipped: DIR absent", t)
        u = self.fx().other_on("q99").text()
        self.assertIn("ca1 51000.0 ms; ca2 51000.0 ms", u)
        self.assertNotIn("skipped: DIR absent", u)

    def test_the_exit_code_is_zero_when_a_clause_is_not_decided(self):
        code, out = self.fx().rows_off("lv1").run_main()
        self.assertEqual(code, 0, out)
        self.assertIn("L4 VERDICT: S RETIRE; V NOT DECIDED", out)


class QueueAgreement(unittest.TestCase):
    """The queue script and this scorer must name the same six units and the same three variables: a typo in one is a VOID unit after a boot has been spent on it."""

    def test_the_queue_runs_the_same_units_with_the_same_variables(self):
        text = QUEUE.read_text(encoding="utf-8")
        units = [(m.group(1), m.group(2), m.group(3)) for m in (re.match(r'^unit (\w+) "\$IMG" (\w+) "(.*)"$', line) for line in text.splitlines()) if m]
        self.assertEqual([u[0] for u in units], list(s102.UNITS))
        for label, knobs, xenv in units:
            self.assertEqual(knobs, "prod", label)
            self.assertEqual(dict(re.findall(r"-e (TF_GLM_OVN_[A-Z0-9_]+)=(\S+)", xenv)), s102.WANT[label[:2]], f"{label}'s XENV {xenv!r}")
        self.assertIn("for name in " + " ".join(s102.VARS) + "; do", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
