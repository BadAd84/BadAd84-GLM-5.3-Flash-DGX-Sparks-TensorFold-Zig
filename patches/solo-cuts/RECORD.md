# RECORD.md - patches/solo-cuts

What it is: our own change (not an upstream commit), on this repo's engine stack, that lets a solo prompt step
(`TF_GLM_CHUNK_SOLO=4096`) run in a request that has request starts (`TF_GLM_REQUEST_STARTS=1`) wherever the plan's next
two chunks are the grid's two. Upstream's #2404 refuses a solo step for any request with a cut ("a pass with starts takes no
solo or batched pass"). The server's chunk plan lists a start at every grid step from the last start as well as at each
message, so every chat request under request starts ran in 2,048-row steps, and the solo pass's cold-prompt gain was lost on
exactly the requests the starts are for. Measured on this stack (OVERNIGHT-2026-11-12.md, section 50): a cold first token with
request starts was +4.1%, +6.5% and +7.2% slower than without them at 8k, 32k and 120k, equal to the solo-only arm's mean, and a
~113k cold prime cost 7.3% more.

The first version of this package counted every start between a step's first row and its end, including the cut the plan
itself lists at the step's middle grid point, so it took no solo step on a real request: its GPU run (section 51) read +4.24%,
+6.94% and +7.45% cold at 8k, 32k and 120k, as the arm without it read +4.80%, +7.13% and +7.69%. Its host tests used start
lists with a few message starts and no grid steps. This version leaves the middle point out, tests with lists shaped as
`chunk_plan.Plan.starts` and `withCut` build them, and grows the index ring (below).

The path, before this package (file:line on the tree it applies to):

- rank 0's choice: `cuda_follow.zig:259` (`Leader.chunk`) asks `prompt_solo.at` (`cuda_prompt_solo.zig:34`), which
  returned false whenever `e.cur.cuts.items.len > 0`; `prompt_cuts.leaderRows` (`cuda_prompt_cuts.zig:41`) then sizes
  the step: to the next cut, or a solo pass's rows when `wide`.
- every rank's step: `cuda_engine.zig:389` (`prefillChunk`) takes its rows from `prompt_cuts.stepRows`
  (`cuda_prompt_cuts.zig:53`), which returned `error.BadChunk` for a part longer than a grid step when any cut existed,
  and `cuda_engine.zig:392` asks `prompt_solo.allowed` (`cuda_prompt_solo.zig:44`), which refused with any cut.
- the list: `zig/src/server/chunk_plan.zig` `Plan.starts` appends `last + step` until the prompt's end (a grid start) and takes
  a message start sooner when one lies 256 or more rows past the last start (`withCut` adds the system end); `cuda_lanes.zig:276`
  sends it to every rank before the first step. After a message start the grid restarts from it.
- the ring: `State.ready` (`cuda_state.zig:533`) rebases the index rings to the pool below the pass's first row when it does
  not fit, then returns `error.PastRing` unless `pos + rows <= base + ring_rows`. `index_ring` (`cuda_state.zig:27`) was
  `2 * prefill_rows`, a solo pass's rows exactly, so a solo pass from a row off the 4-row pool's edge (`pos % 4` of 1 to 3,
  which every grid after a message start is, for three starts in four) failed there.
- not changed: `prompt_pair.pairedAt` (`cuda_prompt_pair.zig:64`) still refuses a paired step with cuts and
  `cuda_lanes.zig:572` a batched pass.

What it does:

- `cuda_prompt_cuts.cutInside(cuts, start, rows)` is true when some cut `c` has `start < c < start + rows` and `c` is not the
  step's middle grid point `start + prefill_rows`. A solo step is two chunks of the cold plan run as one pass: the plan's next
  chunk ends at `start + prefill_rows` and the one after it at the step's end, which holds exactly when `cutInside` is false (the
  walk test checks this against `nextCut`). A cut at the step's first row is the step's own start, and one at its end is the next
  step's, so both are fine.
- `stepRows` returns a solo step's rows unless `cutInside`, and `prompt_solo.at` and `prompt_solo.allowed` refuse exactly when it
  holds. All three read the same list on every rank, so the ranks size every step alike. `takesTwo` still refuses a step whose
  middle grid point holds a keep mark. A request with no cut is untouched (`cutInside` is false for an empty list).
- `cuda_state.zig`: `solo_rows` is `2 * prefill_rows` (as before) and `index_ring` is `solo_rows + sparse.pool`, so a solo pass
  from any row fits after its rebase (`pos % pool + solo_rows <= index_ring`). The plain grid starts every step on a multiple of
  2,048, where the rings rebase exactly as before. The ring is 4 rows (1 KiB) longer in each of 2 rings for each DSA layer and
  the head, 24 KiB a state at TP=2 (`cuda_kv8_test.zig` pins the arena's bytes, and moves by that); a kept state's image and the
  disk store's identity carry the ring's size, so a store written before this change is not read.

Reply contract: upstream's for a solo pass, the tokens two 2,048-row chunks give. The GPU check (cold first token and every
reply with request starts on and solo on, against the recipe without them, and a growing conversation sent as one salt to every
arm) is `scripts/queues/queue74.sh`; its result is under Gate.

What it edits (all on the tree it applies to):

| file | change |
|---|---|
| `zig/src/families/glm/cuda_prompt_cuts.zig` | `cutInside` leaves the middle grid point out; the tests that expected a refusal for a start at the middle now expect a step, and one row off it still a refusal; a walk over lists shaped as the server sends them (every step starts on a cold cut, and a step is solo exactly where the plan's two chunks are the grid's) |
| `zig/src/families/glm/cuda_prompt_solo.zig` | `at` and `allowed` refuse by `cutInside` in place of `cuts.items.len > 0`; a host test of both over start lists, at a start on and off the pool's edge; a host test that `State.ready` fits a solo pass from each pool residue |
| `zig/src/families/glm/cuda_state.zig` | `solo_rows` and `index_ring` as above |
| `zig/src/families/glm/cuda_kv8_test.zig` | the arena bytes at four contexts, 24,576 more each |
| `docs/recipes/glm-5.3-flash-cuda.md` | the request starts row: a solo pass where no message start is inside it |

