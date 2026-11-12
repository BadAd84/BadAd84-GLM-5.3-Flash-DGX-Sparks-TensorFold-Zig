> `LeftoverTests` is running a newer turn. The output below is from its PREVIOUS run (published 10m45s ago), not the current one. Live progress: `history://LeftoverTests`; its next result auto-delivers to its owner.[D-tests] Audit complete. 53/53 files classified. Report follows.

# 1. DEFECT-CANDIDATES (most severe first)

---

## D1 (HIGH, confidence high): two ported GPU checks cannot compile, because the port took the dependent files and left their dependency in the pin's private form

**Our files**
- `work/parity/tree/zig/tests/cuda/glm_index_check.zig:8` `const d = 128;`
- `:9` `const page_bytes = 65536;`
- `:11` `const Case = struct { cap: usize, pos: usize, rows: usize, heads: usize = 32, paged: bool = false, bits: bool = false };`
- `:34` `fn bf16(x: f32) u16 {`
- `:39` `const Bufs = std.ArrayList(cuda.DeviceBuffer);`
- `:42` `fn zeros(gpu: check.Gpu, bufs: *Bufs, n: usize) !u64 {`
- `:51` `fn fromHost(gpu: check.Gpu, bufs: *Bufs, bytes: []const u8) !u64 {`
- `:215` `fn same(gpu: check.Gpu, what: []const u8, a: u64, b: u64, n: usize, np: usize, c: Case) !usize {`

**Fork lines** (`zig/tests/cuda/glm_index_check.zig`, same line numbers): every one of those eight is `pub`:
```
pub const d = 128;
pub const page_bytes = 65536; // a page's stride: 128 pools of keys in its first half, as pages holding other rows
pub const Case = struct { cap: usize, pos: usize, rows: usize, heads: usize = 32, paged: bool = false, bits: bool = false };
pub fn bf16(x: f32) u16 {
pub const Bufs = std.ArrayList(cuda.DeviceBuffer);
pub fn zeros(gpu: check.Gpu, bufs: *Bufs, n: usize) !u64 {
pub fn fromHost(gpu: check.Gpu, bufs: *Bufs, bytes: []const u8) !u64 {
pub fn same(gpu: check.Gpu, what: []const u8, a: u64, b: u64, n: usize, np: usize, c: Case) !usize {
```

**The consumers our stack did port:**
- `work/parity/tree/zig/tests/cuda/glm_index_ovn_check.zig:6,9,10,11` and `:37`
  ```
  const base = @import("glm_index_check.zig");
  const d = base.d;
  const Case = base.Case;
  const Bufs = base.Bufs;
  ...  for (qi) |*x| x.* = base.bf16(rand.floatNorm(f32));
  ```
- `work/parity/tree/zig/tests/cuda/glm_index_regroup_check.zig:6,7,10,11,12` (same, plus `const ovn = @import("glm_index_ovn_check.zig");`)

**What goes wrong.** Zig refuses a cross-file reference to a declaration that is not `pub`. Both files are therefore un-compilable as written. The build is green only because nothing reaches them: `work/parity/tree/zig/tests/cuda/main.zig` has no `@import` and no command for either (verified by reading the whole file, lines 1-131 imports and 360-581 dispatch; the only reference to `glm_index_check.zig` is line 43/451 for the base check), so Zig never semantically analyses them. The port therefore shipped two dead files that will break the build the moment anyone registers them.

**Which patch.** `patches/engine/0009-index-sched-decode-pools32.patch:714` adds `zig/tests/cuda/glm_index_ovn_check.zig`; `patches/engine/0010-index-regroup.patch:224` adds `glm_index_regroup_check.zig` (which imports the ovn one). Those patches port `TF_GLM_OVN_DECODE_INDEX`, `_INDEX_SCHED`, `_POOLS32` and `_INDEX_REGROUP`.

**Reached by.** Nothing at runtime; it is a build hazard plus the dead gate in G1 below. The knobs it would have defended are all off by default.

**Minimal port.** Add `pub` to those eight declarations in `zig/tests/cuda/glm_index_check.zig`, then register the two commands (G1).

---

## D2 (HIGH, confidence high on the knob path / medium on the default path): a prompt pass fires a cache mark only when the mark equals a fixed 2,048-row step start, so marks inside a step are silently dropped

**Our files**
- `work/parity/tree/zig/src/families/glm/cuda_engine.zig:360-366`
  ```
  pub fn prefill(e: *Engine, ids: []const u32, from: ?Resume, cancel: ?Cancel, marks: ?Marks) !u32 {
      var start = try e.prefillStart(ids.len, from);
      while (true) {
          const rows = @min(ids.len - start, fw.prefill_rows);
          if (try e.prefillChunk(ids[start..@min(ids.len, start + rows + 1)], start, rows, ids.len, null, cancel, marks)) |first| return first;
          start += rows;
      }
  }
  ```
- `work/parity/tree/zig/src/families/glm/cuda_engine.zig:394`
  ```
  if (marks) |m| if (start > 0 and std.mem.indexOfScalar(u32, m.at, @intCast(start)) != null) m.call(m.ctx, @intCast(start));
  ```
- `work/parity/tree/zig/src/families/glm/cuda_lanes.zig` `prefillFn`: the reply-prefill arm steps `self.x.chunkOf(...)` per `chunkEnd`, but the default arm is
  ```
  var keeps: share_mod.Keeps = undefined;
  const first = try self.x.prefill(s.prompt(), from, .{ .ptr = s, .check = cancelled }, self.marksOf(s, &keeps));
  ```

