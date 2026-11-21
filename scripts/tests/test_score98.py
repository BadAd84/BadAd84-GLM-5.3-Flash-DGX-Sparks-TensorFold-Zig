#!/usr/bin/env python3
"""test_score98.py: scripts/queue-scores/score98.py's P0 to P5 clauses on fixtures in upstream's report format.

Run from the top-level shell: python scripts/tests/test_score98.py
SCORE98=<path> points the tests at a copy of the scorer (scripts/tests/mutants_score98.py runs them against each mutant that way).

The fixtures are write-ups of the shape tools/bench_cache_agents.py and its compare write (read from tools/bench_agent_compare.py, tools/bench_agent_trace.py and
tools/tests/test_bench_cache_agents.py): a report carries schema_version 1, benchmark cache_agents, the tool's settings keys, one row a request with the tool's
identity and evidence fields, expected_requests, completed_schedule, fixture_sha256, summary and qualified; a compare report carries token_exact, qualified,
issues, traces.agent_loops.a and .b (requests, usage_verified, cache_evidence, rebuilt_rows, ttft_sum_s) and per_request. Rebuilt rows are prompt_tokens -
cached_tokens, as the tool defines them.

THE ROWS ARE THE REAL ENGINE'S SHAPE. Agent prompts are 4,096 + 4 rows a turn, and a turn that lost nothing resumes at the largest 2,048-row prefill boundary
at or below the previous prompt's end (cached_from_gaps), which is what queue91's chain rows show: cached counts are multiples of 2,048 and the gap to the previous
prompt is alignment loss (55, 1326, 567, 1839, 1060, 257, 1505 with nothing evicted). FIXTURE_CHUNK and FIXTURE_TEMPLATE are literals on purpose, so a mutant of
the scorer's constants cannot move the rows it is judged on. A turn that lost its previous state is listed in the gap plan (2400 rows at the default), and for
turn >= 1 the rebuilt count is growth + gap, so a plan is also exact arithmetic: rebuilt rows R and the totals it implies are controlled by choosing gaps.

The default fixture is the clean HOLDS case: 2 conversations, 8 rounds, turns 2 and 5 of each conversation lost their state (gap 2400) and the rest resume at the
chunk boundary, so A rebuilt 22,328 rows against B's 16,864, R = 24.47%, and 4 of A's 14 counted turns missed (28.57%, above the 10% gate). The exact 10% case
and the exact 1.0% case are built from totals chosen so the Fractions are exact (20,000 against 18,000 rebuilt rows; 1,200.00 s against 1,212.00 s).

THE FIRST P2 TEST WAS WRITTEN BEFORE THE SCORER'S AMENDMENT and failed against the rule as first delivered (which counted any gap above 8 rows as a miss): on a
trace where every turn resumes chunk-aligned with nothing evicted, the old rule read 12 of 14 turns as misses and the test's expectation (NOT oversubscribed) failed.
"""
import hashlib
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
SEED = 11


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_OVER = os.environ.get("SCORE98")
SCORER = pathlib.Path(_OVER) if _OVER else ROOT / "scripts/queue-scores/score98.py"
s98 = load("score98", SCORER)


