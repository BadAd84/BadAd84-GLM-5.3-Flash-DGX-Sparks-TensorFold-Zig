# Group B (`B-forward-kernels`) leftover audit

Instrument rerun per file against `work/parity/tree`; every claim below was checked by opening our file, the pin's file (`work/pin/tree`) and the fork blob (`git show fork-ssh/ovn-up:<path>`). 46 files, 348 hunks.

---

## 1. DEFECT-CANDIDATES

### D1. `TF_GLM_OVN_ONEPASS_PIPE` carries the pre-fix DECODE scale: the pipeline's attention output is garbage

* ours: `work/parity/tree/zig/kernels/cuda/glm_onepass_pipe.cuh:32` -> `const float s = r.s[i];`
* fork: `zig/kernels/cuda/glm_onepass_pipe.cuh:32` -> `const float s = __shfl_sync(0xffffffffu, r.s[i], 0);`
* fork commit `dd426c1a1` "glm: fix the onepass-pipe DECODE scale (per-lane broadcast), add base and reset checks" (2026-10-31).

What goes wrong: `convert_pipe<DECODE=true>` folds the per-row FP8 scale into the value in every lane, but `raw_load` (shared with the production one-pass) writes `r.s[i]` only in lane 0; lanes 1..31 hold 1.0. Only dims 0-15 get the scale, dims 16-511 are unscaled, which corrupts the softmax. The fork's own GPU run (onp1, spark4, TP=1) measured count-1 rows matching to dim 15 and differing from dim 16 on, and multi-key rows wrong by 100-500x.

Reached by: `TF_GLM_OVN_ONEPASS_PIPE=1` on the prompt path, via `cuda_dsa_block.zig:158` -> `onepass.runPipe(...)` when `onepass.takesExact(prompt, c.ls, l.heads, l.lw, rows)` holds, i.e. FP8 latent cache (`c.ls != 0`) and a 32-head block. Not the default path (knob defaults off). Patch: **0017-onepass-pipe** (ported at `a63e56649`, before the fix existed).

Confidence: **high**. Our file is the pre-fix blob verbatim, the fork commit names the mechanism and the symptom, and our tree ships the `exact` variant as `Set.onepass_pipe` (`cuda_glue.zig:9`, `cuda_forward.zig:229`), so the knob reaches the broken path.

Minimal port, one line in `zig/kernels/cuda/glm_onepass_pipe.cuh`:

```
-        const float s = r.s[i];
+        const float s = __shfl_sync(0xffffffffu, r.s[i], 0);
```

(and the comment above `convert_pipe`: `// DECODE on: default decode (scale folded into the value); raw_load loads the scale only in lane 0, so broadcast it.`)

---

### D2. `TF_GLM_OVN_ONE_CHUNK`'s KDA capture hook was never called: the marks it keeps hold uncaptured state

* ours: `work/parity/tree/zig/src/families/glm/cuda_forward.zig:292` (the `.kda` arm of `Forward.mixer`) goes straight to `kda_block.bodyProfile(...)`.
* ours: `work/parity/tree/zig/src/families/glm/cuda_one_chunk.zig:179` defines `pub fn kdaBlock(f, r, k, li, rows, out, fronted, cap)`, and `grep -rn kdaBlock zig/` returns **that definition only**. No caller anywhere in the tree.
* fork: `zig/src/families/glm/cuda_forward.zig:331` ->
  `if (b.prefill) if (f.one) |cap| return @import("cuda_one_chunk.zig").kdaBlock(f, r, k, li, rows, out, fronted, cap);`

What goes wrong: with the knob on, `cuda_engine.zig:390` calls `one_chunk.enter(...)`, which sets `f.one = cap` (`cuda_one_chunk.zig:141`) and stages the mark buffers through `keep.before(...)` (`:144`); `cuda_engine.zig:440` then calls `leave(...)`, which drives `snapshots.gate` per mark, and `cuda_snapshots.zig:132` routes the keep to `one_chunk.keep.keepAt`. The only producer of the per-mark KDA state is `keep.layer(cap, ...)`, called exclusively from `kdaBlock` (`cuda_one_chunk.zig:207`). Because `mixer` never enters `kdaBlock`, `keep.layer` never runs, so each mark is written out of the `Capture.rec`/`Capture.conv` slots that `keep.before` staged, not out of the state at the mark. A session resumed from an inside-chunk mark replays its KDA chain from the wrong recurrent state and conv window: wrong replies on exactly the resume the knob exists to make possible. The chunk's own live state is still correct (the pin's `bodyProfile` runs), so nothing fails loudly.

