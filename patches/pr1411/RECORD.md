# RECORD.md - patches/pr1411

What it is: upstream PR ashhart/TensorFold#1411 (GLM-5.3-Flash on CUDA keeps conversation states on disk, every rank's
part, `--learn-conversations`), by Robert Wojciechowski, re-seated on this recipe's engine, plus one test-fixture line
our own series needs. Retire the package when the pin moves past #1411's landing on upstream main.

Source: repository `wojo/TensorFold`, branch `up-glm-disk`, head `d730aff64a2daf4f8c10f8f737084edc5cc87326` (10 commits),
on upstream main `3885dceb2bb60fe02e609066b75ec752baf51e38`; fetched as `pull/1411/head` on 2026-11-14.

Base it applies to: `93a2e93ecebff8aa52b88e58c5dd222516e69c5f` (v1.2.7) plus `patches/engine/` 0001-0036, tree
`2a07e8cff17123a4fad350f5fb1213fcdb93e28e`, i.e. after `scripts/apply.sh`; final tree `e8f7f3c74548a445c98da58910aa13a7f1c6ee88` (0001-0012 alone: `e567d98959661da15d756103cc2d59051cacb78b`). On 0001-0035 the base tree was `685c6abbda55` and the final `321771fa88e0`. On 0001-0034 alone (the tree the gates and the images `rs2x3d` and `pr1411` were built from) the base tree was `f5495931b233` and the final `4156b5dd8708e1c423372a0bd4484608afad8bef` (the PR's ten alone: `886db39a209392dcf43123790aafb2bd060ba1c8`).

How it was made (`work/disk-tier/package.py`): each commit merged onto the tree so far with its parent as the base,
re-emitted as `git diff-tree -p --full-index` under its own author, date and message. Every patch adds and removes
only lines the original commit does; a change our series already carries is left out and named in the table. Edited by
us: the context of the patches the table marks three-way (the files our series also touches) and the index lines of
all ten; patch 0011 is ours.

| patch | source | how |
|---|---|---|
| 0001 | `79b80934f` | context re-seated (three-way); already in our series, so not in the patch: `-    fn ptr(a: Arena) u64 {`, `+    pub fn ptr(a: Arena) u64 {` |
| 0002 | `1e957fbe5` | context re-seated (three-way) |
| 0003 | `422bac28a` | as is |
| 0004 | `8cf55dc16` | as is |
| 0005 | `d526c36df` | as is |
| 0006 | `8b86def3b` | already in our series whole (16 lines) |
| 0007 | `48b3425e4` | as is |
| 0008 | `5361d4ecb` | as is |
| 0009 | `4f4da8e25` | as is |
| 0010 | `d730aff64` | as is |
| 0011 | `e6b0aea97` | ours (fork commit), for patches/engine/0028 |
| 0012 | `ours` | for patches/engine/0028: the rig's Engine.head, undefined without it |
| 0013 | `ours` | TF_GLM_OVN_DISK_SLICE_MIB: a read-ahead state restored in slices between rounds |

Apply after the series: `scripts/apply.sh WORK` then `patches/pr1411/apply.sh WORK/tree` (`--check` writes nothing and
prints the tree it would make). Hashes: `SHA256SUMS`.
