#!/usr/bin/env python3
"""test_score93.py: scripts/queue-scores/score93.py's keep-seqs and no-copy receipt rules on fixture reports shaped like tools/bench_concurrent.py's output.

Run from the top-level shell: python scripts/tests/test_score93.py
"""
import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("score93", ROOT / "scripts/queue-scores/score93.py")
s93 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s93)

PROMPTS = ("code", "chat")
TEMPS = (0.0, 1.0)
BASE = {"code": 62.0, "chat": 50.0}


def report(streams, scale=1.0, per_cell=None, digest="a", digest_by_cell=None, alone_bad=False, serial_bad=False, none_sha=False, prompts=PROMPTS):
    cells = []
    for prompt in prompts:
        for temp in TEMPS:
            for n in streams:
                s = scale * (per_cell or {}).get((prompt, temp, n), 1.0)
                tag = (digest_by_cell or {}).get((prompt, temp, n), digest)
                shas = [f"{tag}-{prompt}-{temp}-{n}-{i}" if temp else f"{tag}-{prompt}-{n}" for i in range(n if temp else 1)]
                cells.append({"prompt": prompt, "temperature": temp, "streams": n, "aggregate_tps": BASE[prompt] * n ** 0.5 * s,
                              "alone": {"equal": 3 * n - (1 if alone_bad else 0), "unequal": 1 if alone_bad else 0, "failed": 0},
                              "serial": {"equal": 1 - (1 if serial_bad else 0), "unequal": 1 if serial_bad else 0, "failed": 0},
                              "reps": [{"evidence": [{"token_sha256": None if none_sha else sha} for sha in shas]} for _ in range(3)]})
    return {"label": "x", "cells": cells}


