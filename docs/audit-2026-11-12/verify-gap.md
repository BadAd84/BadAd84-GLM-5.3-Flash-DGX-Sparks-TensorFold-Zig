# VerifyGap, 2026-11-14: where the 2- and 4-stream round goes against production, and the lever

CPU only. Inputs: rank 0's fresh exports on spark1 `~/nsys/rec-p{1,2,4}.sqlite` (queue17, 06:21-06:26 UTC; image
`glm53-zig:rs2`, tree `4ed20ea3d175`, `KNOBS=measured`: the ten DEFS plus the RoCE wire at 4 streams or fewer; warm-up
cell, then one 400-token `streams.py` cell, chat prompts), copied here, read, then deleted (restore:
`scp adam@spark1:'nsys/rec-p*.sqlite' spark1/nsys/`); our ids cells `ids-rec`, `ids-rec-b`, `ids-c7` (copied to
`spark1/bench/`); production's cells on the `production` branch; production's boot log and P2 counters
(`../drafter-lever/spark1/bench/prodprof/`). Every script prints its SQL; every output is kept (`*.out`).

## 1. One decode round of the current recipe, rank 0, ms a round

Rounds where every stream decodes (one keep step a stream): 149 at P1, 156 at P2, 160 at P4. `stages.py` cuts the main
stream (18) at each `tf_glm_put_words` (verify, keep, drafter steps), the verify into 45 layers at its first 90
all-gathers (`tp_roce_multi`, or `ncclDevKernel_AllGather*`), a kernel's stage by position and name; busy is the union of
kernel, memcpy and memset intervals. `evidence2.py` re-measures each name-unique stage with one SQL query over the same
round windows (TEMP table `win`), and agrees to the microsecond (`evidence2.out`).

