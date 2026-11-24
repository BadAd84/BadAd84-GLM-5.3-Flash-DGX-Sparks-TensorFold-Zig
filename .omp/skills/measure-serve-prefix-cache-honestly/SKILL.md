---
name: measure-serve-prefix-cache-honestly
description: "Measure prefix-cache reuse on a live LLM serve (vLLM/TensorFold/llama.cpp) without contaminated arms: provenance filtering, fresh prefixes, correct expectations"
---

# Measuring prefix-cache reuse on a live serve

Use when a served model "re-prefills warm sessions", when deciding whether a cache/tier change helps, or when
quoting a prefill cost. The pitfalls below each produced a WRONG number in a real campaign (2026-10-29, our GLM
serve), so run the checks mechanically.

## Contract: what to expect before measuring

Most production engines reuse **exact prefixes only**: the incoming prompt must START with a stored state's rows
(kept state / block chain root). Consequences to predict in the arms:

- append a user turn -> ~100% cached, near-zero wall time
- edit/insert/reorder ANYWHERE in the prompt -> **0% cached, full prefill** (measured at 25%, 50% and 75% of a
  65k prompt: every one cost the whole prefill). Do not assume block-level partial reuse; measure it.
- truncation (compaction) -> also a full miss, because the result is a suffix, not a prefix.

## Harness shape

1. Build a **unique** prefix per attempt (nonce in every line): leftovers from an earlier attempt otherwise
   silently serve the arm and report 100% cached.
2. Arms: prime (fresh), append (control), then one change per arm at 25/50/75%.
3. Report wall time as the metric; counters are secondary (see below).

## Provenance filtering (the rule that saves the measurement)

- Snapshot `/health` before and after each request and require `requests_total` delta == **1**.
- Also require the prompt-token delta to match that arm's own prompt size (~5% tolerance). A large delta means a
  foreign request (another agent, an advisor, the session's own model calls) landed inside the window.
- **NEVER retry a contaminated arm with the same prefix**: the discarded attempt already prefilled it and created a
  state, so the retry reports 100% cached and 0.2 s. Use a FRESH prefix per attempt instead.
- If you cannot silence other clients, keep retrying with fresh prefixes until one attempt is clean, and report only
  clean arms (state how many were discarded).

## Counter semantics to pin before quoting anything

- `prompt_tokens_total` may be prefill-only, or may include cache hits; verify with a known-size prompt.
- A tier/cache may expose its own timings (e.g. `kv_tier_load_s`, `kv_tier_load_copy_s`): prefer those over
  inference. They are the cheapest honest measurement of restore cost.

## Report

Give the wall-time table with the clean/discarded counts, and state which levers exist (append-only prompts, NVMe
restore, compaction that drops the middle rather than rewriting the head). Do not present a contaminated arm.
