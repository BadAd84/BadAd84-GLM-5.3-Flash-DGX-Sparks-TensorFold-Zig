---
name: attribute-serving-concurrency-gap-to-stream-drift
description: "Serving serve close at 1-2 streams but far behind at 4-8: attribute the gap to stream drift vs row budget before changing allocations."
---

# Attributing a serving concurrency gap (drift, not rows)

Use when a shared-window LLM serve (TensorFold/ai-engine/production-style) is close at 1-2 streams but far behind a
reference at 4-8 streams, and you are about to "just allow more rows". Measured on ai-engine GLM TP=3 (2026-11-03):
the row-budget theory cost a full 20-cell A/B and was refuted; the gap was stream drift, and one afternoon of
arithmetic found it.

## 1. Do the three-number arithmetic FIRST (from cells you already have)

For each level take the probe's own numbers: aggregate tok/s, per-stream tok/s, tokens a stream a round.

- `round_ms = tokens_per_round / per_stream_tok_s * 1000`  (both are per stream over the same rounds)
- `effective_streams = agg_tok_s / per_stream_tok_s`

Diagnosis table:

| round_ms vs reference | effective_streams vs stream count | conclusion |
|---|---|---|
| higher | equal | the round itself is slow: per-row or per-stage cost |
| equal | LOWER (e.g. 5.6 of 8) | the streams DRIFT: they finish raggedly and the tail runs alone |
| equal | equal but fewer tokens a round | the drafter/chain policy caps tokens a round |

Do not skip this: "more rows" can be level (it was) while "fewer finishing streams" explains the whole gap.

## 2. If it is drift, instrument the spread

Patch the stream client to emit per-stream finish times and the spread beside the aggregate:
`"per_stream_finish_s": [round(s["last"] - min(first), 3) ...]`, `"spread_s": last_finish - first_send`.
Validate by running the edited client against a DEAD port: the failure must be the network one (Connection refused),
never a silent zero. A wider window (fewer rounds) is one arm; the fair allocation is the other.

## 3. Read the allocator before proposing a fairness fix

Shared-window allocators are often ONE global greedy ("tokens a millisecond" across every stream). That starves
streams: with three streams and six spare rows it gave 6 / 0 / 0. Prove it in a host test, then implement the fair
quota as a knob: each spare row goes to the SHALLOWEST stream (ties to the likelier node), the priced stop condition
and everything else unchanged, default off.

- Test the property, not the literal counts you expect: assert greedy spread >= 3 and fair spread <= 1, and that the
  totals are equal. (A hardcoded greedy expectation is your guess, not the code's contract; the counts are DRAFTS -
  the caller adds each stream's fixed row.)
- `WIN_FREE`-style "fill with no cost model" does NOT fix drift: it keeps the same greedy order, only with a bigger cap.
  Measure it to close that path rather than reasoning about it.

## 4. Correctness/risk to state in the write-up

- Slicing/fill gates that already exist (e.g. "only while another stream decodes") mean the knob's effect is
  conditional; read the call site before believing a mechanism.
- A per-rank plan built from rank-local cost tables is only safe while the ranks' inputs agree: the A/B's per-cell
  reply digests are the desync check, so require digest equality in the arm definition.

## 5. Report form

State round time, tokens a round, per-stream rate and effective streams side by side; the drift conclusion is only
credible when round time is shown to be at parity.