Reached by: `TF_GLM_OVN_ONE_CHUNK=1` plus a prompt chunk that contains a mark. Not the default path. Patch: **0011-one-chunk** (its header lists the ported surface and this hook is not in the list).

Confidence: **high**. The callee exists, compiles and is unreachable; `enter`/`leave`/`keepAt` are all wired.

Minimal port, in `zig/src/families/glm/cuda_forward.zig`, first line of the `.kda =>` arm of `mixer` (our tree has no `fronted`, so pass `false`):

```
             .kda => |k| {
+                if (b.prefill) if (f.one) |cap| return @import("cuda_one_chunk.zig").kdaBlock(f, r, k, li, rows, out, false, cap);
                 const cur = st.cur[li];
```

---

### D3. `TF_GLM_OVN_DRAFT_EDGE`, `_DRAFT_NOISE` and `_DRAFT_BETA`'s noise are dead knobs: the selector was left in the pin's form

* ours: `work/parity/tree/zig/src/families/glm/dflash_select.zig:55` -> `sc[m] = c[m].v + dot;` then `if (sc[m] > sc[best]) best = m;`
* fork: `zig/src/families/glm/dflash_select.zig:60-68`:

```
            sc[m] = c[m].v + k.edge * dot; // EDGE unset: 1.0, today's bits
            key[m] = sc[m];
            if (keyed) |s| { // pick score / T + noise g; chance softmax((score / T + g) / beta) with BETA, else of score
                const g_m = ovn.gumbel(s.seed, q.pos + @as(i64, @intCast(t)), c[m].id);
                sc[m] *= inv_t;
                key[m] = sc[m] + k.noise * g_m;
                if (k.noisy) sc[m] += g_m;
            }
            if (key[m] > key[best]) best = m;
```

  plus the preamble `zig/src/families/glm/dflash_select.zig:17-19` (`const k = &dr.knobs;`, `keyed`, `inv_t`) and the `ovn` import at `:2`.

What goes wrong: every other half of the feature is ported. `dflash_ovn.Knobs` carries `edge`, `noisy`, `noise` (`dflash_ovn.zig:46-48`), `Knobs.read` parses `DRAFT_EDGE`/`DRAFT_BETA`/`DRAFT_NOISE` (`:56-60`), `gumbel` exists (`:80`), `dflash_load.zig:173,201` fills `dr.knobs` and `dr.temp`, and `dflash.zig:96-103`'s `located()` fills `Req.pos`/`Req.sampling` with the doc comment "TF_GLM_OVN_DRAFT_NOISE's pick reads it". Nothing reads them: `grep -rn "gumbel|\.edge\b|knobs\.noise|\.noisy\b" zig/src/families/glm/` matches only `dflash_ovn.zig` itself. So `DRAFT_EDGE` and `DRAFT_NOISE` change nothing at all, and `DRAFT_BETA` changes only the chance softmax temperature (`dr.temp`, read at `dflash_select.zig:59`) without the Gumbel term it is defined by, which is a different quantity from production's `noisy_confidence`. An A/B of these knobs would read "no effect" and the lever would be retired on a false negative.

Reached by: `--drafter` plus any of the three knobs. Not the default path. Patch: **0004-draft-knobs**.

Confidence: **high** (both sides read, zero consumers found).

Minimal port, in `zig/src/families/glm/dflash_select.zig`: add `const ovn = @import("dflash_ovn.zig");` at the top, add the three preamble lines inside `select`, declare `var key: [TOPK]f32 = undefined;` beside `sc`, and replace the body of the candidate loop with the fork's nine lines quoted above. Nothing else in the file moves (the `k` -> `slot` rename at `:43` is cosmetic).

---

### D4. TP=3 logit gather still posts one `ncclBroadcast` a row a rank: `prompt_logprobs` past ~100 rows hangs