**Fork lines** (commit `1b4bd29752ecddd65746d400e1dc91e067c0fa41`, "glm cuda: a whole prompt pass steps at its marks (probe, concurrent fills)"):
```
zig/src/families/glm/cuda_engine.zig
-    pub fn prefill(e: *Engine, ids: []const u32, from: ?Resume, cancel: ?Cancel, marks: ?Marks) !u32 {
+    pub fn prefill(e: *Engine, ids: []const u32, from: ?Resume, cancel: ?Cancel) !u32 {
-            if (try e.prefillChunk(..., cancel, marks)) |first| return first;
+            if (try e.prefillChunk(..., cancel, null)) |first| return first;

zig/src/families/glm/cuda_lanes.zig
+    /// The prompt pass in one call, Leader.chunk's steps unpaired: each ends at Engine.chunkEnd, so every mark keeps.
     fn prefillFn(ptr: *anyopaque, s: *lanes.Stream) anyerror!void {
-        const first = try self.x.prefill(s.prompt(), from, .{ .ptr = s, .check = cancelled }, marksOf(s));
-        self.lanes.getPtr(s).?.first = self.take(first);
+        var at: usize = if (from) |r| r.at else 0;
+        while (true) {
+            const step = try self.x.chunk(s.prompt(), at, false, from, .{ .ptr = s, .check = cancelled }, marksOf(s));
+            if (step.first) |first| {
+                self.lanes.getPtr(s).?.first = self.take(first);
+                return;
+            }
+            at += step.rows;
+            from = null; // restored by the first step
+        }
     }
```
Its message states the consequence in the fork's own words: "the disk tier's boot probe (2,088 tokens, a mark at 2,048) never kept its state, so every --learn-conversations boot died with ProbeUnmarked, and concurrent fresh prompts of 2,049 to 4,096 tokens, refused by canBatch, fell back to the same pass and never kept their history state."

**What goes wrong and on which input.** `Engine.prefill` visits starts `S, S+2048, S+4096, ...` where `S = prefillStart(...)`. A mark is fired only if it is exactly one of those starts (`cuda_engine.zig:394`). Every other mark is dropped, so the pass keeps no state there and the next turn re-prefills the whole prompt.

Two reachable inputs in our tree:

1. **`TF_GLM_OVN_KDA_CHUNKED=1` (patch `0019-kda-chunked`), the stronger case.** The prompt cache's grid becomes 32 rows:
   - `work/parity/tree/zig/src/families/glm/cuda_kda_chunk.zig:8` `pub const sub_rows = 32;`
   - `:19-21` `pub fn snapGrid() ?u32 { return if (enabled()) sub_rows else null; }`
   - `work/parity/tree/zig/src/families/glm/cuda_native.zig:31-33` `pub fn snapGridNow() ?u32 { return @import("cuda_kda_chunk.zig").snapGrid(); }`
   - `work/parity/tree/zig/src/native/cuda_snaps.zig:16-18` `if (@hasDecl(F, "snapGridNow")) if (F.snapGridNow()) |g| { ... rules.grid = g;`
   With marks at multiples of 32 and steps at multiples of 2,048, 63 of every 64 marks are dropped. The knob's own log line says "states kept on 32 rows", which is exactly what does not happen.

2. **The default path, through patch `0007-resume-any-row`.** With the knobs off the grid is `snap_min_rows` = `prompt_rows` = 2,048 (`work/parity/tree/zig/src/families/glm/cuda_native.zig:28` `pub const snap_min_rows: u32 = prompt_rows;`, `cuda_state.zig:19` `pub const prefill_rows = 2048;`). A pass that starts at 0 therefore hits every mark. A pass **resumed at a row that is not a multiple of 2,048** steps at `from.at + k*2048`, so every later mark (a multiple of 2,048) misses. Patch 0007 is precisely what makes such resume rows normal. I rate the arithmetic high-confidence and the production frequency medium, because I did not read `prefillStart`'s clamping.

**Minimal port.** Replace the default arm of `prefillFn` in `zig/src/families/glm/cuda_lanes.zig` with the stepped loop above (our tree already has `Leader.chunk` and `engine.chunkEnd`, `cuda_engine.zig:35-41`, and the reply-prefill arm immediately above already does exactly this with `chunkOf`), and drop the now-unused `marks` parameter from `Engine.prefill`/`prefillChunk`'s fixed-step path.

---

## D3 (MEDIUM-HIGH, confidence high): `canBatch` admits a prompt that has a cache mark strictly inside it, and the batched pass fires no mark

**Our file**: `work/parity/tree/zig/src/families/glm/cuda_lanes.zig:584-585`
```
pub fn canBatch(s: anytype) bool {
    return s.prompt_logprobs == null and s.images.len == 0 and s.reuse.saved == null and s.prompt_len <= engine.prompt_rows;
}
```

**Fork**: commit `03138041e` "glm cuda: a prompt with a cache mark inside it is not batched; the logprobs host stub gets its 2D copy" adds the refusal, and the message states the mechanism: "canBatch admitted any fresh prompt of up to prompt_rows tokens, and the batched pass (prefillMany) fires no mark... canBatch now refuses a stream with a mark strictly inside its prompt; a host test fails on the old rule."

**What goes wrong.** A fresh prompt that the batch path takes keeps nothing at its interior marks.

**Which input / which knob.** With every knob off this is **unreachable** in our tree and I can quote why: the batch admits only `prompt_len <= 2048`, and the cache grid with the knobs off is `snap_min_rows = 2048`, so the first mark is at 2,048 which is the prompt's end, never strictly inside. It becomes reachable under `TF_GLM_OVN_KDA_CHUNKED=1` (patch `0019-kda-chunked`), where `rules.grid = 32` (chain quoted in D2) and every prompt of 33 or more tokens carries interior marks.

**Patch it belongs to.** The batch path is the pin's; the reachability is created by patch 0019.

**Minimal port.** In `canBatch`, add the fork's clause: refuse when any mark in the stream's mark list satisfies `m > 0 and m < s.prompt_len`. The fork's accompanying host test is listed as G4b.

---

## D4 (MEDIUM, confidence high on the code, medium on severity): the reply-prefill eviction guard is absent, so a background reply pass evicts another conversation's latest state

**Our files**
- `work/parity/tree/zig/src/core/lane_host.zig:77` `warm_alone: bool = false, // the wait ends at any other admitted job too (a filling prompt), set by its family`
- `work/parity/tree/zig/src/families/glm/cuda_native.zig:39` `pub const warm_alone = true;`
- `grep -rn "spares_only" src/` returns nothing, and `grep -rn "warm_spares" src/` returns nothing.

