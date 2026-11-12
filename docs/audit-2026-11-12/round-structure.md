# round-structure.md - production's one-stream decode round against ours at v1.2.7

Lane `RoundStructure`, 2026-11-12. Read-only: code reading, plus today's cell results and production's boot log read
on spark1 over SSH. No build, no test, no GPU work. This file is the only one written.

## Sources and conventions

- **Production code**: `C:/Users/Adam/Gitea/work-recon/pyprod/tensorfold/`. It carries `TF_GLM_KV_SHARD`,
  `TF_GLM_DRAFT_WIDE`, `TF_GLM_EXPERT_ROTATE` and OTS comments through 0126, which matches the served image
  `tensorfold-glm53:v110hunt4-shard`. `P:<file>:<line>` is `families/glm5_next/cuda/<file>`, `Pc:` is
  `tensorfold/cuda/`.
- **Production settings**: `GLM-5.3-Flash-DGX-Sparks-TensorFold-Python-TP3/scripts/glm53/v110/v110ots.env` (`ENV:`).
  **Production measurements**: that repo's `int-docs/` (`PN:`).
- **Ours**: tag `v1.2.7` (commit `93a2e93ecebf`), read with `git -C work/parity/tree show v1.2.7:<path>`. `Z:` is
  `zig/src/families/glm/`, `ZL:` is `zig/src/core/lanes/`.
- **Our measurements**: `docs/OVERNIGHT-2026-11-12.md` (`ON:`), `docs/PATCH-EVAL.md` (`PE:`), and the fork's
  `C:/Users/Adam/Gitea/ai-engine/docs/` (`AE:`). The fork's drafter and step protocol are v1.2.7's unless a row says
  otherwise, so its receipts are quoted as "measured on the fork", never as measured on v1.2.7.
- **Today's cells, on spark1** (read over SSH, unchanged): `~/bench/<cell>/P<n>.jsonl` from `scripts/streams.py`
  (`B:<cell>`), production's boot log of the profile run `~/bench/prodprof/log-P1.txt` (`BL:`), and our rank 0 log of
  the profiled cell `~/bench/v127-prof/r0-P1.log` (`BR:`). `prodwin` and `prodprof` are production; `v127` is v1.2.7
  as built, `v127-pad` adds `TF_GLM_KDA_PAD=1`, `v127-prof` adds `TF_GLM_PROF` to that; `roce1-pad` and
  `roce1-pad-nccl` are the fork's stack through 0042 plus the RoCE gather (`ON:126-128`), on and off, with the pad,
  and `roce1-nccl` is the off arm without it. Every cell is one prose prompt (`scripts/streams.py:32-33`), 400 tokens,
  greedy (`ON:179`), three requests; `pyprod` is production's run of 2026-11-11 at one to eight streams (`ON:16`).
- **A capture of our pad stack at one stream** (read-only `sqlite3` queries on spark1): `~/nsys/f5-pad-p1.sqlite`,
  rank 0 of the stack through 0041 on the old pin with the KDA pad, 2026-11-12, the capture behind `ON:103-121`
  (`NS:`). Its window is the 154 drafter passes: 153 rounds in 6,758 ms (44.2 ms a round, 3.92 rows); stream 18 is
  the main stream, 20 the L2 prefetch. Its draw reads each row on its own (a 48-byte read 3.93 times a round, with a
  gather and a synchronize each), where v1.2.7 reads all rows once (`Z:cuda_engine_pick.zig:14-42`, called at
  `Z:cuda_engine.zig:534`), so it has about 2.9 more synchronizes and gathers a round than v1.2.7.
- **MiaAI recipe (Zig engine 1.1.9 + patches)**: `work-recon/GLM-5.3-Flash-DGX-Sparks-1104/patches/engine/` (`MIA:`).
- Every number is labelled **measured** (where), **derived** (arithmetic shown) or **estimate**.

## 0. Findings in short

1. **Production's served one-stream round never touches the one-stream graphs.** With `TF_GLM_KV_SHARD=1`
   (`ENV:48`) the decoder forces the lone-stream path off (`P:multi.py:344-354`, applied at `P:multi.py:869`; an
   explicit `TF_GLM_MULTI_LONE=1` is refused, `P:engine.py:1505-1508`). Every round, one stream included, goes
   through `BatchedVerify`: one CUDA graph per total row count, then one graph for the commit and the drafter's
   context update. Its boot log says so: "lone stream on the one-stream graphs off" (`BL:`). The start-up line's two
   columns (`P:multi.py:1120-1150`) time different graph sets: the one-stream column the dense graphs
   (`P:graphs.py:56-59`, no token selection), the batched column the set that always runs the token selection
   (`P:verify.py:180-181,225`). A window with no row at position 2,051 or later (`SPARSE_FROM`, `P:sparse.py:14-18`),
   which is every window of the prose cell, replays a third set, `dense_graphs` (`P:verify.py:23-26,343-346`), that no
   boot line times. The measured round puts it within 0.9 ms of the one-stream column (section 1.3), so `ON:202`'s
   "38.6 against production's 36.9" compares against a set the prose round does not replay.
2. **Production's drafter is not hidden under the verify.** It runs on the same stream, after the commit and
   before the next verify; it cannot start earlier because its pending token is a verify sample and its context
   rows are the verify's taps (`PN:notes/drafter-pass-DrafterFable.md:91-96`; the measured stream order is "sample
   tail -> commit -> taps graph -> drafter graph -> message gathers -> propose -> verify graph",
   `PN:notes/decode-nsys-DecNsysMimo.md:38-40`). What production does instead: (a) a pass that reads 328.5 MB a
   rank against our 1,047 MB (TP-split drafter, every linear 4-bit), (b) one CUDA graph of 218 kernels, (c)
   launched at the end of the previous round (OTS 0087 prelaunch), so the host's round-end work and the next
   message run under it (about 0.65 ms of host time hidden), (d) one pinned readback. Its pass costs 1.96 ms in
   today's boot calibration, plus 0.033 ms a kept tap row (`BL:`, "drafter costs"), not 1 ms. The "about
   1 ms" traces to MIA 0038's seed (`draft_ms 1.37`, measured on sm_120
   x8); MIA 0097 replaced it for GB10 with 5.92 ms for the Mia Zig engine, whose drafter is built like ours.
3. **Our verify is fully eager.** There is no CUDA graph anywhere in `Z:` (`git grep -i graph v1.2.7 --
   zig/src/families/glm` finds nothing). About 1,400 host launches a window on every rank (estimate; 1,815 a
   round in all measured on the pad stack, section 4), and every all-gather goes through NCCL at TP=3
   (`TF_GLM_ROCE_MULTI` defaults off, `Z:cuda_ranks.zig:27`), where production replays one graph with RoCE one-shot
   gathers inside (`ENV:11`, `Pc:roce.py:584-606`).
4. **Our round has three cross-rank steps** (verify, keep, block), each a broadcast that every follower receives
   with a main-stream synchronize and a blocking read. Production sends one 4 KiB message a round, queued on the
   GPU behind the prelaunched pass, and every rank computes the drafts and the samples itself. On rank 0 the three
   step boundaries cost 0.07 ms a round in all (measured on the pad stack, section 1.3); the followers' side is not
   measured.