def h(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


FIXTURE_CHUNK = 2048  # the engine's prefill granularity, literal: a scorer mutant must not move the rows it is judged on
FIXTURE_TEMPLATE = 8
BASE, GROWTH = 4096, 4
DEFAULT_MISSES = ((0, 2), (0, 5), (1, 2), (1, 5))
DEFAULT_MISS = 2400


def aligned(previous_prompt):
    """The largest FIXTURE_CHUNK-row prefill boundary at or below (previous prompt - FIXTURE_TEMPLATE), as the real engine reports it."""
    return ((previous_prompt - FIXTURE_TEMPLATE) // FIXTURE_CHUNK) * FIXTURE_CHUNK


def spread(total, n):
    """n integers summing exactly to total, each within one of the mean."""
    q, r = divmod(total, n)
    return [q + 1] * r + [q] * (n - r)


def cached_from_gaps(plan, *, convs=2, rounds=8, bases=(BASE, BASE), growth=GROWTH):
    """Cached counts per agent row (round major, conversation minor) from a {(conversation, turn): gap} plan: an unlisted turn >= 1
    resumes at the engine's chunk boundary, a listed one resumes `gap` rows short of the previous prompt, turn 0 is cold."""
    out = []
    for r in range(rounds):
        for c in range(convs):
            if r == 0:
                out.append(0)
            else:
                previous = bases[c] + growth * (r - 1)
                mode = plan.get((c, r), "aligned")
                out.append(aligned(previous) if mode == "aligned" else previous - mode)
    return out


def agent_plan(*, convs=2, rounds=8, bases=(BASE, BASE), growth=GROWTH, misses=(), miss_value=DEFAULT_MISS, resumed=()):
    """Rebuilt rows per agent row: the whole prompt at turn 0, `miss_value` at each missed (conversation, turn), else the next value of `resumed`."""
    out, k = [], 0
    for r in range(rounds):
        for c in range(convs):
            if r == 0:
                out.append(bases[c])
            elif (c, r) in misses:
                out.append(miss_value)
            else:
                out.append(resumed[k])
                k += 1
    if k != len(resumed):
        raise ValueError(f"resumed has {len(resumed)} values, {k} turns need one")
    return out


def digest(values):
    """bench_agent_trace.digest: the fixture fingerprint over the ordered request fingerprints."""
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def row(index, kind, conversation, rnd, turn, prompt, cached, ttft, token):
    return {"index": index, "trace": "agent_loops", "conversation": conversation, "round": rnd, "turn": turn, "kind": kind,
            "request_seed": SEED + index, "request_sha256": h(f"request-{index}"),
            "prompt_tokens": prompt, "cached_tokens": cached, "tokens": 2,
            "cache_state": "cold" if cached == 0 else "reused", "complete": True, "token_sha": None,
            "token_sha256": token(index), "output_sha256": h(f"output-{index}"), "tool_calls": 0, "tool_sha256": None,
            "error": None, "completion": "finished", "ttft_s": ttft}


def make_trace(agent=None, *, cached=None, convs=2, rounds=8, bases=(BASE, BASE), growth=GROWTH, oneoff=8, oneoff_cached=0,
               ttft_agent=0.25, ttft_oneoff=0.25, token=None, qualified=True, completed=True):
    """One run report in the tool's format.

    Exactly one of `agent` (the rebuilt rows of each agent turn) or `cached` (its cached_tokens), in row order, round major and conversation minor. `cached`
    is the realistic mode: cached_from_gaps() builds the engine's chunk-aligned resumption, and a lost previous state is listed in the gap plan. Turn 0 is cold.
    """
    if (agent is None) == (cached is None):
        raise ValueError("give exactly one of agent or cached")
    token = token or (lambda i: h(f"token-{i}"))
    rows, index, serial = [], 0, 0
    for r in range(rounds):
        for c in range(convs):
            prompt = bases[c] + growth * r
            hit = prompt - agent[r * convs + c] if cached is None else cached[r * convs + c]
            if not 0 <= hit <= prompt:
                raise ValueError(f"cached {hit} outside 0..{prompt} at row {r * convs + c}")
            rows.append(row(index, "agent", c, r, r, prompt, hit, ttft_agent, token))
            index += 1
            for _ in range(2):
                prompt = oneoff
                rows.append(row(index, "one_off", f"oneoff-{serial:08d}", r, 0, prompt, oneoff_cached, ttft_oneoff, token))
                index += 1
                serial += 1
    rebuilt = sum(r["prompt_tokens"] - r["cached_tokens"] for r in rows)
    return {"schema_version": 1, "benchmark": "cache_agents",
            "settings": {"trace": "agent_loops", "conversations": convs, "rounds": rounds, "prefix_tokens": 32, "reply_tokens": 2,
                         "seed": SEED, "temperature": 0, "one_offs_per_turn": 2, "history_mode": "measured_replies"},
            "thinking": {"thinking": "off requested (unverified)", "thinking_off_requested": True, "thinking_switch": None,
                         "thinking_applicable": None},
            "system_prefixes": [{"tokens": 32, "text_sha256": h("prefix"), "ids_sha256": h("ids")}],
            "rows": rows, "expected_requests": convs * rounds * 3, "completed_schedule": completed, "setup_error": None,
            "fixture_sha256": digest([r["request_sha256"] for r in rows]),
            "summary": {"requests": len(rows), "usage_verified": len(rows), "cache_evidence": "verified", "rebuilt_rows": rebuilt,
                        "ttft_sum_s": sum(r["ttft_s"] for r in rows)},
            "qualified": qualified}


def make_compare(a, b, *, token_exact=True, qualified=True, rebuilt_a=None, rebuilt_b=None, ttft_a=None, ttft_b=None, issues=()):
    """One compare report in the tool's format; a None keyword takes the trace's own summary value, a value overrides it."""
    def side(rep, rebuilt, ttft):
        s = rep["summary"]
        return {"requests": s["requests"], "usage_verified": s["usage_verified"], "cache_evidence": s["cache_evidence"],
                "rebuilt_rows": s["rebuilt_rows"] if rebuilt is None else rebuilt,
                "ttft_sum_s": s["ttft_sum_s"] if ttft is None else ttft}
    sa, sb = side(a, rebuilt_a, ttft_a), side(b, rebuilt_b, ttft_b)
    delta = sb["rebuilt_rows"] - sa["rebuilt_rows"] if None not in (sa["rebuilt_rows"], sb["rebuilt_rows"]) else None
    time = sb["ttft_sum_s"] - sa["ttft_sum_s"] if None not in (sa["ttft_sum_s"], sb["ttft_sum_s"]) else None
    return {"schema_version": 1, "benchmark": "cache_agents_comparison", "token_exact": token_exact, "qualified": qualified,
            "issues": list(issues), "per_request": [],
            "traces": {"agent_loops": {"a": sa, "b": sb, "rebuilt_rows_b_minus_a": delta, "ttft_sum_b_minus_a_s": time,
                                       "rows_no_worse": (delta <= 0) if delta is not None else None}},
            "note": "Latency and rebuilt-row changes are reported; no performance threshold is imposed."}


def default_a(**kw):
    return make_trace(cached=cached_from_gaps({m: DEFAULT_MISS for m in DEFAULT_MISSES}), **kw)


def default_b(**kw):
    return make_trace(cached=cached_from_gaps({}), **kw)


class Fixture:
    """DIR/ce-A/trace.json, DIR/ce-B/trace.json and DIR/compare.json, rewritten whole from scratch on demand."""

    def __init__(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="score98-", dir=ROOT / "work"))
        self.a = default_a()
        self.b = default_b()
        self.cmp = None
        self.drop = set()

    def write(self):
        shutil.rmtree(self.root, ignore_errors=True)
        docs = (("ce-A/trace.json", self.a, "a"), ("ce-B/trace.json", self.b, "b"),
                ("compare.json", self.cmp if self.cmp is not None else make_compare(self.a, self.b), "c"))
        for name, doc, key in docs:
            if key in self.drop:
                continue
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc), encoding="utf-8")
        return self

    def report(self):
        self.write()
        return s98.report(str(self.root))

    def verdict(self):
        return self.report()[1]["verdict"]

    def text(self):
        return "\n".join(self.report()[0])

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Base(unittest.TestCase):
    def fx(self):
        f = Fixture()
        self.addCleanup(f.close)
        return f

    def run_main(self, f):
        f.write()
        r = subprocess.run([sys.executable, str(SCORER), "--dir", str(f.root)], capture_output=True, text=True, timeout=900)
        return r.returncode, r.stdout