* ours: `work/parity/tree/zig/src/families/glm/cuda_structured.zig:11` -> `try e.smp.gather(e.stream, e.exchange(), e.spans, &.{...}, rows, e.smp.full.ptr);`
* ours: `work/parity/tree/zig/src/families/glm/cuda_sampler.zig:160-165` -> `Spread.post` loops `for (0..t.rows) |row| for (t.spans, 0..) |span, q| ncclBroadcast(...)`.
* fork: `cuda_structured.zig:11` passes `e.smp.stage.ptr, e.smp.full.ptr`; `cuda_sampler.gather` broadcasts one `[rows][span]` block a rank into a staging buffer and places it with one `cuMemcpy2DAsync`.
* fork commit `0a77dcd7d` "glm cuda: a logit gather broadcasts one block a rank, so TP=3 prompt_logprobs past ~100 tokens no longer hangs. Spread.post queued one ncclBroadcast per row per rank in one NCCL group; at TP=3 a 128-row prompt-logprob pass (381 broadcasts) never left ncclGroupEnd. Fixes #1559".

What goes wrong: on our serve (TP=3) a `prompt_logprobs` or structured-output pass of more than about 100 rows wedges inside `ncclGroupEnd`, which stalls the whole engine thread.

Reached by: the **default path** at world 3, any request with `prompt_logprobs` or a grammar over ~100 rows. This is a **pin defect the fork fixed**, not a port slip; I list it here because it is a live TP=3 hang and the hunk falls in my group.

Confidence: **high** for the mechanism and that our code is the unfixed form; **medium** that the exact row threshold is ~100 on our build (the fork measured 128 rows at TP=3).

Minimal port: commit `0a77dcd7d` in full. `cuda_structured.zig` is the one line in my group:

```
-    try e.smp.gather(e.stream, e.exchange(), e.spans, &.{.{ .rank = e.share.rank, .logits = logits }}, rows, e.smp.full.ptr);
+    try e.smp.gather(e.stream, e.exchange(), e.spans, &.{.{ .rank = e.share.rank, .logits = logits }}, rows, e.smp.stage.ptr, e.smp.full.ptr);
```

The substance (the `stage` buffer, `Spread.post`, `place`) is in `cuda_sampler.zig` and `cuda_prompt_logprobs.zig`, which belong to another group. **Cross-group: flagging for whoever owns `cuda_sampler.zig` (6 rewritten-and-left hunks there).**

---

## 2. SPEED-LEADS (default-on in the fork, absent from our tree)

### S1. FP8 latent keys fetched a tile ahead, in 8-byte loads (`450b9519c`)

* ours: `work/parity/tree/zig/kernels/cuda/glm_glue_attn.cuh:63-83` -> one `load_kv` lambda; its `if constexpr (FP8)` arm (`:71-83`) does eight single-byte global loads a slot and converts synchronously right after the previous tile was computed. `:100-102` `load_kv(0); commit(); load_kv(1); commit();`, `:196` `if (tile + 2 < tiles) load_kv(tile + 2);`.
* fork: `glm_glue_attn.cuh:72-160` -> split into `fetch(tile)` (one 8-byte `uint2` load of the codes plus the scale into `pre_c[]`/`pre_s[]` registers, `PER = KT * (LW/8) / 256` slots a thread) and `store(tile)` (converts from registers and writes `uint4` at a time into the free shared buffer), with `fetch(0); store(0); fetch(1); commit();` at entry and, inside the loop, `if constexpr (FP8) { if (tile + 1 < tiles) store(tile + 1); if (tile + 2 < tiles) fetch(tile + 2); }`.
* Fork's measured claim (commit message, nvcc 13.3 sm_121a): "with ~100 KB of shared memory a block is alone on its SM, so every gather's latency was exposed, while the BF16 path double-buffers by cp.async ... This is both the prompt's MLA stage (**~220 ms of a 2,048-row chunk**) and decode's (`chunks_16_fp8`). chunks_16_fp8 98 -> 126 registers, chunks_32_fp8 128 -> 163, no spills; both stay one block an SM. BF16 kernels unchanged." Bit-identical: "The conversion, rounding and math are unchanged, so the bits are too."

Why it applies to us: our serve runs 8-bit KV, so `tf_glm_chunks_16_fp8` / `tf_glm_chunks_32_fp8` are the DSA attention kernels on both the decode and the prompt path; the BF16 arm that already double-buffers is the one we do not use. This is the largest default-on prompt win in the group, and it also lands on the decode chunk kernel (below the 2.2 ms floor of the profile table you gave, so decode-side worth under ~2 ms a round; the prompt side is the big number).