5. **Our DFlash2 windows are priced by a stale table** (52 ms + 6.8 ms a row "on two GB10s",
   `Z:cuda_copy_policy.zig:5-6`), because `facts()` drops the load-time prices whenever the drafter is loaded
   (`Z:cuda_lanes.zig:100,116`). This is why the window rule differs from production's, not the drafter pass.
6. **Production's round is about 36.8 ms, not 31.9, and it verifies more rows than we do.** `ON:186-187` divide
   aggregate counters with the warm-up included. Per request, production returns the same reply three times with 388
   drafted and 266 accepted, so 399 - 266 = 133 decode rounds: 3.00 tokens and 3.92 rows a round, 36.7 to 37.4 ms at
   81.67 (`B:prodwin`) and 81.37, 81.29, 80.33 tok/s (`B:prodprof`). The same rule gives our engine's own counter,
   143 = 399 - 256 (`B:v127-pad`: 43.8 ms, 2.79 tokens, 3.80 rows; 44.5 ms with `TF_GLM_PROF`, so the profiler costs
   0.7 ms a round). The round gap is 7.0 ms, and production also keeps 7.5% more tokens a round; the two replies
   differ (`8347edfe4ee6` against `323d3f5bcb55`), so that 7.5% is not yet attributable to the drafter (section
   1.3).

## 1. The order of work in a one-stream round

### 1.1 Production (as served: `--parallel 4`, `COMM=roce`, `TF_GLM_KV_SHARD=1`; `ENV:11,48`)

Rank 0's decode iteration is `P:multi.py:3149-3183`, then `_round` (`P:multi.py:3570-3692`).

| # | step | code | GPU work, host wait |
|---|---|---|---|
| 1 | room for the widest window; `lone` stays False (needs `tune.lone`, which the shard turns off) | `P:multi.py:3152-3170` | host |
| 2 | the ROUND op (sid, depth, lone, short) as ONE fixed 4 KiB all-gather from pinned staging; rank 0 never waits here (`MsgGather.send`, OTS 0102) | `P:multi.py:3174-3179`; `P:engine.py:909-932` | 1 gather queued |
| 3 | propose: a copy proposal, else `MultiDrafter.propose` -> `candidates`: the pass prelaunched last round matches the key (slot, pending, context generation), so the host only waits on its event, then merges and walks the chain | `P:multi.py:3585-3601`; `P:dflash2_multi.py:556-615` | **wait 1** (event) |
| 4 | verify: `BatchedVerify.forward`: ids + KDA and DSA segment tables in ONE pinned H2D, then the captured graph for R rows (a dense variant when no row is sparse) | `P:multi.py:3604-3620`; `P:verify.py:278-295,325-365` | 1 H2D, 1 graph |
| 5 | sample: top-k, pack, one all-gather, pinned readback; every rank samples alike | `P:multi.py:3629-3638`; `P:decode.py:76-121` (readback `:107`) | **wait 2** |
| 6 | accept (host loop) | `P:multi.py:3639-3648` | host |
| 7 | commit and the drafter's context update as ONE graph (`commit_taps`: KDA replay, conv shift, positions, kept rows' taps, the taps compute), one pinned table H2D | `P:multi.py:3649-3663`; `P:verify.py:484-566`; default on `P:verify.py:27-31` | 1 H2D, 1 graph |
| 8 | take tokens, update each stream's depth policy | `P:multi.py:3664-3683` | host |
| 9 | **prelaunch** the next round's block pass: pinned H2D of [pending, slot, position], the block graph for S streams, async D2H of the candidates into pinned memory and an event | `P:multi.py:3684-3688,3708-3736`; `P:dflash2_multi.py:519-554`; default on `P:multi.py:180-183` | 1 H2D, 1 graph, 1 D2H queued |
| 10 | emit text and stats; the next iteration's message | | host, under the pass |

Followers (`P:multi.py:3854-3872`): the next message's gather is queued right after the previous message's work
(`MsgGather.pre`, `P:engine.py:893-907`), so it starts on the GPU when the prelaunched pass ends; `take` reads it
back through a pinned buffer (`P:engine.py:934-952`); ROUND runs the same `_round` (`P:multi.py:3950-3955`). Every
rank computes its own drafts from the same gathered candidates and its own tokens from the same gathered top-k
("all sample by one keyed rule from the same gathered candidates, so no broadcast", `P:engine.py:1`). Nothing is
sent rank to rank inside a round except that message.

### 1.2 Ours (v1.2.7)

The lane core's one-stream round is `ZL:engine.zig:201-255` (`familyRound`), on the GLM backend `Z:cuda_lanes.zig`.