class Verdicts(Base):
    """A clean case for every verdict word, and the clauses that decide the boundaries."""

    def test_holds_when_the_policy_rebuilds_fewer_rows(self):
        f = self.fx()
        lines, v, failed = f.report()
        self.assertEqual(v["verdict"], "HOLDS")
        self.assertFalse(failed)
        self.assertIn("P0 QUALIFIED: both traces are qualified", "\n".join(lines))
        self.assertIn("P1 EXACT: EXACT at every one of 48 requests", "\n".join(lines))
        self.assertIn("P2 NOT VACUOUS: OVERSUSCRIBED", "\n".join(lines))

    def test_the_gain_line_prints_r_from_the_tools_sums(self):
        text = self.fx().text()
        self.assertIn("rebuilt rows: A 22328, B 16864", text)
        self.assertIn("R = 1 - 16864/22328 = 24.47%", text)
        self.assertIn("VERDICT: HOLDS", text)

    def test_neutral_when_the_gain_is_under_ten_percent(self):
        f = self.fx()
        f.b = make_trace(cached=cached_from_gaps({(0, 3): DEFAULT_MISS, (1, 3): DEFAULT_MISS}))  # rebuilt 21648, R = 3.05%
        lines, v, failed = f.report()
        self.assertEqual(v["verdict"], "NEUTRAL")
        self.assertEqual(v["reason"], "P3")
        self.assertFalse(failed)
        self.assertIn("P3 GAIN: NEUTRAL at R 3.05%", "\n".join(lines))

    def test_neutral_when_r_is_exactly_zero(self):
        f = self.fx()
        f.b = default_a()  # the same plan as A: rebuilt 22328 both
        lines, v, _ = f.report()
        self.assertEqual(v["verdict"], "NEUTRAL")
        self.assertIn("R = 1 - 22328/22328 = 0.00%", "\n".join(lines))

    def test_fails_when_b_rebuilds_more_rows_than_a(self):
        f = self.fx()
        misses = [(c, r) for c in (0, 1) for r in (2, 3, 5, 6)]
        f.b = make_trace(cached=cached_from_gaps({m: DEFAULT_MISS for m in misses}))  # rebuilt 31872, R = -42.74%
        lines, v, failed = f.report()
        self.assertEqual(v["verdict"], "FAILS")
        self.assertEqual(v["reason"], "P3")
        self.assertFalse(failed)  # only P1 moves the exit code
        self.assertIn("P3 GAIN: FAILS at R -42.74%", "\n".join(lines))

    def test_not_decided_when_the_cache_never_overflowed(self):
        f = self.fx()
        f.a, f.b = make_trace(cached=cached_from_gaps({})), make_trace(cached=cached_from_gaps({}))
        lines, v, failed = f.report()
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertEqual(v["reason"], "P2")
        self.assertFalse(failed)
        self.assertIn("the cache never overflowed", "\n".join(lines))


