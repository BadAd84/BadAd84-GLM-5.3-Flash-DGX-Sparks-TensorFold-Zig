---
name: diagnose-gbm10-serve-oom-and-memguard
description: "Diagnose GLM serve memory exhaustion (GB10 unified-memory OOM: NV_ERR_NO_MEMORY, kernel kills) and keep the watchdog v14 memguard + pool headroom configured on spark1-3"
---

# Diagnose GLM serve memory exhaustion on DGX Sparks (GB10) and keep the watchdog guard armed

Use when the GLM serve on spark1-3 (or any GB10 unified-memory serve) wedges, dies, or shows `NV_ERR_NO_MEMORY`, and when tuning the watchdog's memguard or pool headroom.

## The failure class (confirmed 2026-10-25, twice in one day on spark2)

1. The GPU pool is unified memory: meminfo cannot see it. At exhaustion, `/proc/meminfo` shows tiny anon (~5-7 GB), page cache evicted to 0, free ~0.5 GB - while nvidia-smi holds 97-100 GiB of compute allocations. The kernel OOM dump's task table shows NO userspace hog; do not hunt one.
2. The NVIDIA driver fails first: `NVRM: nvCheckOkFailedNoLog: Check failed: Out of memory [NV_ERR_NO_MEMORY]` in dmesg, then `tensorfold invoked oom-killer`, then the kernel kills tensorfold AND `systemd --user` (UID 1000) and `sd-pam`. A dead worker leaves rank 0 wedged in a collective; the peer-watch patch ends it ~120 s later.
3. Growth: ~2.5 GB/h under fleet agent load (big 530-580k prefills), never returned (upstream issue #197 / #143 / #154). Life per boot was ~3-12 h before the guard.

## Diagnosis procedure

1. `dmesg -T | grep 'Out of memory: Killed'` on the dead node - gives the kill time, the process, and anon/total-vm. Check docker inspect for `OOMKilled`.
2. Sample `/health` deltas while traffic runs: per request, prompt-delta vs cached-delta. `cached 0` on a >10k prompt = full cold prefill. Correlate with `kv_tier_*` counters (loads/written/skipped_disk) and `kept_mix.by_chat`.
3. `kept_prompts` at the entry cap (TF_GLM_CACHE_ENTRIES) with many chats = churn: big sessions' states drop between turns -> periodic ~100 s cold prefills. Fix: raise the cap (32 -> 96 done 2026-10-26; kept bytes were ~2 GB).
4. The NVMe tier showing `kv_tier_loads 0` is NORMAL when harnesses rebuild history per session (prompts share only the ~16k system prompt with stored states). Tier restores only byte-identical replays. `skipped_disk > 0` means a node's /home is under the 50 GiB floor - the tier self-protects and that rank stops persisting.
5. Warmth sampler: `~/prof/warmwatch.py` on spark1 (nohup python3, logs `~/prof/warmwatch/warm.tsv` + `.log`, per-request warmth + kept-mix deltas).

## The guard (watchdog v14, deployed)

- `glm-watchdog.sh` v14 on spark1's SYSTEM unit (`glm-watchdog-system.service`, OOMScoreAdjust=-900). NEVER also run the user unit - two supervisors race recoveries (it happened 2026-10-25; user unit now stopped + disabled).
- Memguard: every tick reads MemAvailable on the head + ssh'd workers; any node < `GLM_WD_MEMGIB` (6 GiB) for `GLM_WD_MEM_STREAK` (3) ticks triggers `~/restart_when_idle.sh memguard-<ts>` (planned idle restart, no kill/capture), cooldown `GLM_WD_MEM_COOLDOWN_S` (2700). One-shot: `glm-watchdog.sh --check-mem`.
- Crash-path visibility: `serve unreachable: N/40` every 10 DOWN samples; capture's df/du/dmesg/nvidia-smi/ip are timeout-wrapped (v13 hung 3 h inside an unbounded capture).
- Repo source of truth: glm5.3-flash-dev `scripts/glm53/glm-watchdog.sh`; docs gate `check-doc-inventory.sh` fails on watchdog-version drift (README + both docs + `docs/spark-live-state.json` via `refresh-spark-state.sh`).

## Headroom levers (owner-approved values)

- `KV_POOL_GIB` 35 -> 31 (2026-10-26): the pool is unified memory held from boot, so each GiB is a GiB of daily headroom. Pool 6,586,368 -> 5,949,440 tokens. Pool size is NOT in the NVMe tier folder key (tier continuity survives).
- `TF_GLM_CACHE_ENTRIES` 32 -> 96 (kept bytes ~2 GB at 32).
- `TF_GLM_FILL_FAST_MS=400` (ots0122) for warm-turn first-token.
- `TF_GLM_PREFILL_ROWS 4096 -> 2048` remains available as a decode-stall trade (prefill -4-6%) - NOT applied; needs the owner's sign-off per the fleet trade rule.
- Apply via env file (`~/v110ots.env` on spark1) + `~/restart_when_idle.sh <label>`; a rank setting that is in the tier folder key (e.g. prefill rows) starts the tier empty once.

## The real fix

The Python engine has no fix for the growth class - it is fixed only in the Zig engine (TensorFold zig; upstream recipe PR #211). The migration path is the owner's `ai-engine` repo (fork of TensorFold Zig main, GLM + DSV4.1 + Qwen in one tree); until it beats production, the memguard + headroom bridge keeps spark1-3 alive.
