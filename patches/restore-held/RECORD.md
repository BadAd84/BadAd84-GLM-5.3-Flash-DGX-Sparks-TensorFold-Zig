# RECORD.md - patches/restore-held

## Current base (re-seated 2026-11-20)

This package applies to upstream TensorFold main `1ece6e6dbbc073582d50738ce8e73e3c3261a73b` (1.3.0) with the packages before it in the order engine, pr1411, cache-salt, learn-starts,
solo-cuts, disk-any-position, restore-held: it takes the tree `f6a5171dad7e942bdf1c13690921e85f17462840` to `5ae4bbe5e4186133616753872b735b42ea18184d` (1 patch, 47 in all; both ids are
`git write-tree` on the tree built with `scripts/apply.sh` and the packages' `apply.sh` in that order). What each patch needed is in `docs/audit-2026-11-12/reseat-main-1ece6e6.md`.

Gate: full run `sg-20261120-165217` on the gate host, the pristine main (tree `3a37e287fb1c`) against this series (47 patches in the seven packages, tree `5ae4bbe5e418`, the id the run expected): `check-native-cuda-host`, `compile-cuda-tests` (10 of 10 steps), `test-glm-ring-host`, `test-glm-logprobs-host`, `test-rows-host`, `test-glm-pdl-scan` (3 of 3 tests), `test-kernel-contract` (258 of 258 tests) and `fmt` rc 0 on both, `test-glm-onepass-order-host` rc 0 on the stack (not a step of the base); `test-cuda-host` rc 1 on both with the base's one failing name, `cli_config_test`'s `serve --config` case (7,903 of 7,947 tests passed on the stack, 43 skipped, 1 failed; 7,687 of 7,731 on the base); no new failing name; lean base 6,993 files and 168 problems, head 7,063 files and 168 problems, 0 new. Verdict PASS. An earlier run of the same series (`sg-20261120-145609`) failed with 7 new failing names, every one an abort inside `cuLaunchKernelEx`: upstream's `7948cc42d` launches every GLM kernel through it and asks every fake test driver to forward it (`cuda_pdl.forwardEx`), and the fakes in tests our patches add (`cuda_mla_ovn_test`, the latent-rows test in `cuda_latent`, `cuda_disk_ranks_test`) did not. The lanes' quick checkpoints had not run the host test step, so only the full gate saw it; each of the five fakes now carries the line, inside the patch that owns the test (23, 36 and the `pr1411` package).

The text below was written for the v1.2.9 series (base `6b9de695104b6b8b30c20458da87ac06c9480289`): its file and line references, tree ids and measurements are to that base.

What it is: our own change (not an upstream commit), default off behind `TF_GLM_OVN_RESTORE_HELD`. A warm turn restores its
kept prompt state into a sequence and, a pass later, keeps the state again; each is a copy of the whole state between the
sequence and the snapshot pages. On three GB10s at TP=3 an nsys capture of a ~113k conversation (queue85's, rank 0,
`docs/audit-2026-11-12/queue-rows/queue85/pf-f85w/passes.txt`) shows 850 MiB in 10.8 ms for the restore and 858 MiB in 10.3 ms
for the keep on every turn, 21 ms of an 822 to 838 ms first token; the state is 7.5 MiB a 1,000 rows, so the cost grows with
the conversation (OVERNIGHT-2026-11-12.md, section 65). With the switch a restore into the sequence that still holds the state's
rows copies only what a sequence rewrites.

Why the rows are already there (file:line on the tree the package applies to):

- a sequence only appends: every forward writes rows from the sequence's position on (`Forward.run`, `cuda_forward.zig:401`,
  and a shared window's `begin`, `cuda_shared.zig:16`, call `State.ready` on each sequence first), and `State.reset`
  (`cuda_state.zig:501`), which `Engine.begin` calls for every request, clears the KDA records and the conv rows and nothing else;
- a released slot keeps its sequence: slot 0 always, every slot under `TF_GLM_OVN_KEEP_SEQS` (`cuda_engine.zig:331`), which the
  recipe sets;
- the rows a kept state shares with any later state of the same tokens are the ones `cuda_disk_image.parts` stores by position:
  each DSA layer's latent rows, their fp8 scales and its whole pools. The arena head (KDA records, conv rows, a window's saved
  rows), the two index rings a layer, the pool in progress with its spare row, the head's caches and the tail are a state's own.

What it does:

- `State.held` is the id and position of the kept state whose by-position rows the sequence holds. `keepAs` sets it (the
  snapshot is a copy of the live rows), a completed `restore` sets it, and `State.ready` clears it when the sequence's position
  is below the mark's: `ready` is what every forward calls on a sequence before it writes rows there (a prompt chunk, a solo or
  paired step, a batched pass, a verify window, a shared one), so no caller has to remember to. A restore clears it before it
  copies, so one that fails midway leaves no mark.
