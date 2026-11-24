---
name: hunt-stream-freezes-in-tensorfold-serve
description: "Use when TensorFold serve streams pause/freeze while another request starts, fills or resumes; not for throughput tuning."
---

# Hunt stream freezes in a TensorFold serve (GLM tf-v18 spark1-3, Qwen spark4)

## Model of the problem
TensorFold runs ONE Python engine loop that schedules every stream's rounds. Anything that blocks that loop, or holds
the GIL on another thread, stops EVERY stream. The recipe's smooth playout (`STREAM_SMOOTH=1`, 400 ms buffer, a token
held at most 2.5x that) hides pauses under ~0.4-1 s, so client-visible freezes are the long ones. Prefill slices
(`FILL_BUDGET_MS=200`) slowing other streams to ~65 tok/s during a fill are by design, not a freeze. Streaming itself
costs nothing measurable (`streamcost.py`, F63).

## 1. Probe (glm5.3-flash-dev `scripts/glm53/v18/`, copies in spark1 `~`)
`python3 ~/interfere.py <port> <decode tokens> <decode seed> <max_tokens> cold|warm <other tokens> <other seed> [extra seed]`
- Streams a greedy decode of a CACHED longdec.py prompt (run `longdec.py 8888 32000 1 932` first), starts the other
  request 3 s in: `cold` = an uncached longdec prompt, `warm` = a cached one plus ~20k new tokens (a warm agent turn).
- Prints chunk gaps (median / p99 / max) before / during / after, then the 5 longest gaps with epoch times and their
  offset from the other request's start. Read the OFFSET: +0 s = the request's start (tokenization, admission);
  the end of the window = the fill's end (state persisted to the NVMe tier); ~+2 s on a warm turn = the tier load.
- Fresh seeds for every cold arm: the NVMe tier caches longdec seeds across restarts. Give max_tokens enough to
  outlast the other request (the filler never ends by itself).

## 2. Attribute
`bash ~/freezehunt.sh <other tokens> <other seed> <label> [cold|warm] [extra seed]`: interfere.py under a sidecar
(`--pid=container:glm53-flash-tf --cap-add SYS_PTRACE`, py-spy mounted) running `freeze_sampler.py` - each pass:
/proc thread state, wchan, syscall (never hangs) + `py-spy dump --nonblocking` bounded at 1 s. `freeze_stacks.py`
prints every thread's frames per gap (window opens 1 s BEFORE the gap: the playout buffer delays what the client sees).
- py-spy itself HANGS against rank 0 during big fills/copies (it reads the target's memory). "0 samples" in a gap or
  `PYSPY TIMEOUT` lines are a hint of memory-map activity there; then read the code path that runs at that offset.

## 3. Causes found and their fixes (all byte-identical, measured 2026-10-07; ledger F62, F65, F68, F69)
- **GPU->host copy into FRESH pageable memory on the engine loop** (`.cpu()` / `.to("cpu")`): the driver faults every
  page in, ~0.1 GiB/s vs ~35 GiB/s into touched pages. Tell in `tier_copy_bench.py`: rep 0 slow, reps 1+ fast
  (allocator reuse). Fix: `out = torch.empty_like(t, device="cpu"); out.fill_(0); out.copy_(t)` (OTS 0080):
  226k fill-end freeze 2.3-2.6 s -> 69 ms.
- **Tokenizer `encode` holds the GIL** (~1.2 us a token): every long request's start stops all streams (~0.75 s at
  600k). Check with `tok_gil.py` (a counting thread's rate during encode: ~1% held vs >90% released). Fix:
  `tok.encode_batch_fast([text], add_special_tokens=flag)[0].ids`: same ids, GIL released, ~30% faster (GLM 0082, Qwen
  `tokenize-nogil` layer). Route EVERY `self.tok.encode(` through one helper; grep that none remain.
- **Serial disk reads on the engine loop** (NVMe tier `load`): disk-bound ~2.1 GiB/s with one read in flight; 8 in
  flight ~5.3 GiB/s (`tier_read_par.py`). Fix: bounded read-ahead on reader threads, copies to the pool in order on
  the caller (OTS 0081): 596k resume freeze 3.2 -> 1.2-1.4 s. The rest needs an async load (cross-rank protocol).

## 4. Shipping a fix
- Prove bits against the old path in the serving image (whole tensors / ids / file bytes), with a mutant runner whose
  anchors match exactly once. The test's first pass must use the SHIPPED constants: a mutant of a default survives a
  test that overrides it. If the real input cannot expose a branch (GLM's/Qwen's tokenizer post-processor adds no
  special tokens, so add_special_tokens mutants survived), add a synthetic case that can.
- Live: a `pNN_qual.sh` (tag `v18-ots-pre00NN` on spark1-3, NVMe restart test when tier code changed, `ab_long.sh`
  digests + draftcmp 7/7, the freeze probe again; automatic rollback on any failure), then manifests, docs (stack doc
  sections 3 and 8, ledger), `refresh-spark-state.sh` / live-state, gates, signed commit.
- Watch detached logs with `grep -a`: a binary byte makes grep say "binary file matches" and miss the DONE marker.
