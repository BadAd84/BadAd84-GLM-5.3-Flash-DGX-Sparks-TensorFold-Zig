---
name: bench-and-bisect-the-glm-zig-recipe
description: "Boot, verify, bisect and benchmark the GLM Zig TensorFold recipe on spark1-3 (TP=3): detached serve, watchdog/production stop, chat as the correctness instrument, per-arm build cycle, 1/2/4/6/8 bench."
---

# Bench and bisect the GLM Zig recipe (spark1-3, TP=3)

Repo: `GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig` (as hhart pin + numbered `patches/engine/*.patch`). Its docs are SSOT: `PORT-LEDGER.md` (patch record), `docs/BENCH.md` (numbers), `docs/OVERNIGHT-*.md` (the latest session). Read them first.

## Boot window preconditions (all measured; skipping any spoils the run)

1. Stop production AND both watchdogs. `~/glm-v110-stop.sh` on spark1, then `ssh -A -tt spark1 'sudo systemctl stop glm-watchdog-system.service </dev/null'` and `systemctl --user stop glm-watchdog.service` from a login shell (a non-login `--user stop` can silently do nothing). The system watchdog restarts production after its down limit; that engine holds ~83 GiB and the TP=3 ranks then fail `the checkpoint's 61.3 GiB of weights do not fit`.
2. Check no other GPU holder: `nvidia-smi` process table on the box; a stray python is usually production's engine or a leftover probe container.

## Boot

- `scripts/serve.sh <rank> <P> [ctx]` is rank-local and launches `docker run -d` (detached on purpose: an attached run kills every rank when the launching shell ends). Logs are `docker logs glm53-zig-r<rank>`; `KEEP=1` disables `--rm` so a crashed container keeps its log and exit code.
- `scripts/zig-tp3.sh <P> [ctx]` from spark1 boots r0 spark1, r1 spark2, r2 spark3 (`spark$(rank+1)`), waits for `/v1/models`; `scripts/zig-tp3-stop.sh` stops all three. `CTX` is honoured from the environment (or argument 2).
- Model and drafter are CONTAINER paths (`/root/.cache/huggingface/hub/models--.../snapshots/<rev>`); the HF cache mount makes the snapshot blob symlinks resolve. Host paths fail on tokenizer.json.
- `config.sh` must sit beside serve.sh on every box (apply/tag/pin live there).

## Verify correctness with a chat, never with health

`curl -s http://127.0.0.1:8300/v1/chat/completions -H 'Content-Type: application/json' -d @prompt.json` with the count-to-20 prompt, temperature 0, 64 tokens, and read the content text: a coherent `1 2 3 4 5 6 7 8 9 10 11` matches the stock pin; token salad means a compute/wiring defect even while `/v1/models` answers. Compare `usage.prompt_tokens` (29 on this tokenizer) to separate template bugs from compute bugs.

## Bisect a broken arm

- Build an arm as a shared clone of the pin plus a patch subset: `git clone --shared work/parity/tree work/<arm>/tree`, checkout the pin, apply `patches/engine/00NN-*` in order, then TRIM `zig/build/cuda_kernels.zig` to the kernels whose `.cu` that subset actually ships (glm_kda_chunk arrives with 0019, glm_onepass 0016, glm_onepass_pipe 0017, glm_l2pf with 0032) or the image build dies `FileNotFound`/`file_open`.
- Test fixes needed per subset: 0032 (catalog) always; 0033 (shadow) with 0004+; 0034 (tap arity) only with 0007+; 0036 (chunk start/len) with 0007+ for chats to work at all.
- Build+distribute: `scripts/build-image.sh TAG src.tar` on spark1 (nvcc; the nvcc/zig compile is the only gate that catches embed/catalog gaps), then `docker save | ssh spark2/3 docker load` over the sparks' own links. Roughly 18 minutes per arm.
- Bisect by halving the patch range, booting each arm and reading ITS OWN reply. For a raise, instrument the actual error sites (`std.log.err` before each guard) instead of re-deriving: the failure names the rank that raised and the values that decided it.

## Benchmark

`DRAFTER=<0|1> KNOBS=<off|measured> bash scripts/bench-arm.sh <image> <tag>` from spark1: a fresh boot per level P=1,2,4,6,8, `streams.py` prose 400 tokens 3 rounds per level, JSONL receipts under `~/bench/<tag>/`. A busy compile on the same box spoils the numbers, so never build during a bench. Report decode aggregate tok/s, TTFT medians and the reply digests; equal digests across arms at the same level are the bit check.

## Current state it should assume

Full stack (0001-0037): coherent, bit-exact to stock, ~stock speed with +0.3..2.5% at P>=4. Stock pin image `glm53-zig:pin9c9`, full stack `glm53-zig:fix2`, arms armK2/K3/K4/K6/armA1/armK8 in the local docker on the sparks.
