# FP8 KV pages: why this ports as a restructure of the attention header, not as a patch package

Current as of 2026-11-23. The lever is `archive/tensorfold-gb10`'s `glm-fp8-pages` (`872b09a6f`, 2026-10-29) plus its
refinement `glm-fp8-pipe` (`1ccdb486e`). Both are one commit each and touch no new module, so on size alone they are
cuttable. The attention half is not.

## What the fork changed and what this series has there now

The fork's commit edits `chunks_wide<..., FP8>` inside `zig/kernels/cuda/glm_glue_attn.cuh` (its 28-line block: a row's
codes and scale with `pt` set live at `pt[c] * pstep + off * LW`, the scales at `page + CH * LW`, a sparse key's row in
`pstep / LW` rows a page) and threads `const int* pt, int64_t pstep` through `tf_glm_chunks_16_fp8` / `_32_fp8`.

This series has no `chunks_wide` in `glm_glue_attn.cuh` (158 lines, thin wrappers only). Its chunk attention is
`glm_attn::chunks_wide` in **`zig/kernels/cuda/common/mla.cuh:48`**, a header shared by GLM, DeepSeek V4.1 and
hy4_flash (`mla.cu`, `hy4_flash/mla_attention.cu` both include it). The FP8 wrappers in `glm_glue_attn.cuh:29,36` call
into it, and `glm_glue_attn_ovn.cuh:312` holds a `same_params` static_assert tying the FP8 wrappers' argument list to the
`_skip` variants.

So the change does not land in the file the commit edits. It lands in a shared kernel used by three families, and the
argument-list change propagates to the `_skip` variants and the static_assert.

## The shape a restructured port would take

1. `common/mla.cuh`: `chunks_wide` gains the page table and step (template parameter with a default, or a runtime pair),
   and the fork's block lands once there rather than twice in per-family wrappers.
2. `glm_glue_attn.cuh`: the `tf_glm_chunks_16_fp8` / `_32_fp8` wrappers gain `pt`/`pstep`; `glm_glue_attn_ovn.cuh`'s
   `_skip` variants and their `same_params` assert follow, or the assert fails.
3. `cuda_latent.zig`'s `chunks()` and `fused()` launches pass them (today they pass `pt`/`ps` only when `scales == 0`,
   because FP8 with pages is refused before the launch).
4. Every other family that includes `common/mla.cuh` recompiles against the new signature, and the FP8-page arithmetic
   must be proved byte-identical to today's window path for bf16 (`kv8 == false`) at several page counts and rows.

## The parts that would port cleanly, if the restructure is ever taken

`cuda_pages.zig` (keep the `TF_GLM_KV_HOST` page-bytes branch and pass `kv8`), `cuda_state.zig` (`latentPageBytes(c,
kv8)`, `pageCacheBytes`/`pageBytes` with `kv8`), `cuda_latent.zig` (the FP8 write takes `pt`/`ps`; drop
`error.Fp8OnPages`), `cuda_native.zig` (the refusal and its explanation), `cuda_start.zig` (`paging` without `kv8`),
`cuda_dsa_block.zig` (the token lists' row unit). The test rebase would follow as a second patch. The arithmetic
equivalence test for `kv8 == false` is the guard this document asks for if that work is taken.

## The framing, unchanged

The fork measured **-14% and -8% at depth**. The commit deletes a refusal rather than optimising anything. A queue exists
to refute or confirm it on this series at depth, not at short prompts. If it is a loss here too, the price of the answer
was small; that does not change the size of the restructure above.