class P0Qualified(Base):
    def test_p0_not_decided_when_qualified_is_not_true(self):
        f = self.fx()
        f.a["qualified"] = None
        lines, v, _ = f.report()
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertIn("ce-A qualified is None", "\n".join(lines))

    def test_p0_not_decided_when_the_schedule_did_not_complete(self):
        f = self.fx()
        f.a["completed_schedule"] = False
        lines, v, _ = f.report()
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertIn("ce-A completed_schedule is False", "\n".join(lines))

    def test_p0_not_decided_when_completed_schedule_is_missing(self):
        f = self.fx()
        f.a["completed_schedule"] = None
        lines, v, _ = f.report()
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertIn("ce-A completed_schedule is None", "\n".join(lines))


class P1Exact(Base):
    def test_p1_fails_when_the_tools_verdict_is_false(self):
        f = self.fx()
        f.cmp = make_compare(f.a, f.b, token_exact=False)
        lines, v, failed = f.report()
        self.assertEqual(v["P1"], False)
        self.assertEqual(v["verdict"], "FAILS")
        self.assertTrue(failed)
        self.assertIn("the tool's compare reports token_exact False", "\n".join(lines))

    def test_p1_not_decided_when_the_tools_verdict_is_none_but_the_rows_agree(self):
        f = self.fx()
        f.cmp = make_compare(f.a, f.b, token_exact=None)
        lines, v, failed = f.report()
        self.assertIsNone(v["P1"])
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertFalse(failed)
        self.assertIn("the tool's compare verdict is None", "\n".join(lines))

    def test_p1_fails_when_a_token_hash_differs_even_if_the_tool_says_exact(self):
        f = self.fx()
        f.b["rows"][3]["token_sha256"] = h("a different token")
        lines, v, failed = f.report()
        self.assertEqual(v["P1"], False)
        self.assertTrue(failed)
        self.assertIn("request 3: the replies' token_sha256 differ", "\n".join(lines))

    def test_p1_fails_when_a_request_fingerprint_differs(self):
        f = self.fx()
        f.b["rows"][5]["request_sha256"] = h("a different request")
        lines, v, failed = f.report()
        self.assertEqual(v["P1"], False)
        self.assertTrue(failed)
        self.assertIn("request 5: the request fingerprints differ", "\n".join(lines))

    def test_p1_fails_when_the_arms_row_counts_differ(self):
        f = self.fx()
        f.b["rows"].pop()
        v = f.report()[1]
        self.assertEqual(v["P1"], False)


