---
name: diagnose-gb10-unified-memory-drain
description: Use when a GB10/Spark serve drains host MemAvailable or OOMs with no process RSS growth; attributes the leak via per-layer elimination and a torch memory_stats debug endpoint
---

# Diagnose a GB10 unified-memory drain (Sparks, GLM/TensorFold serves)

Symptom: MemAvailable drains over hours of real traffic, kernel OOM (look for NVRM `_memdescAllocInternal`/`system_mem.c` failures beside the kill) or a stall-wedge (faulthandler "Timeout" dump, threads in `forward.mm`, requests never idle so every idle-gated restart refuses; only `docker rm -f` all ranks + a coordinated `restart_when_idle.sh` recovers).

## Facts that shape the method
- GB10 is unified memory: CUDA device allocations are INVISIBLE to process RSS/smaps (a serve holding ~90 GiB of device memory shows ~7.6 GiB in smaps) and to AnonPages/Slab/Shmem/Unevictable. "Flat RSS" NEVER excludes a device-side leak.
- `nvidia-smi --query-gpu=memory.used` and `-q -d MEMORY` return N/A on GB10.
- torch's caching allocator fragments under varying-shape traffic: `allocated` flat + `reserved` growing is the signature. Fixed-shape probes and pure-torch alloc/free churn loops DO NOT reproduce it (perfect reuse). The trigger is real agent traffic: long conversations appending ~23k tokens a turn, each a slightly different shape.
- `expandable_segments:True` is the fragmentation fix (one `_set_allocator_settings` line in engine init, `--parallel > 1`); TensorFold's qwen3_5 family already sets it, glm5_next did not.
- Kept prompt states own tensors OUTSIDE the KV pool; TF_GLM_CACHE_ENTRIES bounds the COUNT only - the MEMORY bound is TF_GLM_KEPT_BYTES_GIB (0 = off = unbounded). Check /health `kept_bytes` vs `kept_bytes_cap`.

## Procedure (measure, never assume)
1. Evidence first: `sudo dmesg | grep -E 'oom-kill|Out of memory|NVRM'`; memguard log `~/prof/memguard-fallback.log` (trigger readings + restart history); rank logs survive wedged boots under `~/.cache/tensorfold-glm53/logs/` via stop.sh - but `docker rm` destroys them, so `docker logs > file; gzip` BEFORE removing a wedged container.
2. Eliminate layers with per-layer probes: (a) 300 fixed-shape requests (drains nothing = not per-request); (b) growing conversations (chainturn.py, 4 concurrent x 8-12 turns) sampling per-node avail + serve RSS + /health kept_bytes each turn; (c) full /proc/meminfo diff across 3 turns (which counter moves); (d) a spill-OFF boot as A/B if the spill tier is suspected.
3. When every process/kernel counter is flat but avail drains: build a DEBUG image adding a `/cuda` GET endpoint returning `torch.cuda.memory_stats()` (allocated/reserved/segments/live_blocks; patch pattern in glm5.3-flash-dev `scripts/glm53/v110/sync/fix/cuda-endpoint.patch`, built via the build_knobs.sh FROM-live-image + patch pattern). Boot it, rerun the growing-conversation probe, read /cuda per turn.
4. Verdict: allocated grows = live-tensor leak (find the holder); reserved grows with allocated flat = allocator fragmentation (fix: expandable_segments); both flat while avail drains = driver-side (escalate to nvidia/driver level).
5. Ship the fix as a repo-versioned patch on the stack, verify on the same probe workload (reserved/avail flat, digests unchanged - allocator settings change no numerics), then update env/GLM_IMAGES/docs/spark-live-state and commit.

## Gotchas
- Nested ssh heredoc quoting breaks every inline python probe: write probe scripts to files and scp them; no f-strings with escaped quotes inside `ssh '...'`.
- The wedge blocks idle-gated recovery: stop the watchdogs, hard-remove all ranks, one coordinated restart.
- Only spark1 serves :8888; health 000 on spark2/3 is NORMAL (workers do not serve HTTP).