| # | step | code | GPU work, host wait |
|---|---|---|---|
| 1 | late-draft flush: a no-op for GLM (`defer_lone_draft` is false; only `qwen27_lanes` sets it) | `ZL:engine.zig:203`; `ZL:late_draft.zig:11-38`; `ZL:backend.zig:80` | |
| 2 | plan the window, allocate drafts by chances against the cost table, build it | `ZL:engine.zig:207-212`; `ZL:allocate.zig:34-80`; `Z:cuda_lanes.zig:97-124` | host |
| 3 | **verify step**: `Leader.verify` -> `put_words` kernel + `ncclBroadcast` of 256 B (no host wait on rank 0) -> `Engine.verify`: the eager forward (embed, 45 layers, stream mean, final norm, head), then the draw: a `top1` launch a row, one NCCL all-gather, `stream.synchronize`, blocking D2H | `Z:cuda_lanes.zig:445-469`; `Z:cuda_follow.zig:84-108,257-261`; `Z:cuda_engine.zig:434-446,528-535`; `Z:cuda_engine_pick.zig:15-41` | about 1,400 launches, 91 NCCL gathers; **wait 1** |
| 4 | conclude: the accepted path, committed tokens | `ZL:engine.zig:218,328-440` | host |
| 5 | **keep step**, exactly one a round (from `keepFn` when a draft failed, else from `draftBlock`'s `bind`): broadcast + `forward.commit` (KDA replay when fewer rows kept, conv shift, `setPos` memset) | `Z:cuda_lanes.zig:175-181,509-516,545`; `Z:cuda_follow.zig:288-292`; `Z:cuda_forward.zig:572-599` | 2 or 3 launches |
| 6 | **block step**: `Leader.block` -> broadcast -> `Drafter.draft`: ingest (D2D taps copy, 2 H2D, fc, norm, 5 x (kv, ctx_kv)), 5 H2D tables, the eager block pass, then 2 x (`stream.synchronize` + blocking D2H), then the host select | `ZL:engine.zig:221-229,443-500`; `Z:cuda_lanes.zig:540-557`; `Z:cuda_follow.zig:309-316`; `Z:cuda_engine.zig:477-481`; `Z:dflash.zig:236-314`; `Z:dflash_block.zig:49-60,70-186` | about 135 launches; **waits 2, 3** |
| 7 | chain cut: past the first draft, a chance is zeroed where the chain product falls under 0.7 | `Z:cuda_lanes.zig:558-567`; `Z:dflash.zig:42-45` | host |
| 8 | step end (trail, sweep), then step 2 of the next round | `ZL:engine.zig:157-159` | host |

Followers (`Z:cuda_follow.zig:349-443`): every step is received with `ncclBroadcast` + `stream.synchronize` + a
blocking D2H (`Z:cuda_follow.zig:74-77,117-130`). The Link lives on the engine's MAIN stream
(`Z:cuda_native.zig:332`), so each receive also waits for all of the follower's own earlier work. A follower runs
the verify including the draw's synchronize and read (`:390`), the keep (`:414`) and the block pass without the
select (`:421-427`); it never computes drafts, which arrive as the next verify step's ids.

### 1.3 The two GPU timelines and what each part costs

| part of the round | production (served) | ours (v1.2.7, pad on) |
|---|---|---|
| verify | 33.3 to 34.2 ms at 3.92 rows (derived: the 36.8 ms round less the two rows below; the one-stream column gives 33.3 at 3.92 rows, 29.20 + 0.92 x 4.50 from `BL:`; the always-select batched column would give 36.5 ms and a 39 to 40 ms round, which the measured round rules out) | 37.0 to 37.7 ms at 3.80 rows (derived: 29.41 + 0.9 x 9.23 from `BR:`, less up to the profiler's 0.7 ms) |
| drafter | 2.0 to 2.2 ms: block pass 1.96 (+0.033 a kept tap row), a row bucket's update 0.265 at most, today's boot calibration over RoCE (`BL:`); 2.29 ms block in October's (`PN:notes/drafter-pass-DrafterFable.md:36-39`) | 5.4 to 6.2 ms: on v1.2.7 with the phases synchronized ingest 0.48, tables 0.01, block 5.69 to 5.71, select 0.04 (`BR:`); 5.4 to 5.9 in `ON:201` |
| commit, sample, accept, message, emit, idle | 0.6 to 1.3 ms (estimate: about 1.0 in `PN:notes/prose-100-roofline-2026-10-09.md:105-108`, whose non-verify total is 3.8 ms with a 2.39 ms block; 1.84 ms at `dec35k` under NCCL before RoundGraphs and the message gather, `PN:notes/decode-nsys-DecNsysMimo.md:51-57`) | 0 to 1.4 ms (derived: 43.8 less the two rows above, both upper bounds) |
| round | 36.7 to 37.4 ms: 133 rounds a request (399 - 266 accepted), 3.00 tokens and 3.92 rows a round (derived from `B:prodwin`, `B:prodprof`) | 43.8 ms: 143 rounds, 2.79 tokens, 3.80 rows (the engine's counters, `B:v127-pad`); 44.5 ms with `TF_GLM_PROF` (`B:v127-prof`) |

Production's round is 7.0 ms shorter (43.8 against 36.8) and carries 7.5% more tokens (3.00 against 2.79), which
together make the 28% (derived: 81.2 / 63.6 = 1.28 = 43.8 / 36.8 x 3.00 / 2.79). Of the 7.0 ms, from the rows
above: the drafter 3.2 to 4.2, the verify 2.8 to 4.4 at these rows (3.4 to 4.9 at equal rows, a row costing about
4.6 ms in `BR:`), the rest within 1.3 ms either way. `ON:189-192`'s first reading is reversed on two counts:
production verifies more rows than we do (3.92 against 3.80), not fewer, and its drafter costs it about 2 ms a round
rather than being hidden. The tokens a round come from two different replies (`8347edfe4ee6` against
`323d3f5bcb55`), and both the text and the drafter's settings move them: on reply `3ec88b6418f7` v1.2.7 without the
pad drafts 398 and keeps 250 while the fork's stack drafts 421 and keeps 251 (`B:v127`, `B:roce1-nccl`); v1.2.7 with
the pad, on reply `323d3f5bcb55`, drafts 401 and keeps 256 (`B:v127-pad`). No existing cell gives a same-text pair: at
one to eight streams production's replies (`8347edfe4ee6`, `66b9fe5c1ea4`, `8ab1a46288e5`, `c01484b25e1f`,
`B:pyprod`) and ours (`323d3f5bcb55`, `a903d540de88`, `3532ba23f928`, `a32f22d65d77`, `B:v127-pad`) differ on every
prompt. So attributing the 7.5% (up to 3.3 ms of our round, derived: 43.8 x 0.075) takes both drafters scored on one
fixed token sequence, which production's per-round recorder can give (`TF_GLM_ROUND_LOG`, built and not deployed:
`PN:notes/prose-100-roofline-2026-10-09.md:153-155`).

Measured without profilers on rank 0 of the pad stack at one stream (`NS:`; segments cut at each step's `put_words`
kernel, 153 rounds, 44.2 ms a round at 3.92 rows):

| step | span ms | busy ms | idle ms | NCCL ms | kernels | gap to the next step ms |
|---|---:|---:|---:|---:|---:|---:|
| verify, with this stack's per-row draw | 37.62 | 36.28 | 1.34 | 3.35 | 1,540 | 0.015 |
| keep | 0.26 | 0.25 | 0.01 | 0.00 | 3.5 | 0.004 |
| drafter | 5.95 | 5.79 | 0.16 | 0.36 | 139 | 0.052 |

The keep row leaves out one 48 ms segment; four further segments (1.1 ms each) hold a marker without a verify, a
commit or a drafter pass. So on rank 0 the steps cost almost nothing at their boundaries: the drafter step is its
kernels (5.79 of 5.95 ms), and what a graph could take out of the verify step is its 1.3 ms of idle plus whatever
of its 3.4 ms in NCCL is waiting for a later rank (section 3.3).

Production's own round profile measured its split on the October images (read today on spark1, the one-stream
reports with three rows or more): on v18-ots with the clocks locked (`~/prof/stages/profile-lines.log`, 95 reports,
3.9 rows, 3.1 tokens) the wall is 39.89 ms, of which the verify's GPU time is 36.02 and the rest 3.9: propose 2.74
(the drafter, before the prelaunch existed), message 0.77, commit 0.10, taps 0.10, sampling 0.12; on v110-ots99 under
NCCL (`~/prof/night/rank0-prof.log`, 9 reports, 6.7 rows) the wall is 54.9 ms, of which the verify's GPU time is
50.42 and the rest 4.5: message 3.34 (the gather queued behind the prelaunched pass, so the drafter's GPU time lands
there), emit 0.47, propose 0.26, sampling 0.18, commit 0.12, taps 0.10. Today's 1.96 ms pass over RoCE puts the rest
at 2.6 to 3.5 ms (the table above), in line with those. Today's image left no such line: `work/prod-prof.sh` arms
`TF_GLM_MULTI_PROFILE=20` (`:8`), but `BL:` holds only the start-up line, because `RoundProfile` prints with a plain
`print` (`P:multi_tune.py:281,333`), production's own plan says the profile "Needs `PYTHONUNBUFFERED=1` to reach
`docker logs` live" (`scripts/glm53/v110/draftsim_plan.md:98-100,106` in the production repo), and the script removes
the container with `docker rm -f` (`:12`), which drops the unwritten buffer (inference). With `PYTHONUNBUFFERED=1`
beside the knob the same run prints the `multi profile (batched)` line (`P:multi_tune.py:328-339`).

### 1.4 Speculation, side streams, graphs

- **Queued before the accept count is known.** Production: nothing that depends on it. The pass is prelaunched
  after the commit (`P:multi.py:3684`); followers queue the next message's gather before rank 0 has written it,
  which is early in time but not in content (`P:engine.py:893-907`); a speculative taps update was considered and
  not built (`PN:notes/drafter-pass-DrafterFable.md:97-103`). Ours: nothing. The lane core has an early-draft path
  (`speculate_early`, `ZL:engine.zig:211`) and a late-draft deferral, both off for GLM (`Z:cuda_lanes.zig:109`,
  `ZL:backend.zig:80`).