class P2ChunkAligned(Base):
    """The real engine's resumption: cached is the largest 2,048-row prefill boundary at or below the previous prompt's end."""

    def test_p2_chunk_aligned_resumption_with_nothing_evicted_is_not_oversubscribed(self):
        f = self.fx()
        f.a = make_trace(cached=cached_from_gaps({}))  # every turn resumes at the chunk boundary, nothing evicted
        f.b = make_trace(cached=cached_from_gaps({}))
        lines, v, _ = f.report()
        self.assertEqual(v["P2"], False)
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertIn("the cache never overflowed", "\n".join(lines))


class P2Vacuity(Base):
    def test_p2_exactly_ten_percent_is_oversubscribed(self):
        f = self.fx()
        # 2 conversations, 6 rounds: 10 counted turns, exactly one of them resumes short of the allowance
        f.a = make_trace(cached=cached_from_gaps({(1, 5): 2057}, rounds=6), rounds=6)
        f.b = make_trace(cached=cached_from_gaps({}, rounds=6), rounds=6)
        lines, v, _ = f.report()
        self.assertEqual(v["P2"], True)
        self.assertEqual(v["verdict"], "HOLDS")
        self.assertIn("not resumed in full: 1 (10.00%)", "\n".join(lines))

    def test_p2_under_ten_percent_is_not_decided(self):
        f = self.fx()
        f.a = make_trace(cached=cached_from_gaps({(0, 2): 2057}))  # one of 14 turns: 7.14%
        f.b = make_trace(cached=cached_from_gaps({}))
        lines, v, _ = f.report()
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertIn("not resumed in full: 1 (7.14%)", "\n".join(lines))

    def test_p2_a_thrash_to_the_shared_prefix_is_a_miss(self):
        f = self.fx()
        f.a = make_trace(cached=cached_from_gaps({(0, 1): 70000 - 32768}, convs=1, rounds=2, bases=(70000,), growth=0),
                         convs=1, rounds=2, bases=(70000,), growth=0)
        f.b = make_trace(cached=cached_from_gaps({}, convs=1, rounds=2, bases=(70000,), growth=0),
                         convs=1, rounds=2, bases=(70000,), growth=0)
        lines, v, _ = f.report()
        self.assertEqual(v["P2"], True)
        self.assertIn("not resumed in full: 1 (100.00%)", "\n".join(lines))
        self.assertIn("max 37232", "\n".join(lines))

    def test_p2_pairs_each_conversation_with_its_own_previous_turn(self):
        f = self.fx()
        bases = (BASE, 100000)  # a cross-conversation pairing would compare against a prompt ~96,000 rows away
        f.a = make_trace(cached=cached_from_gaps({}, bases=bases), bases=bases)
        f.b = make_trace(cached=cached_from_gaps({}, bases=bases), bases=bases)
        lines, v, _ = f.report()
        self.assertEqual(v["P2"], False)
        self.assertIn("not resumed in full: 0 (0.00%)", "\n".join(lines))


class P2Boundaries(Base):
    def test_p2_gap_2056_is_not_a_miss_and_2057_is(self):
        for gap, expected in ((0, False), (55, False), (1839, False), (2047, False), (2056, False), (2057, True)):
            with self.subTest(gap=gap):
                f = self.fx()
                plan = {(c, r): gap for c in (0, 1) for r in range(1, 6)}
                f.a = make_trace(cached=cached_from_gaps(plan, rounds=6), rounds=6)
                f.b = make_trace(cached=cached_from_gaps({}, rounds=6), rounds=6)
                _, v, _ = f.report()
                self.assertEqual(v["P2"], expected)

    def test_p2_boundary_shows_the_count_on_the_missed_side(self):
        f = self.fx()
        plan = {(c, r): (2057 if (c, r) == (0, 5) else 0) for c in (0, 1) for r in range(1, 6)}
        f.a = make_trace(cached=cached_from_gaps(plan, rounds=6), rounds=6)
        f.b = make_trace(cached=cached_from_gaps({}, rounds=6), rounds=6)
        lines, v, _ = f.report()
        self.assertEqual(v["P2"], True)
        self.assertIn("not resumed in full: 1 (10.00%)", "\n".join(lines))