| stage | P1 | P2 | P4 | evidence |
|---|---:|---:|---:|---|
| rows in the verify | 3.76 | 6.05 | 11.74 | `tf_glm_top1` a verify |
| **round** | **37.73** | **52.74** | **80.51** | put_words to put_words |
| verify step | 34.10 | 48.31 | 75.06 | |
| - routed experts (42) | 19.50 | 31.47 | 53.91 | `s.value like 'tf_exl3%' or s.value = 'plan_kernel'` |
| -- of which the two `tf_exl3_grouped_1` launches | 18.54 | 30.20 | 52.35 | `routed.out` |
| - shared expert | 1.51 | 1.57 | 1.63 | position (FFN, not router or routed) |
| - router | 0.59 | 0.61 | 0.60 | `router_tile`, `slice_sum`, `topk` in the FFN |
| - dense FFN (3 layers) | 0.32 | 0.33 | 0.31 | position |
| - KDA projections (34) | 3.44 | 3.52 | 3.89 | position (mixer, not chain) |
| - KDA chain, one per stream (34) | 1.05 | 1.75 | 2.97 | `s.value in ('tf_glm_kda_prep', 'tf_glm_kda_step', 'tf_glm_kda_out')` |
| - MLA projections, norms, indexer, absorb, expand (11) | 2.01 | 2.15 | 2.40 | position |
| - MLA attention, one per stream (11) | 0.37 | 0.65 | 1.29 | `lat_write_fp8, index_write, pool_keys, merge, chunks*` |
| - HC glue (`hc_partial8`, `hc_finish`, `hc_post`) | 1.62 | 1.92 | 2.57 | `s.value in (...)` |
| - head and draw (final norm, head, `top1`) | 1.01 | 1.04 | 1.06 | after the 90th gather |
| - layer all-gathers: the step's first (waits for ranks 1, 2) | 0.32 | 0.46 | 0.38 | `gathers.out`: p10 0.14-0.19 ms |
| - layer all-gathers: the other 89 | 1.51 | 1.92 | 2.95 | median 11.9 / 13.0 / 18.0 us each |
| - draw gathers (one per stream) | 0.02 | 0.04 | 0.08 | |
| - GPU idle inside the verify | 0.94 | 0.87 | 0.92 | span less busy; host-bound share <= 0.05 (`launchbound.out`) |
| keep steps (one per stream) | 0.23 | 0.41 | 0.75 | |
| - KDA replay (`tf_glm_kda_replay_layers`, 0.42 ms each) | 0.20 | 0.35 | 0.63 | 0.5 / 0.9 / 1.5 a round |
| drafter step | 3.40 | 4.03 | 4.71 | |
| - context ingest (fc, 5 k/v) | 0.45 | 0.46 | 0.48 | |
| - block linears (4-bit `group_kernel` + sums) | 1.60 | 1.65 | 1.88 | |
| - block attention | 0.12 | 0.19 | 0.35 | |
| - MLP split gather 1 (waits for ranks 1, 2) | 0.24 | 0.59 | 0.65 | wire at P1/P2, NCCL at P4 (512 KiB > the wire's 256) |
| - MLP split gathers 2-5 | 0.15 | 0.25 | 0.34 | |
| - draft head + top16 | 0.52 | 0.56 | 0.64 | |
| - norms, conv, swiglu, candidates gather, selector, words | 0.15 | 0.16 | 0.15 | |
| - idle inside + tail (2 readbacks, select, verify launch) | 0.16 | 0.16 | 0.21 | |
| L2 prefetch side stream (overlapped, not in the round) | 6.03 | 6.31 | 6.72 | `k.streamId = 20` |

Sampling (the draw) is `top1` + draw gathers + one sync and read a stream on every rank (`cuda_engine_pick.zig:15-41`):
1.03 / 1.08 / 1.14 ms with the head. Host gaps on rank 0 are the step tails, 0.19 / 0.19 / 0.26 ms a round; rank 0's
host launches the verify a median 13.9 / 17.1 / 26.3 ms ahead of its GPU (`launchbound.out`), so the verify is GPU-bound.

**How the stages scale** (rows x1.61 then x3.12 against P1; streams x2 and x4):

- Linear in rows: the routed experts, 3.87 / 3.90 / 3.15 ms a row inside each capture; their intercept grows with
  streams (rows from different streams share fewer experts: at equal rows two streams cost 2.6-4.4 ms more than one,
  P2 against P1 at 5-7 rows). Sublinear: projections, HC glue (x1.19, x1.59), the other gathers (x1.28, x1.96).
- **Superlinear in rows, because they scale with streams**: MLA attention x1.79 / x3.55, keeps x1.78 / x3.25, the KDA
  chain x1.67 / x2.83 (+ its launch gaps 0.20 / 0.34 / 0.53), and the drafter's first MLP gather x2.43 / x2.65: the
  followers' lag, which grows with the keep steps each must receive (`waits.out`: 300 / 694 / 707 us in rounds with no
  KDA replay at 1 / 2 / 4 keeps). Together 2.43 / 4.26 / 6.66 ms a round.

## 2. Production at 2 and 4 streams, as far as its data goes

No production capture or round counter exists at P2 or P4 (its round profile line never printed:
`docs/audit-2026-11-12/round-structure.md:173-178`; `pyprod` P4 has no counters). What is bounded (`prodround.out`;
assumption A1: a stream's tokens a round in a shared round equal its one-stream value, prose 3.000 for production on
133 rounds, `accept-gap.md:29-36`; 3.142 for ours on prose33):

