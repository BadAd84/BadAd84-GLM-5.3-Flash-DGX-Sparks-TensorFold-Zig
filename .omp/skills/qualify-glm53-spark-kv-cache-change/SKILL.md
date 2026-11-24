---
name: qualify-glm53-spark-kv-cache-change
description: "Qualify any KV-cache / prefix-cache / NVMe-offload / scheduler change on the GLM-5.3-Flash 2x DGX Spark serve (port 8889) with the harnesses already on spark1 - cold/flood/restore protocol, byte-identical checks, restart-persistence check, 4-lane agent simulator - and the traps that fake a result (persistent-cache hits on reused prompts, zero connector counters, watchdog killing boots, pkill self-match)."
---

# Qualify a KV-cache / offload / scheduler change on the GLM-5.3-Flash Sparks

All harnesses live on spark1 (`ssh adam@spark1.ots-int.net`). Serve = `~/glm53-current`, port 8889, model id `glm-53-flash-exl3`. Boot via `~/arm_boot.sh <FAST 0|1> <coop|nocoop>` (edits .env, stops both nodes, mem-hygiene, boots, waits health).

## Before ANY manual boot
1. `systemctl --user stop glm-watchdog` - it kills a container mid graph-capture ("head container missing during startup"). Restart it when done.
2. Never `pkill -f <literal>` / `pgrep -f <literal>` from the ssh shell: the pattern is in your own command line and kills your session. Indirect it: `pat="kvoff_corr"; pgrep -f "${pat}ect.py"`.
3. Keep >40 GiB free on BOTH nodes: the NvmeDirect spec's `capacity_bytes` is a boot-time free-space gate. Delete dead `~/.cache/vllm-glm53-flash/kv-mmap/*.mmap` (old #58 tier) and prune `kv-nvme/r*/` by mtime.

## Harnesses (all on spark1 home)
- `bench_arm.sh <arm> [runs]` + `bench_summary.py <arms...>` - single-stream structured/prose (repo bench_decode.py, port-fixed). Parity gate for every arm.
- `kvoff_correct.py <seed>` - cold -> GPU-hit control -> 3x100k flood (evict) -> restore; byte-compares a HIGH-MARGIN task (first 12 primes) and an EARLY-CONTEXT task (quote first 12 words) across cold/hit/restored; decode after restore x3. This is the correctness gate for anything touching KV.
- `kvoff_restart.py pre|post <seed>` - persistence across a full serve restart; `post` also sends a never-seen control that MUST stay cold.
- `agent_lanes.py <label> <lanes> <ctx> <turns>` - N concurrent growing conversations; per-lane cold/warm TTFT, decode, global hit %.
- `prefill_test.py` / `/tmp/cold100k.py <seed> <tag> <tokens>` - cold prefill throughput.
- Thinking-off kwarg for this template is `{"enable_thinking": false}`; `{"thinking":{"type":"disabled"}}` is ignored (reasoning-only output, no content delta).

## Traps that fake a result
- With the persistent NVMe cache live, ANY prompt sent before is a hit forever (even after restart). Prefill/TTFT A/Bs need never-seen salted prompts; a reused prompt showed a bogus 35x prefill gain.
- NvmeDirect bypasses `vllm:kv_offload_*` byte counters (stay 0). Prove restores with wall time + `/sys/block/nvme0n1/stat` sector reads + never-seen control staying cold.
- A FULL mmap tier crawls prefill to ~0 tok/s - looks like a hang.
- A restore's first decode request dips (~26 vs 30 tok/s) then recovers; measure 3 requests.
- Structured bench min can be a cold-JIT outlier (9 tok/s); read min/max, not just median.

## Decision record (2026-09-19)
- Keeper: FAST=1, coop OFF, `GLM53_APC_RETENTION_INTERVAL_SWA=0`, mixed-prefill 0, NvmeDirect persistent cache (40 GiB gate), `GLM53_NONE_HASH_SEED` set (pins NONE_HASH without PYTHONHASHSEED).
- coop + SWA=0 collapses decode (32/25); fair mixed-prefill raises hits but worsens warm TTFT unevenly; PR#233 BF16 large-M = no prefill gain here.
- Per-turn cost is the DFlash replay clamp (~2k tokens); at 4 lanes warm TTFT is ~80% contention.
