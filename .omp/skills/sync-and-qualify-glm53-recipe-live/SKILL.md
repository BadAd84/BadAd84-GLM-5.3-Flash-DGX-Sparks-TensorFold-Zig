---
name: sync-and-qualify-glm53-recipe-live
description: "Use when moving the live GLM-5.3-Flash serve to a newer MiaAI-Lab TensorFold recipe release: bank, stock baseline, OTS patch port, cross-stack A/B, disk-tier comparisons; not vLLM-era."
---

# Move the live GLM-5.3-Flash serve to a newer MiaAI-Lab recipe release

Recipe: github.com/MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold (`R`). SSOT: glm5.3-flash-dev
`docs/GLM53-FLASH-PRODUCTION-STACK.md`; ledger `docs/GLM53-TENSORFOLD-TP3-PORT.md`. Done this way for v1.8 -> v1.10 on
2026-10-08 (ledger F86-F87, scripts in `scripts/glm53/v110/`, box copies in spark1 `~/`). Building is
non-disruptive; the baseline and every A/B borrow the production serve (spark1-3 run one model at a time).

## Order (owner-set)
1. Bank what runs. 2. Pull the new release and baseline it as shipped. 3. Port our patches. 4. Cross-stack A/B, then
production. 5. Package the upstream PRs (skill `submit-ots-patch-as-miaai-recipe-pr`; owner: one batch at the end).

## Reconciliation rule (owner-set)
Stay as close to upstream as possible. Where upstream merged or converged on one of ours, take upstream's (and its
switch) and drop ours: our 0072 -> recipe 0087 `DISPLAY_KV_BACKEND=dispram`, 0074 -> 0091 `TF_GLM_LOOP_GUARD=1`, 0079
-> 0090 `TF_GLM_EXL3_DEC_ORDER=1`, 0076 / 0077 -> 0085 / 0086. Check with `diff --strip-trailing-cr`: the maintainer
rewords comments, the code stays ours. Keep only unique load-bearing patches.

## 1. Bank
- Signed tag in each serve repo it covers (`git tag -s bank-YYYY-MM-DD -F <msg file>`), pushed: glm5.3-flash-dev,
  and qwen3.8-flash-next-dev when Qwen's image is banked too.
- Prove the images ARE the repo: production's `tf.ots-patches` label equals `name:sha256[:12]` of each CR-stripped
  patch file; Qwen's image files equal its layers by md5 after a CR strip (`build_qwen_ots.sh` strips CRs).

## 2. What moved, and the stock image
- `gh api "repos/$R/commits?sha=main"`, `CHANGELOG.md` (each release names its image tag + digest and the patches it
  adds), the `patches/` list, `gh pr view` of our PRs (merged ones reappear under upstream numbers).
- Engine line: TensorFold 1.0.x is a Zig rewrite; its 1.0.2 build on a GB10 serves only Nemotron 3.5
  (`tensorfold-native capabilities --json`), so the GLM and Flash Next recipes stay on Python TensorFold 0.6.x until
  that lists their families on CUDA.
- Pull on every node by the release's digest (`scripts/config.sh`: `GHCR_IMAGE@IMAGE_DIGEST`) and tag it
  `tensorfold-glm53:v0.6.0-<hash8>`; remove the plain `tensorfold-glm53:v0.6.0` tag config.sh defaults `IMAGE` to
  (every release has the same `TF_VERSION`, so that tag collides across releases).
- Recipe tree: a fresh clone at the release sha on spark1 (`~/mia110` @ 549fdc5) with `scripts/local.sh` copied
  (WORKER / WORKER2 = spark2 / spark3 names, WORKER_WEIGHTS copy). Not a worktree: `~/mia15-v18`'s parent repo is
  gone and its git link is broken.
- Extract both images' packages (`docker create`, `docker cp <cid>:/usr/local/lib/python3.12/dist-packages/tensorfold`,
  drop `__pycache__`) and `diff -rq` them: the files upstream changed are where our patches need re-porting.

## 3. Port
- Trial-apply our kept patches in order (`git apply -p1` in a `git init` copy of the new package): clean /
  `-C1 --recount` fuzz / fail. A failure cascades into later patches' context (decode.py start-up loads): fix the
  root first. `patch` is not installed on kindling; re-anchor a hunk git cannot place with a python replace that
  asserts each anchor occurs exactly once.
- Ported patches: `scripts/glm53/v1NN/otsNNNN-<name>.patch` (the `ots` prefix: upstream's own 00NN numbers now
  collide with ours), built by `build_v1NN.sh` (build_v18.sh with BASE / UPSTREAM_HASH / `ots[0-9]*.patch`: COPY
  layers, `tf.patches` kept so the kernel-cache folder is shared unless compiled sources change, content-hashed
  extension names, one files digest proven equal on all three nodes). Tests and mutant runners adapted under
  `scripts/glm53/v1NN/tests/` (lanes on spark5, under the gpu-bench lock).
- Prove the port: every patch applies in order, then compare the patched tree with production's file by file:
  byte-identical where upstream did not touch the file, every other difference explained.

