---
name: diagnose-gb10-unified-memory-oom
description: Diagnose GB10 unified-memory OOMs/wedges on a TensorFold serve (spark1-3 GLM fleet) when logs show nothing
---

# Diagnosing GB10 unified-memory OOMs on a live TensorFold serve (spark1-3)

Use when a GLM/Dolphin serve on DGX Spark (GB10, unified memory) drains MemAvailable, kernel-OOMs, or wedges under sustained traffic, and the cause is not obvious from logs.

## What is different about GB10

- Host RAM and GPU memory are one pool (~123 GiB). A process's smaps/RSS do NOT show its CUDA device allocations (measured: serve smaps total 7.6 GiB while it owns ~90 GiB of device memory). "Flat RSS" never excludes a device-side leak.
- `nvidia-smi` reports N/A for memory on GB10. Do not use it.
- MemAvailable drops that appear in NO process RSS and NO /proc/meminfo counter (AnonPages/Slab/Shmem/Unevictable flat) are device allocations: measure them with torch's own accounting, not the OS's.

## The wedge signature

A memory-pressure stall shows as: faulthandler "Timeout (0:05:00)!" dump with engine threads inside `forward.mm`, health dead or requests stuck, and the serve NEVER goes idle. Idle-gated restarters (restart_when_idle, memguard) then give up forever. Recovery is only: `docker rm -f glm53-flash-tf` on all three ranks, then one coordinated `bash ~/restart_when_idle.sh <label>` from spark1 (starts all ranks). Save the dead container's log first: `docker logs glm53-flash-tf | gzip > ~/.cache/tensorfold-glm53/logs/<date>-wedged-rank0.log.gz` (docker rm destroys it otherwise).

## Diagnosis ladder (each rung eliminates one layer)

1. Slope the drain: 4 concurrent growing conversations (chainturn.py on a state file, 12 turns), sample `free -m` per turn per node. Short fixed-shape requests prove nothing: only varying-shape traffic triggers allocator fragmentation.
2. Eliminate processes: `smaps` of the serve (root-owned: needs sudo) plus `ps -eo rss` diff on all nodes. Expect this to look clean - see GB10 note above.
3. Eliminate kernel memory: /proc/meminfo diff (AnonPages, Slab, SUnreclaim, Shmem, Unevictable, PageTables) across 3 turns.
4. Eliminate config layers by booting without them one at a time (SPILL_GIB off; knobs off). A restart is ~5 min via restart_when_idle.
5. Name device-side growth: build a debug image adding a /cuda GET route returning torch.cuda.memory_stats() (allocated/reserved/segments/live blocks) - patch in glm5.3-flash-dev scripts/glm53/v110/sync/fix/cuda-endpoint.patch; build with build_knobs.sh BASE=<live image> TAG=<image>-dbg DIR=<patch dir>. Read it per turn. allocated flat + reserved growing = caching allocator fragmentation; allocated growing = live tensor leak; both flat while the node drains = driver-side.

## Known causes already fixed here (do not re-derive)

- Kept prompt states own memory outside the KV pool (DFlash2 window copies, hundreds of MiB for long conversations); TF_GLM_CACHE_ENTRIES bounds count only. Fix: TF_GLM_KEPT_BYTES_GIB=8 in v110ots.env.
- Allocator fragmentation under varying-shape traffic with --parallel>1. Fix: expandable_segments:True in the glm5_next engine init (sync/fix/expandable-segments.patch). Watch reserved not allocated.

## Rules

- Everything measured, nothing inferred: per-turn tables with the numbers, before claiming a mechanism.
- The owner wants the engine fixed, not mitigation (no lowered thresholds as the answer).
- Every probe script goes in glm5.3-flash-dev work/hunt/deploy/ and is run detached (setsid nohup) on spark1; avoid inline python through ssh layers - scp a file, run the file (quoting through ssh+heredoc breaks f-strings).
