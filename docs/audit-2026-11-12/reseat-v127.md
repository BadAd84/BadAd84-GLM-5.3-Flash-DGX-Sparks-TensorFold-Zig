# reseat-v127.md - the fold series re-seated on v1.2.7 (lane ReseatV127, 2026-11-12)

Base `v1.2.7` = `93a2e93ecebff8aa52b88e58c5dd222516e69c5f` (tree `43eac956`), from pin `9c9bf542`. Source: the 35
fold patches (`work/fold/0001..0035-*.patch`). Everything is index and tree objects in `work/reseat/repo`; no
checkout, no commit, nothing written outside `work/reseat/` and this file.

## Result

**Ten patches re-seated, `work/reseat/0001..0010-*.patch`, covering fold 0001-0010. Fold 0011-0035 were NOT
re-seated: the run's request budget ended at step 10.** For each of those 25, `work/reseat/DECISIONS.md` gives the
survey status on v1.2.7 and the v1.2.7 facts that decide how it must be re-seated. None of them is claimed done.

| new patch | fold | decision |
|---|---|---|
| 0001-logit-gather-blocks | 0001 | KEPT; the defect is still present at v1.2.7 (`Spread.post`, one broadcast a row a rank) |
| 0002-shared-window-width | 0002 | KEPT; still present, and `window_rows` is now 32 (`6d4191a95`), so the literal 4 is 8x short |
| 0003-rows-worker-and-quiesce-drain | 0003 | KEPT; still present (5 s panic in `quiesce`, sync-only grid test) |
| 0004-prompt-bench | 0004 | KEPT, context re-seated by 3-way merge |
| 0005-ovn-knob-registry | 0005 | RE-EXPRESSED on `platform/environment.zig` `.glm` rows |
| 0006-kda-pad-one-width | 0006 | RE-EXPRESSED: only the TF_GLM_KDA_DUMP hook is ours at v1.2.7 |
| 0007-draft-knobs | 0007 | RE-EXPRESSED: nine rows, `confidence()` now fallible, Drafter literal merged |
| 0008-index-decode-windows | 0008 | RE-EXPRESSED: one row |
| 0009-kept-walk-prefix-helper | 0009 | RE-EXPRESSED onto the moved walks, a field rename, `prove()` on v1.2.7's link rule |
| 0010-ring-past-refusal | 0010 | SPLIT: any-row resume RETIRED (TF_GLM_REQUEST_STARTS), ring guard KEPT, pairing beside a drafter DEFERRED |

Every knob still defaults off. Every TF_* setting the ten patches read is now a row of
`zig/src/platform/environment.zig`: 12 new rows (`git diff 43eac956 de2e3267 -- zig/src/platform/environment.zig`),
nine `TF_GLM_OVN_*` knobs plus TF_GLM_KDA_DUMP, TF_GLM_DFLASH2_WIN and TF_GLM_INDEX_DECODE_FROM, each with a line in
`docs/environment.md`, read through `environment` and `profile.lookup`.

## Checks (full output in `work/reseat/PROOF.md` and `proof_checks.txt`)

| check | result |
|---|---|
| 1. plain `git apply --check` on the tree before, from v1.2.7 | 10 of 10 apply; each resulting tree equals `series.tsv`; final tree `de2e3267` |
| 2. line counts over all prefixes, added comments | 62 files touched, 0 over 600 at any prefix; 0 added comment lines past 120 columns |
| 3. forward references | 0 missing imports; 3 identifier flags, all words in comments or a test name (`knob`, `compares`) |
| 4. lean, each side's own `lean_check.py` | v1.2.7 6211 files / 386 problems, head 6220 / 386, **0 new** (in-memory run, no checkout) |
| 5. compile gates | **NOT RUN**: C: was at 1.7 GiB, then 0 bytes, before reaching 233 GiB at the end of the run; no budget was left for the 40-minute gate pair. What was verified by reading, per patch, is in PROOF.md. |

## Deviations from the brief, each with its reason

