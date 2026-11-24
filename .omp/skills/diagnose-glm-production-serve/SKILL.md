---
name: diagnose-glm-production-serve
description: "Diagnose GLM production serve on spark1-3: cold prefills, decode starvation, OOM deaths, NVMe tier behaviour; includes the live measurement recipes and the knob levers with their trade-offs"
---

# Diagnose GLM production serve slowness / cold prefills (spark1-3, ots124)

Symptoms this handles: agents slow on the GLM serve; sparkDash shows prefill churn; decode t/s collapsing during fills; sessions cold after serve restarts; "NVMe tier not loading".

## Order of operations

1. **Read counters, don't theorize.** On spark1: `curl -s localhost:8888/health | python3 -m json.tool` - key fields: `kv_tier_loads` (tier restores; 0 all day = nothing ever prefix-matched), `kv_tier_written_points/_bytes` (writes happening), `kept_prompts` vs `TF_GLM_CACHE_ENTRIES`, `kept_mix` (own/shared/chats/rows), `pool_free_tokens`, `cached_tokens_total`/`prompt_tokens_total` (cumulative warmth).
2. **Watch live with deltas.** Poll /health every 3 s; per request compute prompt/cached deltas. Interpretation:
   - warm = 96-100% cached (normal; big agent turns resume from pool)
   - 0% cached on a big prompt followed by a same-size 100% replay = salt-isolated bench pair (RigMark/sparkDash PrefillBench), by design - NOT a cache fault
   - 0% cached with no replay = a session whose states churned out of the kept cap, or a harness-rebuilt history (diverges at the system prompt - check the common prefix against tier points)
3. **Check memory pressure on all three nodes**: `free -g` + `grep MemAvailable /proc/meminfo`. Under agent load ~2.5 GiB/h burns (driver + anon growth that never returns; unified memory). At zero: driver NV_ERR_NO_MEMORY, then kernel OOM kills tensorfold AND the node's systemd --user. The v14 watchdog memguard restarts at idle below 6 GiB (45-min cooldown). If the serve died: `docker inspect glm53-flash-tf` OOMKilled/ExitCode, node `sudo dmesg -T | grep "Out of memory"`.
4. **Tier folder forensics** (files root-owned: use `docker exec glm53-flash-tf python3 ...`): `/cache/kvtier/<folder-key>-r0/points/*.json` + `.ids.npy` + `.pt`, blocks in `/blocks`. Folder key survives KV_POOL_GIB but changes with TF_GLM_PREFILL_ROWS/FILL_ROWS (tier starts empty once). Compare newest point ids vs the live conversation to measure divergence (how many prefix tokens shared).
5. **Decode-under-fill probe**: POST a tiny 64-token completion every 8 s; if tok/s halves+ within a minute, fills are starving decode (chunk size = TF_GLM_PREFILL_ROWS 4096 vs recipe 2048; the trade is owner's).

## Knobs (env on spark1 ~/v110ots.env, restart via ~/restart_when_idle.sh <label>)

- `TF_GLM_CACHE_ENTRIES` 32 -> 96 (kept-state cap churn dropped big sessions between turns; kept bytes ~2 GB at 32, pool had room) - 2026-10-26.
- `KV_POOL_GIB` 35 -> 31 (headroom) - 2026-10-25.
- `TF_GLM_FILL_FAST_MS=400` (ots0122) - warm turns' first token sooner.
- `TF_GLM_PREFILL_ROWS 4096 -> 2048` halves decode stalls per fill chunk but costs 4-6% prefill (owner trade, not applied).

## Watchdogs

- Supervisor = SYSTEM unit `glm-watchdog-system.service` (OOMScoreAdjust=-900). NEVER also enable the user unit `glm-watchdog.service` (double supervisor racing one stack).
- The v14 watchdog can still hang silently inside recovery; check `pgrep -af glm-watchdog` and the log's last line if the serve is down but no recovery fired. `glm-watchdog.sh --check-mem` / `--check-links` are safe one-shots.
- persistent warmth sampler: spark1 `~/prof/warmwatch.py` -> `~/prof/warmwatch/warm.tsv` + `~/prof/warmwatch.log` (starts via `nohup python3 ~/prof/warmwatch.py`).

## Zig escape (owner direction)

The memory-growth class has no Python fix. Production moves to the owner's own fork repo `ai-engine` (ots/tensorfold-gb10, TensorFold Zig main; GLM via glm-cuda backend). NOT the upstream recipe's `zig-engine` branch.