- **Side streams in a decode round.** Production: the L2 prefetch (`P:l2pf.py:206-303`) and the MoE shared expert
  (`TF_GLM_SHARED_SIDE` default 1, `P:forward.py:516-518,1270-1294`); OutProjSplit and MsgSide exist and are off by
  default (`P:forward.py:521-538`, `P:engine.py:955-966`). Ours: the L2 prefetch only (on by default on a GB10 at two
  ranks or more, `Z:cuda_l2pf.zig:1-14`; fork and join `Z:cuda_forward.zig:469,480,491`); the shared expert runs
  after the routed experts on the main stream (`Z:cuda_moe.zig:53-90`).
- **Graphs.** Production: batched verify graphs for 1..32 total rows with dense and decode-shard variants
  (`P:verify.py:176-208`), commit+taps graphs a drafter bucket (`P:verify.py:416-482`), drafter block graphs per
  stream count and taps graphs per row bucket (`P:dflash2_multi.py:390-408`). The one-stream graphs, keyed
  `(rows, KDA parity)` for 1..8 rows plus sparse pool buckets (`P:graphs.py:44-83`, `P:engine.py:19`), are captured
  only with `--parallel 1`, the lone path, the profile or the serial seam (`P:engine.py:504-528`), and no served
  decode round replays them. Ours: none. The in-tree pattern to copy is DeepSeek V4.1's decode-window graphs over
  `zig/src/cuda/graph_cache.zig` ("keyed by rows and context bucket; bits equal eager",
  `zig/src/families/deepseek_v41/graphs.zig:1-11`), with every rank's verdict agreed in
  `zig/src/families/deepseek_v41/lockstep.zig`.

## 2. The drafter

### 2.1 One pass, side by side (one stream)

| | production (`MultiDrafter`) | ours (`Drafter`) |
|---|---|---|
| rows | 8 through 5 layers; final norm and head on 7 (`x[:, 1:]`, `P:dflash2_multi.py:316-328`) | 8 through 5 layers; norm, head and selector projection on all 8 (`Z:dflash_block.zig:159-166,185`); row 0's head is never read (`Z:dflash_select.zig:17-18`) |
| split at TP=3 | KV heads in whole groups 3/3/2, query heads 12/12/8, MLP 4,096 a rank (`P:tp.py:266-274`, `P:dflash2.py:435-441`); o and down row-parallel fp32 partials, gathered, summed in rank order (`P:dflash2.py:602-610`) | none: `split = world == 2` (`Z:dflash_load.zig:148-149`); at world 3 every rank runs all 32/8 heads and the 12,288-wide MLP (`Z:dflash_load.zig:188-194`) |
| precision | every linear 4-bit, down included (`P:dflash2.py:476-508`) | 4-bit except down and the selector projection, bf16 (`Z:dflash.zig:78-79`, `Z:dflash_load.zig:193,199`) |
| weight bytes a pass, rank 0 | 328.5 MB (`PN:notes/drafter-pass-DrafterFable.md:54`) | 1,047 MB (`AE:research/overnight-2026-10-29/drafter.md:21-37`) |
| launches | one graph replay of 218 kernels (`DrafterFable.md:41`) | about 115 to 120 eager launches for the pass and 18 for the ingest, 7 H2D, 1 D2D (counted from `Z:dflash.zig:236-314`, `Z:dflash_block.zig:70-186`) |
| collectives | 11 a pass (5 o, 5 down, 1 candidates), RoCE, about 27 us each (`DrafterFable.md:36-39`) | 1 (the candidates, `Z:dflash_block.zig:184`), NCCL |
| readback | one pinned D2H queued with the pass, its event waited at the next propose (`P:dflash2_multi.py:533-537,579-580`) | two `stream.synchronize` + blocking D2H (`Z:dflash_block.zig:55-60`, `Z:dflash.zig:301-302`) |
| when | launched at the end of the previous round | launched and read back inside the round's block step |
| context update | taps graph per row bucket (`P:dflash2_multi.py:438-470`), on the served path inside the commit graph (`P:verify.py:416-566`) | eager ingest before the pass (`Z:dflash.zig:236-275`) |
| time | 1.96 ms block pass and 0.265 ms a row bucket's update in today's boot calibration over RoCE (`BL:`); 1.925 ms graph on one GB10, synthetic weights, no network (`DrafterFable.md:27`); 2.29 ms in October's calibration over RoCE, taps8 0.34 (`:36-37`); 3.24 to 3.46 ms traced under NCCL (`DecNsysMimo.md:52,67-69`) | block 5.3 to 5.45, ingest 0.47 ms (`PE:153-155`, phases synchronized); on v1.2.7 block 5.69 to 5.71, ingest 0.48 (`BR:`) |

The kernel split of our pass (pin, knobs off, `PE:158-170`): `tf_qmm_group` 3.0 ms a round over 32 launches (the
4-bit linears, fc, kv and the head) and `glm_mm16_16` 2.2 ms over 6 launches (the five bf16 downs and the selector
projection).

### 2.2 Overlapped, on another stream, shrunk, or fused?

- **Overlapped with the verify: no.** Data dependency (`DrafterFable.md:91-96`), and a measured probe of the pass on a
  second stream beside a bandwidth-bound neighbour hid at most 0.2 ms of its 2.0 (`:93-96`).
- **On another stream: no.** The only decode-round side streams are in section 1.4.
- **Shrunk: yes**, 3.2x fewer weight bytes a rank (the split and the 4-bit down).
- **Fused: yes**, one graph; OTS 0108's fusions (one kernel for the rank-ordered sum, ring writes in `_prep`, one
  top-k) took another 44 us at one stream (`DrafterFable.md:80-85`).
- **Launched early: yes**, OTS 0087's prelaunch hides about 0.65 ms of host round-end work under it
  (`DrafterFable.md:64-65`).

So production's drafter costs about 2.0 to 2.2 ms of GPU time a round on the critical path (`BL:`). Ours costs 5.4
to 6.2 ms (`BR:`, `ON:201`), of which the bytes explain most: 1,047 MB at our measured 177 GB/s effective against 328.5 MB
(`AE:research/overnight-2026-10-29/drafter.md:37-38`).

### 2.3 MIA 0036 / 0038 and their production equivalents