Port: the FP8 half of `chunks_wide` in `glm_glue_attn.cuh`, hunks at fork lines 72, 85, 101, 134, 156, 241, plus the `int64_t c` parameter hoist (fork `:46`, `:59`) and the four wrapper call sites (`:266`, `:273`). The `pt`/`pstep` additions in the same commit range belong to the FP8-pages feature (U7 below) and are separable: pass `nullptr, 0` to keep our slab-only addressing.

### S2. The one-shot RoCE gather serves worlds two to four (`060465305`)

* ours: `work/parity/tree/zig/kernels/cuda/roce_gather.cu:88` -> `uint4* peer_out = out + (long long)(1 - rank) * packs;` (two ranks, hardcoded), one flag set, one receive slot.
* ours: `work/parity/tree/zig/src/cuda/tp_group.zig:75` -> `if (g.world != 2 or g.fast != null) return;`
* fork: `roce_gather.cu` gains `gather_body<LOADS_FIRST>` with `world`, `recv_peer_stride`, `flag_peer_stride`; `if (tid < n_hca * peers)` waits on every peer's flags; the shard loop runs `for (int p = 0; p < peers; ++p)` in rank order. `tp_group.zig:79` -> `if (g.world < 2 or g.world > roce.max_world_roce or g.fast != null) return;`
* Fork commit message: "Gather.init all-gathers every rank blob over the NCCL communicator and connects one queue pair per (peer, HCA) ... tp_group.openRoce drops its world==2 gate (max_world_roce=4)." No speed figure is given in that commit.

Why it applies to us: default-on. `roce.wanted()` returns true unless `TF_ROCE=0` (`work/parity/tree/zig/src/cuda/roce.zig:152-153`) and `cuda_native.zig:321` calls `own.group.openRoce(...)` unconditionally for GLM. At world 2 the pin therefore uses the RoCE one-shot gather for small all-gathers; at **world 3 it silently falls back to NCCL**, which is the `NCCL AllGather 3.1 ms` row of your profile (7.2% of the 42.8 ms round, two gathers a layer). This is the one default-on change in the group that lands squarely on the measured decode round.

Port: `roce_gather.cu` hunks at fork lines 87, 90, 109, 116, 124, 126, 146 (skip `copy_peers_ilp` at `:51`, which is `TF_GLM_OVN_ROCE_ILP`). The host side is `zig/src/cuda/roce.zig` (+184/-83) and `zig/src/cuda/tp_group.zig` (+4), **both outside my group**: flagging for the core/native lane. No receipt exists in the fork for TP=3, so this needs its own A/B before it is believed.

### S3. The EXL3 prompt experts take a whole chunk in one call (`0aec07b2f`)

* ours: `work/parity/tree/zig/src/families/glm/cuda_exl3.zig:130` -> `pub const chunk_rows = 1024;`
* fork: `cuda_exl3.zig:206` -> `pub const chunk_rows = @import("cuda_state.zig").prefill_rows;`
* Fork's measured claim: "chunk_rows was 1,024, so a prompt chunk ran the routed experts as two calls, and each call reads every expert's weights in 64-row tiles: with 288 experts and top-8 routing a call of 1,024 rows gives an expert ~28 rows (its tile 44% full) and **every expert is read twice a chunk**. One call of 2,048 rows gives ~57 (89%) and reads each once. The prompt kernels run the full K with no split per row, so a row's bits do not depend on the call's rows. The fused prompt scratch grows by **~270 MiB a rank**. Decode windows are unaffected."

One line, bit-identical, costs 270 MiB a rank. Loop uses are at `cuda_exl3.zig:140,148,164,168-169`.

### S4. Prompt chunks of 4,096 rows (`85df341ed`)

