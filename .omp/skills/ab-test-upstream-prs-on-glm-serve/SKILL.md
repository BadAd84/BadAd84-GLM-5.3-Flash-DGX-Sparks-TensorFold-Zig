---
name: ab-test-upstream-prs-on-glm-serve
description: "A/B an unmerged TensorFold/MiaAI recipe PR or lever on the GLM Spark serve: arms from the PR head, control from the base, NODEFS stripping."
---

# ab-test-upstream-prs-on-glm-serve

one skill: A/B an upstream recipe/PR on the GLM Spark serve

Merged from 6 skill(s): ab-test-glm-tensorfold-upstream-changes, ab-test-qwen-lever-on-upstream-tensorfold-spark6, ab-test-upstream-prs-on-glm-spark-serve, ab-test-upstream-prs-on-glm-tensorfold-serve, ab-test-upstream-prs-on-glm53-spark, ab-test-upstream-prs-on-tensorfold-glm-serve.

# A/B upstream changes on the OTS GLM TensorFold serve (spark1-3, TP=3)

Upstreams:
- Recipe: `MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold` (patches/*.patch plus start.sh/config.sh). Clone at ~/mia15; v1.8 worktree at ~/mia15-v18.
- Engine: `ashhart/TensorFold`. Its Python engine is FROZEN (#286, 0.6.5/0.6.6), and every GLM CUDA PR there is closed unmerged.

So a GLM gain arrives only as a recipe patch, or by porting a closed PR ourselves.

## 1. Survey, then reproduce the symptom on the LIVE serve
- GitHub API, unauthenticated: 60 calls/h; search is 10/min, so sleep 7 s between searches.
  - For both repos: releases, tags, last 40 commits, open and recently closed PRs, open issues.
  - Then each candidate's body: base version, files, claimed gain, its measurement.
- Before porting anything, reproduce the claimed symptom on :8888 with read-only probes:
  - Sampling cost: `sample_probe.py` (greedy vs temp/top_p, with and without `top_k: 0`; ms/round).
  - Concurrency: `conc_probe.py <url> conc` (1 vs 4 streams, 4 cold 16k prompts).
  - Long-context round cost: `conc_probe.py <url> depth 2000 64000 200000`.
- Several upstream issues do not reproduce on our stack.

## 2. Apply against the WHOLE package tree from the image
- Extract it: `cid=$(docker create IMG); docker cp $cid:/usr/local/lib/python3.12/dist-packages/tensorfold DIR/; docker rm $cid`, then `git init && git add -A && git commit`. A build context holding only the changed files gives false conflicts.
- TensorFold PR:
  - Fetch `https://github.com/ashhart/TensorFold/pull/N.diff`.
  - Keep only the `diff --git a/src/tensorfold/` sections (docs/tests sections break -p2), then `git apply -p2`.
- Recipe PR:
  - It ADDS `patches/00NN-*.patch`: extract that file's added lines, then `git apply -p0`.
  - Its start.sh/config.sh plumbing goes in a recipe worktree: `git -C ~/mia15 worktree add --detach ~/mia-prN <sha>`, `git apply <pr.diff>`, copy `scripts/local.sh`.
- Use `git apply --check --verbose` and count the `^Checking patch` lines. Zero files checked is a vacuous pass: treat it as a FAIL.
- A conflict often means the recipe already carries the idea, so grep the tree for the PR's env knobs first (TF #397 = recipe PREFILL_OVERLAP=2; TF #396's RB=4 = recipe 0009).

## 3. Reachability probe before spending GPU time
- Insert `__import__("tensorfold._probe", fromlist=["hit"]).hit("<site>", rows)` before each PR-modified body.
  - Each anchor must match exactly once; if any does not, write nothing.
  - `_probe.hit` prints at hits 1, 2, 4, 8, ...
- Boot with the production settings, run the workload, then grep `\[probe\]` in `docker logs glm53-flash-tf` on all three ranks.
- No hits means the PR cannot change anything here (2026-10-06: TF #333's BF16 matmul never runs under DENSE=q4).

## 4. Build one arm image on all three ranks
- Build context:
  - `FROM <base>`.
  - One `COPY <file> /usr/local/lib/python3.12/dist-packages/<file>` per changed file.
  - `LABEL tf.patches=<label>`.
- Build on spark1 with `docker build`. On spark2/3: `tar -C ctx -cz . | ssh adam@sparkN.ots-int.net 'd=$(mktemp -d); tar -C $d -xz && docker build -q -t TAG $d'`.
- Cache folder keying:
  - start.sh keys the compiled-kernel AND KV-tier folder (`~/.cache/tensorfold-glm53/<KCACHE>`) on the label only when it is 12 hex digits; otherwise on the image id.
  - A new folder means a ~4 min kernel rebuild and an empty tier.
  - A Python-only arm may reuse its base's folder by taking the base's 12-hex label. Refuse that if any .cu/.cuh/.cpp/.h file changed.
- Proof: the sha256 of the changed files INSIDE each node's image must give one digest across all three nodes.

## 5. Run the arms unattended on spark1
- Before the window:
  - Run `systemctl --user stop glm-watchdog`.
  - Re-lock clocks on every boot: `systemctl --user restart glm-gpuclk` on each Spark.
  - Remote scripts run as files with `</dev/null`: stop.sh and start.sh ssh to the workers and eat stdin.
- Per arm:
  - Source the candidate env and export the overrides (IMAGE, TF_GLM_*, PARALLEL, ...). start.sh forwards every TF_GLM_/TENSORFOLD_/TF_ROCE_ variable to every rank.
  - Run `./stop.sh; ./start-tp3.sh`.
  - Then the measurement sections:
    - corr: firstreq (3 serial == 2 drafted) and draftcmp (7/7 SAME).
    - sdbench at 1/4/8 streams.
    - Sampling and concurrency probes, and the depth probe.
    - prefill_bench, 8k-262k, cold + resume.
    - tools/prompt_reuse.py.
    - agent_lanes.py 4 x 500k x 3 (~33 min).
    - Lowest MemAvailable per Spark, and the engine error count.
- Chain everything in one `setsid nohup bash campaign.sh </dev/null &`, with stages waiting on marker files.
- Batch reads into one ssh session, and poll `/health` over HTTP.
- ALWAYS include a base arm in the same campaign (same day, clocks and disk state). Never judge against doc numbers alone.
- Judging:
  - Replies must be identical (token sha / draftcmp) AND the metric the change claims must move.
  - sdbench 1-stream noise is ~1-2%; 4-stream aggregates swing 10-25% run to run.
  - `depth` uses random prompts, so compare ms/round, never tok/s. One run per depth is a hint, not a verdict.

## 6. Disk-tier changes
- Phases of `resume_phase.py`:
  - A: cold + warm.
  - B: clean restart.
  - C: eviction (TF_GLM_CACHE_ENTRIES=1).
  - D: SIGKILL crash.
  - Z1-Z2: never evicted, then SIGKILL. This separates write-when-kept designs from write-at-eviction ones.
- Judge by reply equality and server `prefill_s` < cold/3.
- Repo copies: glm5.3-flash-dev scripts/glm53/v18/resume_*.{sh,py}.

## 7. After
- Restore or switch production; bring the watchdog back and confirm it is `active`.
- Record each verdict with its numbers in docs/GLM53-SPARK-UPSTREAM-WATCHLIST.md.
- Remove arm images, worktrees and their cache folders. The folders are root-owned, so delete them via a container.
- Keep each Spark's ~/INVENTORY.md current.

Harness copies:
- spark1 ~/: prab_build.sh, probe_insert.py, diffsplit.py, arm_run.sh, qual_run.sh, campaign.sh, conc_probe.py, sample_probe.py, resume_*.sh, resume_phase.py.
- work/v18/ (scratch; may be cleaned).

# A/B upstream PRs on the GLM TP=3 Spark serve

Use when the owner asks whether upstream TensorFold (ashhart/TensorFold) or MiaAI-Lab recipe PRs, issues or settings would speed up the GLM-5.3-Flash serve on spark1-3. Gather the facts first; spend GPU time second.

## 0. Context that changes the answer
- TensorFold's Python engine is frozen (TF #286). Every GLM CUDA PR there is closed unmerged, so GLM speedups arrive only as recipe patches. A TF PR can only be tested by porting it ourselves.
- Survey through the unauthenticated GitHub API: 60 core requests an hour; search allows 10 a minute, so sleep 7 s between searches. Read the full issue or PR body (fetch the issue URL) before judging: list views truncate the measurement tables.

## 1. Classify before building (no GPU)
For each PR, in order:
1. Another model family (a path under families/qwen4_exp, qwen3_5_moe, ...)? Then N/A.
2. Already in the recipe? Grep ~/mia15-v18/patches/*.patch and the image tree for its env names and functions. Example: TF #397 is recipe 0033 TF_GLM_PREFILL_OVERLAP.
3. Does it apply? Check against the FULL package tree taken from the image, never a build-context tree (a partial tree gives a bogus "No such file"): `cid=$(docker create IMAGE); docker cp $cid:/usr/local/lib/python3.12/dist-packages/tensorfold tree/`, then git init and commit.
   - TF PRs are rooted at src/tensorfold: keep only the `diff --git a/src/tensorfold/` sections (`diffsplit.py src`) and run `git apply --check --verbose -p2`.
   - Recipe PRs ADD a patches/NNNN-*.patch file: extract it (`diffsplit.py added`) and apply it with -p0.
   - Count the "Checking patch" lines. A check that names 0 files is vacuous: treat it as a FAIL.
4. Is it reachable under production settings? Build a probe image with probe_insert.py and boot it:
   - Insert one hit-counter line before an anchor matched EXACTLY once, using a self-contained `__import__("tensorfold._probe", fromlist=["hit"]).hit(...)` so no import block is touched. It logs at hits 1, 2, 4, 8, ...
   - Run corr + samp + conc, then read the `[probe]` lines on every rank.
   - Measured examples: DENSE=q4 leaves no BF16 dense matmul (TF #333: 0 hits). KDA_CHUNKED=1 sends prompts to kda_chunked.chain, not step_kernel. The server's default top_k skips nucleus_rows, so send top_k 0 explicitly to test sampling PRs.
A PR that fails any of steps 1-4 gets its verdict with that evidence and no A/B.

## 2. Build arm images (no GPU, about 30 s)
- `prab_build.sh <arm>`: clone the tree and apply the patch. Every changed file becomes one COPY layer FROM the base image, built on spark1 and, via tar over ssh, on spark2 and spark3.
- Print the changed files' digest inside each node's image: all three must match.
- Kernel cache: start.sh mounts ~/.cache/tensorfold-glm53/<KCACHE>, where KCACHE is the tf.patches label if that is 12 hex digits, else the image id's prefix.
  - A Python-only arm can reuse its base's folder by taking that 12-hex key as its label.
  - Refuse the reuse when any .cu/.cpp/.cuh/.h file changed: the compiled kernels would be stale.
  - A new folder costs about 4 min of kernel builds and starts with an empty kv tier.

## 3. Measure (GPU window: needs the owner's go-ahead, it takes :8888 down)
- Stop the watchdog (`systemctl --user stop glm-watchdog`), then start a detached chain on spark1: `setsid nohup bash ~/campaign.sh </dev/null >/dev/null 2>&1 &`.
- Each arm boots fresh through `arm_run.sh <label> <sections> [VAR=VAL...]`: it re-locks the GPU clocks, runs stop.sh, then start-tp3.sh with the overrides.
- Then `qual_run.sh` runs the chosen sections:
  - corr: firstreq + draftcmp; replies must be identical.
  - sd/sd4/sd8: sdbench, the sparkDash protocol.
  - samp, conc, conc8, depth, prefill, reuse.
  - agents: 4 x 500k x 3 turns.
- Every rank's lowest MemAvailable and the engine error count are recorded. Always run a base arm the same night.
- Disk-tier A/B:
  - `resume_ab.sh <arm>` runs resume_phase.py phases A (cold + warm), B (clean restart), C (eviction, TF_GLM_CACHE_ENTRIES=1) and D (SIGKILL every rank).
  - `resume_crash.sh` runs Z1/Z2 (a never-evicted conversation, then a crash). This is the case that separates a write-through tier (0071) from write-at-eviction (#78 spill).
  - Judge only by reply equality and the server's own prefill_s.
- Compare like with like: ms/round across different random prompts is confounded by draft acceptance (a round is longer when more drafts land). Compare ms/token, or rerun on the same prompt.

## 4. Gotchas
- Never pipe a script into bash over ssh: stop.sh and start.sh ssh to the workers and eat the rest of stdin. Write the file, `tr -d '\r'`, and run it with </dev/null.
- UniFi IDS throttles bursts of SSH sessions to the Sparks; the owner suppressed it for the laptop on 2026-10-06. Still batch reads into one session and poll /health over HTTP during long runs.
- Restore production afterwards: the stack's GLM_START (spark-model glm start), restart the watchdog, check `is-active`.

## 5. Output
- A verdict table, one row per PR: applies / reachable / same bits / metric delta vs base / decision, plus the logs path (spark1 ~/qual/).
- Winners are folded into scripts/glm53/v18/ as patches that build_v18.sh builds.

## Files
- spark1: ~/{arm_run.sh, qual_run.sh, campaign.sh, conc_probe.py, sample_probe.py, prab_build.sh, probe_insert.py, diffsplit.py, resume_phase.py, resume_ab.sh, resume_crash.sh} and ~/prab/{tier,notier,upstream,diffs}.
- Repo: glm5.3-flash-dev scripts/glm53/v18/ (resume_*, verify_v18.sh, build_v18.sh).
- Laptop scratch: work/v18/ and work/gh_*.py.

# A/B upstream changes on the GLM TensorFold serve (3 Sparks)

Use when asked whether a TensorFold PR, a MiaAI recipe PR/patch or an env knob helps OUR serve (TP=3, DENSE=q4, PARALLEL 4, RoCE, kindling spark-os). Syncing to a new recipe release is a different job (recipe-sync skills).

## 0. Context that decides most verdicts
- ashhart/TensorFold's Python engine is FROZEN (#286, since 0.6.5). GLM CUDA perf PRs are closed unmerged; they reach us only via MiaAI recipe patches or our own build. Many community GLM PRs re-implement recipe patches we already carry (TF #397 = recipe 0010/0033, `TF_GLM_PREFILL_OVERLAP=2`).
- Survey with the unauthenticated GitHub REST API (60 req/h core, 10/min search: sleep 7 s between searches). When it rate-limits (403), read the PR page with the read tool. Scripts: `work/gh_upstream.py` (releases, tags, commits, open/closed PRs, issues), `gh_details*.py` (bodies + last comments).

## 1. Baseline the live serve first (read-only)
- `sample_probe.py <base_url>`: greedy vs sampled (temp/top_p, with and without `top_k: 0`) decode tok/s, ms/round and reply sha.
- `conc_probe.py <base_url> conc | conc8 | depth N...`: 1 vs 4 (vs 8) aggregate; 4 cold 16k prompts at once (take-turns check); ms/round by context depth. Use a FIXED seed when comparing depth across arms: a random prompt changes tokens/round and therefore ms/round.

## 2. Fetch and apply-check against the FULL package tree
- Diff: `curl -L https://github.com/<repo>/pull/N.diff`. TensorFold PRs are rooted at `src/tensorfold/`: keep only `diff --git a/src/tensorfold/` sections (`diffsplit.py src`) and apply `-p2`. Recipe PRs ADD a patch file: extract it (`diffsplit.py added`) and apply `-p0` onto the package root (paths `tensorfold/...`). OTS patches in `scripts/glm53/v18/` are `-p1`.
- Trees: the package exactly as each image carries it: `cid=$(docker create IMG); docker cp $cid:/usr/local/lib/python3.12/dist-packages/tensorfold DIR/; docker rm $cid`, then `git init` + commit. A build-context tree holding only patched files gives false "No such file" conflicts.
- `git apply --check --verbose`: count the `Checking patch` lines. 0 files checked is a VACUOUS pass: treat it as a fail.

## 3. Prove the PR's code path RUNS under production settings before building its arm
- `probe_insert.py <tree>` adds `tensorfold/_probe.py` and one `__import__("tensorfold._probe", fromlist=["hit"]).hit('site', rows)` line before an exactly-once anchor in each function the PR changes; it writes nothing if any anchor matches 0 or 2+ times. Hits print at 1, 2, 4, 8, ... as `[probe]` lines.
- Build it as a Python-only arm (step 4), boot, run the workload (corr, samp, conc, prefill), then `docker logs glm53-flash-tf | grep '\[probe\]'` on EVERY rank.
- 2026-10-06 results: TF #333 (`qmm._matmul_b16`) never hit (DENSE=q4 converts the BF16 dense weights); TF #396's non-mma absorb/expand only ran on 15-row decode windows, which the PR keeps unchanged (<64 rows). Both no-ops, no arm needed. Requests without `top_k` never reach `sampling.nucleus_rows`.

## 4. Build one image per arm on all three serve nodes
- `prab_build.sh <arm>`: clone the full tree, apply, `git add -A && git diff --cached --name-only` = files to COPY. Dockerfile = `FROM <base>` + one `COPY` per changed file + `LABEL tf.patches=<label>`. Build on spark1 locally and on spark2/3 via `tar -C ctx -cz . | ssh adam@sparkN.ots-int.net 'd=$(mktemp -d); tar -C $d -xz && docker build -q -t TAG $d'`. Then sha256 the changed files INSIDE each node's image: the digest must match on all three.
- Kernel cache: start.sh mounts `~/.cache/tensorfold-glm53/<KCACHE>:/cache`, KCACHE = the `tf.patches` label if it is 12 hex digits, else the image id's first 12. A Python-only arm reuses its base's compiled kernels by carrying the base's 12-hex label (refuse if any .cu/.cpp/.cuh/.h changed). A compiled-source arm needs a non-hex label: new folder and a ~4 min kernel build on first boot. The NVMe tier dir (`/cache/kvtier`) lives in that folder too, so a label change also starts the tier empty.

## 5. Run arms back to back, detached, each from a fresh boot
- Stop the watchdog first (`systemctl --user stop glm-watchdog`); production is down for the campaign, so tell the owner. Restart it when production is back.
- `arm_run.sh <label> <sections> [VAR=VAL ...]`: source the candidate env (`~/v18tier.env` in the 2026-10-06 campaign; production is `~/v18ots.env`), export the overrides (`IMAGE=`, `TF_GLM_*`, `PARALLEL=`...), re-lock GPU clocks on every rank (`systemctl --user restart glm-gpuclk`), `stop.sh`, `start-tp3.sh </dev/null`, then `qual_run.sh 8888 <label> <sections>`; collects `[probe]` lines from all ranks.
- `qual_run.sh` sections: `corr` (firstreq + draftcmp: drafted == serial 7/7), `sd`/`sd4`/`sd8` (sdbench, sparkDash protocol), `samp`, `conc`, `conc8`, `depth`, `prefill` (prefill_bench + resume), `reuse` (tools/prompt_reuse.py), `agents` (agent_lanes.py 4 x 500k x 3). It samples every node's MemAvailable and reports the lowest, plus the engine error count.
- `campaign.sh`: one `run <arm> <sections> [overrides]` line per arm; waits for the previous stage's marker file; appends start/done lines to `~/qual/campaign.log`. Launch `setsid nohup bash ~/campaign.sh </dev/null >/dev/null 2>&1 &`. Read ALL results in ONE ssh session (UniFi IDS rate-limits rapid SSH; poll `/health` over HTTP instead).
- NEVER pipe a script into a remote bash over stdin: stop.sh/start.sh ssh to the workers and eat the rest. Copy the file (scp, or base64 to a file + `tr -d '\r'`) and run it with `</dev/null`.

## 6. Disk-tier A/B (0071 kv tier vs any other tier)
- `resume_phase.py` judges any tier the same way: the greedy reply must equal the first run's; speed from the server's own `prefill_s` / cached tokens. Phases: A cold+warm; CLEAN restart (stop.sh) -> B; eviction with `TF_GLM_CACHE_ENTRIES=1` -> C; CRASH (`docker kill -s KILL` on every rank) -> D; Z1/Z2 = a conversation that is NEVER evicted, then a crash. Z separates write-when-kept tiers (0071) from write-at-eviction / clean-stop tiers (recipe PR #78).
- Drivers: `resume_ab.sh <tier|spill>`, `resume_crash.sh <tier|spill>`.

## 7. Verdict
- Gates: identical firstreq digests and draftcmp SAME 7/7; engine errors 0; head lowest MemAvailable >= ~4 GiB; decode/prefill vs base beyond noise (sdbench structured varies up to ~6% run to run; prose/code ~1%).
- Rank by the owner's workload wall time (650k agent sessions: cold prefill, resume and restart dominate), never by per-step ms alone.
- Record each verdict (and the probe evidence) in `docs/GLM53-SPARK-UPSTREAM-WATCHLIST.md`.

## Locations
- Scratch (transient): `work/` (gh_*.py, sample_probe.py, conc_probe.py) and `work/v18/` (prab_fetch.sh, diffsplit.py, prab_prep3.sh, probe_insert.py, prab_build.sh, arm_run.sh, qual_run.sh, campaign.sh, resume_*). spark1: same names in `~`, package trees in `~/prab/{upstream,notier,tier,diffs}`, logs in `~/qual/`.
- Durable: glm5.3-flash-dev `scripts/glm53/v18/` (build_v18.sh, verify_v18.sh, nvme_restart_test_v18.sh, resume_phase.py, resume_ab.sh, resume_crash.sh). If the scratch harness is gone, rebuild it from sections 2-6.

# A/B-test upstream TensorFold / MiaAI recipe PRs on the GLM-5.3-Flash Spark serve

Use when the owner asks to try unmerged upstream PRs, opt-in flags or alternative patches against the production GLM serve (spark1-3 TP=3, :8888). Not for recipe version syncs.

## Ground rules
- TensorFold's Python engine is frozen (TF #286): GLM CUDA PRs are closed unmerged but still apply to the v0.6.0 base. They are A/B candidates, not upstream direction.
- Owner rule: stay close to upstream. A PR goes in only with a measured win on the owner's workload (long agent contexts, restart/resume) and the same bits (drafted == serial; greedy replies identical).
- Stop the watchdog for the whole campaign (`systemctl --user stop glm-watchdog`). Restore production and the watchdog at the end, or when abandoning.

## 1. Trees and diffs (spark1, no GPU)
- Take FULL package trees from the images, never the partial build context: `cid=$(docker create IMAGE); docker cp $cid:/usr/local/lib/python3.12/dist-packages/tensorfold DIR/; docker rm $cid`. Then `git init` and commit each tree (upstream base, candidate, no-tier variant).
- Fetch a PR diff with `curl -sSL https://github.com/<owner>/<repo>/pull/<n>.diff`.
  - ashhart/TensorFold PRs are rooted at `src/tensorfold/`. Keep only the `diff --git a/src/tensorfold/` sections (split on `^diff --git`) and apply with `-p2`.
  - MiaAI recipe PRs ADD `patches/NNNN-*.patch` (plus start.sh/config.sh plumbing). Extract the added file's `+` lines and apply them with `-p0`. Apply the whole PR diff to a recipe worktree (`git worktree add --detach ~/mia-prN <v1.8 sha>`) to get its launcher plumbing.
- Apply-check with `git apply --check --verbose` and count the `Checking patch` lines; 0 counts as a FAIL. Never combine `--include` with `-p`: the pattern matches the post-strip path, so it silently matches nothing and passes.

## 2. Reachability before any A/B
- Many GLM PRs speed up paths that the production settings never run (TF_GLM_DENSE=q4, TF_GLM_KVB, TF_GLM_KDA_CHUNKED=1, ...). Build a probe arm first:
  - Insert one hit-counter line before an anchor in each changed function. The anchor must match exactly once, else write nothing.
  - Use `__import__("tensorfold._probe", fromlist=["hit"]).hit(...)` so no import block is edited.
  - Boot with the production settings, run the workload, and read the `[probe]` lines in every rank's docker log.
- Code that is never reached needs no A/B; report it with the probe evidence.

## 3. Arm images (all three serve nodes)
- Dockerfile: `FROM <base>`, one `COPY` per changed file to `/usr/local/lib/python3.12/dist-packages/<path>`, then `LABEL tf.patches=<x>`.
- KCACHE: start.sh mounts `~/.cache/tensorfold-glm53/<KCACHE>`. KCACHE is the tf.patches label if it is exactly 12 hex digits, else the image id's first 12.
  - A Python-only arm takes the base's 12-hex folder name as its label: it reuses the compiled kernels, with no ~4 min rebuild.
  - Any .cu/.cpp/.cuh/.h change needs a non-hex label: a fresh folder, where the kernels rebuild. Refuse to reuse the base's folder.
- Build locally on spark1 and on spark2/3 via `tar -C ctx -cz . | ssh adam@sparkN.ots-int.net 'd=$(mktemp -d); tar -C $d -xz && docker build -q -t TAG $d'`. Verify that every node's image gives the same sha256 over the changed files.

## 4. Campaign (detached on spark1)
- Each arm, in order:
  1. Re-lock the clocks (`systemctl --user restart glm-gpuclk` on each node).
  2. `./stop.sh </dev/null`.
  3. `IMAGE=... <overrides> ./start-tp3.sh </dev/null` from the recipe dir.
  4. Run the measurement sections.
- Chain the arms in one script started with `setsid nohup bash campaign.sh </dev/null >/dev/null 2>&1 &`; a sentinel file marks completion.
- Never pipe a script into bash over ssh: start/stop ssh to the workers and eat stdin. Always add `</dev/null`.
- Poll with SHORT ssh sessions every few minutes. One ssh held open for ~25 min was reset by peer.
- Correctness first on every fresh boot:
  - firstreq.py: serial x3 and drafted x2 give one digest.
  - draftcmp.py: 7/7 SAME.
- Match the metric to the PR's claim:
  - prefill: prefill_bench.py (cold 8k/32k/131k/262k + resume)
  - decode: sdbench.py 1/4/8 streams (the sparkDash protocol)
  - sampling: sample_probe.py (ms/round, greedy vs temperature/top_p)
  - long-context round cost: `conc_probe.py <url> depth 2000 64000 200000`
  - concurrency: conc_probe.py conc / conc8
  - agent workload: agent_lanes.py 4 500000 3
  - memory: the lowest MemAvailable per node

## 5. Disk-tier comparisons (0071 kvtier vs recipe #78 spill)
- Judge any tier the same way with resume_phase.py: reply equality, the server's `prefill_s` and the cached tokens.
- Phases:
  - A: cold, then warm
  - B: after a clean restart
  - C: after an eviction (TF_GLM_CACHE_ENTRIES=1)
  - D: after `docker kill -s KILL` on every rank, following an eviction
  - Z1/Z2: a conversation kept and never evicted, then SIGKILL. This case separates write-on-keep (0071) from write-on-evict/clean-stop (#78).
- Tier files are root-owned. Empty them with `docker run --rm -v <dir>:/cache --entrypoint rm <image> -rf /cache/<sub>`.

## 6. Close out
- Restore production:
  1. Kill the campaign scripts (`pgrep -fa 'campaign.s[h]|arm_run.s[h]'`).
  2. `bash -lc "spark-model glm start" </dev/null`.
  3. `systemctl --user restart glm-watchdog` and verify it is `active`.
- Remove the arm images, trees and kernel/tier folders, and update each Spark's `~/INVENTORY.md`.

## Files
- Scratch author copies: work/v18/ (prab_fetch.sh, prab_prep3.sh, diffsplit.py, probe_insert.py, prab_build.sh, arm_run.sh, qual_run.sh, campaign.sh, resume_phase.py, resume_ab.sh, resume_crash.sh) and work/{gh_upstream,sample_probe,conc_probe}.py. Box copies are in spark1's `~`.
- glm5.3-flash-dev: scripts/glm53/v18/ (build_v18.sh, resume_ab.sh, resume_crash.sh, resume_phase.py, verify_v18.sh, nvme_restart_test_v18.sh); scripts/glm53/tp3/ (firstreq, draftcmp, sdbench, prefill_bench, nvme_phase); scripts/glm53/agent_lanes.py.

# A/B upstream PRs and settings on the TensorFold GLM serve (TP=3)

Use when the owner asks for upstream speed-ups, says "try those PRs", or a MiaAI-Lab recipe release, TensorFold PR or issue claims a GLM-5.3-Flash gain. Stack: spark1-3 at TP=3, recipe tree on spark1 (`~/mia15-v18` for v1.8), production SSOT `docs/GLM53-FLASH-PRODUCTION-STACK.md` in glm5.3-flash-dev.

## 0. Survey, then measure the claim on the live serve (read-only)
- Sources: `MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold` and `ashhart/TensorFold`: releases, commits, open and recently closed PRs, open issues. The unauthenticated GitHub API allows 60 req/h (search 10/min). On a 403, read the PR page with the web reader or fetch `https://github.com/<repo>/pull/<n>.diff`, which is not API-limited.
- TensorFold's Python engine is frozen (TF #286, 2026-10). GLM CUDA perf PRs there are closed unmerged, so GLM gains arrive only as recipe patches. Check whether a TF PR re-implements a recipe patch we already run.
- Reproduce the issue's claim on the LIVE serve before building anything (`sample_probe.py <url>`, `conc_probe.py <url> conc|conc8|depth N..`). Several claims (recipe #91, TF #259) did not reproduce here.

## 1. Apply-check against the FULL package tree
- `cid=$(docker create IMG); docker cp $cid:/usr/local/lib/python3.12/dist-packages/tensorfold DIR/; docker rm $cid`, then `git init` + commit. A tree holding only the files the OTS image COPYs gives false "No such file" conflicts.
- TF PRs: keep only the `src/tensorfold/` sections of the .diff, then `git apply --check --verbose -p2`. Recipe PRs add `patches/NNNN-*.patch`: extract the added file whole and apply it with `-p0` (its paths start `tensorfold/`).
- Count the `Checking patch` lines. 0 means the check proved nothing; treat it as a failure.

## 2. Reachability probe before any perf A/B
- Probe image: one hit counter at each site the PR changes, as a self-contained `__import__("tensorfold._probe", fromlist=["hit"]).hit(site, rows)` that logs at hits 1, 2, 4, 8 and so on. Every anchor must match exactly once, else write nothing. It is Python-only, so it shares the base's kernel cache (step 3).
- Boot with PRODUCTION settings and run correctness, sampling and concurrency. Then grep ALL `[probe]` lines on all three ranks. Never use `tail`: the first hits print first and get cut.
- Code that never runs under our settings cannot help, so give the verdict without building the arm. For partially reached code, read which branch each hit takes (for example the mma vs non-mma path).

## 3. Build arm images
- An arm is `COPY` layers over the base image, built on spark1/2/3 from one context. Confirm the changed files' sha256 digest is identical on every node. `scripts/glm53/v18/build_v18.sh` is the production form.
- Kernel cache: `start.sh` mounts `~/.cache/tensorfold-glm53/<KCACHE>`. KCACHE is the `tf.patches` label ONLY if it is 12 hex digits, else the image-id prefix. A new folder means a ~4 min kernel build and an EMPTY NVMe kv tier. A Python-only arm takes the base's 12-hex label; refuse that if any `.cu/.cuh/.cpp/.h` changed.

## 4. Run the arms
- `systemctl --user stop glm-watchdog` first; restart it after and check it reports `active`. The stop and start scripts ssh to the workers and eat stdin: always run them with `</dev/null`, and never pipe a script into bash. Re-lock the clocks per arm (`systemctl --user restart glm-gpuclk` on each Spark).
- Chain the arms detached ON spark1 (`setsid nohup bash campaign.sh </dev/null &`), each from a fresh boot, with stages waiting on marker files. Read the results in ONE ssh session and poll `/health` over HTTP. The UniFi IDS throttles bursts of ssh sessions; Adam's laptop is exempted, but batch anyway.
- Every arm starts with `firstreq.py` (immediately after boot) and `draftcmp.py` (drafted == serial 7/7). Then measure only what the PR claims:
  - `sdbench.py` at 1/4/8 streams
  - `prefill_bench.py`
  - `conc_probe.py depth` (ms/round at 2k/73k/229k)
  - `sample_probe.py`, including `top_k: 0` cases (the server's default top_k never reaches the nucleus path)
  - `agent_lanes.py <label> 4 500000 3` for headroom, recording each Spark's lowest MemAvailable
- Use FIXED prompts for per-round comparisons: random filler per run changes draft acceptance and confounds ms/round. Finalise the probe and bench set BEFORE the base arm. A change mid-campaign leaves the new cases without a baseline.
- Settings-only arms need no image: env overrides over the candidate env (`arm_run.sh LABEL SECTIONS VAR=VAL ...`).

## 5. Disk-tier comparisons
- `resume_ab.sh tier|spill`: cold and warm turns, a clean restart, eviction (`TF_GLM_CACHE_ENTRIES=1`), then a crash (`docker kill -s KILL` on every rank). Replies must be byte-identical.
- `resume_crash.sh`: a never-evicted state, then SIGKILL. This separates write-through tiers (OTS 0071) from write-at-eviction tiers (recipe #78).
- Both scripts are in glm5.3-flash-dev `scripts/glm53/v18/`.

## 6. Verdict and record
- Per PR: applies? reached? same bits? delta vs run-to-run noise? cost in pool tokens and head MemAvailable?
- Verdicts go into `docs/GLM53-SPARK-UPSTREAM-WATCHLIST.md`, production changes into the production stack doc. `bash scripts/check-doc-inventory.sh` must be clean, and every Spark's `~/INVENTORY.md` updated for every image or dir added or removed.

## Gotchas
- Upstream `DISPLAY_KV_MIB` (recipe 0072) fails on kindling spark-os: `DRM_IOCTL_MODE_CREATE_DUMB` returns ENOSYS. The OTS backend is `TF_GLM_DISPLAY_KV_BACKEND=dispram` (`0072-glm-dispram-display-kv.patch`, using `dispram.map_glued`) plus `recipe-dispram-display-kv.patch` (mounts `/run/dispram` and the client, skips the DRM guards). Check the production doc for its GPU validation status.
- Bench helpers in the repo: `scripts/glm53/tp3/{firstreq,draftcmp,sdbench,prefill_bench,nvme_phase}.py` and `scripts/glm53/agent_lanes.py`.
- These live only in scratch, `work/v18/` and `work/`, plus spark1 `~`: `prab_build.sh`, `probe_insert.py`, `diffsplit.py`, `arm_run.sh`, `qual_run.sh`, `campaign.sh`, `sample_probe.py`, `conc_probe.py`. Copy them into the repo before relying on them long-term.

# A/B a Qwen lever on upstream TensorFold (spark6)

Use when a lever has been ported onto ashhart/TensorFold main and needs byte-identity plus a 1/2/4/6 A/B against stock on spark6, which also runs the production Qwen serve and may host other lanes.

## Build
- Worktree off `~/work/lanes/up-pr/tf` (one change per branch). Stock and lever arms MUST come from the same upstream tip: rebuild stock whenever the branch is rebased.
- `cd ~/work/merge && ./build-br.sh TAG git://192.168.99.16/<lane>/tf <FULL 40-char sha>` (git daemon on :9418 serves `~/work/lanes`; a short sha fails the fetch).
- Relabel for the recipe launcher: `echo "FROM tensorfold-qwen38:TAG" | docker build -q --label tf.kernels=embedded -t tensorfold-qwen38:TAG -`.
- The host suite never compiles `.cu`: an image build + boot is the only check of kernel instantiations and mangled symbol names.

## Boot settings for stock upstream 1.2.4
Through the v1.1.4 recipe's `start.sh` (`~/work/lanes/rpr/recipe`): `PREPARE=0 IMAGE=... CHECKPOINT=nvfp4 VISION=0 KV_DTYPE=bf16 CONTEXT=131072 HOST=127.0.0.1`. Its Flash Next refuses `--kv-cache fp8`; 8 streams do not fit at bf16 (32.86 GiB needed vs 31.41), so measure 1/2/4/6 and say so. Recipe v1.1.4 refuses INT4-AutoRound.

## The window (the lock holder owns serve AND sparkDash)
1. From the session (spark6 cannot reach proxmox): `ssh root@proxmox.ots-int.net 'systemctl list-timers "sparkdash*" --all'`; refuse to start if a timer you did not arm is pending. Stop sparkDash: `pct exec 111 -- systemctl stop sparkdash`; arm a uniquely named delayed restart and clear only your own.
2. On spark6: `(cd ~/qwen-zig && ./stop.sh)`; the serve's lock holder follows the container and frees `~/work/gpu.lock` within ~10 s. Take `flock ~/work/gpu.lock` for the whole run; never kill another lane's process.
3. Cells via `~/work/lanes/par114/arm.sh ARM C` with your own `RUNS_DIR`; template driver `par114/abq.sh`. Fresh boot per cell, ABBA per level, two boots where the expected gain is under the ~4% boot spread.
4. Gates per cell: golden 6/6 against STOCK's own replies (`zgold-up124.json`; the 1.0.0 INT4 reference differs by quant), recipe `tools/exact.py`, every rewrite/edit reply sha equal between arms, SOURCES line 127.0.0.1 only, GPU temp per window.
5. Restore on every exit path, guarded: only if the lock is free (`flock -n ~/work/gpu.lock true`), `setsid nohup ~/qwen6-start.sh > ~/qwen6-boot.log 2>&1 < /dev/null &`, prove `/health`, then start sparkDash from the session.

## Traps measured
- `pkill -f`/`pgrep -f` self-match the ssh command line: use `pgrep -f X | grep -vw $$`.
- Never inline a multi-minute pipeline behind one ssh timeout; run it detached and watch with bounded commands.
- Files written by Windows Python carry CRLF: write with `newline="\n"` and `sed -i 's/\r$//'` before deploying.
- `tfm_decode.py` rotates prompts per pass and adds a nonce: reply shas are not comparable across passes, only across arms per prompt.
- Two boots with opposite signs is an unresolved bound (~+-2%), not a no-regression claim; word PR text that way.
