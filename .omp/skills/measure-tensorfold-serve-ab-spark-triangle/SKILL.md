---
name: measure-tensorfold-serve-ab-spark-triangle
description: "A/B a TensorFold-family serve (ai-engine/GLM) on the spark4-6 triangle with the engine's own Prometheus counters - drafter variants, kernel knobs, shard changes; includes the five traps that waste a 20-minute build"
---

# A/B a TensorFold-family serve on the spark4-6 dev triangle

Use for any speed or numerics A/B on the DGX Spark dev triangle (spark4 rank 0, spark5 rank 1, spark6 rank 2), where the pairing must be measured with the engine's own counters rather than a guess.

## 0. Preconditions and ground rules
- `ssh` from WINDOWS: `export SSH_AUTH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg`. spark4 reaches spark5 and spark6; it CANNOT reach spark1, and spark1 cannot reach 4/5/6 (relay through the laptop or fetch from the internet).
- Every cell takes `flock -o ~/work/gpu.lock`; `./stop3.sh TAG` tears down r0/r1/r2 and is NOT conditional, so never run two chains at once - they kill each other's serve mid-measurement.
- Never edit a script that is already running: bash has parsed its functions. Patch, kill by PID, relaunch.

## 1. Launcher with the env hook (serve4.sh)
`serve3.sh` is the world-3 launcher; a copy with two extra lines becomes `serve4.sh`:
- after the SERVE array: `read -r -a XS <<< "${XSERVE:-}"; SERVE+=("${XS[@]}")` so serve flags (e.g. `--metrics-open`, `--drafter /dflash2`) can be added per arm;
- the rank-1/2 ssh lines must launch `serve4.sh` AND pass `XSERVE='${XSERVE:-}'` through, otherwise only rank 0 gets the flag;
- **`serve4.sh` must exist on spark5 and spark6 too** (it launches itself there). Copy it before the first run or the ranks never start and rank 0 dies with `RankNeverCame`.
- Extra host paths must be MOUNTED: add `-v "$HOME/dflash2:/dflash2"` to the docker run line and pass the container path (`--drafter /dflash2`), because only `~/.cache/huggingface` and `~/.cache/tf-up` are mounted by default. Symptom of a missing mount: `/home/adam/dflash2 is neither a directory nor a Hugging Face repo id`.

## 2. The counter instrument (the only honest way to read draft behaviour)
The engine's counters are NOT on `/health`. They are Prometheus gauges on `/metrics`, and that route needs `--metrics-open` in the serve flags: `decode_rounds_total`, `mtp_drafted_total`, `mtp_accepted_total`, `generation_tokens_total`. Parse lines as `k.rstrip().rsplit(' ', 1)` and strip the `tensorfold:` prefix. Assert the keys are present before trusting a zero.
- `streams.py` must be given `--out <file>`; without it the run fails silently inside `subprocess.run(capture_output=True)` and every counter delta reads 0. Always log the return code and stderr.
- Reference numbers for GLM-5.3-Flash at TP=3, P=1, prose: production 3.23 drafted/round, 2.06 accepted (63.8%), 3.07 tokens/round; our MTP-only 1.61/1.11 (68.8%)/2.12; DFlash2 2.76/1.71 (62.0%)/2.72.

## 3. Per-stage truth (TF_GLM_PROF=1)
Boot with `-e TF_GLM_PROF=1` and read `docker logs glmperf3-r0 | grep 'prof verify'`: one line per width with `wall`, `gpu` and the stage ms (kda, routed, mla, gather_a, dense, router, shared, gather_b, head). This is what turns a tok/s difference into a named cause. Two profiles at different world sizes on the SAME image separate world effects from code effects (that is how the KDA doubling was found: 7.52 ms at TP=2 against 15.0 at TP=3).

## 4. Exactness gates and the numerics rule
Every boot runs `python3 ~/glm-run/gate.py 8300 --tag TAG --out res/x-gates.jsonl`: smoke, drafted==serial, concurrent==solo, resumed==fresh. Green gates prove self-consistency only. A change that alters a partition or summation order (e.g. a different head split) keeps the gates green but CHANGES THE REPLY TEXT: compare the `sha` fields `streams.py` records per prompt across arms. Different digests = a numerics change = owner sign-off plus the quality harness, never a silent default.

## 5. Image build (and the trap)
`~/glmperf/build-image-gram.sh TAG SRC.tar` on spark4 (~20-25 min, needs `~/xgrammar` at v0.2.8), then ship with `docker save | ssh docker load` to spark5/6. The xgrammar submodule copy in that script must `rm -rf "$ctx/xgrammar/$SUB"` first: the v0.2.8 archive already contains empty `3rdparty/<sub>` dirs, so `cp -r` nests the submodule one level too deep and the grammar build dies with `'dlpack/dlpack.h' file not found`.

## 6. Sequence for a change you mean to ship
1. Exactness gates on every boot. 2. The full matrix at 1/2/4/6/8 streams (no regression at any level; a trade needs the owner). 3. Reply digests compared across arms. 4. Re-run the production parallel test so the trajectory stays honest.

## 7. Operational traps that cost real time
- `pkill -f <pattern>` kills your own ssh when the pattern text appears in your own command line (it always does). Use `pgrep` first, then `kill <pid>`; or use the `[x]` bracket trick and keep the literal out of the command.
- Never pipe stdin into `ssh -A -tt` (no EOF, the command hangs to the deadline).
- WSL `/tmp` is tmpfs and the VM idle-shuts-down between tool calls: keep scratch under `$HOME`.
- Check build liveness by CPU delta (`zig`/`cicc` at ~100%), never by log silence - docker's `#10 72.69` line does not move during a long RUN.
