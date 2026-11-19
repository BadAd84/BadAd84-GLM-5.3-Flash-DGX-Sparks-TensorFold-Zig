# RECORD.md - patches/disk-any-position

What it is: our own change (not an upstream commit), on this repo's engine stack, that lets a conversation state's disk
image take any position, not only a multiple of the 4-row pool. With `--learn-conversations` the image's `parts` refused a
state off a pool's edge (`error.SnapshotShape`) and the store counted the save as skipped, so a state kept at a request start
or at a prompt's end reached the disk only when its position happened to be a multiple of 4: three in four did not.

Measured on this stack before the change (OVERNIGHT-2026-11-12.md, section 51; `TF_GLM_REQUEST_STARTS=1 --learn-conversations`
at TP=3 on image `v129w`, the stack with learn-starts): six saves skipped in the first boot, four in the second and five in
the third; the 32k and 120k conversations, whose only kept states were at 32,035 and 120,601 rows, resumed from nothing
(a cold first token of 16.2 and 60.0 s) after an eviction, a SIGKILL and a clean restart; the 596k-token conversation resumed
at 595,968 rows, the state its first turn kept, instead of 619,434, the endpoint its second turn kept. Every resumed reply
equalled a cold server's: the tier was exact and incomplete.

The path, before this package (file:line on the tree it applies to):

- the save: the store asks the family's image for a state's parts (`cuda_glm_disk.zig` through `cuda_disk_image.storeParts`),
  which calls `parts` (`cuda_disk_image.zig:117`): `if (at == 0 or at % sparse.pool != 0 or at > sh.capacity) return
  error.SnapshotShape`. The store logs `imprint: saving N tokens skipped (SnapshotShape)` and counts `save_skipped`; the request
  is unaffected, and the state stays in RAM only.
- the staging floor: `cuda_glm_disk.zig:190` opens the store with `longest` (`cuda_disk_image.zig:111`), the capacity's whole pools,
  because `parts` took no other position.

Why the alignment is not needed (each point is a read of the code at the pin plus this stack, not a measurement):

