# RECORD.md - patches/pr1411

What it is: upstream PR ashhart/TensorFold#1411 (GLM-5.3-Flash on CUDA keeps conversation states on disk, every rank's
part, `--learn-conversations`), by Robert Wojciechowski, with our 0011 and 0012 (the disk tests' MTP head flag) and 0013
(`TF_GLM_OVN_DISK_SLICE_MIB`, a read-ahead disk state restored in slices between rounds), as ONE net patch on the recipe's
engine series. Retire the package when the pin moves past #1411's landing on upstream main.

Source: repository `wojo/TensorFold`, branch `up-glm-disk`, head `d730aff64a2daf4f8c10f8f737084edc5cc87326` (10
commits) on upstream main `3885dceb2bb60fe02e609066b75ec752baf51e38`; checked 2026-11-15 with `gh pr view 1411 -R
ashhart/TensorFold --json state,mergedAt,headRefOid`: OPEN, not merged, the same head. The per-commit form of the same
work on pristine v1.2.9 (each PR commit merged with its parent as the base, adding and removing only its own lines, and
our three, gated on spark5) is lane V129B's `work/V129B/package/patches/pr1411/`; its RECORD.md has the commit table and
the edits each patch carries.

Base it applies to: upstream v1.2.9 `6b9de695104b6b8b30c20458da87ac06c9480289` plus the engine series
(`/mnt/c/Users/Adam/Gitea/GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig/work/V129A/series`, 32 patches), tree `e02b8a89c2ccbb7fe67e42fb4bf300bec1a5f2c3`, i.e. after `scripts/apply.sh`. Final tree `3b06d167fd742683f210ffc7f69eef5199640664`. With
`patches/cache-salt/` on top, the whole stack: `27a87244e7dca097007c8b086b7c49a76a8e69d2`.

Why one net patch: the series rewrites the CUDA-family scaffolding the PR patches, so the per-commit patches leave 6
rejected hunks on it. Made by `python work/V129B/recut_combined.py /mnt/c/Users/Adam/Gitea/GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig/work/V129A/series`: the per-commit package applied to the
series tree with --reject, each reject settled, the GLM env test and rows fitted to the series' conventions, the result
emitted as `git diff-tree -p --full-index` (edited by us: the settled hunks below; everything else is the PR's and our
patches' own lines):
- 0001 `zig/src/families/glm/cuda_snapshot_pages.zig`: `fn ptr` -> `pub fn ptr` is already the series' text (no change)
- 0002 `zig/src/families/glm/cuda_snapshots.zig`: 0002's `blankAs` and `seal` and 0005's `ringHolds` with its two `seal` checks inserted before the series' `restore`; 0002's `UnsealedState` guard at the top of `restore`
- 0005 `zig/src/families/glm/cuda_snapshots.zig`: settled with 0002's reject
- 0006 `zig/src/core/rows_test.zig`: 0006's `gridRoundTrip` refactor is already the series' text; its two tests are present
- 0013 `docs/environment.md`: 0013's knob row, placed by the env-rows fit
- 0013 `zig/src/platform/environment.zig`: 0013's knob row, placed by the env-rows fit
- fit `zig/src/families/glm/cuda_env_test.zig`: the series' strict test counts GLM's readers without the TF_GLM_OVN_ rows and checks each of those in its own 'every speed-hunt knob' test, so `TF_GLM_OVN_DISK_SLICE_MIB` stays out of `counts`: the series' `counts` line is kept (the file is the series' own)
- fit `zig/src/platform/environment.zig`: the `TF_GLM_OVN_DISK_SLICE_MIB` row at the end of the series' TF_GLM_OVN_ group, after TF_GLM_OVN_KEEP_SEQS
- fit `docs/environment.md`: the `TF_GLM_OVN_DISK_SLICE_MIB` row at the end of the series' TF_GLM_OVN_ group, after TF_GLM_OVN_KEEP_SEQS

Apply after the series: `scripts/apply.sh WORK`, then `patches/pr1411/apply.sh WORK/tree` (`--check` writes nothing and
prints the tree it would make). Hashes: `SHA256SUMS`.

## Gate (spark5, 2026-11-15T17:28:49Z; `python work/V129B/recut_combined.py SERIES_DIR --gate`)

```
v129b-comb base tree 4be51cc6beefee860f611b5bb928dd06a4f3c72c
v129b-comb tree id 27a87244e7dca097007c8b086b7c49a76a8e69d2 (35 patches)
v129b-comb check rc=0 | 
v129b-comb fmt rc=0
[v129b-comb gates] check-native-cuda-host rc=0 | Build Summary: 7/7 steps succeeded
[v129b-comb gates] test-cuda-host rc=1 | Build Summary: 410/412 steps succeeded (1 failed); 6850/6885 tests passed (33 skipped, 2 failed)
[v129b-comb gates] compile-cuda-tests rc=0 | Build Summary: 10/10 steps succeeded
[v129b-comb gates] test-glm-ring-host rc=0 | Build Summary: 4/4 steps succeeded; 3/3 tests passed
[v129b-comb gates] test-glm-logprobs-host rc=0 | Build Summary: 4/4 steps succeeded; 10/10 tests passed
[v129b-comb gates] test-glm-onepass-order-host rc=0 | Build Summary: 3/3 steps succeeded
[v129b-comb gates] test-rows-host rc=0 | Build Summary: 3/3 steps succeeded
[v129b-comb gates] fmt rc=0 
[v129b-comb gates] GATES-DONE v129b-comb bad=1
[v129b-comb gates] rc=1
[v129b-comb names] v129-base: 2 failing names | 3836/3852 tests passed (14 skipped, 2 failed)
[v129b-comb names] v129b-comb: 2 failing names | 6850/6885 tests passed (33 skipped, 2 failed)
[v129b-comb names] only v129b-comb fails: none
[v129b-comb names] only v129-base fails: none
[v129b-comb names] rc=0
[v129b-comb lean] base /home/adam/v129/trees/base: 6454 files, 341 problems
[v129b-comb lean] head /home/adam/v129/trees/v129b-comb: 6512 files, 341 problems
[v129b-comb lean] lean: 341 problems, 341 on the base, 0 new
[v129b-comb lean] rc=0
[v129b-comb gates] error: 'cli_config_test.test.serve --config: expand reads the file, passes other commands through and names what it cannot read' failed:
[v129b-comb gates] error: 'listener.test.accepted IPv4 and IPv6 TCP streams disable Nagle for incremental responses' failed:
```