class Fixture:
    def __init__(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="score93-", dir=ROOT / "work"))

    def put(self, label, streams, **kw):
        d = self.root / label
        d.mkdir(parents=True, exist_ok=True)
        (d / "concurrent.json").write_text(json.dumps(report(streams, **kw)), encoding="utf-8")

    def keep(self, over=None, skip=()):
        """Both contexts, every boot at scale 1 unless `over` maps a label to report kwargs."""
        over = over or {}
        for prefix in ("ks262", "ks1m"):
            for x in ("A1", "A2", "B1a", "B1b") + (("B0",) if prefix == "ks1m" else ()):
                label = f"{prefix}-{x}"
                if label not in skip:
                    self.put(label, (1, 4), **over.get(label, {}))
        return self

    def nocopy(self, over=None, skip=()):
        over = over or {}
        for x in ("A1", "A2", "B1a", "B1b", "B0"):
            label = f"nc-{x}"
            if label not in skip:
                self.put(label, (1, 2, 4), **over.get(label, {}))
        return self

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Keep(unittest.TestCase):
    def fx(self, **kw):
        f = Fixture().keep(**kw)
        self.addCleanup(f.close)
        return f

    def verdict(self, f):
        return s93.keep(str(f.root))[1]

    GAIN4 = {("code", 0.0, 4): 1.05, ("chat", 0.0, 4): 1.05}

    def test_holds_when_the_four_stream_cells_gain_at_1m_and_nothing_else_moves(self):
        over = {f"ks1m-B1{x}": {"per_cell": self.GAIN4} for x in "ab"}
        self.assertEqual(self.verdict(self.fx(over=over)), "KEEP_SEQS: RECEIPT HOLDS at both contexts")

    def test_a_missing_boot_is_not_decided_and_named(self):
        v = self.verdict(self.fx(skip=("ks1m-B0",)))
        self.assertTrue(v.startswith("KEEP_SEQS: NOT DECIDED"), v)
        self.assertIn("ks1m-B0", v)

    def test_no_gain_at_1m_fails(self):
        v = self.verdict(self.fx())
        self.assertTrue(v.startswith("KEEP_SEQS: RECEIPT FAILS"), v)
        self.assertIn("not above A on both boots", v)

    def test_a_gain_under_the_limit_fails(self):
        over = {f"ks1m-B1{x}": {"per_cell": {("code", 0.0, 4): 1.005, ("chat", 0.0, 4): 1.005}} for x in "ab"}
        self.assertIn("not above A on both boots", self.verdict(self.fx(over=over)))

    def test_one_b1_boot_below_an_a_boot_fails_even_when_the_mean_gains(self):
        over = {"ks1m-B1a": {"per_cell": {("code", 0.0, 4): 1.15, ("chat", 0.0, 4): 1.15}}, "ks1m-B1b": {"per_cell": {("code", 0.0, 4): 0.995, ("chat", 0.0, 4): 0.995}}}
        self.assertIn("not above A on both boots", self.verdict(self.fx(over=over)))

    def test_a_slow_one_stream_cell_at_262k_fails_and_is_named(self):
        over = {f"ks1m-B1{x}": {"per_cell": self.GAIN4} for x in "ab"}
        over.update({f"ks262-B1{x}": {"per_cell": {("code", 0.0, 1): 0.985}} for x in "ab"})
        v = self.verdict(self.fx(over=over))
        self.assertIn("code at 0 with 1 stream(s) is 1.50% slower in B1", v)

    def test_a_gain_is_not_required_at_262k(self):
        over = {f"ks1m-B1{x}": {"per_cell": self.GAIN4} for x in "ab"}
        self.assertEqual(self.verdict(self.fx(over=over)), "KEEP_SEQS: RECEIPT HOLDS at both contexts")

    def test_the_default_path_must_match_main(self):
        over = {f"ks1m-B1{x}": {"per_cell": self.GAIN4} for x in "ab"}
        over["ks1m-B0"] = {"scale": 1.02}
        v = self.verdict(self.fx(over=over))
        self.assertIn("B0 differs from A by +2.00%", v)

    def test_a_different_reply_digest_in_any_boot_fails(self):
        over = {f"ks1m-B1{x}": {"per_cell": self.GAIN4} for x in "ab"}
        over["ks1m-B1b"]["digest_by_cell"] = {("code", 0.0, 4): "zzz"}
        v = self.verdict(self.fx(over=over))
        self.assertIn("more than one reply digest", v)

    def test_a_sampled_digest_difference_also_fails(self):
        over = {f"ks1m-B1{x}": {"per_cell": self.GAIN4} for x in "ab"}
        over["ks262-B1a"] = {"digest_by_cell": {("chat", 1.0, 4): "zzz"}}
        self.assertIn("more than one reply digest", self.verdict(self.fx(over=over)))

    def test_the_tools_own_alone_check_must_be_clean(self):
        over = {f"ks1m-B1{x}": {"per_cell": self.GAIN4} for x in "ab"}
        over["ks1m-A1"] = {"alone_bad": True}
        self.assertIn("own alone or serial check", self.verdict(self.fx(over=over)))

    def test_the_serial_check_must_be_clean_too(self):
        over = {f"ks1m-B1{x}": {"per_cell": self.GAIN4} for x in "ab"}
        over["ks262-A2"] = {"serial_bad": True}
        self.assertIn("own alone or serial check", self.verdict(self.fx(over=over)))

    def test_a_missing_reply_digest_is_not_clean(self):
        over = {f"ks1m-B1{x}": {"per_cell": self.GAIN4} for x in "ab"}
        over["ks1m-A1"] = {"none_sha": True}
        self.assertIn("own alone or serial check", self.verdict(self.fx(over=over)))

    def test_sampled_cells_do_not_enter_the_rate_rules(self):
        over = {f"ks1m-B1{x}": {"per_cell": {**self.GAIN4, ("code", 1.0, 4): 0.90}} for x in "ab"}
        self.assertEqual(self.verdict(self.fx(over=over)), "KEEP_SEQS: RECEIPT HOLDS at both contexts")


