---
name: bench-engine-kernels-side-by-side-on-gb10
description: "Stage slower than production but code looks equal: time both engines' real kernels on one GB10 with identical inputs before porting."
---

# Bench two engines' kernels side by side on one GB10

When: ai-engine (Zig) is slower than production (Python TensorFold, glm5.3-flash-dev prodpkg) on a stage, and a code comparison says the kernels/tiling are the same and the difference should be small. Measured 2026-11-01: WideExpertsDiff estimated 1-4 ms for routed experts; the side-by-side bench found ~2x at 32-64 rows per expert, all in launch shape (grouping kernel, empty grid blocks, compaction/copies), fixed bit-exactly by TF_GLM_OVN_ITEMS.

## Build the harness (a lane can do this; no GPU needed to write it)
- Reuse kernel sources VERBATIM from both trees (production `families/glm5_next/cuda/*.cu`, strip only torch includes and at::Tensor wrappers; ours `zig/kernels/cuda/*.cu` + includes). Separate namespaces/TUs.
- Replicate each engine's LAUNCHER exactly (grids, template params, args) from its host code (production `.cpp`/`.py`, ours the Zig `runWith`), including knob variants as separate arms.
- One logical synthetic weight set; both engines point into the same device buffers (only addressing may differ). Same routing for both.
- Routing modes: `lockstep` (every row of a window routed alike: production's counting probe shape) and `distinct` (fixed seed; optionally `--hot N` experts). Sweep rows R in 1..64; report D (distinct experts).
- Time as the serve runs it: capture the whole stage in a CUDA graph, 5 warm-ups, median of 50 replays; plus eager per-kernel events for the split.
- Sanity: compare outputs between engines (and between your variant arms) BIT FOR BIT, printing differing count AND nonzero count (all-zero outputs would pass trivially).
- Compile-check locally with the fatbins.cmd nvcc/vcvars locators for sm_121a.

## Run on a spare GB10
- spark6 when the triangle is busy: `flock -o ~/work/gpu.lock docker run --rm --gpus all --network none -v $PWD:/w -w /w nvcr.io/nvidia/pytorch:26.07-py3 bash -c 'bash build.sh && ./bench ...'`. Note `-w /w` (a bare `./bench` outside /w fails rc 127).
- Record the dirs in spark6's ~/INVENTORY.md.

## Read and act
- Find where cost grows with rows-per-expert vs production; the per-kernel split names the step.
- Prototype the fix INSIDE the bench first (e.g. our kernels on production's plan) and prove bit-exactness there, then port to the engine behind a default-off TF_GLM_OVN_* knob.
- Engine GPU check must include the new shapes (lockstep windows of many rows) and be proven to fail with a faithful mutant (e.g. members offset off by one) before any serve A/B.
- To run tf-cuda-test checks on spark6 without the grammar build: `~/work/items/build-nogram.sh TAG SRC.tar` (build-image-gram.sh's Dockerfile minus libtfgrammar).

Reference: ai-engine work/scratch/routedbench, docs/PARITY.md 2f item 28.