1. **Fold 0010 is not re-expressed by feeding the cache's marks into `cuts`.** With `snap_grid` kept, v1.2.7's
   planned cache puts every mark on the grid or a request start, which are already cuts, so the feed changes
   nothing. With `snap_grid` removed (old 0007's form), each kept state's `below` digest records its own pass's
   resume point, and the next turn's `resumes()` refuses it as SnapshotOutOfStep from the third turn on. Carrying a
   state's cut list forward would break upstream's resumed == fresh contract. Upstream's own TF_GLM_REQUEST_STARTS
   already keeps and resumes at the request's message starts (9347a8a7d, f3988faa7, c5d45eee8, 3464a7d44; "58,735
   instead of 57,344" at TP=2), so the any-row lever is RETIRED, with old 0024/0028/0034/0036/0045/0048/0063 and the
   ringsAgree half of 0042/0043. The two things to measure are in DECISIONS.md: REQUEST_STARTS against the old
   any-row receipts, and the pairing loss with cuts.
2. **The registry is per lever.** Each patch adds the rows of the knobs it reads (a switch arrives with its
   reader), and `ovn.zig` makes a knob without a row a compile error.
3. **Stage 1's file splits were not needed for fold 0001-0010.** No file passes 600 at any of these ten prefixes;
   the splits the drift report projects (cuda_follow 618, cuda_native 617, tokenizer 615, tests/cuda/main 606) come
   from fold 0012, 0027 and 0035, which were not reached.

## Findings made while re-seating (each in the patch header and DECISIONS.md)

- **fold-series.md F8 is wrong**: TF_GLM_OVN_KEPT_WALK is a real switch (`prompt_prefix.gated()`); off, every walk
  asks exactly as before.
- **Fold 0006 carried a prefix compile defect**: `body()` called the 14-parameter `bodyProfile` with 13 arguments
  from fold 0006 to 0022 (old 0003's port artifact, undone by old 0019). The re-seat does not carry it.
- **v1.2.7's `Entry.seen` collides with fold 0009's field of that name**; renamed `Entry.proved`.
- **v1.2.7's `link()` links equal-born entries**; the gated `prove()` had to follow, or KEPT_WALK=1 would drop
  those links and change eviction choices.
- `dflash.confidence()` can fail at v1.2.7 (`c632a57f0`); the fold's `orelse dflash.confidence()` would not compile.

## Class (c) and the instrument, checked at the tag

- 0001 logit gather: still present (`cuda_sampler.zig` has no commit in range).
- 0002 shared-window width: still present, and larger (`window_rows` 32).
- 0003 rows worker and quiesce drain: still present (`health_test.zig:238`, `rows_test.zig:18`).
- 0004 prompt-bench: applies; its server surface (`plain`, `chat.prepare`) is unchanged in shape.

## What exists

`work/reseat/`: the ten patches, `series.tsv`, `DECISIONS.md` (all 35 fold patches), `PROOF.md`,
`proof_checks.txt`, `survey.log` (all 35 carried naively, for the status of 0011-0035), the tools (`lib.py`,
`reseat.py`, `series.py`, `series_def.py`, `emit.py`, `checks.py`, `refs.py`, `leanmem.py`, `survey.py`), the hand
edits under `ovl/`, and `repo/` (the scratch clone, a few MB of objects; never gc it while `ovl/` is in use).

## Continuation: fold 0011-0035 (lane ReseatV127b, 2026-11-12)

**The whole fold series is re-seated or decided: `work/reseat/0001..0033-*.patch`, final tree
`93a99447e7030697ca29b93cc1410871bb34c98a`, every check green, including the compile gates.** Of the 25 fold patches,
20 are carried (6 KEPT or KEPT*, 14 RE-EXPRESSED, one of those with a part DEFERRED), three new split patches
keep every file at or under 600 lines at every prefix, and five fold patches are not carried (one RETIRED, four
DEFERRED, each with its measurement). Per-patch reasons and v1.2.7 line citations: `work/reseat/DECISIONS.md`;
check output: `work/reseat/PROOF.md`. The first compile of 0001-0010 found two defects there; both are fixed (below).

| new | fold | decision |
|---|---|---|
| 0011 ovn-check-table | - | NEW (split): `zig/tests/cuda/main.zig` 598 -> 597; the GLM OVN check commands in `glm_ovn_checks.zig` |
| 0012 exl3-decode-items | 0011 | KEPT*: PR #2044 is not in v1.2.7; only main.zig's dispatch line moved |
| 0013 forward-pieces-split | - | NEW (split): `row_step`, `max_pieces`, `ranges()`, `Pieces` to `cuda_forward_pieces.zig`; `cuda_forward.zig` 600 -> 544 |
| 0014 index-sched-decode-pools32 | 0013 | RE-EXPRESSED: three rows; 0008's registry read kept |
| 0015 index-regroup | 0014 | RE-EXPRESSED: one row |
| 0016 lanes-step-split | - | NEW (split): `Lanes.prefillStep` to `cuda_lanes_step.zig`; `cuda_lanes.zig` 600 -> 570 |
| 0017 plain-margin | 0016 | RE-EXPRESSED onto v1.2.7's `facts()` and `depth_constants.zig` |
| 0018 exchange-kb | 0017 | KEPT, one row |
| 0019 router-warm | 0018 | KEPT*, one row (max 2) |
| 0020 win-free | 0019 | RE-EXPRESSED onto `window_costs_lone`; the fold's dead `Config.first_tree` dropped |
| 0021 sparse-onepass | 0020 | RE-EXPRESSED: its `ranges()` move not needed after 0013 |
| 0022 onepass-pipe | 0021 | RE-EXPRESSED: five rows; `Mla`'s four unported knob reads and two dead fields dropped (F9) |
| 0023 kda-chunked | 0023 | RE-EXPRESSED onto `cuda.kda` (`5b80e93ac`); `cuda_kda_chunk.zig` comes with it (F12 fixed); the 32-row snap grid dropped |
| 0024 mm-knobs | 0024 | RE-EXPRESSED onto `glm_swiglu.cuh`'s `swiglu1<AFTER>` (`88267c063`) and the single router tile (`c0f8e1c4c`) |
| 0025 mla-knobs | 0025 | KEPT*: the OVN copies still mirror `common/mla.cuh`'s default instantiation |
| 0026 glue-fuse | 0026 | RE-EXPRESSED, PART DEFERRED: router and SwiGLU `_pdl` twins not carried; KVB8 moved onto the live `Mla.wanted()` |
| 0027 head-block-rule | 0029 | KEPT |
| 0028 head-flag | 0030 | RE-EXPRESSED: the MULTI_FILL absorb site goes with the era |
| 0029 exl3-chunk-rows | 0032 | KEPT |
| 0030 exl3-dec-order | 0033 | RE-EXPRESSED: TF_EXL3_DEC_ORDER a `.cuda` row (was a getenv) |
| 0031 memo-equal-strindex | 0034 | RE-EXPRESSED: v1.2.7's `min_bytes` 64 kept |
| 0032 fp8-tile-ahead | 0031 | RE-EXPRESSED into `common/mla.cuh`'s `chunks_wide` (`42735f94f`) by a function-level 3-way merge |
| 0033 render-once-host-once | 0035 | RE-EXPRESSED: TF_GLM_OVN_HOST_ONCE a row; `encodeSegments` into `kept.zig` (`tokenizer.zig` 615 -> 580) |

Not carried:

- **fold 0022 shared-drafts: RETIRED** by `cc2fa8d23` (`.allocate_shared_drafts = drafting and !block`,
  `cuda_lanes.zig:103`, +3.7% four-stream at TP=2) for a drafter serve, and contradicted for the MTP head by
  `d7d559944` (allocator on, capped at 3, `:17`/`:119`; 19-50% under main without the cap).
- **fold 0012 reply-prefill: DEFERRED.** Its capped 256-row chunks cannot step at v1.2.7 (`stepRows` needs a cold
  cut, `cuda_prompt_cuts.zig:53-54`) and the reply's end is not a cut of the next request, so carried it is dead
  code. Main's turns instrument (below) bounds what it could buy at the 11k shape: about 150-190 ms a turn.
- **fold 0015 one-chunk and fold 0028 its wiring: DEFERRED.** v1.2.7 keeps states only where a chunk ends, and
  `resumes()` refuses anything else, so a capture inside a chunk has nothing to keep. Measure first what cutting at
  request starts costs a cold agent prefill (REQUEST_STARTS=1 against 0).
- **fold 0027 shared-round era: DEFERRED** (28 files, +2,007/-85, six unmeasured knobs on a `facts()` and
  shared-round dispatch upstream rewrote). **COST_TIME is not redundant**: it times prices only with a DFlash2 drafter,
  while v1.2.7's load-time pricing feeds MTP only (`cuda_lane_cost_measure.zig:1`, `facts()`'s
  `costs = if (block) null`, and `55a95af06` keeps DFlash2's shared rounds on main's constants). Its MULTI_FILL resume
  path is dead at v1.2.7 (`prefillManyFn` refuses kept states, `cuda_lanes.zig:218`). What decides it: each knob
  against off on the image that carries the era (`ai-engine:all1`), five levels, digests equal; port only winners,
  COST_TIME first, as a drafter mode of `cuda_lane_costs.zig`.

### The any-row decision, now measured

Main's `scripts/turns.py` (rows read from spark1 `~/bench/turns/{v127,v127rs,all1}.out` at 16:38 UTC: an 11,273-token
chat, four turns each adding the reply and a short user message, run twice):