Base it applies to: the stack at the pin `6b9de695104b6b8b30c20458da87ac06c9480289` (v1.2.9) plus
`patches/engine` (37 patches, series tree `d674e199cf6d97f7ac84a374c83153baabc911ed`), `patches/pr1411` (2),
`patches/cache-salt` (2) and `patches/learn-starts` (1), tree `098a8968dc83c191e71c67bc3a9a13da9545a52c` (42 patches).
This package makes tree `b0ae14df04d750dfbc217d13efc9a998d0ac6ac8` (43 patches). Both ids are `git write-tree` on the
tree built from the pin by `scripts/apply.sh` and the packages' `apply.sh` in that order, with this package's
`apply.sh --check` giving the second. The docs hunk sits on `learn-starts`' text of the request starts row, so this
package applies after it.

## Gate

- Full run `sg-20261119-210540` on the gate host, the pristine pin (tree `4be51cc6beef`) against the 44-patch stack (tree
  `7656da6d8139`, this package and `patches/disk-any-position` included): `check-native-cuda-host`, `compile-cuda-tests`,
  `test-glm-ring-host`, `test-glm-logprobs-host`, `test-rows-host` and `fmt` rc 0 on both, `test-glm-onepass-order-host` rc 0 on the
  stack (not a step of the base); `test-cuda-host` rc 1 on both with the same one failing name, `cli_config_test`'s `serve --config`
  case, which fails on the pristine v1.2.9 itself (6,912 of 6,946 passed on the stack, 33 skipped, 1 failed; 6,716 of 6,750 on the
  base); lean base 6,454 files and 341 problems, head 6,518 files and 341 problems, 0 new. Verdict PASS.
- Mutants, each the patch with one change, through the fast loop's `test-cuda-host`: each failed only the tests named here beyond the
  pristine `cli_config_test`. The names are short forms of the test titles: stepRows is `glm request starts: a step runs to the next
  cut, or solo where no start is inside it, from a cold cut only`; cutInside is `a start is inside a step when it falls past the
  step's first row and before its end`; walk is `a walk taking solo steps where no start is inside them starts every step on a cold
  cut`; server-list walk is `the server's list has a start every grid step, and a walk takes solo steps between messages`; leader
  rows is `rank 0's step rows (Leader.chunk) are the rows each other rank sizes from its part`; engine predicates is `a solo pass:
  taken between request starts, refused where one is inside it, in rank 0's choice and the check`; ring fit is `a solo pass from any
  row fits the index ring once the rings rebase at its first row`; arena bytes (kv8) is `GLM FP8 KV: canonical per-rank state bytes
  at configured long windows are metadata rather than a fit claim`.

| mutant | what it changes | tests that fail |
|---|---|---|
| m1 | a start at the step's first row counts as inside it | stepRows; cutInside; server-list walk; engine predicates |
| m2 | a start at the step's end counts as inside it | stepRows; cutInside; server-list walk; engine predicates |
| m3 | `stepRows` never refuses a solo-sized step | stepRows; leader rows |
| m4 | `stepRows` refuses a solo step for any cut, as before | stepRows; leader rows; walk; server-list walk |
| m5 | rank 0's choice (`at`) refuses any cut, as before | engine predicates |
| m6 | rank 0's choice never refuses for a start | engine predicates |
| m7 | every rank's check (`allowed`) refuses any cut, as before | engine predicates |
| m8 | every rank's check never refuses for a start | engine predicates |
| m9 | the step's middle grid point counts as inside it, as in the first version | stepRows; cutInside; server-list walk; engine predicates |
| m10 | the index ring holds a solo pass's rows and no pool more | arena bytes (kv8); ring fit |

- Image `glm53-zig:v129za` (id `15941b680fe9`, the same on spark1, spark2 and spark3) was built from tree `9d7f1de0488a`, source
  tar sha256 `a96cdfc17d4cfe9b934d45acceffdea21a794f336140e8f3e52f390e2c5ca9f0`. It differs from the committed stack's tree
  `7656da6d8139` in three test files and comment text only (`diff` of the two source tars: the arena bytes in `cuda_kv8_test.zig`,
  which the image's copy still had at the old sizes, and trailing or doc comments in `cuda_prompt_cuts.zig` and
  `cuda_prompt_solo.zig`); every line of engine code is equal.
- GPU, queue74 block C1 (`scripts/queue-scores/score74.py`, boots f1 rs1 rs2 f2, `TF_GLM_REQUEST_STARTS=1` on rs, one seed on every
  boot): cold first token with request starts against the mean of the two boots without them (their spread 0.20%, 0.51% and 0.27%):
  rs1 +1.23%, +0.49%, +0.18% and rs2 +1.19%, +0.35%, +0.17% at 8k, 32k and 120k, down from +4.2%, +6.9% and +7.5% before this
  package's revision. One reply digest for each (size, request) over all four boots. A growing conversation of about 113k tokens (one
  salt, 8 turns): the first turn 1.000 of the recipe's, turns 2 to 8 0.653 (851 against 1,304 ms on average), all 8 turns with one
  reply digest and one prompt length over the four boots; turn 2 resumed at 112,640 rows, the start its first turn kept, and turns 3
  to 8 at 113,963, 115,252, 116,524, 117,793, 119,038 and 120,286 rows, each the previous prompt's end less its three header tokens.
