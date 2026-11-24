# Declarations the re-seat is missing, corrected audit (2026-11-24)

Definition: a `pub fn`/`pub const`/`pub var` a patch adds whose NAME is absent from the tree at any visibility,
matched against the file the patch puts it in. Earlier versions counted private declarations as missing, or counted
locals and context lines; this one does neither.

The image builds with these absent, because a patch whose declaration and call site were both dropped leaves nothing
that references it.

**CURRENT STATE: zero.** All 42 declarations this audit named are now in the tree, ported from
`work/premerge` (the series applied cleanly to `fa13df5dd`), file by file with `compile-cuda-tests` behind each batch.
Commits: `12f88816d`, `b5ab47f9a`, `a4b87e997` (patch 0030's fifteen), `16ad13dd4`, `29db29575` (0038's twelve and the
last twelve), plus `qakvRows` and `projectedRows`, private helpers the compiler named.

`keepsSequence` was among them: the method our KEEP_SEQS pull request adds was absent from the series' own tree, so the
feature was partly missing here as well as unmerged upstream.

The table below is the audit as it stood before the port, kept as the record of what was missing.

| patch | file | name |
|---|---|---|
| 0007-index-decode-windows.patch | `zig/src/families/glm/cuda_index.zig` | `decodeFrom` |
| 0012-index-sched-decode-pools32.patch | `zig/src/families/glm/cuda_sparse.zig` | `ovnListBytes` |
| 0021-kda-chunked.patch | `zig/src/cuda/kernels.zig` | `glm_l2pf` |
| 0024-glue-fuse.patch | `zig/src/families/glm/cuda_forward.zig` | `l2pfFor` |
| 0024-glue-fuse.patch | `zig/src/families/glm/cuda_glue.zig` | `hcGlue` |
| 0024-glue-fuse.patch | `zig/src/families/glm/cuda_glue.zig` | `hcRow` |
| 0025-head-block-rule.patch | `zig/src/families/glm/cuda_dsa_block.zig` | `denseRows` |
| 0025-head-block-rule.patch | `zig/src/families/glm/cuda_latent.zig` | `headBlockOf` |
| 0030-render-once-host-once.patch | `zig/src/core/template/eval.zig` | `rootMarked` |
| 0030-render-once-host-once.patch | `zig/src/core/template/template.zig` | `Watch` |
| 0030-render-once-host-once.patch | `zig/src/core/template/template.zig` | `More` |
| 0030-render-once-host-once.patch | `zig/src/core/template/template.zig` | `renderMore` |
| 0030-render-once-host-once.patch | `zig/src/core/tokenizer/tokenizer.zig` | `kept` |
| 0030-render-once-host-once.patch | `zig/src/core/tokenizer/tokenizer.zig` | `checkSpans` |
| 0030-render-once-host-once.patch | `zig/src/core/tokenizer/tokenizer.zig` | `segments` |
| 0030-render-once-host-once.patch | `zig/src/server/messages.zig` | `Args` |
| 0030-render-once-host-once.patch | `zig/src/server/messages.zig` | `toolArgumentsWith` |
| 0030-render-once-host-once.patch | `zig/src/server/model_text.zig` | `Kept` |
| 0030-render-once-host-once.patch | `zig/src/server/model_text.zig` | `Pieces` |
| 0030-render-once-host-once.patch | `zig/src/server/model_text.zig` | `keep` |
| 0030-render-once-host-once.patch | `zig/src/server/model_text.zig` | `pieces` |
| 0030-render-once-host-once.patch | `zig/src/server/model_text.zig` | `prefixPieces` |
| 0030-render-once-host-once.patch | `zig/src/server/prompt.zig` | `needsUserAfterTool` |
| 0031-glm-exl3-x3-decode.patch | `zig/src/cuda/exl3_experts.zig` | `Ovn` |
| 0031-glm-exl3-x3-decode.patch | `zig/src/cuda/exl3_experts.zig` | `Variant` |
| 0031-glm-exl3-x3-decode.patch | `zig/src/cuda/exl3_experts.zig` | `variant` |
| 0031-glm-exl3-x3-decode.patch | `zig/src/cuda/exl3_experts.zig` | `fusable` |
| 0031-glm-exl3-x3-decode.patch | `zig/src/cuda/exl3_experts.zig` | `rowsIn` |
| 0032-glm-keep-seqs.patch | `zig/src/families/glm/cuda_engine.zig` | `keepsSequence` |
| 0037-glm-side-prio.patch | `zig/src/families/glm/cuda_forward_pieces.zig` | `high` |
| 0038-glm-piece-front.patch | `zig/src/families/glm/cuda_dsa_block.zig` | `bodyRest` |
| 0038-glm-piece-front.patch | `zig/src/families/glm/cuda_dsa_block.zig` | `prepareRows` |
| 0038-glm-piece-front.patch | `zig/src/families/glm/cuda_forward.zig` | `pieceFront` |
| 0038-glm-piece-front.patch | `zig/src/families/glm/cuda_forward.zig` | `pieceMla` |
| 0038-glm-piece-front.patch | `zig/src/families/glm/cuda_forward.zig` | `pieceFfn` |
| 0038-glm-piece-front.patch | `zig/src/families/glm/cuda_forward.zig` | `pieceFrontRows` |
| 0038-glm-piece-front.patch | `zig/src/families/glm/cuda_forward.zig` | `mixerFrom` |
| 0038-glm-piece-front.patch | `zig/src/families/glm/cuda_forward.zig` | `ffnFrom` |
| 0038-glm-piece-front.patch | `zig/src/families/glm/cuda_kda_block.zig` | `bodyRest` |
| 0038-glm-piece-front.patch | `zig/src/families/glm/cuda_kda_block.zig` | `projectRows` |
| 0038-glm-piece-front.patch | `zig/src/families/glm/cuda_moe.zig` | `routeRows` |
| 0038-glm-piece-front.patch | `zig/src/families/glm/cuda_moe.zig` | `bodyRest` |