**Fork lines** (commit `c9468e336e2ce1dfdd71b007268bd022b5c07cb1`, "reply prefill: the eviction guard, and no background pass beside admitted work"):
```
zig/src/core/lane_host.zig:74
-    warm_alone: bool = false, // the wait ends at any other admitted job too (a filling prompt), set by its family
+    warm_spares: bool = false, // a warm pass's lookups and keeps evict only superseded states, set by its family

zig/src/core/lane_job.zig:58
+        if (job.host.cache) |store| {
+            store.spares_only = job.spares();
+            defer store.spares_only = false;
+            _ = store.keepBorn(job.cacheKey(), job.request.bornLen(), at, s, job.request.chunks, job.host.spans(job.request));
+        }
+    /// A warm pass on a `warm_spares` host: its lookup and keeps evict no conversation's latest state.
+    pub fn spares(job: *const Job) bool {
+        return job.request.background and job.host.warm_spares;
+    }

zig/src/core/prompt_cache_policy.zig:21
-    return best orelse oldest;
+    return best orelse if (s.spares_only) null else oldest;

zig/src/families/glm/cuda_native.zig:42
-pub const warm_alone = true;
+/// That pass keeps nothing it would evict a conversation's latest state for (production's cap_spares).
+pub const warm_spares = true;
```

**What goes wrong and on which input.** While a reply's background prefill looks up or keeps, `victimBut` still falls back to the oldest entry, so the speculative pass evicts a live conversation's latest kept state. That conversation's next turn then re-prefills from scratch. The fork's test is `lane_host_warm_test.zig` "warm_spares: a reply pass evicts no other conversation's latest state and keeps nothing; a request still evicts".

**Knob.** `TF_GLM_OVN_REPLY_PREFILL` (patch `0008-reply-prefill`), off by default: `work/parity/tree/zig/src/families/glm/cuda_reply_prefill.zig:25-29` `/// The lane host's warm_quiet for GLM (cuda_native.warmQuietNow): null while the knob is off or refused.` and `work/parity/tree/zig/src/native/cuda.zig:458` `.warm_turns = h.store != null and snaps.warmQuiet(F) != null,`.

**Minimal port.** Add `spares_only: bool = false` to `pc.Store`, change `prompt_cache_policy.victimBut`'s last line to `return best orelse if (s.spares_only) null else oldest;`, add `Job.spares()` and the `store.spares_only` set/restore around `keepBorn` in `lane_job.zig`, add `warm_spares` to `LaneHost` and to `api.Info`/`cuda.Host` (that is the `serve(h, F, io, ...)` arity change the trainer and health tests show), and set `pub const warm_spares = true` in GLM's `cuda_native.zig`.

---

## D5 (MEDIUM, confidence medium): the background-pass drop depends on a non-zero quiet window, so a reply pass can still run inside a live fill

**Our file**: `work/parity/tree/zig/src/core/lane_host.zig:382`
```
if (r.background and r.max_tokens == 0 and h.warm_quiet > 0 and !h.quiet(job)) return h.ended(h.cancel(job)); // other work came first
```
with `:268` `while (!h.closing and !h.foregroundWaiting() and h.core.activeCount() == 0 and !(h.warm_alone and h.admitted.items.len > 1) and ...)`.

**Fork line** (same commit `c9468e336`):
```
+        // another admitted job (a stream, a prompt filling by steps or taken into a batch): the pass would run in it
+        if (r.background and r.max_tokens == 0 and (h.admitted.items.len > 1 or (h.warm_quiet > 0 and !h.quiet(job)))) return h.ended(h.cancel(job));
```
and the `warm_alone` term is removed from `quiet()`.

**What goes wrong.** Our form only drops the pass when `warm_quiet > 0`. The quiet value is the knob's own setting (`cuda_reply_prefill.zig:26-29` `return s.quiet_ns;`), so a configuration with `quiet_ns = 0` leaves the guard inert and the background pass runs beside a decoding stream or a filling prompt. The fork's commit names the same hole for other families: "qwen27, qwen4 and the Flash Next batch host could run one inside a live fill"; in our tree only GLM declares `warm_alone`, while `src/families/nemotron/cuda_native_omni.zig` also declares `warmQuietNow`.

**Knob.** `TF_GLM_OVN_REPLY_PREFILL` with a zero quiet window (patch 0008); and any other family with `warm_turns` and no `warm_alone`.

**Confidence** medium: I did not read `settings()` to confirm `quiet_ns` can be zero. The nemotron leg needs no such assumption.

**Minimal port.** Replace line 382 with the fork's line and delete the `warm_alone` term from `quiet()` (keep or delete the field as the rest of the port dictates).

---

# 2. GATE-GAPS (ported behaviour shipped undefended), most valuable first

## G1. `glm-index-ovn-check` and `glm-index-regroup-check` are never registered, so patches 0005 / 0009 / 0010 have no gate at all

Our `work/parity/tree/zig/tests/cuda/main.zig` has no import and no dispatch line for either file (full file read; `glm_index_check.zig` appears only at `:43` and `:451`). Nothing else imports them either (`grep -rln` across `tests/cuda` returns only `glm_index_regroup_check.zig` importing the ovn one). An unregistered test never runs, and in Zig it is never even compiled, which is how D1 stayed invisible.

Defends: `patches/engine/0005-index-decode-windows.patch`, `0009-index-sched-decode-pools32.patch`, `0010-index-regroup.patch`.

Exact test text to add to `zig/tests/cuda/main.zig`:
```zig
const glm_index_ovn_check = @import("glm_index_ovn_check.zig");
const glm_index_regroup_check = @import("glm_index_regroup_check.zig");
```
in the import block near line 43, this in `usage` near line 282:
```
    \\  glm-index-ovn-check       TF_GLM_OVN_DECODE_INDEX, _INDEX_SCHED and _POOLS32 against today's kernels, byte for byte (one GPU)
    \\  glm-index-regroup-check   TF_GLM_OVN_INDEX_REGROUP's scores and pools against today's, byte for byte (one GPU)
```
and this in `run` next to line 451:
```zig
    if (std.mem.eql(u8, cmd, "glm-index-ovn-check")) return glm_index_ovn_check.run(gpu);
    if (std.mem.eql(u8, cmd, "glm-index-regroup-check")) return glm_index_regroup_check.run(gpu);
```
This must land together with D1's `pub` fix or the build breaks.

## G2. The only unit defence of patch 0042's `error.PastRing` is missing from `glm_ring_host.zig`

Our `work/parity/tree/zig/glm_ring_host.zig` ends at the two rollback-pool tests; the fork has a third. The file is already built: `work/parity/tree/zig/build/glm_family_host.zig:65` creates the `ring_host` module, so the test costs nothing to add.

