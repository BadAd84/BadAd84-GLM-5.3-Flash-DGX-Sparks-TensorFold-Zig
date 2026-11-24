---
name: diagnose-stream-drift-in-shared-window-serves
description: "A shared-window LLM serve (GLM/TensorFold style) lags a reference stack at 4-8 concurrent streams: decide whether the limit is admission budget, per-row cost, or stream drift/tail straggling before proposing a fix"
---

# Diagnosing a high-concurrency serve gap: budget, per-row cost, or drift

Use when our serve's aggregate throughput lags production at 4-8 streams and the round/rows
hypotheses are still guesses. Measured on ai-engine GLM TP=3, 2026-11-03.

## 1. Compute effective streams first (one line, decisive)

`effective = agg_tok_s / per_stream_tok_s` from the same cell.

- equal to the stream count: all streams are decoding together; a gap is per-round work.
- BELOW it: the streams drifted and finished raggedly, so the aggregate
  (`tokens / first-send..last-finish`) counts fewer streams than were sent. Ours read 5.6 of 8
  where production read 8.0, and its round time was already at parity - the whole gap was drift.

Do NOT go on to admission/cost-model work while this number is short.

## 2. Separate budget from per-row cost (from existing cells, no new boots)

From a probe cell take `tok_per_round` and per-stream rate; `ms_per_round = tok_per_round /
per_stream * 1000`. Then cost a row = ms_per_round / tokens_per_round.

- Refuted here: filling every window to the depth cap (`TF_GLM_OVN_WIN_FREE=1`) measured LEVEL
  at 2/4/6/8 and left tokens/stream/round unchanged (5.66), because the drafter caps the tokens
  a round at its chain cut - the row budget was never binding.

## 3. Find out WHY the streams drift, in the allocator

Our `allocateDrafts` was one global greedy on tokens/ms across ALL streams: with three streams
and six spare rows it gives 6/0/0 (a confident stream takes everything, an unconfident one takes
none), so starved streams fall behind every round. A host test pins it in miniature; write that
test before touching the policy.

Fix shape: a fair quota - each spare row to the shallowest stream, ties to the likelier node
(`TF_GLM_OVN_WIN_FAIR=1`). Note a free-fill knob alone cannot fix drift: it keeps the greedy
order and only raises the cap, which is why it measured level.

## 4. Instrument the tail, do not infer it

Add per-stream finish times and `spread_s = max(last) - min(first)` to the stream client next to
`per_stream` (we added both to `~/glmrepro/streams.py`), then run 8 distinct prompts and read the
spread. Validate an edited client by running it against a dead port: the failure must be the
network one, never a silent zero.

## 5. A/B discipline for this class

- Both arms on the SAME image; the candidate is the sixth argument of `pp-chain-ab.sh`
  (`IMAGE TAG WAITLOG WAITPAT A_XENV B_XENV`) - passing one env string silently labels the
  CONTROL arm as the candidate. Check `grep 'pp-chain-ab' <chain>.sh` after writing it.
- Verify the env reaches every rank (`serve4.sh` pushes `XENV` to each box; a knob that stops at
  rank 0 shows up as an illegal address or unchanged behaviour on the first prompt only).
- Expect the fair arm's signature to be a RISE in aggregate at 4-8 with tokens/round nearly
  unchanged; a tokens/round rise instead means the chain rule moved, not fairness.
