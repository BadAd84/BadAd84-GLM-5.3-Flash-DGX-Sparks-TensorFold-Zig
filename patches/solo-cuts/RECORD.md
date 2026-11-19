# RECORD.md - patches/solo-cuts

What it is: our own change (not an upstream commit), on this repo's engine stack, that lets a solo prompt step
(`TF_GLM_CHUNK_SOLO=4096`) run in a request that has request starts (`TF_GLM_REQUEST_STARTS=1`) wherever no start lies
inside the step. Upstream's #2404 refuses a solo step for any request with a cut ("a pass with starts takes no solo or
batched pass"). A chat prompt has a message start after row 0, so every chat request under request starts ran in
2,048-row steps, and the solo pass's cold-prompt gain was lost on exactly the requests the starts are for. Measured on
this stack (OVERNIGHT-2026-11-12.md, section 50): a cold first token with request starts was +4.1%, +6.5% and +7.2%
slower than without them at 8k, 32k and 120k, equal to the solo-only arm's mean, and a ~113k cold prime cost 7.3% more.

The path, before this package (file:line on the tree it applies to):

- rank 0's choice: `cuda_follow.zig:259` (`Leader.chunk`) asks `prompt_solo.at` (`cuda_prompt_solo.zig:34`), which
  returned false whenever `e.cur.cuts.items.len > 0`; `prompt_cuts.leaderRows` (`cuda_prompt_cuts.zig:41`) then sizes
  the step: to the next cut, or a solo pass's rows when `wide`.
- every rank's step: `cuda_engine.zig:389` (`prefillChunk`) takes its rows from `prompt_cuts.stepRows`
  (`cuda_prompt_cuts.zig:53`), which returned `error.BadChunk` for a part longer than a grid step when any cut existed,
  and `cuda_engine.zig:392` asks `prompt_solo.allowed` (`cuda_prompt_solo.zig:44`), which refused with any cut.
- not changed: `prompt_pair.pairedAt` (`cuda_prompt_pair.zig:64`) still refuses a paired step with cuts and
  `cuda_lanes.zig:572` a batched pass; `cuda_lanes.zig:276` still sends the cuts to every rank before the first step.

What it does: `cuda_prompt_cuts.cutInside(cuts, start, rows)` is true when some cut `c` has `start < c < start + rows`.
`stepRows` returns a solo step's rows unless that holds, and `prompt_solo.at` and `prompt_solo.allowed` refuse exactly
when it holds. A cut at the step's first row is the step's own start, and one at its end is the next step's, so both
are fine. All three read the same list on every rank (the leader's `cuts` call sends it before the first step), so the
ranks size every step alike. A step that would end at a cut still ends there: a solo step is only taken where it runs
two whole grid chunks between cold cuts. `takesTwo` still refuses a step whose middle grid point holds a keep mark.
A request with no cut is untouched (`cutInside` is false for an empty list).

Reply contract: upstream's for a solo pass, the tokens two 2,048-row chunks give; the cold-reply digests with the
switch on and off are the GPU check, not part of this record until they have run.

What it edits (all on the tree it applies to):

| file | change |
|---|---|
| `zig/src/families/glm/cuda_prompt_cuts.zig` | `cutInside`; `stepRows` takes a solo step unless a start is inside it; the tests that expected a refusal for any cut now expect it for a start inside the step; a walk test (every step starts on a cold cut) |
| `zig/src/families/glm/cuda_prompt_solo.zig` | `at` and `allowed` refuse by `cutInside` in place of `cuts.items.len > 0`; a host test of both over start lists |
| `docs/recipes/glm-5.3-flash-cuda.md` | the request starts row: a solo pass only where no start is inside it |

Base it applies to: the stack at the pin `6b9de695104b6b8b30c20458da87ac06c9480289` (v1.2.9) plus
`patches/engine` (36 patches, series tree `bb881628a1995a58308c64c44a9522e9e3c153d2`), `patches/pr1411` (2),
`patches/cache-salt` (2) and `patches/learn-starts` (1), tree `85d45758d73b66f75f6fbe38b0c58a9cde586008` (41 patches).
This package makes tree `fc3526cde368da5a0a034794045c3bd5c1bf2814` (42 patches). Both ids are `git write-tree` on the
tree built from the pin by `scripts/apply.sh` and the packages' `apply.sh` in that order, with this package's
`apply.sh --check` giving the second. The docs hunk sits on `learn-starts`' text of the request starts row, so this
package applies after it.

## Gate

Measured on the shared gate host (x86_64, 16 threads) with `scripts/spark-gates.py`, pin `6b9de695104b`, Zig 0.17.0.

- Fast loop on `patches/engine,patches/pr1411,patches/cache-salt,patches/learn-starts,patches/solo-cuts` (tree
  `7708651f40d6`, 41 patches, before engine 0036 joined): `check-native-cuda-host` and `zig fmt` rc 0; lean 341 problems
  against 341 on the pristine pin, 0 new; `test-cuda-host` 3,145 of 3,167 passed, 21 skipped, 1 failed, `cli_config_test`'s
  `serve --config` case, which fails on the pristine v1.2.9 itself.
- Eight mutants of this patch, each applied in place of it on the same stack and run through `test-cuda-host`. Each fails
  exactly the tests named for it, plus the pristine pin's own case, and nothing else:

| mutant | what it changes | tests that fail |
|---|---|---|
| m1 | a start at the step's first row counts as inside it | stepRows, cutInside, engine predicates |
| m2 | a start at the step's end counts as inside it | stepRows, cutInside, engine predicates |
| m3 | `stepRows` never refuses a solo-sized step | stepRows, leader rows |
| m4 | `stepRows` refuses a solo step for any cut, as before | stepRows, leader rows, walk |
| m5 | rank 0's choice (`at`) refuses any cut, as before | engine predicates |
| m6 | rank 0's choice never refuses for a start | engine predicates |
| m7 | every rank's check (`allowed`) refuses any cut, as before | engine predicates |
| m8 | every rank's check never refuses for a start | engine predicates |

  The tests are `cuda_prompt_cuts`' "a step runs to the next cut, or solo where no start is inside it, from a cold cut only"
  (stepRows), "a start is inside a step when it falls past the step's first row and before its end" (cutInside), "rank 0's
  step rows (Leader.chunk) are the rows each other rank sizes from its part" (leader rows) and "a walk taking solo steps where
  no start is inside them starts every step on a cold cut" (walk), and `cuda_prompt_solo`'s "a solo pass: taken between request
  starts, refused where one is inside it, in rank 0's choice and the check" (engine predicates).