**Would our code pass it? Yes.** Our `cuda_state.zig:513-540`:
```
pub fn ready(st: *State, stream: cuda.Stream, rows: usize) !void {
    if (st.pos + rows > st.capacity) return error.PastCapacity;
    if (st.pos + rows > st.base + st.ring_rows) try st.rebase(stream, false);
    if (st.pos + rows > st.base + st.ring_rows) return error.PastRing; // rows past the ring overwrite its neighbour
}
pub fn readyMtp(st: *State, stream: cuda.Stream, n: usize) !void {
    if (st.mtp_len + n > st.capacity) return error.PastCapacity;
    if (st.mtp_len + n > st.mtp_base + st.ring_rows) try st.rebase(stream, true);
    if (st.mtp_len + n > st.mtp_base + st.ring_rows) return error.PastRing;
}
fn rebase(st: *State, stream: cuda.Stream, mtp: bool) !void {
    const at = if (mtp) st.mtp_len else st.pos;
    const floor = if (mtp) at -| window_rows else at;
    const nb = floor / sparse.pool * sparse.pool;
```
with `sparse.pool = 4` (`cuda_sparse.zig:9`) and `window_rows = 8` (`cuda_state.zig:21`). Walking the fork's test with `ring_rows = 64`: `ready(64)` at `pos = 65` rebases to `nb = 64`, then `65 + 64 = 129 > 128` gives `PastRing` and `base == 64`; `ready(63)` gives `128 > 128` false, so it passes; `readyMtp(64)` at `mtp_len = 64` rebases to `(64 - 8)/4*4 = 56`, then `128 > 120` gives `PastRing`; `readyMtp(56)` gives `120 > 120` false, so it passes. Every assertion holds.

Exact test text to add at the end of `zig/glm_ring_host.zig`:
```zig
test "glm ring: a pass the rebased ring cannot hold is refused, not written past the ring" {
    var d: cuda.Driver = undefined;
    d.api.cuMemcpyDtoDAsync_v2 = copy;
    d.api.cuMemsetD32Async = set;
    const stream: cuda.Stream = .{ .d = &d, .handle = null };
    var keys: [64]u8 = @splat(0);
    var gates: [64]u8 = @splat(0);
    var rings = [_]u64{ @intFromPtr(&keys), @intFromPtr(&gates) };
    var pos: u32 = 0;
    var mtp: u32 = 0;
    var st: State = undefined;
    st.arena = .{ .buf = .{ .d = &d, .ptr = 0, .len = 0 } };
    st.capacity = 1024;
    st.ring_rows = keys.len;
    st.ring_row = 1;
    st.rings = &rings;
    st.caches = &.{};
    st.cur = &.{};
    st.pos_dev = @intFromPtr(&pos);
    st.mtp_pos_dev = @intFromPtr(&mtp);
    st.mtp_caches = .{ .lc = 0, .ik = rings[0], .ig = rings[1], .pk = 0, .pk_rows = 0 };
    try st.restoreHost(stream, 65, 0, &.{}, .{ 0, 0 }); // a row into the pool at 64: a rebase keeps that row
    try t.expectError(error.PastRing, st.ready(stream, keys.len)); // 65 + 64 rows past a ring based at 64
    try t.expectEqual(@as(usize, 64), st.base);
    try st.ready(stream, keys.len - 1);
    try st.setMtpLen(stream, 64);
    try t.expectError(error.PastRing, st.readyMtp(stream, keys.len)); // MTP keeps a verify window before its cursor
    try st.readyMtp(stream, keys.len - glm.forward.window_rows);
}
```

## G3. `glm-reply-prefill-check` is never registered, so patch 0008 has no end-to-end gate

`work/parity/tree/zig/tests/cuda/glm_reply_prefill_check.zig` exists (its header reads "`glm-reply-prefill-check`: B, C and E equal A in the first token and the next window's tokens and logits; D differs") and imports only `std`, `cuda`, `check.zig` and `glm_lanes_tests.zig`, so unlike D1 it has no privacy problem. `main.zig` has no entry for it. Defends `patches/engine/0008-reply-prefill.patch`, and it is the check that would have surfaced D4 and D5 in a live run.

Text to add to `main.zig`:
```zig
const glm_reply_prefill_check = @import("glm_reply_prefill_check.zig");
```
```
    \\  glm-reply-prefill-check <ckpt> <rank> <world> <idfile>  TF_GLM_OVN_REPLY_PREFILL: next turns resumed from a reply's background pass (and one that stepped aside) against the turn without it, bit for bit, with red controls
```
```zig
    if (std.mem.eql(u8, cmd, "glm-reply-prefill-check")) return glm_reply_prefill_check.replyPrefillCheck(gpu, try arg(rest, 0), try std.fmt.parseInt(c_int, try arg(rest, 1), 10), try std.fmt.parseInt(c_int, try arg(rest, 2), 10), try arg(rest, 3));
```

## G4a. `chunkEnd` has no whole-pass test: every mark inside a pass must be a step start

Our `cuda_engine.zig:43-48` tests `chunkEnd` on four single calls only. The fork's `glm_prompt_logprobs_host.zig` test walks whole passes, including a resume off the grid. **Our `chunkEnd` (`cuda_engine.zig:35-41`) would pass it**: it is line-for-line the fork's function, and the assertions only use `chunkEnd`, not `prefill`. It is the regression net for patch `0036-chunk-step-start-len` and for the `Leader.chunk` loop that D2's fix installs.

Text to add to `zig/glm_prompt_logprobs_host.zig` (with `C = glm.engine.prompt_rows`, which is 2,048 in our tree):
```zig
test "GLM prompt rows: a whole pass's steps (Engine.chunkEnd, Lanes.prefillFn's) start at every mark inside it" {
    const C = glm.engine.prompt_rows;
    const probe = glm.native.snap_min_rows;
    const Case = struct { from: usize, len: usize, marks: []const u32 };
    const cases = [_]Case{
        .{ .from = 0, .len = probe + 40, .marks = &.{probe} }, // the disk tier's probe: one fixed step skipped it
        .{ .from = 9, .len = 3 * C + 5, .marks = &.{ 100, C + 7, 2 * C, 3 * C + 5 } }, // the template's row 9
        .{ .from = C + 3, .len = 2 * C, .marks = &.{ C + 3, C + 900, 2 * C - 1 } }, // a resume off the grid
        .{ .from = 0, .len = 2 * C + 1, .marks = &.{ 1, C - 1, C + 1, 2 * C } },
    };
    for (cases) |c| {
        var starts: [16]usize = undefined;
        var n: usize = 0;
        var at = c.from;
        while (at < c.len) : (n += 1) {
            starts[n] = at;
            const end = glm.engine.chunkEnd(at, c.len, c.marks);
            try std.testing.expect(end > at and end - at <= C); // never past one chunk: the pass stays unpaired
            at = end;
        }
        for (c.marks) |m| if (m > c.from and m < c.len) try std.testing.expect(std.mem.indexOfScalar(usize, starts[0..n], m) != null);
    }
}
```

