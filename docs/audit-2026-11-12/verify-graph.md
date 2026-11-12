# verify-graph.md - one-stream verify windows as CUDA graphs on the re-seated tree (lane VerifyGraph, 2026-11-12)

The lever of `round-structure.md` section 5.2 (item 2 of its table), built as one patch on the re-seat's final tree.
Everything here is code reading, host builds and host tests on the workstation; nothing ran on a GPU or a Spark. The
patch, its tools and the full check output are in `work/vgraph/` (`PROOF.md`); citations are `file:line` in the
patched tree (`work/vgraph/tree`, git tree `a7f220edfb289f62c8a1755b67266bc2a85e0894`) unless they name the base;
`P:<file>:<line>` is production's `work-recon/pyprod/tensorfold/families/glm5_next/cuda/<file>`, as in
`round-structure.md`.

## Result

`work/vgraph/0034-verify-graph.patch`: one patch, 13 files, +823/-19, a `git diff-tree -p --full-index` from the
re-seat final tree `93a99447e7030697ca29b93cc1410871bb34c98a` (upstream v1.2.7 `93a2e93ecebf` plus re-seat patches
0001-0033). No helper patch was needed.

| check | result |
|---|---|
| 1. plain `git apply --check` on `93a99447` | rc=0; the applied tree equals `a7f220ed` |
| 2. lines and comments | largest touched file 565 (`cuda_forward.zig`); 0 added comment lines past 120 columns; 0 comment lines after a comment line |
| 3. `scripts/gates.sh` (tree on `~/vg/vgraph`) | every step rc=0: `check-native-cuda-host`, `test-cuda-host` (383/383 steps), `compile-cuda-tests` (the GPU check compiles), the four standalone host steps, `zig fmt --check` |
| `scripts/gate-names.sh v127base vgraph`, `reseat vgraph` | 0 failing names on either side, both comparisons |
| `scripts/lean.sh` base `93a99447` against head | base 6253 files / 386 problems, head 6256 / 386, 0 new |
| 4. forward references (`work/reseat/refs.py`'s walk) | clean: 0 missing imports, 0 flagged identifiers |
| mutants of the decisions (host tests) | see "Mutants" below |

The first gate run failed to compile (`std.EnumSet(..).initEmpty` and `std.StaticBitSet(64).initEmpty` do not exist in
the gate's Zig std, which has `.empty`); fixed, and the second run is the green one above. GPU receipts: none yet
(the run plan is at the end).

## What the patch does

- **The switch.** `TF_GLM_OVN_VERIFY_GRAPH`, a `.glm` flag row (`zig/src/platform/environment.zig:114`), its line in
  `docs/environment.md:80`, read with `cuda.ovn.on("VERIFY_GRAPH")` (`cuda_vgraph.zig:125`). Default off.
- **The split.** `Forward.run` is now `stage` then `compute` (`cuda_forward.zig:376-409`): `stage` is the old run's
  first loop (rings readied, pending rows set, ids copied with `copy_source.enqueue`), `compute` the rest (embed,
  `whole` or `pieced`, `finish`), unchanged in order. `chunksAt` (`:371`) is the dense chunk count both `whole` and
  `pieced` computed inline.
- **The hook.** `Engine.verify` calls `cuda_vgraph.run` and falls back to `f.run` when it returns false
  (`cuda_engine.zig:446`); `Engine.deinit` frees the graphs after its synchronize (`:231`).
- **The graphs** (`cuda_vgraph.zig`, 351 lines): `run` (`:124`) stages the ids eagerly, computes the key (`shapeOf`,
  `:36`), runs the window's first time eagerly and from the second through `graph_cache.Cache(Key)` (`step`, `:111`);
  its engine (`capture`, `launch`, `free`, `:264-311`) keeps each graph's template beside the executable so the
  score nodes can be set before a replay.
- **One owner for the score launch.** `sparse.scoreLaunch` (`cuda_sparse.zig:99`) builds the scores launch (kernel,
  grid, arguments) that `selectTokensProfile` used to build inline, and `index.scoresLaunch`
  (`cuda_index.zig:161`) the index kernel's; the eager selection now launches what they return
  (`cuda_sparse.zig:136-139`), and the replay sets the same data on its nodes. `dsa_block.selectOf` (`:121`) is the
  selection's inputs `attend` passed inline; `dsa_block.scoreLaunch` (`:128`) is `attend`'s first-block scores
  launch for a window. `sparseFrom`, `denseBelow` and `scoreBlocks` hold the three decisions the key mirrors.
- **The sequence's name.** `State.gen` (`cuda_state.zig:410,458`), a count each state takes when made.

## Design choices, the alternatives, and why

### What becomes a key, what is set on a node, what is a device value already

Read from the base tree, every host value a one-stream window's launches take:

| value | where the eager window reads it | in the graph |
|---|---|---|
| rows R | grids and row counts everywhere | key (`Key.rows`) |
| KDA parity `st.cur[li]` | picks `recAt(cur)` / `recAt(1 - cur)` as the chain's state in and out (base `cuda_forward.zig:239-251`) | key (`Key.parity`), as production keys `(rows, parity)` (`P:graphs.py:56-59`) |
| the sequence's buffers | `st.rec`, `st.proj`, `st.save_*`, `st.conv`, `st.caches[di]`, `st.pos_dev` (base `cuda_state.zig:449-453`) | key (`Key.gen`) |
| index ring base `st.base` | `c.ik`, `c.ig` = ring - base rows (base `cuda_state.zig:542-547`), read by `indexUpdate` | key (`Key.base`); a rebase is rare (ring of 4,096 rows) |
| dense chunks `nch` | `min(chunksFor(pos + R), b.nch)` (base `cuda_forward.zig:409`): the chunk kernel's grid z, the merge's count | key (`Key.nch`, 0 when the dense half does not run) |
| dense or sparse halves | `host_pos < dense_limit`, `sparseRows` (base `cuda_dsa_block.zig:103-105,144,153`); `qi` in `prepare` | implied by `nch` and `Key.sparse` |
| pool bucket `np_max` | `poolBucket(host_pos, R, pk_rows - 2)`: scores and select args, `wideSelect`, the index kernels' choice (base `cuda_sparse.zig:84,108,127`) | key (`Key.np`); it doubles, so a key lasts a doubling |
| score blocks `nb` | `cdiv(scoreColumns(host_pos, R, np_max), 64)`: the scores launch's argument and grid y (base `cuda_sparse.zig:103-110`) | **set on the node** before a replay whose blocks moved |
| position, lengths, KV page tables | `st.pos_dev` (i32 on the device, set by `setPos`), `c.pt` tables | device values already |
| ids | `copy_source.enqueue` into `b.ids` | staged before each replay (`stage`), as eager |

Positions are device values in every kernel that reads them (`latentWrite`, `indexUpdate`, the attention chunks, the
token assembly), so a graph replayed at a later position reads the new one. The engine-wide buffers (`e.bd`, the
weights, the L2 table, the drafter's `taps_step`) are fixed for the engine's life; the cache's fingerprint is the
window buffers' address and whether the KV pages are attached (`cuda_vgraph.zig:142-145`), so the one late change of
placement (slot 0's caches re-placed at the pool's attach, base `cuda_pages.zig:125`) drops every graph.

### Score blocks: set on the node, not a key and not a device value

`nb` moves every 256 positions ((pos + rows) / 4 crosses a multiple of 64). In the key, a long context's windows
would need a new graph for every (rows, parity) pair every 256 positions: about 92 rounds at 2.79 tokens a round
(derived), against one capture per pair, where a capture costs the host the window's launches again plus
instantiation and upload (estimate 15 to 30 ms, unmeasured), 10 to 16 pairs a span. That is about as much as the 1 to
3 ms a round the graph saves (estimate), so a key on `nb` would leave the owner's long-context windows no faster. A
device-side `nb` needs the scores kernels to read their block count from memory and stop early, which is a kernel
change and a different launch from the eager one (the brief's bar is the same launches with the same arguments).
Instead each graph keeps its template and its score nodes, found after the capture by kernel and by argument 3, the
layer's pooled keys (`scoreNodes`, `cuda_vgraph.zig:315-335`; argument 3 is `pk` in both scorers, pinned by a host
test). When the blocks moved, `launch` (`:290-302`) builds every layer's scores launch with the code the eager window
runs (`dsa_block.scoreLaunch`) and sets it with `cuGraphExecKernelNodeSetParams`; a launch already in flight keeps
its old parameters (the driver applies them to later launches).

### One graph for the whole window, not per-layer segments

Every host value is either a key or one patchable node, so nothing forces a break inside the window. Segments around
the 11 selections would mean 12 graph launches and 11 eager islands a window and, at the graph boundaries, the same
NCCL lateness the graph is meant to remove (`round-structure.md` 3.3: 2.6 ms a round of gather time above p10).
Production replays one graph a window too (`P:verify.py:325-365`).

### Exact row counts, both parities

Our grids take the exact row count (no padded rows in this engine; padding would change the launches), so a key
names its rows exactly, 1 to 32 (`window_rows`); production keys exact rows too (1..8 and 1..32,
`P:graphs.py:44-83`, `P:verify.py:176-208`). The KDA parity stays a key rather than a device table: a table needs
the chain kernels to read state pointers from memory (production carries parity in its segment table,
`P:verify.py:267-271`), which is a kernel change. Two parities double the keys: at one stream about 32 graphs
(8 row counts, 2 parities, the bench's 1 or 2 chunk counts), under the cap of 64.

### The sequence by `State.gen`, not by address

Hits do not vote (`graph_cache.zig:184-189`), so every rank must make the same hit or miss or the miss's vote has no
partner and the ranks hang. A key on the state's arena address would hit on one rank whose allocator reused an
address and miss on another whose did not. `gen` counts the states a process made (`cuda_state.zig:372-373,458`);
ranks make and free states at the same steps (bind, release, the pool's attach, the router warm-up on every rank),
so a sequence's key means the same sequence on every rank, and a freed sequence's graphs are never hit again and age
out by the cache's LRU.

### Lockstep, failure, the first window, eager reasons

- `graph_cache` votes on each miss, room first, then the capture (`graph_cache.zig:190-229`); the vote is
  `cuda_ranks.gather` of one u32 a rank on the engine's NCCL communicator, outside any capture
  (`cuda_vgraph.zig:155-163`), as DeepSeek V4.1's `Agreement` does over its collective
  (`deepseek_v41/graphs.zig:163-202`). A capture that fails on any rank turns graphs off on every rank, logged by
  `graph_cache`, and the window runs eagerly.
- At the first verify window every rank votes once on the reasons that hold for all its windows (`open`,
  `:184-209`): `TF_GLM_PROF` (`e.profs`: its events are read on the host between sections), `--vision` (the splice
  reads image rows by host position), `TF_GLM_KV_HOST` (host-chosen slots), a RoCE wire (`group.fast` at two ranks or
  `group.multi` under `TF_GLM_ROCE_MULTI`: their proxy and wire were not read for capture safety here),
  `TF_GLM_KDA_DUMP` (a synchronize and a read), and DSA layers with different dense limits. Any of them on any rank
  keeps every rank eager; each reason is logged once (`tell`, `:227-233`).
- A key runs eagerly its first time (`step`, `:111-121`), so every kernel and NCCL connection it uses is loaded
  before a capture records it (production's `capture` makes one eager run for the same reason, `P:graphs.py:12-30`).
- The body has no host side effects in decode (the KDA layers commit at `commit`, not in `mixer`, base
  `cuda_forward.zig:253`), so a capture that records it and a launch that runs it equal one eager window.
- The L2 prefetch's fork and join are inside the window: the side stream joins the capture at its first `fork` and
  `whole` joins it back before `compute` returns (base `cuda_forward.zig:412,428,441`; `cuda_l2pf.zig:215-239`).

### Memory and the boot pool

Nothing is made at boot: `e.vgraph` is null until the first verify window opens it (`cuda_vgraph.zig:126`). Each
rank's room is read after `Engine.init` returns (base `cuda_native.zig:340`, `finishRank`) and rank 0 sizes the pool
from the smallest, so the pool line at boot is the same with the switch on or off (by construction; not read from a
boot log). Graph memory then comes from what the native memory plan leaves outside the pool (the reserve, base
`native/cuda_memory.zig:122-156`): a capture needs MemAvailable to keep 4 GiB past 64 MiB for it (`Room`, `:75-83`),
DeepSeek V4.1's default rule (`deepseek_v41/graphs.zig:97-134`); below it the cache sheds its oldest quarter and the
window runs eagerly, and room again lifts the cap. At most 64 graphs a rank. Each capture's measured cost is logged
(`graph cache glm verify windows: captured, N held: MemAvailable a -> b GiB`). The 4 GiB floor is checked against the
serve, by reading: the engine has no run-time memory guard (its only MemAvailable reads are the boot plan and the tp
fate watcher's MEM report, base `fabric/tp/fate.zig:31`); 4 GiB is the engine's own least unified-memory reserve
(base `native/cuda_memory.zig:141-149`: the default reserve is max(4 GiB, a tenth of the pool)); and this repo's
serve keeps 12.5, 14.5, 13.0 and 6.5 GiB out of the pool at 1, 2, 4 and 6-8 streams (`scripts/serve.sh:16,34`), so
graphs have at most 8.5, 10.5, 9.0 and 2.5 GiB above the floor (derived: the reserve less 4 GiB, before what the
engine takes after the room is read) before the cache sheds and runs eagerly. Production's watchdogs belong to
production and are stopped in a bench window
(`AGENTS.md:64-66`).

### Shared windows stay eager

A shared window's KDA chains and attention take each segment's state pointers and row offset on the host
(`cuda_shared.zig:52-86`), so a key by total rows alone would bake the first combination's states into the graph. A
key holding the whole segment list (each stream's gen, rows, parity, base, chunks, bucket) is exact, but at two
streams or more the row split changes nearly every round, so such keys seldom recur. Production's batched graphs are
keyed by total rows because its kernels read the segments from a device table (`P:verify.py:267-295`); here that
means new kernel signatures. Not done in this patch; shared windows, prompt chunks, the MTP head, the drafter, the
draw and the commit run as before.

## The knob off: the same launches

With the switch off `cuda_vgraph.run` returns false before anything else (`:125`) and `Engine.verify` calls
`f.run`, which is `stage` then `compute`: the old `run`'s statements in their order. The selection's scores launch
is built by `scoreLaunch` from the expressions it used inline (the same kernel, configuration and arguments; the
index kernel's by `scoresLaunch`) and launched at the same point between the same profiler spans. `State.gen` is a
host counter. The GPU receipt for this claim is the knob-off digests against `glm53-zig:rs1`'s.

## Mutants

Each mutant changes one decision in a copy of the gated tree, anchor matched once, and runs `test-cuda-host`
(`work/vgraph/mut.py`; output in `PROOF.md`).

| mutant | what it breaks | result |
|---|---|---|
| `key-drops-ring-base` | `shapeOf` keys every ring base alike | KILLED by "rows, KDA parity, the sequence and its ring base each name a graph" |
| `node-by-kernel-alone` | `scoreNodes` takes the first score node of a kernel, ignoring its pooled keys | KILLED by "score nodes are found by kernel and pooled keys in any order" |
| `capture-at-first-sight` | `step` captures a key the first time it comes | KILLED by "a key runs eagerly its first time, is captured its second" |
| `score-args-swapped` | the plain scorer's pool count and block count swap places (knob-off path) | KILLED by "the score blocks a replay sets are the eager launch's" |
| skip setting the score nodes in `Graphs.launch` | a replay keeps the blocks of its capture | not runnable without a GPU; the GPU check fails it on its patched count of 0 |

## What the main session runs

1. **Image.** The build's input is made: `work/vgraph/vg1-src.tar` (`srctar.sh`: `git archive` of tree `a7f220ed`,
   174,520,320 bytes, 11,314 files, the tree's count; sha256
   `0cef4eefa31bdcb79d676630931121ba5a1b4336aba64554241206e09d372f46`, so `build-image.sh` labels the image
   `glm53-zig.src-sha256=0cef4eefa31bdcb7`). Copy it to spark1 and `bash ~/work/glm53-zig/build-image.sh vg1
   <dir>/vg1-src.tar` (`scripts/build-image.sh`), then `docker save glm53-zig:vg1 | ssh spark2 docker load` and
   likewise spark3. The build compiles the CUDA units and `tf-cuda-test`, which nothing local compiles for sm_121.
2. **Knob off against rs1** (the same path): `bash bench-arm.sh glm53-zig:vg1 vg1-off` with the env of the rs1
   cell it is compared with (the pad cell: `XENV="-e TF_GLM_KDA_PAD=1"`); every reply digest equal to rs1's at
   every level.
3. **The GPU check**, before relying on the knob: on each of spark1-3 in the vg1 image, every rank with
   `TF_GLM_OVN_VERIFY_GRAPH=1` and the serve's NCCL settings:
   `tf-cuda-test glm-vgraph-check <ckpt> <rank> 3 <idfile on a path all three see>` (rank 0 writes the NCCL id
   there). PASS needs byte-equal logits, tokens and states over 2 x 64 windows and nonzero captured, replayed and
   patched counts; each follower prints its own counts.
4. **Knob on**: `XENV="-e TF_GLM_KDA_PAD=1 -e TF_GLM_OVN_VERIFY_GRAPH=1" bash bench-arm.sh glm53-zig:vg1 vg1-on`
   at 1, 2, 4, 6 and 8 streams, digests equal to vg1-off's; `scripts/abba.sh` for any level that reads low; the
   engine's round counter (ms a round) beside tok/s; rank 0's log lines `glm verify graphs:` and `graph cache glm
   verify windows:` (captured, replayed, patched, eager, MemAvailable per capture).
5. **turns** (`scripts/turns.py`, the 11k chat: every window past the dense limit, so the patched score nodes) on
   vg1 with the knob off and on: first-token times as before, decode tok/s and digests equal.
6. Then `scripts/nsys-rank0.sh` at one stream on rank 0 and rank 1, knob on: graph launches a round, main-stream idle,
   NCCL time, against the pad stack's profile (`round-structure.md` section 4).

## Measured by the runs above, and decided here

- **Gain.** 1 to 3 ms a round at one stream (`round-structure.md` 5.2, estimate): the main stream's 1.7 ms of idle a
  round and the gathers' 2.6 ms a round above their p10 time, much of it waiting for a later rank; the host is already
  ahead of the GPU, so the launch time itself is not the prize. Step 4's round counter measures it.
- **NCCL inside a GLM graph.** NCCL captures collectives into graphs and mixes them with eager ones on one
  communicator; the followers' step broadcasts and the draw's gathers stay eager. Step 3 is the first run of it at
  TP=3 and fails on any byte difference.
- **Capture cost** (estimate 15 to 30 ms a key) is paid once per key per sequence and logged per capture. At one
  stream the bench's slot 0 keeps its state across requests (`freeSlot` takes the lowest free slot,
  `cuda_lanes.zig:153-162`; slot 0 is never freed, base `cuda_engine.zig:299-305`), so a cell's later requests
  replay. Slots 1 and up are freed when their stream ends unless the KV pages are on, so a stream that decodes alone
  at two streams and more pays its keys again; step 4's captured count against its round count at P2 measures what
  that costs, and no change is made for it before that number exists.
- **Every rank alike, decided.** A rank without the switch never opens the graphs and the others' first vote waits for
  it. The switch is not added to the ranks' settings fingerprint (`cuda_ranks.zig:202-234`, which no OVN knob is in)
  because that would change the boot handshake's bytes with the knob off; the bench and serve path cannot split it,
  since `zig-tp3.sh` hands one `XENV` to every rank's `serve.sh` (`scripts/zig-tp3.sh:19-27`).
- **The 4 GiB floor, decided.** It equals the engine's least unified-memory reserve and leaves the serve's reserves
  room (Memory, above); what a graph really costs is logged per capture.
