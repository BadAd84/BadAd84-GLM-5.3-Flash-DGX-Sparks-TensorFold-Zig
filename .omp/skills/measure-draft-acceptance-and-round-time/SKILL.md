---
name: measure-draft-acceptance-and-round-time
description: "Measure spec-decoding acceptance, tokens/round and per-round latency on a TensorFold serve (GLM/Qwen/DSV4.1 OTS repos); also how to read the engine's TF_GLM_PROF profilers without falling for their print strides"
---

# Measure draft acceptance and round time on a TensorFold serve

Use when asked about draft/speculative performance, tokens per round, ms per round, or why a drafter's speedup is thin, on any OTS serve repo (GLM-5.3 Zig, Qwen3.8 Zig, DeepSeek-V4.1 Zig).

## The counters

The server exposes on `/metrics`, as counters over FINISHED requests (so a before/after pair around one wave of concurrent requests is that wave's own record):

- `tensorfold:mtp_drafted_total` - draft tokens verified
- `tensorfold:mtp_accepted_total` - draft tokens kept
- `tensorfold:decode_rounds_total` - decode rounds used

The `tensorfold:` prefix is emitted by metrics.zig (`const prefix = "tensorfold:"`); a parser matching bare names finds nothing and reports all-null. Strip the namespace before matching, and return None (never 0) when a counter is absent or resets, so a serve without counters cannot report a fabricated 0% acceptance.

Derived per wave: `acceptance = d_accepted / d_drafted`, `tok_per_round = (completion_tokens - 1 summed) / d_rounds`, `ms_per_round = span_s * 1e3 / d_rounds`.

## The harnesses

Each repo carries one, stdlib-only, plus unittest suites whose end-to-end case runs against a fake HTTP serve scripting the counters:

- GLM Zig: `scripts/streams.py` (+ `scripts/tests/test_streams_accounting.py`)
- Qwen Zig: `scripts/qwen38/zig/bench/draft_accounting.py` (+ `tests/test_draft_accounting.py`)
- DSV4.1 Zig: `scripts/harness/draft_accounting.py` (+ `tests/test_draft_accounting.py`)

Run: `streams.py PORT N --kind prose --max-tokens 400 --rounds 3 --tag X --out rows.jsonl` with the serve up; rows carry agg/decode tok/s, TTFT, tokens, sha plus draft_rounds/drafted/accepted/acceptance/ms_per_round/tok_per_round.

A healthy GLM-5.3-Flash EXL3 TP=3 reading: acceptance 0.596, tok/round 2.68, ms/round 52.3 (identical across rounds). At 2.68 tok/round, 51 tok/s means a 52 ms round; a 83 tok/s Python serve implies ~32 ms, so the gap is per-round latency, not drafting - chase decode-path kernels/knobs, not the drafter.

## Reading the profilers without being fooled

- `TF_GLM_PROF=1` profiles only PROMPT chunks: `glm prof prompt chunk to N rows (calls): wall/gpu; gate embed kda mla gather_a dense router routed shared gather_b head draw mtp commit`.
- Verify/decode rounds use `e.profs[ids.len - 1]`, labels `verify N rows`, but they PRINT only every `every` calls (default 64; prompt profs set 4) and only prompt profilers print at deinit. A cell with fewer than 64 decode rounds prints nothing - take `--max-tokens` around 300 to cross the stride.
- Shared multi-stream rounds: `TF_GLM_OVN_SHARED_PROF=1`, labels `shared N segs to M rows` / `shared commit N segs`; they need a genuinely shared round, so a one-stream test shows nothing.

## Bench discipline

Fresh boot per level, `DRAFTER` fixed across arms, digests as the correctness gate (same sha at every level means bit-exact). Adopt the owner's order when evaluating patches or env: clean pin, then env batches, then patch blocks, each judged by no regression at 1/2/4/6/8 plus equal digests.