## G4b. The discriminating test for D3 (this one FAILS on our tree under a 32-row grid)

The fork's companion test in the same file:
```zig
test "GLM prompt rows: a prompt with a cache mark inside it is not batched (the batch fires no mark)" {
    const S = struct { images: []const u8 = &.{}, reuse: struct { saved: ?*u8 = null, marks: []const u32 = &.{} } = .{}, prompt_len: usize = 2088, prompt_logprobs: ?u8 = null };
    var s: S = .{ .reuse = .{ .marks = &.{2048} } }; // the disk tier's probe: snap_min_rows + 40 tokens, kept at 2,048
    // ... expect canBatch(s) == false
    s.reuse.marks = &.{2088}; // at its end: the pass keeps that state itself
    // ... expect canBatch(s) == true
}
```
Our `canBatch` (`cuda_lanes.zig:584-585`) ignores marks entirely, so it returns `true` in both arms. Listed here because the test is the mutant for D3; the fix is D3's.

## G5. The shared-window check never covers 5 to 8 rows a stream, although our engine allows 8

`work/parity/tree/zig/tests/cuda/glm_lanes_tests.zig:244,266,280,285` fix the per-stream width at 4 (`const S = 5;`, `const lone = try a.alloc(u16, 4 * V);`, `var ids: [S][4]u32`, `const rows = 1 + (round + i) % 4;`). Our `window_rows` is 8 (`cuda_state.zig:21`, re-exported `cuda_forward.zig:36`), so a stream may bring up to 8 rows into a shared verify and that half of the range is untested. The fork's form derives the width:
```zig
    const W = glm.forward.window_rows; // a stream's rows a round at most
    const lone = try a.alloc(u16, W * V);
    const mine = try a.alloc(u16, W * V);
    var ids: [S][W]u32 = undefined;
    var outs: [S][W]u32 = undefined;
    var twin: [S][W]u32 = undefined;
```
Port the `W` substitution only. The fork's extra `wide` rounds (33 to 64 rows) and `e.settings.shared_rows` belong to the unported `TF_GLM_OVN_SHARED_ROWS` knob and must be left out.

## G6. The paged check never cuts a prompt at marks off the page and pool edges

`work/parity/tree/zig/tests/cuda/glm_paged_tests.zig` lacks the fork's sub-test that runs 5,000 and 9,001-token prompts through `x.chunk(ids, start, false, null, null, marks)` with cuts at `{1001, 2049, 3337, 4097, 6151}` and compares each against a twin, then three decode windows. Our tree has `Leader.chunk` and `engine.Marks`, so the sub-test is portable as written (drop the fork's `kv8` parameter and the `fp8` arm, which belong to the unported FP8-on-pages feature). It exercises patch 0007 and patch 0011 on a paged stream, which no gate of ours does today.

## G7. The disk grid round trip only covers the synchronous writer, not the I/O worker GLM's store uses

`work/parity/tree/zig/src/core/rows_test.zig:17-19` fixes `sync_writes = true` for every case, and the grid test at `:250-291` runs that one arm. The fork refactors it to `fn gridRoundTrip(sync: bool, tag: []const u8)` with `o.sync_writes = sync;`, drains via `_ = rows.write.drain(r, rows.write.nowNs() + 3 * std.time.ns_per_s);` and adds:
```zig
test "a grid family's chunk starts reach the I/O worker's writes as well, the writer GLM's store uses" {
    try gridRoundTrip(false, "grid-worker");
}
```
Our tree has both writers (`src/core/rows_write.zig:118 pub fn drain(r: *Rows, deadline: i128)`, `src/core/lane_host_rows.zig:39 if (!r.sync_writes) _ = rows.write.step(r);`), so only the asynchronous arm is untested.

## G8. `quiesce` has no test that it waits for an open connection to drain

`work/parity/tree/zig/src/server/health_test.zig:241-243` keeps a spin with a 5 s panic; the fork replaces it with a helper and adds `test "quiesce waits for an open connection to drain before the server is freed"` (dial, wait for `open_connections > 0`, close from a thread after 200 ms, then assert `drained == 0`). Core server behaviour, portable as written.

## G9. `glm_resume_tests.zig` case lengths are hardcoded

`work/parity/tree/zig/tests/cuda/glm_resume_tests.zig:40-42` use `.len = 6000`; the fork uses `.len = 3 * C - 144` with `C = glm.engine.prompt_rows`. Identical today (3 * 2048 - 144 = 6000), so no behaviour is missed, but the file already defines `const C = glm.engine.prompt_rows;` at `:37` and the literal silently stops meaning "three chunks less a tail" the moment S1 lands. Port with S1.

## G10. `glm_snap_fixture.zig` hardcodes the ring width

