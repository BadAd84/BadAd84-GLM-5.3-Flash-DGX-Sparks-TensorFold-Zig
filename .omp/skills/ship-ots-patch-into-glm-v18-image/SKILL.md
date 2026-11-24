---
name: ship-ots-patch-into-glm-v18-image
description: "Use when adding or regenerating an OTS patch (scripts/glm53/v18/00NN-*.patch) for the TensorFold GLM-5.3-Flash v18 production image on spark1-3: in-image CPU tests, mutants, offline speed checks, build with a rollback tag, idle-gated restart, byte-identity post-check, docs."
---

# Ship an OTS patch into the GLM v18 production image

The production image `tensorfold-glm53:v18-ots` is the upstream image `tensorfold-glm53:v0.6.0-31557ed1` plus glm5.3-flash-dev's `scripts/glm53/v18/0*.patch`.
- `scripts/glm53/v18/build_v18.sh`, run on spark1, applies the patches in name order with `git apply -p1` (paths `a/tensorfold/...`).
- It builds the image on spark1-3 and adds a `tf.ots-patches` label holding each patch's sha256 prefix.
- Upstream recipe patches differ: they use `patch -p0` against site-packages (no `a/` or `b/` prefix).

## 1. Write the patch
- Take the files from the PRODUCTION image, not from a local source copy:
  `cid=$(docker create tensorfold-glm53:v18-ots); docker cp -q $cid:/usr/local/lib/python3.12/dist-packages/tensorfold/<path> <dir>; docker rm $cid`.
- Generate the patch in a throwaway git repo using `-c core.autocrlf=false`:
  1. init the repo and commit the base files;
  2. copy the edits in;
  3. `git diff --cached > 00NN-name.patch`.

  Then check that `grep -c $'\r'` prints 0.
- To regenerate an existing patch (0071 gained the free-disk floor this way):
  1. apply upstream, then the old patch;
  2. replace the file;
  3. diff from upstream;
  4. `git apply` every later patch on top, to prove the order still holds.
- Where upstream code exists, backport it verbatim: 0074 took TensorFold PR #262's `server/loop_guard.py` unchanged. Wire it into the path production actually runs: the CUDA server's gates (the gates list in `cuda/server.py`, and `engine/call_gate.py`).
- The root filesystem on kindling Sparks lacks tools such as `patch`, so run them inside the image.

## 2. Test on CPU inside the image
- Mount the patched tree over the installed package:
  `docker run --rm --network none -e CUDA_VISIBLE_DEVICES= -v $TREE/tensorfold:/usr/local/lib/python3.12/dist-packages/tensorfold:ro --entrypoint python3 tensorfold-glm53:v18-ots /t.py`.
- Drive the production entry point, not only the helper. Production builds `GlmApp` (`families/glm5_next/cuda/app.py`), whose `run` delegates to `App.run` (`cuda/server.py`).
  - A scripted fake engine needs: `generate(ids, count, sampling, feed, **kw)`, `eos`, `concurrent=False`, `tp=3`, `vision=None`, and `request=SimpleNamespace(policy=None, stop_eos=True)`.
  - Give `GlmApp` a `Path` model dir; a str breaks `model_dir / "tokenizer.json"`.
  - Mount `~/.cache/huggingface` read-only so the test uses the real tokenizer and chat template.
  - Example: `scripts/glm53/v18/test_loop_guard_app.py`.
- Mutants (`mutants_0074.sh`, `mutants_0071.sh`):
  - each anchor must match exactly once, otherwise report ERROR;
  - count a mutant KILLED only on a `FAIL` line;
  - a run with no FAIL line and no "all passed" CRASHED; it is never a survival;
  - mutate the wiring too (gate dropped, arming removed, counter removed), not just the helper.

## 3. Measure speed patches without downtime
- **Kernel constants:** load the production image onto the free GB10 (spark5), from spark1 under `ssh -A`:
  `docker save tensorfold-glm53:v18-ots | ssh adam@spark5 docker load` (~6 min).
  Then time the engine's own kernels with CUDA-graph replays at production shapes and compare output bits (`dsa_index_bench.py`, `dsa_index_tune.py`, `dsa_index_matrix.py`).
