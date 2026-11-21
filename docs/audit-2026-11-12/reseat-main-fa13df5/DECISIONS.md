# DECISIONS: the 47-patch series from the tip 46c6ee229 onto upstream main fa13df5dd

## Oracle

`python work/reseat2/series.py build-old`: `old chain: 47 patches, final tree 1fd680b2b681e80d1e40492f881b444602a5bc89`,
`oracle 1fd680b2b681e80d1e40492f881b444602a5bc89`, `ORACLE MATCH`. N0 = fa13df5dd1fdd23ada775510a464c9aa03a39e09, tree
efd5bccea8b50fc9c98966f4a9f4161d2a6864d7.

## One line per patch (placement, tree after it, recipe use)

1. `engine/0001-shared-window-width.patch`: placed clean, tree `e190c496773e116d5d855c892af19af1e5e3af86`; recipe: no knob (a GPU check's buffer sizes; test code only).
2. `engine/0002-rows-worker-and-quiesce-drain.patch`: placed clean, tree `82ed43b6693a7b1349e19c2e6b36149704aca547`; recipe: no knob (the disk grid on the I/O worker and a quiesce drain test: default path).
3. `engine/0003-prompt-bench.patch`: placed clean, tree `ee54d3601c3c58173adcd669dec575c8eb24b4fb`; recipe: no knob (the prompt-bench host step: a tool).
4. `engine/0004-ovn-knob-registry.patch`: placed clean, tree `0919e064770c6d52f865faedad51b9b502519a3a`; recipe: no knob of its own: it IS the `cuda.ovn` registry every TF_GLM_OVN_ read goes through, so every active OVN patch (0006, 0008, 0020, 0022, 0023, 0030-0034) depends on it at compile time.
5. `engine/0005-kda-pad-one-width.patch`: placed clean, tree `10c6639679b08549cd912a54a07ce457ad703348`; recipe: knob unset (`TF_GLM_KDA_DUMP`, a diagnostic; the recipe's `TF_GLM_KDA_PAD=1` is upstream's switch); no active patch uses its code.
6. `engine/0006-draft-knobs.patch`: resolved, OVERLAP 1, tree `2ed50f47a6850b7148b2e642a78e8cf3cf89d2d8`; recipe: active (prod.env: DRAFT_BETA, CUTS, DOWN4, EDGE, MLPSPLIT, NOISE, ONEPASS).
7. `engine/0007-index-decode-windows.patch`: resolved, OVERLAP 2, amended twice, tree `48288a253e59ba77dc5e8e54d222209a1b283158`; recipe: knob unset (`TF_GLM_INDEX_CUDA=all`, `TF_GLM_INDEX_DECODE_FROM`); no active patch uses it; 0012 and 0013 (both knob unset) are written on its fields and `Mode.all`.
8. `engine/0008-kept-walk-prefix-helper.patch`: placed clean, tree `20359f237573cfa2b65fcfe24b17d257c031d49e`; recipe: active (prod.env: TF_GLM_OVN_KEPT_WALK).
9. `engine/0009-ring-past-refusal.patch`: placed clean, tree `5ac7ff488086b828a954dde2e5e48320be405434`; recipe: no knob (a pass the rebased index ring cannot hold is refused: default path).
10. `engine/0010-ovn-check-table.patch`: placed clean, tree `f499aef8bda8a45cb74596c2a91650703f1b9046`; recipe: no knob (the OVN check table of the GPU test binary: test code).
11. `engine/0012-index-sched-decode-pools32.patch`: resolved, OVERLAP 2 (its DECODE_INDEX part), tree `4226a9df0aef6bf736aaab3593fb95de3fbb31d3`; recipe: knob unset (DECODE_INDEX, INDEX_SCHED, POOLS32); no active patch uses its code (the text hits were common names); 0013 sits on its scoresTiles line.
12. `engine/0013-index-regroup.patch`: resolved, tree `553ef6f9af9dc5b50f268f3f8ba963b17fe34429`; recipe: knob unset (INDEX_REGROUP); no active patch uses its code (prompt rows only: `scorer` returns .plain under rows_from).
13. `engine/0014-lanes-step-split.patch`: placed clean, tree `b2f014db850600f421c59871db528e98f6139228`; recipe: no knob (the stepped prompt pass moved to its own file: default path).
14. `engine/0015-plain-margin.patch`: placed clean, tree `39455045c551df95736880d2d8cf8b20a1025660`; recipe: knob unset (PLAIN_MARGIN); no active dependant.
15. `engine/0016-exchange-kb.patch`: placed clean, tree `e42272106818ddd5657d9c6ba836df50dca91afd`; recipe: knob unset (EXCHANGE_KB); no active dependant.
16. `engine/0017-router-warm.patch`: placed clean, tree `3221bcbc73a6785c1635b33dd2d29d9fbd4927a8`; recipe: knob unset (ROUTER_WARM); 0024 (knob unset) edits the file it creates, `cuda_router_warm.zig`; no active dependant.
17. `engine/0018-win-free.patch`: placed clean, tree `9467d0d31e1d69ccaae8d9e8f5208abd38364cfe`; recipe: knob unset (WIN_FREE); no active dependant.
18. `engine/0019-sparse-onepass.patch`: resolved, tree `06c87369cee41cf4a19b243b029a496fc7ee28fd`; recipe: knob unset (SPARSE_ONEPASS), but a PREREQUISITE of active 0020: 0020's pipe lives in 0019's `cuda_onepass.zig` and is built on its `Kernels.load` (via `open`), `takes` (inside `takesExact`), `smem` (`pipe_smem = smem + 24 * 4`), `threads` and `min_heads`/`max_heads`; 0025 (no knob) edits the same file.
19. `engine/0020-onepass-pipe.patch`: resolved, tree `91c55c924e4d7e5988f6a2946a20dc68e11d8214`; recipe: active (prod.env: ONEPASS_PIPE, MLA_FUSEMERGE); needs 0019 (above). The kernel the active ONEPASS_PIPE=1 runs is chosen by 0024's line (`x.exact`), see 0024.
20. `engine/0021-kda-chunked.patch`: placed clean, tree `beff249701a4bb2a6ec4225d13f9a334d42ac761`; recipe: knob unset (KDA_CHUNKED), but its argument `if (b.prefill) kda_chunk.prompt(&f.m.chunked, st.pos) else null` sits on the forward's default `bodyProfile` call (null with the knob off), and it is the patch that unglues 0020's `onepass_pipe`/`tiled` field line; later patches that edit that call line (0024's `l2pfFor`) are written on it.
21. `engine/0022-mm-knobs.patch`: placed clean, tree `847d9f9cad1bf6847b2c4c60c60340b1d2c5934c`; recipe: active (prod.env: MM_DECTILE, SWIGLU_REDUCE; dev.env adds MM_WIDE).
22. `engine/0023-mla-knobs.patch`: resolved, tree `4b6e9a74b903ab7ac0b96d10013e7ae5dc6a9df2`; recipe: active (it registers no row; its kernels serve MLA_FUSEMERGE, which 0020 registers and prod.env sets).
23. `engine/0024-glue-fuse.patch`: resolved, tree `cc2c614b66f5d0d0f01e68cc99c84e8cd3220044`; recipe: its own knobs unset (GLUE_FUSE, GLUE_ROW, PDL_EARLY), BUT it changes the active path in two ways: `glue.Set.onepass_pipe` takes `x.exact` (0020 had `x.chunk`), so the recipe's ONEPASS_PIPE=1 runs `tf_glm_onepass_pipe_exact` because of this patch; and its glue refactor (`glueRows` to `cuda_forward_glue.zig`, `post(r, x, rows)`, `prefetch` renamed `l2pfFor`) is the default path with GLUE_FUSE off. Its `Mla.wanted()` edit only adds KVB8, so MLA_FUSEMERGE=1 does not depend on it.
24. `engine/0025-head-block-rule.patch`: placed clean, tree `9d7f8734764127f62a362a2ed8070625c1124258`; recipe: no knob (the head block takes the head count: default path).
25. `engine/0026-head-flag.patch`: placed clean, tree `07af9449088ec0bee5cee819eb61c67e548a4ad1`; recipe: no knob (the MTP head's passes only without a DFlash2 drafter: default path).
26. `engine/0027-exl3-dec-order.patch`: placed clean, tree `cb737d7d7f406941584cdd4a9d48b33a06505ccc`; recipe: active (prod.env: TF_EXL3_DEC_ORDER).
27. `engine/0028-memo-equal-strindex.patch`: placed clean, tree `5b3bdbac541b1fe84adfb0ddaeb6b9522a81bed1`; recipe: no knob (byte equality and string index: default path).
28. `engine/0029-fp8-tile-ahead.patch`: placed clean, tree `44374470a1dca4bd9d96c607aba7898a0eb7719a`; recipe: no knob (FP8 keys a tile ahead: default path).
29. `engine/0030-render-once-host-once.patch`: placed clean, tree `287abf5ab1603d171370f0c73ddb549f205fd293`; recipe: active (prod.env: HOST_ONCE; the render-once part is the default path).
30. `engine/0031-glm-exl3-x3-decode.patch`: placed clean, tree `a737472aac19f9372f2d0f2eb7b211a904439a34`; recipe: active (prod.env: X3_NC, X3_XROW, X3_FUSEDOWN).
31. `engine/0032-glm-keep-seqs.patch`: placed clean, tree `19f1ce96e1cb19f7129fe9e2b7a044f4933051e2`; recipe: active (prod.env: KEEP_SEQS).
32. `engine/0033-glm-off-effort-line.patch`: placed clean, tree `ecbd6a5ea0bc075d29dc9e3fbff6ac506fab331e`; recipe: active (prod.env: OFF_EFFORT_LINE).
33. `engine/0034-glm-no-copy.patch`: placed clean, tree `a3c1313d94bad13f1bc0c51ddc2e8d9ef182a204`; recipe: active (prod.env: NO_COPY).
34. `engine/0035-glm-mm-ovn-check.patch`: placed clean, tree `9698006510918dbdb311a0ce54114e3cbb1aabaa`; recipe: no knob (the MM OVN GPU check: test code).
35. `engine/0036-glm-latent-rows.patch`: placed clean, tree `5638b355ed8dfbb3925906d33fe31ef8b23d6641`; recipe: dev candidate (dev.env: LATENT_ROWS; its MLA_FUSEMERGE lines are 0020's, reformatted).
36. `engine/0037-glm-side-prio.patch`: placed clean, tree `b7bab235b92f7ea5ddbff2237d14b5d47ef5fdae`; recipe: dev candidate (dev.env: SIDE_PRIO).
37. `engine/0038-glm-piece-front.patch`: placed clean, tree `cf8a101d6182c0b21207d74a3bc36109c1e3bf2e`; recipe: dev candidate (dev.env: PIECE_FRONT, PIECE_FFN, PIECE_MLA; FRONT_ROWS unset).
38. `engine/0039-glm-piece-kda.patch`: placed clean, tree `9d18692091aac67443466401195d4aae73fa79ca`; recipe: knob unset (PIECE_KDA); no active dependant.
39. `pr1411/0001-pr1411-on-the-v129-engine-series.patch`: placed clean, then amended (lane_host.zig kept at 600 lines), tree `ad57176cc9350322fb0024e865b3aeeb83dfe75e`; recipe: knob unset (the disk tier needs serve.sh LEARN=1, default 0; DISK_SLICE_MIB unset); 0040 and 0046 (no knob of their own) build on its files and run only on its path; 0047 reads `cuda_disk_image.zig` in a host test.
40. `pr1411/0002-pr1411-disk-read-rows-in-one-step.patch`: placed clean, tree `4719d486cd5f348fe0e600b0f6d8518613acd108`; recipe: no knob of its own, runs only with the disk tier (LEARN=1).
41. `cache-salt/0001-server-cache-salt-and-cache-salt-per-key-keep-kept-prompt-states-apart.patch`: resolved (and one blank-line removal moved into pr1411 0001), tree `9cc36c0aeec8742df1d2c319e24fe24536e51547`; recipe: flag unset (`--cache-salt-per-key`); the request field `cache_salt` is live for any client that sends one (the bench clients do not).
42. `cache-salt/0002-tests-the-server-goldens-model-capabilities-carry-cache-salt.patch`: placed clean, tree `5764817835691f245426ab7f2b7aa02cce07f464`; recipe: no knob (goldens: test data).
43. `learn-starts/0001-glm-disk-request-starts.patch`: placed clean, tree `db2d479e80bd18f91dda77baf9223cc4e6548c2d`; recipe: knob unset (upstream's `TF_GLM_REQUEST_STARTS`, set by neither env file, with LEARN=1).
44. `solo-cuts/0001-glm-solo-between-starts.patch`: placed clean, tree `6fb63f4b82e3603b8e7b1e9bff850c715c6b01ba`; recipe: knob unset in effect (it acts only when request starts exist, i.e. with TF_GLM_REQUEST_STARTS=1).
45. `solo-cuts/0002-glm-solo-to-start.patch`: placed clean, tree `c80bf1cfe48715f2143ae91df0d7f054ee29fd10`; recipe: dev candidate (dev.env: SOLO_TO_START).
46. `disk-any-position/0001-glm-disk-state-at-any-position.patch`: placed clean, tree `2bf5025c155d91270afb1a6d2a77fa59965cf25f`; recipe: no knob of its own, runs only with the disk tier (LEARN=1).
47. `restore-held/0001-glm-restore-held.patch`: placed clean, tree `19c545b35927ecbf59924852e6d5d07465c2bfe7`; recipe: dev candidate (dev.env: RESTORE_HELD).

Final tree after patch 47: `19c545b35927ecbf59924852e6d5d07465c2bfe7`.

## Hand resolutions

### 0006 draft-knobs (OVERLAP 1: the drafter MLP split)
- Conflict: `zig/src/families/glm/dflash_load.zig`, the line `const mlp = df.mlpSplit(world, e.settings.roce_wide);`
  that our patch keeps as context and wraps with `Knobs.read`, which upstream `5df57c025` (PR #3616) changed to
  `df.mlpSplit(world, e.settings.draftWide())` (`draftWide()` = `roce_wide or draft_split`, `TF_GLM_DRAFT_SPLIT=1`).
- Done: upstream's line kept verbatim, our two lines (`var temp: f64 = 1.0;` and `Knobs.read(&temp)`) after it;
  every other line of the patch merged as written (the line check shows its added/removed lines identical to the tip's).
- Window on one image: ours = the recipe (`TF_GLM_OVN_DRAFT_MLPSPLIT=4`, `TF_GLM_DRAFT_SPLIT` unset); upstream's
  alone = `TF_GLM_OVN_DRAFT_MLPSPLIT=0 TF_GLM_DRAFT_SPLIT=1`. `TF_GLM_DRAFT_SPLIT` is read by `cuda_ranks.zig`'s
  settings parser (0 or 1, default 0), not a registry row. Setting both stacks the two splits (as `TF_ROCE=1` with
  MLPSPLIT did on the tip): a window should not set both. No new switch was needed.

### 0007 index-decode-windows (OVERLAP 2: decode-window index scores; upstream ADOPTED our mechanism)
- Upstream `c1bfb2853` (TF_GLM_DSCORES, from MiaAI-Lab patch 0091), `16ead2656` and `76e0c0b27` put a decode
  window's index scores on `glm_index_scores` with `decodeLoop` and `takesDecode`, default on: decode windows of 8
  rows or more (4 from 2,048 blocks), one-row windows kept on `tf_glm_scores`. Ours routes decode windows of ANY row
  count through the indexer kernels under `TF_GLM_INDEX_CUDA=all`, gated by depth with `TF_GLM_INDEX_DECODE_FROM`.
- The merge-tree blob of `cuda_index.zig` was unusable (a duplicated doc line, the `decode_from` field lost), so the
  file was rewritten from `git show fa13df5dd:zig/src/families/glm/cuda_index.zig` plus only our distinct surface:
  the `all` word (enum, `3 => .all`, its parse test line), the `decode`/`decode_from` fields, `load` setting
  `.select = mode == .both or mode == .all, .decode = mode == .all, .decode_from = decodeFrom(profile.lookup(...))`,
  `takes` extended with `or (k.decode and np >= k.decode_from)`, `decodeFrom()` with its two tests, the three doc
  lines that name `all`, and our `Mode.all` assertions as a separate test (decode windows of 1 and 7 rows taken;
  `topk - 1` pools and an unaligned key cache refused). Upstream's `decodeLoop`, `takesDecode`, `scoresGrid`,
  `scores`, `scoresTiles` and every upstream test are the base's, except that upstream's `takes` test, which builds
  `const k: Kernels = undefined`, now initialises `k.decode = false; k.decode_from = 0;` (our `takes` reads them;
  without this the test read undefined memory).
- Dropped from ours, as duplicates of upstream's adopted decode path: `tileLoop`, the `scoresGrid` decode-window
  expectations and our renamed copy of the `takes` test.
- Window: ours off = `TF_GLM_INDEX_CUDA` unset (upstream's `TF_GLM_DSCORES` decides); ours on =
  `TF_GLM_INDEX_CUDA=all` (`quick` wins over upstream's `dec` branch in `cuda_sparse.selectTokens`); upstream's off =
  `TF_GLM_DSCORES=0`.
- OPEN, speed only: with `all`, a decode window now goes through upstream's `scores`, which passes `score_tiles` tiles
  a CTA for every row count; the tip's `scores` passed `tileLoop(rows)` (1 tile a CTA for a decode window). Same
  bytes (every tiling writes the same scores), possibly different speed. Restoring it would change upstream's
  `scores` (the parent's rule: base functions unchanged), so it is recorded, not done.
- Amends: `amend 7` twice (the test initialisation; then the doc lines and the `Mode.all` test); patches 8 to 47
  replayed clean both times.

### 0012 index-sched-decode-pools32 (OVERLAP 2, its TF_GLM_OVN_DECODE_INDEX part)
- Conflicts: `cuda_forward.zig` (both sides added a `Modules` field: upstream's `dscore`, our `pools32`: both kept)
  and `cuda_index.zig` (four regions): `load` takes our multi-line literal (0007's fields plus `split_rows`,
  `split_fn`, `sched_fn`); upstream's `takesDecode` kept whole with our `decodeSelect` and `splits` after it; in
  `scoresTiles` upstream's argument list (its `loop`) with our prompt-row sched choice
  `if (k.sched_fn) |x| (if (rows >= rows_from) x else k.scores_fn) else k.scores_fn`; upstream's two decode tests
  kept and our split test added.
- Upstream loads its `dscore` through the same `Kernels.load(d, k.glm_index, .scores)`: with our knobs unset its new
  fields stay off (`split_rows` 0, `split_fn`/`sched_fn` null), and `dscore` is only used by `takesDecode` (ignores
  them) and `scoresTiles` (sched only for prompt rows, which `dscore` never serves). Our `cuda_sparse.zig` hunks (the
  split select, `decodeSelect`, POOLS32's int32 gather) merged below upstream's new `else if (dec)` scores branch.
- Window: ours on = `TF_GLM_OVN_DECODE_INDEX=n` (then `quick` takes decode windows ahead of `dec`); ours off = unset.

### 0013 index-regroup
- Conflict in `scoresTiles`: our `scorer(rows)` switch (regroup, sched, plain) replaces 0012's sched line, kept on
  upstream's argument list. `scorer` returns `.plain` under `rows_from`, so upstream's decode path is untouched.

### 0019 sparse-onepass, 0020 onepass-pipe, 0023 mla-knobs, 0024 glue-fuse
- Every conflict was a both-sides-added row: `kernels.zig` (upstream's `inkling2_ops`/`inkling2_rows` against our
  `glm_onepass`), `glue.Set` (upstream's `dscore` against our `onepass`, then 0020's `pdl_early` and `mla`),
  `Modules` (upstream's `dscore` load against our `onepass` load, both kept, each with its own unload), and the
  `Forward.set()` literal, which now carries upstream's `.dscore` with our `.onepass`, `.onepass_pipe`, `.mla` and
  (0024) `.pdl_early` and the `x.exact` choice. Upstream's own changes to the prompt-side sparse files since the tip
  are only the decode index commits above, so there is no prompt-side code overlap for 0019 and 0020.

### cache-salt 0001
- Both sides added a line: `engine_api.zig` (upstream's `unread` field, `856c11249`, against our `salted`) and
  `server/root.zig` (upstream's `structural_tag.zig` test import against our two): both kept, upstream's first.

### pr1411 0001 and cache-salt 0001: the 600-line cap of `zig/src/core/lane_host.zig`
- Upstream's slow-reader work (`856c11249`, then `2ae4ecc7d` and `cd6bfaa46` to meet the limit) leaves the file at
  exactly 600 lines. pr1411 0001 adds one line (its `lane_host_fetch.slice(h)` call), so every prefix that ends inside
  pr1411 had 601 lines: the N40 checkpoint's lean step reported `zig/src/core/lane_host.zig: over 600 lines (1 new)`.
  cache-salt 0001 already removes three blank lines at declaration boundaries there (its own +2 and this one).
- Done: `amend 39` removes the blank line between `};` and `test {` at the end of the file (one of the three cache-salt
  removes), so pr1411 0001 keeps the file at 600 alone; on replay cache-salt 0001 merged clean and no longer removes
  that line. No code or comment line moved and the final tree is unchanged (`19c545b35927`); `zig fmt` keeps a file
  with no blank line between two top-level declarations as it is.

## Overlap scan beyond the brief's two

`overlap.py` lists, per patch, the upstream commits between the tip and fa13df5dd that touch its files
(`overlap.txt`). Besides OVERLAP 1 and 2, every hit does a different job: `856c11249` (slow-reader scheduling,
lane_host and engine_api), `6b4cc34e1` (spill of backend-expired prompt states, beside 0008's kept walk),
`b9ba96568` (deferred tools in the prompt, beside 0030 and 0033), `c896bfc0c` (the unified memory budget, beside
pr1411), `6e8a89570` (deadline_s), `TENSORFOLD_PARALLEL`, and file-size and build fixes. Registry rows upstream added
in the range: `TENSORFOLD_PARALLEL`, `TF_HY4_MEM_FLOOR_GIB`, `TF_GLM_DSCORES`, `TF_DSV41_FLOAT_LINEAR`, and a forms
change to `TF_GLM_DRAFT_CONFIDENCE`; only `TF_GLM_DSCORES` overlaps ours.

## OPEN

- 0007 with `TF_GLM_INDEX_CUDA=all`: decode windows tile `score_tiles` a CTA through upstream's `scores` (the tip: 1);
  same bytes, speed may differ (above).
- The decision pass must know: removing 0024 would switch the active ONEPASS_PIPE from `exact` to `chunk`; removing
  0019 breaks the build of active 0020; removing 0021 changes the line every later edit of the forward's
  `bodyProfile` call is written on.
