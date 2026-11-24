---
name: sync-glm53-exl3-recipe-to-upstream
description: "Sync the pinned MiaAI-Lab GLM-5.3-Flash-EXL3 2xSpark recipe (glm5.3-flash-dev) up to current upstream while keeping our unique grafts, then qualify+swap the live serve - use for the periodic recipe catch-up."
---

# Sync the GLM-5.3-Flash EXL3 recipe to upstream + qualify

Our live GLM serve runs `~/glm53-current` @ a pinned upstream commit + UNCOMMITTED overlay edits/grafts. Upstream (MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks) keeps advancing its OWN recipe on the SAME vLLM fork (487ecf187 - it has NOT moved to vLLM 0.30; EXL3 is fork-only). Getting in sync = catch up the recipe, keep our unique grafts, rebuild+qualify.

## Orientation first
- EXL3 port ownership: Turboderp (quant + exllamav3 kernels) + MiaAI-Lab (the vLLM GB10 recipe we run) + blazux (arm64 base image `vllm/vllm-openai:glm53-flash-arm64-cu130`). NOT vLLM-upstream, so no external forward-port to 0.30.
- Do NOT chase NVFP4-mainline: measured slower (~21-30 vs our 36-80) AND still needs its own GB10 patch stack (barrydeen recipe) -> no fork-escape.

## Phase 0 - baseline + snapshot (non-disruptive)
- Record identity: `git -C ~/glm53-current rev-parse HEAD`, running image, `~/glm53-flash-2spark` rollback tree HEAD, KV-cache key. Our tree carries ZERO commits - all customization is `git diff` (tracked) + untracked grafts.
- Baseline bench the LIVE serve: `bash ~/bench_arm.sh baseline 5` (structured+prose to ~/bench_results); extract tok_s_median/ttft/accept.

## Phase 1 - reconcile in a scratch worktree (non-disruptive)
- `git -C ~/glm53-current fetch origin`; `git worktree add --detach ~/glm53-sync-scratch <upstream-tip>`.
- `git -C ~/glm53-current diff > /tmp/our.diff`; in scratch `git apply --3way /tmp/our.diff`; copy untracked grafts in.
- **Marker orientation: in `git apply --3way`, `<<<<<<< ours` = UPSTREAM (working tree), `theirs` = OUR change.** (Reverse of intuition.)
- Resolution rule (owner-directed): where upstream ADDED an equivalent to ours -> take upstream, drop ours (revert those files whole with `git checkout <tip> -- file` to avoid dead clean-merged defs); keep ONLY our unique load-bearing grafts (copy-starvation exl3.py, NvmeDirect KV, none-hash-seed, kv-offload-groups, indexer-warmup, ots-kvcache-key, DFLASH_SCHEDULE); take upstream's newer version of a shared feature (e.g. KDA_BF16_LARGE_M).
- Verify: no conflict markers, `py_compile` overlay + `bash -n start.sh`.

## Phase 1 build (non-disruptive - new tag)
- Copy tuned `.env`: `cp ~/glm53-current/.env ~/glm53-sync-scratch/.env`; set `IMAGE=glm53-flash-sm121:sync<tip>`.
- Build: the Dockerfile applies EVERY overlay patch at build (`RUN python3 patch_*.py` + test gates) FROM `${BASE}` (default `vllm/vllm-openai:glm53-flash-arm64-cu130@sha256:905c...`; docker auto-pulls). `docker build --build-arg GLM53_RECIPE_STAMP=sync -t glm53-flash-sm121:sync<tip> .`. A failed anchor = loud RUN failure = the merge telling you what still needs reconciling. 83/83 steps + `build exit 0` = validated.

## Phase 2 - swap + qualify (WINDOW - takes serve down ~15-20 min)
- Only in a maintenance window (owner confirms model not in use).
- Detached swap MUST use `setsid bash swap.sh </dev/null >/dev/null 2>&1 &` (a one-shot-ssh `nohup ... &` gets torn down - empty log, no effect). swap.sh: stop watchdog -> `docker rm -f` head + worker -> mem-hygiene -> `cd ~/glm53-sync-scratch && SKIP_BUILD=1 SKIP_DOWNLOAD=1 SKIP_SYNC=1 SKIP_PULL=1 ./start.sh` (auto-ships image to worker via docker save|ssh load; ots-kvcache-key computes a NEW key -> empty cache, no stale KV) -> health-wait :8889 up to ~20 min.
- Gates: kvoff_restart pre/post, test_nvme_direct_stale, prefill_test (copy-starvation); then `bench_arm.sh sync 5` and compare tok_s vs baseline. Regression -> boot the `:local` rollback (`spark-model glm start` from ~/glm53-current). Clean+equal -> adopt: land scratch as ~/glm53-current, re-arm watchdog+disk-guard, update INVENTORY/production-doc/watchlist.

## Phase 3/4
- A/B upstream's new knobs (GLM53_DRAFT_KV_COMPACT #238) single-stream AND multi-lane (agent_lanes.py).
- Re-validate remaining grafts one at a time (ON vs OFF) on the synced base; drop any upstream now does differently.
