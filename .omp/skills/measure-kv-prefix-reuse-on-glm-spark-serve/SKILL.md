---
name: measure-kv-prefix-reuse-on-glm-spark-serve
description: Use when measuring KV/prefix-cache reuse or cold-prefill cost on the TensorFold GLM spark serve; skips contaminated arms and reports wall time as the metric.
---

# Measure KV prefix reuse on the GLM spark serve

Goal: find out what a prompt change actually costs, without contaminating the measurement with other traffic

## Preconditions
- Serve reachable at `127.0.0.1:8888` on the spark (run the script ON the box). Model id from `/v1/models` (e.g. `GLM-5.3-Flash-EXL3`).
- Know that `~/.omp/agent/WATCHDOG.yml` routes the GLM turn reviewer to `ots-glm/glm-53-flash-exl3`, so the owner's session and its advisors keep hitting the serve. Every arm must therefore verify its own provenance.

## Procedure
1. Write a script that, per arm: reads `/health` (`requests_total`, `prompt_tokens_total`, `cached_tokens_total`), sends ONE chat completion with `max_tokens` 6-8 and `chat_template_kwargs {"thinking": false}`, then reads `/health` again.
2. **Provenance filter (mandatory):** accept the arm only when `requests_total` rose by EXACTLY 1 and the prompt delta matches the arm's own size (measure that size once first; an ~130k-char digit-heavy filler is ~64-67k tokens, not chars/4). Retry with a FRESH prefix (new nonce per line) - never reuse a prefix a discarded attempt already sent, or the retry will hit its own state.
3. Arms: (a) prime fresh prefix; (b) same messages, changed final user message; (c) insert one line at N% of the prefix; (d) insert N tokens from the end.
4. Report **wall time** as the metric. `prompt_tokens_total` is not "tokens sent" in every case and `kv_tier_load_s` is cumulative, so treat counters as indicative.

## What the results look like on this serve (2026-10-29)
- Append at a message boundary: ~0.3 s, 100% cached. Edit inside content: 0% cached, full prefill (25 s for 65k at ~2.6k tok/s), even 64 tokens from the end. Editing a middle message reuses only the system block (~33% of a 6-message prompt).
- So a checkpoint saves only the prefix before an edit; head edits (compaction) gain nothing from checkpoints.

## Gotchas
- `tcpdump -A` captures are too fragmented for body diffs, and `posts.log` counts are inflated per interface.
- A single-pass run with `requests_total` deltas around the WHOLE run is cleaner than per-arm retries when traffic is sparse.
