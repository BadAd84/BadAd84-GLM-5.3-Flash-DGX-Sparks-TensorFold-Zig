---
name: fix-glm-53-flash-prefix-cache-hits
description: "Enable working prefix-cache hits on the MiaAI-Lab GLM-5.3-Flash-EXL3 2xDGX Spark deployment by applying PRs #83 (per-group retention) and #84 (fine-grained 64-token hits). Use when GLM's /metrics shows vllm:prefix_cache_queries_total incrementing normally but vllm:prefix_cache_hits_total staying at 0.0, or when warm re-turns don't get any speedup on identical prompts. 2026-09-18: retention (#83 equivalent) is now MERGED in main via #130 with changed env semantics; fine-grained hits (#84) remain local-only."
---

# Enable GLM-5.3-Flash-EXL3 prefix cache hits (MiaAI-Lab PR#83 + PR#84)

## STATUS 2026-09-18 (read first - main moved)

- **Per-group retention (#83's function) is MERGED in main via #130**, but the semantics CHANGED: on current main an EMPTY `GLM53_APC_RETENTION_INTERVAL_SWA` INHERITS the global retention interval instead of applying #83's automatic SWA rule. The checkout-pr-83 recipe below is for the OLD tree (~/glm53-flash-2spark era); on a current-main tree use main's #130 knob directly.
- **Fine-grained 64-token hits (#84 / #125) are NOT in main** and our rebase PR #195 was closed merge-hold ("keeping this local"). The overlay file `overlay/patch_apc_fine_grained_hits.py` remains a LOCAL-ONLY carry - copy it forward when moving trees, it is `[ -f ]`-guarded in `GLM53_OVERLAY_ORDER`.

Stock config from `boot-glm-53-flash-exl3-on-2x-dgx-sparks` skill applies
`patch_hybrid_prefix_hit.py` but that alone leaves you with **0.0 hits** on
`vllm:prefix_cache_hits_total` even though `vllm:prefix_cache_queries_total`
increments per query. Two upstream PRs on MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks
are needed to make cache actually deliver hits.

## The two failures without these patches

1. `[kv_cache_coordinator.py:635] Disabling fine-grained prefix-cache hits
   because these KV cache managers require block-aligned lookups:
   KpoolTailManager.` -> hits align to scheduler block (3584 tokens) not the
   64-token hash grid, so any warm re-turn re-prefills up to 3583 tokens.
2. Hybrid APC groups: `[('MLAAttentionSpec', [0], 'FullAttentionManager', False),
   ('MambaSpec', [2,3,4,5], 'MambaManager', False), ('SlidingWindowSpec', [6],
   'SlidingWindowManager', True)]` - only SWA hits are enabled at all. And the
   DFlash2 draft group there hashes `cdiv(2047, 64) + 1 = 33` block IDs per
   cached segment vs 1 for MLA + 4 for Mamba (~87% of a 642-id LRU pool). Two
   sessions of ~53K tokens each evict each other.

## Fix

Apply MiaAI-Lab PR#83 (per-group retention: sparse for drafter, dense for
target) plus optional PR#84 (fine-grained 64-token hits). Both live on PR
branches that don't merge cleanly with main (unrelated histories), so
**checkout PR#83 branch + copy PR#84's single overlay file** is cleanest.

### Steps (on spark1, in `/home/adam/glm53-flash-2spark/`)

1. Fetch both PR branches:
   ```
   git fetch origin refs/pull/83/head:pr-83 refs/pull/84/head:pr-84
   ```

2. Stop currently-running GLM containers (both nodes):
   ```
   docker stop glm53-exl3-head; ssh -o StrictHostKeyChecking=no adam@192.168.100.11 docker stop glm53-exl3-worker
   docker rm -f glm53-exl3-head;  ssh -o StrictHostKeyChecking=no adam@192.168.100.11 docker rm -f glm53-exl3-worker
   ```

3. Checkout PR#83 tree onto working dir (this includes updated start.sh with
   the launcher wiring for the SWA retention env var). Preserve current .env
   which is gitignored:
   ```
   cp .env /tmp/glm-env-backup
   git checkout pr-83 -- .
   cp /tmp/glm-env-backup .env
   ```

