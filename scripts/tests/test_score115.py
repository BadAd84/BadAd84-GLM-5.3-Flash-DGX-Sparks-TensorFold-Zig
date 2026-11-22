"""test_score115.py - score115.py's rules on fixtures built in the queue's own row shape (dec-<label>/SC8.jsonl, agg_tok_s and a sha list a round).
Run: python scripts/tests/test_score115.py"""
import importlib.util
import json
import os
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCORE = os.environ.get("SCORE115", str(ROOT / "scripts/queue-scores/score115.py"))  # a copy under test, so mutants_score115.py can point here
spec = importlib.util.spec_from_file_location("score115", SCORE)
s114 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s114)
CTL = [f"c{i}" for i in range(1, 7)]
T = [f"t{i}" for i in range(1, 7)]
X = [f"x{i}" for i in range(1, 7)]


def build(dirp, ctl=None, arm=None, sha_override=None, missing=None):
    """Eighteen boots at 170 tok/s. `ctl` / `arm` = {label: agg} move a whole boot (three rounds at that value); `sha_override` = (label, [sha...]);
    `missing` = label whose file is left out."""
    ctl = ctl or {}
    arm = arm or {}
    for label in CTL + T + X:
        if label == missing:
            continue
        d = pathlib.Path(dirp) / f"dec-{label}"
        d.mkdir(parents=True, exist_ok=True)
        v = ctl.get(label, arm.get(label, 170.0))
        sha = ["aa"]
        if sha_override and sha_override[0] == label:
            sha = sha_override[1]
        d.joinpath("SC8.jsonl").write_text(
            "".join(json.dumps({"tag": f"{label}-SC8", "round": k, "agg_tok_s": v, "sha": sha}) + "\n" for k in range(3)), encoding="utf-8")


class Rules(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="score115-", dir=ROOT / "work")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_decide(self):
        return s114.decide(self.d)

    def test_both_arms_adopt_inside_the_limit(self):
        build(self.d, arm={**{l: 169.5 for l in T}, **{l: 169.0 for l in X}})  # T 0.3% slower, X 0.6% slower
        res = self.run_decide()
        self.assertEqual([res["arms"][a]["verdict"] for a in ("T", "X")], ["ADOPT", "ADOPT"])
        self.assertIn("ADOPTED", res["bundle"])
        self.assertEqual(res["rc"], 0)

    def test_a_cell_past_the_limit_holds_that_arm(self):
        build(self.d, arm={**{l: 170.0 for l in T}, **{l: 168.0 for l in X}})  # X 1.19% slower: inside a 2% mutant's limit, past the real one
        res = self.run_decide()
        self.assertEqual(res["arms"]["T"]["verdict"], "ADOPT")
        self.assertEqual(res["arms"]["X"]["verdict"], "HOLD")
        self.assertIn("HELD", res["bundle"])
        self.assertIn("X HOLD", res["bundle"])

    def test_the_limit_is_inclusive(self):
        build(self.d, arm={l: 168.3 for l in T})  # 170/168.3 -> exactly 1.0000% slower within the doubles' reach
        res = self.run_decide()
        self.assertAlmostEqual(res["arms"]["T"]["change"], 0.010, places=12)
        self.assertEqual(res["arms"]["T"]["verdict"], "ADOPT")  # exactly at the limit is not over it

    def test_a_noisy_control_prints_noise_and_no_verdict(self):
        build(self.d, ctl={"c1": 150.0, "c2": 190.0})  # spread (190-150)/mean ~ 23%
        res = self.run_decide()
        self.assertIsNotNone(res["noise"])
        self.assertGreater(res["noise"], 0.05)
        self.assertIn("NOT DECIDED: NOISE", res["bundle"])
        self.assertIn(f"{res['noise']:.2%}", res["bundle"])  # the figure is printed, not just the word
        self.assertEqual(sorted(res["arms"]), ["T", "X"])  # both arms' spreads survive the clause
        for arm in ("T", "X"):
            self.assertIsNone(res["arms"][arm]["verdict"])  # and neither carries a verdict
            self.assertGreaterEqual(res["arms"][arm]["spread"], 0.0)
        self.assertEqual(res["rc"], 0)

    def test_the_noise_clause_is_inclusive_at_five_percent(self):
        base = [170.0] * 6
        base[0], base[1] = 166.0, 174.0  # (174-166)/170 = 4.71%, inside the clause
        build(self.d, ctl=dict(zip(CTL, base)))
        res = self.run_decide()
        self.assertIsNone(res["noise"])
        self.assertTrue(res["arms"])

    def test_a_missing_boot_is_not_decided(self):
        build(self.d, missing="t4")
        res = self.run_decide()
        self.assertIn("t4", res["missing"])
        self.assertIn("NOT DECIDED", res["bundle"])
        self.assertEqual(res["rc"], 0)

    def test_a_different_digest_exits_one_and_dominates_the_verdict(self):
        build(self.d, sha_override=("x3", ["bb"]))
        res = self.run_decide()
        self.assertEqual(res["rc"], 1)
        self.assertTrue(res["differ"])
        self.assertIn("DIGESTS DIFFER", res["bundle"])
        self.assertEqual(res["arms"], {})

    def test_a_different_digest_dominates_noise(self):
        build(self.d, ctl={"c1": 150.0, "c2": 190.0}, sha_override=("t1", ["bb"]))  # noisy control AND a different reply
        res = self.run_decide()
        self.assertEqual(res["rc"], 1)
        self.assertIsNone(res["noise"])
        self.assertIn("DIGESTS DIFFER", res["bundle"])

    def test_the_arms_are_decided_independently(self):
        build(self.d, arm={**{l: 170.0 for l in T}, **{l: 160.0 for l in X}})  # X 5.9% slower, T level
        res = self.run_decide()
        self.assertEqual(res["arms"]["T"]["verdict"], "ADOPT")
        self.assertEqual(res["arms"]["X"]["verdict"], "HOLD")
        self.assertNotIn("ADOPTED", res["bundle"])

    def test_each_arm_spread_comes_from_its_own_boots(self):
        build(self.d, arm=dict(zip(T, (160.0, 165.0, 170.0, 175.0, 180.0, 170.0))))  # T spread (180-160)/170 ~ 11.8%
        res = self.run_decide()
        self.assertAlmostEqual(res["arms"]["T"]["spread"], (180.0 - 160.0) / 170.0, places=12)
        self.assertAlmostEqual(res["arms"]["X"]["spread"], 0.0, places=12)

    def test_the_control_spread_uses_the_control_boots_only(self):
        build(self.d, arm=dict(zip(T, (90.0, 95.0, 100.0, 105.0, 110.0, 115.0))))  # the arm's own wide spread must not trip the noise clause
        res = self.run_decide()
        self.assertIsNone(res["noise"])
        self.assertIn("HOLD", res["arms"]["T"]["verdict"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
