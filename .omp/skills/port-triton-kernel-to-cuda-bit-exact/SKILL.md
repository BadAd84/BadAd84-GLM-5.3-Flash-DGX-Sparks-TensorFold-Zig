---
name: port-triton-kernel-to-cuda-bit-exact
description: "Use when a profiled Triton kernel in the TensorFold GLM/Qwen serves must be rewritten in CUDA (or rebalanced) with every output bit-identical: PTX-order recipe, tests, mutants, offline bench, live ship."
---

# Bit-exact CUDA port of a Triton kernel (GB10, TensorFold)

When: a kernel is hot at production shapes, has headroom against its roofline, and no Triton knob is left that keeps the bits (num_warps at R>1, split-K, kWidth and any reassociation change them). Used 2026-10-07/08 for OTS 0084 (prompt scoring), 0085 / 0094 (prompt sparse attention), 0095 (decode scoring), 0097 (decode latent attention): every reply byte-identical.

## 0. Profile first
- Kernel share from an nsys / kernel timeline at production shapes; roofline: GB10 DRAM ~239-253 GB/s, bf16 mma.sync ~125 TFLOPS peak. Headroom = time / floor.
- Inside a kernel use ncu PC sampling (stall reasons per instruction). A clock64 phase trace read right after bar.sync times the barrier's issue, not its completion: every wait reads ~0 and it blames the wrong warp role.

## 1. Read Triton's arithmetic, not its source
- Dump TTGIR + PTX of the exact specialization production launches (same constexprs, warps, stages).
- Record: mma shape and each dot's K order; the operand `kWidth` (`#ttg.dot_op<..., kWidth=N>`). kWidth 2 = contiguous k pairs; kWidth 4: k = 32b+16u+4t+2h+e goes to step 2b+h, slot 8u+2t+e. Using the wrong one is off by 1 ulp almost everywhere.
- Also: scale order (e.g. `(dot*ks)*scale`), `ex2.approx` of x*log2e, the exact shuffle tree (lane xor order, warp partials as (s0+s2)+(s1+s3)), fma vs mul+add, `div.full`, the fp8->bf16 sequence (copy Triton's for tiles holding NaN codes).
- Measured on GB10 (lane-prefill `mma_sym.py`, `mma_lat.py`): mma.sync gives the same bits with A/B swapped and with k reordered inside one 16-wide step; HMMA latency ~30 cycles.
- Free (no bit changes): which warp computes an output, heads per tile, grid shape, persistent vs one CTA per item, skipping fully masked tiles (max -inf, alpha 1, p 0), stores that hide under mma.

## 2. Build
- New `.cu`, loader `load(name="tensorfold_<x>_otsNNNN", ...)`, patch header `# kcache: shared` (build_v18.sh content-hashes the name). Load it in `decode.Engine.__init__` beside 0084/0085/0095/0097's: a lazily built extension froze every stream 23 s at the first request of a new image.
- Env switch `TF_GLM_<X>_CUDA=0` keeps Triton; route only the shapes production runs (FP8, TP=3's 22/21 heads, ...).
- Keep partial-output contracts identical (e.g. chunk partials incl. empty chunks) so downstream Triton kernels run unchanged.
- Hybrid split when CUDA loses on part of the space (0095: 1-3-row segments are memory-bound and Triton reads 8-12% faster; CUDA writes a table handing them back so each segment is done once).
- Speed after exactness, from ncu: index loads used at once in address math cause long-scoreboard stalls (add the base at the dependent load: 205 -> 98 us); swizzle `c ^ ((r ^ (c >> 3)) & 7)` for producer bank conflicts; bound a loop by a count ptxas cannot see to stop mma bursts; balance mma per scheduler; `__launch_bounds__(256, 2)` against register blowup.

## 3. Prove the bits
- Test against the Triton kernel with every output, partial and scratch NaN- or sentinel-filled first (every store and non-store compared): 1-4 streams, 1-16 rows, 35k-600k, 22 and 21 heads, count boundaries (31-33, 511-513, 1024, 2050), padding ids (-1, 2^30) never read, every e4m3 code incl. NaN, arbitrary scales, tiny/huge inputs, +-0, a CUDA graph replay over new data, routing, the switch, the extension name. First pass uses the shipped constants.
- An overflow guard is only killable by checking a neighbour's scratch stays at the sentinel.
- Start-up test: loaded once with FP8 and the switch on, never with switch 0 or bf16; counters reset per case.
- Mutants: anchors match exactly once; kill = non-zero exit AND a FAIL line; hang or crash without FAIL = survivor; a fresh TORCH_EXTENSIONS_DIR (or `touch` the source) per run, since torch rebuilds by mtime and loads stale builds; prints `exit N`; zero survivors, or a written proof that the mutant cannot change any output.

## 4. Bench and ship
- Offline: cold, a CUDA graph of 11 calls (one per DSA layer, own keys), 256 MiB L2 flush between replays, median of 30. Benches where rows share pools sit in L2 and overstate live gains.
- spark5 is shared with Clef: `flock /home/adam/gpu-bench.lock` per run, containers <= 24 GB, wait for >= 30 GB MemAvailable (lane-decode `run5c.sh`); a lane's 4.9 GB int32 temporaries OOM-restarted Clef twice.
- Live (spark1): patch at the top of glm5.3-flash-dev `scripts/glm53/v18/`, `build_v18.sh`; decode -> `img_ab.sh <label> <old> <new> warm`, prefill -> `cold_ab.sh <label> <image> <seed1> <seed2> [size1 size2]` with fresh seeds; every digest identical (firstreq 011a34adf6, draftcmp 7/7, realdec, longdec, multidec); then `soak_mix.sh 12`; rollback tag `v18-ots-pre00NN`; production doc s3 / provenance / s8, ledger F-row, campaign doc, gates, Spark inventories, signed commit.