- **P2**: production's 2-stream round **50.4-50.8 ms** (prose 59.0-59.47 tok/s, `production/target/pyprod/P2.jsonl`)
  at **6.62 rows** (prodprof-P2's 727 drafted / 466 accepted, `prodprof/P2.jsonl`); check: story's lone tail then comes
  out at 30.8-31.1 ms a round at 2.70 rows, in line with its one-stream column. Ours: 52.74 ms at 6.05 rows (capture),
  55.2-55.6 ms at 6.50 rows (ids cells, same method), **55.2 ms at 6.62 rows: +4.5 ms (+8.9%)**.
- **P4**: production's 4-stream round **80.3-80.5 ms**; its streams then keep 3.000 / 2.875 / 2.527 / 2.006 tokens a
  round (story's 2.006 equals its P2 value 2.005, an independent check), 10.41 a round, at **~13.9 rows** (13.6-14.4
  for acceptance 0.59-0.69 on facts and prose2). Ours: 80.51 ms at 11.74 rows, ~9.7 tokens; at 13.9 rows 88.6 ms
  (slope) or 88.9 (the 14-row verify bucket, 83.4 ms, + drafter + keeps): **+8.2-8.5 ms (+10%)**.
- One-stream verify by rows (boot log `prodprof/log-P2.txt:65`, one-stream graphs): 24.82 / 29.20 / 33.70 / 37.45 /
  41.15 / 44.43 / 48.22 ms at 2-8 rows; ours (P1 capture) 26.4 / 30.8 / 35.4 / 39.9 / 43.5 / 47.1 / 52.1: +1.6 at 2-4
  rows growing to +2.4-3.9 at 5-8 (production's served dense set sits ~0.9 above that column).
- Drafter pass by streams (`int-docs/notes/drafter-pass-DrafterFable.md:25-34,80-85`, October image): 1.88 / 1.97 /
  2.14 / 2.29 ms at 1-4 streams after its fusions, + a 0.30-0.38 ms taps update and ~0.3 ms of RoCE gathers: about 2.6
  at P2 and 3.0 at P4, growing 0.18 ms a stream. Ours 3.40 / 4.03 / 4.71 (+0.63, +0.68): **+1.4 at P2, +1.7 at P4**,
  of which the first MLP gather's wait 0.59 / 0.65 and the linears' efficiency (ours ~2.2-2.5 ms for the 4-bit
  linears and head against production's ~1.55-1.75 at 89% of roofline).
- Structure where ours grows faster per stream: production runs one launch per kernel over all streams
  (`work/accept-gap/prod/forward.py:790-812` `kda_segments` -> `chain_segments`; `:1181-1233` `dsa_segments`, `seg_*`),
  one commit graph replaying every stream (`verify.py:405-406,456-457`), one message a round; ours launches the KDA
  chain and MLA attention once per stream (`cuda_shared.zig:52-86`), a keep step and a draw sync per stream, and every
  follower receives each step with a sync and read (`cuda_follow.zig:117-130`). Our per-stream work grows 1.83 ms
  (1 -> 2) and 2.40 ms (2 -> 4); production's equivalent is about the KDA state bytes, ~0.4 ms a stream.
- Not bounded: production's verify split by stage at 2 or 4 streams, its routed time, gathers and glue there.

So at equal rows the 2-stream round is ~4.5 ms behind (verify ~3.6, drafter ~1.5, our keeps against production's commit
and host ~-0.6; production's host share from its October four-stream round, DrafterFable.md:70-71) and the 4-stream
round ~8 ms (verify ~7, drafter ~1.7, keeps/host ~-0.75). The bench cells add admission: our capture's P4 cell fills its
four prompts one at a time (prompt steps 142 + 180 + 182 + 200 = 704 ms; the fourth stream decodes from 905 ms) where
production fills them together (TTFT 225-228 ms); P2 320 ms against ~158. That is up to 0.48 s of the P4 cell's 1.6 s
wall gap and 0.16 s of P2's 0.93 s, outside the round.

## 3. The lever: the routed experts on production's decode kernel path (the X3 set)

**Evidence.** The hot frame at 2 and 4 streams is `tf_exl3_grouped_1`: 30.20 / 52.35 ms of the 52.74 / 80.51 ms round
(57% / 65%; the routed stage 31.47 / 53.91 ms, 3.90 / 3.15 ms a row). It runs none of production's decode-kernel
settings: block order 0 (grid x = items: 38 / 95), 4-byte nc loads one tile ahead (`exl3_decode.cuh:55-65`, upstream
8d46e2906), the input rotated once per pair (`tf_exl3_experts_rot_in`, 10.0 / 14.7 us a layer) and a separate down
epilogue (`tf_exl3_down_combine`, 8.9 / 12.8 us). Production serves `TF_GLM_EXL3_DEC_ORDER=1`
(`production/launch/v110ots.env:14`), `EXL3_LOADS=nc` and its fused down and row rotation (`docs/speed_target.md:90-91`).
The fork measured the same kernels both ways on one GPU (`ai-engine docs/PARITY.md:828-852`): ours on the item plan
+5% / +7% against production's routed path at 24 / 48 rows of 44 hot experts, +3% uniform at 64 rows, more in lockstep
shapes; with the X3 set (DEC_ORDER + X3_NC + X3_XROW + X3_FUSEDOWN) it matches production (0.905 vs 0.915 ms, 0.236 vs
0.249). Its serve ABBA on the item plan: **+4.7 / +4.6 / +4.9 / +4.5 / +4.6% at 1/2/4/6/8 streams, every digest
equal** (`SPEEDUPS.md:154-157`). This repo ported DEC_ORDER only (0030, never measured here) and left X3_NC / XROW /
FUSEDOWN out (`git show efe9655:docs/PORT-LEFTOVER.md`, lines 48-50).

**Expected.** The fork's figures predate upstream's load-ahead in our kernel (8d46e2906 is not an ancestor of the
fork's ITEMS runs, `b099d3ce8`), which #1505 measured at +0.5-0.7% (`SPEED-REPORT.md:654`). Less that share:
**P2 -1.1 to -2.0 ms a round (+2.1 to +3.9%, 80.81 -> ~82.5-84.0 tok/s), P4 -1.9 to -3.2 ms (+2.4 to +4.2%, 105.47 ->
~108-110 tok/s)**; the low ends are the bench's 5% gap less ~1.5 points for the load-ahead (3.5% of the routed stage),
the high ends the serve ABBA less 0.7 points. Floor from our own kernel times, XROW and FUSEDOWN alone (rotation once a
row ~3 us, the fused epilogue a fifth of its launch): 0.6 / 0.9 ms. Against production that is -9.4 -> -5.9 to -7.5% at
2 streams and -10.6 -> -6.8 to -8.5% at 4. It also applies at 1, 6 and 8 streams (the stage is 52-67% of every round)
and frees per-row cost, which our window planner prices: at P4 it now verifies ~2.0 drafts a stream against
production's ~2.5. Bits: unchanged by construction (same chains, tiles and sums; the fork's GPU check compares every
variant with the plain decode, 0 of 3,984 values differ).

**Not built here**: a CUDA port (new `exl3_ovn.cuh`, its entry points, the launcher) whose only gates are the image
build on spark1 and a GPU check, so it is not a contained host-tested change. Design:

- Source: the archived fork's `7d41fa9b7` (X3_NC 1|2|w, X3_FUSEDOWN, X3_XROW; 552 lines), `ca8479639` (X3_NC=w on the
  plain walker), and the item-plan plumbing of `ovn-items` (`769c8cfca`: the decode arena sized for the 9-slot layout;
  the X3 variants on items in `b099d3ce8`). Not `95a3e51cb` (ROTEXPERT, a numerics trade). One numbered patch,
  `0034-exl3-x3-decode.patch`, `RECORD.md` naming the commits and the Apache-2.0 source of the 16-byte staged loads
  (TensorFold glm5_next `exl3.cu` dec_kernel LD 1, jayleaton 0580).
- `zig/kernels/cuda/exl3_ovn.cuh` (new): `OvnTail`/`OvnArgs`, `ldg_nc_v4`, the staged walker, the fused down epilogue,
  the row-rotation read. `zig/kernels/cuda/exl3_experts.cu`: the `tf_exl3_ovn_*` entry points beside today's, keeping
  `GROUPED_LOAD` (AHEAD) on the plain path and the `ord` swap on both.
- `zig/src/cuda/exl3_experts.zig`: `Ovn` (loads off|nc1|nc2|word, fuse_down, xrow) and `runWith` on items launching the
  variants (`rot_in` a row under XROW, the down launch writing ey's slot rows under FUSEDOWN, no `down_combine`).
  `zig/src/families/glm/cuda_exl3.zig`: the per-matrix trellis bases (gb, ub, db) and the knobs read at load.
  `zig/src/families/glm/cuda_state.zig`: the 9-slot decode arena.
- Knobs through the series' OVN registry (`zig/src/cuda/ovn.zig`, patch 0005), so the fork's `cuda.ovn.text("X3_NC")`
  and `cuda.ovn.on(...)` calls stand as written: three `.glm` rows of `zig/src/platform/environment.zig`,
  `TF_GLM_OVN_X3_NC` (text, forms 0, 1, 2 or w), `TF_GLM_OVN_X3_XROW` and `TF_GLM_OVN_X3_FUSEDOWN` (flags), all default
  off, with `cuda_env_test.zig`'s row check and the OVN check table (0011). `TF_EXL3_DEC_ORDER` stays as 0030 has it.
- Checks: `zig/tests/cuda/glm_exl3_ovn_tests.zig` (every variant against the plain decode's ey, items on, widths 640
  and 768, lockstep and distinct windows) registered in `zig/tests/cuda/main.zig`, with the fork's planted control
  (members one slot off) shown failing; host tests for the knob forms and the arena sizes, with mutants (X3_NC=2 read
  as 1, the arena one slot short); `scripts/gates.sh`, `scripts/gate-names.sh` against `rs2`'s tree, `scripts/lean.sh`
  base against head (`exl3_experts.zig` is 387 lines today, the 600 limit holds).

**Arms** (`arms-client.sh`: `arms-file.sh`'s line format run through `bench-client.sh` / `streams_ids.py` on top of
`KNOBS=measured`; its stub test passes and kills both planted mutants, `test-arms-client.sh`, `mutant-arms-client.sh`):

    # rung 1, image glm53-zig:rs2, nothing to build (arms-x3-r1.txt): bash arms-client.sh /dev/null "" arms-x3-r1.txt glm53-zig:rs2
    x3o-ctl|||1 2 4 6 8|1
    x3o-ord|-e TF_EXL3_DEC_ORDER=1||1 2 4 6 8|1
    x3o-ord-b|-e TF_EXL3_DEC_ORDER=1||1 2 4 6 8|1
    x3o-ctl-b|||1 2 4 6 8|1
    # rung 2, image glm53-zig:rs2x3 = the series + 0034, built and on all three hosts (arms-x3-r2.txt);
    # add -e TF_EXL3_DEC_ORDER=1 to both test lines only if rung 1 held at every level
    x3-ctl|||1 2 4 6 8|1
    x3-on|-e TF_GLM_OVN_X3_NC=1 -e TF_GLM_OVN_X3_XROW=1 -e TF_GLM_OVN_X3_FUSEDOWN=1||1 2 4 6 8|1
    x3-on-b|-e TF_GLM_OVN_X3_NC=1 -e TF_GLM_OVN_X3_XROW=1 -e TF_GLM_OVN_X3_FUSEDOWN=1||1 2 4 6 8|1
    x3-ctl-b|||1 2 4 6 8|1

Each test cell is read against the control beside it; replies equal to the control's at every level; `x3-ctl` equal
to rs2's recipe cells and digests. Then the frame itself: `IMAGE=<image> KNOBS=measured XENV="<test -e list>" bash
nsys-rank0.sh x3-p4 4`, the export as `queue17.sh` does it, and `python routed.py x3-p4.sqlite 4` against
`routed.out` (gate/up 832.9 and down 413.6 us a MoE layer at 4 streams).

## 4. The other levers, ranked (ms a round at P2 / P4)

| lever | P2 | P4 | basis |
|---|---:|---:|---|
| per-stream KDA chains and MLA attention run concurrently (side streams; production's segment kernels in effect) | <= 0.68, ~0.5 | <= 1.84, ~1.5 | `segspan.out`: hideable span a layer; KDA bound by state bytes; needs per-segment wide q/y offsets and MLA partials (`cuda_state.zig:230`, sized for one segment), serial when a segment is sparse |
| keep steps folded into the drafter step, followers skip the draw read (MIA 0031) | ~0.45 | ~0.5 | the drafter's first-gather wait 0.59 / 0.65 ms; followers not captured |
| drafter linears at production's efficiency (and its attention split) | ~0.6 | ~0.7 | linears + head 2.21 / 2.52 ms against ~1.65-1.75 |
| prompt admission: waiting prompts in one fill (bench cells only) | 0.16 s a cell | 0.48 s a cell | `timeline.out` |

## 5. Status

No patch built (section 3). Written here: the probes (`stages.py`, `table.py`, `evidence2.py`, `routed.py`,
`segspan.py`, `gathers.py`, `waits.py`, `hostrt.py`, `launchbound.py`, `timeline.py`, `kdastep.py`, `keepgaps.py`,
`steps.py`, `seq.py`, `explore.py`, `prodround.py`), their outputs (`*.out`, `spark1/nsys/*.rounds.json`), the arms
runner and its test and mutants, the arms files. The read tree (`setup.sh` rebuilds it) and the WSL scratch are removed.