* ours: `work/parity/tree/zig/src/families/glm/cuda_state.zig:19` -> `pub const prefill_rows = 2048;` (`index_ring = 2 * prefill_rows` at `:27`).
* fork: 4,096, with everything that is a chunk following it: the prompt buffers, `cuda_exl3.chunk_rows`, the index rings, the pair's twin and second-chunk floor, the follower's whole-pass steps, the batched-prompt pass, the image map, `dflash.TAP_ROWS`, the prompt cache's pass rule. Explicitly **not** following it: `snap_min_rows` (stays 2,048), the `--learn-conversations` probe, DFlash2's `MAX_CTX` ingest piece, `TF_GLM_INDEX_SPLIT`'s default position, the dense limit and `dflash.WIN`.
* No tok/s figure in the commit; the mechanism is half as many chunk boundaries a prompt, and it composes with S3 (a 4,096-row expert call).

Note for the record: this is the commit the ring fixes came from. Its last paragraph is exactly what patch **0042** ported ("a pair at a start off its pool could write one to three rows past the index ring after State.ready rebased it (ringsAgree now requires the pair to fit from the rebase), and State.ready/readyMtp refuse such a pass (error.PastRing)"). So 0042 took the guards and left the size change, which is the same shape as the defect class this audit exists for, except that here the remainder is a speed lever rather than a bound. Most of the change is in `cuda_state.zig` (another group); in my group it touches `dflash.zig` (TAP_ROWS) and `dflash_load.zig`.

### S5. A sparse FP8 key's page offset as a 32-bit remainder (`1ccdb486e`)

Default-on, but only reachable with **FP8 KV on pages**, which our tree refuses (`cuda_start.zig:51` -> `if (kv8) return error.Fp8OnPages;`, `cuda_latent.zig:96` -> `if (t.pt != 0) return error.Fp8OnPages;`). Measured by the fork at "a 2,048-row sparse prompt chunk's MLA stage took 525 ms against ~226 ms on the slab" before the fix. Listed so it is not lost: it is a prerequisite of U7, not a lead on its own.

### Knob-gated levers that aim at the hottest kernels (not default-on, so formally UNPORTED-FEATURE)

Recorded here rather than buried in the table, because `tf_exl3_grouped_1` is 19.0 ms of the 42.8 ms round and the fork has five levers on it that we do not carry at all:

| lever | fork commit | fork's claim | our state |
|---|---|---|---|
| `TF_EXL3_DEC_ORDER` (`GroupedArgs.ord`, grid swap) | `46b46550f` | "MiaAI recipe PR #95, **+1-3% decode** there"; unset is byte-for-byte today's launch | `exl3_grouped.cuh:23` has no `ord`; `exl3_experts.cu:21,25,29` pass `blockIdx.x, blockIdx.y` |
| `TF_GLM_OVN_X3_NC=1\|2\|w` (one-word loads, `nc_body`) | `7d41fa9b7`, `ca8479639` | - | absent (`exl3_ovn.cuh` not in our tree) |
| `TF_GLM_OVN_X3_FUSEDOWN` (fused down epilogue) | `7d41fa9b7` | - | absent |
| `TF_GLM_OVN_X3_XROW` (rotate once a row) | `7d41fa9b7` + `tf_exl3_ovn_rot_rows` | - | absent |
| `TF_GLM_OVN_X3_ROTEXPERT` (per-expert share rotation) | `95a3e51cb` | bit-exact | absent |

`TF_EXL3_PIPE` (`aa44a6285`, `tf_exl3_grouped_p0/p1/p2`) is **SUPERSEDED** for us: see the table note on `exl3_experts.cu`.

---

## 3. Per-file table

Counts are hunks, not lines; `D`/`S`/`SUP`/`UNP`/`COS` are DEFECT-CANDIDATE / SPEED-LEAD / SUPERSEDED / UNPORTED-FEATURE / COSMETIC.