`docs/RECON-MIA-RECIPE.md:31` lists them as "DFlash2 window rules by expected tokens, tpm seeds". They are window
rules, not a faster pass. MIA 0036 adds `TF_GLM_DRAFT_RULE=tpm` (selector chances calibrated online, a window offers
the drafts whose chain chance beats tokens a ms times a row's verify ms); MIA 0038 seeds it with sm_120 x8 prices
"verify 9.4 + 1.31 ms a row, drafter 1.37 ms"; MIA 0097 replaced those for GB10 with "38.73 + 5.68 ms a row past the
first ... the drafter's pass is 5.92 ms", measured on a Spark pair, and notes that the default rule (`cut`) never
reads them. MIA 0109 is the same MLP split as item 1 below ("5.5 ms a round at one stream and 8.7 at four" for the
unsplit drafter on four GB10s).

Production's equivalents: the default DFlash2 policy `fc5:0.3` unless `TF_GLM_DFLASH_POLICY` names another
(`P:engine.py:15-17`); `fncN:P[:B]`, a product of noise-aware confidences at temperature 2.0
(`P:dflash2.py:64-80,783-799`); `fcostN:noisy`, the depth maximizing expected tokens per round ms over a boot-timed
table (`P:dflash2.py:83-90`, `P:engine.py:442-470`, `P:multi.py:1053`); the selector's edge weight 0.6 below the
stream threshold (`P:dflash2.py:25-61`). Production's notes name `fnc7:0.3` as the served policy
(`PN:notes/boot-time-BootFable.md:84-88`). Ours: the 0.7 cut on raw selector chances (`Z:cuda_lanes.zig:558-567`),
edge weight 1 (`Z:dflash_select.zig:55`), and the stale window table (finding 5).

### 2.4 What we can do bit-exactly

- **Drafts and replies unchanged:** the pass as one graph, launched at the round's end, one pinned readback, the
  ingest folded into a commit graph, the head and selector projection on 7 rows. Same kernels, same order.
- **Replies unchanged, drafts changed:** the TP split of the MLP (and of the attention) and the 4-bit down.
  Verification keeps the target's own sample, so the reply digests cannot move; on the fork every digest stayed
  equal (`AE:reports/SPEED-REPORT.md:842-862`). Acceptance can move: the MLP split measured -2.4% tokens a round on
  the fork (`:852,862`).

## 3. The verify at equal rows, section by section

### 3.1 What the 4.9 ms compares

- Ours: `TF_GLM_PROF` on v1.2.7, live decode, the mean of 64 calls a row bucket. A section is the time between two
  CUDA events recorded on the main stream (`Z:cuda_prof.zig:61-102`), so it includes any idle between its kernels;
  the window records about 265 events (6 marks a MoE layer, 4 a dense one: `Z:cuda_forward.zig:446,452,468-484`,
  `Z:cuda_moe.zig:63-64`), whose own cost is not measured apart; the whole profiler costs 0.7 ms a round (43.8
  against 44.5 ms, `B:v127-pad`, `B:v127-prof`). 29.41 ms at 2 rows, 38.64 at 4 (`BR:`).
- Production: `_compare_paths` at start-up, the fastest of 6 replays, distinct timing tokens, slot 0 at near-zero
  context (`P:multi.py:1120-1150`, `P:verify.py:212-239`). Today (`BL:`): one-stream 24.82 at 2 rows and 33.70 at 4,
  batched 25.65 and 36.90. The one-stream column times the dense graphs (`P:graphs.py:56-59`), the batched one the set
  that always runs the token selection (`P:verify.py:180-181,225`); the prose window replays the dense batched set,
  which no boot line times, and the measured round puts it within 0.9 ms of the one-stream column (section 1.3).
- So the 4-row gap is about 4.0 to 4.9 ms with our profiler on (38.6 against 33.7 to 34.6) and about 3.3 to 4.9 ms
  without it (the profiler's 0.7 ms a round is not all in the verify). `ON:202`'s 1.7 ms uses the always-select
  column.

### 3.2 Per section at 4 rows (ours from the task's v1.2.7 profile; the layer counts from `Z:config.zig:12-21,116-122`: 45 layers, DSA at 3, 7, ..., 43, so 34 KDA and 11 DSA; 3 dense, 42 MoE)

| section (ours) | ms | ours: what runs (code) | production at the same place (code) | difference in code |
|---|---:|---|---|---|
| embed | 0.01 | ids staged by `copy_source.enqueue`, `embed_b16` (`Z:cuda_forward.zig:439-446`) | one pinned H2D of ids and tables before the graph (`P:verify.py:278-295`) | none that matters |
| kda (34 layers, with the attention `hc_pre`) | 5.3 | `hc_partial8` on 16 blocks a row + `hc_finish` (`Z:cuda_glue.zig:201-219`); 3 projection matmuls (`Z:cuda_kda_block.zig:95-115`); the three-kernel chain (`:131-136`); o_proj (`:73-76`) | `hc_pre` with `hc.cu` on 48 blocks a row (`TF_GLM_HC_DEC` default on, `P:glue.py:189-224`); `kda_segments` (`P:forward.py:790-812`) | the HC grid; the chain is "production's KDA line for line" (`AE:PARITY.md:853-856`) |
| mla (11 layers, with `hc_pre`) | 3.2 | projections, norms, index key and gate, absorb, latent and index writes, dense attention, expand, o_proj (`Z:cuda_dsa_block.zig:91-160`) | `dsa_segments` in the graph | both skip the token selection when no row is sparse (`Z:cuda_dsa_block.zig:141-150`; `P:verify.py:343-346`) |
| gather_a (45) | 2.0 | the L2 fork, then `ncclAllGather` of fp32 partials (`Z:cuda_forward.zig:222-240,469-471`) | RoCE one-shot inside the graph (`Pc:roce.py:584-606`, `P:engine.py:1161-1172`) | transport, and the followers' start lag (section 1.2) |
| dense (3) | 0.4 | `hc_post`, `hc_pre`, gate/up, SwiGLU, down | `mlp_front` with the fused `matmul_swiglu` (`P:forward.py:1236-1249`) | one kernel less a layer |
| router (42, with `hc_post` + ffn `hc_pre`) | 1.5 | `router_tile` + `slice_sum` + `topk` (`Z:cuda_moe.zig:57-60`, `Z:cuda_glue.zig:168-183`) | `route_select`: `_router_part` + `_topk_sum` (`P:glue.py:632-647`) | one kernel less a layer |
| routed (42) | 21.7 | `exl3.run` (`Z:cuda_moe.zig:65`) | `exl3_mm.routed` on the router's 16-pair item plan (`P:forward.py:1279-1292`) | the plan: -2 to -4% at 8 rows or fewer in a both-engines bench (`AE:PARITY.md:828-852`); our fold's 0044, not in v1.2.7 |
| shared (42) | 1.7 | after the routed experts: gate/up, SwiGLU, down, `put_slot`, `combine` (`Z:cuda_moe.zig:73-90`) | on a side stream from the block's start, one `combine_shared` (`P:forward.py:1270-1309`, `P:glue.py:686-693`) | serial against overlapped; two kernels against one |
| gather_b (45) | 1.8 | the L2 fork, NCCL gather, `hc_post`, taps (`Z:cuda_forward.zig:480-484`) | RoCE in the graph, `hc_post` | as gather_a |
| head | 1.0 | stream mean, final norm, 8-bit head (`Z:cuda_forward.zig:490,495-511`) | final norm and an FP8 head under `TF_GLM_DENSE=q4` (`P:weights.py:334-337`) | same bytes class |

The routed experts are near their bandwidth floor (`ON:202-205`), so the gap is in the rest.

### 3.3 Where the 3.3 to 4.9 ms most likely goes (estimates)

| cause | estimate | evidence |
|---|---:|---|
| gathers: NCCL ring LL plus the wait for followers, against RoCE in a graph | 1.4 to 2.5 ms | on the pad stack 94.9 all-gathers and 3.7 ms a round, durations p10 11.5 us, p50 26.8, p90 58.5, p99 296, so 2.6 ms a round above the p10 time (`NS:`; derived: 3.7 - 94.9 x 0.0115); the `TF_GLM_PROF` sections hold 3.8 ms with the L2 fork, `hc_post` and five taps copies; production 1.35 to 2.4 ms for about 90 (`AE:PARITY.md:812-813`); RoCE in place of NCCL took 1.3 ms off our round with the pad (`B:roce1-pad`) |
| main-stream idle | up to 1.7 ms | rank 0's main stream idles 1.7 ms a round on the pad stack (263.7 ms over 153 rounds) in about 1,600 gaps of a few us, the largest shares just before the all-gathers (0.18 and 0.16 ms a round after `glm_mm_reduce` and `tf_glm_combine`) (`NS:`); 1.6 ms on the fork at 8-row windows (`AE:PARITY.md:808-811`); production's whole round idles 0.67 ms (`DecNsysMimo.md:50`) |
| routed item plan | about 0.6 ms | +1.4% tok/s at P1 with the pad on our stack (`patches/engine/0044-exl3-decode-items.patch` header), 2 to 4% of 21.7 ms in the bench (`AE:PARITY.md:828-852`) |
| MoE glue (side stream, fused combine and route) | up to 0.3 ms | the fork's `SHARED_SIDE` alone was level at one stream (`AE:reports/SPEED-REPORT.md:854`) |
| our profiler's own events | up to 0.7 ms | the whole profiler costs 0.7 ms a round (43.8 against 44.5 ms, `B:v127-pad`, `B:v127-prof`), not all of it in the verify |

## 4. Kernel launches and host waits a round (one stream, rank 0 unless stated)

| | production (served path) | ours (v1.2.7) |
|---|---|---|
| CUDA graph launches | 3: verify, commit+taps, drafter (`DecNsysMimo.md:109`; `P:verify.py:351,556`; `P:dflash2_multi.py:530`) | 0 |
| kernels inside graphs | about 1,000 in the verify ("per-shape CUDA graphs replace ~1,000 launches a round with one replay", `PN:GLM53-SPEED-CAMPAIGN-2026-10.md:73`), 218 in the drafter | n/a |
| eager kernels | the sampler's top-k, about 25 tiny kernels (`DecNsysMimo.md:206-209`), 2 gathers (sample, message) | verify about 1,400 (below) with 91 NCCL gathers; keep 2 or 3; drafter about 135 with 1 NCCL gather; 3 x (`put_words` + broadcast); on the pad stack 1,815 launches a round in all, 1,402.6 `cuLaunchKernel` and 412.0 `cuLaunchKernelEx`, 9.2 ms of host time (`NS:`) |
| H2D copies | 3 pinned (window tables, commit table, drafter meta: `P:verify.py:293,553`, `P:dflash2_multi.py:527`) + message staging (`P:engine.py:924`) | ids (`Z:cuda_forward.zig:439`), 7 drafter uploads from host arrays (`Z:dflash.zig:251-252,291-295`), `setPos` memsets |
| host waits, rank 0 | 2: candidates event, sample readback | 3: the draw, the candidates, the projections; the pad stack measured 5.9 `cuStreamSynchronize` a round with the host blocked 29.8 ms in them, its draw reading each row (`NS:`), so the host runs well ahead of the GPU |
| host waits, each follower | 3: message, candidates, sample | 4: three step receives (broadcast + main-stream synchronize + read each) and the draw |
| rank-to-rank rendezvous a round | 1 message, queued on the GPU | 3 steps (verify, keep, block) |

**Our verify's launches, counted from the call sites** (R = 4, dense region, `KDA_PAD`, 4-bit dense packs; a
matmul is 1 launch, 2 with a split-K sum, `Z:cuda_b16.zig:57-96`): attention `hc_pre` 2; KDA mixer 7 to 11 (3
projections, chain 3, o_proj); DSA mixer about 15 to 20; gather 1; `hc_post` 1 + ffn `hc_pre` 2; MoE 11 to 13
(route 3, routed 2 grouped kernels a layer as measured, `PE:162`, shared 5 to 7); dense MLP 3 to 5; gather 1;
`hc_post` 1; plus 2 L2 side launches a layer. That is about 29 a KDA+MoE layer, 37 a DSA+MoE layer, 21 a KDA+dense
layer: 31 x 29 + 11 x 37 + 3 x 21, about 1,370, plus the head and the draw, about 1,380 on the main stream
(estimate). The pin's nsys per round agrees in kind (`PE:160-170`: 84 routed, 103 `bmm_decode`, 168
`glm_mm4_16`, 95 NCCL gathers, 123 L2 kernels, and 58 other kernel types whose launch count it does not give).

