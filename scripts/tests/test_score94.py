#!/usr/bin/env python3
"""test_score94.py: scripts/queue-scores/score94.py's head-skip and solo-to-start receipt rules on fixture reports shaped like queue94's boots.

Run from the top-level shell: python scripts/tests/test_score94.py
SCORE94=<path> points the tests at a copy of the scorer (scripts/tests/mutants_score94.py runs them against each mutant that way).
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
_OVER = os.environ.get("SCORE94")
SCORER = pathlib.Path(_OVER) if _OVER else ROOT / "scripts/queue-scores/score94.py"
spec = importlib.util.spec_from_file_location("score94", SCORER)
s94 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s94)

HEAD = "TF_GLM_HEAD_SKIP=1: the MTP head absorbs no prompt rows and keeps none in a kept state"
PROMPTS = ("code", "chat")
TEMPS = (0.0, 1.0)
BASE = {"code": 62.0, "chat": 50.0}
HK_LABELS = ("hk-A1", "hk-A2", "hk-B1a", "hk-B1b", "hk-B0")
ST_LABELS = ("st-A1", "st-A2", "st-B1a", "st-B1b", "st-B0", "st-B1x")


def report(streams, scale=1.0, per_cell=None, digest="a", digest_by_cell=None, alone_bad=False, serial_bad=False,
           none_sha=False, prompts=PROMPTS):
    """tools/bench_concurrent.py's report, as test_score93.py builds it: one cell a (prompt, temperature, streams)."""
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


HK_CACHE_MS = {"hk-A1": 100.0, "hk-A2": 100.4, "hk-B1a": 97.0, "hk-B1b": 97.4, "hk-B0": 100.2}
ST_COLD_MS = {"st-A1": {8000: 3647, 32000: 13640, 120000: 50990}, "st-A2": {8000: 3650, 32000: 13650, 120000: 51010},
              "st-B1a": {8000: 3496, 32000: 13472, 120000: 51000}, "st-B1b": {8000: 3500, 32000: 13480, 120000: 51010},
              "st-B0": {8000: 3649, 32000: 13645, 120000: 51000}, "st-B1x": {8000: 3651, 32000: 13655, 120000: 51005}}
ST_C3K_MS = {"st-A1": 1653.8, "st-A2": 1654.2, "st-B1a": 1475.9, "st-B1b": 1476.5, "st-B0": 1654.0, "st-B1x": 1655.0}
ST_C3K_T2 = {"st-A1": 1681, "st-A2": 1682, "st-B1a": 1684, "st-B1b": 1686, "st-B0": 1682, "st-B1x": 1683}
ST_C74_MS = {"st-A1": 811.0, "st-A2": 811.7, "st-B1a": 812.0, "st-B1b": 810.3, "st-B0": 811.5, "st-B1x": 811.2}


def c3k_default(label):
    return dict(zip(range(3, 11), [ST_C3K_MS[label]] * 8))


def c74_default(label):
    return dict(zip(range(2, 9), [ST_C74_MS[label]] * 7))


