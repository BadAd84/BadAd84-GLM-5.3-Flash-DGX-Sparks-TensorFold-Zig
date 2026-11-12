All 55 files classified. Final report:

# C-core-native: fork changes our port lacks

## 0. Method and the two headline corrections

Instrument rerun on every file of the group (`scripts/port-leftover.py ../ai-engine 9b2991d12 fork-ssh/ovn-up work/parity/tree --show .zig`, filtered to the group list): 55 files, 142 rewritten-and-left hunks, 1,015 missing lines, 574 kept lines, matching the brief.

First I measured which of the 55 our patch stack touches at all (`diff work/pin/tree/<f> work/parity/tree/<f>`): **only 14 differ from the pin**; 41 are byte-identical to the pin. That does not clear them (the worked example's `ringsAgree` was byte-identical to the pin too), but it says where to look hardest.

Two briefing assumptions turned out to be wrong, and both change conclusions:

- **`zig/src/cuda/roce.zig` is NOT superseded.** `git show 9b2991d122c7:zig/src/cuda/roce.zig` and `work/pin/tree/zig/src/cuda/roce.zig` are 597 lines each and `diff -u` prints nothing: upstream has not touched RoCE since the fork's merge base. Every one of the 34 rewritten-and-left hunks there is live fork work, and the central one (worlds 2 to 4) matters to us because we serve TP=3. See SPEED-LEAD S2.
- **`zig/src/native/cuda_kv_pool.zig` and `zig/src/native/cuda_snaps.zig` have zero leftovers** and so are absent from the instrument's whole 186-file output, not just from my group list. There is nothing to classify in them; the kept-state byte and page-rounding leftovers the brief expected live in `zig/src/families/glm/cuda_snapshot_pages.zig` (3 R / 13 M), `cuda_snapshot_layout.zig` (3 R / 9 M) and `cuda_snapshots.zig` (2 R / 28 M), all in group A-step-state.

On the brief's high-severity question: **no fork change in the tokenizer or the template alters token ids or the rendered prompt on the default path.** Evidence under D-none below and in S1/S3/S4; the whole tokenizer/template delta is the HOST_ONCE extraction plus two measured optimisations the fork proves equal (its own fuzz test for `strIndex`, "ids identical" in the commit message).

---

## 1. DEFECT-CANDIDATES

### D1 (high confidence, medium-high severity). The reply-prefill eviction guard: a background warm pass can evict another conversation's latest kept state

**Ours:** `work/parity/tree/zig/src/core/prompt_cache.zig:126` (no `spares_only` field after `hold`), `prompt_cache_policy.zig:29` `return best orelse oldest;`, `lane_job.zig:58-62` (`kept` calls `keepBornFrame` unguarded), `lane_stream.zig:28` (`lookupUserFrame` unguarded).
**Fork:** `prompt_cache.zig:126`, `prompt_cache_policy.zig:24`, `lane_job.zig:58-70`, `lane_stream.zig:28,35`, all from commit **c9468e336** "reply prefill: the eviction guard, and no background pass beside admitted work" (30 Oct 2026, author Adam Hillson). Its message states the mechanism exactly:

> Production's cap_spares: while a background reply pass looks up or keeps, victimBut has no oldest fallback (Store.spares_only), so the pass never evicts another conversation's latest state; such a keep keeps nothing.

The fork's lines:

```zig
// prompt_cache.zig, after `hold:`
    spares_only: bool = false, // set around a call: it evicts only superseded states, never a conversation's latest
// prompt_cache_policy.zig
    return best orelse if (s.spares_only) null else oldest;
// lane_job.zig
        if (job.host.cache) |store| {
            store.spares_only = job.spares();
            defer store.spares_only = false;
            _ = store.keepBornFrame(job.cacheKey(), job.request.bornLen(), at, s, job.request.chunks, job.host.spans(job.request), job.request.images, job.frame);
        }
    /// A warm pass on a `warm_spares` host: its lookup and keeps evict no conversation's latest state.
    pub fn spares(job: *const Job) bool {
        return job.request.background and job.host.warm_spares;
    }
// lane_stream.zig, around the lookup
    if (h.cache) |store| store.spares_only = job.spares(); // its lookup makes room for its marks: no latest state goes
    ...
    if (h.cache) |store| store.spares_only = false;
```

**What goes wrong, on which input.** Conversation A's turn ends; `server/warm.zig:28` submits the background pass that prefills the reply and the next turn's opening. That pass takes the normal lane path (`lane_stream.open` -> `store.lookupUserFrame`, then `Job.kept` -> `store.keepBornFrame`). To make room for its own marks the store calls `prompt_cache_policy.victimIn`; with no superseded entry available it falls through to `oldest`, which is routinely conversation B's only, latest, state. B is idle, so nothing protects it. B's next turn then re-prefills its whole context. On the owner's workload that is the 650k-token cold prefill the NVMe tier exists to avoid, traded for a background prefill of someone else's reply. No wrong tokens, pure latency, but it is the expensive kind.

**Default path?** No. It needs `TF_GLM_OVN_REPLY_PREFILL=1`. Chain verified in our tree: `families/glm/cuda_reply_prefill.zig:27-31 quietNs()` returns null unless `cuda.ovn.on("REPLY_PREFILL")`; `families/glm/cuda_native.zig:35 warmQuietNow()` feeds `native/cuda_snaps.zig:51 warmQuiet(F)`; `native/cuda.zig:458` sets `.warm_turns = h.store != null and snaps.warmQuiet(F) != null`; `cuda_startup_phase.zig:37-38` sets `h.host.warm_quiet` / `warm_alone`. With the knob off there are no warm turns and the guard is unreachable; with it on, every turn end reaches it.

**Patch it belongs to:** 0008 (`TF_GLM_OVN_REPLY_PREFILL`), wired by 0025 ("carry the family's warm-turn wait to the lane host"). Our port took the fork's pre-c9468e336 state: `warm_alone` (removed by that very commit) is in our tree at `lane_host.zig:77`, and `warm_spares`/`spares_only` never arrived. Confirmed by `git grep`: `warm_alone` fork=0 files, ours=6; `warm_spares` fork=7, ours=0; `spares_only` fork=5, ours=0.

**Confidence: high.** The fork commit is a deliberate fix for this exact feature, the knob chain is verified end to end in our files, and the fallback line it removes is present verbatim in ours.

**Minimal port** (four of my files; the fifth, `lane_host.zig`, is D-tests' and I have messaged that lane):

1. `prompt_cache.zig` insert after line 126: the `spares_only` field above.
2. `prompt_cache_policy.zig:29`: `return best orelse if (s.spares_only) null else oldest;` (ours routes both `victimBut` and the `own_only` path through `victimIn`, so this one line covers both; the fork's own file still has only `victimBut`).
3. `lane_job.zig:62`: wrap as above, keeping **our** `keepBornFrame(... , job.request.images, job.frame)` signature, and add `pub fn spares`.
4. `lane_stream.zig`: the two `store.spares_only = ...` lines, before line 28 and after line 33, verbatim (our surrounding lines are identical to the fork's).
5. `job.spares()` needs a host flag. Faithful: add `warm_spares: bool = false` to `LaneHost` and set it in `cuda_startup_phase.zig` beside `warm_alone`, with GLM declaring it. Minimal, no new field: `return job.request.background and job.host.warm_quiet > 0;`, which in our tree is true exactly for a GLM warm pass.

**Sibling, same commit, outside my files (for the D lane):** the fork also replaced `setup`'s drop test with `(h.admitted.items.len > 1 or (h.warm_quiet > 0 and !h.quiet(job)))`. Ours (`lane_host.zig:382`) still requires `warm_quiet > 0`, so for qwen27, qwen4 and the Flash Next batch host (warm_quiet 0) a background pass can still run inside a live fill. For GLM the behaviours coincide because `warm_alone` makes `quiet()` return false as soon as another job is admitted, so this half is not a GLM defect.

### D2 (medium confidence, low severity, no runtime effect). `df_sumw` ships with no compile record

**Ours:** `work/parity/tree/zig/src/core/contract/glm_cuda_records.zig` ends its `glm_dflash` run at line 38 (`df_gsum`); there is no `df_sumw` entry anywhere in the tree (`grep -rn df_sumw` returns only `zig/kernels/cuda/glm_dflash.cu:273` and `zig/tests/cuda/glm_draft_onepass_tests.zig`).
**Fork:** `glm_cuda_records.zig:36` adds

```zig
    .{ .launch = .{ .name = "df_sumw", .symbol = "df_sumw", .image = "glm_dflash", .threads = 256, .min_sm = 80 }, .usage = .{ .{ .regs = 32, .static = 0, .bound = 0 }, .{ .regs = 40, .static = 0, .bound = 0 }, .{ .regs = 40, .static = 0, .bound = 0 }, .{ .regs = 33, .static = 0, .bound = 0 }, .{ .regs = 33, .static = 0, .bound = 0 } } },
```

**What goes wrong.** We ported the kernel (`glm_dflash.cu:273`, and our own GPU check at `glm_draft_onepass_tests.zig:85-122` exercises it precisely at world 3: "world 3 is bf16(((g0 + g1) + g2))"), so on a TP=3 serve `df_sumw` runs in the DFlash2 draft block every round. Our contract registry (`registry_joins.zig:6`) therefore has a per-SM register and shared-memory receipt for every other `glm_dflash` kernel but not this one: a future nvcc or source change can move its occupancy with no gate noticing. There is no runtime misbehaviour today and no test fails (our tree has no "pending" entry for it either, unlike `glm_l2pf`, which has `glm_l2pf_pending.zig`, wired at `registry.zig:590`).

**Default path?** Yes for execution (TP>=2 draft path, no knob); the missing item is the receipt, not the code.
**Patch:** 0004/0023 ported the kernel, 0032 is the one that registers ported kernels, so the record belongs with 0032.
**Confidence: medium** on severity classification (it is a gate hole, not a behaviour change); high that the line is absent and the kernel is live.
**Minimal port:** the one record line above, appended to the `glm_dflash` run in `glm_cuda_records.zig` (or a `df_sumw` entry in a pending file if the receipts for our build differ).

### D-none: the places a defect of the worked example's shape could have hidden, checked and clear

Recorded because an absence is a claim:

- **Patch 0006 (KEPT_WALK) is a faithful port.** `diff` of the fork's file against ours: `prompt_prefix.zig` differs only by our extra `test {}` block; `prompt_cache_policy.zig` differs only by `spares_only` (D1) and by our extra `victimIn`/`own`, which come from the pin's `keep_others` work; `rows_store.zig:287 matches` is line-for-line the fork's (`prompt_prefix.starts`); `prompt_cache_index.zig:12` uses `prefix.ends`, which `prompt_prefix.zig:44-49` defines as last-id-then-whole, i.e. exactly the fork's duplicated pair of lines, so the one "missing" line there is the fork carrying a redundant merge leftover.
- **Patch 0007 (resume at any row) left nothing in `lanes/open.zig`.** Our `batchable` (`open.zig:63-67`, with `many_resumed`) produces no leftover hunk; the file's single hunk is the unrelated `first_tree` gate.
- **Tokenizer and template do not move ids.** `git diff 9b2991d122c7 fork-ssh/ovn-up -- zig/src/core/tokenizer/tokenizer.zig` is a pure extraction: `checkSpans` and `encodeSegments` lift the same statements out of `encodeMaskedCounted`, which then calls them with the same arguments; `validMasked` and `Segment` only become `pub`. In `template.zig`, `renderProvenanceGlobals` now calls `renderMore` with `More{}`, and `rootMarked` executes `body[0..split]` then `body[split..]` instead of `body`, differing only if a top-level statement returns non-normal flow. Every `c.wrote(from)` in `eval.zig` returns immediately when `watch == null`. The commit itself claims "ids identical".
- **Our prompt-cache test wiring was moved, not dropped.** Our `prompt_cache.zig` deletes the pin's `test {}` block, but all 14 `prompt_cache_*_test.zig` files are imported from `engine_api_test.zig:12-34`; each has exactly one importer.

---

## 2. SPEED-LEADS

### S1. Render and tokenize a request once: 91 ms -> 41 ms at 650k, 25 ms -> 10-13 ms at 200k

**Fork sha ef81b4a49**, "server: render and tokenize a request once; TF_GLM_OVN_HOST_ONCE". Measured claim quoted verbatim from the commit:

> chat.prepare rendered and tokenized the whole conversation four times (prompt, history, continuation and rewind probes) and parsed every tool call in each render: 91 ms for a ~650k agent turn, 25 ms at 200k (prompt_bench, ReleaseFast, GLM-5.3 template). Now the prompt is encoded once with its segments kept and each probe re-encodes only the segments that differ (ids proven equal to a full encode); the history mark comes from the template render without a second pass; tool arguments are parsed once; content.0 indexes without counting code points. 650k: 91 -> 41 ms, 200k: 25 -> 10-13 ms, ids identical.

**Default-on?** Yes for the whole saving above. `TF_GLM_OVN_HOST_ONCE=1` only adds the early stop in the rewind probe (`srv.host_once`, read at `server.zig:228` in the fork); the `Once` struct, the kept segments, the memoised tool arguments and the template history mark all run unconditionally.

**Ours:** `server/prompt.zig:155` still does `const history = try renderIds(srv, cx, input.messages, input.tools, thinking, effort, false);` and then two further probe renders; `hf_text.zig:440` still calls `template.renderProvenanceGlobals`; `model_text.zig` has no `Kept`/`Pieces`/`keep`/`pieces`/`prefix_pieces`; `messages.zig` has no `Args` memo.

Why it is worth the owner's attention despite being host-side: it is 50 ms of single-threaded engine-thread work per agent turn at the context size our serve actually runs, and it is paid again on every probe-heavy turn. Porting cost is not small: it needs the new files `core/template/generation.zig`, `core/template/watch.zig`, `core/tokenizer/kept.zig`, `server/hf_text_kept.zig` plus the `model_text` vtable, i.e. 8 files of mine and 4 new ones (the fork's own `zig/build/server.zig` `promptBench` step and `zig/tests/server/prompt_bench.zig` are how it was measured, and would give us the same before/after number locally without a GPU).

### S2. RoCE one-shot gather at worlds two to four: our TP=3 serve cannot use the RDMA gather at all

**Fork sha 060465305**, "roce: serve worlds two to four in the one-shot gather" (plus 07dfdd046 rail pairing by shared /24, 1470a3c86 errno on RTR, 57353178e test fix). No measured figure is given in any of those messages; I am not inventing one.

**Ours:** `cuda/tp_group.zig:75` `if (g.world != 2 or g.fast != null) return;` and `cuda/roce.zig:240` `if (group.world != 2) return error.PeerRefused;`.
**Fork:** `tp_group.zig:79` `if (g.world < 2 or g.world > roce.max_world_roce or g.fast != null) return;` with `max_world_roce = 4`, a per-peer receive slot and flag set in `Layout.of(max_bytes, world, hcas)`, one queue pair per (peer, HCA), and `post` striping each sequence to every peer.

**Why it matters here.** GLM opens this path itself: `families/glm/cuda_native.zig:321 try own.group.openRoce(...)`. The gathers it serves are per decode round: `cuda_draw1.zig:71`, `cuda_engine_pick.zig:27`, `cuda_forward.zig:246`, `dflash_block.zig:79` all call `Group.allGather`, which at `tp_group.zig:87` prefers `g.fast` and otherwise falls to `ncclAllGather`. At world 3 our `g.fast` is always null, so every one of those small gathers is an NCCL collective. The fork's later rails commit (c920d6e5a) calls these "decode gathers", confirming the path.

**Partly superseded, and this is the caveat that decides whether to port.** The pin does have a second route for three ranks or more: `families/glm/cuda_roce_multi.zig:1` ("TF_GLM_ROCE_MULTI=1 at three ranks or more: the main stream's small all-gathers on fabric/tp's multirank RoCE"), wired at `cuda_native.zig:323`, landing in `g.multi` and consulted at `tp_group.zig:88`. It is **off by default** (`cuda_ranks.zig:27 roce_multi: bool = false`) and needs `TF_TP_MASTER` and `TF_TP_KERNEL_IMAGE` (`cuda_ranks.zig:158`), where the fork's route needs no env at all. So the honest statement is: if our TP=3 serve already sets `TF_GLM_ROCE_MULTI=1` with the fabric env, the gap is small and this is a second implementation; if it does not (which the repo cannot tell me), our decode rounds are on NCCL for every small gather and this is the largest untapped decode-path lead in my group. The cheap first step is to read the serve's env, not to port.

**Not default-on, therefore not leads:** `TF_GLM_OVN_ROCE_RAILS` / `_LINK1` / `_ROCE_ILP` / `_ROCE_CPU` (c920d6e5a, "Default off and bit-exact") and `TF_GLM_OVN_PRX` (b9c9f4a0f, 320 MiB pinned a rank).

### S3. `memo.equal`: 0.23 ms where `mem.eql` took 2.1 ms on 1.4 MB

**Fork sha ef81b4a49**, `zig/src/core/tokenizer/memo.zig`, with the measurement in the code comment:

```zig
/// Byte equality: indexOfDiff took 0.23 ms where mem.eql took 2.1 on 1.4 MB (ReleaseFast, x86_64 laptop).
pub fn equal(x: []const u8, y: []const u8) bool {
    return std.mem.indexOfDiff(u8, x, y) == null;
}
```

**Ours:** `memo.zig:40` and `memo.zig:76` still `std.mem.eql(u8, e.text, text)`. Default-on, on the prompt path (one confirmation compare per memo hit, and hits are segments of 1,024 bytes and up). Semantics identical: `indexOfDiff` returns null exactly when the slices are equal. **Minimal port: the three lines above.** This is the cheapest item in the whole report.

### S4. `access.strIndex`: stop counting code points at the index

**Fork sha ef81b4a49**, `zig/src/core/template/access.zig`. Ours at `access.zig:123` still evaluates `index(i, uni.count(s.s))`, which walks the entire string; the fork's `strIndex` stops at the requested index for non-negative `i` and falls back to the old form for negative ones. The fork proves equality with a 2,000-case randomised test over mixed ASCII, multi-byte and malformed bytes. Default-on, part of the 91 -> 41 ms above (the commit names "content.0 indexes without counting code points" as one of its four components). **Minimal port: the `strIndex` function plus the one call-site change at `access.zig:123`.**

### S5 (conditional, listed so it is not lost). Disk reads for a pool that reuses spare storage

**Fork sha 52c1e382f**, `rows_select.zig` capacity and `rows_read.zig` `ready`. Its message: "A family whose kept states live in preallocated storage it reuses (GLM's snapshot pages on CUDA) and cannot trim never had a disk read chosen". GLM is that family in our tree (`cuda_snaps.zig:73` sets `.reuses` from `F.snap_reuses`, declared at `families/glm/cuda_native.zig:432`, and the `Snaps` vtable sets no `.trim`). It is **inert for us today**: GLM has no `kept_disk`, so `--learn-conversations` is refused at `native/cuda_refusal.zig:62` ("for Nemotron, the Qwen hybrids and Flash Next only") and `store.disk` is null, so `rows_select.chooseAt` returns at its first line. It becomes a prerequisite the day we port the fork's GLM disk tier (`cuda_glm_disk.zig`), and would otherwise silently refuse every restore.

---

## 3. Per-file table (all 55)

R = rewritten-and-left hunks, H = total hunks, M = missing lines, K = kept lines. Class counts are per hunk.

| # | file | R / H / M / K | DEF | SPD | SUP | UNP | COS | note |
|---|---|---|---|---|---|---|---|---|
| 1 | cuda/roce.zig | 34/48/171/236 | 0 | 24 | 0 | 24 | 0 | Pin is byte-identical to the fork's base (597 lines, empty diff): nothing here is superseded by upstream. Worlds 2-4 gather = S2; verbs split, rails, ILP, CPU pin, PRX = unported knobs. |
| 2 | server/prompt.zig | 10/14/88/33 | 0 | 14 | 0 | 0 | 0 | All ef81b4a49 (`Once`, `Probe`, `rendered`, `closer`, `rewindWith`). S1. `continuedLen` is already in the pin at `prompt.zig:168`, so that hunk is pin-side motion only. |
| 3 | core/rows_store.zig | 10/20/61/12 | 0 | 0 | 0 | 18 | 2 | DISK_CARRY / PUMP / LOCAL / READERS fields, `TENSORFOLD_ROWS_STAGING_GIB`, `unlink` helper, test list. 2 cosmetic: `@import("lanes").rows_image/rows_file` module move. `matches` is already the fork's line. |
| 4 | cuda/exl3_prompt.zig | 10/15/61/13 | 0 | 0 | 0 | 15 | 0 | `Ovn` (EY_DIRECT, X3_PROMPT_K64, X3_PROMPT_ORDER, X3_YBF16, X3_ROTEXPERT) plus the `Out` argument; `fromEnv().any()` is false by default so `extra` stays null and `run` is the pin's. Ours == pin at `exl3_prompt.zig:58`. |
| 5 | core/tokenizer/tokenizer.zig | 10/13/19/17 | 0 | 13 | 0 | 0 | 0 | Pure extraction for HOST_ONCE (S1); verified statement-for-statement against the base. No id change. |
| 6 | core/rows_read.zig | 7/10/66/11 | 0 | 0 | 0 | 10 | 0 | `piped`/`Piped` readers, mirror begin/end, and the `ready(s, at, bytes)` + `reuses` pair (S5). Inert: GLM has no disk store. |
| 7 | core/rows_write.zig | 7/20/37/9 | 0 | 0 | 0 | 18 | 2 | DISK_PUMP ring staging and DISK_LOCAL mirror filing throughout; 2 cosmetic module-move lines. Our `Rows` has no `pump`/`mirror` field at all. |
| 8 | core/rows_prefetch.zig | 6/9/23/13 | 0 | 0 | 0 | 7 | 2 | `threads`/`readEach` (DISK_READERS) and `Piece.window/k` for the mirror; 2 module-move lines. |
| 9 | core/template/template.zig | 5/9/22/7 | 0 | 9 | 0 | 0 | 0 | `More`, `Watch`, `split`, `rootMarked` (S1). With `watch == null` the render is byte-identical. |
| 10 | cuda/exl3_experts.zig | 4/20/129/14 | 0 | 0 | 6 | 14 | 0 | Superseded: `fusable`/`fusedBytes`/`fusedScratch`/item grouping are our item-plan PR in another shape (`exl3_experts.zig:80,104`, `runWith(..., ey, it)`), so those are the brief's "ignore" class. Unported: X3_NC, XROW, ROTEXPERT, FUSEDOWN, TF_EXL3_PIPE, TF_EXL3_SPLITK, TF_EXL3_DEC_ORDER, all env-gated off. |
| 11 | core/lane_host_fill.zig | 4/9/10/145 | 0 | 0 | 0 | 4 | 5 | `sliced()`/`slice_pending` is TF_GLM_OVN_FILL_SLICE_MS, a knob with no field in our tree. The 145 kept lines are the policy tests the fork moved to `lane_host_fill_policy_test.zig`, plus `pub` on `step`/`longStep`/`runnable`. |
| 12 | native/cuda_refusal.zig | 3/6/12/3 | 0 | 0 | 0 | 6 | 0 | GLM `--learn-conversations` wording and tests for the fork's GLM disk tier. Ours (`:62`) is the pin's refusal, which is what makes S5 and the rows_* disk hunks inert. |
| 13 | native/cuda.zig | 3/8/11/4 | 0 | 0 | 2 | 6 | 0 | `warmQuiet(F)`/`warmSpares`/`copyProposers` plumbing (the `warm_quiet` half is superseded by our 0025 `callbacks.warm_quiet`/`warm_alone`; the `warm_spares` half is D1's host flag), and `glm_disk` attach (unported). |
| 14 | server/hf_text.zig | 3/5/9/15 | 0 | 5 | 0 | 0 | 0 | `renderMore` + `Watch` + `kept_mod` vtable (S1). Ours at `:440` is the pin's `renderProvenanceGlobals`. |
| 15 | core/rows_io.zig | 2/8/37/2 | 0 | 0 | 0 | 7 | 1 | `Ring`, `staged_files`, `abandoned`, `freed` (DISK_PUMP); 1 module-move line. |
| 16 | core/template/eval.zig | 2/4/19/4 | 0 | 4 | 0 | 0 | 0 | `Ctx.watch`/`wrote`/`rootMarked` (S1); no-ops when `watch == null`. |
| 17 | core/lane_host_prefix.zig | 2/3/5/2 | 0 | 0 | 0 | 3 | 0 | `TENSORFOLD_PREFIX_WAIT_MIN_ROWS`, default 0, which makes the rewritten `least` (`:44` ours) arithmetically identical. |
| 18 | core/rows_select.zig | 2/4/5/2 | 0 | 0 | 0 | 4 | 0 | The `reuses` capacity rule, S5. Our `moot` gate from 0006 is already the fork's line. |
| 19 | core/tokenizer/memo.zig | 2/3/4/2 | 0 | 3 | 0 | 0 | 0 | S3, with the fork's measured 0.23 vs 2.1 ms. Three lines to port. |
| 20 | core/rows_write_sync.zig | 2/2/2/2 | 0 | 0 | 0 | 0 | 2 | Module move only (`@import("lanes").rows_image`, `.rows_file`). |
| 21 | native/cuda_disk.zig | 1/3/51/2 | 0 | 0 | 0 | 3 | 0 | `TF_GLM_OVN_DISK_CARRY_SALT`, `carryOf`, and that feature's fake-device test. |
| 22 | core/template/access.zig | 1/2/17/1 | 0 | 2 | 0 | 0 | 0 | S4 `strIndex` plus its equality fuzz test. |
| 23 | cuda/tp_group.zig | 1/6/8/1 | 0 | 1 | 0 | 5 | 0 | The world gate belongs to S2; `openPrx`/`prx` fields are unported. |
| 24 | native/cuda_startup_phase.zig | 1/3/7/1 | 0 | 0 | 1 | 2 | 0 | `serve(h, F, ...)` + `snaps.warmQuiet(F)` is our 0025 in another shape (`:37` `callbacks.warm_quiet`); `warm_spares` is D1's; `copyProposers` is unported (no GLM `copyProposers` in our tree, so our pin-side `LaneHost.proposers` at `lane_host.zig:42` stays null, i.e. not an inert-wiring defect). |
| 25 | core/lane_job.zig | 1/1/6/1 | 1 | 0 | 0 | 0 | 0 | **D1**: `Job.spares()` and the guarded `keepBornFrame`. |
| 26 | native/cuda_family_memory.zig | 1/1/6/1 | 0 | 0 | 0 | 1 | 0 | `later_bytes` in `learnBytes`; no family in our tree declares `later_bytes` (`grep` empty), so inert. |
| 27 | server/chat.zig | 1/2/4/1 | 0 | 0 | 0 | 2 | 0 | `cache_salt` (fork sha 639d426cc); `server/cache_salt.zig` does not exist in our tree. |
| 28 | core/lanes/depth.zig | 1/2/2/1 | 0 | 0 | 0 | 2 | 0 | `full_depth` (TF_GLM_OVN_DEPTH_FULL), default false; our `free_shared_test.zig:189` records "`full` (shared_depth_full) is not ported" as a deliberate choice. |
| 29 | core/lanes/engine.zig | 1/2/2/1 | 0 | 0 | 0 | 2 | 0 | `shared_depth_full` and `shared_copy_width` wiring, both default false. |
| 30 | core/lanes/windows.zig | 1/1/2/1 | 0 | 0 | 0 | 1 | 0 | TF_GLM_OVN_SHARED_COPY width, default false: `own` reduces to `e.alone`, the pin's expression. |
| 31 | core/rows_verify.zig | 1/2/2/1 | 0 | 0 | 0 | 1 | 1 | Mirror verify hook (DISK_LOCAL) and one module-move line. |
| 32 | core/lanes/open.zig | 1/1/1/1 | 0 | 0 | 0 | 1 | 0 | `e.cfg.first_tree`, default true, so identical to the pin's unguarded read. Our 0007 `batchable` change produced no leftover. |
| 33 | core/lanes/open_first.zig | 1/1/1/1 | 0 | 0 | 0 | 1 | 0 | Same `first_tree` gate, same default. |
| 34 | core/prompt_cache_policy.zig | 1/1/1/1 | 1 | 0 | 0 | 0 | 0 | **D1**: `return best orelse if (s.spares_only) null else oldest;` at our `:29`. |
| 35 | server/model_text.zig | 0/5/20/0 | 0 | 5 | 0 | 0 | 0 | `Kept`, `Pieces`, `stop`, `history`, `cut` and the three vtable hooks (S1). |
| 36 | build/server.zig | 0/1/13/0 | 0 | 1 | 0 | 0 | 0 | The `prompt-bench` step that produced S1's numbers; worth porting first if S1 is attempted. |
| 37 | cuda/root.zig | 0/2/11/0 | 0 | 0 | 0 | 2 | 0 | Module and test registration for `roce_rails`, `roce_verbs`, `prx*`. |
| 38 | core/lanes/config.zig | 0/5/8/9 | 0 | 0 | 0 | 4 | 10 | `first_tree`, `shared_depth_full`, `shared_copy_width` unported. The 9 kept lines are a false positive: our cost-table loop is already inside `if (!m.free_shared)` exactly as the fork's, only re-indented from the base. |
| 39 | core/lanes/fake.zig | 0/1/8/0 | 0 | 0 | 0 | 0 | 1 | Test-only `Fake.swung()`/`swingChances` for the probabilities work. |
| 40 | native/cuda_options.zig | 0/2/7/0 | 0 | 0 | 0 | 2 | 0 | `--parallel` reaching a family that reads `parallel`; GLM has no such field in our tree. |
| 41 | core/lanes/lanes.zig | 0/2/6/0 | 0 | 0 | 0 | 2 | 0 | Exports for the disk tier (`rows_file`, `rows_image`, `disk_readers`, `carry_*`) and the `shared_depth_test` import. |
| 42 | server/messages.zig | 0/4/6/0 | 0 | 4 | 0 | 0 | 0 | `Args` memo so tool arguments are parsed once (S1's third component). |
| 43 | server/root.zig | 0/3/6/0 | 0 | 2 | 0 | 1 | 0 | `pub` exports for the bench and the HOST_ONCE tests (S1); `cache_salt.zig` import is unported. |
| 44 | core/contract/glm_cuda_records.zig | 0/2/5/0 | 1 | 0 | 0 | 4 | 0 | **D2** `df_sumw`; the four `tf_glm_chunks_seg*` records are for glue kernels absent from our tree (`grep` finds no `tf_glm_chunks_seg16`). |
| 45 | core/kv_pool.zig | 0/1/4/0 | 0 | 0 | 0 | 1 | 0 | `takeFree`, called only from the fork's `families/glm/cuda_lineage.zig:258` (TF_GLM_OVN_LINEAGE); no such file or caller in our tree. |
| 46 | core/lane_host_rows.zig | 0/1/4/0 | 0 | 0 | 0 | 1 | 0 | `idleMs` (1 ms while a DISK_PUMP save waits); its only caller is the fork's `lane_host.zig:550`, and `r.pump` cannot be non-null for us. |
| 47 | build/cuda.zig | 0/3/3/1 | 0 | 0 | 0 | 2 | 2 | PRX/RoCE host test step; the kept line is the `rows_host.tests` signature before the lanes-module parameter. |
| 48 | core/prompt_cache.zig | 0/4/3/1 | 1 | 0 | 0 | 0 | 3 | **D1** field. The `:340` line is ours with an extra `n <= prompt.len` conjunct (`prefix.starts` already rejects that case, so identical); the test-block hunk is wiring our port moved to `engine_api_test.zig:12-34`, all 14 files still imported. |
| 49 | server/cortheon/fuzz.zig | 0/1/3/0 | 0 | 0 | 0 | 0 | 1 | Test-only tolerance helper `linear()`. |
| 50 | core/lane_stream.zig | 0/2/2/0 | 2 | 0 | 0 | 0 | 0 | **D1**: the two `store.spares_only` lines around the lookup; our surrounding code is the fork's verbatim. |
| 51 | server/server.zig | 0/2/2/0 | 0 | 0 | 0 | 2 | 0 | `host_once` field and its env read; the knob only adds S1's early stop. |
| 52 | build/cuda_kernels.zig | 0/1/1/0 | 0 | 0 | 0 | 0 | 1 | False positive and a fork defect: the fork lists `l2pf` twice (its lines 165 and 166); ours has the single correct entry at `:165`. |
| 53 | core/lanes/stream.zig | 0/1/1/0 | 0 | 0 | 0 | 1 | 0 | `slice_pending` field for FILL_SLICE_MS. |
| 54 | core/prompt_cache_index.zig | 0/1/1/0 | 0 | 0 | 1 | 0 | 0 | The fork keeps both the old `prompt[n-1] != ...` pair and the new `prefix.ends`; ours at `:12` computes the same predicate once (`prompt_prefix.zig:44-49`). |
| 55 | cuda/kernels.zig | 0/1/0/2 | 0 | 0 | 0 | 0 | 2 | False positive: the fork still declares `l2pf` and `l2pace` (its lines 89-90), ours at `:112-113`; only their position moved. |

Totals by class across the group's 142 rewritten-and-left hunks and 240 hunks: DEFECT-CANDIDATE 5 hunks (4 of them one defect), SPEED-LEAD 63, SUPERSEDED 10, UNPORTED-FEATURE 134, COSMETIC 32.

---

## 4. What I did not check, and why

- **Runtime proof of D1.** The audit is read-only and no build or serve was run, so the eviction is derived from the code path and the fork author's own description, not observed. The cheap confirmation when someone can run it: with `TF_GLM_OVN_REPLY_PREFILL=1`, two conversations and a cache budget that holds two states, watch `Store.counts.evicted` and B's `at` across A's warm turn.
- **Whether our TP=3 serve already sets `TF_GLM_ROCE_MULTI=1`, `TF_TP_MASTER` and `TF_TP_KERNEL_IMAGE`.** That is serve environment, not repo state, and it decides whether S2 is a large lead or a duplicate route. I could not read it without ssh.
- **The size of S2.** No fork commit gives a figure for the worlds 2-4 gather, and I did not estimate one.
- **Files outside my 55.** `lane_host.zig` (the other half of D1) is D-tests'; `families/glm/cuda_snapshot_*.zig` (the kept-state bytes and page rounding the brief mentioned under kv_pool/snaps) are A-step-state's; `cuda_prompt_pair.zig` is A-step-state's. I messaged LeftoverTests with the `lane_host.zig` detail rather than editing or re-classifying their file.
- **`native/cuda_kv_pool.zig` and `native/cuda_snaps.zig`** carry zero leftover hunks in the whole instrument run, so there was nothing to classify; I verified that rather than assuming it.
- **Pin-side provenance of each `fabric/tp` file.** I established that the pin's `cuda_roce_multi.zig` exists and is wired, which is what the supersession claim needs, but I did not audit `fabric/tp/roce_multi.zig` itself for parity with the fork's gather.