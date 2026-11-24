---
name: microbench-tensorfold-glm-kernels-offline
description: "Use to attribute or tune a TensorFold GLM kernel (DSA indexer etc.) off the live serve: spare GB10, production image, CUDA-graph timing, bit-for-bit constant sweeps."
---

# Microbenchmark and tune TensorFold GLM kernels off the live serve

When: a long-context or multi-agent decode slowdown is on the GPU and code reading names a kernel as the cause, or you
want to tune a kernel's speed-only constants without a production window.

Why: on 2026-10-07 code reading named the DSA indexer as THE long-context lever; measured alone it was 3.1 ms of the
54 ms the round grew from 35k to 226k. The same bench then found a bit-exact ~20% indexer win (OTS patch 0075).

## 1. Prove the time is GPU-side first
- Host profile over the WHOLE decode: a py-spy dump sidecar (`--pid=container:glm53-flash-tf --cap-add SYS_PTRACE`)
  started before the request and stopped after it (glm5.3-flash-dev `scripts/glm53/v18/longhost.sh`), aggregated with
  `pyspy_agg.py --busy`, which drops samples whose scheduler thread sits in `tensorfold/cuda/scheduler.py get`
  (an idle server). A fixed 20 s window once sampled 97% idle and still read like a profile.
- Compare like with like: `longdec.py <port> <tokens> <max_tokens> <seed>` (fixed-seed prompt: cold fill, then
  decode-only), equal tokens a round across contexts.

## 2. Get a free GB10
- spark5 (Clef) or spark4 (Qwen) have headroom; check `MemAvailable` and disk. Never a GLM rank.
- Copy the production image: `ssh -A adam@spark1 'docker save tensorfold-glm53:v18-ots | ssh adam@<ip> docker load'`
  (24.6 GB, ~5.5 min). Run it in the FOREGROUND of the `ssh -A` session (an async harness job if needed): detached
  with setsid nohup, the forwarded agent dies with the outer session and the inner ssh fails `Permission denied
  (publickey,password)` while `docker save` keeps writing into a dead pipe. Loading over an existing tag leaves the old
  image untagged: `docker image prune -f`, then compare the image id with spark1's (`docker images`). Record it in that
  box's `~/INVENTORY.md` with its `docker rmi` line.
- Run with `--gpus all --network none -v ~/.cache/tf-triton:/root/.triton` (persistent Triton cache).
- Several lanes may time on spark5's GPU at once: wrap every timing run in `flock /home/adam/gpu-bench.lock <cmd>`.

## 3. Bench the engine's own kernel at production shapes
- Import the real functions (`sparse.seg_select_tokens`, `segments.SegRows`, `segments.SelectScratch`,
  `kv8.quantize_rows`), never a re-implementation.
- Production buffers: `SegRows(R, dev, max_segs=max(4, streams))`, `SelectScratch(R, 1048592, dev)`, segments
  `(base, ctx - rows, rows)` with bases on 2048-token extents, fp8 pooled keys `[base / 4 + 2, 128]`, 32 index heads
  x 128, 11 DSA layers a round.
- Time it as the serve runs it: warm 3x on a side stream, capture a CUDA graph, replay N between cuda Events.
  Report ms a call and x11.
- Shapes: 1 x 3 and 1 x 16 rows at 35k / 144k / 226k / 512k / 1M; 4 x 8 rows at 590k (`dsa_index_bench.py`).

## 4. Sweep speed-only constants, bit for bit
- Constants are module globals (`sparse.SEG_SCORE_GRID`, `sparse.SPLIT_WARPS`, `sparse.split_chunk`) or launch
  parameters: set, run, restore.
- Reference = production's constants. Compare scores over each row's VISIBLE pools only
  (`torch.equal(out[r, :n], ref[r, :n])`, n = (pos + 1) // 4) and selections with `torch.equal` on tokens and counts.
- Learned: a `tl.dot` kernel's block size and num_warps can change fp32 bits; a grid stride does not; an exact
  integer selection never does. Keep only arms whose output is SAME (`dsa_index_tune.py`).
- Then a whole-call regression matrix over contexts 8k..590k x (1x3, 1x16, 4x3, 4x8) (`dsa_index_matrix.py`): a
  win at 590k can lose at 8k.

## 5. Patch and stage
- Change only the constants, with a comment citing the measurement. Diff against the image's package with
  `git -c core.autocrlf=false` (LF), check it applies after 0071..0074 in order, and re-run the bench with the
  patched module mounted over the image path.
- `scripts/check-python.sh` flags names a lambda captures in a module-level loop that ends with `del` (undefined
  name): put the loop body in a function.
- Live only after `build_v18.sh` + a restart (`restart_when_idle.sh`, owner-chosen window). Live check:
  `firstreq.py` / `draftcmp.py` byte-identical, `longdec.py` decode at long context.

## Reference numbers (v18, GB10, 2026-10-07)
- Round 84.0 ms at 35k vs 138.3 ms at 226k (~15.5 tokens a round); host waits on the readback 98%.
- Indexer x11: 1 x 16 rows 0.78 ms (35k) -> 3.90 ms (226k); 4 x 8 rows x 590k 18.1 ms.
- Patch 0075 (grid 512, selection warps 8): 4 x 8 x 590k 14.5 ms; 1 x 16 x 226k 2.9 ms; same bits.