## 5. Ranked changes to our engine

Ranked by the central estimate of ms saved a round at one stream; items 5 to 9 sit within 0.25 ms of each other once
the capture bounds them, so their order among themselves is not significant. "Replies bit-exact" means reply digests equal;
"drafts change" means the drafter's arithmetic moves, so acceptance can move, while no reply token can.

| # | change | mirrors | ms at P1 | bits | 2 / 4 / 6 / 8 streams |
|---|---|---|---:|---|---|
| 1 | drafter MLP split at TP=3 and 4-bit down | `P:dflash2.py:435-441,476-508,602-610`; MIA 0109 | 2.9 to 3.9, measured on the fork | replies bit-exact, drafts change | 4-bit down about -2.0 ms at every level (fork estimate, `AE:research/overnight-2026-10-29/drafter.md:60`); the split's gathers grow with 8S rows, so gate it by stream count |
| 2 | verify windows as CUDA graphs | `P:verify.py:176-208,325-365`; `P:graphs.py:44-83` | 1 to 3, estimate | bit-exact | shared windows by total rows to 32, as production's batched set |
| 3 | RoCE all-gathers at TP=3, with a size gate | `ENV:11`; `Pc:roce.py:563-606` | 1.3, measured with the pad (41.8 against 43.1 ms a round, the engine's counter, same reply) | bit-exact | +1.4 / +0.3 / -0.6 / -1.3% measured, so gate by bytes at our own break-even |
| 4 | routed experts on the item plan (our `0044`, PR #2044) | `P:forward.py:1279-1292` | about 0.6, measured on our stack (+1.4% at P1 with the pad) | bit-exact | +1.4% (rerun) / +1.3% / +1.7% / +2.2% measured at 2 / 4 / 6 / 8 |
| 5 | the drafter pass as one graph, launched at the round's end, one pinned readback | `P:dflash2_multi.py:390-408,519-591`; `P:multi.py:3684-3736` | 0.1 to 0.2, bounded by the capture (the drafter step's 0.16 ms idle and 0.05 ms boundary on rank 0, `NS:`) | bit-exact | a graph per stream count; helps every level |
| 6 | the keep rides the next step; followers skip the draw's read | MIA 0031; production has no such step at all | 0 to 0.3, estimate (0.02 ms at rank 0's keep boundaries, `NS:`; the followers' receives not measured) | bit-exact | the same steps happen at every level |
| 7 | commit and drafter ingest as one graph | `P:verify.py:416-566` | up to 0.15 (the keep step idles 0.01 ms; the ingest sits inside the drafter step's 0.16, `NS:`) | bit-exact | constant a round |
| 8 | DFlash2 windows priced by measured costs, production's chain rule | `P:engine.py:15-17,442-470`; `P:dflash2.py:25-90` | 0 to 0.5 net, estimate | replies bit-exact, drafts change | shared rounds use their own static table today |
| 9 | MoE glue: shared expert on a side stream, one combine kernel, route sum folded into top-k, fused gate/up + SwiGLU | `P:forward.py:1236-1309`; `P:glue.py:632-647,686-693`; MIA 0006 | up to 0.3 | bit-exact | the fork measured `SHARED_SIDE` level at P1, -0.6% at P4 |
| 10 | `hc_partial` on 48 blocks a row for decode | `P:glue.py:189-224` | about 0 | bit-exact | the fork measured +0.4% at P4, +1.0% at P8 (`AE:SPEEDUPS.md:139`) |

Central estimates add to about 8 ms, which would bring 43.8 ms to about 35.8 ms, about 78 tok/s at our 2.79 tokens a
round against production's 81.2 (derived; the items overlap, notably 2 with 3, 6, 7 and 9). At 2.79 tokens a round,
matching production needs a 34.4 ms round; the rest of the difference is tokens a round (section 1.3).

The levels these changes must not regress: production leads v1.2.7 with the pad by 31, 26 and 33% at one, two and
four streams and trails it by 3 and 8% at six and eight (81.73 / 89.22 / 117.98 / 114.78 / 131.28 against 62.19 /
70.57 / 88.91 / 118.29 / 143.25 tok/s, `ON:16`, `ON:168-169`). Item 3 measured slower at six and eight streams, item
1's split is estimated to cost at eight (section 5.1) and item 9's side stream measured -0.6% at four, so those ship
gated by bytes or stream count; items 2, 4, 5, 6 and 7 keep every reply bit and remove launches, waits or bytes at
every level. At four streams the same stack's capture (`~/nsys/f5-pad-p4.sqlite`, rank 0, a window that includes
prompt fills) idles 4.6% of the time (3.9% at one stream) and spends 6.1% in all-gathers with a median of 46.0 us
(26.8 at one stream; 8.4% of the round there), so graphs keep their share of the round at four streams while RoCE's
edge per gather narrows, as its measured +0.3% at four streams shows.

### 5.1 Drafter MLP split and 4-bit down

- **What.** At world 3, cut the drafter's gate/up by rows and down by K over the ranks, sum the fp32 partials in
  rank order, and quantize down to 4 bits as every other drafter linear. Our fork has both as knobs
  (`TF_GLM_OVN_DRAFT_DOWN4`, `TF_GLM_OVN_DRAFT_MLPSPLIT`, `patches/engine/0004-draft-knobs.patch`), with
  `df_sumw` for the rank-ordered sum and an fp32-out tile in `qmm_group.cu`; `docs/PATCH-AUDIT.md:31` item 15 is the
  `loadF32` defect that 0041 fixed for this pair.
- **Ours today.** `Z:dflash_load.zig:148-149,188-194`; `Z:dflash_block.zig:147-156`.
- **Measured on the fork** (`AE:reports/SPEED-REPORT.md:845-852,862`, P=4 boots, digests equal): `DRAFT_ONEPASS` +
  `DRAFT_DOWN4` took one stream from 42.8 to 39.9 ms a round (+6.9% tok/s, tokens a round unchanged at 2.734);
  adding `DRAFT_MLPSPLIT=4` took it to 38.9 ms with tokens a round 2.667 (-2.4%), +7.3% tok/s in all; at four streams
  +0.8% and +3.3%. `ONEPASS` is a no-op at one stream (8 rows fit one 16-row launch).
- **Streams.** The pass has 8S rows; our 4-bit linears launch 16 rows at a time and re-read their weights each
  launch (`Z:dflash_block.zig:32-36`), so from 3 streams `ONEPASS` matters too (fork estimate -2.2 to -6.8 ms at 4
  to 8 streams, `AE:research/overnight-2026-10-29/drafter.md:59,71-93`). The split's gather grows with rows (fork
  estimate -1.3 / -1.2 / -0.6 / 0 / +0.4 ms at 1 / 2 / 4 / 6 / 8, `:61`), hence the `=4` gate.