`work/parity/tree/zig/test_support/glm_snap_fixture.zig` line with `.{ if (at > 4096) at / 4 * 4 else 0, if (head > 4096) (head -| 8) / 4 * 4 else 0 }`. In our tree `ring_rows = @min(capacity, index_ring) = @min(16448, 2 * 2048) = 4096` (`cuda_state.zig:27,105,453`), so the literal is correct today. The fork reads it from the state:
```zig
        const ring = s.ring_rows; // a position past the ring's rows has rebased it (State.ready), MTP a verify window back
        try s.restoreHost(f.e.stream, at, head, &.{@as(u1, @truncate(at))}, .{ if (at > ring) at / 4 * 4 else 0, if (head > ring) (head -| 8) / 4 * 4 else 0 });
```
Mandatory if S1 is ported (the fork's ring becomes 8,192 and the literal would set wrong bases, making every snapshot host test assert the wrong prefix). Same class as the ported-dependency defects, caught before it bites.

## G11. `glm_snapshot_host.zig` never keeps a state past the index rings

`work/parity/tree/zig/glm_snapshot_host.zig:80,83` size the arena with `3 * f.e.stateBytes(8192) + 17` and loop `for ([_]usize{ 2048, 3073, 4096, 8192 }) |at|`. The fork adds a row past the rings:
```zig
        const past = f.seq.st.ring_rows + 4097; // past the index rings' rows: the fixture's state has rebased them
        try f.e.prepareSnapshots(3 * f.e.stateBytes(past) + 17);
        for ([_]usize{ 2048, 3073, 4096, 8192, past }) |at| for ([_]usize{ at - 1, at, at + 7 }) |head| {
```
This is the snapshot-side companion of patch 0042 (a kept state whose rings have rebased), portable as written; with our `ring_rows = 4096` it adds `at = 8193`.

---

# 3. SPEED-LEADS found in this group (default-on in the fork, absent from ours)

Only two of my files carry a default-on speed change; both are listed with the fork commit.

**S1. Prompt chunks of 4,096 rows, fork commit `85df341edd7ba5cf7377e446a60fbd966821809b`, "glm cuda: prompt chunks of 4,096 rows".**
`zig/src/families/glm/cuda_state.zig:17` is `pub const prefill_rows = 4096;` in the fork against `:19 pub const prefill_rows = 2048;` in ours (the pin's value, `git show 9b2991d122c7:zig/src/families/glm/cuda_state.zig:19`). Default-on, no knob. One constant drives the prompt buffers, `cuda_exl3.chunk_rows` (fork `:208 = cuda_state.prefill_rows` against our `:130 pub const chunk_rows = 1024;`), `index_ring` (two chunks, for a pair), the pair's floor, the follower's steps, the batched pass, the image map, `dflash.TAP_ROWS`, the prompt cache's pass rule. The commit gives no measured figure, so the prize has to be measured, not quoted; it halves the number of prompt steps and quadruples the EXL3 routed-expert call size on the prompt path.

This matters for the audit beyond speed: **our patch `0042-pair-fits-rings` ported only the two ring fixes out of this commit** ("Two ring fixes found on the way: a pair at a start off its pool could write one to three rows past the index ring after State.ready rebased it (ringsAgree now requires the pair to fit from the rebase), and State.ready/readyMtp refuse such a pass (error.PastRing)"). The rest of the commit, the chunk size itself and its test adaptations, is unported. Porting it requires G9, G10, G11 and the `cuda_disk_image_test.zig` capacity cases in the same change, which is exactly what the fork did.

**S2. The disk pump's idle wait, fork commit `25aab052e`, "glm disk: DISK_LOCAL saves at the knob-off speed; follower read fix".**
Our `work/parity/tree/zig/src/core/lane_host.zig:550` waits a fixed 100 ms:
```
h.wake.waitTimeout(h.io, &h.mutex, .{ .duration = .{ .raw = .fromMilliseconds(100), .clock = .awake } }) catch {};
```
the fork waits `rows_host.idleMs(h)`. Measured claim in the commit message: "GB10 (ovn9): with DISK_LOCAL the 9-token state saved in 29 s against 2.5 s and the 267k state in 5.4-6.9 s against 2.4 s. The default pump staged every save 4 pieces a round (a busy round is a 4-5 s prompt chunk): it now takes only a save the staging permit could never hold whole (pump_auto). While a pumped save runs the idle wait is 1 ms, not 100 ms." The 1 ms wait is one line of the fix; the rest (`rows_pump.zig`, `rows_write.zig`, `rows_local.zig`, `cuda_glm_disk_local.zig`) is outside my group. Gated by DISK_LOCAL, so not default-on for a serve that does not use it, but default-on for any serve that does.

---

# 4. Per-file table (all 53 files)

Counts are hunks reported by the instrument for that file, then my classification of those hunks. "R&L" is the group file's rewritten-and-left count.

| # | file | hunks | R&L | DEFECT | GATE-GAP | SPEED | SUPERSEDED | UNPORTED | COSMETIC | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | zig/tests/cuda/roce_gather_tests.zig | 25 | 24 | 0 | 0 | 0 | 0 | 25 | 0 | Whole file generalised from world 2 to any world plus a prompt-shard timing arm; our `src/cuda/roce.zig:240` still reads `if (group.world != 2) return error.PeerRefused;` and `max_world_roce` does not exist in our tree, so multi-world RoCE is unported and the check cannot be generalised ahead of it. |
| 2 | zig/exl3_prompt_host.zig | 13 | 12 | 0 | 0 | 0 | 0 | 12 | 1 | Every hunk is the extra `.{}` Ovn argument on `scratchBytes`/`bytes`/`scratch` (ours: `cuda_exl3.zig:147 pub fn scratchBytes(rows, dims, width, prefill, shx)`), `grouped_pipe`, and `glm.exl3.chunk_rows` in place of 1024. Follows S1 and the EXL3 OVN switches; the chunk_rows hunk is S1's. |
| 3 | zig/src/families/glm/cuda_kv8_test.zig | 12 | 9 | 0 | 0 | 0 | 2 | 10 | 0 | Fork implements FP8 KV on pages; ours still refuses (`error.Fp8OnPages`) and `cuda_state.zig:83 pub fn pageBytes(w)` takes one argument. Our refusal tests are the correct gate for our tree (SUPERSEDED in our favour); the rest is the unported feature. |
| 4 | zig/tests/cuda/glm_lanes_tests.zig | 10 | 7 | 0 | 1 (G5) | 0 | 0 | 8 | 1 | `W = window_rows` substitution is G5; `S = 8`, the `wide` rounds and `e.settings.shared_rows` need `TF_GLM_OVN_SHARED_ROWS` (unported); `x.prefill(ids, null, null)` is the arity 1b4bd2975 removes (see D2). |
| 5 | zig/tests/cuda/glm_index_check.zig | 7 | 7 | 7 (D1) | 0 | 0 | 0 | 0 | 0 | All seven hunks are the missing `pub`. Load-bearing for the two ported checks; see D1. |
| 6 | zig/tests/cuda/glm_ref_kda.zig | 5 | 5 | 0 | 0 | 0 | 0 | 5 | 0 | Same `pub` widening, but its consumer `glm_ref_kda_chunk.zig` is fork-only (not in our tree), so inert here. |
| 7 | zig/glm_prompt_host.zig | 6 | 5 | 0 | 0 | 2 (S1) | 0 | 3 | 1 | `prefill_rows`/`prompt_rows` derived from the engine instead of literal 2048 belongs to S1; `mtp` renamed `head` and `split_min` belong to unported changes (our `Engine` has no `head` field, our `Settings` no `split_min`). |
| 8 | zig/tests/cuda/glm_paged_tests.zig | 6 | 4 | 0 | 1 (G6) | 0 | 0 | 4 | 1 | The marks-cut sub-test is portable (G6); the `kv8`/`fp8` arm and the 33,000-token lengths follow FP8-on-pages and S1. |
| 9 | zig/src/native/cuda_health_test.zig | 4 | 4 | 0 | 0 | 0 | 0 | 4 | 0 | All four are the `serve(h, Family, io, ...)` arity added by `c9468e336`; consequence of D4's unported `warm_spares`. |
| 10 | zig/src/families/glm/cuda_start_test.zig | 5 | 3 | 0 | 0 | 0 | 3 | 2 | 0 | Fork deletes the `Fp8OnPages` refusal cases because it supports FP8 on pages. Ours must keep them; our file has strictly more coverage for our tree. |
| 11 | zig/glm_snapshot_host.zig | 6 | 3 | 0 | 1 (G11) | 0 | 0 | 4 | 1 | `past = ring_rows + 4097` is G11; `e.head = true`, the `TF_KV_SHARE` adapter test and the split into `glm_snapshot_paged_host.zig` are unported (our file still holds the paged tests inline, which is why the instrument shows them as "ours still has"). |
| 12 | zig/src/core/rows_test.zig | 5 | 3 | 0 | 1 (G7) | 0 | 0 | 0 | 4 | The `gridRoundTrip(sync, tag)` refactor plus the worker arm; see G7. |
| 13 | zig/tests/cuda/main.zig | 19 | 2 | 0 | 3 (G1, G3) | 0 | 0 | 16 | 0 | 16 of 19 hunks register fork-only files absent from our tree (`glm_exl3_ovn_tests`, `glm_mm_ovn_tests`, `glm_onepass_check`, `glm_lineage_tests`, `l2pace_tests`, and so on). The three that matter are the two index checks and the reply-prefill check, all three present in our tree and unreachable. |
| 14 | zig/build/rows_host.zig | 3 | 2 | 0 | 0 | 0 | 0 | 3 | 0 | Fork adds a second artifact filtered on `"disk_readers"`; `grep -rn "disk_readers" src/` returns nothing in our tree, so there is nothing to run. |
| 15 | zig/src/core/lane_host.zig | 3 | 2 | 2 (D5) | 0 | 1 (S2) | 0 | 0 | 0 | The `admitted.items.len > 1` guard and the `warm_alone` to `warm_spares` field swap are D5/D4; the `rows_host.idleMs(h)` wait is S2. |
| 16 | zig/src/families/glm/cuda_ranks_test.zig | 3 | 1 | 0 | 0 | 0 | 0 | 3 | 0 | `TF_GLM_SPLIT_MIN`, `TF_GLM_OVN_SHARED_ROWS`, `_SHARED_BS_ROWS` and the `ovn_comms`/`moe_owners`/`shared_rows` fingerprint fields are all unported settings; our fingerprint field list at `:275` matches our own `Settings`. |
| 17 | zig/tests/cuda/glm_exl3_tests.zig | 3 | 1 | 0 | 0 | 0 | 0 | 3 | 0 | The `k.prompt.ovn` switches matrix and the extra `scratchBytes` argument; unported EXL3 OVN variants. |
| 18 | zig/glm_prompt_logprobs_host.zig | 4 | 1 | 1 (D3) | 2 (G4a, G4b) | 0 | 0 | 1 | 0 | The two chunkEnd/marks tests (one passes, one fails) plus the `cuMemcpy2DAsync` stub the fork added for an unported sampler change. |
| 19 | zig/src/server/health_test.zig | 3 | 1 | 0 | 1 (G8) | 0 | 0 | 2 | 0 | The quiesce-drain test is portable; the `dial`/`closeAfter` helpers come with it. |
| 20 | zig/test_support/glm_snap_fixture.zig | 2 | 1 | 0 | 1 (G10) | 0 | 0 | 1 | 0 | `s.ring_rows` for the literal 4096 (G10) and `f.e.head = mtp` (unported `Engine.head`). |
| 21 | zig/build/windows_host.zig | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | Adds the filter `"the room leaves aside"` for a fork-only pool test. |
| 22 | zig/qwen35_cost_open_host.zig | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | `serve(struct {}, ...)` arity; follows D4. |
| 23 | zig/src/native/cuda_prompt_cancel_test.zig | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | Same arity. |
| 24 | zig/src/native/dense_trainer_close_test.zig | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | Same arity. |
| 25 | zig/src/native/nemotron_trainer_test.zig | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | Same arity. |
| 26 | zig/src/native/trainer_close_test.zig | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | Same arity. |
| 27 | zig/test_support/glm_mm_cuda.zig | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | Adds `cluster: ?Dim3` to the fake launch config, needed only by the unported `TF_GLM_OVN_MM_CLUSTER`. |
| 28 | zig/tests/cuda/glm_loader_gate.zig | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | Extra `weights.load` argument; our `cuda_weights.zig:532` still takes ten. |
| 29 | zig/tests/cuda/glm_ref_attn.zig | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | `latent.headBlock(1, heads)`; our `cuda_latent.zig:16 headBlock(rows)` plus `:21 headBlockOf(rows, heads)` is the pin's split form. |
| 30 | zig/src/families/glm/cuda_mla_ovn_test.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 75 lines of `LATENT_MMA`, `SEG_PASS` and `TF_GLM_PROF` mla-stage tests for kernels our stack did not port (patch 0021 ported only part of the MLA knob set). |
| 31 | zig/glm_mm_policy_host.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 53 lines for `MM_WIDE`, `MM_CLUSTER`, `MM_DECTILE`, `SWIGLU_REDUCE`; patch 0020 ported some mm knobs but not these kernels. |
| 32 | zig/src/core/lane_host_warm_test.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 48 lines, the `warm_spares` and batch-drop tests; they are the mutants for D4 and D5 and should land with that fix. Cannot be ported alone (they need `host.warm_spares` and `store.spares_only`). |
| 33 | zig/src/families/glm/cuda_disk_image_test.zig | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 44 lines: the `rows_kept` list, a state past the rings, `back = far - ring_rows` bases and the blank-seal case. Companion of S1 and of patch 0042; portable once `capacity = index_ring + 2048` is expressed from our own constants. |
| 34 | zig/src/core/rows_pool_select_test.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 23 lines needing `table.trim` and `table.reuses`, which do not exist in our `rows` table (`grep "trim:\|reuses:"` empty). |
| 35 | zig/tests/cuda/experts3_tests.zig | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 23 lines of NVFP4 decode timing at GLM's routed shape; a bench, no assertion. |
| 36 | zig/build/glm_family_host.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 21 lines registering host tests for `onepass_order`, `SHARED_FIRST`, `HC_ROWS`, `ROUTER_WARM`, `KDA_PIECES`, `PRX`, `MULTI_FILL` and `copy.zig`; every target is fork-only. |
| 37 | zig/src/core/lane_host_prefix_test.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 13 lines for `TENSORFOLD_PREFIX_WAIT_MIN_ROWS`, an unported env knob. |
| 38 | zig/src/families/glm/cuda_lanes_test.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 13 lines for `TF_GLM_OVN_DEPTH_FULL`, `SHARED_COPY` and `e.settings.shared_rows`; all unported. |
| 39 | zig/glm_ring_host.zig | 1 | 0 | 0 | 1 (G2) | 0 | 0 | 0 | 0 | The single highest-value gap in the group: patch 0042's `error.PastRing` has no unit test, and our code passes the fork's. |
| 40 | zig/src/native/cuda_warm_serve_test.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 8 lines asserting `warm_spares` reaches the host; the mutant for D4's family wiring. |
| 41 | zig/src/native/copy_drafts_cuda_test.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 6 lines setting `e.settings = .{}` and faking `SHARED_DRAFTS`; needs the unported `shared_rows` setting. |
| 42 | zig/src/families/glm/cuda_zero_budget_test.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 5 lines, same `settings`/`SHARED_DRAFTS` shape. |
| 43 | zig/tests/cuda/glm_ref_tests.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 4 lines calling `glm_ref_kda_chunk`, `glm_ref_moe_ovn`, `glm_ref_ovn`, `glm_ref_hc_rows`; none of those files exist in our tree, so patches 0019 and 0022 shipped their kernels without a float64 reference. Worth recording as a follow-up: porting the reference files would turn this into a real gate. |
| 44 | zig/build/cuda_server_host.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 3 lines wiring a `test-prompt-once-host` step over fork-only filters. |
| 45 | zig/tests/cuda/glm_resume_tests.zig | 1 | 0 | 0 | 1 (G9) | 0 | 0 | 0 | 0 | Three case lengths expressed as `3 * C - 144` instead of 6000; numerically identical today. |
| 46 | zig/glm_dflash_host.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 2 lines asserting `glm.dflash.STEP_ROWS >= glm.ranks.most_shared_rows`; `most_shared_rows` does not exist in our tree (our `dflash.zig:31 STEP_ROWS = 32` equals our fixed `shared_rows = 32`). |
| 47 | zig/glm_image_cache_host.zig | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 2 lines adding `snap_min_rows`/`snapGridNow` decls to a stub family so the fork's cache rules resolve; inert for us. |
| 48 | zig/src/core/lanes/free_shared_test.zig | 1 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 2 lines for `cfg.shared_depth_full`, an unported knob. |
| 49 | zig/tests/cuda/glm_index_ovn_check.zig | 1 | 0 | 0 | 1 (G1) | 0 | 0 | 0 | 2 | Our copy lacks the fork's `pub const Inputs`/`pub fn inputs` (the regroup check imports them). Together with D1 this file neither compiles nor runs. |
| 50 | zig/glm_structured_host.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 line `e.settings = .{}` for the unported shared-rows setting. |
| 51 | zig/src/families/glm/cuda_pages_test.zig | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | Fork writes `.grid = native.snap_min_rows`; ours writes `.grid = cuda_engine.prompt_rows` (`:413`). Equal today (both 2048) because `cuda_native.zig:28 pub const snap_min_rows: u32 = prompt_rows;`. Diverges if S1 lands, so change it with S1. |
| 52 | zig/src/native/draft_sources_cuda_test.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 line `e.settings = .{}`; unported shared-rows setting. |
| 53 | zig/tests/cuda/glm_draft_onepass_tests.zig | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 line rounding a wide reference to bf16, part of the unported `ybf16` EXL3 variant. |

Totals across the group: 5 defect-candidates (D1 to D5, touching 4 files), 11 gate-gaps, 2 speed-leads, 3 files where our coverage is deliberately broader than the fork's (SUPERSEDED), and the remaining bulk unported-feature or cosmetic.

---

# 5. What I did not check, and why

- **I did not build or run anything.** The assignment is read-only, so every "would pass" and "would not compile" claim is derived from reading both trees. D1's compile claim rests on the Zig rule that a non-`pub` declaration is not visible across files plus the quoted declarations and uses; G2's "would pass" rests on walking the fork's assertions through our quoted `ready`/`readyMtp`/`rebase` with `sparse.pool = 4` and `window_rows = 8`. Both should be confirmed by one `zig build` and one `test-glm-ring-host` run before anything lands.
- **`prefillStart`** in `cuda_engine.zig` I did not read, so D2's default-path leg (resume at an off-grid row) is rated medium. The knob leg does not depend on it.
- **`cuda_reply_prefill.zig` `settings()`** I did not read, so D5's "`quiet_ns` can be zero" premise is unverified; the nemotron leg of D5 does not need it.
- **Non-test production files** outside my group (`cuda_prompt_pair.zig`, `cuda_one_chunk*.zig`, `cuda_follow.zig`, `dflash.zig`, `rows_pump.zig`) I read only where a test pointed at them. S1's full porting surface is 17 files and most of them are not mine; `LeftoverStepState` owns the step-state side.
- **The fork's own fork-only test files** (`glm_ref_kda_chunk.zig`, `glm_ref_ovn.zig`, `glm_onepass_check.zig`, and the rest of the 60-odd absent files) I inventoried by name but did not read; they are listed as unported because the feature they test is unported, which I verified by grepping our tree for each feature's knob or symbol.
- **`rows_pool_select_test.zig`'s portability** I judged from the absence of `trim`/`reuses` in our rows table; I did not trace whether an equivalent exists under another name.