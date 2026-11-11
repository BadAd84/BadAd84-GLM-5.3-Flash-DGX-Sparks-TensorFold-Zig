# PATCH-AUDIT.md - what patches 0002-0039 take away from the pin (2026-11-11)

Why: patch 0003 was found to have replaced the pin's correct `TF_GLM_KDA_PAD` sizing with an older form (fixed by
0040). So every line the stack removes or rewrites was read against three trees: the pin (`work/pin/tree`), the
patched tree (`work/parity/tree`) and the tree the patches were ported from (`ai-engine/work/aie/fair-base`).

Method: `scripts/patch-removals.py` lists, per patch and file, the removed lines the same file's hunks do not add
back (557 lines over 0002-0039: 198, 118 and 241 in the three reports). Each was classified as gated, refactor,
intended, regression or unclear, with
file and line evidence. The three full reports are in `docs/audit-2026-11-11/`. Nothing in them was run: runtime
consequences are read from the code, and the items marked "GPU check" below need one.

## Fixed by patch 0041 (the pin's or the source tree's form restored)

| # | where | what the stack did | when it bites |
|---|---|---|---|
| 1 | `cuda_dsa_block.attendLastRow` | sparse pass over `rows` rows where the pin launches 1 | default path: a prompt MTP chunk past the dense limit reads and writes past its row |
| 2 | `cuda_prompt_pair.prefill` | ran with the drafter's taps set, which `pairBody` refuses | default path with `--drafter`: a lone prompt of 6,144 tokens or more |
| 3 | `cuda_follow.chunkOf` | wide step even when a mark cut the first chunk short | default path, a mark inside the first chunk of a long prompt |
| 4 | `cuda_native` | a second `own.lanes = ...` dropped `--mtp-confidence` | MTP head without a drafter |
| 5 | `cuda_forward.whole` | L2 prefetch joined before the stream mean, for every forward | default path, timing only |
| 6 | `cuda_kda_block.bodyProfile` | L2 prefetch of site o forked before the projections | default path, timing only |
| 7 | `cuda_tile.tileLinears` | the pin's `synchronize` before the read-back dropped | load with packed linears |
| 8 | `dflash_load` | header and short-read checks replaced by unchecked JSON; `tap_rows` never set | a bad drafter file; `TF_GLM_CHUNK_SOLO` |
| 9 | `cuda_forward.Modules`, `commit` | `m.tiled` uninitialised, `m.* = undefined` dropped, `keep` passed as 8 bytes | latent |
| 10 | `cuda_lanes` | `draft_probabilities` lost `--mtp-confidence` | latent |
| 11 | `core/prompt_cache.keepBorn` | "the same state again" at any prefix length | an entry kept under another lookahead |
| 12 | `Forward.set()` | `.mla`, `.onepass`, `.onepass_pipe` no longer passed | `SPARSE_ONEPASS`, `ONEPASS_PIPE`, `ABSORB_VEC`, `MLA_FUSEMERGE` changed no launch; `MLA_FUSEMERGE` still shrank the partial buffers |
| 13 | `cuda_glue.Kernels` | `GLUE_FUSE` / `GLUE_ROW` / `PDL_EARLY` kernels loaded only with an MLA knob; `ROUTER16` loaded and never launched; `KVB8` not counted | those knobs set alone |
| 14 | `Engine.verifyShared` | the engine's own copy ran, not `cuda_engine_shared`'s | `DRAW1`, `SHARED_PROF` did nothing in shared rounds |
| 15 | `cuda_q4.Kernels` | `.module` never set | `DRAFT_DOWN4` with `DRAFT_MLPSPLIT` at three ranks: `loadF32` fails |
| 16 | `cuda_native`, `cuda_engine`, `cuda_kda_block` | `snapGridNow`, `snap_tail` gone; solo passes routed to the pair path; `body` one argument short | `KDA_CHUNKED`, `PROMPT_TAIL`, `CHUNK_SOLO`; dead code |

Items 12, 13 and 15 are in `serve.sh`'s `KNOBS=measured` set, so every cell measured with that set before 0041 ran
some knobs that did nothing, one that overran a buffer, and (with the drafter loaded) one that could not load.

## Not changed, recorded

- **Two defaults differ from the pin on purpose** (the source tree's behaviour, not behind a default-off knob):
  `allocate_shared_drafts` is off unless `TF_GLM_OVN_SHARED_DRAFTS` (0018; the pin has it on whenever drafting),
  and short prompts admitted together run one batched pass unless `TF_GLM_PROMPT_MANY=0` (0023; the pin steps
  each). Patch 0018's own text calls the first "the pin's behaviour today", which the pin's line contradicts.
  Each is measured as its own arm against the fix5 base (`f5-shared-drafts`, `f5-prompt-many0`).
- **The head-block rule is the source tree's, not the pin's** (0031): at TP=3's 21 or 22 heads a launch of 5 to 63
  rows takes the 32-head tile where the pin takes the 16-head one. Reply digests are equal at every level; the
  block arms that straddle it (a0027 against the full stack) measured level. Not gated.
- **Any-row keeps and resumes** (0007) replace the pin's 2,048-row grid on the default path, and with item 2 fixed
  a pair now runs while a drafter is loaded. Both are the source tree's behaviour. GPU check: the patch's own
  `glm-resume-check`, and a long prompt's digests against the pin's (`f5-long` against `pin-long`).
- **The whole-prompt pass (`TF_GLM_PROMPT_STEPS=0`) does not cut at marks** now that marks can sit at any row. The
  followers run that pass without marks, so rank 0 cannot cut there alone; states planned inside a chunk are not
  kept on that path.
- **Dead or duplicated code left by 0022 and 0023**: `Kernels.read()` / `Kernels.wanted()` copies in `cuda_glue.zig`,
  `cuda_engine_wait.zig`'s `Wait` beside `cuda_engine_gate.zig`'s, the `gb10_*` cost tables in `cuda_lanes.zig`
  beside `cuda_copy_policy.zig`'s, a doubled docblock in `cuda_follow.zig`, and `Config.first_tree`, which nothing
  reads.