- **Production's full split** (attention by KV groups too) saves 74 MB more for 5 more gathers: a wash at NCCL
  gather costs, positive after item 3 (`drafter.md:137-140`; production found the same, `DrafterFable.md:104-106`).
- **Files.** `Z:dflash_load.zig`, `Z:dflash_block.zig`, `Z:dflash.zig` (`rawBytes`, `carve`), `Z:cuda_q4.zig`,
  `zig/kernels/cuda/glm_dflash.cu`, `zig/kernels/cuda/qmm_group.cu`.
- **Confirm.** `TF_GLM_DFLASH2_PROF=1` alone (with `TF_GLM_PROF` also on, v1.2.7 gives block 5.69 to 5.71 ms, `BR:`)
  at P1 and P4: the block should fall toward 2.5 to 3 ms; the cell's drafted, accepted and round counters;
  `scripts/bench-arm.sh` at 1/2/4/6/8 with reply digests equal to the knob-off arm.

### 5.2 Verify windows as CUDA graphs

- **What.** Capture the one-stream window for 1..8 rows (and the shared window by total rows to 32) and replay it,
  staging ids before the replay, as production does.
- **Ours today.** No graph. What has to become a key or a device table before capture: the KDA parity, which
  picks state pointers on the host (`Z:cuda_forward.zig:269-272`; production keys `(rows, parity)`,
  `P:graphs.py:56-59`, or carries parity in its segment table, `P:verify.py:267-271`); the DSA host position and
  chunk count (`Z:cuda_forward.zig:466`, `Z:cuda_dsa_block.zig:141,150`; production's dense and per-pool-bucket
  sparse sets, `P:graphs.py:69-83`, `P:verify.py:198-205`); the ids upload, which refuses capture
  (`zig/src/cuda/copy_source.zig:495-506`); the profiler's events (`Z:cuda_prof.zig:71-76`); the L2 fork and join,
  which must rejoin before the capture ends (`Z:cuda_l2pf.zig:215-250`; production's `P:l2pf.py:298-303`).
- **Template.** `zig/src/families/deepseek_v41/graphs.zig` (keys `{rows, ctx}`, the memory room rule at
  `:97-134`), `zig/src/cuda/graph_cache.zig`, `zig/src/families/deepseek_v41/lockstep.zig`.
- **ms.** Estimate 1 to 3 at one stream, bounded by the pad stack's capture (`NS:`): rank 0's main stream idles
  1.7 ms a round, and the all-gathers spend 2.6 ms a round above their p10 time, mostly waiting for a later rank.
  The host is ahead of the GPU (29.8 ms a round blocked in synchronizes), so the 9.2 ms of launch time is hidden
  today; graphs buy the idle and the followers' lateness, not the launch time.
- **Bits.** Exact when every captured launch is the eager one with the same arguments
  (`P:graphs.py:1`; `zig/src/families/deepseek_v41/graphs.zig:1`).
- **Confirm.** First `scripts/nsys-rank0.sh` on rank 0 and on rank 1 at one stream with `TF_GLM_PROF` off, through
  `scripts/nsys-kern.py`: launches a round, main-stream idle a round, NCCL time a round. Then the cells and the GPU
  byte checks.

### 5.3 RoCE all-gathers at TP=3

- **What.** The window's small all-gathers on RoCE: either v1.2.7's own `TF_GLM_ROCE_MULTI=1`
  (`Z:cuda_roce_multi.zig:1-26`; it needs `TF_TP_MASTER` and `TF_TP_KERNEL_IMAGE`, `Z:cuda_ranks.zig:175`), or the
  fork's worlds-2-to-4 gather (`060465305` and three follow-ups, `ON:123-128`).
- **Measured with the pad** (the fork's stack through 0042 plus the gather, `TF_ROCE` on against off, three requests
  a cell, every reply identical): 65.68 against 63.87 tok/s at one stream (+2.8%; 41.8 against 43.1 ms a round, the
  engine's counter), then +1.4 / +0.3 / -0.6 / -1.3% at two, four, six and eight streams (means of the three
  requests, `B:roce1-pad`, `B:roce1-pad-nccl`). Without the pad `ON:160-163` reports +2.0% at one stream. v1.2.7's
  own `TF_GLM_ROCE_MULTI` has not been measured.
- **Gate.** This production serve sends "all-gathers up to 512 KiB over RoCE ..., larger ones over NCCL" (`BL:`;
  `TF_ROCE_MAX_KB` defaults to 256 KiB, `Pc:roce.py:568`, 16 KiB a row, `P:engine.py:22-26`). Production's 512 KiB
  would keep our six- and eight-stream windows on RoCE, where it measured slower, so set the byte gate at our own
  break-even, between the four- and six-stream windows on these cells (estimate: about 16 rows, 256 KiB).
- **Confirm.** ABBA of `TF_GLM_ROCE_MULTI=0/1` on v1.2.7 at 1/2/4/6/8; `TF_GLM_PROF` gather_a and gather_b.

### 5.4 Routed experts on the item plan

- **What.** Our `patches/engine/0044-exl3-decode-items.patch` (PR #2044's two commits, not in v1.2.7): the
  router's 16-pair item plan for decode windows, as production's `grouped.route` (`P:forward.py:1281`), the
  grouped kernels in their standard mode, the down epilogue writing the slot rows in place.
- **Measured on our stack** (the patch's header, spark1-3, TP=3, drafts on, every reply digest equal): with
  `TF_GLM_KDA_PAD=1`, 63.94 / 74.66 / 93.28 / 124.59 / 150.80 tok/s without and 64.81 / 74.23 / 94.45 / 126.65 /
  154.07 with at 1 / 2 / 4 / 6 / 8 streams (+1.4 / -0.6 / +1.3 / +1.7 / +2.2%; the two-stream cell rerun ABBA
  gave +1.4%). At one stream that is about -0.6 ms a round (derived: 1.4% of 43.8). On upstream main the same
  commits measured +1.2 / +0.2 / +0.1 / +0.7 / +2.1%. A both-engines kernel bench agrees in direction (-2 to -4%
  of the routed time at 8 rows or fewer, more at wider rows: `AE:PARITY.md:828-852`) and found it bit-identical
  (0 of 2,097,152 values).
- **Files.** `zig/src/cuda/exl3_experts.zig`, `Z:cuda_exl3.zig`, the GPU check `zig/tests/cuda/glm_exl3_items_tests.zig`.
- **Confirm.** Re-measure on v1.2.7 (the patch was cut against the pin stack): `TF_GLM_PROF` routed section at P1
  and P4, the cells, digests.

### 5.5 The drafter pass as one graph, launched at the round's end

- **What.** Capture the block pass per stream count, stage its tables from pinned memory, queue one D2H of the
  candidates and projections with an event, and launch it right after the keep instead of inside the block step,
  reading it back when the lane core plans the next window.
- **Ours today.** Eager pass, pageable uploads, two synchronizing reads (`Z:dflash.zig:257-314`).
- **ms.** 0.1 to 0.2, bounded by the pad stack's capture (`NS:`): on rank 0 the drafter step is 5.95 ms, 5.79 of it
  kernels and 0.16 idle, and the host starts the next verify 0.05 ms after the pass ends, so a graph and a prelaunch
  can take out at most that idle and gap there. Production's 0.65 ms hidden by 0087 (`DrafterFable.md:64-65`) was
  Python host time, which our host does not spend. The follower side is not measured.
- **Bits.** Exact.
- **Confirm.** `TF_GLM_DFLASH2_PROF` (block ms), nsys gap between the keep's kernels and the next verify's first.

### 5.6 The keep rides the next step; followers skip the draw's read

- **What.** MIA 0031's `keep_flag` (the keep's rows in the next verify or block header) and `discard_draws` (a
  follower joins the draw's gather and does not read it). Our keep is its own step (`Z:cuda_follow.zig:288-292,414`)
  and our followers read the draw (`Z:cuda_engine_pick.zig:32-35`).
- **ms.** 0 to 0.3, estimate. On rank 0 the keep's two boundaries cost 0.02 ms a round (0.015 after the verify,
  0.004 after the keep, `NS:`); the rest is one broadcast receive with a main-stream synchronize and read a round on
  each follower, plus one synchronize-and-read a verify, which no capture measures (spark2 and spark3 hold no nsys
  file newer than 2026-11-01).
- **Bits.** Exact ("No arithmetic changes", MIA 0031).
- **Confirm.** nsys on rank 1: host gaps at step boundaries.

### 5.7 Commit and drafter ingest as one graph

- **What.** Production's `commit_taps`: one pinned table and one graph for the KDA replay, conv shift, positions
  and the drafter's context update (`P:verify.py:416-566`). Ours: `forward.commit` (`Z:cuda_forward.zig:572-599`)
  then the eager ingest with two uploads (`Z:dflash.zig:236-254`).
- **ms.** Up to 0.15: the keep step idles 0.01 ms a round and the ingest's share sits inside the drafter step's
  0.16 ms of idle (`NS:`); production measured its own version of this fix at 0.09 / 0.11 / 0.22 ms a round with a
  Python host (`DecNsysMimo.md:201-205`).
- **Bits.** Exact.

### 5.8 DFlash2 window pricing and the chain rule

- **What.** Price DFlash2 windows with load-time measured verify costs and the pass's cost (production:
  `fcost`, `P:engine.py:442-470`; `P:multi.py:1053`) instead of `copy_policy.window_costs` (52 + 6.8 ms a row,
  `Z:cuda_copy_policy.zig:5-6`), which `facts()` selects whenever a drafter is loaded (`Z:cuda_lanes.zig:100,116`);
  optionally production's edge weight and noise-aware cut (`P:dflash2.py:25-90`).
- **Why the net is small.** Production verifies 3.92 rows a round against our 3.80 (section 1.3), so there is no
  surplus of rows on our side to cut; the rule decides which drafts are offered, and its effect on one text is not
  measured. The fork's `DRAFT_EDGE=0.6` and `DRAFT_BETA=2` arms were inside the noise (`AE:reports/SPEED-REPORT.md:885-893`).
- **Bits.** Replies exact, drafts change.
- **Confirm.** Tokens a round, drafts a round and ms a round from the cell's counters, not tok/s alone.

### 5.9 MoE glue, and 5.10 HC grid

Small and bit-exact (same kernels on disjoint buffers, or the same bits on a wider grid). Under item 2 the launch
count they save stops mattering; the shared-expert overlap is the only part a graph does not give. MIA 0006
measured 70.6 to 60.6 us a MoE layer at one row on sm_120; the fork measured level at one stream on GB10.
