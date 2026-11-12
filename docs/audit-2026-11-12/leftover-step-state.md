Audit complete. Full report follows.

---

# Group A-step-state - fork changes our port lacks

Instrument rerun per file against `work/parity/tree` (pin `9c9bf542`, fork `fork-ssh/ovn-up` 595e28743, base `9b2991d122c7`). Every claim below comes from a file I opened this session; fork facts are cited at `fork-ssh/ovn-up:<path>:<line>`, ours at `work/parity/tree/<path>:<line>`.

## 1. DEFECT-CANDIDATES, most severe first

### D1 - `chunkEnd` does not realign to the chunk grid, so paired prompt steps stop entirely after any off-grid resume or mark. DEFAULT PATH.

- ours: `zig/src/families/glm/cuda_engine.zig:36` `var end = @min(len, start + prompt_rows);` (test 43-48)
- fork: `cuda_engine.zig:37` `var end = @min(len, (start / prompt_rows + 1) * prompt_rows);`, commit `cfa2cd93c` 2026-10-29 *"a prompt chunk ends on the chunk grid, so chunks after an unaligned start pair again"*
- patches: introduced by **0007** (`chunkEnd` is 0007's own function) and made load-bearing by **0042** (`ringsAgree` gained `start % pool + ra + rb <= ring`). It is the same pair as the worked example, one step further on.

What goes wrong. `prompt_pair` is on by default: `zig/src/families/glm/cuda_ranks.zig:21` `pair: bool = true, // TF_GLM_PROMPT_PAIR`. The leader takes a wide step only when `a_end == start + engine.prompt_rows` (`cuda_follow.zig:246`). With the fork's realigning `chunkEnd` that identity can hold **only at a multiple of 2,048**, so every paired step starts pool-aligned and 0042's new pool term is always satisfied. With our non-realigning form `a_end == start + 2048` holds at *any* start, so after an off-grid resume the pair is offered at off-pool starts and 0042 refuses it, for the whole rest of the prompt.

Walk, resume at row 9 (the chat template's kept state, which the fork says sits in front of almost every prompt), `ring_rows = 4096`, `pool = 4`:

| start | `ringsAgree` first term `start+2048+rb <= base+ring` | second term `start+2048 > base+ring and start%4+4096 <= 4096` | pairs |
|---|---|---|---|
| 9 (base 0) | 4105 <= 4096 no | 2057 > 4096 no | no |
| 2057 (base 0) | 6153 <= 4096 no | 4105 > 4096 yes, but 1+4096 = 4097 > 4096 | no |
| 4105 (base 2056) | 8201 <= 6152 no | 6153 > 6152 yes, but 1+4096 > 4096 | no |

Every later chunk keeps `start % 4 == 1`, so **no step in the prompt ever pairs**. The fork measured exactly this before the fix: *"no step paired again (measured: 'paired steps: 0' on 32,827 / 133,616 / 8,274-token prompts)"*. The cost is the whole of pairing (each chunk's exchanges hidden under the other chunk's sites) on every resumed prompt, which is the warm-turn agent case.

Second consequence, knob-gated. With `TF_GLM_CHUNK_SOLO=4096` (`cuda_ranks.zig:20`, default false) `e.pair` is always null (`prompt_pair.wanted(on, solo, world)` = `on and !solo and world > 1`, called at `cuda_engine.zig:170`), so a wide step goes to `prompt_solo.allowed` (`cuda_engine.zig:387`). `cuda_prompt_solo.ringsAgree` has no pool term and returns true at an off-pool start once the first term fires; `State.ready` then rebases to `pos/4*4` and 0042's new line returns **`error.PastRing`** (`cuda_state.zig:516`), failing the request. In the fork this cannot happen because a wide step is only ever offered at a grid multiple. Our own constant admits as much: `cuda_state.zig:28` *"A solo prompt pass's rows (TF_GLM_CHUNK_SOLO): a whole ring, which a rebase **at a grid point** leaves it."*

Third corroboration that the realign belongs with 0007/0011: our ported `cuda_one_chunk.cut` already assumes it, `cuda_one_chunk.zig:43` `const whole = if (len - start <= C) len else (start / C + 1) * C;`.

Confidence **high**: the fork commit names the same mechanism, the arithmetic above is from our own `ringsAgree` and `State.rebase`, and `pair = true` is our default.

Minimal port (`cuda_engine.zig:34-48`, exactly `cfa2cd93c`):

```zig
/// Where a prompt chunk from `start` ends: the next multiple of `prompt_rows`, the prompt's end, or the first mark past
/// `start`. A start off that grid (a resume or a mark) ends on it, so the chunks after it start aligned and can pair.
pub fn chunkEnd(start: usize, len: usize, marks: []const u32) usize {
    var end = @min(len, (start / prompt_rows + 1) * prompt_rows);
    for (marks) |m| {
        if (m > start and m < end) end = m;
    }
    return end;
}

test "a prompt chunk ends on the chunk grid, at the prompt's end or at the first mark past its start" {
    const C = prompt_rows;
    try std.testing.expectEqual(C, chunkEnd(0, 9 * C, &.{}));
    try std.testing.expectEqual(2 * C + 100, chunkEnd(2 * C, 2 * C + 100, &.{}));
    try std.testing.expectEqual(2 * C, chunkEnd(C + 9, 9 * C, &.{})); // a resume at C + 9 realigns at 2C
    try std.testing.expectEqual(C, chunkEnd(9, 9 * C, &.{})); // the template's row 9: the rest of the first chunk
    try std.testing.expectEqual(C + 903, chunkEnd(C, 9 * C, &.{ 9, C + 905, C + 903, C }));
    try std.testing.expectEqual(C + 900, chunkEnd(C + 3, 9 * C, &.{ C + 3, C + 900 })); // its own start does not cut
}
```

### D2 - `canBatch` admits a prompt with a cache mark strictly inside it; the batched pass fires no mark, so that kept state is silently lost. DEFAULT PATH.

- ours: `cuda_lanes.zig:584-586`, `return s.prompt_logprobs == null and s.images.len == 0 and s.reuse.saved == null and s.prompt_len <= engine.prompt_rows;`
- fork: `cuda_lanes.zig:632-635`, same body rewritten to early-returns plus `for (s.reuse.marks) |m| if (m > 0 and m < s.prompt_len) return false; // a kept state the batch would skip`, commit `03138041e` 2026-10-29
- patch: the batched pass itself is pin code, but its safety precondition was GLM's `snap_grid`, which **0007** deleted (`cuda_native.zig:27-28`, *"No snap_grid: states keep and resume at any row"*).

Why the pin was safe and we are not. `cuda_snaps.cacheRules` only sets `rules.planned`/`rules.grid` when the family declares `snap_grid` (`zig/src/native/cuda_snaps.zig:12-16`). With the pin's `snap_grid = 2048` the mark planner snapped every candidate to the grid (`prompt_cache.zig:438` `const at = if (s.rules.planned) s.startAt(starts, w) else w;`) and then dropped it (`:439` `at <= from or at >= prompt.len`), so no mark could sit inside a prompt of at most 2,048 tokens. With 0007 `planned = false`, so `at = w` unsnapped; `min_prompt` is 0 for CUDA families (`cuda_snaps.zig:7`), `usable(at, starts)` is just `at > 0` (`prompt_cache.zig:~560`), and the history mark is explicitly exempt from `min_gap` when `from == 0` (`prompt_cache.zig:441`, the `(k > 0 or (from > 0 and ...))` tail). So a fresh second-turn prompt of, say, 800 tokens with a 300-token history gets a mark at 300, `canBatch` admits it, `prefillMany` runs it in one pass and calls no `m.call`, and the state is never kept.

`together` is on by default (`cuda_lanes.zig:44` `together: bool = true`, set from `TF_GLM_PROMPT_MANY` at `cuda_native.zig:365`), and `prefillManyFn` is reached whenever two or more streams queue at once (`zig/src/core/lanes/open.zig:47-48`).

Effect: a lost cache state, so the next turn re-prefills from scratch. No wrong replies. The fork additionally hit `ProbeUnmarked` on the NVMe tier's 2,088-token boot probe, which cannot reach us at `prompt_rows = 2048` because `canBatch` already refuses prompts over 2,048.

Confidence **high** that the guard is absent and the pin's protection is gone (both quoted above); **medium** on how often production traffic puts a mark inside a sub-2,048-token prompt.

Minimal port (`cuda_lanes.zig:584-586`):

```zig
pub fn canBatch(s: anytype) bool {
    if (s.prompt_logprobs != null or s.images.len != 0 or s.reuse.saved != null or s.prompt_len > engine.prompt_rows) return false;
    for (s.reuse.marks) |m| if (m > 0 and m < s.prompt_len) return false; // a kept state the batch would skip
    return true;
}
```

### D3 - the logit gather posts one NCCL broadcast per row per rank, and a TP=3 prompt-logprobs pass past about 100 rows never leaves `ncclGroupEnd`. DEFAULT PATH, and a hang.

- ours: `cuda_sampler.zig:96-112` (`gather`) and `cuda_sampler.zig:151-166` (`Spread.post`, `for (0..t.rows) |row| for (t.spans, 0..) |span, q| ... ncclBroadcast(...)`)
- fork: `cuda_sampler.zig:100-120` plus `place` at `:111`, `Spread` carrying `stage`/`mine` at `:160-175`; commit `0a77dcd7d` 2026-10-28, *"Spread.post queued one ncclBroadcast per row per rank in one NCCL group; at TP=3 a 128-row prompt-logprob pass (381 broadcasts) never left ncclGroupEnd ... Fixes #1559"*
- not caused by our port: `work/pin/tree/zig/src/families/glm/cuda_sampler.zig` has the identical row-by-row `Spread.post`. This is a fork fix we never took.
- reached by any request asking for prompt logprobs at TP>1 (`cuda_prompt_logprobs.zig:86` calls `e.smp.gather(...)` with `n` up to `batch_rows`). Our serve is TP=3. The decode draw is unaffected (at most 8 rows).

Confidence **high** on the code shape, **high** on the diagnosis because the fork reproduced and numbered it (381 broadcasts at 128 rows, TP=3).

Minimal port: take `0a77dcd7d` whole. It is `cuda_sampler.zig` (a `stage: cuda.DeviceBuffer` of `rows * vocab * 2`, `gather` gaining a `stage` argument, `place` doing one `cuMemcpy2DAsync` a span, `Spread` broadcasting `t.rows * span.len()` once a rank), `cuda_prompt_logprobs.zig` (its own `stage` buffer, passed through at `:76`/`:86`), and `cuda_structured.zig` (one call site, outside this group).

### D4 - the follower binds `h.slot` on a `.disk` step. Latent only because our disk tier is unreachable.

- ours: `cuda_follow.zig:391`, the exclusion list ends `... and kind != .pool) try e.bind(h.slot);`
- fork: `cuda_follow.zig:441`, same line with `and kind != .disk`
- patch: **0023** (it added `Kind.disk` at our `cuda_follow.zig:17`, the handler at `:485`, and `cuda_disk_ranks.zig`).

Every disk header is built without `.slot` (`cuda_disk_ranks.zig:60, 74, 87, 99, 111`), so followers would `bind(0)`, which creates sequence 0 if absent and switches `e.cur`/`e.slot` and the vision slot (`cuda_engine.zig:bind`, `if (e.images) |v| try v.activate(slot)`).

Unreachable today: nothing in our tree ever assigns `Engine.link` (grep over `zig/src/families/glm/*.zig` finds only the read at `cuda_disk_ranks.zig:41`), the fork sets it at `cuda_native.zig:348` `if (p.rank == 0 and p.world > 1) own.e.link = &own.link;`, and no code calls `cuda_disk_ranks.blank/put/take/seal/prefixes`. So rank 0 never sends a disk step. Note the same gap means 0023's multi-rank disk tier cannot work at all here: `leader(e)` is always null, so `prefixes` returns `error.NoRank` for `out.len != 1` and `put`/`take` to a rank other than 0 return `error.NoRank`.

Confidence **high** on the missing guard, **high** that it is inert now.

Minimal port: add `and kind != .disk` to `cuda_follow.zig:391`. Porting the tier itself additionally needs `own.e.link = &own.link` in `cuda_native.zig` and whatever drives it.

### D5 - the whole-prompt `Engine.prefill` steps in fixed 2,048-row chunks, so it fires only the marks that happen to fall on a multiple of 2,048 from the resume point.

- ours: `cuda_engine.zig:360-367` (`const rows = @min(ids.len - start, fw.prefill_rows);`, `marks` forwarded) and the caller `cuda_lanes.zig:235`
- fork: `cuda_engine.zig:432-439` loops the same way but takes **no** `marks` at all, and `prefillFn` was rewritten to loop `Leader.chunk`; commit `1b4bd2975` *"prefillFn called Engine.prefill, which steps in fixed 4,096-row chunks and fires a mark only at a step start ... prefillFn now steps through Leader.chunk, each step ending at Engine.chunkEnd, so every mark is a step start; the marks parameter is gone"*
- patch: **0007** (marks are its feature).

Reachability: the stepped vtable is the default (`cuda_lanes.zig:81`, `whole = off("TF_GLM_PROMPT_STEPS")` at `cuda_native.zig:365`), so the normal path is `prefillStep` -> `chunkOf` and is fine. The whole-pass path runs with `TF_GLM_PROMPT_STEPS=0`, and through core callers of `backend.prefill`: `zig/src/core/lanes/open.zig:29` (`add`) and `zig/src/core/lane_host_warm.zig:11` (the background pass, which in our tree only exists with `TF_GLM_OVN_REPLY_PREFILL`, and that branch already loops `chunkOf` at `cuda_lanes.zig:225`).

Confidence **medium**: the code difference is certain, the frequency of the non-stepped path in our deployment is not.

Minimal port: make `prefillFn`'s non-reply branch loop `chunkOf(..., false, ..., 0)` to completion the way the REPLY_PREFILL branch at `cuda_lanes.zig:220-233` already does, and drop `marks` from `Engine.prefill`/`Leader.prefill`.

### D6 - patch 0011's `TF_GLM_OVN_ONE_CHUNK` is inert, and would not compile if it were wired.

- ours: `cuda_engine_ovn.zig:7-16` opens `SHARED_PROF`, `DRAW1`, `SEG_KDA`, `SEG_COMMIT` and nothing else, so `cuda_one_chunk.on` is never set true and `Engine.one` (`cuda_engine.zig:123`) is never allocated. `enter`/`leave`/`taking` therefore return immediately, and `cuda_follow.chunkOf` (`:241-253`) never calls `one_chunk.plan`/`put`/`arm`, nor does the follower call `one_chunk.read`.
- fork: `cuda_engine_ovn.zig:16-19` creates the capture and sets `on`; `cuda_follow.zig:270-281` plans, puts and arms it; `cuda_follow.zig:467` reads it on the follower.
- the compile trap: `cuda_one_chunk.zig:82` `if (e.head) return false;` inside `keepsInside`, called from `plan` at `:77`. Our `Engine` has no `head` field (`cuda_engine.zig:104` is the last `mtp: bool`, and grep finds no `head` member). Zig never analyses `plan`, because nothing calls it and `one_chunk` is absent from `cuda.zig`'s `test` block, which is why the tree builds. Wiring the knob breaks the build until `head` lands (see S2) or the line becomes `if (e.mtp)`. Note `cuda_prompt_pieces.zig:117` carries the opposite adaptation with a comment: *"the pin signals the head pass by its MTP head, not an e.head flag"*.
- Also missing: `cuda_one_chunk.zig` lacks the fork's `defer cap.marks = 0; // after the keeps: keepAt refuses a mark past it`, and `cuda_one_chunk_keep.zig` keeps the pin's `Plan.init`/`putAssumeCapacityNoClobber` shapes rather than the fork's `heldPages`-aware ones.

Confidence **high** (all three facts read directly). Severity low at runtime, high as a port-integrity finding: a patch in the stack claims a feature that cannot be switched on.

### D7 - `TF_GLM_OVN_REPLY_PREFILL`'s background pass can evict another conversation's latest kept state.

- fork: `cuda_native.zig:40` `pub const warm_spares = true;`, commit `c9468e336` *"while a background reply pass looks up or keeps, victimBut has no oldest fallback (Store.spares_only), so the pass never evicts another conversation's latest state; such a keep keeps nothing."*
- ours: no `warm_spares` decl, and our core has no `spares_only` hook at all (grep over `zig/src/core`, `zig/src/native` finds only `victimBut` and `keep_others`).
- patch: **0008** (REPLY_PREFILL), knob default off.

Confidence **high** that the guard is absent, **medium** on impact because it needs the knob on. The same commit removed `warm_alone` in favour of a core rule; our 0025 wired `warm_alone` through instead, which is an equivalent older shape and not a defect.

## 2. SPEED-LEADS, largest claimed gain first

### S1 - skip the MTP head's prompt absorb when DFlash2 is loaded. `a8ccc5c81`, 2026-10-28.

Measured in the commit: *"61-86 ms of each 1.5-1.8 s 2,048-row chunk, 4.0-4.7% of a cold prefill, plus the head's rows in every kept state"*. Default-on, no knob: `head = o.mtp and !o.drafter`. Our production serve runs `--drafts` with `--drafter`, so `e.mtp` is true (`cuda_native.zig:272` passes `.mtp = o.drafts`) and every prompt row is absorbed into caches nothing reads. Replies cannot move, because with a drafter loaded the head never drafts and its output is never read.

Our sites, all four of which must change together or kept states will disagree about `mtp_len` across paths and fail `restore` with `error.SnapshotSize`:

```
cuda_engine.zig:104      mtp: bool,
   + head: bool, // the MTP head's own passes run: drafting without DFlash2, which reads only the head's .draft weights
cuda_engine.zig:197      ... .mtp = o.mtp };            ->  ... .mtp = o.mtp, .head = o.mtp and !o.drafter };
cuda_engine.zig:433      if (e.mtp) try prompt_solo.mtpRows(e, &f, as_i32);   ->  if (e.head) ...
cuda_prompts.zig:56      if (e.mtp and g.rows > 1) {    ->  if (e.head and g.rows > 1) {
cuda_prompt_pair.zig:144 if (!e.mtp or nxt.len == 0) return;  ->  if (!e.head or nxt.len == 0) return;
```

and, optional but in the fork (`cuda_snapshots.zig:40`), the admission estimate:

```
cuda_snapshots.zig:34  const head: ?usize = if (!e.mtp) null else if (!e.head) 0 else @min(e.capacity, std.math.add(usize, at, window_rows) catch return std.math.maxInt(u64));
```

`Options.drafter` already exists (`cuda_engine_types.zig:47`), so the port needs no new plumbing. It also unblocks D6's compile trap. Note `cuda_prompt_pieces.zig:117` is a fifth site the fork gates (`cuda_prompt_pieces.zig:120`).

### S2 - restore pairing on resumed prompts. `cfa2cd93c`. Same change as D1.

Stated as a speed lead because that is what it buys: pairing goes from 0 paired steps to every aligned chunk pairing on 32,827 / 133,616 / 8,274-token prompts. The commit gives the paired-step counts, not a tok/s figure; the pairing feature itself is upstream's (the pin ships `cuda_prompt_pair.zig`), so the gain is "whatever pairing is worth on this box", recoverable in one A/B against `TF_GLM_PROMPT_PAIR=0` once the two lines land.

### S3 - one broadcast a rank in the logit gather. `0a77dcd7d`. Same change as D3.

*"Same bytes, world broadcasts whatever the rows"*, against `rows * world` today. At TP=3 and 128 rows that is 3 against 381 collectives. Default-on for any prompt-logprobs request.

### S4 - prompt chunks of 4,096 rows. `85df341ed`, 2026-10-29. Default-on.

`cuda_state.prefill_rows` 2048 -> 4096 (ours `cuda_state.zig:19`). No tok/s figure in the message; it is the one chunk constant and everything chunk-shaped follows it (prompt buffers, EXL3 routed-experts call, the index rings `2 * prefill_rows`, the pair's twin and `min_rows`, the follower's whole-pass steps, the batched pass, the image map, `dflash.TAP_ROWS`, the profiling label). The commit names what must **not** follow: `snap_min_rows` stays 2,048 (ours is `prompt_rows` at `cuda_native.zig:28`, so it would need pinning to the literal), the disk probe stays 2,088, DFlash2 keeps `MAX_CTX` 2,048 pieces, `TF_GLM_INDEX_SPLIT` keeps default 2,048, the dense limit 2,051 and `dflash.WIN` are not chunks. Our 0042 is literally the pair of ring fixes this commit made on the way, so the rest of it is the natural follow-up; D1 is a prerequisite (the same commit's own test set includes the off-pool `ringsAgree` cases).

### S5 - complete DFlash2 prompt taps at TP>1. `57c9f1367` then `f7b884fbd`, 2026-10-29. Default-on.

Cross-group pointer: the edits land in `cuda_forward*.zig`/`cuda_taps.zig`/`dflash*.zig`, not mine, but the defect it fixes is visible from my group's `cuda_engine.zig:392`. With `TF_GLM_PREFILL_REDUCE=split` (the default) each rank glues only its own rows, so *"on each rank the drafter ingested a stale residual for the other ranks' rows: two thirds of its prompt context at TP=3"*. The first fix cost *"cold TTFT +8.5% at 7.9k tokens (4.97 -> 5.39 s)"*; `f7b884fbd` gets the same correctness by sharing each rank's own tap rows, so it is the one to port. Worth checking with the group that owns `cuda_forward.zig`.

### S6 - shared windows made after the page pool. `d1661d165` + `d77dc922e`, with `cuda_engine_shared.ensure`/`laterBytes`. Default-on restructuring.

Ours still allocates `e.bs` during `Engine.init` (`cuda_engine.zig:244`, flagged `kept` by the instrument) and sizes the page pool with that memory already gone (`cuda_native.zig:355` `const mine: u64 = if (o.room) |r| r.read(r.ctx) orelse 0 else maxInt(u64);` against the fork's `... -| later`). The fork defers the shared buffers to the first verify and sets aside only `laterBytes`, which leaves the KV page pool larger. No measured figure in the commits; the win is more KV pages, so fewer cold prefills. Lower priority than S1-S4 and entangled with the unported `TF_GLM_OVN_SHARED_ROWS`.

### S7 - `.first_tree = false` for the GLM Metal backend. `backend.zig:71` in the fork.

Default-on, but it is `zig/src/families/glm/backend.zig`, the non-CUDA backend. Irrelevant to the Spark serve; listed for completeness.

## 3. Per-file table (all 32 files)

Counts are the instrument's for our tree. "R&L" is rewritten-and-left hunks.

| # | file | hunks | R&L | DEFECT | SPEED | SUPERSEDED | UNPORTED | COSMETIC | note |
|---|---|---|---|---|---|---|---|---|---|
| 1 | cuda_state.zig | 25 | 18 | 0 | 1 | 1 | 21 | 2 | Almost all kv8-on-pages, `DROP_MTP`, `LINEAGE`, `SEG_KDA`, exl3 `Ovn`/`heldScratch`, `Share.widest` (`EXPERT_ROTATE`); `prefill_rows` 2048 vs 4096 is S4; `glueAlt` differs only in local names (`S * D * 2` vs `hc * hidden * 2`, ours line 345); `Arena` moved to `cuda_arena.zig` in the fork is cosmetic. |
| 2 | cuda_follow.zig | 31 | 16 | 2 | 0 | 0 | 26 | 3 | D4 (`.disk` bind, ours :391) and D6's leader plumbing (`one_chunk.plan/put/arm/read`); the rest is `LINK1`/`LINK_ROCE`, `FILL_SLICE_MS` (`chunk_part`, `slicePart`, `sliceEnd`), `SHARED_ROWS` (`max_shared_rows`), `DISK_LOCAL`. `chunkRows`/`indexSplit` match; the big test block is a port-time test swap. |
| 3 | cuda_lanes.zig | 25 | 10 | 1 | 0 | 2 | 20 | 2 | D2 (`canBatch`, ours :584). `facts()` matches the fork except `DRAFT_FIXED`, `DEPTH_FULL`, `SHARED_COPY` and the `SHARED_ROWS`-sized cost slices; cost tables are numerically identical to `cuda_copy_policy`'s (52.0/6.8, 76.0/4.1), only duplicated. `FILL_SLICE_MS` (`slicing`/`settled`/`settle`/`onward`) and `LINEAGE` (`keptId`) unported. |
| 4 | cuda_engine.zig | 32 | 9 | 2 | 2 | 0 | 24 | 4 | D1 (`chunkEnd`, :36) and D5 (`prefill`, :360). S1 needs `head` here (:104, :197, :433). `one_chunk.enter` sits **before** the gate (ours :390) where the fork runs it after (:97), which would leak an armed capture on a cancel if the knob worked. Rest: `rotlayer`, `PK8`, `DROP_MTP`, `L2PACE`, `FILL_SLICE_MS`, `SHARED_ROWS`. |
| 5 | cuda_pages.zig | 14 | 6 | 0 | 0 | 1 | 13 | 0 | All kv8-on-pages (`pageBytes(&e.w, e.settings.kv8)`, `initPaged(..., kv8, ...)`, `place(..., kv8)`) and `LINEAGE` page tags. Superseded in effect: our tree refuses fp8 on pages by name (`cuda_native.zig` test *"TF_KV_PAGES with --kv-cache fp8 ... on and all are refused"*), which the fork's change lifts. |
| 6 | cuda_sampler.zig | 10 | 6 | 1 | 1 | 0 | 0 | 3 | D3/S3, the whole file's delta is `0a77dcd7d`. |
| 7 | cuda_native.zig | 20 | 5 | 1 | 1 | 1 | 16 | 1 | D7 (`warm_spares`) and D4's enabling line (`own.e.link = &own.link`). S6 (`laterBytes` in the room calculation, :355). `snap_min_rows` is ours `= prompt_rows` = 2048 = the fork's literal, superseded now but a trap under S4. Rest: `SHARED_ROWS` (`settingsOf`/`autoRows`), `rotlayer`, `PRX`, `LINK1`, kv8 page bytes, `copyProposers`. |
| 8 | cuda_prof.zig | 8 | 3 | 0 | 0 | 0 | 5 | 3 | Profiling only: `mla_chunks`/`mla_merge` sections, `max_marks` 512 -> 1024 (needed only by the segment era), `TF_GLM_PROF_ROUTE`. |
| 9 | cuda_snapshot_pages.zig | 9 | 3 | 0 | 0 | 0 | 9 | 0 | `SNAP_GATHER` and `LINEAGE`'s shared-lease accounting (`p.shared` in `room`/`take`/`share`). |
| 10 | cuda_snapshot_layout.zig | 4 | 3 | 0 | 0 | 0 | 4 | 0 | `PK8` (`sparse.pooledRow`) and kv8 scale rows (`addCache` for `x.ls`). I checked the any-row arithmetic: `@min(at, st.ring_rows)` and `@min(at / pool + 2, pk_rows)` are correct for a keep at any row with any ring base. |
| 11 | cuda_snapshots.zig | 11 | 2 | 0 | 1 | 0 | 9 | 1 | S1's `planBytes` head term (:34). Rest is `LINEAGE`, `SNAP_GATHER`, `ONE_CHUNK`'s `taking` branch wiring. `heldPages` differing by `pub` + `@hasField` is cosmetic. |
| 12 | cuda_shared.zig | 5 | 2 | 0 | 0 | 0 | 5 | 0 | `SEG_KDA`/`SEG_DSA`/`KDA_PIECES` fills, `L2PF_PACED`, `index_shard`, the decode mla-split profile. |
| 13 | cuda_prompt_logprobs.zig | 5 | 2 | 1 | 0 | 0 | 0 | 2 | D3's other half (the `stage` buffer, :76/:86). |
| 14 | cuda_prompts.zig | 2 | 2 | 0 | 1 | 0 | 1 | 0 | S1 site (`e.mtp and g.rows > 1`, :56); `prx`/`split_min` on the Forward literal unported (`split_min` is not in our Settings). |
| 15 | cuda_prompt_pair.zig | 7 | 1 | 0 | 1 | 1 | 5 | 1 | 0042 landed `ringsAgree` and 0007 landed `drafterIdle`/`pairRows`, all byte-equal to the fork. Remaining: `PRX` (`fprx.takes`, the check constants, the plan test) and the paired-step log line. S1 site at :144. The instrument's two "kept" lines at fork :56 are a difflib alignment artefact: both trees have that function. |
| 16 | cuda_lanes_fill.zig | 1 | 0 | 0 | 0 | 0 | ~40 | ~88 | Our `multiFill` is a faithful inline port of the fork's `plan` + loop (same ordering rule, same `prompt_rows` cap, same `cut` = `chunkEnd`); the deltas are the fork's `plan` extraction with its four tests, and `FILL_SLICE_MS`'s `onward`/`settle`. |
| 17 | cuda_engine_shared.zig | 1 | 0 | 0 | 1 | 0 | 78 | 0 | S6 (`ensure`/`release`/`laterBytes`) plus `SHARED_ROWS` and `SEG_DSA`. Our `rowsOf` equivalent lives in `cuda_follow.verifyShared` against the fixed 32 rows. |
| 18 | cuda_disk_ranks.zig | 1 | 0 | 0 | 0 | 0 | 75 | 0 | `DISK_BCAST`/`DISK_LOCAL`/`DISK_CARRY` ops and `LINEAGE` remap. Whole file is dead in our tree (no `Engine.link`, no callers). |
| 19 | cuda_disk_image.zig | 1 | 0 | 0 | 0 | 0 | 70 | 0 | Same era, same deadness. |
| 20 | cuda_cost_time.zig | 1 | 0 | 0 | 0 | 0 | 54 | 0 | All `SHARED_ROWS`-driven (variable shapes, `sharedTable` interpolation to 64 rows). `COST_TIME` itself is wired here (`cuda_native.zig:367`). |
| 21 | cuda_draw1.zig | 1 | 0 | 0 | 0 | 0 | 52 | 0 | `SHARED_ROWS` sizing and the deferred `ensure` construction. `DRAW1` itself is wired (`cuda_engine_ovn.zig:10`). |
| 22 | cuda.zig | 14 | 0 | 0 | 0 | 0 | 29 | 0 | Module-registry lines for unported features only (`index_shard`, `kda_pieces`, `dsa_seg`, `prompt_pieces` alias, the disk family, `rotlayer`, `lineage`, `l2pace`). |
| 23 | cuda_engine_ovn.zig | 1 | 0 | 1 | 0 | 0 | 26 | 0 | D6 (no `ONE_CHUNK` open). Rest: `FILL_SLICE_MS`, `LINEAGE`, `KDA_PIECES`, `SEG_DSA`, and the move of `DRAW1`/`SEG_DSA` into `ensure`. |
| 24 | cuda_prompt_pieces.zig | 1 | 0 | 0 | 1 | 0 | 16 | 0 | S1's fifth site (ours :117 `if (e.mtp and nxt.len > 0)`, fork :120 `e.head`), with a comment recording the deliberate adaptation. |
| 25 | cuda_engine_prof.zig | 2 | 0 | 0 | 0 | 0 | 9 | 0 | `PROF_ROUTE` and segment-era sections. |
| 26 | cuda_router_warm.zig | 1 | 0 | 0 | 0 | 0 | 3 | 0 | Later-era call shapes (`moe.route`, `post` arity). Knob is wired (`cuda_engine.zig:243`). |
| 27 | cuda_one_chunk_keep.zig | 1 | 0 | 1 | 0 | 0 | 0 | 1 | D6: ours keeps the pin's `Plan.init`/`putAssumeCapacityNoClobber` shapes where the fork passes `snapshots.heldPages(e, at)` and `.shared = plan.shared`. Inert while the knob cannot be opened. |
| 28 | backend.zig | 1 | 0 | 0 | 1 | 0 | 0 | 0 | S7, `.first_tree = false`, Metal backend only. |
| 29 | cuda_engine_types.zig | 1 | 0 | 0 | 0 | 0 | 1 | 0 | `Snap.lin` (`LINEAGE`). Our `Snap` already carries `shared` and `win_from`. |
| 30 | cuda_lanes_shared.zig | 1 | 0 | 0 | 0 | 0 | 1 | 0 | One `SHARED_ROWS` comptime assert (`max_rows <= ranks.least_shared_rows`). |
| 31 | cuda_one_chunk.zig | 1 | 0 | 1 | 0 | 0 | 0 | 0 | D6: missing `defer cap.marks = 0;` in `leave`, and `keepsInside` reads a non-existent `e.head` (:82). |
| 32 | cuda_relay.zig | 1 | 0 | 0 | 0 | 1 | 0 | 2 | No gap. 0013 ported `EXCHANGE_KB`; the two "kept" lines are the unpieced `ncclSend`/`ncclRecv` branch, which both trees have. |

## 4. What I did not check, and why

- **Files outside my 32.** `cuda_forward*.zig` (18 R&L hunks), `cuda_ranks.zig`, `cuda_sparse.zig`, `dflash*.zig`, `cuda_copy_policy.zig`, `cuda_structured.zig`, `zig/src/core/prompt_cache_policy.zig`. I read into several of them to settle questions here (`prompt_solo.ringsAgree`, `dflash.ingestsNone`, `sparse.splitAt`, the cost tables, `prompt_cache.marksRewind`, `cuda_snaps.cacheRules`) but did not classify their hunks. Three cross-group items that belong to someone's list: S5's tap fix in `cuda_forward`/`cuda_taps`; `spares_only` in `zig/src/core/prompt_cache_policy.zig` (D7's core half); and `cuda_structured.zig`'s one-line `gather` call in D3's port.
- **No build, no run, no GPU.** Read-only brief. So every claim is a code claim; the two arithmetic walks (D1's pairing table, D1's `PastRing` case) are hand-evaluated against the quoted `ringsAgree`, `State.ready` and `State.rebase` bodies, not executed. D1 and S1 both deserve a boot A/B before anyone quotes a number; D1 can be confirmed cheaply by counting `paired steps` in the serve log on a resumed prompt, which is exactly how the fork detected it (`cuda_prompt_pair.zig:133` in the fork is the log line, and that line is itself unported here, so our build has no counter to read - worth taking with D1).
- **How often production traffic puts a mark inside a sub-2,048-token prompt (D2).** That needs the prompt-cache marks from a live run; I established only that nothing in the code prevents it any more.
- **`prompt_solo`'s own off-pool exposure beyond what D1 covers.** The file is identical in both trees (it does not appear in the instrument's output at all), so there is no fork change to port; I noted it only where 0042 widened its failure mode.
- **Decompiler-free areas.** No `.cu`/`.cuh` files are in this group, so nothing kernel-side was examined.