4. Copy PR#84's fine-grained overlay file on top (PR#83's start.sh has a slot
   for it in `GLM53_OVERLAY_ORDER` that's `[ -f ]`-guarded, so it's picked up
   if present):
   ```
   git show pr-84:overlay/patch_apc_fine_grained_hits.py > overlay/patch_apc_fine_grained_hits.py
   chmod +x overlay/patch_apc_per_group_retention.py overlay/patch_apc_fine_grained_hits.py
   ```

5. Add env vars to `.env` (SKIP_PULL=1 + SKIP_BUILD=1 should already be there
   per `boot-glm-53-flash-exl3-on-2x-dgx-sparks` skill):
   ```
   echo 'GLM53_APC_RETENTION_INTERVAL_SWA=0' >> .env
   echo 'GLM53_FINEGRAINED_APC=1' >> .env
   ```

6. Detached relaunch (never inline, start.sh blocks on rsync/build):
   ```
   mv /home/adam/glm53_start.log /home/adam/glm53_start.log.pre-apc 2>&1 || true
   cd /home/adam/glm53-flash-2spark && (nohup bash start.sh > /home/adam/glm53_start.log 2>&1 < /dev/null &)
   ```

## Verification

After ~10 min for full boot (image ship + shard load + engine init), confirm
from the log:

```
[glm53-exl3] drafter (SWA) prefix-cache retention interval: 0 (both ranks)
patched kv_cache_coordinator.py (per-group APC retention; VLLM_PREFIX_CACHE_RETENTION_INTERVAL_SWA drives the DFlash2 drafter group)
(EngineCore pid=NNN) INFO [kv_cache_coordinator.py:362] [glm53-apc-per-group] retention_by_group=[None,None,None,None,None,None,0] (global=None swa_env=0 eagle_min_exempt=[6])
```

The `retention_by_group=[None*6,0]` line is the definitive PR#83-applied
signature. `None` = dense global retention on MLA + Mamba groups, `0` = the
SWA drafter group at index 6 keeps only reachable-boundary tails.

With PR#84 also applied, additional log line:

```
[glm53-apc-finegrained] Fine-grained prefix-cache hits ENABLED
effective alignment=64 tokens (hash_block_size; scheduler_block_size=3584)
scratch groups checked: {'KpoolTailManager': 4}
```

## Measured effect (verified 2026-09-02 on our stack)

With PR#83 only (no PR#84):

| Fire (identical 12.9K-token prompt) | Wall | Prefill tok/s | Cache hits |
|---|---:|---:|---:|
| 1 (cold) | 29.9 s | 432 | 0 |
| 2 (warm) | 8.9 s | 1,445 | +7,168 |
| 3 (warm) | 3.6 s | 3,605 | +10,752 |

**3.35x cold vs warm speedup, 69.3% hit rate on repeated prompts.** With PR#84
also applied, the docs quote 99.95% cached across alternating 120K-token
conversations with 0.5s warm TTFT.

## Trade-offs vs PR#83-alone

PR#84 adds fine-grained hits but at cost of ~0.3 tokens/step drafter
acceptance loss on warm turns per @wdkr's benchmark in the PR discussion.
At temp 0 the generated text differs slightly from cold when only PR#84 is
engaged (target's fine-hit computation is not bit-identical to cold prefill).
For byte-exact RE precision use cases, prefer PR#83 alone; for interactive
general coding/RE workhorse, apply both.

## When to use vs skip

- Use always for multi-turn / agentic use of GLM as a general workhorse
  post-specialist-model (the model retains the general chit-chat / broad
  knowledge the specialist strips).
- Skip for pure Stage 2 distillation (one-shot solves, no reuse anyway - the
  patches don't help). Extra kernel warmup time not worth it for zero-reuse
  workload.

## Cross-refs

- `boot-glm-53-flash-exl3-on-2x-dgx-sparks` skill - the prerequisite boot
  playbook. Apply THIS skill on top after a clean boot works.
- Issue #54661 (nood-co1/Blockbrain Labs) - upstream vLLM RFC for the same fix.
- PR#83 https://github.com/MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks/pull/83
- PR#84 https://github.com/MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks/pull/84
- Our rebase PR#195 (closed merge-hold, kept local) + PR#196 (thin-decode, superseded by merged #217)
- MiaAI-Lab README section on 'What runs' documents the two knob names.