| file | hunks | D | S | SUP | UNP | COS | note |
|---|---|---|---|---|---|---|---|
| `glm/cuda_forward.zig` | 35 | 1 | 0 | 3 | 29 | 2 | D2 (one_chunk hook). Rest: `l2pace`, `moe_side`, `slices`, `rotlayer`, `DECODE_SHARD`, `PEER_FIRST`, `FRONTS`, `SIDE_PRIO`, `PRX`, `SPLIT_MIN`, `SHARED_SIDE`, moe `Ovn`. `pieced`/`run` prologue moves are the pin's layout. |
| `glm/cuda_exl3.zig` | 26 | 0 | 1 | 0 | 25 | 0 | S3 `chunk_rows`. Rest is `X3_ROTEXPERT` + the `ITEMS` item-plan surface the brief says to ignore. |
| `cuda/glm_glue_attn.cuh` | 17 | 0 | 9 | 0 | 4 | 4 | S1 (FP8 tile-ahead). `pt`/`pstep` on the FP8 wrappers is U7; `merge_body`/`scores_body` are namespace refactors for kernels we do not carry. |
| `glm/cuda_weights.zig` | 10 | 0 | 0 | 0 | 9 | 1 | `EXPERT_ROTATE` (`share.at(c, i)`) and `DROP_MTP` only. |
| `cuda/roce_gather.cu` | 9 | 0 | 8 | 0 | 1 | 0 | S2. The `copy_peers_ilp` helper is `TF_GLM_OVN_ROCE_ILP`. |
| `glm/cuda_dsa_block.zig` | 13 | 0 | 0 | 4 | 9 | 0 | `headBlock` sites are ours as `headBlockOf` (0031); the `onepass_pipe` hook is present at `:158`. Rest: `DECODE_SHARD`, `FRONTS` row slicing, prof variants, the FP8-pages `page_rows` row width (`:278`, inert while `cuda_start` refuses FP8 on pages). |
| `cuda/exl3_grouped.cuh` | 10 | 0 | 0 | 0 | 10 | 0 | `ord` + the `OvnTail` X3 family (`exl3_ovn.cuh` absent). |
| `glm/cuda_kda_block.zig` | 9 | 0 | 0 | 0 | 9 | 0 | `FRONTS` (`projectRows`/`restProfile`/`chainProfile` split) and the `cuda_l2pf` -> `cuda_l2pace` rename. Our `o_site` still forks the pin's `TF_GLM_L2PF`. |
| `glm/cuda_forward_pieces.zig` | 14 | 0 | 0 | 1 | 13 | 0 | `piecedLayers`, `FRONTS`, `PEER_FIRST`, `PRX` zero-copy, `glueOwn`. Our `partials`/`shareGlued` are the pin's. |
| `glm/cuda_latent.zig` | 17 | 0 | 0 | 2 | 7 | 8 | `headBlock`/test are ours as `headBlockOf`. `LATENT_MMA`, `SEG_PASS`, FP8 pages unported; the `attentionProfile`/`mark` wrappers are the mla profile split. |
| `glm/cuda_mlp.zig` | 7 | 0 | 0 | 0 | 7 | 0 | All `bodyRows(lo, hi)` row slicing for `FRONTS`. `swigluReduceB16` is already at `cuda_mlp.zig:58`. |
| `glm/cuda_glue.zig` | 17 | 0 | 0 | 1 | 16 | 0 | `HC_ROWS`/`HC_DEC`, `TOPK_SUM`, `COMBINE_SY`, `SNAP_GATHER`, `LATENT_MMA`, `SEG_PASS`, `PK8`, `DECODE_SHARD` loader fields plus `hcPostAt`/`hcRowAt`. `routerSlices` is our `router()` at `:248-263`. |
| `glm/cuda_moe.zig` | 8 | 0 | 0 | 0 | 8 | 0 | `Ovn` (`COMBINE_SY`, `TOPK_SUM`, `SHARED_FIRST`) and the `run`/`route`/`sharedFront`/`fillTail` split it needs. |
| `glm/cuda_shard.zig` | 8 | 0 | 0 | 0 | 8 | 0 | `EXPERT_ROTATE` (`Share.at`, `widest`) and `TF_GLM_KDA_ALIGN` (`kdaUnit`, default 1). |
| `cuda/exl3_experts.cu` | 6 | 0 | 0 | 1 | 5 | 0 | `tf_exl3_grouped_p*` (TF_EXL3_PIPE) is **superseded**: our `exl3_experts.cu:14-18` already sets `constexpr int GROUPED_LOAD = tf_exl3::AHEAD;` for `__CUDA_ARCH__ >= 1200`, and GB10 is sm_121, so the standard entry points already walk a tile ahead. Rest: `ord`, `ovn_walk/walkw/nc1/nc2`, `ovn_rot_rows`, `exl3_prompt_ovn.cuh`. |
| `cuda/glm_glue_latent.cuh` | 5 | 0 | 0 | 0 | 3 | 2 | `lat_write_fp8` page addressing (U7); the `glm_latent` namespace wrappers are structural. |
| `glm/dflash_select.zig` | 5 | 4 | 0 | 0 | 0 | 1 | D3. The `k` -> `slot` capture rename is cosmetic. |
| `glm/cuda_sparse.zig` | 7 | 0 | 0 | 3 | 3 | 1 | `PK8` unported. Our `ovnListBytes` at `:60-66` already carries the `POOLS32` scratch term and the split tables. |
| `cuda/exl3_prompt.cuh` | 3 | 0 | 0 | 0 | 3 | 0 | `XK` template parameter for the prompt OVN variants. |
| `glm/cuda_copy_policy.zig` | 3 | 0 | 0 | 0 | 3 | 0 | `TF_GLM_OVN_SHARED_ROWS` (32..64) sizing. |
| `glm/cuda_ranks.zig` | 13 | 0 | 0 | 0 | 13 | 0 | Settings/digest words for `SPLIT_MIN`, `SHARED_ROWS`, `SHARED_BS_ROWS`, `ovn_comms`, `moe_owners`. `index_split = 2048` already matches (`:22`). |
| `cuda/glm_glue_rows.cuh` | 5 | 0 | 0 | 1 | 4 | 0 | `rank_sum`'s rotated start word (`EXPERT_ROTATE`), `tf_glm_combine_sy`, `tf_glm_snap_copy`. The combine/top-1 block is ours from 0035. |
| `cuda/glm_glue_index.cuh` | 3 | 0 | 0 | 0 | 1 | 2 | Bodies split into `glm_index::*_body` so `PK8`/fused kernels can call them. |
| `glm/cuda_forward_pair.zig` | 3 | 0 | 0 | 0 | 3 | 0 | `partials(..., own_later)` and `glueOwn` (PEER_FIRST / PRX). |
| `glm/cuda_start.zig` | 2 | 0 | 0 | 0 | 2 | 0 | U7: fork's `auto` is `world >= 2` with FP8 allowed on pages; ours is `world >= 2 and !kv8` plus `error.Fp8OnPages`. Coherent with `cuda_latent.zig:96` and `cuda_dsa_block.zig:278`, so inert, not a defect. |
| `glm/dflash.zig` | 4 | 0 | 0 | 2 | 1 | 1 | `promptRun` (`:400-406`) keeps `keep_from` inline; identical to `ingestsNone`, which we also have at `:395` and use from `cuda_prompt_pair.zig:74`. `STEP_ROWS = 32` is the `SHARED_ROWS` lever. |
| `glm/cuda_proj.zig` | 1 | 0 | 0 | 0 | 0 | 1 | A test's row list gains `prefill_rows`. |
| `glm/cuda_structured.zig` | 1 | 1 | 0 | 0 | 0 | 0 | D4. |
| `glm/dflash_block.zig` | 2 | 0 | 0 | 1 | 1 | 0 | `draftHead` (DROP_MTP). The `onepass`/`mlpsplit` block is ours at `:176-184`. |
| `glm/dflash_load.zig` | 2 | 0 | 0 | 0 | 1 | 1 | `draftHead` (DROP_MTP). `rawBytes(bits, world)` already takes the world max (`dflash.zig:49-53`), so `ef522a2e1` is in the pin. |
| `glm/cuda_forward_glue.zig` | 1 | 0 | 0 | 0 | 1 | 0 | `rotlayer.word`/`first`, `glueRowsAt`, `hcRowAt`/`hcPostAt` row forms. |
| `cuda/glm_glue_moe.cuh` | 4 | 0 | 0 | 3 | 1 | 0 | `tf_glm_topk_sum` unported; the swiglu restructure is ours as the `_pdl` pair (0022). |
| `glm/cuda_index.zig` | 5 | 0 | 0 | 0 | 5 | 0 | `PK8` scorer arm only. |
| `cuda/glm_glue.cu` | 2 | 0 | 0 | 0 | 2 | 0 | Includes for six kernel headers we do not carry (`glm_glue_hc_rows`, `attn_seg`, `latent_mma`, `shard`, `seg`, `pk8`). |
| `glm/cuda_mtp_load.zig` | 1 | 0 | 0 | 0 | 1 | 0 | `into(..., draft_only)` / `draftHead` (DROP_MTP). |
| `glm/cuda_q4.zig` | 3 | 0 | 0 | 0 | 0 | 3 | `module`, `loadF32`, `launchGroup`, `many_rows` are all present (0004); only the literal field order differs. |
| `glm/cuda_onepass.zig` | 1 | 0 | 0 | 1 | 0 | 0 | `takesExact` uses `headBlockOf` (0031) at `:106`. |
| `glm/dflash_ovn.zig` | 1 | 0 | 0 | 0 | 1 | 0 | `DRAFT_FIXED` knob (`e8192b5cc`), not ported by 0004. |
| `cuda/glm_index.cu` | 1 | 0 | 0 | 0 | 1 | 0 | `glm_index_pk8.cuh` include. |
| `cuda/glm_onepass_pipe.cuh` | 1 | 1 | 0 | 0 | 0 | 0 | D1. |
| `cuda/glm_ops.cu` | 2 | 0 | 0 | 1 | 1 | 0 | `glm_ops_seg.cuh` include unported; `dsa_tokens` body shape is ours (`:32-43`, with the `_i32` POOLS32 twin). |
| `glm/cuda_kda_seg.zig` | 1 | 0 | 0 | 0 | 0 | 1 | Our `Seg` is at `:13`, identical fields, not `pub`. |
| `glm/cuda_tile.zig` | 1 | 0 | 0 | 1 | 0 | 0 | `TF_GLM_KDA_DUMP` is at our `cuda_tile.zig:66` inside the pad (0024 moved it). `bbe001d58`'s split-rest padding is present at `:84-102`. |
| `cuda/glm_glue_bmm.cuh` | 3 | 0 | 0 | 0 | 0 | 3 | Kept-only; our file carries `router_tile<false>`, `tf_glm_router_tile_pdl` and `router16<3|4>` at `:312-498`. Matcher artifact of the fork's namespace move. |
| `cuda/glm_glue_hc.cuh` | 5 | 0 | 0 | 0 | 0 | 5 | Kept-only, zero missing lines: the fork's `HC_ROWS`/`HC_DEC` kernels live in a new file `glm_glue_hc_rows.cuh` that our tree does not have at all (see U4). |
| `glm/cuda_mm.zig` | 3 | 0 | 0 | 0 | 0 | 3 | Kept-only; our `window()` at `:222-268` already holds the `wide`/`cluster`/`dectile` hooks (0020). Matcher artifact. |
| **total** | **348** | **7** | **18** | **25** | **216** | **39** | 43 hunks are the paired restructures counted on both sides above; no file was left unfinished. |

