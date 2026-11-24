---
name: measure-tensorfold-prefix-reuse
description: "Measure KV prefix reuse on the OTS TensorFold GLM serve (spark1-3): clean-arm harness, contamination traps, and the measured baseline behaviour."
---

# Measuring KV prefix reuse on our TensorFold GLM serve

Use when asked whether a prompt change re-prefills, when a serve shows "warm sessions re-prefilling", or before
proposing any cache/chunking change. Serve: spark1-3, `:8888`, model id from `/v1/models` (`GLM-5.3-Flash-EXL3`).

## What the serve does (measured 2026-10-29, v110)

- Reuse happens ONLY for an exact-prefix state match (append a new user turn: 0.2-0.3 s, cached 100%) and for the
  shared SYSTEM prefix (patch 0117).
- An edit inside content costs a FULL prefill wherever it lands: 0% cached for one inserted line at 25/50/75% and even
  64 tokens from the end of a ~65k prompt. Editing message 4 of a 6-message chat reused only the system block.
- Prefill ~2.6k tokens/s (65k = 25 s; 1M ~ 6.4 min). Tier restore is ~0.3-0.5 s per 226k-1.27M tokens.

## Procedure (clean arms only)

1. Build a FRESH unique prefix per attempt (a nonce in every line, ~130k chars ~ 65k tokens for this text style).
2. Snapshot `/health` before and after each request; accept the arm only if `requests_total` rose by EXACTLY 1 and
   `prompt_tokens_total` delta matches that arm's own prompt size (~64-67k for the above).
3. Arms: prime (fresh prefix); append (same messages, new final user turn); edit (one line inserted at a position, or
   one message's content changed).
4. Report wall time as the metric. `prompt_tokens_total` is not "tokens sent", and `kv_tier_load_s` is cumulative.

## Traps that invalidated real sweeps

- **Retrying a discarded arm poisons it**: the discarded attempt already created the state, so the retry reads 100%
  cached and proves nothing. Retry with a NEW nonce, not the same prompt.
- **Foreign traffic**: the `GLM turn reviewer` advisor routes to `ots-glm/glm-53-flash-exl3` (this serve), and the
  agent's own main calls land in `/health` windows; that produced a false "partial reuse" reading. The repo rule
  applies: count `requests_total` per arm, discard and redo contaminated ones (or firewall `:8888` with `~/fw8888.sh`).
- **`tcpdump -i any` capture** (`pwcap`) duplicates streams per interface and splits bodies, so its line counts are
  not request counts and it is not usable for body diffs.
- Do not conclude "the fleet is idle" from low request counts: one session plus its advisors is continuous traffic.

## Files

Harnesses live in the session scratch and are recorded in `docs/notes/overnight-watch-2026-10-26.md`
(`arm_b_verify.py`, `tail_window_test.py`, `sweep_filtered.py`, `msg_boundary_test.py`).
