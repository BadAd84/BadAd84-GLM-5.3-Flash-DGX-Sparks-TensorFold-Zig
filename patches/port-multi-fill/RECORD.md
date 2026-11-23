# RECORD.md - patches/port-multi-fill

## Base: upstream main `fa13df5dd1fdd23ada775510a464c9aa03a39e09`, the engine series and the six packages before it

Lands LAST on the stack - engine, pr1411, cache-salt, learn-starts, solo-cuts, disk-any-position, restore-held, then this
package (41 patches) - and was gated on the engine series alone first (tree `59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450`,
`iter mf-final`: `check fmt test ctest`, `test-cuda-host` 7,995 of 8,038 with 43 skipped and no failures, `compile-cuda-tests`
10 of 10, `ctest` rc 0). Two hunks were context-repaired for the full stack when it landed there: `cuda_native.zig`'s
`release(own);` (added by `restore-held`) and the `own.link.lead(...)` line that had replaced `own.link.asleep`; the change
itself is untouched, and `SHA256SUMS` was regenerated. It also carries the stepped many vtable (`TF_GLM_PROMPT_MANY`)
because `prefill_many` is not admitted without it, so **this package and `patches/port-prompt-many` are alternatives, not a
stack**: both add the same vtable block.

Source: `archive/ai-engine`, branch `ovn-batchresume` (`refs/heads/ovn-batchresume`), merged into `ovn-up` by
`93dfbf29ab1010c0cac9209119bc3fe73f2aaf2b`; the lever's own commits are `32060d70636136570111de75ec65805e0221fa09`
(2026-10-30, `cuda_lanes_fill.zig` + `cuda_prompt_pieces.zig` + the follower's `many` flag-1 step) and
`23062bd9cccaf97b802e1ec7c9b534c74bcf6c9a` (2026-11-01, `plan()`, the host tests, `glm-multifill-check`, the mutant
tool).

The text was edited, because the series' prompt path is not the fork's:

- `cut()` is `prompt_cuts.nextCut` (this series' chunk grid and request starts) plus the first kept-state mark, not the
  fork's `chunkEnd`; `admits()` also refuses a stream with request starts (`s.chunks.len != 0`).
- The mark context is this series' `cuda_share.Keeps` (`Lanes.marksOf(s, &keeps)`), alive for the whole `multiFill`.
- `Lanes.releaseFn` becomes `pub` so the fill file can release a stream opened before a refusal.
- Both knobs default off and are `.glm` rows (`TF_GLM_PROMPT_MANY`, `TF_GLM_OVN_MULTI_FILL`); `multi` forces the many
  vtable on. The fork's PROMPT_MANY default was on.
- The GPU check compares batched against solo on first token, window tokens, logits and position; the fork's held-state
  image comparison needs `glm.disk_image` / `glm.disk_ranks`, which live in `patches/disk-any-position`, not the engine
  series. Its marks are at the chunk grid (2,048 / 4,096 / 6,144), because a mark fires only at a chunk start here.

`apply.sh --check` against the engine series: `before: 59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450`, `checked 1 patch(es);
tree id: 282674504f865d5af53054b619088f07c3491a7b`, rc 0, nothing written.

Gate: not yet taken. The command is `python scripts/spark-gates.py iter --name port-multi-fill --pin
fa13df5dd1fdd23ada775510a464c9aa03a39e09 --dir patches/engine,patches/port-multi-fill check fmt test ctest --max-load 14`
(the CUDA-test binary compile is needed because this package adds `glm_multifill_check.zig`).

## The measurement that decides it

Several cold prompts in one pass, which is the shape the fork's probe never contained: four short prompts resumed off
one kept state, cold first token and TTFT of the four, `TF_GLM_OVN_MULTI_FILL=1` against unset (control), then against
`TF_GLM_PROMPT_MANY=1` alone to separate the pieces from fresh-prompt batching. The expected cell: **at 4 and 8 prompts
arriving together, the batched pass at least as fast as the serial fills on the last prompt's TTFT, with every reply's
first token equal to its solo run**; a decode regression at 1 stream kills it under the repo's rule (as PROMPT_MANY's
-1.3% at one stream already suggests for that arm). `glm-multifill-check` is the exactness receipt; the speed receipt is
a serve-level queue with 4 and 8 simultaneous cold prompts.

Patches, in file-name order:

- `0001-glm-multifill.patch`