- **Per-request knobs need no restart:** `tf_policy` in the request body picks the DFlash2 draft policy (`policy_ab.py`). Seeded replies are identical across policies, so only speed differs.
- **Decode comparisons:** use only fixed prompts with identical replies (`sdbench.py`, or `longdec.py` cold then decode-only).
- **Host profiles:** cover the whole decode and drop idle samples (`longhost.sh`, `pyspy_agg.py --busy`).

## 4. Build with a rollback
- First tag the running image on all three nodes:
  `docker tag tensorfold-glm53:v18-ots tensorfold-glm53:v18-ots-<pre>`.
  Keep the old `~/v18ots.env` and `~/glm-v18-start.sh` beside the new ones.
- Copy `build_v18.sh` and every `0*.patch` to `~/v18-build` on spark1 and strip CRs. Run it under `ssh -A` (it ssh-es to spark2/3), then check that the three "files digest" lines match.
- New serve flags go in `OTS_SERVE_ARGS` in `~/v18ots.env`; `glm-v18-start.sh` passes them to `start-tp3.sh`.
  - Check them first in the new image with `build_parser().parse_args(...)`.
  - The recipe also parses flags in a throwaway container before it stops anything.
  - An old image rejects a new flag, so rollback = the old image AND `OTS_SERVE_ARGS=""`.

## 5. Restart only when idle
- Command, on spark1 (repo copy `scripts/glm53/v18/restart_when_idle.sh`):
  `setsid nohup ~/restart_when_idle.sh <label> <max_wait_s> <post-check cmd...> >/dev/null 2>&1 </dev/null &`
- What it does:
  1. waits for three idle `/health` samples;
  2. stops the watchdog;
  3. runs `spark-model glm stop` and waits until the old serve stops answering;
  4. runs `spark-model glm start` and waits for health 200 (~2 min);
  5. starts the watchdog;
  6. runs the post-check.

  Log: `~/prof/restart-<label>.log`.
- Two bugs hit its first run:
  - a setsid shell has no `~/.local/bin` on PATH (`spark-model: command not found`);
  - a `/health` check right after a failed stop sees the OLD serve's 200 and reports success.

  Wait for health to go DOWN before waiting for it to come UP.
- A restart still cuts agents' in-flight requests (a Paperclip agent went to `error`). Idle gating is a window, not a lock; when production is in use, restart only in an owner-chosen window.

## 6. Post-check, then record
- **Running config:** `docker inspect glm53-flash-tf` shows the image id, `.Args` containing the flag, and the `tf.ots-patches` label.
- **Byte identity:**
  - send a greedy thinking-on request with `return_token_ids: true` and compare its `tensorfold.token_sha` before vs after (`~/ref_reply.py` on spark1);
  - `verify_v18.sh`'s `firstreq.py` / `draftcmp.py` check drafted == serial.
- **Docs:**
  - `docs/GLM53-FLASH-PRODUCTION-STACK.md`: the provenance sha list, the settings table, the section 3 bullet, and the v18 file list (name every new script); mark staged-but-not-live items as such;
  - a ledger row in `docs/GLM53-TENSORFOLD-TP3-PORT.md`;
  - `~/INVENTORY.md` on spark1-3 (rollback tag, scratch files).
- **Live state:** run `work/v18/spark_probe.sh` on spark1 from a top-level call, then `work/regen_spark_state.py <probe> docs/spark-live-state.json`. The repo's `refresh-spark-state.sh` cannot reach the YubiKey agent from a harness child process.
- **Gates:** `scripts/check-doc-inventory.sh` and `scripts/check-python.sh`. The latter runs pyflakes, which reports undefined names when a module-level loop `del`s names that a lambda captures; put such loop bodies in a function.
- Copying a tree from Windows with `tar` drops exec bits: `chmod +x` the scripts after extracting on a Spark, or they exit 126.