class NoCopy(unittest.TestCase):
    def fx(self, **kw):
        f = Fixture().nocopy(**kw)
        self.addCleanup(f.close)
        return f

    def verdict(self, f):
        return s93.nocopy(str(f.root))[1]

    CODE1 = {("code", 0.0, 1): 1.10}

    def over(self, **extra):
        o = {f"nc-B1{x}": {"per_cell": self.CODE1} for x in "ab"}
        o.update(extra)
        return o

    def test_holds_when_code_at_one_stream_gains_and_nothing_else_moves(self):
        self.assertEqual(self.verdict(self.fx(over=self.over())), "NO_COPY: RECEIPT HOLDS")

    def test_a_missing_group_is_not_decided(self):
        v = self.verdict(self.fx(over=self.over(), skip=("nc-B0",)))
        self.assertTrue(v.startswith("NO_COPY: NOT DECIDED"), v)
        self.assertIn("nc-B0", v)

    def test_no_gain_on_the_code_cell_fails(self):
        v = self.verdict(self.fx())
        self.assertIn("B1 is not above A and B0 on every boot", v)

    def test_a_missing_code_cell_is_a_failure_not_a_pass(self):
        f = Fixture()
        self.addCleanup(f.close)
        for x in ("A1", "A2", "B1a", "B1b", "B0"):
            f.put(f"nc-{x}", (1, 2, 4), prompts=("chat",))
        v = self.verdict(f)
        self.assertTrue(v.startswith("NO_COPY: RECEIPT FAILS"), v)
        self.assertIn("no code at 0 with 1 stream(s) cell in every group", v)

    def test_the_gain_must_also_beat_the_default_path_boot(self):
        over = {"nc-B1a": {"per_cell": {("code", 0.0, 1): 1.012}}, "nc-B1b": {"per_cell": {("code", 0.0, 1): 1.0085}}, "nc-B0": {"per_cell": {("code", 0.0, 1): 1.009}}}
        self.assertIn("B1 is not above A and B0 on every boot", self.verdict(self.fx(over=over)))

    def test_one_b1_boot_below_b0_fails_the_gain(self):
        over = self.over()
        over["nc-B1b"] = {"per_cell": {("code", 0.0, 1): 0.99}}
        self.assertIn("B1 is not above A and B0 on every boot", self.verdict(self.fx(over=over)))

    def test_a_cell_slower_than_one_percent_fails_and_is_named(self):
        over = self.over()
        for x in "ab":
            over[f"nc-B1{x}"] = {"per_cell": {**self.CODE1, ("chat", 0.0, 2): 0.98}}
        self.assertIn("chat at 0 with 2 stream(s) is 2.00% slower in B1", self.verdict(self.fx(over=over)))

    def test_the_default_path_must_match_main_on_every_cell(self):
        over = self.over(**{"nc-B0": {"per_cell": {("chat", 0.0, 4): 1.03}}})
        self.assertIn("B0 differs from A by +3.00%", self.verdict(self.fx(over=over)))

    def test_a_sampled_reply_difference_fails(self):
        over = self.over()
        over["nc-B1a"]["digest_by_cell"] = {("code", 1.0, 2): "zzz"}
        self.assertIn("more than one reply digest", self.verdict(self.fx(over=over)))

    def test_a_greedy_reply_difference_in_b0_fails(self):
        over = self.over(**{"nc-B0": {"digest_by_cell": {("chat", 0.0, 1): "zzz"}}})
        self.assertIn("more than one reply digest", self.verdict(self.fx(over=over)))

    def test_the_tools_own_checks_must_be_clean(self):
        over = self.over(**{"nc-A2": {"alone_bad": True}})
        self.assertIn("own alone or serial check", self.verdict(self.fx(over=over)))

    def test_cells_at_other_stream_counts_are_not_rate_checked(self):
        f = Fixture()
        self.addCleanup(f.close)
        for x in ("A1", "A2", "B1a", "B1b", "B0"):
            streams = (1, 2, 4, 8)
            kw = {"per_cell": self.CODE1} if x.startswith("B1") else {}
            if x.startswith("B1"):
                kw["per_cell"] = {**self.CODE1, ("code", 0.0, 8): 0.5}
            f.put(f"nc-{x}", streams, **kw)
        self.assertEqual(self.verdict(f), "NO_COPY: RECEIPT HOLDS")


if __name__ == "__main__":
    unittest.main(verbosity=1)