- the pooled-key kernel writes only a completed pool: `tf_glm_pool_keys` (`zig/kernels/cuda/glm_glue_index.cuh:39`) returns when
  `4 * p + 3 > pos + rows - 1`. A prompt pass that ends inside a pool leaves that pool's row unwritten, which is what
  `unwritten` (`cuda_disk_image.zig:214`) already assumes of every row past the whole pools (it zeroes them in the probe's image),
  and a pass that starts inside a pool reads that pool's earlier rows from the index rings, which the image carries.
- the shared rows layer takes it: `core/rows_image.zig` `valid` accepts a pooled part of `at / per` to `at / per + 1` rows, and
  `parts` gives exactly `at / pool` whole pools as rows by position and leaves the pool past them, with the spare row, as the
  state's own bytes (`cache`: `n / pool + 2` rows), as the RAM snapshot plan (`cuda_snapshot_layout.zig:89`) counts them.
- `segments`, `route`, `leaseBytes`, `imageBytes` and `unwritten` carry no other condition on `at`.

What it does: `parts` refuses a position of 0 or past the capacity and takes every other, and `longest` is the capacity. An
image written at a position on a pool's edge is unchanged, and so is the words' format: only states the old `parts` refused
are new files.

Reply contract: a kept state resumes the same tokens whether it came from RAM or from the image. The GPU check is the disk
tier's own (`scripts/queue-disk-tier.sh`): every resumed reply against a cold server's, after an eviction, a SIGKILL and a clean
restart. Its result is under Gate.

What it edits (all on the tree it applies to):

| file | change |
|---|---|
| `zig/src/families/glm/cuda_disk_image.zig` | `parts` takes any position from 1 to the capacity; `longest` is the capacity |
| `zig/src/families/glm/cuda_disk_image_test.zig` | the lease bytes against the snapshot plan at positions off a pool's edge; the longest state is the capacity; the rows by position at 6,143 and 6,141; the round trip through the lease and the probe hash's unwritten spans at 2,051 (two helpers taking the position) |

Base it applies to: the stack at the pin `6b9de695104b6b8b30c20458da87ac06c9480289` (v1.2.9) plus `patches/engine` (37
patches, series tree `d674e199cf6d97f7ac84a374c83153baabc911ed`), `patches/pr1411` (2), `patches/cache-salt` (2),
`patches/learn-starts` (1) and `patches/solo-cuts` (1, the revision that grows the index ring), tree
`b0ae14df04d750dfbc217d13efc9a998d0ac6ac8` (43 patches). This package makes tree
`7656da6d8139b1b139ad0262bd3bb812897b0665` (44 patches). Both ids are `git write-tree` on the tree built from the pin by
`scripts/apply.sh` and the packages' `apply.sh` in that order, with this package's `apply.sh --check` giving the second.

## Gate

- Full run `sg-20261119-210540` on the gate host, the pristine pin (tree `4be51cc6beef`) against the 44-patch stack (tree
  `7656da6d8139`, this package the last of it): `check-native-cuda-host`, `compile-cuda-tests`, `test-glm-ring-host`,
  `test-glm-logprobs-host`, `test-rows-host` and `fmt` rc 0 on both, `test-glm-onepass-order-host` rc 0 on the stack (not a step of
  the base); `test-cuda-host` rc 1 on both with the same one failing name, `cli_config_test`'s `serve --config` case, which fails on
  the pristine v1.2.9 itself (6,912 of 6,946 passed on the stack, 33 skipped, 1 failed; 6,716 of 6,750 on the base); lean base
  6,454 files and 341 problems, head 6,518 files and 341 problems, 0 new. Verdict PASS.
- Mutants, each the patch with one change, through the fast loop's `test-cuda-host`: each failed only the tests named here beyond the
  pristine `cli_config_test`. The names are short forms of the test titles, all `GLM disk image: ...`: lease bytes is `the lease bytes
  the image counts are the snapshot plan's, at each position and head length`; longest is `the longest state is the capacity, so
  the staging floor prices it`; rows by position is `the store's rows are by position from 0 in whole blocks; rings, pools in
  progress and the head are its own`; seal is `a disk read's blank state is refused until sealed, and its seal checks the words`;
  probe hash is `the probe's hash leaves out what a prompt pass does not write, whatever the slot ran before`; probe hash inside a
  pool is `the same inside a pool, where the unfinished pool's keys are not written either`.

| mutant | what it changes | tests that fail |
|---|---|---|
| u1 | `parts` refuses a position off a pool's edge, as before | longest; rows by position |
| u2 | `longest` is the capacity's whole pools, as before | longest |
| u3 | `parts` counts the pool in progress as a row by position | rows by position |
| u4 | `unwritten` leaves the pool in progress's row in the image | probe hash inside a pool |
| u5 | the lease's pooled rows round up | lease bytes; rows by position; seal; probe hash; probe hash inside a pool |

- The GPU image is `glm53-zig:v129za`, built from tree `9d7f1de0488a`, which differs from this stack's tree in test files and
  comment text only (`patches/solo-cuts/RECORD.md`, Gate).
- GPU, queue75 block E (`scripts/queue-disk-tier.sh f75` with `TF_GLM_REQUEST_STARTS=1 --learn-conversations`: boots `k1`, `k2` after a
  SIGKILL of every rank, `k3` after a clean stop, a reference boot without the tier; OVERNIGHT-2026-11-12.md, section 52): all 17 turns'
  replies equal a cold server's (token digests), `save_skipped`, `write_failed`, `restore_failed` and `check_failed` 0 on every rank in
  every boot. After the SIGKILL the 32k and 120k conversations resumed at 32,035 and 120,601 rows from the disk (first token 0.57 and
  0.93 s; 16.18 and 59.95 s on the stack without this package) and the 596k one at 619,434 rows, the endpoint its second turn kept
  (14.93 s; 595,968 rows and 28.73 s without it). The tool's two failed checks were its eviction step clearing the 2,048-row grid
  states while the states a turn resumes from sit at the previous prompt's end; `scripts/disk.py` now clears the real ones.
