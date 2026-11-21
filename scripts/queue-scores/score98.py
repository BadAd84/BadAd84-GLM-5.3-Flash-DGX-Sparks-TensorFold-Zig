#!/usr/bin/env python3
"""score98.py [--dir DIR] - queue98 (scripts/queues/queue98.sh): E3, the served A/B of upstream's opt-in prompt-cache victim policy TF_CACHE_EVICT=decayed_resume
against TF_CACHE_EVICT unset, both boots on the stack on the pin (image m130a) at the deployed shape.

DIR holds ce-A/trace.json, ce-B/trace.json and compare.json, the way queue98 writes them: trace.json is upstream's tools/bench_cache_agents.py `run` report
(schema_version 1, benchmark cache_agents), ce-A with TF_CACHE_EVICT unset and ce-B with it set to decayed_resume; compare.json is the same client's `compare`
report of A against B. The boots' metrics-before.txt and metrics-after.txt are read only by the CACHE block, which prints the budget, the minimum state, the
states and the bytes (states plus spare buffers, not occupancy) around each run and compares each arm's budget with the replay's 8,426,464,256 B, as a report;
r0-boot.log and r0-after.log are kept for the owner and are not read. Default DIR is work/pp98/f98-c.

EVERY NUMBER BELOW COMES FROM THE TOOL'S OWN DEFINITION, never a second one, and the formulas are copied from tools/bench_agent_compare.py:
  usage_verified(row) is the tool's own: complete is True, no error, prompt_tokens and cached_tokens are nonnegative integers, cached_tokens <= prompt_tokens,
    and cache_state equals "cold" for cached_tokens 0 and "reused" otherwise;
  a trace's rebuilt rows is summarize()'s rebuilt_rows: the sum of prompt_tokens - cached_tokens over every row, or None when any row fails usage_verified();
  a trace's TTFT sum is summarize()'s ttft_sum_s: the sum of ttft_s, or None unless every row passes time_verified() (complete, no error, a 64-hex
    output_sha256 and a finite nonnegative ttft_s);
  reply equality is token_equal()'s: both rows complete, no error, a 64-hex token_sha256 on each, and the two equal; this scorer recomputes it from the rows and
    also reads the compare report's own token_exact verdict, and P1 requires both;
  a request's identity is its request_sha256 (the client's fingerprint of the request body without the model), compared at the same index.
The compare report's traces.agent_loops.a and .b summary objects are the primary source of the two rebuilt-row totals and the two TTFT sums, cross-checked against
each trace's own summary object and against the rows themselves; a receipt that contradicts itself is NOT DECIDED, naming the contradiction.

THE RULES, FIXED BY THE PARENT AND WRITTEN BEFORE ANY ROW EXISTED, implemented literally:
  P0 QUALIFIED: both traces qualified and completed_schedule true (the tool's own flags); a missing file or a false flag is NOT DECIDED, naming which.
  P1 EXACT: every request's reply equal across the two arms (the tool's compare verdict, and recomputed from the rows' token_sha256 and request fingerprints); a
     difference FAILS (the policy cannot change tokens). A compare verdict of None (the tool could not verify) with rows that agree is NOT DECIDED, never a pass.
  P2 NOT VACUOUS: the cache was oversubscribed in A, measured as: at least 10% of A's agent-turn requests (kind agent, turn >= 1) did NOT resume the whole previous
     turn's prompt from cache. The test is cached_tokens against the PREVIOUS agent row of the SAME conversation: a turn is resumed in full when cached_tokens >=
     previous prompt_tokens - RESUME_ALLOWANCE, with RESUME_ALLOWANCE = RESUME_CHUNK + TEMPLATE_ROWS = 2,048 + 8 = 2,056; otherwise NOT DECIDED ("the cache never
     overflowed").
     AMENDED BEFORE ANY E3 ROW EXISTED. The rule as first written counted any gap above TEMPLATE_ROWS (8 rows) as a miss. Real queue91 rows
     (docs/audit-2026-11-12/queue-rows/queue91/f91-c/mn1/chain.jsonl) show the engine resuming at the largest 2,048-row prefill boundary at or below the previous
     prompt's end: prompt_tokens 112695, 113966, 115255, 116527, 117796, 119041, 120289, 121557 against cached_tokens 0, 112640, 112640, 114688, 114688,
     116736, 118784, 118784. The cached counts are multiples of 2,048 and the gaps 55, 1326, 567, 1839, 1060, 257, 1505 are alignment loss, with nothing evicted.
     Under the first rule nearly every real turn would have read as a miss, so the vacuity gate would pass whatever the cache did. The allowance is therefore
     2,056 rows. A lost previous-turn state leaves a gap of at least one turn's growth (about 2,064 rows at the E3 settings) plus its own alignment loss, so it is
     still a miss. The 10% threshold, the pairing and the NOT DECIDED wording are unchanged. The P2 block also reports the gap distribution (min, median, max) and
     the chunk alignment of A's nonzero cached counts; neither affects the verdict.
  P3 GAIN, the verdict: R = 1 - B_rebuilt / A_rebuilt over the whole trace, rebuilt rows as the tool's own summary sums them. HOLDS when P0-P2 hold and R >= 10%;
     NEUTRAL when 0 <= R < 10%; FAILS when R < 0 or P1 fails.
  P4 TIME: sum over all requests of TTFT in B against A, and the mean TTFT of agent requests; B must not be slower than A by more than 1.0% on the sum for a HOLDS
     (otherwise the verdict is NEUTRAL with the reason named).
  P5 REPLAY AGREEMENT (report only, no verdict): the measured R beside the simulation's predicted range 44% to 50% (within / below / above), per-conversation rebuilt
     rows A and B, and per-round totals every 4 rounds.
  Exit code 1 only when P1 fails; everything else exits 0.

The arithmetic is exact: rebuilt-row counts and R are integers and Fractions, and the 1.0% time allowance and the 10% thresholds are Fractions, so a boundary case
(R exactly 10%, B exactly 1.0% slower) is decided by equality, not by a float's rounding.
"""
import argparse
import json
import math
import os
import re
import statistics
import sys
from fractions import Fraction

