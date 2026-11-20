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
`patches/engine` (39 patches), `patches/pr1411` (2), `patches/cache-salt` (2) and `patches/learn-starts` (1), tree
`24e9c520faf9b16dfe82cf53d88c8db36a520338` (44 patches). This package (two patches) makes tree
`181fa1a3dd7a6b876e56f373c43b3c7dfa984e12` (46 patches). Both ids are `git write-tree` on the tree built from the pin by
`scripts/apply.sh` and the packages' `apply.sh` in that order, with this package's `apply.sh --check` giving the second.
The docs hunk sits on `learn-starts`' text of the request starts row, so this package applies after it.

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

## 0002: `TF_GLM_OVN_SOLO_TO_START`, a solo step may end at a request start (2026-11-20)

What it is: our own change, default off. The first patch refuses a solo step whenever a request start lies inside it, the middle
grid point excepted. A chat prompt ends in a message start 3 rows before its last row (the reply's header), so a last stretch of
more than one grid step before that start ran as a 2,048-row pass and a remainder: queue85's capture shows an 8,183-row prompt as
passes of 4,096, 2,048, 2,036 and 3 rows (OVERNIGHT-2026-11-12.md, sections 59 and 64). A warm turn that adds 2,307 to 4,096 rows
is cut the same way. With the switch the solo step ends at the start: 4,096, 4,084 and 3 rows for that prompt.

What it does:

- `cuda_prompt_cuts.soloRows(len, cuts, start, to_start)` is the one statement of what a solo step is: the cold plan's next two
  chunks, the first of them a grid step (`nextCut(start) == start + prefill_rows`, so no start inside it), ending where the plan's
  chunk after it ends (`nextCut` of the middle point: the next start, a grid step on, or the prompt's end). Without `to_start` it
  returns null unless that end is the whole step's (`min(len, start + solo_rows)`), which is the rule of 0001 (`cutInside` over a
  whole step; a host test compares the two on every cold cut of the test prompts). With it the step ends at the start.
- `stepRows` (every rank's size of a step from the part it was sent) and `leaderRows` (rank 0's) return `soloRows`' answer for a
  long part or a wide step and `error.BadChunk` where it names none, so a rank that sizes a part differently refuses it; `leaderRows`
  returned 4,096 rows for any wide step before. `prompt_solo.at` (rank 0's choice) takes its rows from `soloRows`, asks `takesTwo`
  about the step's own end (a second chunk of one row is still not taken, a keep mark at the middle grid point still refuses) and
  `ringsAgree` about the step's own rows. `prompt_solo.allowed`, every rank's check, is unchanged: a step that ends at a start has
  none inside it.
- `prompt_solo.toStart()` reads the switch (`cuda.ovn.on("SOLO_TO_START")`); `Leader.chunk` (`cuda_follow.zig`) and
  `Engine.prefillChunk` (`cuda_engine.zig`) pass it to `leaderRows` and `stepRows`. The registry row is in
  `zig/src/platform/environment.zig`, the docs rows in `docs/environment.md` and `docs/recipes/glm-5.3-flash-cuda.md`, and rank 0
  logs the switch at boot.
- The pass itself is not touched: `prefillChunk` runs a step's rows as one pass whatever their count, as it does for a solo step
  that ends at the prompt's end, and a state is kept when the next step starts at a marked row, which the start still is.

Reply contract: 0001's, the tokens two 2,048-row chunks give. With the switch unset no step is sized differently.

What it edits: `cuda_prompt_cuts.zig`, `cuda_prompt_solo.zig`, `cuda_follow.zig`, `cuda_engine.zig` (the two call sites and the boot
log line), `zig/src/platform/environment.zig`, `docs/environment.md`, `docs/recipes/glm-5.3-flash-cuda.md`, and the GPU check
`zig/tests/cuda/glm_solo_tests.zig` (two prompts with request starts, below).

### Gate of 0002

Full run `sg-20261120-093958` on the gate host, the pristine pin (tree `4be51cc6beef`) against the 47-patch stack (tree
`9297755c6943c6f85d9c78ffdfd2bcc0f3a40e1d`: this package's two patches, `patches/disk-any-position` and patch 0039 included):
`check-native-cuda-host`, `compile-cuda-tests`, `test-glm-ring-host`, `test-glm-logprobs-host`, `test-rows-host` and `fmt` rc 0 on
both, `test-glm-onepass-order-host` rc 0 on the stack (not a step of the base); `test-cuda-host` rc 1 on both with the same one
failing name, `cli_config_test`'s `serve --config` case, which fails on the pristine v1.2.9 itself (6,925 of 6,959 passed on the
stack, 33 skipped, 1 failed; 6,716 of 6,750 on the base); lean base 6,454 files and 341 problems, head 6,523 files and 341
problems, 0 new. Verdict PASS.

### Mutants of 0002

Each is the patch with one added line changed, run through the fast loop's `test-cuda-host` on the 47-patch stack (6,959 tests);
each fails only the tests named, beyond the pristine `cli_config_test`. The names are short forms of the test titles (stepRows,
soloRows: a solo step is the plan's next two chunks, old rule: without to_start a solo step is sized and refused exactly as
cutInside over a whole step says, walk, server-list walk, 8k prompt: a prompt whose last message starts 3 rows before its end,
engine predicates: a solo pass taken between request starts, to_start predicates: a solo step ends at a start in its second chunk).

| mutant | what it changes | tests that fail |
|---|---|---|
| s1 | the first chunk need not be a grid step | stepRows; soloRows; old rule; walk; server-list walk; engine predicates; to_start predicates |
| s2 | without the switch a step may end at a start too | stepRows; soloRows; old rule; server-list walk; 8k prompt; engine predicates; to_start predicates |
| s3 | the switch is ignored: never to a start | stepRows; soloRows; server-list walk; 8k prompt; to_start predicates |
| s4 | two chunks judged by the prompt's end | to_start predicates |
| s5 | the rings asked about a whole step | to_start predicates |
| s6a | the switch is always on | engine predicates; to_start predicates |
| s6b | another switch is read | to_start predicates |
| s7 | rank 0 sizes a wide step without the switch | soloRows; walk; server-list walk; 8k prompt; to_start predicates |
| s8 | every rank sizes a long part without the switch | stepRows; soloRows; walk; server-list walk; 8k prompt |
| s9 | a long part is never refused | stepRows; old rule |
| s10 | rank 0's wide step is a whole one where the plan names none | soloRows; old rule |
| s11 | the step ends where its first chunk does | stepRows; soloRows; old rule; walk; server-list walk; 8k prompt; engine predicates; to_start predicates |
| s12 | rank 0's choice does not ask the plan | engine predicates; to_start predicates |
| s13 | no registry row | the build refuses: `TF_GLM_OVN_SOLO_TO_START has no row in platform/environment.zig` (the registry's own comptime check; no test runs) |

Thirteen are killed by tests. s13 is not a test result: the registry refuses a switch with no row at compile time, so the mutant
does not build.

### GPU checks of 0002

`tf-cuda-test glm-solo-check` now runs ten prompts, the eight it had and two with request starts (the 8,183-row chat shape above,
and one of 8,692 rows with starts off the 4-row index pool's edge, where a solo step runs from row 301 to the start at 3,350),
and fails unless the solo passes taken equal the case's own count for the setting (1 and 1 without the switch, 1 and 2 with it).
On the 8-prompt version, image `glm53-zig:v129zd`, three ranks, real checkpoint, through `scripts/gpu-check-tp3.sh`: rc 0 0 0, one
PASS line, 156 s (10:13 UTC). On the image with this patch, `glm53-zig:v129zf` (id `112d31581f2f` on all three ranks, built from
tree `9297755c6943` by `scripts/queues/queue89.sh`): one GPU on glm-synth's 2-layer checkpoint, switch off and on, PASS and PASS;
three ranks on the real checkpoint, four runs (the check's plain environment, then the recipe's `DEFS` and `NEWX`, each with the
switch off and on): rc 0 0 0 and one PASS line each, 172 to 181 s each; every one names the setting it ran. The speed result is
queue89's (OVERNIGHT section 64).
