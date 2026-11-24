---
name: measure-prefix-cache-cost-with-controlled-arms
description: "Use when a local LLM serve shows 'warm sessions re-prefilling' or high cold-prefill latency; proves whether the client or the cache is at fault."
---

# Measure whether cold prefills come from the client or the cache

## When
A served model (vLLM / TensorFold / llama.cpp / anything OpenAI-compatible) is reported as "warm sessions keep re-prefilling" or "context is not caching": long prompts intermittently pay a full prefill. Before touching the cache tier, memory pool, or eviction policy, measure which side causes the miss.

## Procedure
1. Craft one large reference prefix (e.g. 60-160k tokens, ~4 chars/token) with a nonce so it is not already in the cache.
2. Send three requests DIRECTLY to the API (no agent/harness layer), reading the server's own counters around each (e.g. `/health` `prompt_tokens_total` / `cached_tokens_total`, or the server's cache-hit metric), and also record wall time:
   - **A**: fresh prefix + short question - expect full prefill, `cached +0`.
   - **B**: identical prefix, different final user message - expect ~100% cached and a sub-second wall time.
   - **C**: same prefix with ONE sentence inserted near the FRONT (5% in) - expect `cached +0` again and a full prefill.
3. Compute prefill throughput from arm A (prefix tokens / wall time) so cold events of any size can be predicted: cold seconds ~= tokens / throughput.

## Reading the result
- **B cached, C not** = the cache is correct and the CLIENT is changing the prompt early. The fix is client-side: append-only prompt assembly (stable system prompt, append tool results, never reorder or edit earlier messages, no top-of-prompt timestamps), or a per-session cache namespace (e.g. a `cache_salt` field) so concurrent sessions do not thrash one prefix.
- **B not cached either** = a genuine serving-side problem (prefix cache not enabled/misconfigured, tier read path down, pool/slot rotation). Then check tier loads, pool size, and whether states are keyed per slot.

## Gotchas
- Read the server's counters, not a packet capture: `tcpdump -i any` sees each stream on more than one interface, so request/header counts inflate by several times.
- A string searched in captured bodies (e.g. `cache_salt`) may be the WORD inside prompt text rather than an API field - check whether the parser/server treats it as a parameter.
- Sampler TSVs often store CUMULATIVE totals; difference consecutive rows before calling anything a delta, or you will "verify" zero events.
- Keep arms interleaved and identical in max_tokens/temperature/thinking, or the comparison measures something else.