---

## 4. What I did not check, and why

* **The host side of S2.** `zig/src/cuda/roce.zig` (+184/-83 in `060465305`) and `zig/src/cuda/tp_group.zig` are outside my file list. I verified only the gate (`tp_group.zig:75` in our tree) and the default (`roce.zig:152`, `cuda_native.zig:321`). Whether `roce.Gather.init` can be lifted to three ranks on our fabric is that lane's call.
* **The host side of D4.** `cuda_sampler.zig` and `cuda_prompt_logprobs.zig` carry the real fix; they belong to another group. I read our `Spread.post` to establish the defect is present, nothing more.
* **`cuda_state.zig`** (18 rewritten-and-left hunks, the largest single file of the whole run) is in another group, and S4 lives mostly there. I read only `prefill_rows`/`index_ring`.
* **The `ITEMS` / 9-slot item-plan hunks in `cuda_exl3.zig`** (`769c8cfca`, `e95d31f81`, `f9209395e`) are the separate upstream PR the brief says to ignore; I counted them as UNPORTED without reading their semantics. If that PR is landing, `exl3.bf16Slots` at `cuda_moe.zig:147` and `scratchBytes(..., o)` go with it.
* **No GPU work.** Every speed claim above is the fork author's own measurement quoted from its commit, or a mechanism I can point at in the source. S2 in particular has **no** TP=3 receipt anywhere in the fork; S1, S3 and S5 have figures but none taken on a 3-Spark GLM serve. None of the four should be quoted as ours until it has its own A/B.
* **I did not run the build, the tests or the mutant suite** (read-only assignment), so the minimal ports in section 1 are written against the current line shapes and are untested.