## 4. Baseline and A/B (borrowing production)
- Launchers: `glm-v1NN-start.sh` sources `~/v1NN.env`, a symlink to the arm's settings (`v110stock.env` baseline,
  `v110ots.env` our image, `v110spill.env`, `v110tier.env`), then `cd ~/mia110 && ./start-tp3.sh`;
  `glm-v1NN-stop.sh` sources it and runs `stop.sh`. Each env sets `IMAGE=... PREPARE=0`; the baseline carries only
  deployment settings (pool, dispram span, PARALLEL, COMM) plus upstream's switches for our merged patches.
- Switch stacks by copying `~/.config/glm-stack.env.v18` or `.v110` over `~/.config/glm-stack.env` (GLM_STACK,
  GLM_START, GLM_STOP, GLM_IMAGES), then `~/restart_when_idle.sh <label>`; it also starts a serve that is down
  (curl exit 7 counts as idle).
- kindling: v1.10 as published HANGS at start on the 64 KiB-page kernel (the vision tower's upload from the
  safetensors mmap: no `vision:` line after the drafter timings, ranks spinning, 15 min). The baseline image is
  upstream + our 0073 alone (`tensorfold-glm53:v110-base`); 0073 is an upstream PR (`upstream/recipe-pr-mmap-uploads/`).
- `baseline.sh <label>`: the whole suite on the running serve (ab_long, realdec, 4 x 596k multidec, warm turns, a
  cold 112k, fills beside a stream). Digests printed; at v1.10 every one equalled v18's.
- Carry the NVMe tier into the new kernel-cache folder (`~/.cache/tensorfold-glm53/<tf.patches hash>/kvtier`) with
  `tier_carry.sh <from hash> <to hash>` on each node: hardlinks made in a container, points before blocks, dot files
  skipped; safe while serving (the tier writes through temp names + `os.replace`). The fingerprint did not change, so
  v1.10 resumed v18-written states with identical replies.
- `stack_ab.sh <label> v18 v110:<env> v18 v110:<env>`: interleaved arms across restarts, bits checked against the
  v18 references in every arm, the serve ends on the last arm. The v1.10 port: bits OK in every arm, speed within ~1%.

## Comparing disk tiers (ours vs upstream's spill tier, recipe 0088)
- Use the real agent pattern: `chainturn.py` / `tier_chain.sh` (each request = the previous prompt + reply + ~20k
  new). `warmturn.py` inserts its tail before the closing instruction, so it BRANCHES from the history and needs a
  shared-prefix state; spill never wrote those (a clean stop flushed 4 GB a node and the branch still re-prefilled;
  multi.py `_unspillable` returns `no_draft_window` for states without a DFlash2 window). A branch test overstates
  our lead.
- Measured (F87, `spill_qual.sh` / `tier_vs_spill.sh`): spill writes nothing while the pool is under
  `SPILL_HIGHWATER` (0.70), only at eviction pressure or the clean-stop flush, and a SIGKILL loses every
  never-evicted state; ours writes at keep and resumed after the crash.
- A ~700 ms worst gap of a stream beside a ~619k request in an image without our 0082 is tokenization holding the
  GIL, not the tier.

## Upstream qualify tools (`tools/`, PORT / API_URL as `tools/client.py`)
- `prompt_reuse.py [size]`: sub-agent shared-prefix resume; exit 1 under 90%. Light enough for live production.
- `pool_pressure.py [size]`: two agents at a full pool; needs a FRESH server with nothing else sending: boot a small
  pool (`KV_POOL_GIB=1 CONTEXT=131072`), else it fills the whole production pool (~45 min).
- `display_kv_check.py`: without `--gpu` fake drivers, non-disruptive
  (`docker run --rm --entrypoint python -v <recipe>/tools/display_kv_check.py:/c.py <img> /c.py`); `--gpu` needs the
  GPU free.

## Restore production
`~/restart_when_idle.sh <label>` with glm-stack.env naming the production stack, or
`ssh adam@192.168.99.11 'bash -lc "spark-model glm start"'` (spark-model is in `~/.local/bin`, not on a non-login
PATH); wait for health 200, `systemctl --user restart glm-watchdog`, confirm `docker inspect -f '{{.Config.Image}}'
glm53-flash-tf`.

## Traps (each cost real time)
- NEVER pipe a remote script into bash when it calls stop.sh / start-tp3.sh / spark-model: their ssh-to-workers read
  stdin and eat the rest of the script. scp it, `tr -d '\r'`, run with `</dev/null`.
- A detached `setsid ... start-tp3.sh &` plus a poll loop failed silently: start through `restart_when_idle.sh` /
  spark-model, or run start-tp3.sh in the foreground.
- `docker inspect -f '{{index .Config.Labels "tf.patches"}}'` through nested ssh escaping breaks (`template parsing
  error: unclosed action`): single-quote the whole ssh command or run it in a script on the box.
- After a LAN IP remap the head's known_hosts lacks the workers' names: `ssh-keyscan` them on spark1; keep worker refs
  on `spark{N}.ots-int.net` names (GLM_WORKERS, recipe `scripts/local.sh`), never raw IPs.
- `systemctl --user is-active` right after a start can say inactive; recheck after a few seconds.
- Every A/B prompt set must be never-seen, or the NVMe tier / kept prompts measure the cache, not the change.