class P2Report(Base):
    def test_p2_reports_the_gap_distribution_and_the_chunk_alignment(self):
        f = self.fx()
        gaps = {(0, 1): 0, (0, 2): 55, (0, 3): 1839, (0, 4): 2047, (0, 5): 2056}
        f.a = make_trace(cached=cached_from_gaps(gaps, convs=1, rounds=6), convs=1, rounds=6)
        f.b = make_trace(cached=cached_from_gaps({}, convs=1, rounds=6), convs=1, rounds=6)
        lines, v, _ = f.report()
        text = "\n".join(lines)
        self.assertIn("gaps (previous prompt minus cached, over A's 5 counted turns): min 0, median 1839, max 2056", text)
        self.assertIn("chunk alignment: 1 of 5 nonzero cached counts in A are multiples of 2048", text)
        self.assertEqual(v["P2"], False)  # 2056 is inside the allowance


class P3Gain(Base):
    def test_r_exactly_ten_percent_holds(self):
        f = self.fx()
        f.a = make_trace(agent_plan(misses=DEFAULT_MISSES, resumed=spread(1952, 10)))  # rebuilt 20000
        f.b = make_trace(agent_plan(resumed=spread(9552, 14)))  # rebuilt 18000
        lines, v, _ = f.report()
        self.assertEqual(v["P3_R"], s98.Fraction(1, 10))
        self.assertEqual(v["verdict"], "HOLDS")
        self.assertIn("R = 1 - 18000/20000 = 10.00%", "\n".join(lines))
        self.assertIn("P3 GAIN: R 10.00% is at or above the 10% threshold, the gain clause holds", "\n".join(lines))

    def test_p3_not_decided_when_compare_contradicts_the_traces(self):
        f = self.fx()
        wrong = f.a["summary"]["rebuilt_rows"] + 1
        f.cmp = make_compare(f.a, f.b, rebuilt_a=wrong)
        lines, v, _ = f.report()
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertIn("the receipts contradict each other", "\n".join(lines))
        self.assertIn(f"compare traces.agent_loops.a.rebuilt_rows {wrong}", "\n".join(lines))

    def test_p3_not_decided_when_a_rebuilt_total_is_not_a_number(self):
        f = self.fx()
        f.b["summary"]["rebuilt_rows"] = None
        f.cmp = make_compare(f.a, f.b, rebuilt_b=None)
        lines, v, _ = f.report()
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertIn("rebuilt rows A 22328, B None", "\n".join(lines))

    def test_p3_not_decided_when_a_rebuilt_no_rows_to_save(self):
        f = self.fx()
        f.a = make_trace(cached=[0] * 16, bases=(0, 0), growth=0, oneoff=0)
        f.b = make_trace(cached=[0] * 16, bases=(0, 0), growth=0, oneoff=0)
        lines, v, _ = f.report()
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertIn("has no denominator", "\n".join(lines))


class P4Time(Base):
    def test_exactly_one_percent_slower_still_holds(self):
        f = self.fx()
        f.a = default_a(ttft_agent=25.0, ttft_oneoff=25.0)
        f.b = default_b(ttft_agent=25.25, ttft_oneoff=25.25)  # sums 1200.00 against 1212.00
        lines, v, _ = f.report()
        self.assertEqual(v["P4"], True)
        self.assertEqual(v["verdict"], "HOLDS")
        self.assertIn("B 1212.00 s against A 1200.00 s (+1.00%)", "\n".join(lines))

    def test_over_the_one_percent_allowance_is_neutral_with_the_reason(self):
        f = self.fx()
        f.a = default_a(ttft_agent=25.0, ttft_oneoff=25.0)
        f.b = default_b(ttft_agent=25.375, ttft_oneoff=25.375)
        lines, v, _ = f.report()
        self.assertEqual(v["P4"], False)
        self.assertEqual(v["verdict"], "NEUTRAL")
        self.assertEqual(v["reason"], "P4")
        self.assertIn("VERDICT: NEUTRAL (P4:", "\n".join(lines))
        self.assertIn("+1.50%", "\n".join(lines))

    def test_the_gate_is_the_sum_and_the_agent_mean_is_reported(self):
        f = self.fx()
        f.a = default_a(ttft_agent=1.0, ttft_oneoff=5.0)
        f.b = default_b(ttft_agent=2.0, ttft_oneoff=2.0)  # agent mean twice A's, the sum 45% lower
        lines, v, _ = f.report()
        self.assertEqual(v["P4"], True)
        self.assertEqual(v["verdict"], "HOLDS")
        self.assertIn("agent-request mean TTFT: B 2.000 s against A 1.000 s (+100.00%)", "\n".join(lines))

    def test_not_decided_when_a_ttft_sum_is_unavailable(self):
        f = self.fx()
        f.b["rows"][0]["ttft_s"] = None
        f.b["summary"]["ttft_sum_s"] = None
        f.cmp = make_compare(f.a, f.b, ttft_b=None)
        lines, v, _ = f.report()
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertIn("P4 TIME: NOT DECIDED", "\n".join(lines))


