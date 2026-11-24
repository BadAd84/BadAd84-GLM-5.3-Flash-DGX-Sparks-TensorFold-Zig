---
name: qualify-a-tensorfold-prefill-reuse-change
description: "Measure or A/B a TensorFold GLM serve prefill/reuse change on spark1-3 while live sessions are using it (idle-gated ABBA, provenance filtering, restart detection, digests)."
---

# Qualifying a prefill or cache-reuse change on the GLM serve

Use when testing `TF_GLM_PREFILL_ROWS/FILL_ROWS`, a shared-prefix / checkpoint engine patch, or any claim of the form "this makes cold prefills faster or cheaper to resume" on production spark1-3. The box is usually serving omp sessions, so measurements must survive foreign traffic.

## Harness rules that decide whether a number means anything

1. **Detect the restart by the container, not by health.** `~/restart_when_idle.sh <label>` waits for idle, so `/health` can still answer 200 from the OLD serve for minutes. Capture `docker inspect glm53-flash-tf --format '{{.State.StartedAt}}'` before, poll until it CHANGES, then wait for 200. A health-gated probe that fires early measures a dead box (Errno 111) and wastes a boot.
2. **Gate every probe on an idle serve**: `/health` needs `decode_running == 0 and fill_running == 0 and requests_running == 0` before and after. A foreign 1M-token advisor prefill that started earlier adds no `requests_total` but still competes for the GPU.
3. **Provenance-filter**: accept a probe only when `requests_total` rose by exactly 1 and its `prompt_tokens_total` delta matches the prompt you sent. Do NOT retry a discarded arm with the same text - the discarded attempt already cached that prefix, so the retry reads 100% and looks like a win. Use a fresh nonce per attempt and prime it again.
4. **Take the min of 2+ clean probes per arm**, record `nvidia-smi --query-gpu=temperature.gpu` at each window and `pool_free` (a 5M-token pool is ~5 sends of 200k and then every probe pays evictions), and interleave ABBA (A, B, B, A) with a fresh boot per arm. Boot-to-boot variation has been as large as the effect being measured.
5. **Report a range, not a point.** If the arms' ranges overlap, the arm is NOT established, whatever the means say.
6. Digests: `~/firstreq.py 8888` for the reply digest (bit-exactness); note that changing `TF_GLM_PREFILL_ROWS` re-keys the NVMe tier folder, so an arm boot starts on a cold tier (reverting restores the old folder's points).

## Prefix / reuse probes

Direct HTTP to `http://127.0.0.1:8888` with `{"model": "GLM-5.3-Flash-EXL3", "chat_template_kwargs": {"thinking": false}, "max_tokens": 6, "temperature": 0}` and two messages. Build a unique filler (~2 chars/token for digit-heavy text, ~1 char/token for `r{i} v{...}` style), send it as the system message, then:

- **append arm**: same system, different final user message -> expect ~100% cached, sub-second.
- **edit arms**: insert one line at 25/50/75% and N tokens from the end -> expect cached +0 (any content edit costs the whole prompt; measure the wall time, not the rate only).
- **6-message chat**: prime system/user/assistant/user/assistant/user, then edit message 4 -> today only the system block is reused (~33%).

Compute `cached`/`prompt` from `/health` deltas around each request, never from a cumulative field (`warm.tsv` columns are cumulative too - difference consecutive rows).

## What has already been measured (reuse the numbers, do not re-derive)

Append 0.2-0.3 s at 100% cached; any content edit a full prefill (65k = 24-31 s); mid-chat edit reuses only the system block; prefill 2.5-2.6k tok/s; tier load ~0.5 s per load (`kv_tier_load_s` is cumulative); `PREFILL_ROWS` 8192 is NOT established and costs +3.04 GiB estimate; `INDEXER_SHARD=all` is prefill-neutral.

## Before proposing to ship

Only the owner accepts a trade, and the fleet rule applies: parallel 1/2/4/6/8, TTFT gate, digests, sparkDash stopped and `~/fw8888.sh on` for the qualification window (which breaks live advisor sessions for its duration - say so first). A lead measured under live traffic is not a verdict.