TRACE = "agent_loops"
RESUME_CHUNK = 2048        # P2: the engine's prefill granularity: it resumes at the largest 2,048-row boundary at or below the previous prompt's end
TEMPLATE_ROWS = 8          # P2: rows the chat template re-renders at the assistant/user junction
RESUME_ALLOWANCE = RESUME_CHUNK + TEMPLATE_ROWS  # P2: a turn is resumed in full when cached_tokens >= previous prompt_tokens - 2,056
OVERSUSCRIBED = Fraction(1, 10)   # P2: at least this share of A's agent turns must have missed
GAIN = Fraction(1, 10)     # P3: R at or above this is a gain
SLOW = Fraction(1, 100)    # P4: B may be slower than A on the TTFT sum by at most this
PREDICTED = (Fraction(44, 100), Fraction(50, 100))  # P5: work/cache-replay-lane/REPORT.md sections 4 to 6, all three byte models
SHA = re.compile(r"[0-9a-f]{64}")
GAUGE = re.compile(r"^(?:tensorfold:)?(prompt_cache_(?:budget_bytes|minimum_state_bytes|states|bytes)) ([\d.]+)$")
CACHE_NAMES = ("prompt_cache_budget_bytes", "prompt_cache_minimum_state_bytes", "prompt_cache_states", "prompt_cache_bytes")
# The budget the replay assumed, from queue91's boot of the stack on the pin at the deployed shape (prompt_cache_budget_bytes 8426464256) and
# work/cache-replay-lane/REPORT.md section 3. The CACHE block compares each arm's own gauge against it.
PREDICTION_BUDGET = 8426464256


def integer(value):
    """A nonnegative integer as the tool counts one (type is int, so True is not a count)."""
    return type(value) is int and value >= 0


def sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def seconds(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def usage_verified(row):
    """bench_agent_compare.usage_verified, expression for expression."""
    prompt, cached = row.get("prompt_tokens"), row.get("cached_tokens")
    return (row.get("complete") is True and not row.get("error") and integer(prompt) and integer(cached)
            and cached <= prompt and row.get("cache_state") == ("cold" if cached == 0 else "reused"))


def time_verified(row):
    """bench_agent_compare.time_verified, expression for expression."""
    return row.get("complete") is True and not row.get("error") and sha(row.get("output_sha256")) and seconds(row.get("ttft_s"))


def rebuilt_rows(rows):
    """summarize()'s rebuilt_rows: the whole trace's rebuilt rows, or None when a row's usage is unverified."""
    return sum(r["prompt_tokens"] - r["cached_tokens"] for r in rows) if rows and all(usage_verified(r) for r in rows) else None


def time_sum(rows):
    """summarize()'s ttft_sum_s: the whole trace's TTFT in seconds, or None when a row's timing is unverified."""
    return sum(r["ttft_s"] for r in rows) if rows and all(time_verified(r) for r in rows) else None


def identical(x, y):
    """bench_agent_compare.token_equal as an equality test: True only when both sides are complete, error-free and carry the same 64-hex token_sha256."""
    if x.get("error") or y.get("error") or x.get("complete") is not True or y.get("complete") is not True:
        return False
    a, b = x.get("token_sha256"), y.get("token_sha256")
    return sha(a) and sha(b) and a == b


def load(path):
    """(report, None) or (None, a sentence naming what is wrong)."""
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
    except FileNotFoundError:
        return None, f"{path} is missing"
    except (OSError, ValueError) as exc:
        return None, f"{path} is not readable JSON ({type(exc).__name__})"
    if not isinstance(value, dict):
        return None, f"{path} is not a JSON object"
    return value, None


def pct(value):
    return f"{float(value):.2%}"


# ---------------------------------------------------------------- P0

def p0(a, ea, b, eb):
    """(lines, True when both reports carry the tool's two flags)."""
    out = ["== P0 QUALIFIED: the client's own qualified and completed_schedule flags on both traces"]
    problems = []
    for name, rep, err in (("ce-A", a, ea), ("ce-B", b, eb)):
        if err:
            problems.append(f"{name}: {err}")
            out.append(f"{name}: NOT DECIDED: {err}")
            continue
        qualified, completed = rep.get("qualified"), rep.get("completed_schedule")
        rows = rep.get("rows") or []
        out.append(f"{name}: qualified {qualified!r}, completed_schedule {completed!r}, {len(rows)} row(s), setup_error {rep.get('setup_error')!r}")
        if qualified is not True:
            problems.append(f"{name} qualified is {qualified!r}")
        if completed is not True:
            problems.append(f"{name} completed_schedule is {completed!r}")
    if problems:
        out.append("P0 QUALIFIED: NOT DECIDED: " + "; ".join(problems))
        return out, False
    out.append("P0 QUALIFIED: both traces are qualified and their schedules completed")
    return out, True


# ---------------------------------------------------------------- P1

def p1(a, b, cmp, ecmp):
    """(lines, True exact, False a difference, None not decided)."""
    out = ["== P1 EXACT: every request's reply equal across the arms (the tool's compare verdict plus the rows' token hashes and request fingerprints)"]
    if ecmp:
        out.append(f"P1 EXACT: NOT DECIDED: {ecmp}")
        return out, None
    issues = []
    tool = cmp.get("token_exact")
    out.append(f"the tool's compare: token_exact {tool!r}, qualified {cmp.get('qualified')!r}, issues {cmp.get('issues')!r}")
    if tool is False:
        issues.append("the tool's compare reports token_exact False")
    ra, rb = a.get("rows") or [], b.get("rows") or []
    if len(ra) != len(rb):
        issues.append(f"the arms carry {len(ra)} and {len(rb)} rows")
    bad = []
    for i, (x, y) in enumerate(zip(ra, rb)):
        if x.get("request_sha256") != y.get("request_sha256"):
            bad.append(f"request {i}: the request fingerprints differ ({x.get('request_sha256')!r} against {y.get('request_sha256')!r})")
        elif not identical(x, y):
            bad.append(f"request {i}: the replies' token_sha256 differ or are unverified ({x.get('token_sha256')!r} against {y.get('token_sha256')!r})")
    out.append(f"the rows: {len(ra)} paired request(s), {len(bad)} differing or unverified")
    for line in bad[:8]:
        out.append("  " + line)
    if bad:
        issues.append(f"{len(bad)} request(s) differ")
    if issues:
        out.append("P1 EXACT: FAILS: " + "; ".join(issues))
        return out, False
    if tool is not True:
        out.append(f"P1 EXACT: NOT DECIDED: the rows agree but the tool's compare verdict is {tool!r}, not True")
        return out, None
    out.append(f"P1 EXACT: EXACT at every one of {len(ra)} requests")
    return out, True


# ---------------------------------------------------------------- P2

def p2(a):
    """(lines, True oversubscribed, False the cache never overflowed, None not decided; share)."""
    out = ["== P2 NOT VACUOUS: A's agent turns that did not resume the previous turn's prompt (the previous agent row of the same conversation; a turn resumed in "
           f"full when cached_tokens >= that prompt minus the {RESUME_ALLOWANCE}-row allowance: {RESUME_CHUNK} chunk plus {TEMPLATE_ROWS} template rows)"]
    rows = a.get("rows") or []
    conv, shape = {}, []
    for r in rows:
        if not isinstance(r, dict) or r.get("kind") != "agent":
            continue
        c, turn = r.get("conversation"), r.get("turn")
        if not integer(c) or not integer(turn):
            shape.append(f"agent row {r.get('index')!r}: conversation {c!r}, turn {turn!r}")
            continue
        conv.setdefault(c, []).append(r)
    if shape:
        out.append("P2 NOT VACUOUS: NOT DECIDED: out of shape: " + "; ".join(shape[:6]))
        return out, None, None
    total = missed = 0
    gaps, bad = [], []
    for c in sorted(conv):
        prev = None
        for r in sorted(conv[c], key=lambda r: (r.get("round") if integer(r.get("round")) else -1, r.get("index") if integer(r.get("index")) else -1)):
            if prev is not None and r["turn"] >= 1:
                if not (usage_verified(prev) and usage_verified(r)):
                    bad.append(f"conversation {c} round {r.get('round')!r}: an unverified prompt/cached count")
                else:
                    gaps.append(prev["prompt_tokens"] - r["cached_tokens"])
                    total += 1
                    if r["cached_tokens"] < prev["prompt_tokens"] - RESUME_ALLOWANCE:
                        missed += 1
            prev = r
    if gaps:
        ordered = sorted(gaps)
        out.append(f"gaps (previous prompt minus cached, over A's {len(gaps)} counted turns): min {ordered[0]}, "
                   f"median {statistics.median(ordered):g}, max {ordered[-1]}")
    else:
        out.append("gaps: none counted")
    nonzero = [r["cached_tokens"] for r in rows if isinstance(r, dict) and integer(r.get("cached_tokens")) and r["cached_tokens"] > 0]
    aligned = sum(1 for v in nonzero if v % RESUME_CHUNK == 0)
    out.append(f"chunk alignment: {aligned} of {len(nonzero)} nonzero cached counts in A are multiples of {RESUME_CHUNK}")
    if bad:
        out.append("P2 NOT VACUOUS: NOT DECIDED: " + "; ".join(bad[:6]))
        return out, None, None
    if total == 0:
        out.append("P2 NOT VACUOUS: NOT DECIDED: A has no agent turn with turn >= 1")
        return out, None, None
    share = Fraction(missed, total)
    ok = share >= OVERSUSCRIBED
    out.append(f"A's agent turns with turn >= 1: {total}; not resumed in full: {missed} ({pct(share)}); the threshold is {float(OVERSUSCRIBED):.0%}")
    if not ok:
        out.append(f"P2 NOT VACUOUS: NOT DECIDED: the cache never overflowed ({missed} of {total} turns rebuilt more than the {RESUME_ALLOWANCE}-row allowance)")
        return out, False, share
    out.append(f"P2 NOT VACUOUS: OVERSUSCRIBED, {missed} of {total} agent turns did not resume the previous turn's whole prompt")
    return out, True, share


# ---------------------------------------------------------------- P3 and P4 numbers

def trace_side(cmp, side):
    return (((cmp or {}).get("traces") or {}).get(TRACE) or {}).get(side) or {}


def totals(rep, name):
    """(rebuilt rows, TTFT sum, contradictions): the rows' own sums against the report's own summary object."""
    rows = rep.get("rows") or []
    summary = rep.get("summary") or {}
    rebuilt, ttft = rebuilt_rows(rows), time_sum(rows)
    bad = []
    if summary.get("rebuilt_rows") != rebuilt:
        bad.append(f"{name}: summary.rebuilt_rows {summary.get('rebuilt_rows')!r} against the rows' {rebuilt!r}")
    if summary.get("ttft_sum_s") != ttft:
        bad.append(f"{name}: summary.ttft_sum_s {summary.get('ttft_sum_s')!r} against the rows' {ttft!r}")
    return rebuilt, ttft, bad


def p3(a, b, cmp):
    """(lines, R or None, A, B)."""
    out = [f"== P3 GAIN: R = 1 - B_rebuilt / A_rebuilt over the whole trace, rebuilt rows from the tool's summarize (compare.json traces.{TRACE}.a and .b)"]
    ra, _, w1 = totals(a, "ce-A")
    rb, _, w2 = totals(b, "ce-B")
    A = trace_side(cmp, "a").get("rebuilt_rows")
    B = trace_side(cmp, "b").get("rebuilt_rows")
    bad = w1 + w2
    if A != ra:
        bad.append(f"compare traces.{TRACE}.a.rebuilt_rows {A!r} against ce-A's rows' {ra!r}")
    if B != rb:
        bad.append(f"compare traces.{TRACE}.b.rebuilt_rows {B!r} against ce-B's rows' {rb!r}")
    if not integer(A) or not integer(B):
        out.append(f"P3 GAIN: NOT DECIDED: rebuilt rows A {A!r}, B {B!r} (the tool reports None when a row's usage is unverified)")
        return out, None, A, B
    if bad:
        out.append("P3 GAIN: NOT DECIDED: the receipts contradict each other: " + "; ".join(bad[:6]))
        return out, None, A, B
    out.append(f"rebuilt rows: A {A}, B {B}")
    if A <= 0:
        out.append(f"P3 GAIN: NOT DECIDED: A rebuilt {A} rows, so 1 - B/A has no denominator with anything left to save")
        return out, None, A, B
    r = Fraction(A - B, A)
    out.append(f"R = 1 - {B}/{A} = {pct(r)}")
    if r < Fraction(0):
        out.append(f"P3 GAIN: FAILS at R {pct(r)}: B rebuilt more rows than A")
    elif r < GAIN:
        out.append(f"P3 GAIN: NEUTRAL at R {pct(r)}: 0 <= R < {float(GAIN):.0%}")
    else:
        out.append(f"P3 GAIN: R {pct(r)} is at or above the {float(GAIN):.0%} threshold, the gain clause holds")
    return out, r, A, B


def agent_mean(rep):
    """The mean TTFT of the trace's agent requests, or None when there are none or a timing is unverified."""
    rows = [r for r in (rep.get("rows") or []) if r.get("kind") == "agent"]
    if not rows or not all(time_verified(r) for r in rows):
        return None
    return sum(r["ttft_s"] for r in rows) / len(rows)


def p4(a, b, cmp):
    """(lines, True ok, False slower than the allowance, None not decided; delta or None)."""
    out = ["== P4 TIME: the sum of all requests' TTFT, B against A (the gate), and the mean TTFT of agent requests (reported)"]
    _, sa, w1 = totals(a, "ce-A")
    _, sb, w2 = totals(b, "ce-B")
    A = trace_side(cmp, "a").get("ttft_sum_s")
    B = trace_side(cmp, "b").get("ttft_sum_s")
    bad = w1 + w2
    if A != sa:
        bad.append(f"compare traces.{TRACE}.a.ttft_sum_s {A!r} against ce-A's rows' {sa!r}")
    if B != sb:
        bad.append(f"compare traces.{TRACE}.b.ttft_sum_s {B!r} against ce-B's rows' {sb!r}")
    if not seconds(A) or not seconds(B) or A == 0:
        out.append(f"P4 TIME: NOT DECIDED: TTFT sums A {A!r}, B {B!r}" + (" (" + "; ".join(bad[:4]) + ")" if bad else ""))
        return out, None, None
    if bad:
        out.append("P4 TIME: NOT DECIDED: the receipts contradict each other: " + "; ".join(bad[:6]))
        return out, None, None
    delta = (Fraction(B) - Fraction(A)) / Fraction(A)
    ma, mb = agent_mean(a), agent_mean(b)
    slower = Fraction(B) - Fraction(A) > Fraction(A) * SLOW
    out.append(f"TTFT sum: B {float(B):.2f} s against A {float(A):.2f} s ({float(delta):+.2%}); the allowance is +{float(SLOW):.2%}: "
               + ("SLOWER than A by more than the allowance" if slower else "within the allowance"))
    if ma and mb is not None:
        out.append(f"agent-request mean TTFT: B {mb:.3f} s against A {ma:.3f} s ({(Fraction(mb) - Fraction(ma)) / Fraction(ma):+.2%})")
    else:
        out.append("agent-request mean TTFT: not available (no verified agent rows on an arm)")
    return out, (not slower), delta


# ---------------------------------------------------------------- CACHE gauges (report only)

def gauges(path):
    """({name: value}, None) from a metrics file's prompt_cache_ lines, or (None, why)."""
    if not os.path.exists(path):
        return None, f"{path} is missing"
    values = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = GAUGE.match(line.strip())
                if m:
                    values[m.group(1)] = float(m.group(2))
    except OSError as exc:
        return None, f"{path} is not readable ({type(exc).__name__})"
    return values, None


def cache_block(d):
    """(lines,): the prompt cache's gauges the queue kept around each run and each arm's budget against the replay's, a report and nothing more."""
    out = ["== CACHE: the prompt cache's own gauges around each run (report only: no verdict, no exit code)"]
    readings = {}
    for arm in ("ce-A", "ce-B"):
        for when in ("before", "after"):
            values, err = gauges(os.path.join(d, arm, f"metrics-{when}.txt"))
            if err:
                out.append(f"{arm} metrics-{when}.txt is missing" if "is missing" in err else f"{arm} metrics-{when}.txt: {err}")
                continue
            readings[(arm, when)] = values
            missing = [n for n in CACHE_NAMES if n not in values]
            if missing:
                out.append(f"{arm} metrics-{when}: " + ", ".join(f"{n} is missing" for n in missing))
                continue
            out.append(f"{arm} metrics-{when}: budget {values['prompt_cache_budget_bytes']:.0f}, "
                       f"minimum state {values['prompt_cache_minimum_state_bytes']:.0f}, "
                       f"states {values['prompt_cache_states']:.0f}, "
                       f"bytes {values['prompt_cache_bytes']:.0f} (states plus spare buffers, not occupancy)")
    for arm in ("ce-A", "ce-B"):
        for when in ("before", "after"):
            values = readings.get((arm, when)) or {}
            if "prompt_cache_budget_bytes" in values:
                budget = values["prompt_cache_budget_bytes"]
                out.append(f"budget: the replay assumed {PREDICTION_BUDGET} B; {arm}'s gauge ({when}) reads {budget:.0f} B: "
                           + ("equal" if budget == PREDICTION_BUDGET else "different"))
                break
        else:
            out.append(f"budget: {arm} has no prompt_cache_budget_bytes gauge to compare with the replay's {PREDICTION_BUDGET} B")
    return out


# ---------------------------------------------------------------- P5

def conversation_rebuilt(rep, c):
    rows = [r for r in (rep.get("rows") or []) if r.get("kind") == "agent" and r.get("conversation") == c]
    return rebuilt_rows(rows) if rows else None


def p5(a, b, r):
    """(lines,) only: the replay agreement is a report."""
    out = ["== P5 REPLAY AGREEMENT (report only: no verdict, no exit code)"]
    if r is None:
        out.append("measured R: not available, so it cannot be placed against the simulation's 44% to 50%")
    else:
        low, high = PREDICTED
        where = "within" if low <= r <= high else "below" if r < low else "above"
        out.append(f"measured R {pct(r)} against the simulation's predicted 44% to 50%: {where}")
    convs = sorted({rr.get("conversation") for rr in (a.get("rows") or []) if rr.get("kind") == "agent" and integer(rr.get("conversation"))})
    out.append(f"per-conversation rebuilt rows, A and B ({len(convs)} conversation(s)):")
    for c in convs:
        ca, cb = conversation_rebuilt(a, c), conversation_rebuilt(b, c)
        out.append(f"  conversation {c}: A {ca!r}, B {cb!r}")
    rounds = sorted({rr.get("round") for rr in (a.get("rows") or []) if integer(rr.get("round"))})
    if not rounds:
        out.append("per-round totals: no rounds in A's rows")
        return out
    total_rounds = rounds[-1] + 1
    for upto in range(4, total_rounds + 1, 4):
        ta = rebuilt_rows([rr for rr in (a.get("rows") or []) if integer(rr.get("round")) and rr["round"] < upto])
        tb = rebuilt_rows([rr for rr in (b.get("rows") or []) if integer(rr.get("round")) and rr["round"] < upto])
        if ta and tb is not None:
            out.append(f"  rounds 1 to {upto}: A {ta}, B {tb}, R {pct(Fraction(ta - tb, ta))}")
        else:
            out.append(f"  rounds 1 to {upto}: A {ta!r}, B {tb!r}")
    return out


# ---------------------------------------------------------------- report and exit code

def verdict(p0ok, p1state, p2state, r, p4state):
    """(word, reason): the combined P0-P4 verdict, with the clause that decided it."""
    if not p0ok:
        return "NOT DECIDED", "P0"
    if p1state is False:
        return "FAILS", "P1"
    if p1state is None:
        return "NOT DECIDED", "P1"
    if p2state is not True:
        return "NOT DECIDED", "P2"
    if r is None:
        return "NOT DECIDED", "P3"
    if r < 0:
        return "FAILS", "P3"
    if r < GAIN:
        return "NEUTRAL", "P3"
    if p4state is None:
        return "NOT DECIDED", "P4"
    if p4state is False:
        return "NEUTRAL", "P4"
    return "HOLDS", None


def report(d):
    """(lines, states, failed): the whole report; failed only when P1 finds a difference."""
    a, ea = load(os.path.join(d, "ce-A", "trace.json"))
    b, eb = load(os.path.join(d, "ce-B", "trace.json"))
    cmp, ecmp = load(os.path.join(d, "compare.json"))
    lines = [f"== score98: {d} (ce-A/trace.json, ce-B/trace.json, compare.json)"]
    missing = [e for e in (ea, eb, ecmp) if e]
    if missing:
        lines.append("MISSING: " + "; ".join(missing))
    l0, p0ok = p0(a, ea, b, eb)
    if ea or eb:
        l1 = ["== P1 EXACT: not run", "P1 EXACT: NOT DECIDED: a trace is missing, so there are no two arms to compare"]
        if ecmp:
            l1.append(f"P1 EXACT: and {ecmp}")
        p1state = None
    else:
        l1, p1state = p1(a, b, cmp or {}, ecmp)
    l2, p2state, share = p2(a or {})
    l3, r, ra, rb = p3(a or {}, b or {}, cmp or {}) if not (ea or eb) else (["== P3 GAIN: not run", "P3 GAIN: NOT DECIDED: a trace is missing"], None, None, None)
    l4, p4state, delta = p4(a or {}, b or {}, cmp or {}) if not (ea or eb) else (["== P4 TIME: not run", "P4 TIME: NOT DECIDED: a trace is missing"], None, None)
    lc = cache_block(d)
    l5 = p5(a or {}, b or {}, r)
    word, reason = verdict(p0ok, p1state, p2state, r, p4state)
    detail = []
    if reason == "P0":
        detail.append("a trace is missing, unreadable or not qualified")
    elif reason == "P1":
        detail.append("the replies are not provably equal across the arms")
    elif reason == "P2":
        detail.append("A's cache never overflowed, so the policy had nothing to choose" if p2state is False else "the vacuity test did not decide")
    elif reason == "P3":
        detail.append(f"R {pct(r)} is below 0" if r is not None and r < 0 else f"R {pct(r)} is in 0 <= R < {float(GAIN):.0%}" if r is not None else "R is not measurable")
    elif reason == "P4":
        detail.append(f"the TTFT sum is {float(delta):+.2%} in B, over the +{float(SLOW):.2%} allowance" if delta is not None
                      else "an arm's TTFT sum is not available")
    if word == "HOLDS":
        detail.append(f"R {pct(r)} >= {float(GAIN):.0%} and the TTFT sum is within +{float(SLOW):.2%}")
    lines += l0 + l1 + l2 + l3 + l4 + lc + l5
    lines.append(f"VERDICT: {word}" + (f" ({reason}: {'; '.join(detail)})" if reason else f" ({'; '.join(detail)})"))
    states = {"P0": p0ok, "P1": p1state, "P2": p2state, "P2_share": share, "P3_R": r, "P3_A": ra, "P3_B": rb,
              "P4": p4state, "P4_delta": delta, "verdict": word, "reason": reason}
    return lines, states, p1state is False


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default="work/pp98/f98-c", help="queue98's f98-c (default work/pp98/f98-c)")
    args = ap.parse_args(argv)
    lines, _, failed = report(args.dir)
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
