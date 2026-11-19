# RECORD.md - patches/pr1411

What it is: upstream PR ashhart/TensorFold#1411 (GLM-5.3-Flash on CUDA keeps conversation states on disk, every rank's
part, `--learn-conversations`), by Robert Wojciechowski, with our 0011 and 0012 (the disk tests' MTP head flag) and 0013
(`TF_GLM_OVN_DISK_SLICE_MIB`, a read-ahead disk state restored in slices between rounds), as TWO patches on the recipe's
engine series: 0001 is the net patch of the PR's ten commits plus those three, 0002 the PR's later `1f6b50c67` (a disk
read sends each block's rows to the other ranks in one step). Retire the package when the pin moves past #1411's landing
on upstream main.

Source: repository `wojo/TensorFold`, branch `up-glm-disk`, head `f0a9651b6c718c73cf29b652e4bb13f85643e169` (12
commits) on upstream main `93de4c724`; checked 2026-11-17 with `gh pr view 1411 -R ashhart/TensorFold --json
state,headRefOid`, which printed `{"headRefOid":"f0a9651b6c718c73cf29b652e4bb13f85643e169","state":"OPEN"}`, not merged.
`git -C work/parity/tree range-diff 3885dceb2bb60fe02e609066b75ec752baf51e38..d730aff64a2daf4f8c10f8f737084edc5cc87326
93de4c724..refs/remotes/pr/1411-f0a9651b6` shows the ten commits 0001 nets as content-identical (`=`) and two new ones,
`1f6b50c67` (0002) and `f0a9651b6` (not carried: see 0002 below). The per-commit form of the same work on pristine v1.2.9
(each PR commit merged with its parent as the base, adding and removing only its own lines, and our three, gated on
spark5) is lane V129B's `work/V129B/package/patches/pr1411/`; its RECORD.md has the commit table and the edits each patch
carries.

Base it applies to: upstream v1.2.9 `6b9de695104b6b8b30c20458da87ac06c9480289` plus the engine series as it stands on
disk (`patches/engine/0001` to `0035`, 35 patches), tree `2af443845021d4b310032b3e51d81c38d6059df4` (the pin's own tree
`4be51cc6beefee860f611b5bb928dd06a4f3c72c`). 0001 alone makes `6f9edaa1ea9b782d1616edaa96a1c70325fd00e1`, the two
together `acc0517075df9dc954b9667d582ebcc8c995337d`, and both patches apply with `--check` on that engine tree
(`patches/pr1411/apply.sh --check`); with `patches/cache-salt/` on top the whole stack is
`5137a5ef75ab14cbe0a83ba34511523e2322795c`. The earlier 0001-only record measured the series at 32 patches, tree
`e02b8a89c2ccbb7fe67e42fb4bf300bec1a5f2c3`, final `3b06d167fd742683f210ffc7f69eef5199640664`.


Why 0001 is one net patch of the PR's ten commits: the series rewrites the CUDA-family scaffolding the PR patches, so the
per-commit patches leave 6 rejected hunks on it. Made by `python work/V129B/recut_combined.py /mnt/c/Users/Adam/Gitea/GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig/work/V129A/series`: the per-commit package applied to the
series tree with --reject, each reject settled, the GLM env test and rows fitted to the series' conventions, the result
emitted as `git diff-tree -p --full-index` (edited by us: the settled hunks below; everything else is the PR's and our
patches' own lines). The numbers below are the PR's own commits:
- 0001 `zig/src/families/glm/cuda_snapshot_pages.zig`: `fn ptr` -> `pub fn ptr` is already the series' text (no change)
- 0002 `zig/src/families/glm/cuda_snapshots.zig`: 0002's `blankAs` and `seal` and 0005's `ringHolds` with its two `seal` checks inserted before the series' `restore`; 0002's `UnsealedState` guard at the top of `restore`
- 0005 `zig/src/families/glm/cuda_snapshots.zig`: settled with 0002's reject
- 0006 `zig/src/core/rows_test.zig`: 0006's `gridRoundTrip` refactor is already the series' text; its two tests are present
- 0013 `docs/environment.md`: 0013's knob row, placed by the env-rows fit
- 0013 `zig/src/platform/environment.zig`: 0013's knob row, placed by the env-rows fit
- fit `zig/src/families/glm/cuda_env_test.zig`: the series' strict test counts GLM's readers without the TF_GLM_OVN_ rows and checks each of those in its own 'every speed-hunt knob' test, so `TF_GLM_OVN_DISK_SLICE_MIB` stays out of `counts`: the series' `counts` line is kept (the file is the series' own)
- fit `zig/src/platform/environment.zig`: the `TF_GLM_OVN_DISK_SLICE_MIB` row at the end of the series' TF_GLM_OVN_ group, after TF_GLM_OVN_KEEP_SEQS
- fit `docs/environment.md`: the `TF_GLM_OVN_DISK_SLICE_MIB` row at the end of the series' TF_GLM_OVN_ group, after TF_GLM_OVN_KEEP_SEQS

0002, the PR's disk-read-rows commit: upstream `1f6b50c67` (author and subject in its header), the first of the two
commits head `f0a9651b6` added after `d730aff64`, applied on 0001 with `git apply --reject`: no hunk was rejected and
nothing was settled by hand. 4 files, +175/-20: `cuda_disk_image.zig` (`Copy.fromDevice`, device bytes into image bytes
a page at a time, no host copy), `cuda_disk_ranks.zig` (`Op.put` -> `Op.rows`, `rows` with `place` and `fits`,
`copyDevice`, `copy` factored through `through`), `cuda_disk_ranks_test.zig` (two new tests, rows entries in the bad-step
table), `cuda_glm_disk.zig` (`scatter` one table and one broadcast instead of a step per rank per piece). Cut with
`scripts/mkpatch.sh` from saved copies of the four files in the 0001 tree, so it is exactly the diff from the 0001 tree to
the tree with the commit; re-cut from those copies and compared byte for byte, the same sha256.

`f0a9651b6` is not carried: it only takes `const glm = @import("glm_cuda");` out of `zig/src/native/cuda.zig` and names the
import at the two places where the file compares, because upstream main holds that file at 600 lines and the import took it
to 601. On this series `zig/src/native/cuda.zig` is 600 lines, and 0001 already writes the inline
`F == @import("glm_cuda").native` at both of those places, so the commit's patch has no pre-image line here and no part of
it is missing from the tree.

The two restore paths after 0002 (both end in the same family `scatter`):
- default, `TF_GLM_OVN_DISK_SLICE_MIB` unset or 0: `rows_slices.budget()` is 0, so `lane_host_fetch.slice()` returns
  before it begins a restore, the request reads its state whole when it is admitted, and `cuda_glm_disk.scatter` sends
  the other ranks' and the shared pieces of each block through `ranks.rows`: one table and one broadcast of their bytes
  per link-sized step, the shared rows once for every rank, and each rank copies its pieces from the link's buffer device
  to device (`place`, `copyDevice`, `Copy.fromDevice`). That is the commit's own path, line for line; no line of 0002 reads
  the knob.
- sliced, the knob set to a whole MiB count: `rows_slices.begin` starts a `Restore` at a lookup and one turn of the engine
  loop takes a slice (`slices.step(x, budget)`, a range at image byte 0 going whole with the words), which calls the same
  family `scatter` with that slice's ranges. Each slice is then one `rows` step of that slice's pieces (more only past the
  link's room), the seal still rides the first slice, and `finish` enters the state as an entry once it is whole.

Apply after the series: `scripts/apply.sh WORK`, then `patches/pr1411/apply.sh WORK/tree` (both patches, in file-name
order; `--check` writes nothing and prints the tree it would make), then `patches/cache-salt/apply.sh WORK/tree`, whose two
patches apply unchanged on top. Hashes: `SHA256SUMS`.

## Gate of 0001 and 0002 (the shared x86_64 gate box, 2026-11-17; `scripts/spark-gates.py`)

Fast loop, `iter --pin 6b9de695104b6b8b30c20458da87ac06c9480289 --dir
patches/engine,patches/pr1411,patches/cache-salt check fmt test lean`:

```
tree id 5137a5ef75ab14cbe0a83ba34511523e2322795c (39 patches applied)
== check-native-cuda-host
Build Summary: 7/7 steps succeeded
check rc=0 in 10 s
== fmt
fmt rc=0 in 1 s
== test-cuda-host
error: 'cli_config_test.test.serve --config: expand reads the file, passes other commands through and names what it cannot read' failed:
Build Summary: 410/412 steps succeeded (1 failed); 6821/6855 tests passed (33 skipped, 1 failed)
test rc=1 in 545 s
== lean, against the pristine pin
base ~/spark-gates/pins/6b9de695104b6b8b30c20458da87ac06c9480289: 6454 files, 341 problems
head ~/spark-gates/iter-iter/tree: 6516 files, 341 problems
lean: 341 problems, 341 on the base, 0 new
lean rc=0 in 10 s
```

Green: the one failing test name is the pristine pin's own, and lean has 0 new problems.

Full run, `gates --pin 6b9de695104b6b8b30c20458da87ac06c9480289 --tree base --tree
stack=patches/engine,patches/pr1411,patches/cache-salt --clean`, run `sg-20261117-013844`:

```
                             base          stack
patches                      0/0           39/39
tree id                      4be51cc6beef  5137a5ef75ab
expected                     match         -
check-native-cuda-host       0             0
test-cuda-host               1: 1 failing  1: 1 failing, 0 new
compile-cuda-tests           0             0
test-glm-ring-host           0             0
test-glm-logprobs-host       0             0
test-glm-onepass-order-host  n/a           0
test-rows-host               0             0
fmt                          0             0
gate-names                   -             0
lean new                     -             0
verdict                      reference     PASS
```

[stack names] base: 1 failing names | 6716/6750 tests passed (33 skipped, 1 failed)
[stack names] stack: 1 failing names | 6899/6933 tests passed (33 skipped, 1 failed)
[stack names] only stack fails: none; only base fails: none
[stack lean] base 6454 files, 341 problems; head 6516 files, 341 problems; lean: 0 new
VERDICT PASS: stack pass against base

The one failing name on both trees is `cli_config_test.test.serve --config: expand reads the file, passes other
commands through and names what it cannot read`, the pin's own failure; the two new tests of 0002 are inside the 6899
that passed, and `gate-names` finds no name that only the stack fails.

Mutation receipt for 0002: the package with one added line of `cuda_disk_ranks.zig` changed (in `place`,
`table[i + 3] == every and me == 0`, so a follower copies none of the shared pieces: the PR author's own "drop the shared
pieces on a follower"), built as `work/Pr1411b/mut` by `work/Pr1411b/mutant-repo.sh` (anchor matched exactly once) and
run as `iter --pin 6b9de695104b6b8b30c20458da87ac06c9480289 --name mut --dir
patches/engine,work/Pr1411b/mut,patches/cache-salt test`:

```
tree id 1d5e97b617ee452ab02c9c65eafe442beb46dd9f (39 patches applied)
== test-cuda-host
error: 'cuda_disk_ranks_test.test.GLM disk ranks: a follower copies its pieces and the shared ones from the step's broadcast, and no other rank's' failed:
error: 'cli_config_test.test.serve --config: expand reads the file, passes other commands through and names what it cannot read' failed:
Build Summary: 409/412 steps succeeded (2 failed); 6898/6933 tests passed (33 skipped, 2 failed)
iter rc=1
```

The mutated tree (`1d5e97b6...`) differs from the clean one (`5137a5ef...`), and the only failing name it adds to the
pin's own `cli_config_test` is that new follower test: the two tests of 0002 are load bearing.


## Gate of 0001 alone (spark5, 2026-11-15T17:28:49Z; `python work/V129B/recut_combined.py SERIES_DIR --gate`)

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
[v129b-comb lean] base ~/v129/trees/base: 6454 files, 341 problems
[v129b-comb lean] head ~/v129/trees/v129b-comb: 6512 files, 341 problems
[v129b-comb lean] lean: 341 problems, 341 on the base, 0 new
[v129b-comb lean] rc=0
[v129b-comb gates] error: 'cli_config_test.test.serve --config: expand reads the file, passes other commands through and names what it cannot read' failed:
[v129b-comb gates] error: 'listener.test.accepted IPv4 and IPv6 TCP streams disable Nagle for incremental responses' failed:
```

## With `patches/engine/0036` in the series (2026-11-19)

The series is then 36 patches, tree `bb881628a1995a58308c64c44a9522e9e3c153d2`; this package applies to it unchanged
and makes `da6fb412b415964303c93c18d7da9f98626c9b85` (`git write-tree` on a temporary index from the pin).
`patches/cache-salt` then makes `33247f87b97b2762424a0e5390cf86044be13268`.