class P5Replay(Base):
    def within(self):
        f = self.fx()
        f.a = make_trace(agent_plan(misses=DEFAULT_MISSES, resumed=spread(1952, 10)))  # rebuilt 20000
        return f

    def test_places_r_against_the_predicted_range(self):
        f = self.within()
        f.b = make_trace(agent_plan(resumed=spread(2552, 14)))  # rebuilt 11000, R = 45.00%
        text = f.text()
        self.assertIn("R = 1 - 11000/20000 = 45.00%", text)
        self.assertIn("measured R 45.00% against the simulation's predicted 44% to 50%: within", text)

    def test_above_the_range(self):
        f = self.within()
        f.b = make_trace(agent_plan(resumed=spread(56, 14)))  # rebuilt 8504, R = 57.48%
        text = f.text()
        self.assertIn("R = 1 - 8504/20000 = 57.48%", text)
        self.assertIn(": above", text)

    def test_below_the_range(self):
        f = self.within()
        f.b = make_trace(agent_plan(resumed=spread(3152, 14)))  # rebuilt 11600, R = 42.00%
        text = f.text()
        self.assertIn("R = 1 - 11600/20000 = 42.00%", text)
        self.assertIn(": below", text)

    def test_prints_each_conversation_and_every_four_rounds(self):
        text = self.fx().text()
        self.assertIn("conversation 0: A", text)
        self.assertIn("conversation 1: A", text)
        self.assertIn("rounds 1 to 4: A", text)
        self.assertIn("rounds 1 to 8: A", text)

    def test_it_carries_no_verdict(self):
        lines, v, _ = self.fx().report()
        start = next(i for i, l in enumerate(lines) if l.startswith("== P5"))
        end = next(i for i, l in enumerate(lines) if l.startswith("VERDICT:"))
        p5 = lines[start:end]
        self.assertTrue(any(l.startswith("measured R") for l in p5))
        self.assertFalse(any(w in l for l in p5 for w in ("HOLDS", "NEUTRAL", "FAILS", "NOT DECIDED")))


class CacheGauges(Base):
    REAL = ("tensorfold:prompt_cache_budget_bytes 8426464256\n"
            "tensorfold:prompt_cache_minimum_state_bytes 176160768\n"
            "tensorfold:prompt_cache_states 0\n"
            "tensorfold:prompt_cache_bytes 8426356736\n")

    def metrics(self, f, arm, when, text):
        (f.root / arm / f"metrics-{when}.txt").write_text(text, encoding="utf-8")

    def test_prints_the_real_gauge_lines_of_each_arm(self):
        f = self.fx()
        f.write()
        self.metrics(f, "ce-A", "before", self.REAL)
        self.metrics(f, "ce-A", "after", "tensorfold:prompt_cache_states 3\ntensorfold:prompt_cache_bytes 9000000000\n")
        text = "\n".join(s98.report(str(f.root))[0])
        self.assertIn("ce-A metrics-before: budget 8426464256, minimum state 176160768, states 0, "
                      "bytes 8426356736 (states plus spare buffers, not occupancy)", text)
        self.assertIn("ce-A metrics-after: prompt_cache_budget_bytes is missing, prompt_cache_minimum_state_bytes is missing", text)
        self.assertIn("ce-B metrics-after.txt is missing", text)

    def test_the_budget_line_reads_equal(self):
        f = self.fx()
        f.write()
        for arm in ("ce-A", "ce-B"):
            self.metrics(f, arm, "before", self.REAL)
        text = "\n".join(s98.report(str(f.root))[0])
        self.assertIn("budget: the replay assumed 8426464256 B; ce-A's gauge (before) reads 8426464256 B: equal", text)
        self.assertIn("budget: the replay assumed 8426464256 B; ce-B's gauge (before) reads 8426464256 B: equal", text)

    def test_the_budget_line_reads_different(self):
        f = self.fx()
        f.write()
        self.metrics(f, "ce-A", "before", self.REAL)
        self.metrics(f, "ce-B", "before", self.REAL.replace("prompt_cache_budget_bytes 8426464256", "prompt_cache_budget_bytes 8000000000"))
        text = "\n".join(s98.report(str(f.root))[0])
        self.assertIn("ce-B's gauge (before) reads 8000000000 B: different", text)

    def test_a_missing_gauge_is_named(self):
        f = self.fx()
        f.write()
        self.metrics(f, "ce-A", "before", "tensorfold:prompt_cache_states 0\n")
        text = "\n".join(s98.report(str(f.root))[0])
        self.assertIn("ce-A metrics-before: prompt_cache_budget_bytes is missing, prompt_cache_minimum_state_bytes is missing, "
                      "prompt_cache_bytes is missing", text)
        self.assertIn("budget: ce-A has no prompt_cache_budget_bytes gauge", text)

    def test_the_block_changes_no_verdict(self):
        f = self.fx()
        before = f.verdict()
        f.write()
        self.metrics(f, "ce-A", "after", self.REAL)
        self.assertEqual(s98.report(str(f.root))[1]["verdict"], before)


