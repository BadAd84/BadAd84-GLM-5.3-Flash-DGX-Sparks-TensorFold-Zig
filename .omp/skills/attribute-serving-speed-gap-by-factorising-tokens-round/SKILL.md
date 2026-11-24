---
name: attribute-serving-speed-gap-by-factorising-tokens-round
description: "When a served model is slower than a reference, factorise the gap into tokens-accepted-per-round x ms-per-round from real counters before optimising anything; also protects against profile-span unit errors."
---

# Attribute a serving speed gap before optimising

Use when one inference engine/serve is slower than another on the same model and hardware and you must decide WHERE to spend effort. Comparing tok/s alone hides which half of the system is behind.

## 1. Factorise, do not compare tok/s

    tok/s = (tokens accepted per round) / (ms per round)

Measure both sides on the SAME prompt set, same stream count, same moment (run them simultaneously if two serves exist).

- tokens per round: from server counters, never derived from tok/s alone.
- The two factors are independent levers with different fixes:
  - ms per round -> kernel/bandwidth/collective work
  - tokens per round -> drafter quality, draft window length, acceptance policy

Worked example (GLM-5.3-Flash, TP=3, P=1): production 3.02 tokens/round at 36.36 ms vs a new engine at 2.07 and 46.07 ms gave 1.45x x 1.27x = 1.84x against a measured 1.81x gap. The factorisation moved the work from kernels (no headroom) to the drafter.

## 2. Read the counters

Common counter sets:
- TensorFold Python `/health`: `rounds_total`, `drafted_total`, `accepted_total`, `completion_tokens_total`, `requests_total`.
- TensorFold native (Zig) JSON status: `decode_rounds_total`, `mtp_drafted_total`, `mtp_accepted_total`, `generation_tokens_total`.

Compute per round: drafted/round, accepted/round, accept% = accepted/drafted, tokens/round = tokens/rounds. Sanity check: tokens/round should be about accepted/round + 1 (the bonus token).

Get deltas around a fixed workload (e.g. N rounds x 400 tokens), not lifetime totals - foreign traffic (dashboards polling) pollutes absolute counters; a poll usually adds no completion tokens, so ratios stay usable but note it.

## 3. Guard against the profile-span error

Before computing ANY rate from a profiler row (ms, GiB/s, % of roofline), prove what the row's span covers: read the code that emits the mark AND the code that aggregates it. A mark emitted per layer and summed per forward makes one-layer bytes over all-layer time. Real case: this produced "2.5% of roofline, 2x headroom" when the true figure was 88-108% of roofline - a whole workstream aimed at headroom that did not exist.

Tells that span is wrong: bandwidth 10-40x off roofline; a stage whose share contradicts its known byte volume; two independent runs disagreeing by a large constant factor.

## 4. Then rank the levers by measured prize

For each factor, state the achievable change and its predicted effect on tok/s, e.g. "TP=3 sharding cuts per-rank expert bytes 3.85 -> 2.56 GiB, so the expert stage 18.2 -> 12.2 ms, ~1.5x on that stage" - and only then decide what to implement. Prefer the factor whose fix is a policy/wiring change over a kernel rewrite when both are available.

## 5. Report honestly

State the corrected numbers plainly, including retracting an earlier wrong figure and where it came from. A negative result ("no kernel headroom") is a result: record it so nobody re-opens the work.