- `snapshots.restore` copies the plan less `layout.Plan.byPosition`'s ranges when the state's id is the mark's (an id names one
  state at one position) and the switch is on (`pages.Pool.moveBut`, whose `Copy.run` clips each piece with `pages.eachBut`); any other restore is whole,
  as is every restore into a paged sequence (`byPosition` names no range there; a state that left pages to the shared store
  (`TF_KV_SHARE`) is only kept by such a sequence).
- `Lanes.claim` gives a stream that resumes a kept state the free slot whose sequence still holds it (`Lanes.heldSlot`), else the
  lowest free slot as before, so conversations that alternate keep finding their own rows. A paged engine keeps the lowest slot.
- Every rank keeps its own mark and takes the same decision: the ranks run the same keeps, restores and steps.

Reply contract: none changes. The bytes of the sequence after a restore are the kept state's either way.

What it does not do: the keep still copies the whole state. Two kept states cannot share pages while a kept state is its parts
back to back (a part's offset depends on the position), so that half needs another layout or the copy taken off the first
token's path.

What it edits (all on the tree it applies to):

| file | change |
|---|---|
| `zig/src/families/glm/cuda_state.zig` | `State.held`, `Held`; `State.ready` clears the mark below it |
| `zig/src/families/glm/cuda_snapshot_layout.zig` | `Plan.byPosition` and `max_by_position` |
| `zig/src/families/glm/cuda_snapshot_pages.zig` | `Pool.moveBut`, `eachBut`; `Copy.run` clips by the ranges it is given (none: the copy as before) |
| `zig/src/families/glm/cuda_snapshots.zig` | `restoreHeld`; `keepAs` and `restore` set the mark; `restore` skips the held ranges |
| `zig/src/families/glm/cuda_lanes.zig` | `heldSlot`, `claimAt`; `claim` asks `heldSlot` first |
| `zig/src/families/glm/cuda_restore_held_test.zig` (new), `cuda_lanes_test.zig`, `cuda.zig` | the host tests and their registration |
| `zig/tests/cuda/glm_restore_held_check.zig` (new), `glm_ovn_checks.zig` | the GPU check `glm-restore-held-check` |
| `zig/src/platform/environment.zig`, `docs/environment.md` | the switch's registry row and docs row |

Base it applies to: the stack at the pin `6b9de695104b6b8b30c20458da87ac06c9480289` (v1.2.9) plus `patches/engine` (39 patches),
`patches/pr1411` (2), `patches/cache-salt` (2), `patches/learn-starts` (1), `patches/solo-cuts` (2) and
`patches/disk-any-position` (1), tree `9297755c6943c6f85d9c78ffdfd2bcc0f3a40e1d` (47 patches). This package makes tree
`83a3ea2a5b88a8eade1846f7f779d06bf6d96559` (48 patches); both ids are `git write-tree` on the tree built from the pin by
`scripts/apply.sh` and the packages' `apply.sh` in that order, with this package's `apply.sh --check` giving the second. It
applies last because it reads `cuda_disk_image.zig` (a file of `patches/pr1411`) in its host test and edits `cuda_snapshots.zig`
and `cuda_lanes.zig` below that package's and `patches/solo-cuts`' hunks.

## Gate

Full run `sg-20261120-113810` on the gate host, the pristine pin (tree `4be51cc6beef`) against the 48-patch stack (tree
`83a3ea2a5b88a8eade1846f7f779d06bf6d96559`, this package last): `check-native-cuda-host`, `compile-cuda-tests` (10 of 10 steps),
`test-glm-ring-host`, `test-glm-logprobs-host`, `test-rows-host` and `fmt` rc 0 on both, `test-glm-onepass-order-host` rc 0 on the
stack (not a step of the base); `test-cuda-host` rc 1 on both with the same one failing name, `cli_config_test`'s `serve --config`
case, which fails on the pristine v1.2.9 itself (6,931 of 6,965 passed on the stack, 33 skipped, 1 failed; 6,716 of 6,750 on the
base); lean base 6,454 files and 341 problems, head 6,525 files and 341 problems, 0 new. Verdict PASS.

## Mutants

Each is the patch with one change, run through the fast loop's `test-cuda-host` on the 48-patch stack (6,965 tests); each fails the
tests named, beyond the pristine `cli_config_test`. The names are short forms of the test titles. In `cuda_restore_held_test.zig`:
eachBut is `restore held: a copy leaves out the ranges it is told, piece by piece`; ranges is `restore held: the by-position ranges
are each DSA layer's latent rows, scales and whole pools, as the disk image counts them`; restore bytes is `restore held: a restore
into the sequence that kept the state copies its own parts alone, and every planned byte is the kept one`; paged is `restore held: a
paged sequence names no by-position range, its rows being on pages`; failed restore is `restore held: a restore that fails midway
leaves no mark, and the next one is whole`. In `cuda_lanes_test.zig`: slot choice is `TF_GLM_OVN_RESTORE_HELD: a stream that resumes a
kept state takes the free slot whose sequence still holds it`. The disk image tests and snapshot tests are existing tests
(`cuda_disk_image_test`, `glm_snapshot_host`, `glm_snapshot_host_ram`) that restore into a sequence still holding the state, with the
number that fail in brackets.

| mutant | what it changes | tests that fail |
|---|---|---|
| h1 | `State.ready` clears the mark at the mark's own row too (`pos <= at`) | restore bytes |
| h2 | `State.ready` never clears the mark | restore bytes |
| h3 | `restoreHeld` reads another switch (`SOLO_TO_START`) | restore bytes; slot choice |
| h4 | a keep marks its position plus one row | restore bytes; failed restore |
| h5 | a keep sets no mark | restore bytes; failed restore |
| h6 | any mark counts, whatever state it names | restore bytes |
| h7 | the held ranges are skipped whatever the switch says | restore bytes; snapshot tests (4) |
| h8 | the held ranges are skipped whatever the mark says (the switch still gates) | restore bytes; failed restore |
| h9 | a restore does not clear the mark before it copies | failed restore (the test aborts) |
| h10 | a completed restore marks row 0 | restore bytes; failed restore |
| h11 | a completed restore sets no mark | restore bytes; failed restore |
| h12 | `Pool.moveBut` passes no ranges to its copy | restore bytes |
| h13 | `eachBut` yields an empty piece before a range that starts where the copy has reached | eachBut |
| h14 | `eachBut` yields an empty piece after the last range when it ends the copy | eachBut |
| h15 | `Copy.run` copies a clipped piece the wrong way | restore bytes; disk image tests (4); snapshot tests (5) |
| h16 | a paged sequence names by-position ranges | paged |
| h17 | the latent range is one row short | ranges |
| h18 | no scales range | ranges |
| h19 | the pool in progress counts as held | ranges |
| h20 | `byPosition` names an empty range | ranges |
| h21 | `heldSlot` ignores the switch | slot choice |
| h22 | `heldSlot` ignores a paged engine | slot choice |
| h23 | `heldSlot` picks the slot that holds another state | slot choice |
| h24 | `heldSlot` may pick a slot a stream holds | slot choice |
| h25 | `claim` never asks `heldSlot` | slot choice |

All 25 are killed by tests. Two mutants of the first set did not build (h8 and h12 each left a constant or a parameter unused, which Zig
refuses, so their runs read a build error, not a result); they were rewritten to keep what they leave out in use and rerun, and the rows
above are from those runs. h9 is killed through an abort of its test: the test shortens a lease by one page so that its restore fails,
and with the mark kept the expectation fails; the test then ends with that page unreturned and, I think (an inference from the test's
text), the pool's own assertion aborts the process. A clean failure would need the test to put the page back with a `defer`.

## GPU checks

`tf-cuda-test glm-restore-held-check` (`zig/tests/cuda/glm_restore_held_check.zig`) on one GPU with glm-synth's 2-layer checkpoint, image
`glm53-zig:v129zg` (id `52a1f0ce250a` on spark1, spark2 and spark3, built from tree `83a3ea2a5b88` by `scripts/queues/queue90.sh`),
through that queue (12:10 UTC): with the switch off, rc 0 and `PASS TF_GLM_OVN_RESTORE_HELD off: every restore is whole, 3 cases, fp8
and bf16 caches; 6 planted controls (a held byte changed) were repaired`; with it on, rc 0 and `PASS TF_GLM_OVN_RESTORE_HELD=1: a
state resumed by the sequence that kept it equals a whole restore's in every planned byte and 12 greedy steps equal a cold run's, 3
cases, fp8 and bf16 caches; 6 planted controls (a held byte changed) stayed changed`. The verdict lines are in
`docs/audit-2026-11-12/queue-rows/queue90/synth-restore-held-*.pass.txt`.

Speed, queue90 (OVERNIGHT section 69; eight boots on that image, every reply one digest): the ~113k conversation's warm turns 0.95%
faster than the controls' mean (805.1 against 812.8 ms), the ~284k conversation's 2.54% faster (854.0 against 876.2 ms), the cold first
token at 8k, 32k and 120k level (0.06% faster, 0.03% and 0.06% slower), greedy decode at one client level. In the profiled boot the
restore of a warm turn that resumes into the sequence that kept the state is 164.6 MiB in 4.0 and 1.9 ms where the whole one, in queue85's
capture of the same turns, is 858.0 and 865.9 MiB in 11.5 and 11.8 ms. It passed its pre-written rule (`scripts/queue-scores/decide84.py`, block `held`) and is in the recipe's
env files.
