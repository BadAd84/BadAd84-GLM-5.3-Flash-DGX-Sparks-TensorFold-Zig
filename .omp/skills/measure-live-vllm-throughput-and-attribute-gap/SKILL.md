---
name: measure-live-vllm-throughput-and-attribute-gap
description: "Measure the LIVE tokens/s of a running vLLM serve (e.g. the OTS GLM-5.3-Flash serve on spark1:8888) from Prometheus counters without synthetic load, and attribute any gap to the documented benchmark by decomposing tok/s into steps/s x tokens/step."
---

# Measure live vLLM throughput and attribute the gap to benchmark

Use when asked "what t/s are we getting" on a running serve — especially when the instruction is to monitor the CURRENTLY PROCESSING task rather than send a benchmark workload. Applies to the OTS GLM-5.3-Flash-EXL3 serve (spark1:8888, TP=3) but generalises to any vLLM + speculative-decoding deployment.

## Golden rule
Measure the LIVE rate from the Prometheus counters of the real in-flight requests. Do NOT run a synthetic benchmark when the user wants the live task measured. A synthetic bench answers a different question.

## Connect
```
export SSH_AUTH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg
ssh adam@spark1.ots-int.net
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8888/health
docker ps --format '{{.Names}}\t{{.Status}}'
```

## Sample the counters (deltas over an interval)
`curl -s http://127.0.0.1:8888/metrics` twice, N seconds apart, and take deltas:

| quantity | counter | formula |
|---|---|---|
| live decode rate | `vllm:generation_tokens_total` | delta / interval = **tok/s** |
| engine step rate | `vllm:spec_decode_num_drafts_total` | delta / interval = **steps/s** |
| tokens per step | - | dgen / ddrafts |
| draft acceptance | `spec_decode_num_accepted_tokens_total` / `spec_decode_num_draft_tokens_total` | ratio |
| pressure | `vllm:num_requests_running`, `vllm:kv_cache_usage_perc` | direct |
| context shape | `vllm:request_prompt_tokens_sum` / `_count` | mean prompt length |

Sample in a loop (5 s cadence, ~60 s) and read the STEADY-STATE window — request boundaries show up as transient steps/s dips and kv% -> 0 (prefill).

## The decomposition that answers "why"
```
tok/s = steps/s  x  tokens/step
```
Compare `steps/s` with the benchmark's IMPLIED step rate:
`benchmark_tok_s / benchmark_tokens_per_step`.

- **steps/s MATCHES** -> the engine is fine. The gap is purely speculative acceptance, i.e. content-dependent drafting. NOT throttling, NOT KV pressure, NOT context-length cost.
- **steps/s is LOWER** -> a real regression. Check config drift, thermals, external contention, numerics.

Worked example (2026-09-21): doc structured bench 78.5 tok/s @ 6.71 tok/step = 11.7 steps/s. Live 28 tok/s @ 2.4 tok/step = 11.7 steps/s. Identical step rate -> gap is entirely acceptance (41% live vs 96% bench).

## Per-position acceptance ("how far does the drafter reach")
`vllm:spec_decode_num_accepted_tokens_per_pos_total{position="N"}` is cumulative — normalise against position 0. Measured live: pos0 1.0, pos1 0.68, pos2 0.34, pos3 0.23, pos4 0.04, pos5 0.03, pos6 0.02 — the drafter reliably nails ~2-3 tokens then collapses, which is why adaptive-k shortens the verify length.

## Rule out config drift (before blaming content)
```
docker inspect <container> --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E "FAST|COOP|APC_RETENTION|ADAPTIVE_K|DFLASH|MAX_NUM_SEQS"
```
Compare against the keeper doc `glm5.3-flash-dev/docs/GLM53-FLASH-PRODUCTION-STACK.md`. Keeper values: `GLM53_EXL3_MOE_FAST=1`, coop geometry empty (coop OFF), `VLLM_PREFIX_CACHE_RETENTION_INTERVAL_SWA=0`, `GLM53_ADAPTIVE_K=ema`, `GLM53_ADAPTIVE_K_SET=2,4,7`, `DFLASH_TOKENS=7`, `MAX_NUM_SEQS=4`, `GPU_MEM_UTIL=0.85`.

## Gotchas (measured)
- The step counter is `vllm:spec_decode_num_drafts_total`. `position` is a LABEL only on `accepted_tokens_per_pos_total` — do not look for a per-position drafts metric.
- `vllm:time_per_output_token_seconds*` DOES NOT EXIST on this build. Don't rely on it for latency.
- Drafted tokens per draft is ~3.6, NOT `DFLASH_TOKENS=7` — adaptive-k caps the verify length. Don't assume 7.
- First structured run after boot can cold-JIT down to ~9 tok/s; read min/max before claiming a delta.
- The doc's acceptance diagnostic (accept ~0.96 = clean path; ~0.8x structured = numerics perturbed, which was coop-v2's tell) is only valid on the SAME benchmark prompt. Low acceptance on DIFFERENT content is expected and is NOT evidence of a fault — which is exactly why the steps/s decomposition above is the correct discriminator.

## Health signals to report alongside the rate
prefix-cache hit rate (`prefix_cache_hits_total`/`queries_total`), `num_preemptions_total`, kv%, requests running/waiting, container uptime.