| arm | turns 2-4 resume at | first token, turns 2-4 | exact repeat (chat 2) | cold |
|---|---|---|---|---|
| v127 (REQUEST_STARTS off) | 10,240 | 943-999 ms | 823-999 ms | 8,596 ms |
| v127rs (TF_GLM_REQUEST_STARTS=1) | 11,260 | 211-254 ms | 102-252 ms | 8,776 ms |
| ai-engine:all1 (any-row) | 11,270 / 11,333 / 11,357 | 190-249 ms | 62-66 ms | 7,711 ms |

REQUEST_STARTS gives back most of the any-row win on the agent's next turn, which is what the RETIRED verdict for
fold 0010 rests on; what it leaves is the tail since the last kept start (GLM thins starts to 256 rows apart, so it
stayed at 11,260 for three turns) and exact repeats. Still unmeasured: the same at 31k and 650k, and the pairing loss
with cuts (PORT-LEFTOVER S6). all1's cold prefill is 10% faster than v1.2.7's; that is the old stack's levers and
is not explained by any patch decided here.

### Defects found while re-seating (each fixed, each in its patch header)

- **0005 never compiled**: `ovn.zig:6:19` (`Cache`'s `key` unused) and `:22:36` (`set`'s `text` shadows `ovn.text()`).
  Found by the first gate run of 0001-0010; with the fix 0001-0010 pass every gate.
