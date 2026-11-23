# RECORD.md - patches/port-fp8-pages

## Base: upstream main `fa13df5dd1fdd23ada775510a464c9aa03a39e09`, then the 32 patches of `patches/engine/`

Applies to the engine series alone. `apply.sh --check` on tree `59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450` gives
tree `5bf069846d1bcae48c959497b0e7da63b7f047c1`, rc 0, nothing written.

Source: `archive/tensorfold-gb10`'s `glm-fp8-pages` (`872b09a6f`, 2026-10-29, "FP8 KV on pages - each page part holds
E4M3 codes, then their scales") and its refinement `glm-fp8-pipe` (`1ccdb486e`). This package is cut in three numbered
patches because the first two can be judged before the test rebase, and because the kernel half has an instrument the
Zig gates cannot provide.

The framing, plainly: the fork measured **-14% and -8% at depth**. The commit deletes a refusal rather than optimising
anything, and the queue exists to refute or confirm that on this series at depth, not at short prompts. If it is a loss
here too, the price of a closed question was small.

## 0001 - the FP8 page read inside `chunks_wide` (`0001-glm-mla-fp8-page-read.patch`)

This series' `common/mla.cuh` already takes `pt`/`pstep` and already pages the BF16 path, so there is no signature
restructure: only the FP8 fetch refused pages. The patch adds the page arithmetic inside that lambda behind
`if (pt && ok)`, so with `pt` null the FP8 read is exactly today's and no BF16 instantiation passes through the code at
all (`fetch` is called only from `if constexpr (FP8)` blocks).

Instrument: **no Zig gate step can read a `.cuh`.** `scripts/gates.sh` runs only Zig steps plus `fmt`, and the only nvcc
invocation in the repo is the image build. The receipt for this patch is therefore an nvcc compile on the gate host:
`nvcc -std=c++17 -arch=sm_121a -ptx -o /dev/null -Izig/kernels/cuda` over `mla.cu`, `glm_glue.cu` and
`hy4_flash/mla_attention.cu`, rc 0 each with the patched header in place (nvcc release 13.3, host
`~/tools/cuda-13.3/usr/local/cuda-13.3/bin/nvcc`). Caveat stated with the step: `-ptx` proves the source and its device
instantiations compile, not that a kernel keeps its register budget; the SASS budget is the image build's business. A
`scripts/gates.sh` step now runs the same compile (kernel step, after the Zig steps), proven to fail on a planted `#error`
and to pass on this tree.

## 0002 - the FP8 branch, wrappers and refusals

Not cut yet: `glm_glue_attn.cuh`'s `tf_glm_chunks_16_fp8`/`_32_fp8` gain `pt`/`pstep`, `glm_glue_attn_ovn.cuh`'s
`_skip` variants and their `same_params` static_assert follow, then `cuda_latent.zig`'s FP8 write and the
`error.Fp8OnPages` deletions, `cuda_native.zig`, `cuda_start.zig`, `cuda_pages.zig`, `cuda_state.zig`,
`cuda_dsa_block.zig`. The standing requirement on it: with `kv8 == false` every path must produce today's numbers, and
the `latentPageBytes`/`pageCacheBytes` equivalence gets a host test pinning the bf16 result against the current tree at
several page counts and rows. If any resolution would change a default path with the knobs off, the package stops and
the structural reason is written down instead.

## 0003 - the test rebase

Not cut yet: `cuda_kv8_test.zig`'s recorder growth and argument offsets, `cuda_start_test.zig`, and the removed
startup-refusal case.

Patches, in file-name order:

- `0001-glm-mla-fp8-page-read.patch`
