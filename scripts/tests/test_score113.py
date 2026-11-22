"""test_score113.py - score113.py's rules on fixtures built in the real row layout (rows.jsonl cold rows and dec-<label>/<KIND><LEVEL>.jsonl rows with
agg_tok_s and a sha list), read through score91's own boot(), so a fixture shape that differs from the queue's cannot pass here and fail there.
Run: python scripts/tests/test_score113.py"""
import importlib.util
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCORE = os.environ.get("SCORE113", str(ROOT / "scripts/queue-scores/score113.py"))  # a copy under test, so mutants_score113.py can point here
spec = importlib.util.spec_from_file_location("score113", SCORE)
s113 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s113)
CELLS = [("P", "greedy prose"), ("C", "greedy code"), ("SP", "sampled prose"), ("SC", "sampled code")]
CTL = [f"c{i}" for i in range(1, 9)]
T = [f"t{i}" for i in range(1, 5)]
X = [f"x{i}" for i in range(1, 5)]


def build(dirp, cold=None, dec=None, sha_override=None, missing=None, cold_sha=None):
    """Sixteen boots at 100 tok/s and a 1,000 ms first token. `cold` = {label: ttft_ms} (one value a size at both), `dec` = {(label, kind, level): agg},
    `sha_override` = (label, kind, level, [sha...]), `missing` = label whose every file is left out."""
    cold = cold or {}
    dec = dec or {}
    rows = []
    for label in CTL + T + X:
        if label == missing:
            continue
        d = pathlib.Path(dirp) / f"dec-{label}"
        d.mkdir(parents=True, exist_ok=True)
        for size in (8000, 32000):
            for rep in (0, 1):
                rows.append({"case": "cold", "tag": label, "target_tokens": size, "rep": rep,
                             "ttft_ms": cold.get(label, 1000.0), "token_sha": (cold_sha or {}).get(label, "cs"), "flags": []})
        for kind, _ in CELLS:
            for level in (4, 8):
                v = dec.get((label, kind, level), 100.0)
                sha = ["aa"]
                if sha_override and sha_override[:3] == (label, kind, level):
                    sha = sha_override[3]
                (d / f"{kind}{level}.jsonl").write_text(
                    json.dumps({"tag": f"{label}-{kind}{level}", "round": 0, "agg_tok_s": v, "sha": sha}) + "\n", encoding="utf-8")
    (pathlib.Path(dirp) / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


class Rules(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="score113-", dir=ROOT / "work")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_decide(self):
        return s113.decide(self.d)

    def test_both_arms_adopt_when_cold_is_over_the_bar_and_no_cell_is_slower(self):
        build(self.d, cold={l: 985.0 for l in T + X})  # 1.5% faster first token, decode exactly equal
        res = self.run_decide()
        self.assertEqual([res["arms"][a]["verdict"] for a in ("T", "X")], ["ADOPT", "ADOPT"])
        self.assertIn("ADOPTED", res["bundle"])
        self.assertEqual(res["rc"], 0)

    def test_one_cell_over_the_limit_holds_that_arm_and_the_bundle(self):
        build(self.d, cold={l: 985.0 for l in T + X}, dec={(l, "SP", 8): 98.0 for l in T})  # T's sampled prose 2% slower at eight clients, all four boots
        res = self.run_decide()
        self.assertEqual(res["arms"]["T"]["verdict"], "HOLD")
        self.assertEqual(res["arms"]["X"]["verdict"], "ADOPT")
        self.assertIn("HELD", res["bundle"])
        self.assertIn("T HOLD", res["bundle"])

    def test_a_cold_mean_that_is_not_positive_rejects(self):
        build(self.d, cold={l: 1010.0 for l in T + X})  # 1% slower first token
        res = self.run_decide()
        self.assertEqual([res["arms"][a]["verdict"] for a in ("T", "X")], ["REJECT", "REJECT"])
        self.assertIn("REJECTED", res["bundle"])

    def test_a_positive_cold_mean_under_the_bar_holds(self):
        build(self.d, cold={l: 995.0 for l in T + X})  # 0.5% faster, under the 1% bar
        res = self.run_decide()
        self.assertEqual(res["arms"]["T"]["verdict"], "HOLD")
        self.assertNotIn("ADOPTED", res["bundle"])

    def test_the_limit_is_inclusive(self):
        build(self.d, cold={l: 985.0 for l in T}, dec={(l, "P", 4): 99.0 for l in T})  # T's greedy prose exactly 1% slower, all four boots
        res = self.run_decide()
        self.assertEqual(res["arms"]["T"]["verdict"], "ADOPT")  # exactly at the limit is not over it

    def test_a_missing_boot_is_not_decided(self):
        build(self.d, missing="t3")
        res = self.run_decide()
        self.assertIn("t3", res["missing"])
        self.assertIn("NOT DECIDED", res["bundle"])
        self.assertEqual(res["rc"], 0)

    def test_a_different_digest_overrides_and_exits_one(self):
        build(self.d, cold={l: 985.0 for l in T + X}, sha_override=("x2", "C", 4, ["bb"]))
        res = self.run_decide()
        self.assertEqual(res["rc"], 1)
        self.assertTrue(res["digests"])
        self.assertIn("DIGESTS DIFFER", res["bundle"])
        self.assertEqual(res["arms"]["T"]["verdict"], "NOT DECIDED (digests)")

    def test_the_bundle_needs_both_arms(self):
        build(self.d, cold={l: 985.0 for l in T}, dec={(l, "SC", 8): 95.0 for l in X})  # X 5% slower on sampled code, X's cold not faster either
        res = self.run_decide()
        self.assertEqual(res["arms"]["T"]["verdict"], "ADOPT")
        self.assertEqual(res["arms"]["X"]["verdict"], "HOLD")
        self.assertNotIn("ADOPTED", res["bundle"])

    def test_a_cold_digest_difference_exits_one(self):
        build(self.d, cold={l: 985.0 for l in T + X}, cold_sha={"x1": "cs-other"} if False else None)
        # one boot's cold reply differs at 32k only: rewrite that boot's rows for the larger size
        p = pathlib.Path(self.d) / "rows.jsonl"
        rs = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        for r in rs:
            if r["tag"] == "x1" and r["target_tokens"] == 32000 and r["rep"] == 1:
                r["token_sha"] = "cs-other"
        p.write_text("".join(json.dumps(r) + "\n" for r in rs), encoding="utf-8")
        res = self.run_decide()
        self.assertEqual(res["rc"], 1)
        self.assertTrue(any(c[0] == "cold" for c, _ in res["digests"]))

    def test_every_cell_is_read_at_both_levels(self):
        build(self.d)
        res = self.run_decide()
        cells = set(res["arms"]["T"]["changes"])
        for kind, _ in CELLS:
            self.assertIn(("dec", kind, 4), cells)
            self.assertIn(("dec", kind, 8), cells)
        self.assertIn(("cold", 8000), cells)
        self.assertIn(("cold", 32000), cells)


if __name__ == "__main__":
    unittest.main(verbosity=2)
