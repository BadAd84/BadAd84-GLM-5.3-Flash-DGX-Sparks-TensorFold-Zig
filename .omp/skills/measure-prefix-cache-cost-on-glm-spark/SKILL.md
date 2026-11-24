---
name: measure-prefix-cache-cost-on-glm-spark
description: "Measure and interpret GLM-5.3-Flash prompt-cache hits and cold-prefill cost on the OTS spark serve (kept-state granularity, /health counter traps); use for warm-session re-prefills, cold events, prefix-change cost, or chunked-checkpoint design questions."
---

# Measure prefix-cache cost on the GLM Spark serve

Use when a session is accused of "re-prefilling", when cold prefills need a cause, or when someone asks to
"chunk the cache" so a prompt need not match in full.

## What the engine actually reuses

- Reuse unit is a **kept state**: a whole-conversation snapshot with a line/fork/branch bookkeeping
  (OTS patches 0117 fork-point-shared, 0126 kept-branch-point, 0120 unsalted text states). There is NO
  vLLM-style chained 8k-block hashing. The boot line `states of 8192+ tokens` is a MINIMUM state size.
- A prompt that is a prefix of a kept state (or the reverse) resumes from it; otherwise the divergence point
  costs a prefill from there. Mid-prompt edits therefore cost nearly the whole prompt in practice.
- The tier (`TF_GLM_KV_TIER_GIB`, `/cache/kvtier/...`) stores whole states too: it rescues restart/resume and
  eviction, never a changed prefix.

## Procedure (three-arm, then position sweep)

1. Pick the model id from `/v1/models` (production: `GLM-5.3-Flash-EXL3`). Send thinking off:
   `chat_template_kwargs: {thinking: False}`, `temperature: 0`, `max_tokens: 8`.
2. Build a unique ~250k-token filler prefix (digits/punctuation tokenize near 1 token/char, so 260k chars
   is ~248k tokens). Direct HTTP to `127.0.0.1:8888` on spark1, no agent layer.
3. Arms: (A) fresh prefix, (B) same prefix + new user turn, (C) same prefix with ONE sentence inserted at
   5/25/50/75%. Time each request; read `/health` deltas around each.
4. **Trust WALL TIME.** `/health`'s `prompt_tokens_total` is not the incoming prompt length (measured 248k
   for a prime vs 96k for an identical-length insert prompt), so its cached column is indicative only.

Reference numbers (2026-10-29, ~248k prompt): fresh 37.4 s; identical repeat 0.2 s at 100% cached; insert at
25% 37.1 s, 50% 28.3 s, 75% 19.7 s. Prompt throughput ~6.6k tok/s, so 675k tokens ~ 4 min.

## Traps

- Leftover states from an earlier test contaminate the next (the prime reported 61% cached). Use a fresh
  nonce per line for any conclusive run.
- Do not claim "blocks" or "partial reuse before the change" from one arm; sweep positions.
- The sampler `warm.tsv` columns are CUMULATIVE totals: differencing successive rows is required to get
  per-request prompt/cached deltas (comparing the columns directly once produced a bogus "zero colds").
- `warmwatch.log` can be truncated when the sampler is restarted in another container; count colds from the
  TSV deltas, not from `grep COLD`.

## Reading the result for the owner

A cold's cost is roughly `tokens_after_the_change / prompt_throughput`. The fix with real upside is writing
checkpoint states every ~32k tokens to RAM and the NVMe tier so a mid-prompt change resumes from the last
checkpoint; measure any such change with this same sweep.
