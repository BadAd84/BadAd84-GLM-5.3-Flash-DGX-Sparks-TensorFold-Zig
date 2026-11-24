---
name: deploy-gate-register-spark-serve
description: "Deploy, gate, and register a TensorFold-recipe model serve on the OTS DGX Spark pair (no NFS, memguard-aware, omp registration)"
---

# Deploy and verify a local TensorFold/recipe serve on the OTS DGX Sparks

End-to-end runbook distilled from the DeepSeek-V4.1-Flash-1017 deployments (spark4 rank 0 + spark5 rank 1). Adapt paths per model; the sequence and gates are the reusable part.

## Prerequisites (check, don't assume)

- kindling spark-os on every box (`/home` is the only big persistent fs; `/` is a RAM overlay - nothing installed outside /home,/srv,/var/lib/docker,/var/log survives reboot).
- Serve needs ~300 GiB free per box after cleanup (`df -h /home`); rank weight file ~106 GB, checkpoint in HF cache ~197 GiB.
- scp fails spark4-ward: move files with `ssh host 'cat > f' < local`. WSL is the harness shell; Windows git reads C:/ paths only; kindling lacks xz/patch/ensurepip (venv via get-pip, git apply instead of patch).
- Stop other work on the boxes first: a compile container BESIDE the live serve drove MemAvailable to 1.67 GiB and memguard killed the serve (2026-11-08 16:42).

## Deploy sequence (MiaAI-recipe pattern, no NFS)

1. Clone the recipe repo, write `scripts/local.sh` (WORKER=<fabric peer>, checkpoint pin, `PREPARE=0`, `NFS_VOLUME=<host path>` per docs/requirements.md "Or no NFS at all").
2. Seed any local model artifacts into the HF cache layout (snapshot dir + refs/main + blobs as hardlinks from ~/models - zero extra disk).
3. Download the checkpoint (`hf download repo --revision REV`), then rsync the snapshot AND the shared `hub/blobs` store to the worker (snapshot links into blobs).
4. `python3 scripts/prepare.sh` by hand: it builds the image (engine fork + recipe patches), makes kit/token-map/rank-0 weight file, and stops at its step 6 (NFS volume) - that is expected. Do step 7 on the worker by hand: rsync data dirs, then run its docker `tf-dsv41-rank-cache` command to write rank 1's weight file.
5. `./start.sh`; verify `/health`, one real completion, both ranks' docker logs, `MemAvailable` on both.

## The memory model (why every ceiling exists)

- GB10 unified memory: no swap, no eviction; host exhaustion wedges the machine (power-cycle), not a clean OOM. memguard (soft floor 2.5 GiB held 4 s, hard 1 GiB instant) kills the rank FIRST on purpose - a controlled 30 s restart beats a power cycle. Never lower the floor; reclaim memory instead.
- After-load MemAvailable is NOT the safe level: transient prefill-workspace spikes (~0.5 GiB on long-turn boundaries) dip below it. Safe = dips bottom 0.5 GiB ABOVE the floor under a worst-case load test (4 concurrent pool-filling prefills), sampled every 1-5 s.
- Watch `~/.cache/dsv41-tensorfold/logs/memguard.log`: "recovered: no kill" dips are fine; "killed container" is exit 137.
- Reclaim order: display-carveout KV (dispramd) > /tmp + tmpfs scratch > dockerd restart (a few hundred MiB real) > smaller POOL. The 12.2 GiB engine reserve is protective; never lower it.

## Gates before calling it serving

- Exactness harness 6/6 (drafted==serial, burst==solo, staggered==solo, resumed==fresh, images, needle) with deterministic digests equal to the off/default path.
- A cold near-window needle (~93% of the window) answered correctly, memory sampled 1-5 s, low >= floor+0.5 GiB on both ranks.
- The ceiling: step the pool until a run fails the margin, then revert to the last pass and re-verify. Auto-revert scripts beat manual fixes overnight.
- Benchmark runs (probe/RigMark): stop sparkDash (`pct exec 111 -- systemctl stop sparkdash`, restore in a trap), firewall :8888 via `fw8888.sh guard <pid> <dir>` (armed from an interactive ssh -A; the guard lifts at exit), record memguard kill counts per run.

## omp registration

- Provider block in ~/.omp/agent/models.yml: baseUrl http://sparkN.ots-int.net:8888/v1, api openai-completions, auth none, model id = the SERVED name (set SERVED_NAME in the recipe local.sh to a convention-matching name, e.g. ds41-flash-1017-exl3 mirroring glm-53-flash-exl3), thinking {mode: effort, efforts, defaultLevel, requiresEffort: false}, compat stream timeouts 2400000 ms (cold near-window prefills take minutes to first token).
- Mirror to ots/omp-config, commit signed from the Windows side, push. Smoke test: `omp -p "Reply OK" --model provider/model`.
- Default thinking effort: pick the benchmark-validated arm (low), not the flashiest (high burns minutes on think blocks and fails capped-output gates while reasoning).
