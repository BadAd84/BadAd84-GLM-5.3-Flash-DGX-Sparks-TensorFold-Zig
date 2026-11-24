---
name: sync-glm53-exl3-recipe-with-upstream
description: "Sync the OTS GLM-5.3-Flash EXL3 serve (spark1 ~/glm53-current) with the upstream MiaAI-Lab recipe: reconcile our local overlay grafts against upstream commits, rebuild, qualify in a window - without disrupting the live serve."
---

Sync our pinned GLM-5.3-Flash EXL3 recipe (`~/glm53-current` on spark1) with upstream MiaAI-Lab commits, keeping our unique grafts and dropping ours where upstream converged. The serve is LIVE (agents via CT105 router), so all prep is non-disruptive; only the swap needs a window.

## Our tree shape (know this first)
- `~/glm53-current` = upstream base commit + **uncommitted working-tree edits** (ZERO local commits). Clean fast-forward to upstream tip is possible.
- Our customization = a few MODIFIED tracked files (Dockerfile, start.sh, overlay/exl3.py [copy-starvation, load-bearing], overlay/patch_hybrid_prefix_hit.py, extensions/cooperative_moe/prepare_profile.py) + UNTRACKED grafts (overlay/kvoffload/nvme_direct.py = NvmeDirect persistent KV cache, patch_kv_offload_groups.py, patch_none_hash_seed.py, patch_indexer_warmup_range.py). Several of ours are still OPEN upstream PRs (#58/#231/#232).
- Rollback tree `~/glm53-flash-2spark` kept intact; `spark-model` targets `glm53-current`.

## Phase 0 - baseline/identity (non-disruptive)
`git rev-parse HEAD`, running image (`docker ps`), KV key (`ls ~/.cache/vllm-glm53-flash/kv-nvme/`), confirm rollback tree present. Documented baseline numbers live in `glm5.3-flash-dev/docs/GLM53-FLASH-PRODUCTION-STACK.md` (structured 78-80 / prose 36 / code 44 tok/s).

## Phase 1 - prepare the merge (non-disruptive, scratch worktree)
1. `cd ~/glm53-current; git fetch; git worktree add --detach ~/glm53-sync-scratch <upstream-tip>` (no node_modules junctions here, so worktree is safe).
2. `git diff > /tmp/our_overlay.diff; cd ~/glm53-sync-scratch; git apply --3way /tmp/our_overlay.diff`. **CRITICAL orientation: in the conflict markers, `ours` = UPSTREAM (working tree), `theirs` = OUR local change** (reverse of intuition). Copy the untracked grafts in with `cp -r ~/glm53-current/overlay/kvoffload ./overlay/` etc.
3. Reconcile per this rule: **keep upstream (`@ours`) where upstream added an equivalent to ours; keep only our UNIQUE load-bearing grafts.** Measured resolutions last time: KDA_BF16_LARGE_M (exl3.py) -> take upstream (newer TP2+TP3 superset, we run it OFF); patch_hybrid_prefix_hit + its test + coop-SHA prepare_profile -> `git checkout <upstream> -- <file>` (upstream converged on the SAME `[glm53-dflash-boundary-lookup-v1]` feature + fine-grained eligibility, so revert wholesale = no dangling defs); start.sh -> `@both` for the additive patch-declaration/application blocks (upstream Mamba-align vs our KV-offload), keep our DFLASH_SCHEDULE + ots-kvcache-key blocks; copy-starvation in exl3.py merges CLEAN (keep).
4. Validate the tree: no conflict markers (`grep -rlE '^(<<<<<<<|>>>>>>>|=======)'`), `python3 -m py_compile` the .py, `bash -n start.sh`.
5. **Rebuild the image** - the Dockerfile applies every overlay patch at BUILD time (`RUN python3 /opt/glm53/patch_*.py` + `test_*.py` gates), so the build IS the validation that all patches anchor. Dockerfile is `FROM ${BASE}` with `ARG BASE=vllm/vllm-openai:glm53-flash-arm64-cu130@sha256:905c...`; `build_image()` uses that default (no BASE override) and tags `$IMAGE`. For a scratch build: `docker build --build-arg GLM53_RECIPE_STAMP=<stamp> -t glm53-flash-sm121:<synctag> .` (fresh tag; live `:local` untouched). Docker auto-pulls the base from docker.io/vllm/vllm-openai (mostly cached layers).

## Phase 2 - qualify (WINDOW)
Stop watchdog (`systemctl --user stop glm-watchdog`), swap to the new image, health-wait :8889. Run correctness gates (kvoff_restart pre/post, test_nvme_direct_stale, prefill_test) + bench_decode A/B vs baseline (never-seen prompts). Bump the version-keyed KV root (stack change -> empty cache). Adopt if clean+equal; rollback (`sed spark-model` to glm53-flash-2spark) if regression.
## Phase 3/4 - A/B upstream's #238 compact-DFlash2 knob, then re-validate remaining grafts ON vs OFF one at a time.

## Windows/ssh gotchas (each cost a cycle)
- **Inline base64 of a tarball is TOO LONG for the Windows ssh command line (os error 206).** Transfer FILES via scp (laptop->CT106->spark1); reserve `echo <b64> | base64 -d | ssh spark1 bash -s` for SMALL scripts only.
- Reach spark1 via CT106 jump: `ssh root@192.168.99.106 "... | ssh -o StrictHostKeyChecking=accept-new adam@192.168.99.101 bash -s"` (git-for-windows ssh has no spark1 host key; direct fails).
- Harness conflict tooling: read `<file>:conflicts` for the compact list, `conflict://<N>[/ours|/theirs]` to inspect, `write conflict://* content "N: @ours\nM: @both"` to bulk-resolve. `git checkout <ref> -- <file>` is cleaner than `@ours` when you want to drop ALL our changes to a file (removes clean-merged additions too).