class MissingFiles(Base):
    def test_missing_a_is_not_decided_and_named(self):
        f = self.fx()
        f.drop.add("a")
        lines, v, failed = f.report()
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertFalse(failed)
        self.assertIn("ce-A", "\n".join(lines))
        self.assertIn("trace.json is missing", "\n".join(lines))

    def test_missing_b_is_not_decided_and_named(self):
        f = self.fx()
        f.drop.add("b")
        lines, v, _ = f.report()
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertIn("ce-B", "\n".join(lines))
        self.assertIn("trace.json is missing", "\n".join(lines))

    def test_missing_compare_is_not_decided_and_named(self):
        f = self.fx()
        f.drop.add("c")
        lines, v, failed = f.report()
        self.assertEqual(v["verdict"], "NOT DECIDED")
        self.assertFalse(failed)
        self.assertIn("compare.json is missing", "\n".join(lines))


class ClauseIsolation(Base):
    """Each clause flips alone: only its own reading changes, so a broken clause is named by its own test."""

    def test_p1_alone_flips(self):
        f = self.fx()
        f.b["rows"][3]["token_sha256"] = h("moved")
        lines, v, _ = f.report()
        self.assertEqual(v["P0"], True)
        self.assertEqual(v["P1"], False)
        self.assertEqual(v["P2"], True)
        self.assertIsNotNone(v["P3_R"])
        self.assertEqual(v["verdict"], "FAILS")

    def test_p2_alone_flips(self):
        f = self.fx()
        f.a = make_trace(cached=cached_from_gaps({}))
        lines, v, _ = f.report()
        self.assertEqual(v["P0"], True)
        self.assertEqual(v["P1"], True)
        self.assertEqual(v["P2"], False)
        self.assertIsNotNone(v["P3_R"])
        self.assertEqual(v["verdict"], "NOT DECIDED")

    def test_p4_alone_flips(self):
        f = self.fx()
        f.b = default_b(ttft_agent=0.375, ttft_oneoff=0.375)
        lines, v, _ = f.report()
        self.assertEqual(v["P1"], True)
        self.assertEqual(v["P2"], True)
        self.assertTrue(v["P3_R"] is not None and v["P3_R"] > s98.Fraction(1, 10))
        self.assertEqual(v["verdict"], "NEUTRAL")


class ExitCode(Base):
    def test_one_only_when_p1_fails(self):
        f = self.fx()
        f.b["rows"][2]["token_sha256"] = h("moved")
        rc, out = self.run_main(f)
        self.assertEqual(rc, 1)
        self.assertIn("P1 EXACT: FAILS", out)

    def test_zero_when_the_cache_never_overflowed(self):
        f = self.fx()
        f.a = make_trace(cached=cached_from_gaps({}))
        rc, out = self.run_main(f)
        self.assertEqual(rc, 0)
        self.assertIn("VERDICT: NOT DECIDED", out)

    def test_zero_when_a_file_is_missing(self):
        f = self.fx()
        f.drop.add("c")
        rc, out = self.run_main(f)
        self.assertEqual(rc, 0)
        self.assertIn("compare.json is missing", out)

    def test_the_default_dir_is_the_queue_dir(self):
        r = subprocess.run([sys.executable, str(SCORER), "--help"], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0)
        self.assertIn("work/pp98/f98-c", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