class Fixture:
    def __init__(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="score94-", dir=ROOT / "work"))

    def d(self, label):
        p = self.root / label
        p.mkdir(parents=True, exist_ok=True)
        return p

    def put_concurrent(self, label, streams=(1, 2, 4), **kw):
        (self.d(label) / "concurrent.json").write_text(json.dumps(report(streams, **kw)), encoding="utf-8")
        return self

    def put_cache(self, label, size, ttft_s):
        (self.d(label) / f"cache-{size}.json").write_text(
            json.dumps({"qualified": True, "rows": [{"ttft_s": ttft_s, "cache_state": "cold", "prompt_tokens": size}]}), encoding="utf-8")
        return self

    def put_metrics(self, label, states, bytes_):
        (self.d(label) / "metrics-after.txt").write_text(
            f"# gauges after the cells\ntensorfold:prompt_cache_states {states}\ntensorfold:prompt_cache_bytes {bytes_}\n", encoding="utf-8")
        return self

    def put_headlog(self, label, lines):
        (self.d(label) / "head-skip-line.txt").write_text("".join(HEAD + "\n" for _ in range(lines)), encoding="utf-8")
        return self

    def put_prof(self, label, mtp_ms, chunks=4):
        body = []
        for i in range(chunks):
            body.append(f"info: glm prompt chunk rank=0 slot=0 start={2048 * i} rows=2048 wall_ms=1700.0000 spans=40\n")
            body.append(f"info: glm prompt stage rank=0 slot=0 start={2048 * i} rows=2048 layer=null piece=null site=chunk stage=mtp stream=main ms={mtp_ms / chunks:.4f}\n")
        (self.d(label) / "prof.txt").write_text("".join(body), encoding="utf-8")
        return self

    def put_ours(self, label, cold=None, c3k=None, c3k_t2=None, c74=None, digest=None):
        """One boot's longctx rows; a section left out keeps the default boot's own rows, so an override changes one cell only."""
        cold = ST_COLD_MS[label] if cold is None else cold
        c3k = c3k_default(label) if c3k is None else c3k
        c3k_t2 = ST_C3K_T2[label] if c3k_t2 is None else c3k_t2
        c74 = c74_default(label) if c74 is None else c74
        lines = []
        for size, ms in cold.items():
            for rep in (1, 2):
                dg = (digest or {}).get(("cold", size, rep), f"tok-cold-{size}-{rep}")
                lines.append({"tag": label, "n": 4, "case": "cold", "rep": rep, "target_tokens": size, "ttft_ms": ms,
                              "token_sha": dg, "sha": f"txt-{dg}", "error": None})
        for tag, first, t2, turns in (("c3k", 47820, c3k_t2, c3k), ("c74", 47814, None, c74)):
            lines.append({"tag": tag, "n": 4, "case": "chain", "turn": 1, "ttft_ms": first, "token_sha": f"tok-{tag}-1", "sha": f"txt-{tag}-1"})
            if t2 is not None:
                lines.append({"tag": tag, "n": 4, "case": "chain", "turn": 2, "ttft_ms": t2, "token_sha": f"tok-{tag}-2", "sha": f"txt-{tag}-2"})
            for turn, ms in sorted(turns.items()):
                dg = (digest or {}).get(("chain", tag, turn), f"tok-{tag}-{turn}")
                lines.append({"tag": tag, "n": 4, "case": "chain", "turn": turn, "ttft_ms": ms, "token_sha": dg, "sha": f"txt-{dg}"})
        (self.d(label) / "ours-rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
        return self

    def put_check(self, rel, body):
        p = self.root / "checks" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return self

    def hk(self, skip=()):
        """A clean HOLDS fixture for the head-skip lever, every default boot."""
        for label in HK_LABELS:
            if label in skip:
                continue
            self.put_concurrent(label).put_headlog(label, 1 if label.startswith("hk-B1") else 0)
            for size in s94.HK_CACHE:
                self.put_cache(label, size, HK_CACHE_MS[label])
            self.put_metrics(label, 10, 900_000 if label.startswith("hk-B1") else 1_000_000)
        if "hk-P0" not in skip:
            self.put_prof("hk-P0", 200.0)
        if "hk-P1" not in skip:
            self.put_prof("hk-P1", 0.0)
        return self

    def st(self, skip=()):
        """A clean HOLDS fixture for the solo-to-start lever, every default boot."""
        for label in ST_LABELS:
            if label in skip:
                continue
            self.put_concurrent(label).put_ours(label)
        for rel in ("psts-solo-synth-off.log", "psts-solo-synth-on.log", "psts-solo-off/r0.log", "psts-solo-on/r0.log"):
            self.put_check(rel, "PASS solo prompt passes at TP=3: 10 prompts, ... (a solo step to a start: off), equal their twins\n")
        return self

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Base(unittest.TestCase):
    def fx(self):
        f = Fixture()
        self.addCleanup(f.close)
        return f

    def verdict(self, f, fn):
        return fn(str(f.root))[1]

    def hkv(self, f):
        return self.verdict(f, s94.head_skip)

    def stv(self, f):
        return self.verdict(f, s94.solo)

    def hk(self):
        return self.fx().hk()

    def st(self):
        return self.fx().st()


class HeadSkip(Base):
    def test_holds_when_every_clause_holds(self):
        v = self.hkv(self.hk())
        self.assertTrue(v.startswith("HEAD SKIP: HOLDS"), v)
        self.assertIn("8,192", v)
        self.assertIn("32,768", v)

    def test_each_missing_boot_is_not_decided_and_named(self):
        for label in HK_LABELS:
            v = self.hkv(self.fx().hk(skip=(label,)))
            self.assertTrue(v.startswith("HEAD SKIP: NOT DECIDED"), v)
            self.assertIn(label, v)

    def test_a_missing_cache_report_is_not_decided(self):
        f = self.hk()
        (f.root / "hk-B1b" / "cache-32768.json").unlink()
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: NOT DECIDED"), v)
        self.assertIn("hk-B1b", v)

    def test_a_missing_metrics_report_is_not_decided(self):
        f = self.hk()
        (f.root / "hk-A2" / "metrics-after.txt").unlink()
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: NOT DECIDED"), v)
        self.assertIn("hk-A2", v)

    def test_a_missing_boot_log_is_not_decided(self):
        f = self.hk()
        (f.root / "hk-B0" / "head-skip-line.txt").unlink()
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: NOT DECIDED"), v)
        self.assertIn("hk-B0", v)

    def test_one_differing_reply_digest_in_one_cell_fails(self):
        f = self.hk()
        f.put_concurrent("hk-B1b", digest_by_cell={("code", 0.0, 1): "zzz"})
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: FAILS"), v)
        self.assertIn("H1:", v)
        self.assertIn("more than one reply digest", v)

    def test_the_tools_own_alone_check_must_be_clean(self):
        f = self.hk()
        f.put_concurrent("hk-A1", alone_bad=True)
        v = self.hkv(f)
        self.assertIn("H1:", v)
        self.assertIn("own alone or serial check", v)

    def test_a_switch_line_on_the_default_boot_fails(self):
        f = self.hk()
        f.put_headlog("hk-B0", 1)
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: FAILS"), v)
        self.assertIn("H2:", v)

    def test_a_b1_boot_without_the_switch_line_fails(self):
        f = self.hk()
        f.put_headlog("hk-B1a", 0)
        v = self.hkv(f)
        self.assertIn("H2:", v)
        self.assertIn("did not take the skip", v)

    def test_two_switch_lines_fail(self):
        f = self.hk()
        f.put_headlog("hk-B1b", 2)
        self.assertIn("logged the line 2 times", self.hkv(f))

    def test_a_slower_decode_cell_fails(self):
        f = self.hk()
        f.put_concurrent("hk-B1a", per_cell={("chat", 0.0, 2): 0.98})
        f.put_concurrent("hk-B1b", per_cell={("chat", 0.0, 2): 0.98})
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: FAILS"), v)
        self.assertIn("H3: chat at 0 with 2 stream(s)", v)
        self.assertIn("slower in B1", v)

    def test_a_slower_sampled_decode_cell_fails_too(self):
        f = self.hk()
        for label in ("hk-B1a", "hk-B1b"):
            f.put_concurrent(label, per_cell={("code", 1.0, 4): 0.97})
        v = self.hkv(f)
        self.assertIn("H3: code at 1 with 4 stream(s)", v)
        self.assertIn("slower in B1", v)

    def test_b0_off_the_default_path_on_decode_fails(self):
        f = self.hk()
        f.put_concurrent("hk-B0", scale=1.015)
        v = self.hkv(f)
        self.assertIn("H3:", v)
        self.assertIn("B0 differs from A by +1.50%", v)

    def test_a_slower_cold_first_token_fails(self):
        f = self.hk()
        for label in ("hk-B1a", "hk-B1b"):
            f.put_cache(label, 32768, 102.0)
        v = self.hkv(f)
        self.assertIn("H4:", v)
        self.assertIn("at 32768", v)
        self.assertIn("slower in B1", v)

    def test_b0_cold_one_and_a_half_percent_off_holds(self):
        f = self.hk()
        for size in s94.HK_CACHE:
            f.put_cache("hk-B0", size, 101.5)
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: HOLDS"), v)

    def test_b0_cold_over_two_percent_off_fails(self):
        f = self.hk()
        for size in s94.HK_CACHE:
            f.put_cache("hk-B0", size, 102.5)
        v = self.hkv(f)
        self.assertIn("H4:", v)
        self.assertIn("B0's cold first token at 65536 differs from A by", v)

    def test_a_kept_state_not_strictly_smaller_fails(self):
        f = self.hk()
        f.put_metrics("hk-B1a", 10, 1_000_000)
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: FAILS"), v)
        self.assertIn("H5:", v)
        self.assertIn("not strictly smaller", v)

    def test_zero_kept_states_is_not_decided(self):
        f = self.hk()
        f.put_metrics("hk-B1b", 0, 0)
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: NOT DECIDED"), v)
        self.assertIn("prompt_cache_states is 0", v)

    def test_b0_kept_state_off_by_more_than_a_tenth_fails(self):
        f = self.hk()
        f.put_metrics("hk-B0", 10, 1_002_000)
        v = self.hkv(f)
        self.assertIn("H5:", v)
        self.assertIn("B0's bytes per kept state differ from A", v)

    def test_no_gain_is_neutral_and_prints_it(self):
        f = self.hk()
        for label in ("hk-B1a", "hk-B1b"):
            for size in s94.HK_CACHE:
                f.put_cache(label, size, 100.0)
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: NEUTRAL"), v)
        self.assertIn("cold 8192 B1", v)

    def test_a_gain_under_one_percent_is_neutral(self):
        f = self.hk()
        for label in ("hk-B1a", "hk-B1b"):
            for size in s94.HK_CACHE:
                f.put_cache(label, size, 99.6)
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: NEUTRAL"), v)

    def test_one_b1_boot_not_below_every_a_boot_is_neutral(self):
        f = self.hk()
        for size in s94.HK_CACHE:
            f.put_cache("hk-B1a", size, 96.0)
            f.put_cache("hk-B1b", size, 100.1)
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: NEUTRAL"), v)

    def test_a_gain_at_8k_only_is_neutral(self):
        f = self.hk()
        for label in ("hk-B1a", "hk-B1b"):
            f.put_cache(label, 32768, 100.0)
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: NEUTRAL"), v)

    def test_the_profile_pair_is_printed_and_does_not_decide(self):
        f = self.hk()
        f.put_prof("hk-P1", 150.0)
        lines, v, _ = s94.head_skip(str(f.root))
        self.assertTrue(v.startswith("HEAD SKIP: HOLDS"), v)
        self.assertTrue(any("H6 mtp section: hk-P0 200.00 ms" in line and "not below half" in line for line in lines), lines)

    def test_the_profile_pair_absent_still_holds(self):
        f = self.fx().hk(skip=("hk-P0", "hk-P1"))
        lines, v, _ = s94.head_skip(str(f.root))
        self.assertTrue(v.startswith("HEAD SKIP: HOLDS"), v)
        self.assertTrue(any("H6: not run" in line for line in lines), lines)

    def test_the_labels_cannot_be_swapped(self):
        f = self.fx()
        swap = {"hk-A1": "hk-B1a", "hk-A2": "hk-B1b", "hk-B1a": "hk-A1", "hk-B1b": "hk-A2", "hk-B0": "hk-B0"}
        for label in HK_LABELS:
            other = swap[label]  # the label the data lands on: the two groups exchanged
            f.put_concurrent(other).put_headlog(other, 1 if label.startswith("hk-B1") else 0)
            f.put_metrics(other, 10, 900_000 if label.startswith("hk-B1") else 1_000_000)
            for size in s94.HK_CACHE:
                f.put_cache(other, size, 97.0 if label.startswith("hk-B1") else 100.0)
        v = self.hkv(f)
        self.assertTrue(v.startswith("HEAD SKIP: FAILS"), v)


class SoloToStart(Base):
    def test_holds_when_every_clause_holds(self):
        v = self.stv(self.st())
        self.assertTrue(v.startswith("SOLO TO START: HOLDS"), v)
        self.assertIn("cold chat 8k", v)
        self.assertIn("c3k turns 3 to 10", v)

    def test_each_missing_boot_is_not_decided_and_named(self):
        for label in ST_LABELS:
            v = self.stv(self.fx().st(skip=(label,)))
            self.assertTrue(v.startswith("SOLO TO START: NOT DECIDED"), v)
            self.assertIn(label, v)

    def test_a_differing_ours_reply_hash_in_one_cell_fails(self):
        f = self.st()
        f.put_ours("st-B1b", digest={("cold", 8000, 2): "zzz"})
        v = self.stv(f)
        self.assertTrue(v.startswith("SOLO TO START: FAILS"), v)
        self.assertIn("S1:", v)
        self.assertIn("more than one reply hash", v)

    def test_a_differing_conversation_turn_fails(self):
        f = self.st()
        f.put_ours("st-B0", digest={("chain", "c3k", 5): "zzz"})
        v = self.stv(f)
        self.assertIn("more than one reply hash", v)

    def test_a_differing_concurrent_digest_fails(self):
        f = self.st()
        f.put_concurrent("st-B1x", digest_by_cell={("chat", 0.0, 4): "zzz"})
        v = self.stv(f)
        self.assertIn("S1:", v)
        self.assertIn("more than one reply digest", v)

    def test_an_unclean_boot_check_fails(self):
        f = self.st()
        f.put_concurrent("st-A2", serial_bad=True)
        self.assertIn("own alone or serial check", self.stv(f))

    def test_a_missing_chain_turn_is_not_decided(self):
        f = self.st()
        f.put_ours("st-A1", c3k=dict(zip(range(3, 10), [ST_C3K_MS["st-A1"]] * 7)))
        v = self.stv(f)
        self.assertTrue(v.startswith("SOLO TO START: NOT DECIDED"), v)
        self.assertIn("c3k turn 10", v)

    def test_a_slower_decode_cell_fails(self):
        f = self.st()
        for label in ("st-B1a", "st-B1b"):
            f.put_concurrent(label, per_cell={("code", 0.0, 1): 0.985})
        v = self.stv(f)
        self.assertTrue(v.startswith("SOLO TO START: FAILS"), v)
        self.assertIn("S2: code at 0 with 1 stream(s)", v)
        self.assertIn("slower in B1", v)

    def test_b0_decode_off_by_more_than_one_percent_fails(self):
        f = self.st()
        f.put_concurrent("st-B0", per_cell={("chat", 0.0, 2): 1.015})
        self.assertIn("S2: chat at 0 with 2 stream(s): B0 differs from A by +1.50%", self.stv(f))

    def test_b1x_decode_off_by_more_than_one_percent_fails(self):
        f = self.st()
        f.put_concurrent("st-B1x", per_cell={("code", 0.0, 4): 0.985})
        self.assertIn("S2: code at 0 with 4 stream(s): B1x differs from A by -1.50%", self.stv(f))

    def test_b1x_cold_off_by_one_and_a_half_percent_holds(self):
        f = self.st()
        f.put_ours("st-B1x", cold={n: v * 1.015 for n, v in ST_COLD_MS["st-B1x"].items()})
        v = self.stv(f)
        self.assertTrue(v.startswith("SOLO TO START: HOLDS"), v)

    def test_b0_cold_over_two_percent_off_fails(self):
        f = self.st()
        f.put_ours("st-B0", cold={**ST_COLD_MS["st-B0"], 120000: ST_COLD_MS["st-B0"][120000] * 1.03})
        v = self.stv(f)
        self.assertIn("S3:", v)
        self.assertIn("B0's cold chat first token at 120000 differs from A by", v)

    def test_a_slower_cold_chat_fails(self):
        f = self.st()
        for label in ("st-B1a", "st-B1b"):
            f.put_ours(label, cold={**ST_COLD_MS[label], 32000: ST_COLD_MS[label][32000] * 1.05})
        v = self.stv(f)
        self.assertIn("S3:", v)
        self.assertIn("at 32000", v)
        self.assertIn("slower in B1", v)

    def test_no_c3k_gain_is_neutral(self):
        f = self.st()
        for label in ("st-B1a", "st-B1b"):
            f.put_ours(label, c3k=dict(zip(range(3, 11), [1655.0] * 8)))
        v = self.stv(f)
        self.assertTrue(v.startswith("SOLO TO START: NEUTRAL"), v)
        self.assertIn("c3k turns 3 to 10", v)

    def test_one_b1_boot_not_below_every_a_boot_is_neutral(self):
        f = self.st()
        f.put_ours("st-B1b", c3k=dict(zip(range(3, 11), [1654.1] * 8)))
        v = self.stv(f)
        self.assertTrue(v.startswith("SOLO TO START: NEUTRAL"), v)

    def test_c3k_turn_2_slower_by_more_than_one_percent_fails(self):
        f = self.st()
        for label in ("st-B1a", "st-B1b"):
            f.put_ours(label, c3k_t2=1720)
        v = self.stv(f)
        self.assertIn("S4:", v)
        self.assertIn("c3k turn 2 is", v)

    def test_c74_turns_slower_by_more_than_one_percent_fails(self):
        f = self.st()
        for label in ("st-B1a", "st-B1b"):
            f.put_ours(label, c74=dict(zip(range(2, 9), [825.0] * 7)))
        v = self.stv(f)
        self.assertIn("S4:", v)
        self.assertIn("c74 turns 2 to 8 are", v)

    def test_s5_missing_checks_hold_with_the_clause_named(self):
        f = self.fx().st()
        shutil.rmtree(f.root / "checks")
        lines, v, _ = s94.solo(str(f.root))
        self.assertTrue(v.startswith("SOLO TO START: HOLDS"), v)
        self.assertTrue(any("S5: not decided" in line for line in lines), lines)

    def test_s5_a_fail_line_fails(self):
        f = self.st()
        f.put_check("psts-solo-on/r0.log", "PASS one\nFAIL solo: prompt of 8196: first 3/4\n")
        v = self.stv(f)
        self.assertTrue(v.startswith("SOLO TO START: FAILS"), v)
        self.assertIn("S5:", v)

    def test_s5_a_log_without_a_pass_fails(self):
        f = self.st()
        f.put_check("psts-solo-synth-on.log", "REFUSE TF_GLM_SOLO_TO_START: 0 or 1\n")
        self.assertIn("S5:", self.stv(f))

    def test_the_labels_cannot_be_swapped(self):
        f = self.fx()
        swap = {"st-A1": "st-B1a", "st-A2": "st-B1b", "st-B1a": "st-A1", "st-B1b": "st-A2", "st-B0": "st-B0", "st-B1x": "st-B1x"}
        for label in ST_LABELS:
            other = swap[label]  # the label the data lands on: the two groups exchanged
            f.put_concurrent(other)
            f.put_ours(other, cold=ST_COLD_MS[label], c3k=c3k_default(label), c3k_t2=ST_C3K_T2[label], c74=c74_default(label))
        v = self.stv(f)
        self.assertTrue(v.startswith("SOLO TO START: FAILS"), v)


class ExitCode(Base):
    def run_main(self, root):
        r = subprocess.run([sys.executable, str(SCORER), "--dir", str(root)], capture_output=True, text=True, timeout=900)
        return r.returncode, r.stdout

    def test_the_exit_code_is_one_when_a_lever_fails(self):
        f = self.hk()
        f.put_headlog("hk-B0", 1)
        rc, out = self.run_main(f.root)
        self.assertEqual(rc, 1)
        self.assertIn("HEAD SKIP: FAILS", out)

    def test_the_exit_code_is_zero_when_a_lever_is_neutral_and_the_other_not_decided(self):
        f = self.hk()
        for label in ("hk-B1a", "hk-B1b"):
            for size in s94.HK_CACHE:
                f.put_cache(label, size, 100.0)
        rc, out = self.run_main(f.root)
        self.assertEqual(rc, 0)
        self.assertIn("HEAD SKIP: NEUTRAL", out)
        self.assertIn("SOLO TO START: NOT DECIDED", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
