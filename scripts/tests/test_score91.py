#!/usr/bin/env python3
"""test_score91.py: scripts/queue-scores/score91.py's sync rule on fixture row directories laid out as the queues write them.

Run from the top-level shell: python scripts/tests/test_score91.py
"""
import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("score91", ROOT / "scripts/queue-scores/score91.py")
s91 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s91)

COLD = {8000: 3600.0, 32000: 13400.0, 120000: 51000.0}
TURNS = [47800.0, 840.0, 830.0, 810.0, 805.0, 800.0, 795.0, 800.0]
DEC = {"P": 80.0, "C": 112.0, "SP": 75.0, "SC": 100.0}


def put(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def write_boot(d, label, cold=1.0, warm=1.0, dec=1.0, digest="a", only=None, cold2=None):
    """One boot's rows: latencies scaled by `cold` and `warm`, throughputs by `dec`; every reply digest `digest`; `only` limits what is written."""
    d = pathlib.Path(d)
    if only in (None, "cold"):
        for size, ms in COLD.items():
            for rep in (1, 2):
                scale = cold2 if (rep == 2 and cold2 is not None) else cold
                put(d / "rows.jsonl", [{"tag": label, "case": "cold", "target_tokens": size, "rep": rep, "ttft_ms": ms * scale, "token_sha": f"{digest}{size}{rep}"}])
    if only in (None, "chain"):
        put(d / label / "chain.jsonl", [{"tag": "c74", "turn": t, "ttft_ms": ms * (warm if t > 1 else 1.0), "token_sha": f"{digest}t{t}"} for t, ms in enumerate(TURNS, 1)])
    if only in (None, "dec"):
        for kind, base in DEC.items():
            for n in s91.LEVELS:
                put(d / f"dec-{label}" / f"{kind}{n}.jsonl", [{"agg_tok_s": base * n ** 0.5 * dec, "sha": [f"{digest}{kind}{n}x", f"{digest}{kind}{n}y"]}] * 3)
        put(d / f"dec-{label}" / "pp.jsonl", [{"name": f"p{i}", "sha12": f"{digest}pp{i}"} for i in range(3)])


class Fixture:
    def __init__(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="score91-", dir=ROOT / "work"))
        self.new, self.old = self.root / "new", self.root / "old"

    def full(self, new_kw=None, old_kw=None, skip=()):
        for label in ("mn1", "mn2"):
            if label not in skip:
                write_boot(self.new, label, **(new_kw or {}))
        for label in ("P1", "P2"):
            write_boot(self.old, label, **(old_kw or {}))
        if "mo3" not in skip:
            write_boot(self.new, "mo3", **(old_kw or {}))
        return self

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Score91(unittest.TestCase):
    def fx(self, **kw):
        f = Fixture().full(**kw)
        self.addCleanup(f.close)
        return f

    def verdict(self, f):
        return s91.score(str(f.new), str(f.old))[1]

    def test_equal_stacks_are_accepted(self):
        self.assertTrue(self.verdict(self.fx()).startswith("SYNC: ACCEPTED"))

    def test_a_cell_over_the_limit_is_named_and_one_under_it_is_not(self):
        f = self.fx(new_kw={"dec": 0.985})  # throughput 1.5% down: every decode cell slower
        v = self.verdict(f)
        self.assertTrue(v.startswith("SYNC: 20 cell(s) more than 1% slower (0 inside the old boots' range)"), v)
        self.assertIn("greedy prose at 1 clients", v)
        g = self.fx(new_kw={"dec": 0.991})
        self.assertTrue(self.verdict(g).startswith("SYNC: ACCEPTED"), self.verdict(g))

    def test_latency_up_is_slower_and_latency_down_is_not(self):
        v = self.verdict(self.fx(new_kw={"warm": 1.015}))
        self.assertIn("conversation turns 2+ first token", v)
        self.assertTrue(self.verdict(self.fx(new_kw={"warm": 0.985})).startswith("SYNC: ACCEPTED"))
        w = self.verdict(self.fx(new_kw={"cold": 1.02}))
        self.assertIn("cold 8k first token", w)
        self.assertIn("cold 120k first token", w)

    def test_throughput_up_is_not_slower(self):
        self.assertTrue(self.verdict(self.fx(new_kw={"dec": 1.05})).startswith("SYNC: ACCEPTED"))

    def test_a_different_reply_digest_stops_the_acceptance(self):
        f = self.fx()
        put(f.new / "rows.jsonl", [{"tag": "mn1", "case": "cold", "target_tokens": 8000, "rep": 1, "ttft_ms": 3600.0, "token_sha": "other"}])
        v = self.verdict(f)
        self.assertTrue(v.startswith("REPLIES DIFFER"), v)

    def test_a_different_decode_reply_set_or_prompt_digest_is_found(self):
        f = self.fx()
        put(f.new / "dec-mn2" / "P4.jsonl", [{"agg_tok_s": 160.0, "sha": ["zzz"]}])
        self.assertTrue(self.verdict(f).startswith("REPLIES DIFFER"))
        g = self.fx()
        put(g.new / "dec-mo3" / "pp.jsonl", [{"name": "p1", "sha12": "changed"}])
        self.assertTrue(self.verdict(g).startswith("REPLIES DIFFER"))

    def test_a_missing_boot_or_cell_is_not_decided(self):
        f = Fixture().full(skip=("mn2",))
        self.addCleanup(f.close)
        self.assertTrue(self.verdict(f).startswith("NOT DECIDED: no rows for mn2"))
        g = Fixture()
        self.addCleanup(g.close)
        for label in ("mn1", "mn2"):
            write_boot(g.new, label, only="cold")
        for label in ("P1", "P2"):
            write_boot(g.old, label)
        write_boot(g.new, "mo3")
        self.assertTrue(self.verdict(g).startswith("NOT DECIDED"), self.verdict(g))

    def test_the_old_group_is_all_three_boots(self):
        f = Fixture()
        self.addCleanup(f.close)
        for label in ("mn1", "mn2"):
            write_boot(f.new, label, warm=1.0)
        write_boot(f.old, "P1", warm=1.0)
        write_boot(f.old, "P2", warm=1.0)
        write_boot(f.new, "mo3", warm=0.97)  # one fast old boot: the old mean is 0.99, the new 1.0 is 1.01% slower
        self.assertIn("conversation turns 2+ first token", self.verdict(f))

    def test_a_loss_inside_the_old_boots_range_is_marked(self):
        f = Fixture()
        self.addCleanup(f.close)
        write_boot(f.old, "P1", warm=0.95)
        write_boot(f.old, "P2", warm=1.05)
        write_boot(f.new, "mo3", warm=1.0)
        for label in ("mn1", "mn2"):
            write_boot(f.new, label, warm=1.03)  # 3% over the mean of 0.95, 1.05 and 1.0? the mean is 1.0: over the limit, inside the 0.95 to 1.05 range
        lines, v = s91.score(str(f.new), str(f.old))
        self.assertTrue(v.startswith("SYNC: 1 cell(s) more than 1% slower (1 inside"), v)
        self.assertTrue(any("inside the old boots' range" in l for l in lines))

    def test_a_cold_cell_is_the_mean_of_a_boots_two_requests(self):
        f = Fixture()
        self.addCleanup(f.close)
        for label in ("mn1", "mn2"):
            write_boot(f.new, label, cold=1.0, cold2=1.03)  # the second request 3% slower: the boot's mean is 1.5% slower
        for label in ("P1", "P2"):
            write_boot(f.old, label)
        write_boot(f.new, "mo3")
        self.assertIn("cold 8k first token", self.verdict(f))

    def test_a_changed_first_turn_digest_alone_is_found(self):
        f = self.fx()
        path = f.new / "mn1" / "chain.jsonl"
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows[0]["token_sha"] = "first-turn-differs"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        lines, v = s91.score(str(f.new), str(f.old))
        self.assertTrue(v.startswith("REPLIES DIFFER at 1 key(s)"), v)
        self.assertTrue(any("('chain', 1)" in l for l in lines))

    def test_a_request_starts_arm_is_compared_with_dev_not_prod(self):
        f = self.fx()
        for label in ("md1", "md2", "mr1"):
            write_boot(f.new, label, digest="dev")
        text = "\n".join(s91.arms(str(f.new)))
        self.assertIn("mr1: reply digests equal to md's: True", text)
        self.assertIn("md1 md2: reply digests equal to mn's: False", text)

    def test_the_other_arms_never_change_the_verdict_and_are_reported(self):
        f = self.fx()
        for label, kw in (("md1", {"dec": 1.02}), ("md2", {"dec": 1.02}), ("mz1", {"dec": 0.9}), ("mps", {"dec": 0.8, "digest": "stock"}), ("mr1", {"warm": 0.9})):
            write_boot(f.new, label, **kw)
        self.assertTrue(self.verdict(f).startswith("SYNC: ACCEPTED"))
        text = "\n".join(s91.arms(str(f.new)))
        line = next(l for l in text.splitlines() if l.startswith("mz1 against mn: "))
        self.assertIn("greedy prose at 1 clients -10.00%", line)  # throughput times 0.9 is 10% fewer tokens a second: faster is negative
        md = next(l for l in text.splitlines() if l.startswith("md1 md2 against mn: "))
        self.assertIn("greedy prose at 1 clients +2.00%", md)  # throughput times 1.02: 2% faster is positive
        self.assertIn("mps: reply digests equal to mn's: False", text)
        self.assertIn("md1 md2: reply digests equal to mn's: True", text)
        self.assertIn("mr1 against md", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