- **0004 failed `zig fmt --check`**: the fold aligned `prompt_bench.zig`'s `sites` table for 0035's longer table.
- **Fold F9 is reversed**: `Kernels.load` calls `Mla.wanted()`; the second `read()`/`wanted()` pair inside `Kernels`
  is the dead one, and old 0041's KVB8 term sat on it, so TF_GLM_OVN_KVB8 alone loaded null OVN handles.
- **Fold 0019 (win-free) carried `Config.first_tree`**, a field nothing reads and no `Model` field feeds.
- **The first form of the ranges move** (fold 0020's, into `cuda_forward_pair.zig`) shadowed that file's `pieces`
  (gate run `reseat21`); replaced by 0013.
- **A `.cuda` row needs a line in `environment_test.zig`'s `valid` table**: the coverage test failed until
  TF_EXL3_DEC_ORDER's forms were added (0030).

### Checks (PROOF.md, second section)

| check | result |
|---|---|
| 1. plain `git apply --check`, prefix by prefix from v1.2.7 | 33 of 33; every tree equals `series.tsv`; final `93a99447` |
| 2. line counts at every prefix; added comments | 146 files, 0 over 600 at any prefix; 0 added comment lines past 120 columns (longest exactly 120) |
| 3. forward references | 0 missing imports; 5 identifier flags, all words (`knob`, `compares`, `onepass` in a string and a field name) |
| 4. lean, each side's own `lean_check.py` | v1.2.7 6211 files / 386 problems, head 6253 / 386, **0 new**, no getenv finding |
| 5. compile gates, `scripts/gates.sh` (C: 229-233 GB free) | v127base green; 0001-0010 green after the two fixes; final tree green on every step, fmt rc=0; `gate-names.sh v127base reseat`: 0 failing names on either side |
| 6. CUDA units, this workstation's nvcc 13.3 with the build's flags | all 10 units the series touches compile (`glm_glue`, `glm_mm`, `mla`, `glm_kda_chunk`, `glm_onepass`, `glm_onepass_pipe`, `glm_index`, `glm_ops`, `exl3_experts`, `glm_l2pf`); ptxas gives 0032's chunk kernels 148/148/150/128/128 and 194/194/213/163/163 registers, `pending_133.zig`'s numbers exactly (v1.2.7: 64 x5, 128/128/127/130/130); neither spills |
| 7. every prefix compiles | `check-native-cuda-host` rc=0 on all 32 prefix trees; the same command on the broken earlier form fails (`rc=1`, the `pieces` shadow), so the run can fail |

The kernels are compiled, not run: their bytes and the knobs' effects need the GPU receipts each patch header names,
which this lane does not take (no GPU work, by its brief).

### For Main's round-time finding

Production's one-stream round is 31.9 ms against ours 44.5 ms because it overlaps the drafter with the verify
(`docs/OVERNIGHT-2026-11-12.md` section 11). No carried lever overlaps the drafter with the verify. The levers on the
draft/verify path are marked in DECISIONS.md: 0007 (drafter), 0012, 0014 (DECODE_INDEX), 0017, 0020, 0024
(MM_DECTILE, MM_CLUSTER, ROUTER16), 0025, 0026 (GLUE_FUSE, PDL_EARLY: launch overlap inside a pass, with its router and
SwiGLU twins deferred), 0030, and the deferred era. None of them has a GPU receipt on v1.2.7 yet.

### Tooling added (work/reseat/)

`series_def2.py` (the 23 new steps, each with an anchored `fix`), `fx.py` (anchored edits and conflict-block picks
that assert their anchors), `mf.py` (function-level `git merge-file` for code upstream moved between files),
`conf.py` (a step's conflicts in diff3 form with the default style's block count), `probe.py`, `show.py`,
`heads.py`, `counts.py`, `comments.py`, `gate_tree.sh` (git archive of a tree object, then `scripts/gates.sh`),
`fmt_diff.sh`, `envtest.sh`, `nvcc_check.py` and `spill_check.py` (the CUDA units with the build's nvcc flags, ptxas
registers and spills), `prefix_compile.sh` and `one_compile.sh` (every prefix, and the control that the command
fails). `reseat.py --emit` rebuilds all 33 patches from v1.2.7 in about 40 seconds.
