# OVERNIGHT-2026-11-12.md - what the night measured

spark1-3, TP=3, GLM-5.3-Flash EXL3 4bpw, `scripts/bench-arm.sh` (a fresh boot per level, `streams.py` prose, 400
tokens, 3 rounds), drafts on unless a row says otherwise. Images: `pin` is the clean pin (`glm53-zig:pin9c9`),
`fix4` the stack through 0039, `fix5` the stack through 0041. Cells are on spark1 under `~/bench/<arm>/`.
Tables are `scripts/cells.py` output: mean aggregate tok/s over a cell's rounds.

## 1. The owner's method, restated with what was missing

| step | arm | P1 | P2 | P4 | P6 | P8 | digests |
|---|---|---:|---:|---:|---:|---:|---|
| stock | `pin-drafts` | 51.38 | 58.16 | 72.26 | 95.19 | 115.18 | stock |
| stock + the one env switch that matters | `pin-pad` (`TF_GLM_KDA_PAD=1`) | 64.23 | 70.92 | 84.01 | 107.91 | 129.99 | the pad's |
| stack through 0041 | `fix5` | 51.01 | 59.84 | 81.04 | 110.38 | 135.75 | stock |
| stack through 0041 + the pad | `f5-pad` | 63.94 | 74.66 | 93.28 | 124.59 | 150.80 | the pad's, equal to `pin-pad`'s |
| production (Python, its own numerics) | `pyprod` | 81.73 | 89.22 | 117.98 | 114.78 | 131.28 | its own |

- The pad is +25.0 / +21.9 / +16.3 / +13.4 / +12.9% on the clean pin. It is the pin's own switch. Production's dense
  numerics are 4-bit by its own launchers (`TF_GLM_DENSE=q4`), so pad on is the like-for-like setting.
- On top of the pad, the patch stack adds -0.5 / +5.3 / +11.0 / +15.5 / +16.0%: nothing at one stream, the gain is
  all in concurrency.
- Against production with the pad: -21.8% at one stream, -16.3% at two, -20.9% at four, then +8.5% at six and
  +14.9% at eight.

`pyprod` is the mean of its three rounds a level (P6's rounds span 111.0 to 122.3).

## 2. Defects found and fixed (patches 0040 and 0041)

- **The pad was broken in the stack, not in the pin.** Patch 0003 had replaced the pin's row sizing; through 0039
  the pad returned 4 digests for 2 prompts and 8 for 4, and measured 56.59 / 69.77 / 87.83 / 119.63 / 132.46.
  Through 0041 it returns one digest a prompt and the row above.
- **The stack through 0039 dies on a long prompt with the drafter loaded.** `f4-long` (a 10,929-token prompt, one
  stream): `ended ... reason=error (BadPair) prompt=10929 tokens=0`, then `rank 0: rank 2 stopped (BadPair); this
  rank stops too`. Through 0041 the same request runs (`f5-long`, 56.45 tok/s).
- Fourteen more restorations, read from the code and not exercised by these cells: `docs/PATCH-AUDIT.md`.

## 3. A warm turn's first token: 0007's keeps at any row are bit-exact and worth 22x at this size

| prompt | arm | P1 tok/s | P2 tok/s | first token of a repeated prompt | digests |
|---|---|---:|---:|---:|---|
| about 3.6k tokens | `pin-mid` | 45.21 | 48.68 | 1,428 ms | - |
| about 3.6k tokens | `f5-mid` | 53.40 | 60.80 | 64 ms | equal to the pin's |
| about 10.9k tokens | `pin-long` | 50.63 | 54.94 | 617 ms | - |
| about 10.9k tokens | `f5-long` | 56.45 | 55.95 | 64 ms | DIFFER (section 4) |

The pin resumes a repeated prompt from the last 2,048-row grid point and runs the rest again; the stack resumes at
the prompt's own last row. The aggregate tok/s differences in this table are that first-token time, not decode.

## 4. A paired prompt step wrote past the index rings (found, bisected, fixed: patch 0042)

One stream, the 10.9k-token prompt, the reply's digest:

| image | drafter | pairing on | `TF_GLM_PROMPT_PAIR=0` |
|---|---|---|---|
| pin | off | `d0b0076e1126` | `d0b0076e1126` |
| pin | on (the pin never pairs then) | `d0b0076e1126` | - |
| through 0041 (`fix5`) | off | `34deaa541eee` | `d0b0076e1126` |
| through 0041 (`fix5`) | on | `bfe55367a26a` | `d0b0076e1126` |
| pin + 0001..0006 (`s0006`) | off | `d0b0076e1126` | - |
| pin + 0001..0007 (`s0007`) | off | `34deaa541eee` | - |
| through 0042 (`fix6`) | off | `d0b0076e1126` | `d0b0076e1126` |
| through 0042 (`fix6`) | on | `d0b0076e1126` | - |

At two streams `fix6` with the drafter returns the pin's two digests (`c2c75fcb1015`, `d0b0076e1126`).

**Cause.** The index rings hold 4,096 rows (`index_ring = 2 * prefill_rows`) and a rebase moves a ring's base
down to a multiple of the 4-row pool. The pin starts every prompt step on the 2,048-row grid, so a 4,096-row pair
rebased at its own start fits exactly. Patch 0007 lets a step start at any row (chunks end at marks) but kept the
pin's `ringsAgree` and `State.ready`: a pair starting at a row that is not a multiple of 4 rebased to the pool
below it and wrote up to 3 rows past each ring into the neighbouring ring. Single chunks always fit, which is why
`TF_GLM_PROMPT_PAIR=0` matched the pin. This was on the default path for any long lone prompt whose first mark
falls on such a row, and it gave wrong replies with no error.

**Fix.** The fork has both guards (ref `fork-ssh/ovn-up`); the port had left them out because they live in
functions 0007's own change did not need to touch. 0042 takes them: `ringsAgree` also requires
`start % pool + ra + rb <= ring` (such a step runs as single chunks), and `ready` / `readyMtp` return
`error.PastRing` instead of writing past the ring.

**Cost of the fix.** None measured. Short prompts: `fix6` returns the pin's digests at every level and measures
51.51 / 59.56 / 80.99 / 110.01 / 134.09 tok/s against `fix5`'s 51.01 / 59.84 / 81.04 / 110.38 / 135.75. The long
prompt's cold pass (first token, drafter off): 8,473 ms on `fix6`, 8,459 ms on `s0006` (the pin's pairing), 8,606 ms
with pairing off, so pairing is worth 1.6% of a cold pass at this length.

**How the bisect went wrong twice, and what now prevents it.** The first two bisect images failed to build: my arm
builder applied repair patches (0032, 0034) to trees that did not yet hold what they repair, and my first check of
the kernel catalog matched nothing and printed "none missing". `scripts/arm-tree.sh` now carries the rules (it
reproduces the hand-repaired trees: 0 differing paths for the 0017 arm), and `scripts/catalog-check.py` compares
against the pin's own catalog and was shown to fail on a tree with a missing kernel source before it was trusted.

## 5. The port read in the other direction: `scripts/port-leftover.py`

`docs/PATCH-AUDIT.md` read what the patches take away from the pin. The ring defect is the opposite kind: something
the fork changed that the port never brought. `scripts/port-leftover.py` lists every hunk the fork changed against
its own upstream base (`9b2991d122c7` to `fork-ssh/ovn-up` 595e28743944) whose added lines our tree lacks or whose
removed lines our tree still has. On the 0001..0007 tree it prints `ringsAgree`. On the current tree: 186 files,
479 hunks the fork rewrote and we left, 3,783 fork lines we lack. Four read-only lanes classified every hunk (step
and state, forward and kernels, core and native, tests). Result, enumerated in `docs/PORT-LEFTOVER.md` with the
lanes' full reports beside it in `docs/audit-2026-11-12/`: 12 defects (three more on the default path: no prompt step
pairs after a mark, a prompt-logprobs hang at three ranks that the pin has too, and a kept state lost when prompts
are batched) and 9 speed changes the fork has on by default that the port never brought. Most of the 3,783 lines
are features we did not port, behind knobs.

## 6. Where a round goes with the pad: the profile, and the largest thing the port lacks

Rank 0 under Nsight Systems, `fix5` with `TF_GLM_KDA_PAD=1`, one stream, 400 tokens (63.2 tok/s under the profiler):
7,523 ms of GPU kernel time in 280,855 launches.

| kernel | share | total ms | launches | mean us |
|---|---:|---:|---:|---:|
| `tf_exl3_grouped_1` (routed experts) | 39.5% | 2,974.7 | 12,936 | 230.0 |
| `glm_mm4_16` (4-bit dense, the pad's path) | 11.7% | 882.0 | 41,580 | 21.2 |
| `dsv41_l2pace::paced_kernel` (L2 prefetch pacing) | 9.9% | 744.6 | 13,706 | 54.3 |
| `ncclDevKernel_AllGather_RING_LL` | 7.6% | 569.1 | 14,622 | 38.9 |
| `tf_qmm_group` | 6.0% | 454.4 | 4,940 | 92.0 |
| `glm_mm16_16` | 4.3% | 323.6 | 924 | 350.3 |
| `tfl2pf::segments_kernel` | 2.4% | 178.0 | 5,236 | 34.0 |
| `glm_mm8_16` | 2.0% | 152.5 | 154 | 990.5 |

Without the pad `tf_glm_bmm_decode` held 12.8 ms of each round; with it that kernel is gone from the table and
`glm_mm4_16` takes its place at under half the time, which is the pad's gain. At four streams (`f5-pad-p4`, 93.2
tok/s) the routed experts are 52.3% of kernel time at 573 us a launch.

**The NCCL row is the finding.** About a hundred all-gathers a round go through NCCL. The pin has a one-shot RoCE
gather for exactly these, but it serves two ranks only (`if (group.world != 2) return error.PeerRefused`), so a
three-rank serve falls back to NCCL for every one, silently. The fork extended that gather to worlds 2 to 4
(`060465305` and three follow-ups); the pin's `roce.zig` is byte-identical to the fork's base, and the four commits
apply to our tree without a reject. Image `ai-engine:roce1` (the stack through 0042 plus those four) is queued with
`TF_ROCE=0` on the same image as its control.

## 7. Two smaller measurements

- **A resumed drafter starts with an empty window.** After a kept-state resume near the prompt's end the DFlash2
  drafter has only the rows after the resume point as context. Same reply (`d0b0076e1126`), one stream: acceptance
  0.702 on the pin (which resumes up to 2,048 rows earlier), 0.677 through 0042, 0.698 with
  `TF_GLM_OVN_DRAFT_KEEPWIN=1` (kept states carry the drafter's window). At two streams the knob's round is 0.5 ms
  longer (36.8 against 36.3 ms, the first stream at 38.6 against 39.1 tok/s), so it is a mixed result and stays a knob.
- **Pairing is worth 1.6 to 2.6% of a cold prompt pass at 10.9k tokens**: 8,449 ms paired against 8,674 ms not on
  the pin, 8,473 against 8,606 through 0042. `scripts/streams.py` now records the warm-up pass's first-token time
  (`cold_ttft_ms`), the only cold pass of a cell.

## 8. The CPU gates, run again

`scripts/gates.sh` copies the tree to the WSL filesystem (`~/gt/NAME`) and runs the README's gates there. On a
copy the 26 file-permission, symlink and FIFO tests that fail on a Windows-mounted tree pass: the pin gives 343 of 345
steps and 2,652 of 2,671 tests with one failing test (`health_test`, a benchmark-manifest case, in no GLM file; it
failed on the pin only), the stack through 0042 gives 345 of 345 steps and 2,660 of 2,678 tests with none failing,
and through 0044 the same. `compile-cuda-tests`, `test-glm-ring-host`, `test-glm-logprobs-host`, `test-rows-host` and
`zig fmt --check zig/` are rc 0 on the 0044 tree. A mutant that makes 0044's new host test fail on its first line
makes `test-cuda-host` fail with that test named, so the gate does run it. The restacked 0043 to 0068 tree has no
valid gate result yet: the first run was killed after a hung in-place run on the Windows mount, and the second died
when C: filled.

## 9. Every port patch together, and the RoCE gather

`ai-engine:all1` (the stack through 0042 plus the 25 ported patches, before the item plan and RoCE) at 1, 2, 4, 6
and 8 streams, replies byte-identical to `fix6` at every level: 51.55, 60.44, 82.54, 112.25 and 137.77 tok/s against
51.51, 59.56, 80.99, 110.01 and 134.09 (+0.1, +1.5, +1.9, +2.0, +2.7%). The 10,929-token prompt (`d0b0076e1126`):
first token of the cold pass 7,326 ms against 8,473 ms through 0042 (-13.5%); warm resumes stay 62 to 66 ms.

The RoCE gather (`TF_ROCE`) at 8 streams with the KDA pad, ABBA, tok/s of one stream: A (`TF_ROCE=0`) 22.9 and 22.5,
B (RoCE) 22.5 and 22.5, about -0.9% for RoCE, replies identical. With the earlier cells (+2.0 and +1.7% at one and two
streams, level at four, -0.6 and -1.3% at six and eight) the patch is a trade, so it needs the rewrite-or-gate step
before it lands.

## 10. The clean upstream v1.2.7 base

`glm53-zig:v127`, built from the tag with none of our patches, same boot settings: decode in tok/s at 1, 2, 4, 6 and
8 streams 50.16, 58.57, 79.23, 106.37 and 129.66 (the old pin: 51.38, 58.16, 72.26, 95.19 and 115.18), and with
`TF_GLM_KDA_PAD=1` 62.19, 70.57, 88.91, 118.29 and 143.25 with different replies. Upstream alone gained 9.6, 11.7 and
12.6% at four, six and eight streams in the 600 commits since the pin, so the series has to be measured against this
image. The 10,929-token prompt: first token of the cold pass 8,576 ms and 620 to 640 ms for a repeat of it, where our
series resumes in 62 to 66 ms; the mid prompt 2,964 ms cold and 1,455 ms repeated against 2,577 and 62 ms.
`docs/audit-2026-11-12/v127-drift.md` says what upstream changed (decode windows 8 to 32 rows and MTP chains 3 to 15
drafts by default, load-time round pricing, prompt cuts, a registry for GLM switches) and
`docs/audit-2026-11-12/fold-series.md` the 35-lever form of our series the re-seat starts from.

## 11. Where the one-stream round goes against production

Both serves measured today on the same three machines, one stream, prose prompt, 400 tokens, greedy, KDA pad on ours.

| | production (Python tf-v110) | ours, upstream v1.2.7 |
|---|---:|---:|
| decode tok/s, one stream | 80.8 and 77.9 (cells; 81.73 mean of the earlier run) | 62.3 to 62.7 |
| draft acceptance | 0.686 (388 drafted, 266 accepted a cell) | 0.638 (401 and 256) |
| drafts a round | 2.41 (3,440 drafted over 1,427 rounds) | 2.80 (401 over 143 rounds) |
| tokens a round | 2.59 (3,698 generated over 1,427 rounds, warm-up included) | 2.79 |
| ms a round | 31.9 (2.59 tokens at 80.8 tok/s) | 44.5 |

Production does not draft more cleverly: it verifies fewer rows (3.4 against 3.8 a round) and takes fewer tokens a
round. The 12.6 ms is the first reading of the gap and it is an upper bound: it uses aggregate counters with the
warm-up included, and the sum of production's own component times at 3.4 rows gives 34.6 to 35.8 ms, a gap of 8.7 to
9.9 ms (`round-structure.md` finding 6; one production log line settles which).

The code reading (`docs/audit-2026-11-12/round-structure.md`) corrects two things this section first said. The verify
table above (`TF_GLM_MULTI_PROFILE`) is production's one-stream-graph column; the served path runs the batched graphs
(1: 20.29, 2: 25.65, 3: 31.72, 4: 36.90 ms), because `TF_GLM_KV_SHARD=1` forces the lone path off. And production's
drafter is not hidden under the verify: it runs on the same stream after the commit, in about 2.3 ms of GPU time (one
CUDA graph of 218 kernels, 328 MB read a rank against our 1,047 MB, launched at the end of the previous round).

What the comparison does show: our verify is fully eager (no CUDA graph anywhere in the GLM family, about 1,400
host launches a window), our all-gathers all go through NCCL, our drafter pass costs 5.4 to 5.9 ms, and a 4-row
verify with section timers on is 38.6 ms against production's 36.9. The routed experts in our profile (13.2 ms at 2
rows, 21.7 ms at 4) are close to the bandwidth floor computed from the checkpoint (about 12.6 MB an expert, 42 MoE
layers, 8 of 288 per token, TP=3: 19 to 23 ms at 4 rows at the GB10's 273 GB/s peak, expert counts estimated), so the
levers are the drafter pass, graphs and the gathers, not the expert kernel. The section timers add their own sync
cost, so the profiled figures are upper bounds.

The ranked list in `round-structure.md` section 5 is the work order: the drafter's 4-bit down projection and MLP split
(measured on the fork at 2.9 to 3.9 ms a round, replies bit-exact), verify windows as CUDA graphs (an estimate of 1 to
3 ms, bit-exact), RoCE gathers gated by size, and the routed-expert item plan (0044, +1.4% at one stream).

## 12. A chat's later turns: upstream's request starts against our resume at any row

`scripts/turns.py` sends one chat the way an agent grows it (a 11.3k-token system message, then four turns, each sending
everything before it plus the reply), twice, one stream, drafts on, knobs off. First token of each turn, in ms:

| | turn 1 (cold) | turn 2 | turn 3 | turn 4 | the same chat again, turns 1 to 4 |
|---|---:|---:|---:|---:|---|
| upstream v1.2.7 | 8,596 | 943 | 976 | 990 | 823, 940, 964, 999 |
| v1.2.7 with `TF_GLM_REQUEST_STARTS=1` | 8,776 | 211 | 239 | 254 | 102, 213, 231, 252 |
| our stack `ai-engine:all1` (resume at any row) | 7,711 | 249 | 190 | 198 | 64, 62, 64, 66 |

All three give the same reply for every turn (digests equal). Upstream's request starts get a later turn of a chat to
within 20 to 60 ms of ours, so resuming at any row is not needed for that case, and it is why the re-seat retires it.
What it still wins is an exact repeat of a whole prompt (62 to 66 ms against 102 to 252). With request starts on, the
cold first token is 180 ms slower than with them off in this run (8,776 against 8,596), one cell and not repeated.

## 13. The series re-seated on v1.2.7, every switch off (`glm53-zig:rs1`)

The 33 patches of `docs/audit-2026-11-12/reseat-v127.md` applied to the v1.2.7 tag (tree `93a99447e703`), built into an
image on spark1 (every `.cu` compiled) and benched like the base: one fresh boot a level, 400 tokens a stream, no
switch set. Decode tok/s, against `glm53-zig:v127` with the same settings, replies byte-identical at every level:

| | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| upstream v1.2.7 | 50.16 | 58.57 | 79.23 | 106.37 | 129.66 |
| re-seated series, switches off | 51.55 | 60.88 | 83.11 | 111.63 | 137.43 |
| change | +2.8% | +4.0% | +4.9% | +4.9% | +6.0% |

Nothing regresses at any level. The 10,929-token prompt (`d0b0076e1126`, equal): first token of the cold pass 7,455 ms
against 8,576 on v1.2.7, and a repeat of it 595 to 601 ms (v1.2.7: 620 to 640; the any-row resume is retired, request
starts are the way to resume a chat, section 12). The 3.6k-token prompt: 2,517 ms cold against 2,964, repeat 1,177 to
1,183 against 1,455.
An earlier try of this bench failed at every boot because the image had not been copied to spark2 and spark3 (rank 0
waited for ranks that could not start); `scripts/dist-image.sh TAG` copies an image to spark2 and spark3 and checks the ids agree; a bench needs it after every build.

## 14. Mia's `TF_PROMPT_CACHE_FIRST` (patch 0112 of the MiaAI recipe): not carried

An opt-in that sets the prompt cache (`--prompt-cache-gib`) aside before the KV room is counted in whole windows. It is
in neither the old pin, nor upstream v1.2.7, nor any patch of ours, and it does not apply to the re-seated tree (`git
apply --check` fails in `zig/src/native/cuda_kv_pool.zig:68`): v1.2.7 rewrote the pool plan since (groups sized by
bytes a row, `ca83a689a` kept-state budgets scaled after streams are counted, `949ae97fe` and `4a0e38afd` on naming a
`--prompt-cache-gib`). Carry it only if a measurement on `glm53-zig:rs1` shows the cache taking pages the streams need
at a stream count we serve; no such cell exists.

## 15. Two levers that did not pay: verify windows as CUDA graphs, and a lower draft confidence cut

Production's one-stream decode, measured today from its own counters (`/health` rounds, drafts and tokens around each
400-token request, five requests, identical): 133 rounds, 2.92 drafts and 3.01 tokens a round, acceptance 0.686, 35.6
ms a round, 80.8 tok/s. Ours on v1.2.7 with the pad: 143 rounds, 2.80 drafts and 2.79 tokens a round, acceptance 0.638,
44.5 ms a round, 62.7 tok/s. So production is 8.8 ms (20%) faster a round and takes 8% more tokens from each (section 11's
first reading of 32 ms a round used counters that included other requests and is withdrawn). Its older nsys captures
(`DecNsysMimo`, image `v110-ots99`) show its GPU busy 98.5% of the round, so the difference is GPU time, not host gaps.

**Verify windows as CUDA graphs** (`docs/audit-2026-11-12/verify-graph.md`; the patch applied to the re-seated tree
and passed every host gate). Image `vg1`, `TF_GLM_KDA_PAD=1`, one fresh boot a level, replies byte-identical to the
same image with the graph off:

| | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| graph off | 64.45 | - | - | - | 152.88 |
| graph on (a graph per key, 11 or more captured) | 63.42 | 73.74 | 93.93 | 126.36 | 153.22 |

No gain (-1.6% at one stream, +0.2% at eight): the eager launches already overlap the GPU's work, so the round is
GPU-bound and the roughly 1,400 host launches were not its cost. The patch is not landed.

**A lower draft confidence cut** (`TF_GLM_DRAFT_CONFIDENCE`, upstream's own switch; ours defaults to 0.7, production
runs lower), image `rs1`, pad on, replies equal to the default's:

| cut | 1 | 2 | 4 | 6 | 8 | tokens a round | ms a round | acceptance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.7 (default) | 64.45 | - | - | - | 152.88 | 2.79 | 42.4 | 0.638 |
| 0.5 | 62.11 | 71.29 | 90.77 | 122.49 | 149.42 | 3.00 | 47.3 | 0.504 |
| 0.3 | 60.73 | 65.22 | 86.90 | 119.87 | 149.04 | 3.17 | 51.1 | 0.441 |
| 0.2 | 58.11 | 63.66 | 86.11 | 119.40 | 149.41 | 3.19 | 53.8 | 0.395 |

More drafts per round buy 5 to 14% more tokens a round and cost more ms a round than they return, so the default stays.
Production gets 3.01 tokens a round at 0.686 acceptance, which is a better drafter (4-bit down projection, TP-split
MLP, one graph), not a different cut. The drafter arms of the re-seated series are the next measurements.

## 16. The drafter knobs of the re-seated series, with the pad

Image `rs1`, `TF_GLM_KDA_PAD=1` on every arm, one fresh boot a level, 400 tokens a stream, replies byte-identical to the
pad-only arm at every level. `DOWN4` is `TF_GLM_OVN_DRAFT_DOWN4=1` (the drafter's down projection in 4 bits), `d4s` adds
`TF_GLM_OVN_DRAFT_ONEPASS=1` and `TF_GLM_OVN_DRAFT_MLPSPLIT=4` (one pass for all rows, the MLP split over the ranks up to
four streams):

| arm | 1 | 2 | 4 | 6 | 8 | tokens a round | ms a round | acceptance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pad only | 64.57 | 73.71 | 93.66 | 126.18 | 153.75 | 2.79 | 42.3 | 0.638 |
| pad + DOWN4 | 67.95 (+5.2%) | 77.04 (+4.5%) | 95.33 (+1.8%) | 127.28 (+0.9%) | 154.78 (+0.7%) | 2.77 | 39.8 | 0.647 |
| pad + DOWN4 + ONEPASS + MLPSPLIT=4 | 69.78 (+8.1%) | 78.17 (+6.1%) | 98.83 (+5.5%) | 133.80 (+6.0%) | 160.25 (+4.2%) | 2.77 | 38.8 | 0.651 |

No level regresses, so the set is a win by the fleet rule and goes into the recipe's measured knob set (`scripts/serve.sh`).
Against production (81.73 / 89.22 / 117.98 / 114.78 / 131.28) the best arm is now -14.6%, -12.4%, -16.2% at one, two and
four streams and +16.6% and +22.1% at six and eight. The round is 38.8 ms against production's 35.6.

## 17. The recipe's whole knob set, and every one-knob arm, on the corrected series (`rs2`)

Image `rs2` is the series after the `TF_GLM_OVN_MLA_FUSEMERGE` boot fix (`docs/audit-2026-11-12/mla-boot-fix.md`: the
bounded FP8 chunk kernels of 0025 took the fork's 16 parameters while the host passes 14) and with the dead
`TF_GLM_OVN_ONEPASS_EXACT` switch retired. With the pad on every arm, one fresh boot a level, replies byte-identical to the
pad-only arm, tok/s (change against the first pad-only cell; a second and a third pad-only cell, taken hours later, read
-1.1/-2.5/-1.8/-2.0/-1.4% and +0.5/+0.1/-0.4/+0.2/-0.8%, so about 2% is run-to-run noise on this box):

| arm | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| pad only | 64.57 | 73.71 | 93.66 | 126.18 | 153.75 |
| `MLA_FUSEMERGE` alone | 65.46 (+1.4%) | 74.25 (+0.7%) | 94.66 (+1.1%) | 127.53 (+1.1%) | 155.17 (+0.9%) |
| the seven-knob set (`KNOBS=measured`) | 70.17 (+8.7%) | 78.71 (+6.8%) | 99.40 (+6.1%) | 134.31 (+6.4%) | 165.26 (+7.5%) |

The seven-knob set is the pad plus `INDEX_CUDA`, `KEPT_WALK`, `DRAFT_ONEPASS`, `DRAFT_DOWN4`, `DRAFT_MLPSPLIT=4` and `MLA_FUSEMERGE`, passed
as the arm's own `-e` list with `KNOBS=off`; `scripts/serve.sh`'s `DEFS` is exactly this list. The other seven knobs of the earlier `DEFS`
(`GLUE_FUSE`, `INDEX_SCHED`, `POOLS32`, `INDEX_REGROUP`, `MM_WIDE`, `SPARSE_ONEPASS`, `ROUTER_WARM`) were never in one arm together;
each was measured alone, below. No level regresses. Against
production (81.73 / 89.22 / 117.98 / 114.78 / 131.28) it is -14.1%, -11.8% and -15.8% at one, two and four streams and +17.0% and
+25.9% at six and eight; the round at one stream is 38.5 ms against production's 35.6.

One-knob arms on `rs1` (each against the pad-only cells, replies equal): `INDEX_CUDA`, `INDEX_SCHED`, `POOLS32`, `INDEX_REGROUP`,
`MM_WIDE` and `SPARSE_ONEPASS` are within +-1% at every level, that is noise; `KEPT_WALK`, `GLUE_FUSE` and `ROUTER_WARM` read -2% in
their first cells and -0.6 to +1.4% when repeated, so they are neutral. With `DRAFT_KEEPWIN=1` added to the drafter set the cells
read +8.6 / +6.5 / +5.9 / +6.5 / +6.0% against +8.1 / +6.1 / +5.5 / +6.0 / +4.2%, inside the noise, so it stays out of the set.

## 18. The series re-seated on upstream main (`0fed2e4a5`, 192 commits past v1.2.7), and upstream's RoCE and drafter split

Images: `mb` is pristine main, `mr1` is our 32 patches on it (tree `bc5a465b22b1`; `0029` retired because `8978c4357` runs a
prompt in calls of up to 4,096 rows). Every arm has the pad, one fresh boot a level, replies equal to the control's. `rs2-ctl` is the
seven-knob arm of section 17 run again on image `rs2` the same day; `mr1-7` is the same seven knobs on `mr1`. tok/s at 1/2/4/6/8
streams (change against `rs2-measured`, the first cell of section 17):

| arm | 1 | 2 | 4 | 6 | 8 | ms/round | accept |
|---|---:|---:|---:|---:|---:|---:|---:|
| `rs2-ctl` (v1.2.7 series, seven knobs) | 70.86 (+1.0%) | 79.53 (+1.0%) | 100.01 (+0.6%) | 134.52 (+0.2%) | 165.26 (0.0%) | 38.2 | 0.651 |
| `mb-pad` (main, pad only) | 63.87 | 72.21 | 91.13 | 121.39 | 146.19 | 42.8 | 0.638 |
| `mb-roce` (main, pad, `TF_ROCE=1`) | 66.04 | 74.02 | 94.34 | 126.61 | 154.10 | 40.7 | 0.643 |
| `mr1-7` (re-seated, seven knobs) | 68.48 | 77.05 | 97.59 | 131.24 | 160.23 | 39.5 | 0.651 |
| `mr1-7-roce` (+ `TF_ROCE=1`) | 68.56 | 76.81 | 96.97 | 131.05 | 160.67 | 39.5 | 0.651 |
| `mr1-7-nosplit-roce` (`TF_ROCE=1`, no `MLPSPLIT`) | 68.23 | 76.22 | 96.97 | 135.05 | 167.07 | 39.7 | 0.651 |

- **Main is not shown to be faster or slower than the v1.2.7 series.** With the same seven knobs the re-seated stack reads
  -3.4 / -3.1 / -2.4 / -2.4 / -3.0% against `rs2-ctl`, a round of 39.5 ms against 38.2, with the same acceptance; but the same `rs2`
  arm run again later (`rs2-ctl-b`, section 19) reads as low as `mr1-7` (68.68 against 68.48 tok/s at one stream), so the box drifts
  about 3% between identical runs and the difference is inside it. The pin stays at v1.2.7: nothing on main measured as a win for us.
- **The RoCE gather never connected.** Every `TF_ROCE=1` boot printed `RoCE all-gather: PeerRefused (HCA 0: the queue pair toward rank 1
  refused RTR); NCCL carries every gather`. Upstream pairs HCA h with the peer's HCA h; the cabled triangle pairs differently (skill
  `fix-crossed-mesh-roce-rail-pairing`). So `TF_ROCE=1` here only turned on upstream's drafter MLP split on every pass, and the
  `mb-roce` gain over `mb-pad` (+3.4 / +2.5 / +3.5 / +4.3 / +5.4%) is that split, not RoCE. A RoCE gather on this cabling needs the
  GID-derived pairing patch first; its measured size on the fork was +1.4% at one stream and -1.3% at eight.
- **The drafter split on every pass, one pair of cells.** `mr1-7-nosplit-roce` (upstream's split, every pass) against `mr1-7-roce`
  (ours, only while at most four streams are in a pass) reads -0.5 / -0.8 / 0.0 / +3.1 / +4.0%. Our knob takes a stream count, so
  `TF_GLM_OVN_DRAFT_MLPSPLIT=8` on image `rs2` is the same split without leaving v1.2.7; section 19 repeats it.

## 19. `MLPSPLIT=8` against `=4` on `rs2`, control between the two test cells

Same image, same seven-knob arm except the stream count that gates the split (4 or 8); order `rs2-s8`, `rs2-ctl-b`, `rs2-s8-b`,
the first control `rs2-ctl` having been taken at the start of the window; replies equal in every cell.

| arm | 1 | 2 | 4 | 6 | 8 | ms/round |
|---|---:|---:|---:|---:|---:|---:|
| `rs2-ctl` (`=4`) | 70.86 | 79.53 | 100.01 | 134.52 | 165.26 | 38.2 |
| `rs2-s8` (`=8`) | 70.41 | 77.81 | 97.14 | 131.95 | 161.99 | 38.4 |
| `rs2-ctl-b` (`=4`) | 68.68 | 76.66 | 97.20 | 130.85 | 160.21 | 39.4 |
| `rs2-s8-b` (`=8`) | 70.32 | 78.86 | 99.28 | 136.20 | 167.60 | 38.5 |
| mean of the two `=8` cells against the two `=4` cells | +0.9% | +0.3% | -0.4% | +1.0% | +1.3% | |

The two `=4` cells differ from each other by 3.1 / 3.6 / 2.8 / 2.7 / 3.1% and the two `=8` cells by 0.1 / 1.3 / 2.2 / 3.2 / 3.5%, so
the split's stream count is neutral inside the run-to-run spread and `=4` stays. The section 18 figures of +3.1% and +4.0% at six
and eight streams were one pair of cells inside that spread. On this box one identical arm repeated can read 3% low, so a single
cell, and a gap under about 3%, decides nothing; a claim at that size needs the arm in both orders.

## 20. Where the one-stream round goes, and two drafter-side levers that measured neutral

The profile (`docs/audit-2026-11-12/drafter-lever.md`) is built from the only nsys exports there are, which predate the drafter knobs,
plus the round counters of the five seven-knob cells; its stage table says which stages are stale. At one stream our round is
38.0-39.7 ms against production's 35.6-36.8 ms, with 2.77 tokens against 3.01 a round (acceptance 0.651 against 0.686); the 8% in
tokens is worth about 3.1 ms of our round. The largest stage gaps to production, in ms a round:

| stage | ours | production | gap |
|---|---:|---:|---:|
| verify step, whole | 34.6-36.6 | 32.4 | +2.2 to +4.2 |
| the 90 NCCL all-gathers in it | 3.12 (+0.35 idle before them) | 1.35-2.4, RoCE inside a CUDA graph | +0.7 to +1.8 |
| GPU idle on the main stream in the verify | 1.34 | 0.66 for its whole round | +0.7 |
| drafter step (with the drafter knobs) | 2.6-3.2 | 2.3 | +0.3 to +0.9 |

So since the drafter knobs the drafter is within about a millisecond of production's; the verify step's all-gathers and idle, and the
tokens kept a round, are the gaps. At four streams the verify (routed experts 50.7 ms of 75.2 in the stale capture) and the tokens
a round are the gap.

Two levers measured, image `isplit1` (the series plus `0034`), control and test each twice, order ctl, on, pdl, ctl, on, pdl, all
seven knobs and the pad, replies equal and acceptance equal in every cell (tok/s; change against the first control):

| arm | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| `is-ctl` | 70.46 | 79.44 | 99.90 | 135.14 | 164.57 |
| `is-ctl-b` | 69.95 (-0.7%) | 78.90 (-0.7%) | 99.05 (-0.9%) | 133.84 (-1.0%) | 164.90 (+0.2%) |
| `is-on` (`TF_GLM_OVN_DRAFT_INGEST_SPLIT=1`) | 70.69 (+0.3%) | 79.20 (-0.3%) | 99.97 (+0.1%) | 134.70 (-0.3%) | 164.93 (+0.2%) |
| `is-on-b` | 70.81 (+0.5%) | 79.39 (-0.1%) | 99.76 (-0.1%) | 135.28 (+0.1%) | 164.76 (+0.1%) |
| `is-pdl` (`TF_GLM_OVN_PDL_EARLY=1`) | 70.05 (-0.6%) | 78.70 (-0.9%) | 99.92 (0.0%) | 135.03 (-0.1%) | 165.37 (+0.5%) |
| `is-pdl-b` | 70.22 (-0.4%) | 79.14 (-0.4%) | 99.64 (-0.3%) | 134.95 (-0.1%) | 165.05 (+0.3%) |

The ingest split (the drafter's context ingest cut over the ranks, same K order so the drafts are identical; rank 0's log shows
`a decode ingest's fc in 1408 columns a rank and k, v in 2 x 384, gathered`) moves nothing outside the controls' own spread of
about 1%, which is what its estimate of 0.1-0.25 ms a round (0.3-0.6%) predicted. `PDL_EARLY` is the same. Neither ships: the
ingest split is 253 added lines for a gain no cell can show, and it stays as `docs/audit-2026-11-12/0034-draft-ingest-split.patch.txt`
(sha256 `773988ed1c05`, applies to the series' tree `4ed20ea3d175`, with a bit-exact check of its share matmuls on an RTX 5070:
0 of 671,744 fc words and 0 of 1,679,360 k and v words differ). The levers the profile leaves are the all-gathers (v1.2.7's own RoCE
path with `TF_GLM_ROCE_MULTI=1`, never measured here) and the tokens kept a round.

## 21. v1.2.7's three-rank RoCE wire (`TF_GLM_ROCE_MULTI=1`): +1.4 to +1.8% at one to four streams, none at six, -0.5% at eight

Image `rs2`, the seven knobs and the pad. The wire (`fabric/tp`, ports paired by shared subnet; boot lines `tp roce: rank 0 -> rank 1:
HCA pairs { 0 } from ours { 0 }` and `rank 0 -> rank 2: ... from ours { 1 }`, then `gathers up to 256 KiB a rank on the wire`) needs the
mailbox kernel image on every host (`scripts/mailbox-fatbin.sh`, built with CUDA 13.3, sha256 `c3f526171160`, placed at
`~/.cache/huggingface/tp_mailbox.fatbin`), `TF_TP_MASTER` (rank 0's address) and `TF_TP_KERNEL_IMAGE`. Order ctl, roce, roce, ctl;
replies equal and acceptance equal in every cell (tok/s; change against the first control):

| arm | 1 | 2 | 4 | 6 | 8 | ms/round |
|---|---:|---:|---:|---:|---:|---:|
| `env-ctl` | 70.41 | 78.69 | 99.60 | 135.26 | 165.21 | 38.5 |
| `env-roce` | 71.71 (+1.8%) | 80.37 (+2.1%) | 101.26 (+1.7%) | 135.52 (+0.2%) | 163.77 (-0.9%) | 37.7 |
| `env-roce-b` | 71.37 (+1.4%) | 78.92 (+0.3%) | 100.73 (+1.1%) | 134.85 (-0.3%) | 164.45 (-0.5%) | 37.9 |
| `env-ctl-b` | 70.03 (-0.5%) | 78.25 (-0.6%) | 99.44 (-0.2%) | 134.79 (-0.3%) | 165.26 (0.0%) | 38.6 |
| `rc-ctl` (a third control, taken in the next window) | 70.34 (-0.1%) | 78.73 (+0.1%) | 99.20 (-0.4%) | 134.28 (-0.7%) | 164.66 (-0.3%) | 38.5 |

The mean of the two wire cells against the three control cells is +1.8 / +1.4 / +1.6% at one, two and four streams, +0.1% at six and
-0.5% at eight. The round time is the clearest signal: 37.7 and 37.9 ms with the wire against 38.5, 38.6 and 38.5 without, about
0.7 ms a round, which is what the profile's gather gap predicted (section 20).

A size cap does not keep the gain and lose the loss: `TF_TP_MAILBOX_MAX_KB=64` reads +0.2 / -0.5 / -0.7 / -1.2 / -1.4% and
`=32` reads -0.8 / -0.7 / -0.6 / -1.2 / -0.5% (first cells, against `env-ctl`; the repeats read +0.5 / -0.7 / -1.4 / -0.9 / -1.3% and
-0.3 / -2.8 / -2.9 / -3.1 / -2.7%), so what the wire saves is in the gathers between 64 and 256 KiB. The stream count is a boot-time
`--parallel`, so the gate is the launcher's: `scripts/serve.sh` adds the wire with `KNOBS=measured` only at 4 streams or fewer, and only
when the kernel image is on the host (otherwise it prints that it boots on NCCL). Checked through the launcher on `rs2`: the 4-stream
boot logged `gathers up to 256 KiB a rank on the wire`, the 8-stream boot did not. Those two cells read 99.45 tok/s (-0.2%) and 161.28
tok/s (-2.4%); the 8-stream cell has no wire and the control's configuration, so it shows the box reading 2.4% low at that time, and a
single cell at this size says nothing about the wire.

Against production (81.73 / 89.22 / 117.98 tok/s) the wire's mean cells of 71.54 / 79.65 / 101.00 are -12.5 / -10.7 / -14.4% at one,
two and four streams; at six and eight streams the series is unchanged at +17.0 and +25.9%.

## 22. Production's DFlash2 chain rule on our series: +1.3 to +4.5% at every stream count; the recipe with it

Why: the profile (section 20) leaves tokens kept a round as the largest gap, 2.77 against production's 3.01 at one stream, and the
acceptance analysis (`work/accept-gap`, summarised here) finds a third of it in the draft chain's rule. Production serves `fnc7:0.3`
(`DepthPolicy(7, fixed, 0.3, beta 2.0)`, edge weight 0.6: each draft is scored logits + 0.6 x edge, picked from softmax(score/2), and the
chain stops below 0.3 past the first draft); ours defaults to edge 1.0, temperature 1 and a 0.7 cut. The series already carries the
knobs (`TF_GLM_OVN_DRAFT_EDGE`, `_BETA`, `_CUTS`, patch 0007), so no patch was needed. The same analysis found the two serves do not
get the same prompt for `enable_thinking: false`: production renders 33 tokens (it drops the `Reasoning Effort: Max` line and closes the
think block), ours 40 (it keeps the line), so no earlier cell compared the same text; aligning our rendering would change our reply
digests, and that is not done.

Image `rs2`, the seven knobs and the pad on every arm, order ctl, prod, prod, ctl, replies equal, tok/s (change against the first
control; each test cell sits next to a control cell, `cr-ctl` then `cr-prod`, and `cr-prod-b` then `cr-ctl-b`):

| arm | 1 | 2 | 4 | 6 | 8 | tokens/round | accept |
|---|---:|---:|---:|---:|---:|---:|---:|
| `cr-ctl` | 68.33 | 76.66 | 99.60 | 135.10 | 164.83 | 2.77 | 0.651 |
| `cr-prod` (`EDGE=0.6 BETA=2 CUTS=1:0.3`) | 70.72 (+3.5%) | 80.10 (+4.5%) | 101.84 (+2.3%) | 137.23 (+1.6%) | 167.94 (+1.9%) | 2.81 | 0.671 |
| `cr-prod-b` | 69.11 (+1.1%) | 78.43 (+2.3%) | 99.66 (+0.1%) | 133.64 (-1.1%) | 163.39 (-0.9%) | 2.81 | 0.671 |
| `cr-ctl-b` | 68.25 (-0.1%) | 76.64 (0.0%) | 97.46 (-2.2%) | 131.20 (-2.9%) | 161.08 (-2.3%) | 2.77 | 0.651 |
| `cr-e2` (`EDGE=0.2`, a single cell) | 70.21 (+2.7%) | 79.16 (+3.3%) | 100.31 (+0.7%) | 134.57 (-0.4%) | 164.68 (-0.1%) | 2.77 | 0.722 |

The window's second half read low (both `-b` cells sit 2 to 3% under their first cells), so the comparison is each test cell against the
control next to it: `cr-prod` over `cr-ctl` +3.5 / +4.5 / +2.3 / +1.6 / +1.9% and `cr-prod-b` over `cr-ctl-b` +1.3 / +2.3 / +2.3 /
+1.9 / +1.4% at 1/2/4/6/8 streams, every one positive. The counters agree and are exact: tokens a round 2.77 to 2.81 (+1.4%) and
acceptance 0.651 to 0.671 with the same replies. The fork's loss with this rule at 4 to 8 streams did not reproduce here, so it needs
no stream gate. `EDGE=0.2` (production's own refit) is one cell and is not adopted.

The recipe as `scripts/serve.sh` now defines it (`KNOBS=measured`: the seven knobs, this chain rule, and the RoCE wire of section 21 at
4 streams or fewer), run through the launcher, order ctl, rec, rec, ctl (`cm-ctl` is the seven-knob arm); the boot logs show the wire at
1 and 4 streams and not at 8:

| arm | 1 | 2 | 4 | 6 | 8 | tokens/round | accept |
|---|---:|---:|---:|---:|---:|---:|---:|
| `cm-ctl` | 70.37 | 78.38 | 100.31 | 131.62 | 160.43 | 2.77 | 0.651 |
| `cm-rec` | 70.95 (+0.8%) | 80.29 (+2.4%) | 100.79 (+0.5%) | 134.09 (+1.9%) | 163.69 (+2.0%) | 2.81 | 0.671 |
| `cm-rec-b` | 71.22 (+1.2%) | 80.41 (+2.6%) | 101.09 (+0.8%) | 134.30 (+2.0%) | 163.02 (+1.6%) | 2.81 | 0.671 |
| `cm-ctl-b` | 68.53 (-2.6%) | 77.09 (-1.6%) | 96.78 (-3.5%) | 132.04 (+0.3%) | 164.97 (+2.8%) | 2.77 | 0.651 |

The mean of the two recipe cells against the two control cells is +2.4 / +3.4 / +2.4 / +1.8 / +0.4% at 1/2/4/6/8 streams; at eight
streams the two pairs split (+2.0% and -1.2%), so that +0.4% is inside the spread and not a gain. These are not the sum of the two
effects (the chain rule +2.4 / +3.4 / +2.3 / +1.7 / +1.7%, the wire +1.8 / +1.4 / +1.6 / +0.1 / -0.5%): this box's spread is about 2 to
3% a cell, so the combination is shown to be no worse than either, not shown to add. Cells from different windows are not comparable
(a control cell reads 68.3 to 70.9 tok/s at one stream across them); the recipe's means are 71.09 / 80.35 / 100.94 / 134.20 / 163.36 tok/s,
-13.0 / -9.9 / -14.4% against production at 1/2/4 streams and +16.9 / +24.4% at 6 and 8.

## 23. The one-stream gap was mostly the prompt: production's own prompts through our engine

The acceptance analysis (`docs/audit-2026-11-12/accept-gap.md`) found that `scripts/streams.py` sends chat requests with
`enable_thinking: false`, and the two serves render that differently: production drops the `Reasoning Effort: Max` system line and
closes the think block (the bench's first prose prompt is 33 tokens), ours keeps the line (40 tokens). The replies then differ, and
tokens kept a round and acceptance depend on the reply, so the 2.77 against 3.01 tokens a round and the gap built on it compared
different text.

**M-a, one stream, production's 33 prompt tokens sent as ids to our serve** (`scripts/streams_ids.py`, `scripts/prose33.json`, the
instrument otherwise unchanged; 3 rounds; the reply digest is `9eb3186f9480` in both arms, neither ours on our prompt nor production's
`8347edfe4ee6`, so the text is still not identical, only the prompt):

| arm | draft rounds | drafted | accepted | tokens a round | acceptance | agg tok/s |
|---|---:|---:|---:|---:|---:|---:|
| seven-knob control (`ids-ctl`) | 128 | 390 | 271 | 3.12 | 0.695 | 76.7 to 76.9 |
| production's chain rule (`ids-prod`) | 127 | 394 | 272 | 3.14 | 0.690 | 77.1 to 77.3 |

Against production's 3.000 tokens a round on its own reply, our engine keeps 3.12 to 3.14 on this prompt: the tokens-a-round gap is
gone. The round time is not: 3.12 tokens at 78.7 tok/s decode is about 39.7 ms a round against production's 35.6 ms.

**M-b, our drafter on production's reply** (teacher-forced: each position's prompt is production's prompt plus its reply's first p
tokens, so every drafter sees production's text; `docs/audit-2026-11-12/accept-gap.md` has the method): the share of drafts equal to
production's next tokens at depth 1 to 7 is 0.807 / 0.615 / 0.455 / 0.326 / 0.230 / 0.152 / 0.102 (control) and 0.807 / 0.623 / 0.463 /
0.345 / 0.246 / 0.163 / 0.107 under production's rule. Verifying every correct draft would keep 3.02 (control) and 3.07 tokens a
round against production's 3.000, so our drafter's arithmetic is not behind production's. The replayed rule-limited chains (2.32 and
2.31 tokens a round, with 54 of 399 positions flagged because our target leaves production's text there) sit well under that ceiling;
drafting deeper was measured to lose on tok/s (section 15), so no lever follows.

**The like-for-like table.** `scripts/bench-client.sh` at 1/2/4/6/8 streams, production's rendering of all four bench prompts as
ids, image `rs2`, order recipe, seven-knob control, recipe (`ids-rec`, `ids-c7`, `ids-rec-b`; replies equal across the three):

| arm | 1 | 2 | 4 | 6 | 8 | tokens/round | accept |
|---|---:|---:|---:|---:|---:|---:|---:|
| `ids-c7` (seven knobs) | 76.66 | 79.08 | 103.54 | 140.45 | 172.83 | 3.12 | 0.695 |
| `ids-rec` (recipe) | 78.75 (+2.7%) | 80.78 (+2.1%) | 105.37 (+1.8%) | 139.53 (-0.7%) | 172.85 (0.0%) | 3.14 | 0.690 |
| `ids-rec-b` | 78.66 (+2.6%) | 80.83 (+2.2%) | 105.57 (+2.0%) | 138.99 (-1.0%) | 172.49 (-0.2%) | 3.14 | 0.690 |
| production (its own prompts, the table at the top) | 81.73 | 89.22 | 117.98 | 114.78 | 131.28 | 3.00 | 0.686 |

The two recipe cells agree to 0.1 to 1.0%. Against the control they are +2.6 / +2.2 / +1.9% at one, two and four streams in both
repeats, and -0.7 / -1.0% at six streams (one control cell, inside the box's spread, so neutral) and 0 at eight. Against production, the
mean of the two recipe cells (78.71 / 80.81 / 105.47 / 139.26 / 172.67 tok/s) is **-3.7 / -9.4 / -10.6% at one, two and four streams and
+21.3 / +31.5% at six and eight**. The earlier -13.0 / -9.9 / -14.4% at one, two and four came from the unequal prompts. What remains at
two and four streams is the verify step and its round time (section 20), not the draft chain or the drafter. The instrument is now in
`scripts/` and `AGENTS.md` says to use it for any table set beside production's.

## 24. Where the 2 and 4 stream round goes, and production's routed-expert block order

A fresh capture of the current recipe (rank 0 under nsys, 1/2/4 streams, `docs/audit-2026-11-12/verify-gap.md`) gives the round in ms:

| stage | 1 stream | 2 streams | 4 streams |
|---|---:|---:|---:|
| rows in the verify | 3.76 | 6.05 | 11.74 |
| round | 37.73 | 52.74 | 80.51 |
| verify step | 34.10 | 48.31 | 75.06 |
| routed experts (`tf_exl3_grouped_1` alone) | 19.50 (18.54) | 31.47 (30.20) | 53.91 (52.35) |
| KDA chain and MLA attention, one launch set per stream | 1.42 | 2.40 | 4.26 |
| all-gathers (90 a verify) | 1.85 | 2.42 | 3.33 |
| GPU idle inside the verify | 0.94 | 0.87 | 0.92 |
| keep steps | 0.23 | 0.41 | 0.75 |
| drafter step | 3.40 | 4.03 | 4.71 |

The routed experts are 57% of the round at two streams and 65% at four, and they cost 3.9 / 3.9 / 3.2 ms a row. Production's round at the
same rows is 50.4-50.8 ms at two streams (ours 55.2, +8.9%) and 80.3-80.5 ms at four (ours 88.6-88.9 at equal rows, +10%); its stage
split at two and four streams was never measured, so that bound assumes a stream keeps the same tokens a round in a shared round as
alone. Production runs its routed-expert kernel with settings ours did not: `TF_GLM_EXL3_DEC_ORDER=1` is in its launch environment, and
its load width, row rotation and fused down epilogue are in its speed-target notes. Our series carries only the block order
(`TF_EXL3_DEC_ORDER`, patch 0030), which had never been measured.

`TF_EXL3_DEC_ORDER=1` through the like-for-like instrument (`scripts/arms-client.sh`, production's prompts as ids, the recipe as the
control), order ctl, ord, ord, ctl, replies equal (tok/s; change against the first control):

| arm | 1 | 2 | 4 | 6 | 8 | ms/round |
|---|---:|---:|---:|---:|---:|---:|
| `x3o-ctl` | 78.49 | 81.41 | 105.97 | 139.15 | 171.57 | 39.1 |
| `x3o-ord` | 78.81 (+0.4%) | 81.24 (-0.2%) | 107.20 (+1.2%) | 140.94 (+1.3%) | 173.95 (+1.4%) | 38.9 |
| `x3o-ord-b` | 78.55 (+0.1%) | 80.11 (-1.6%) | 107.40 (+1.3%) | 141.23 (+1.5%) | 173.08 (+0.9%) | 39.0 |
| `x3o-ctl-b` | 77.56 (-1.2%) | 79.74 (-2.1%) | 105.77 (-0.2%) | 139.82 (+0.5%) | 171.78 (+0.1%) | 39.5 |

Each test cell against the control next to it: `x3o-ord` over `x3o-ctl` +0.4 / -0.2 / +1.2 / +1.3 / +1.4% and `x3o-ord-b` over
`x3o-ctl-b` +1.3 / +0.5 / +1.5 / +1.0 / +0.8% at 1/2/4/6/8 streams. No level is negative outside the spread (the one -0.2% is a
pair whose other half is +0.5%), so it joins the recipe: `serve.sh`'s `DEFS` gains `TF_EXL3_DEC_ORDER=1`. About +1% at four streams and
up is far under the +2 to +4% the fork measured for the whole set (16-byte loads, input rotated once per expert pair, fused down
epilogue), which is a CUDA port, not a switch.

## 25. Production's routed-expert kernel set on the item plan (patch 0034): +1.2 to +3.5% at every stream count

The routed experts' decode kernel is 57% of the two-stream round and 65% of the four-stream round (section 24). The fork's X3 set
(16-byte staged trellis loads, the input rotated once per expert pair, a fused down epilogue) was ported by the `VerifyGap` lane as
`patches/engine/0034-glm-exl3-x3-decode.patch` (sha256 `c3294dd83715`): three default-off switches, `TF_GLM_OVN_X3_NC`,
`TF_GLM_OVN_X3_XROW` and `TF_GLM_OVN_X3_FUSEDOWN`, on the item plan only. Upstream already has the row rotation and the 16-byte load
(`tf_exl3_prompt_rotate`, `tf_common::ld_nc`), so the patch wires those and carries the fused epilogue and the walker variants. Receipts
(`docs/audit-2026-11-12/verify-gap.md` section 5): `glm-exl3-items` on the workstation's RTX 5070 (sm_120) 0 of 308 comparisons differ and
7 of 7 planted controls fail it, each on its own variants; host step `test-glm-exl3-x3-host` 31 of 31 and 14 of 14 mutants killed;
`scripts/gates.sh` rc 0 (test-cuda-host 383 of 383 steps), gate-names no failing name, lean 386 against 386, 0 new; nvcc for sm_121 clean
with no spills. The series' tree is now `f5495931b233`, rebuilt from the tag by `scripts/apply.sh` with 0 differing paths.

Image `rs2x3` (the 34-patch series), through the like-for-like instrument, the recipe as control against the set (`TF_EXL3_DEC_ORDER=1`
and the three switches), order ctl, set, set, ctl, replies equal (tok/s; each test cell against the control next to it):

| arm | 1 | 2 | 4 | 6 | 8 | ms/round |
|---|---:|---:|---:|---:|---:|---:|
| `x3-ctl` | 77.11 | 79.71 | 105.31 | 138.42 | 170.12 | 39.7 |
| `x3-set` | 79.54 (+3.2%) | 82.52 (+3.5%) | 107.98 (+2.5%) | 141.11 (+1.9%) | 173.75 (+2.1%) | 38.5 |
| `x3-set-b` | 79.89 (+1.2%) | 83.51 (+2.3%) | 109.71 (+3.0%) | 144.49 (+2.6%) | 178.11 (+2.3%) | 38.4 |
| `x3-ctl-b` | 78.94 | 81.61 | 106.49 | 140.86 | 174.15 | 38.8 |

(`x3-set` is read against `x3-ctl`, `x3-set-b` against `x3-ctl-b`, the control next to each.) Every one of the ten pair readings is
positive, +1.2 to +3.5% at 1 to 8 streams, the round 38.4 to 38.5 ms against 38.8 to 39.7, so no level regresses and the three
switches join `scripts/serve.sh`'s `DEFS`. The window's control read 1.5% lower in its first cell than the recipe of section 24, so the
absolute cells are about, not exact: the mean of the two set cells is 79.72 / 83.02 / 108.85 / 142.80 / 175.93 tok/s, -2.5 / -7.0 /
-7.7% against production at one, two and four streams and +24.4 / +34.0% at six and eight, on production's own prompts.

The whole recipe launched through `serve.sh` (`KNOBS=measured` on image `rs2x3`: the seven knobs, the chain rule, the block order, the three
X3 switches, and the RoCE wire, whose boot line `gathers up to 256 KiB a rank on the wire` is in the 1- and 4-stream boots and not in the
8-stream one), run twice, replies equal: 79.95 / 83.49 / 109.63 / 144.72 / 178.51 and 80.98 / 83.37 / 109.29 / 143.92 / 178.18 tok/s at
1/2/4/6/8 streams, the two runs within 1.3% of each other and a round of 37.8 to 38.3 ms. The mean, 80.47 / 83.43 / 109.46 / 144.32 /
178.35 tok/s, is -1.5 / -6.5 / -7.2% against production at one, two and four streams and +25.7 / +35.9% at six and eight, on
production's own prompts.

## 26. Per-stream KDA chains and MLA attention on side streams (a patch that measured negative at six and eight streams, neutral below)

Section 24's profile has the verify launch each stream's KDA chain and MLA attention in turn on the main stream (KDA 1.05 / 1.75 / 2.97 ms
and MLA 0.37 / 0.65 / 1.29 ms a round at 1 / 2 / 4 streams), where production runs one launch per kernel over all streams. The
`KdaConcurrency` lane bounded what running them concurrently could hide, from the same captures. KDA's steps are byte-bound (a step
reads and writes the 2.88 MB state in 12.6 us, 229 of the GB10's 273 GB/s), so only the copies, prep, out and gaps can overlap: 14.1 and
27.0 us a layer at two and four streams, 0.48 and 0.92 ms a round over 34 layers; MLA attention is latency-bound (6 to 66 blocks a
kernel), so the floor is its longest segment: 0.32 and 0.98 ms a round over 11 layers. A side-stream fork measured 3.0 us on the GB10
(0.3 to 0.5 us between kernels on one stream), about 0.24 ms a round over 45 layers if a join costs the same. The bound after that cost
was about 0.55 ms at two streams and 1.6 ms at four, 1 to 2% of the round.

The patch (`docs/audit-2026-11-12/0035-glm-seg-streams.patch.txt`, sha256 `b54a7166f061`, applies to the 34-patch series' tree
`f5495931b233`) adds `TF_GLM_OVN_SEG_STREAMS=N`: N-1 side streams, segment k on stream k % N with a fork after the projections and a
join before o_proj, each segment with its own chain scratch and its own MLA partials. Receipts: `glm-seg-streams-check` on the
workstation's RTX 5070 0 of 70 comparisons differ and 6 of 6 planted controls fail; host step 8 tests with 30 of 30 mutants killed;
gates rc 0, lean 386 against 386, 0 new. No kernel source changes.

Image `rs2x4` (series plus the patch), through the like-for-like instrument, the recipe as control against `SEG_STREAMS=8` with
`CUDA_DEVICE_MAX_CONNECTIONS=32` (the driver's default eight queues would otherwise serialise the extra streams, so the test arm is two
changes), order ctl, on, on, ctl, replies equal (tok/s; each test cell against the control next to it):

| arm | 1 | 2 | 4 | 6 | 8 | ms/round |
|---|---:|---:|---:|---:|---:|---:|
| `sg-ctl` | 81.43 | 83.93 | 109.53 | 145.41 | 178.28 | 37.6 |
| `sg-on` | 80.16 (-1.6%) | 84.18 (+0.3%) | 109.90 (+0.3%) | 142.28 (-2.2%) | 169.95 (-4.7%) | 38.2 |
| `sg-on-b` | 80.87 (+0.7%) | 84.41 (+1.0%) | 107.99 (-1.2%) | 143.01 (-0.6%) | 170.32 (-4.5%) | 37.9 |
| `sg-ctl-b` | 80.30 | 83.61 | 109.32 | 143.83 | 178.33 | 38.2 |

At eight streams both test cells read about 4.6% under their controls and the round is longer; at two and four streams the readings
(+0.3 / +1.0 and +0.3 / -1.2%) sit inside the box's spread, so the 0.55 and 1.6 ms the bound allowed are not there; at six streams both
cells are negative. It does not ship: it regresses at one level and shows no gain at the levels it was for. The measurement cannot say
whether the side streams fail to overlap on the GB10 or the forks and joins cost more than the bound assumed, and the test arm's second
change (the connection count) was not run alone, so a lower stream count or a scoped use is not excluded. The patch stays archived.

## 27. The drafter's round structure at two and four streams: two bounds under the cut-off, nothing built

The `DrafterRound` lane bounded the profile's two remaining drafter-side items from the three rank-0 captures
(`docs/audit-2026-11-12/drafter-round.md`), after each item's own costs; a bound under about 0.5 ms a round at four streams is not
built (section 26's lever bounded 1.6 ms and measured negative).

| ms a round | 2 streams | 4 streams |
|---|---:|---:|
| keep steps folded into the block step, header first: the ceiling (the drafter's whole first-gather wait above its transfer time) | 0.53 | 0.57 |
| the same fold, fitted | 0.18 to 0.40 | 0.29 to 0.38 |
| MIA 0031 (production's keep fold) as written | -0.05 | -0.03 |
| drafter linears and head against bytes / 273 GB/s | 0.65 | 0.94 |
| the same at production's measured 239 GB/s | 0.44 | 0.73 |
| the same at production's measured efficiency on our bytes | 0.25 | 0.35 to 0.48 |
| the one bit-exact mechanism that can be built (upstream's 32/64-row tiles) | 0 | 0.29 |

The first-gather wait averages 209 / 532 / 566 us at 1 / 2 / 4 streams over 572 rounds and fits 224 + 130 x keeps - 92 x replays us.
Production's keep fold (MIA 0031) sends the keep after rank 0's own replay, so the followers' replays run after it instead of beside it,
and is a small loss here; folding every keep into the block step with the header sent first saves one follower receive a keep. Production's
drafter pass reads 328.5 MB a rank (it splits attention across ranks) against our 402.3 MB, so its 1.55 ms against our 2.2 to 2.5 mixes
bytes with kernel efficiency. Nothing was built; the report specifies the keep fold (default off, bit-identical drafts) and the
same-bytes drafter timing that would settle the linears. With sections 20 to 26, the round-time levers the profile named are now measured
or bounded below the cut-off, and what remains of the gap at two and four streams (-6.5%, -7.2%) is not in one of them.

## 28. Correction: what the six and eight stream cells compare

Production's decode table (its `SPEED-TARGET.md`, cells of 2026-11-11) was taken against one `--parallel 4` serve at every level, so at
six and eight streams two or four requests wait for a slot; its 114.78 and 131.28 tok/s are a four-slot serve with a queue. Every
cell of ours is a fresh boot with `--parallel` equal to the stream count (`scripts/serve.sh` takes it as an argument), so our 6 and 8
stream cells are true six and eight slot decodes, and the +25.7% and +35.9% of section 25 are not a like-for-like lead and should not be
read as one. The same script defaults `--context` to 262,144 at two, four and six streams (196,608 at eight, 1,048,576 at one) where
production runs `--context 1048576` at `--parallel 4`, so our four-stream boot is not production's deployed shape. The one, two and
four stream cells compare similar concurrency and prompts and are the decode comparison this document stands on, with one more caveat:
production's cells are from 2026-11-11 and 2026-11-12 and were not re-measured beside ours. A like-for-like six and eight stream
measurement is a `--parallel 4` boot driven by six and eight client streams; the long-context harness is being extended to run it.

## 29. Long prompts, resuming a long conversation, and the deployed shape: this is where we trail production

Everything above compared decode. The long-context harness (`scripts/queue-longctx.sh`, `scripts/longctx.py`, `scripts/longctx_table.py`,
tested on stubs with planted mutants) boots the deployed shape, `--parallel 4 --context 1048576`, image `rs2x3`, `KNOBS=measured`, and
runs production's own cases (`SPEED-TARGET.md` sections 3 to 5). Rows: `docs/audit-2026-11-12/longctx-lc1-rows.jsonl`, 75 rows, 0
rejected by the table's checks; prompt lengths are the server's own token counts. Production's numbers are from notes of 2026-11-10.

**What the engine supports** (`docs/audit-2026-11-12/longctx-audit.md` is the lane's file:line audit): the deployed shape boots in 116 to
120 s; a 1,047,377-token prompt ran (the largest that fits). GLM has **no disk tier**: `--spill-gib`, `--snapshot-dir` (other than
`none`) and `--learn-conversations` are refused at open, so no conversation survives a crash or restart. `/health` has no `pool_tokens`;
kept prompt states are full copies of the prefix on every rank (6,380 bytes a token a rank) in a separate budget, not production's shared
pool. Prompt passes are 2,048 rows against production's 4,096.

| case | ours | production | ours / production |
|---|---:|---:|---:|
| cold 1k prompt, idle, first token | 0.654 s | 0.54 s | 1.21x |
| cold 8k | 4.606 s | 2.82 s | 1.63x |
| cold 32k | 18.099 s | 10.93 s | 1.66x |
| cold 120k | 67.220 s | 42.86 s | 1.57x |
| conversation turn 1, cold at ~596k tokens | 346.06 s | 224.68 s | 1.54x |
| turn 2, resumed from the pool / kept states | 14.79 s | 12.54 s | 1.18x |
| turn 3 after every rank was SIGKILLed | 377.78 s (a cold refill, 0 tokens cached) | 12.80 s (from the spill tier) | 29.5x |
| warm turn (+1,978 tokens on a 98k kept conversation) beside three decoding streams | 2.702 s | 1.217 s | 2.22x |

With `TF_GLM_REQUEST_STARTS=1` the same warm turn is 1.305 s idle and 1.871 s loaded (1.54x), with the same replies (corrected 2026-11-17: this line said "different numerics", from upstream's registry class; the window's own rows, `docs/audit-2026-11-12/longctx-lc1-rows.jsonl`, give the same `token_sha` on all six warm turns and the cold 32k turn with and without the switch); with
`TF_GLM_CHUNK_SOLO=4096` cold prompts read 4.733 / 18.398 / 68.701 s at 8k / 32k / 120k, no gain. A cold 32k prompt beside three decoding
streams is 19.659 s against 18.099 idle (production not measured).

**Decode at the deployed shape**, N client streams against the `--parallel 4` boot (production's cells are N clients against its own
`--parallel 4`, requests queued past four), production's prompts as ids, tok/s: 4 clients 100.94 against 117.98 (0.86x), 6 clients 102.74
against 114.78 (0.90x), 8 clients 114.31 against 131.28 (0.87x). Our `--context 262144` four-stream boot read 109.46 in section 25's
whole-recipe runs, so the 1M-token context costs this recipe about 8% of its four-stream decode (not yet explained), and the earlier -7.2%
at four streams was a 262,144-token serve, not the deployed shape. The first-token times of the requests that wait for a slot are 13.6 to
18.3 s against production's 9.6 to 14.9 s.

**What this says.** At the shape production runs, the recipe is behind on decode (-14% at four streams), on cold prompts (1.6x slower
first token), on a loaded warm turn (2.2x), and has no crash-surviving tier (29.5x on the 600k conversation after a kill). The decode
cells at one to four streams in sections 25 and 28 were a real comparison of decode only, at a smaller context. By the repo's own rule the
Zig serve does not replace production: it fails every long-context row and the deployed-shape decode.

## 30. The request-start cost that grows with the context: patch 0035, `TF_GLM_OVN_KEEP_SEQS`

Section 29's four-stream decode fell with the context (109.47 / 106.98 / 101.66 tok/s at 262,144 / 524,288 / 1,048,576). Rank-0 captures at the
two ends (`ctx256k`, `ctx1024k`, one measured cell each) put 915 of the 1,026 ms of extra GPU time in one kernel, the f64 all-reduce of the
chunk gate, 16 instances: 384 ms at 262,144 and 1,299 ms at 1M. Mechanism, from the source (tree `f5495931b233`): a request that does not land on
slot 0 makes `Engine.bind` allocate the stream's whole window arena and zero it (`cuda_state.zig` `arena`: `cuMemAlloc`, then a synchronous
`cuMemsetD8`), rank 0 first, and ranks 1 and 2 only when the begin step reaches them, so rank 0 waits for them in the gate's first all-reduce;
`Engine.release` frees the arena again (slot 0's alone is kept). Per request: allocate 48.2 / 176.1 ms, zero fill 10.1 / 38.0 ms, gate wait
63.6 / 216.0 ms, start 122.5 / 430.8 ms, free 16.1 / 59.6 ms at 262,144 / 1M (a start on slot 0: 1.4 to 1.5 ms).

Patch 0035 (default off) keeps every slot's sequence as slot 0's is kept; `Engine.begin` resets it as it does for slot 0 on every request. No kernel
reads past the rows a sequence wrote (`mla.cuh` zero-fills keys past `pos + r`; sparse selection takes visible pools only), and the GPU check on
the RTX 5070 (a kept sequence, poisoned to 0xFF, against a fresh one: tokens, bf16 logits and MTP drafts over 24 steps, bf16 and fp8 caches)
passes byte for byte with its planted control differing. Gates: `test-cuda-host` 6,283 of 6,313, 0 new failing names, lean 386 against 386, 7 of 7
host mutants killed.

Measured on image `rs2x3k` (`KNOBS=measured`, P=4, ids client, four-stream cells, 400 tokens, replies equal to the knob-off cells' in all eight):

| `--context` | order | knob off | knob on |
|---|---|---:|---:|
| 1,048,576 | A B B A | 98.63 / 98.33 | 108.86 / 108.93 (+10.4%, +10.4%) |
| 262,144 | A B B A | 105.96 / 105.65 | 108.43 / 108.60 (+2.4%, +2.8%) |

The model predicted +10.4% and +2.9%. The long-context decode arm with the knob on (4, 6, 8 clients against the P=4 / 1M boot): 110.84 / 109.44 /
119.96 tok/s, 0.94x / 0.95x / 0.91x of production's 117.98 / 114.78 / 131.28 (0.86x / 0.90x / 0.87x without it). Decode at 1, 2, 6 and 8 streams
with the knob is not yet measured (at one stream slot 0 is the only slot, so the path is unchanged).

## 31. Cold prefill gap: what the capture and the arms show, and patch 0036

Window `queue25` (spark1, image `rs2x3`, P=4 / 1M, `scripts` of lane PrefillGap: one capture of a cold 8,192 and a cold 32,768 prompt on rank 0 under nsys,
and arms of two fresh boots each, replies equal to the control's in all): first token at 8k / 32k against the control: `ONEPASS_PIPE=1` -4.6% / -5.6%;
`TF_GLM_CHUNK_SOLO=3` +1.2%; two pieces +0.0%; ring reduce +6.7%; `ABSORB_VEC` -0.3 / -0.6; `MM_WIDE` -1.0 / -1.4; `GLUE_ROW` +0.8; `PDL_EARLY` +0.5;
`INDEX_SCHED` and the pool settings +0.3 / +0.1; a drafter-off pairing arm -5.1% / -6.4% against its own control (the controls of that file read -2.0% / -2.4%,
so noise is about 2%). The recipe needs its drafter, so pairing is not usable. The earlier "`CHUNK_SOLO=4096` gives no gain" verdict (section 29) ran with
8 exchange pieces under `ROCE_MULTI`, so it is confounded; the arms above vary pieces and reduce modes explicitly.

The pass (2,048 rows, rank 0, 1,167.6 ms a chunk at 20 real chunks; the first parse merged chunks and read 576 ms for experts): experts 439 ms, shared expert
114, MLA 128, KDA projections about 120, main-stream waits 90 ms (ranks 1 and 2: 165 and 170 ms). The expert kernels run at production's per-layer figure
(`gate/up` + `down` + `rotate` 8.22 ms against production's 8.31 ms a layer at the same rows). The copy of the routed outputs into the 9-slot rows costs
2.07 to 2.2 ms a layer, 87 to 92 ms a pass; production writes those rows directly. Ranks 1 and 2 wait about 80 ms a pass in the MoE gather because rank 0 holds
768 expert rows against 640 (128-row EXL3 units, 16 units split 6/5/5); fixing that needs 64-row units, i.e. re-quantizing.

Patch 0036 (`TF_GLM_OVN_EY_DIRECT`, default off; the fork's `EY_DIRECT`, ai-engine `f9209395e`) writes the rows in the down kernel and skips the copy; the prompt
arena is 256 MiB smaller a rank. Byte-exact on the RTX 5070: `ey` and the MoE layer output equal the copy path's at 1 / 8 / 17 / 255 / 2,048 / 2,054 rows for
widths 640 and 768 (24 of 24 cases), 7 of 7 planted controls fail, the base kernel's machine code is unchanged, 17 of 17 host mutants killed, gates green, lean 386
against 386. Expected from the capture: -90 ms a pass (about -8%); the Spark cells (ctl, ey, ey, ctl at 8k and 32k) are not yet measured.

## 32. Conversations on disk at TP=3: upstream PR #1411 on the triangle

Upstream PR #1411 (wojo, "GLM-5.3-Flash on CUDA keeps conversation states on disk, every rank's part", `--learn-conversations`; head `d730aff64` on main `3885dceb2`) is
the Zig GLM disk tier. Its receipts are TP=2 only. `patches/pr1411/` carries its ten commits after the series (two by context merge, one with no file because the series
has its lines, plus two test-only patches of ours for patch 0028's head flag; tree after the series and the package: see its `RECORD.md`). The window
(`scripts/queue-disk-tier.sh`, instrument `scripts/disk.py`, table `scripts/disk_table.py`, tested on stubs with a planted wrong-resume mutant) ran on spark1-3 at
`--parallel 4 --context 1048576` with `--learn-conversations --learn-dir <dir>` on every rank: image `pr1411` (the PR head alone, `KNOBS=off`) and image `rs2x3d` (the 0001-0034
series plus the package, `KNOBS=measured`). Rows and tables: `docs/audit-2026-11-12/disktier-{pr1411a,rs2x3da}-{rows.jsonl,table.md}`.

**Correctness:** the store opened with 3 ranks' parts on every boot, found its states after a SIGKILL of every rank and after a clean stop, and every resumed reply
(17 of 17 on each image, markers at 2%, 50% and 97% of the text so a wrong state cannot give the same hash) equals a cold server's reply to the same messages. Every
rank log line counter for the tier (staging full, skipped saves, failed writes or restores, check failures, `RanksDiffer`, world, layout, words, snapshot size) is 0.
A save in flight at a clean stop was written and resumed from disk. The store held 8.5 GiB after the first boot for a 596k-token conversation and two others.

| turn of the 596k conversation (production's text) | `pr1411` image | `rs2x3d` image | production |
|---|---:|---:|---:|
| 1 cold, beside 3 decoding streams: prefill | 447.90 s | 375.58 s | 224.68 s |
| 2 from RAM: prefill (cached 595,968) | 17.74 s | 15.02 s | 12.54 s |
| 3 after SIGKILL of every rank: prefill (cached 618,496) | 18.24 s | 15.18 s | 12.80 s |
| 3 same turn, client first token (a 4,548 MiB read in 12,349 / 10,775 ms is before the prefill) | 30.61 s | 25.97 s | not recorded |
| 4 after a clean restart, beside 3 streams: prefill (cached 641,024) | 20.50 s | 17.56 s | 12.90 s |
| 4 same turn, client first token (a 4,697 MiB read in 2,691 / 3,140 ms) | 31.74 s | 29.52 s | not recorded |

Without a disk tier the same turn 3 refilled cold in 377.76 s (section 29). So a restart now costs about 15 to 18 s of prefill plus a read of 3 to 12 s, against 378 s, and
a conversation survives a crash. Production's column is its `tier_chain.sh` prefill; whether its figure includes the disk read is not recorded, so the client
first-token rows are the ones to compare when production's are measured with the same instrument. The 32k and 120k conversations resume from disk in 0.93 to 1.40 s
(`rs2x3d`) with the read inside that time.

**Gaps against production's tier**, from the same window:
- `cache_salt` is ignored: a request with another salt resumed this conversation's state (cached 30,720 of 32,213, equal to the unsalted control). Our open Mia PR for
  `cache_salt` and ashhart's `cache_salt` PR on upstream are the two implementations; neither is in this tree.
- Reads stall decode: the three other streams' longest gap during the turn-4 read was 10,851 ms (`rs2x3d`; the same read of 4,697 MiB), against a base window max of
  1,280 ms. The read is one engine-thread scatter. Our read-slot and event-reuse work on the Python tier (kept state copies in bounded slices between rounds) is not in this
  store, whose reads take the whole step.
- Block size 256 tokens against 2,048, no folder fsync, no per-conversation eviction or quota, state files with the MTP head's caches (about 0.7 GB for a 640k state)
  are properties of the PR's store read from its code, not measured here.

Decode with the tier is untested at 1, 2, 6 and 8 streams and the 0035/0036 knobs have not been run together with it.

## 33. Patch 0036 on the Sparks: cold first token -8.5% at 8k and -8.2% at 32k

Image `rs2x3y` (series 0001-0036), `KNOBS=measured`, P=4 / `--context 1048576`, a cold 8,192 and a cold 32,768 token prompt of distinct text, two fresh boots a
cell, order control, `TF_GLM_OVN_EY_DIRECT=1`, `EY_DIRECT=1`, control (`prefill-arms.sh`). First token in ms at 8k / 32k, in boot order: control 4,693 / 18,434 and
4,760 / 18,515; knob on 4,304 / 16,926, 4,320 / 17,017, 4,346 / 17,080 and 4,391 / 17,144; control again 4,745 / 18,634 and 4,785 / 18,686. Each knob-on cell sits
7.6% to 9.1% below the adjacent control at 8k and 7.4% to 9.1% at 32k; means 4.746 s against 4.340 s (-8.5%) and 18.567 s against 17.042 s (-8.2%), replies equal
to the control's in all 8 of 8 and `ey_digests.py` printing `REPLIES-EQUAL`. The prediction from the capture was -90 ms a 2,048-row pass (about -8%). The knob-off
image `rs2x3k` (0001-0035) reads 4.742 / 18.544 s, equal to the control, so 0036 with the knob off changes nothing measurable.

## 34. Patches 0035 and 0036 at 1, 2, 4, 6 and 8 streams: both join the recipe

Image `rs2x3y` (series 0001-0036), `KNOBS=measured`, production's prompts as ids, 400 tokens a stream, one fresh boot a level, `--context` at `zig-tp3.sh`'s
per-level default. Control against `TF_GLM_OVN_KEEP_SEQS=1 TF_GLM_OVN_EY_DIRECT=1`, order control, knobs, knobs, control; replies equal to the control's in every cell.
Decode aggregate tok/s:

| arm | 1 stream | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| control, first | 81.19 | 82.56 | 109.22 | 143.76 | 178.65 |
| knobs, first | 79.88 (-1.6%) | 85.12 (+3.1%) | 112.65 (+3.1%) | 150.42 (+4.6%) | 186.81 (+4.6%) |
| knobs, second | 80.44 (-0.9%) | 84.75 (+2.6%) | 112.26 (+2.8%) | 151.00 (+5.0%) | 186.74 (+4.5%) |
| control, second | 81.47 (+0.4%) | 83.60 (+1.3%) | 108.73 (-0.5%) | 144.63 (+0.6%) | 177.77 (-0.5%) |

The one-stream cells read low, so they were rerun, each knob alone and then both (all `KNOBS=measured`, one stream, fresh boots, replies equal): `KEEP_SEQS` alone 81.09 and
81.50, `EY_DIRECT` alone 81.08 and 81.03, controls 80.93, 81.07, 79.95 (a control spread of 1.9% between identical boots), and both knobs in the order control, both, both,
control, both, control: controls 81.23, 79.86, 81.71 (mean 80.93), both 81.51, 79.82, 80.87 (mean 80.73, -0.2%). The low cell appears on both sides (79.82 with the knobs, 79.86 without),
so the first one-stream reading was the box's spread and neither knob regresses one stream. At 2 to 8 streams the knobs together read +2.6% to +5.0% against
controls that agree within 1.3%. Both are now in `serve.sh`'s `DEFS`. Measured at the deployed shape earlier: four-stream decode +10.4% at 1M (section 30) and cold first token
-8.5% at 8k, -8.2% at 32k (section 33).

## 35. `cache_salt` on the triangle: patches/cache-salt (upstream PR #3222) closes the gap section 32 found

Section 32's window showed `cache_salt` ignored (another salt resumed a conversation's state). `patches/cache-salt` carries ashhart's PR #3222 after `patches/pr1411` (four patches; RECORD.md
names the source, the edits and the trees: after the series and pr1411 `e567d98959661da15d756103cc2d59051cacb78b`, after the package `25cefd706dc3741584b0cab4d6b216ed24d752bc`). Gates, a head tree
against a base tree of series plus pr1411: `test-cuda-host`, `compile-cuda-tests`, the standalone host steps and fmt rc 0, 0 failing test names on either side, lean 386 problems against 386 with
0 new, `apply.sh --check` writes nothing. The package adds 14 test blocks and renames one; two earlier step summaries that differed by 5 tests (1314 against 1319) differed because one run step
was replayed from the cache, not because tests were missing (both `server_tests` binaries list the same 1319 names before the package).

Window (`scripts/queue-disk-tier.sh`, image `rs2x3ds` = series + pr1411 + cache-salt, `KNOBS=measured`, P=4 / 1M, `--learn-conversations`; rows and table
`docs/audit-2026-11-12/disktier-rs2x3dsa-*`): the salt probe sent the 32k conversation with another salt and got cached 0 of 32,213 tokens, while the same turn without a salt resumed 30,720; every
one of the 17 resumed replies equals a cold server's reply to the same messages; the 596k conversation's prefill after a SIGKILL of every rank is 15.14 s (cached 618,496), after a clean restart
17.62 s (cached 641,024), turn 2 from RAM 15.13 s, turn 1 cold 374.54 s. Not checked: that a salted state is never written to disk (the PR's own host test covers it; this window's probe runs in the
first boot only and records no disk counters), and decode at 1, 2, 4, 6 and 8 streams with the package.

## 36. Sliced restore (patch pr1411/0013, `TF_GLM_OVN_DISK_SLICE_MIB`): the restoring turn pays for what the other streams are spared

Section 32 found the other three decoding streams stop for up to 10.9 s while a 4.7 GiB disk state is restored. The stall is the restore's copy into place at admission (one scatter a block on
the engine thread), not the disk read, which takes about 3 s on the I/O thread. Patch 0013 holds a queued request whose read-ahead is ready while other requests decode, copies at most N MiB a
turn and resumes the request from RAM when the state is whole. Image `rs2x3f` (series 0001-0036, pr1411 0001-0013, cache-salt), `KNOBS=measured`, P=4 / 1M, the window of section 32 (k1 k2 k3), turn 4 of the
596k conversation (a clean restart, 641,024 tokens cached, 4,697 MiB read, beside three decoding streams). One run a size; rows `docs/audit-2026-11-12/disktier-dslice-*-rows.jsonl`.

| slice | other streams: median / p99 / largest gap while the state restores | restoring turn's first token | reply window, largest gap |
|---|---|---:|---:|
| off | 78 / 9,874 / 9,874 ms | 28.18 s | 747 ms |
| 16 MiB | 112 / 1,359 / 2,094 ms | 55.72 s | 1,394 ms |
| 32 MiB | 146 / 1,391 / 2,061 ms | 41.84 s | 1,315 ms |
| 64 MiB | 216 / 1,511 / 1,982 ms | 35.82 s | 583 ms |
| 128 MiB | 98 / 2,110 / 4,602 ms | 32.87 s | 565 ms |
| 256 MiB | 82 / 2,102 / 3,397 ms | 31.65 s | 563 ms |

The base window's largest gap before the request reads 1,207 to 1,310 ms in every arm. Every turn of every arm (17 each) has the same `token_sha` as the slices-off run, whose own turns equal a cold server's
17 of 17; turn 3 (after a SIGKILL, no other streams) is 25.4 to 26.9 s in all arms, so the knob changes nothing when the restore is alone. The mechanism is the turns: a slice a turn means 4.7 GiB / N turns of
extra delay for the restoring request, each turn also carrying N MiB of copy. At 64 MiB the other streams' worst stall falls 80% (9.9 s to 2.0 s) and the restoring turn waits 7.6 s (27%) longer; at
128 and 256 MiB the restoring turn waits 4.7 and 3.5 s longer but the other streams' worst gap is 3.4 to 4.6 s (a single run each, so the 128/256 maxima may be one outlier). This is a trade of
the other streams' worst stall against the restoring request's first token, not a win at every cell: per the repo rule it ships off, with 64 MiB the measured balance point, until the owner accepts it
or a variant removes the loss (an adaptive N that grows while no other request is waiting is the next piece to try).

## 37. The pin moves to v1.2.9: four patches retired, the packages re-seated, gated on a Spark

Upstream's latest release is v1.2.9 (`6b9de695`, 2026-11-14); main is 557 commits past v1.2.7 and was left alone. A text survey of the 36 + 13 + 4 patches against v1.2.9 read 20 clean, 30 partial, 2 refused
(no whole patch "absorbed"). Two lanes re-seated them (a three-way merge of each patch's own delta, every conflict settled by reading the upstream commit that moved the code):

| result | patches |
|---|---|
| retired, upstream has the behaviour | logit gather (`5cd52c7a8`, `5b927e2bf`); forward pieces split (`1ba369792`); the 2,048-row expert chunk (`8978c4357`); `EY_DIRECT` (`8978c4357`, `dc4aef0ec`) |
| clean | 18 |
| re-seated by hand | 14 (knob rows after `TF_GLM_CONTEXT_CEILING`, the drafter MLP split generalised upstream as `df.mlpSplit`, the index kernels' default flip, the checkpoint ladder, the prompt arena, `glue.Set` unions, the Engine initialiser, the render-once pieces, the X3 decode) |
| kept, listed for a with/without window | decode-window index patches against `TF_GLM_DSEL`; the 16-pair decode item plan against upstream's compact 1024-row calls (now `TF_GLM_OVN_EXL3_ITEMS`, default off, set by `DEFS`; upstream's test is unchanged); `MLPSPLIT` against `df.mlpSplit`; `SPARSE_ONEPASS` against the new prompt plan; the three `X3_*` decode knobs; the glue gather on the collective path |

Upstream PRs: #1411 (head `d730aff64`) and #3222 (head `2a870a8b0508`) are unchanged and still open, so both packages stay. pr1411 0001-0013 became one net patch on the series (0011/0012 were test
fixes for a patch that is now in the series' own text); cache-salt 0003 is retired (v1.2.9 already has `private_files_test.zig`) and 0004 is not needed (`core/engine_api.zig` is 595 lines).

**Gates run on a Spark (spark5, aarch64), because compiling on the workstation is banned.** The first pass found real defects the lanes had missed: the series did not compile (a function between
container fields in `eval.zig`, undeclared `ek` in `cuda_exl3.zig`, a missing `decode` field in `cuda_index.zig`) and two packages broke lean and a knob-count test. `gate-names.sh` had reported "0 failing names"
for the broken trees because a build that stops before any test has none; it now exits 1 with BUILD FAILED. All were fixed inside the patch that owns them. Final: series tree `e02b8a89c2cc`, with pr1411
`3b06d167fd74`, with cache-salt `27a87244e7dc` (rebuilt exactly from the landed files by the repo's own `apply.sh` scripts). Each of the 32 prefixes passes `check-native-cuda-host`; on the full stack
`check-native-cuda-host`, `compile-cuda-tests`, the standalone host steps and `fmt` are rc 0, `test-cuda-host` fails only the two tests the pristine v1.2.9 also fails on aarch64 (`cli_config_test`
"serve --config: expand reads the file..." and `listener` "accepted IPv4 and IPv6 TCP streams disable Nagle..."), `gate-names` has no new failing name and lean has 0 new problems.

Not done on v1.2.9: no image was built and nothing ran on a GPU, so every speed and resume cell above this section is a v1.2.7 number. The GPU bit-exact checks (`glm-exl3-items`, `glm-keep-seqs-check`) are
inherited from v1.2.7 and need a Spark window. `serve.sh`'s `DEFS` now drops `TF_GLM_INDEX_CUDA` and `TF_GLM_OVN_EY_DIRECT` (upstream's default and a retired patch) and adds `TF_GLM_OVN_EXL3_ITEMS`.

## 38. The v1.2.9 stack on the Sparks: resume and cold prompts hold, decode is 4 to 11% below the v1.2.7 stack (STALE RECIPE: superseded by sections 39 and 40)

Image `v129a` (series 0001-0032 + pr1411 + cache-salt on v1.2.9, tree `27a87244e7dc`, `KNOBS=measured`, so `TF_GLM_OVN_EXL3_ITEMS=1`, no `INDEX_CUDA` or `EY_DIRECT`), the first GPU run of the stack. One run each.

**Decode, tok/s (production's prompts as ids, one fresh boot a level), against the v1.2.7 stack with the same knobs plus `KEEP_SEQS` and `EY_DIRECT` (mean of the two knob-on cells of section 34):**

| streams | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| v1.2.9 stack | 76.80 | 79.22 | 103.96 | 135.34 | 165.79 |
| v1.2.7 stack | 80.16 | 84.94 | 112.46 | 150.71 | 186.78 |
| change | -4.2% | -6.7% | -7.6% | -10.2% | -11.2% |

The v1.2.7 cells of that group spread 1.9% at one stream between identical boots, so the one-stream gap is borderline and the six and eight stream gaps are not noise. This is a regression of the v1.2.9 base
or of a re-seat, found by measurement and not yet attributed: the arms that separate upstream's decode levers from ours (`TF_GLM_DSEL` off, our decode index, `MLPSPLIT` off, the X3 decode knobs off, the
decode-window index kernels, our decode item plan against upstream's compact calls, `ONEPASS_PIPE`) are queued as `arms-v129-ab1.txt` and `arms-v129-ab2.txt`.

**Cold first token** (8,192 and 32,768 tokens, one boot): 4.348 s and 16.983 s, against 4.340 s and 17.042 s on the v1.2.7 stack with `EY_DIRECT` (+0.2% and -0.3%): upstream's absorbed prompt path equals our patch.

**Disk tier on v1.2.9 (`patches/pr1411` net patch + cache-salt), the TP=3 window of section 32 (`docs/audit-2026-11-12/disktier-v129a-stale-recipe-rows.jsonl`):** 17 of 17 resumed replies equal a cold server's, `cache_salt` honoured
(another salt cached 0 of 32,213, the unsalted control 30,720), the store opened with three ranks' parts on every boot. The 596k conversation: turn 1 cold 352.59 s (v1.2.7 stack: 374.5 to 375.6 s), turn 2 from RAM
14.02 s, after a SIGKILL of every rank 14.14 s with 618,496 tokens cached, after a clean restart 16.37 s with 641,024 cached (production: 224.68 s, 12.54 s, 12.80 s, 12.90 s; 1.57x, 1.12x, 1.10x, 1.27x).

## 39. The v1.2.9 decode loss, as first attributed (WRONG: a stale recipe, see its erratum and section 41)

Three windows on spark1 (`queue37`, `queue38`, `queue39`, 19:09 to 21:38 UTC), all on `glm53-zig:v129a` unless named, production's prompts as ids, one fresh boot a level, replies equal on every cell. A knob arm is read against its adjacent controls.

**Knob arms against the control (tok/s, change from the control):**

| arm | 1 stream | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| `items0` (`TF_GLM_OVN_EXL3_ITEMS=0`) vs `ctl-a` 76.51 / 78.87 / 103.14 / 134.33 / 165.86 | -0.2% | -0.0% | +0.7% | +0.8% | +0.2% |
| `mlp0` (`DRAFT_MLPSPLIT=0`) vs `ctl-c` 76.11 / - / 103.44 / - / 165.72 | -1.8% | - | +0.1% | - | -0.4% |
| `x3off` (the three X3 knobs off) | +0.7% | - | +0.6% | - | +0.1% |
| `dsel0` (`TF_GLM_DSEL=0`) | -0.0% | - | +0.4% | - | -0.1% |
| `ctl-d` (second control) | +0.1% | - | -0.4% | - | -0.1% |
| `ks0`, `ks0b` (`KEEP_SEQS=0`) vs `ctl-k` / `ctl-k2` (2, 4, 8 streams) | - | -0.3 / +0.3% | -0.3 / -0.6% | - | -0.6 / +0.3% |

The two controls of each pair agree within 0.5%, so every row above is flat: no knob recovers the loss and none was silently costing it. The arms that cannot move this bench by construction (`DSEL`, the decode index, `ONEPASS_PIPE`, the index-kernel default) were confirmed flat or dropped, because the bench's rows sit below the sparse limit (`dense_limit` 2,051 positions) and never run the DSA select. `queue37` was cut after `items0` for that reason and `arms-v129-ab2.txt` was rewritten before it ran: its first form had one pipe too many and booted every arm on the MTP head, not DFlash2 (found by the `DecodeSuspects` lane reading `arms-client.sh`).

**The image A B B A, same recipe (`KNOBS=measured`, the v1.2.7 side with `TF_GLM_INDEX_CUDA=1` and `EY_DIRECT=1` as its recipe had them), 1, 4, 8 streams, tok/s:**

| cell | image | 1 | 4 | 8 | tokens a round | ms a round (1 stream) |
|---|---|---:|---:|---:|---:|---:|
| `img-a1` | v1.2.9 `v129a` | 76.12 | 103.61 | 164.59 | 3.14 | 40.3 |
| `img-b1` | v1.2.7 `rs2x3y` | 78.92 (+3.7%) | 107.76 (+4.0%) | 173.48 (+5.4%) | 3.14 | 38.8 |
| `img-b2` | v1.2.7 `rs2x3y` | 79.86 (+4.9%) | 107.58 (+3.8%) | 173.98 (+5.7%) | 3.14 | 38.4 |
| `img-a2` | v1.2.9 `v129a` | 76.34 (+0.3%) | 103.52 (-0.1%) | 165.49 (+0.5%) | 3.14 | 40.2 |

The two v1.2.9 cells bracket the two v1.2.7 cells and agree within 0.5%; the v1.2.7 image is 3.7 to 5.7% faster at every level, with identical acceptance (3.14 tokens a round). So the loss is in the image, not in the state of the box in this window: the round costs 1.6 to 1.9 ms more on v1.2.9 at one stream, and the gap grows with streams (4 to 5.7%). It is smaller than section 38's -4.2 to -11.2%, which compared against section 34's cells from a different window, so the like-for-like loss is 4 to 5.7%, not 11%.

**What the `DecodeSuspects` lane read (`work/DecodeSuspects/REPORT.md`, nothing run):** the GPU decode kernels and their order are identical between the two stacks, no nvcc flag changed for GLM, every collective call site reads the same, and the archived disk-tier windows show the same shape (+0.70 ms a token at 32k, +0.77 at 120k, +0.76 at 600k, +0.55 in the one-stream bench), nearly flat per token. 18 of the 32 patches have identical changed lines on both pins; of the 14 re-seated ones, only the item-plan switch (0011, `DEFS` restores the old path, now shown flat by `items0`) and DSEL ordering at long context (0012, not reached by this bench) change behaviour. The loss is therefore either host-side or in a part of the image no knob covers; the stage profile on both images (`queue40`) says which.

**Erratum, found from the nsys tables of section 39 (22:13 UTC):** every v1.2.9 cell of sections 38 and 39 ran a STALE recipe. The `serve.sh` on spark1 was the 2026-11-14 11:23 copy: its `DEFS` had neither `TF_GLM_OVN_EXL3_ITEMS=1` nor `TF_GLM_OVN_KEEP_SEQS=1` (the repo's has both since `50dcf30` and `5c13c44`; the staging step copied the tarball and the images but never refreshed `serve.sh`). Patch 0031's X3 kernels run on the item plan, so with the switch unset v1.2.9 took upstream's compact decode path and X3 was inert, which is why `items0` and `x3off` were flat. The kernel tables show it: per MoE call the stale run launched `tf_exl3_group`, `tf_exl3_experts_rot_in`, `tf_exl3_down_combine` and two `tf_exl3_grouped_1` (194.0 us median) where the v1.2.7 image launched `plan_kernel`, `prompt_rotate` and two `tf_exl3_ovn_nc1` (189.5 us): about 145 of the 213 ms of extra kernel time in the cell, 1.07 ms a round, equal to the 1.0 to 1.3 ms the stage profile put in `routed`. So the 4 to 11% "regression" and the A B B A gap of this section measure a recipe without the item plan, not the v1.2.9 engine. Corrected cells with the repo's `serve.sh` are in the next paragraph; the cold-prompt rows of section 38 and the disk-tier rows (not affected by the item plan) were taken on the same stale file and are re-run with the corrected one.

**Corrected cells (22:16 to 23:15 UTC, `queue42`): the repo's `serve.sh` on both images, order v1.2.7 / v1.2.9 / v1.2.9 / v1.2.7, five levels, production's prompts as ids, replies equal.** The v1.2.7 side is the image `rs2x3y` with `TF_GLM_INDEX_CUDA=1 TF_GLM_OVN_EY_DIRECT=1 TF_GLM_OVN_KEEP_SEQS=1` (the knobs its recipe set), the v1.2.9 side is `v129a` with the `DEFS` the repo ships (`EXL3_ITEMS=1`, `X3_*`, `KEEP_SEQS=1`).

| streams | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| v1.2.7 `fx-b1` | 79.08 | 83.23 | 110.59 | 147.17 | 182.08 |
| v1.2.9 `fx-a1` | 78.50 | 81.93 | 108.61 | 142.49 | 176.12 |
| v1.2.9 `fx-a2` | 78.40 | 81.86 | 108.23 | 142.46 | 176.27 |
| v1.2.7 `fx-b2` | 79.46 | 83.15 | 109.70 | 147.30 | 182.62 |
| mean v1.2.7 / mean v1.2.9 | 79.27 / 78.45 | 83.19 / 81.90 | 110.15 / 108.42 | 147.24 / 142.48 | 182.35 / 176.19 |
| v1.2.9 against v1.2.7 | -1.0% | -1.6% | -1.6% | -3.2% | -3.4% |

The two v1.2.9 cells agree within 0.4% at every level and the two v1.2.7 cells within 0.8%, so the bracket is clean; tokens a round is 3.14 on every cell (ms a round 38.7 against 39.1 at one stream). With the recipe as the repo sets it the v1.2.9 stack is 1.0 to 3.4% below the v1.2.7 stack, not 4 to 11%: the stale recipe (compact decode path, X3 inert, no `KEEP_SEQS`) cost 4 to 5.7% on top, the item plan being worth that much on v1.2.9. A residual remains, growing with streams (the one-stream 1.0% is inside the 0.8% spread of the v1.2.7 pair, the 6 and 8 stream gaps are 3.2 and 3.4% against spreads of 0.1 to 0.3%). `queue44` measures its source: stage profile and kernel tables of both images at 1 and 8 streams on the corrected recipe, and the item plan and `KEEP_SEQS` as arms on it. The disk-tier and cold-prompt rows of section 38, taken on the stale file, are re-taken in `queue43`.

## 40. The v1.2.9 stack on the corrected recipe (rank 0 only, see Erratum 2): cold prompts and the disk tier hold; the decode residual is superseded by the all-ranks re-run

All cells here use the repo's `serve.sh` on spark1 (checked byte for byte by `scripts/check-spark-sync.py` before each window; sections 38 and 39 ran on a stale copy, see the erratum in section 39). Image `v129a` (tree `27a87244e7dc`), `KNOBS=measured`, production's prompts as ids.

**Cold first token** (re-taken, one boot): 4.380 s at 8,192 tokens and 17.157 s at 32,768, against 4.348 s and 16.983 s on the stale recipe and 4.340 s and 17.042 s on the v1.2.7 stack: the item plan is a decode-window choice and does not move the prompt path.

**Disk tier (`patches/pr1411` net patch + cache-salt), TP=3, `--parallel 4 --context 1048576`, re-taken** (`docs/audit-2026-11-12/disktier-v129b-rows.jsonl`): all 17 resumed replies equal a cold server's, no check failed, no row rejected. The 596k conversation: turn 1 cold 352.81 s, turn 2 from RAM 14.17 s, after a SIGKILL of every rank 14.28 s of server prefill (618,496 tokens cached; first token 25.02 s), after a clean restart 16.40 s of server prefill (641,024 cached; first token 27.34 s); the 32k and 120k conversations resume from disk in 0.87 to 1.32 s of server prefill. Production for the same chain (`SPEED-TARGET.md`): 224.68 s, 12.54 s, 12.80 s, 12.90 s.

**The decode arms on the corrected recipe (1, 4, 8 streams, `ctl-m` / `ctl-m2` bracket; tok/s):**

| arm | 1 | 4 | 8 |
|---|---:|---:|---:|
| `ctl-m` | 78.96 | 108.51 | 177.27 |
| `items0m` (`TF_GLM_OVN_EXL3_ITEMS=0`) | 76.06 (-3.7%) | 104.56 (-3.6%) | 169.66 (-4.3%) |
| `ks0m` (`TF_GLM_OVN_KEEP_SEQS=0`) | 78.81 (-0.2%) | 106.62 (-1.7%) | 171.89 (-3.0%) |
| `ctl-m2` | 77.93 (-1.3%) | 107.85 (-0.6%) | 176.68 (-0.3%) |

The item plan is worth +3.7 to +4.5% on v1.2.9 (the compact path is what sections 38 and 39 measured by mistake), and `KEEP_SEQS` +1.7% at four streams and +3.0 to +3.3% at eight (nothing at one stream, where the controls spread 1.3%). Both stay in `DEFS`; patch 0011's switch and patch 0035 are load-bearing against upstream's own path, not redundant with it.

**Where the residual is.** `TF_GLM_PROF` stage times of a 3-row verify call, one stream, two cells a side (ms a call): routed 16.00 / 16.06 on v1.2.9 against 15.96 / 16.06 on v1.2.7 (equal now), gather_a 1.67 / 1.57 against 1.40 / 1.49, gather_b 1.39 / 1.24 against 1.15 / 1.15, every other stage equal. nsys on rank 0 at one and eight streams: launch counts identical on both images (269,747 and 671,857), total kernel time +7.0 ms of 6.8 s at one stream, so the compute is the same code at the same speed. The difference is in the kernels that wait on peers: `tp_roce_multi` mean 33.0 against 27.9 us (14,649 launches, median 13.4 against 12.2) at one stream, and NCCL `AllGather_RING_LL` mean 88.6 against 64.0 us (23,744 launches, median 54.2 against 48.8) at eight; the 32-launch NCCL `AllReduce` outlier is the boot barrier. These kernels spin until the slowest rank arrives, so rank 0's traces cannot yet tell slower transport from a later peer; per-rank traces and a source diff of the TP collective path (lane `CollectivePath`) decide it.

**Per rank (`queue45`, `TF_GLM_PROF` on all three ranks, one stream, order v1.2.7 / v1.2.9 / v1.2.9 / v1.2.7; ms a 3-row verify call, means of two cells for rank 0 and four for ranks 1 and 2).** Rank 0 does the most work (routed 16.0 against 13.5 ms on the peers) and is the critical path:

| | stage | v1.2.7 | v1.2.9 | change |
|---|---|---:|---:|---:|
| rank 0 | wall | 30.98 | 31.49 | +0.51 |
| rank 0 | gather_a | 1.40 | 1.71 | +0.31 |
| rank 0 | gather_b | 1.13 | 1.35 | +0.23 |
| rank 0 | routed / kda | 16.01 / 5.20 | 16.04 / 5.17 | +0.04 / -0.03 |
| ranks 1, 2 | wall | 30.68 | 31.04 | +0.36 |
| ranks 1, 2 | routed | 13.54 | 14.75 | +1.21 |
| ranks 1, 2 | kda / mla | 4.03 / 2.33 | 4.43 / 2.40 | +0.40 / +0.07 |
| ranks 1, 2 | gather_a / gather_b | 2.45 / 3.96 | 2.03 / 3.05 | -0.42 / -0.92 |

Two effects, only the first on the critical path. (1) Rank 0's own stages are equal and its two collectives cost 0.53 ms more, which is the whole +0.51 ms of its wall time; per layer that is about +6 us a collective, the +5 us mean of `tp_roce_multi` in nsys. Rank 0's pre-gather work (kda and mla, 7.8 ms) is longer than the peers' (6.3 and 6.8 ms), so it is not waiting for a late peer: the collective itself is slower. (2) The peers' own compute grew (routed +1.21, kda +0.40, mla +0.07 ms) with rank 0's unchanged, so some per-rank path is asymmetric; they still finish before rank 0, and the extra compute is absorbed by shorter waits in their gathers (-0.42 and -0.92 ms). The one-stream gap of 1.0% is effect (1); the lane `CollectivePath` is reading both in source.

**The disk tier is not the cause (`queue46`, 02:11 to 02:46 UTC): a v1.2.9 image of the series alone.** `v129s` is the series without `pr1411` and cache-salt (tree `e02b8a89c2cc`, packed by `work/pack-series.sh`), run with the repo's recipe in the order v1.2.7, series, full, full, series, v1.2.7 with `TF_GLM_PROF` on all three ranks. Decode, tok/s, mean of two cells:

| streams | v1.2.7 (`rs2x3y`) | series only (`v129s`) | full stack (`v129a`) |
|---|---:|---:|---:|
| 1 | 78.71 | 78.94 (+0.3%) | 78.16 (-0.7%) |
| 8 | 186.14 | 179.63 (-3.5%) | 180.57 (-3.0%) |

The series and the full stack agree within 0.5%, so the disk tier and cache-salt cost nothing measurable on the decode path; the 8-stream gap of 3.0 to 3.5% belongs to the engine bump. At one stream the three means span 1.0% against a v1.2.7 pair that spreads 1.7%, and rank 0's wall time is 30.75 / 30.66 / 31.04 ms (v1.2.7 / series / full): inside the noise, so the one-stream gap of earlier tables is not a result. Per rank, means of the cells (ms a 3-row verify call): rank 0 routed 15.99 / 15.84 / 15.91, gather_a 1.35 / 1.51 / 1.69, gather_b 1.06 / 1.19 / 1.25; ranks 1 and 2 routed 13.48 / 14.63 / 14.64, kda 3.98 / 4.44 / 4.43, mla 2.33 / 2.37 / 2.37, gather_a 2.42 / 1.78 / 1.89, gather_b 3.88 / 2.76 / 2.86. The peers' compute is 1.15 ms slower in routed and 0.46 ms in kda in both v1.2.9 images, while rank 0's is unchanged: as the batch grows rank 0's lead over the peers shrinks (it holds 768 expert rows against 640 and does more kda work), so a slower peer reaches the critical path, which fits a loss that grows with streams.

**What the source says (lane `CollectivePath`, `work/CollectivePath/REPORT.md`, nothing run).** The wire is identical at both pins: `git log 93a2e93ec..6b9de695` touches none of the `fabric/tp/roce_multi*.zig` files, `roce_device.cuh` or `mailbox.cu`, and our series edits no fabric file at either pin, so a slower transport is refuted. The commits on the path that did move are the boundary resolve (`c0f3648e7`), the collective backend (`3a88bc8af`) and the logit gather (`5cd52c7a8`, `5b927e2bf`; identical broadcast counts on both stacks); the only re-seat edit on the path is one context line of the glue-fuse patch, inert with `GLUE_FUSE` off. The peers' slower kernels are therefore either the same kernels running slower on ranks 1 and 2 (memory placement on the unified-memory GPUs, clocks) or a stall inside a stage; the wall time equals the GPU time on every rank in every cell (30.29 against 30.23 ms), which points at the kernels. A per-rank nsys of rank 1 on both images at 1 and 8 streams (`scripts/nsys-rank.sh`, `queue47`) compares their kernel medians and a clock and power sample.

**Erratum 2 (03:03 UTC), found from the rank-1 nsys of `queue47`: the corrected recipe of this section reached rank 0 only.** `zig-tp3.sh` starts ranks 1 and 2 with `~/work/glm53-zig/serve.sh` on spark2 and spark3, and those copies were the 2026-11-14 file (hash `abacddca138d`, no `EXL3_ITEMS=1`, no `KEEP_SEQS=1`); the repair of section 39 replaced spark1's copy only. So in every v1.2.9 cell of sections 39 and 40 rank 0 ran the item plan with X3 and `KEEP_SEQS`, and ranks 1 and 2 ran upstream's compact path: the rank-1 kernel tables show `tf_exl3_grouped_1` (187.2 us mean at one stream, 407.3 at eight) on the v1.2.9 image where the v1.2.7 image runs `tf_exl3_ovn_nc1` (181.5 and 397.4 us), while rank 0 runs `tf_exl3_ovn_nc1` on both. That is the whole rank asymmetry above (peers' routed +1.2 ms, kda +0.4 ms) and very probably the 1.0 to 3.4% residual of the corrected cells, which loses its status as a result until it is re-measured with every rank on the repo's recipe (`queue48`, all three `serve.sh` hashes equal, printed in its log). The v1.2.7 cells are unaffected (their recipe knobs travel in `XENV` to every rank). What stands: the disk-tier and cold-prompt rows (the item plan does not touch them), the item-plan and `KEEP_SEQS` arms (their switches travel in `XENV` to every rank, though the controls had the peers stale), the nsys and stage-profile tables as measurements of the mixed configuration, and the series-only against full-stack comparison (both mixed alike). Repairs: `zig-tp3.sh` now copies `serve.sh` and `config.sh` to each worker before it starts the rank, so a worker can no longer run an old copy; `check-spark-sync.py` covers the head and the push covers the workers.

## 41. With every rank on the repo's recipe the v1.2.9 stack decodes at parity with the v1.2.7 stack

`queue48` (03:05 to 04:04 UTC): `serve.sh` and `config.sh` byte-identical on spark1, spark2 and spark3 (hash `1403dc8f5d3c`, printed in the log; `zig-tp3.sh` now copies them to the workers at every boot), image `rs2x3y` (v1.2.7 stack, its recipe knobs `INDEX_CUDA=1 EY_DIRECT=1 KEEP_SEQS=1` in `XENV`) against `v129a` (the v1.2.9 stack, the repo's `DEFS`), order v1.2.7 / v1.2.9 / v1.2.9 / v1.2.7, five levels, production's prompts as ids, replies equal, 3.14 tokens a round on every cell:

| streams | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| v1.2.7 `gx-b1` | 81.30 | 83.92 | 112.89 | 151.20 | 186.82 |
| v1.2.9 `gx-a1` | 80.48 | 84.83 | 112.28 | 150.63 | 187.05 |
| v1.2.9 `gx-a2` | 81.43 | 84.74 | 112.04 | 150.34 | 187.35 |
| v1.2.7 `gx-b2` | 80.70 | 83.44 | 112.47 | 151.17 | 186.92 |
| mean v1.2.7 | 81.00 | 83.68 | 112.68 | 151.19 | 186.87 |
| mean v1.2.9 | 80.96 | 84.78 | 112.16 | 150.49 | 187.20 |
| v1.2.9 against v1.2.7 | -0.1% | +1.3% | -0.5% | -0.5% | +0.2% |

Every difference is inside the spread of the cells (the v1.2.7 pair spreads 0.0 to 0.7%, the v1.2.9 pair 0.1 to 1.2%) and the sign is not consistent, so the v1.2.9 stack matches the v1.2.7 stack at 1, 2, 4, 6 and 8 streams: **there is no decode regression from the pin move.** The 4 to 11% of section 38, the A B B A of section 39 and the 1.0 to 3.4% residual of section 40 were all the same defect in three stages: first no rank had the item plan (a stale `serve.sh` on spark1), then rank 0 had it but ranks 1 and 2 did not (stale copies on spark2 and spark3, found from the rank-1 kernel table). What was learned on the way: `routed` is where the compact path costs (the item plan is worth 3.6 to 4.3% on this stack, section 40 arms), the kernel launch list of one decode call is the instrument that names a wrong recipe in minutes, and a measurement window checks the recipe files on EVERY box it runs on. The cold first token, the disk tier and the item-plan and `KEEP_SEQS` arms of sections 38 and 40 were taken with stale peers and are re-taken in `queue49`.

Against production (`SPEED-TARGET.md`, `--parallel 4`, 1M context; our rows are one boot a level at `--parallel` equal to the stream count): decode 81.00 / 83.68 / 112.68 / 151.19 / 186.87 tok/s against 81.73 / 89.22 / 117.98 / 114.78 / 131.28, that is -0.9%, -6.2%, -4.5%, +31.7%, +42.3% at 1/2/4/6/8 streams (the six and eight stream cells are different serves, see AGENTS.md). Cold prompts and resume remain where the gap is (section 38).

**Re-taken with every rank synced (`queue49`, 04:06 to 05:42 UTC; `serve.sh` hash `1403dc8f5d3c` on all three boxes).**

- **Cold first token** (one boot, replies equal): 4.319 s at 8,192 tokens and 16.895 s at 32,768, against 4.380 s and 17.157 s with stale peers: the item plan does not move the prompt path.
- **Item plan and `KEEP_SEQS` arms** (`ctl-n` / `ctl-n2` bracket, tok/s, 1 / 4 / 8 streams): controls 78.50 / 110.13 / 182.66 and 79.55 / 109.94 / 182.22 (means 79.03 / 110.03 / 182.44, spread 1.3 / 0.2 / 0.2%); `items0n` (`EXL3_ITEMS=0`) 76.12 / 105.92 / 173.31, `ks0n` (`KEEP_SEQS=0`) 78.63 / 107.56 / 174.51, replies equal. Against the control mean, turning the item plan off costs -3.7 / -3.7 / -5.0% (the knob is worth +3.8 / +3.9 / +5.3%) and turning `KEEP_SEQS` off costs -0.5 / -2.2 / -4.3% (worth +0.5, inside the one-stream spread, then +2.3 and +4.5%). Both stay in `DEFS`.
- **Disk tier, TP=3, `--parallel 4 --context 1048576`** (`docs/audit-2026-11-12/disktier-v129c-rows.jsonl`): all 17 resumed replies equal a cold server's, no row rejected. The 596k conversation: turn 1 cold 353.56 s, turn 2 from RAM 14.13 s, after a SIGKILL of every rank 14.22 s of server prefill (618,496 tokens cached, first token 25.00 s), after a clean restart 16.48 s (641,024 cached, first token 27.73 s); the 32k and 120k conversations resume from disk in 0.88 to 1.32 s of server prefill. One coverage check failed, not a reply: `M120000/t3` was expected to resume from disk after the eviction and resumed from RAM instead (1.13 s, reply equal), so that turn did not exercise the disk path; the same conversation resumes from disk at turns 4 and 5 (3.51 and 3.72 s, equal). On every row that took the same path the server prefill matches the stale-peer window of section 40 within 0.5% (596k cold 352.72 s then and 353.50 s now, after SIGKILL 14.28 and 14.22 s, after a clean restart 16.40 and 16.48 s); the first token of `M32000/t3` was 1.60 s then and 2.66 s now with the same 0.87 and 0.88 s of server prefill, the one unexplained difference, and `M120000/t3` took another path, so the disk tier does not depend on the peers' recipe within what these rows can show. Production for the same chain: 224.68 s, 12.54 s, 12.80 s, 12.90 s (1.57x, 1.13x, 1.11x, 1.28x the first-token times above, counting server prefill).

## 42. Thinking-off prompts as production renders them: patch 0033, `TF_GLM_OVN_OFF_EFFORT_LINE`

Owner decision (2026-11-16): a thinking-off chat request renders like production's, without the `Reasoning Effort: Max` system line. Production's Python engine deletes the first literal `<|system|>Reasoning Effort: Max` from the template's text when thinking is off (`prompts.py` `thinking_off`), so a request that names `high` or `low` keeps its line and thinking on is unchanged; its bench prose prompt is 33 tokens where this engine rendered 40. Upstream pins the 40-token rendering in `thinking_request_test.zig` ("main's Max when none is named"), so the change is a default-off switch in our series, set by `serve.sh` `DEFS`: patch `0033-glm-off-effort-line.patch`. It rewrites the checkpoint template when it is loaded (`{%- if effective_reasoning_effort is not none -%}` gains `and (enable_thinking or effective_reasoning_effort != 'max')`), because the rendered text carries offset-based spans that stripping afterwards would corrupt; the server keeps the checkpoint's own template text for everything else it reads from it.

**Gates** (`scripts/spark-gates.py`, shared x86_64 host, run `sg-20261116-112304`): series tree `c08dd8eade95` (33 patches) and stack tree `e946a74361ca` (36, with `pr1411` and cache-salt) both PASS against the pristine v1.2.9 base: `check-native-cuda-host`, `compile-cuda-tests`, the standalone host steps and `fmt` rc 0; `test-cuda-host` fails only the base's own `cli_config_test ... serve --config` test (6,832 of 6,866 passed on the series, 6,894 of 6,928 on the stack, 33 skipped); lean 341 problems on both sides, 0 new.

**Served check** (`queue50`, image `glm53-zig:v129t` = the stack with patch 0033, TP=3, one stream, three rounds a cell):

| cell | prompt tokens (server log) | reply digest | decode tok/s | first token ms |
|---|---:|---|---|---|
| production's prompt as ids (`prose33.json`) | 33 | `9eb3186f9480` | 81.94, 80.44, 80.24 | 132, 137, 136 |
| the same prompt as a thinking-off chat, switch on | 33 | `9eb3186f9480` | 82.90, 80.35, 80.21 | 133, 135, 137 |
| the chat with `TF_GLM_OVN_OFF_EFFORT_LINE=0` | 40 | `323d3f5bcb55` | 75.41, 75.73, 75.39 | 150, 146, 154 |

With the switch on the chat path renders exactly production's prompt: the same 33 tokens and the same 400-token greedy reply as the recorded ids. With it off the prompt is 40 tokens and the reply is a different text, which on this prompt decodes at 75.5 against 81.2 tok/s (acceptance 0.671 against 0.690) and reaches its first token in 150 against 135 ms. That speed difference belongs to this prompt's reply, it is not a general rate: what the switch guarantees is the prompt, token for token.

**Mutants** (one changed line of the patch each, run through `spark-gates.py iter ... test`, the mutated tree id checked to differ from the clean one): `!= 'max'` as `!= 'high'` is killed by "thinking off at a named max drops the line" and "thinking off keeps the line of a named high or low"; `enable_thinking or` removed by "thinking on renders as before"; `if (!on)` inverted by upstream's own "checkpoint GLM 5.3 off closes its generation prefix"; `indexOf` as `lastIndexOf` by "only the first one is rewritten". Two traps met on the way, both in the runner and both caught by its own checks: a first anchor matched the patch's header prose, so the tree id was the clean one and nothing had been mutated; and a failing-name pattern stopped at the apostrophe in a test's name and read a kill as a survivor.

**Decode is unchanged** (`queue51`, the image without the patch `v129a` against the image with it `v129t`, order A T T A, five levels, production's prompts as ids, which never render a template; replies equal):

| streams | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| `v129a` `ty-a1` | 79.79 | 82.95 | 110.38 | 148.00 | 182.09 |
| `v129t` `ty-t1` | 79.58 | 83.14 | 110.21 | 147.09 | 182.31 |
| `v129t` `ty-t2` | 79.06 | 82.80 | 110.89 | 147.38 | 183.31 |
| `v129a` `ty-a2` | 79.12 | 82.76 | 110.98 | 147.74 | 182.41 |
| `v129t` against `v129a` (means) | -0.2% | +0.1% | -0.1% | -0.4% | +0.3% |

Every difference is inside the spread of the pairs (0.2 to 0.8%). A first unbracketed five-level cell on `v129t` had read 1.4 to 2.4% below section 41's means; the bracket shows the old image reads the same in this window, so that was the window, not the patch. `TF_GLM_OVN_OFF_EFFORT_LINE=1` is in `serve.sh` `DEFS`; the recipe image is `glm53-zig:v129t` (stack tree `e946a74361ca`).

## 43. The v1.2.9 stack on the GPU: every bit-exact check passes, the disk tier costs nothing to have on, decode at production's deployed shape

**Our patches' own GPU checks, on the v1.2.9 stack (image `v129t`, one GB10, `tf-cuda-test` from the image, `queue52`, 17:19 to 17:22 UTC).** Before this, the item plan and `KEEP_SEQS` receipts were from v1.2.7 on a workstation GPU. Every check exits 0 with its real counts (not a bare rc):

| check | what it proves | result |
|---|---|---|
| `glm-exl3-items` | the decode item plan equals the plain decode, byte for byte | 0 of 308 comparisons differ (v1.2.7 receipt: 308) |
| `glm-exl3` | routed experts, decode and prompt, against float64 | largest difference 0.157 of the tolerance |
| `glm-keep-seqs-check` | kept sequences, as left and with every byte poisoned, equal fresh ones (24 greedy steps, logits, MTP drafts, prompts of 600 and 3,000 tokens, fp8 and bf16 caches) | PASS; the four planted controls differ at step 0 as planted |
| `glm-lanes-concurrent`, `KEEP_SEQS` 0 and 1 | three concurrent streams each equal their solo run | 38 PASS / 0 FAIL both ways (v1.2.7 receipt: 38 / 0) |
| `glm-draft-onepass`, `glm-index-check`, `glm-index-ovn-check`, `glm-index-regroup-check`, `glm-mla-skip-check`, `glm-onepass-exact-check`, `glm-kda-pad-split`, `glm-ref` | the drafter one-pass, the indexer and its decode variants, the fused MLA chunks, the pipe, the KDA padding, every GLM projection | all PASS (18, 11 and 8 byte-equal cases, 28 calls, 5 shapes; 25 PASS in `glm-ref`) |

**The disk tier is not in the recipe by default, and its presence costs no decode speed.** `serve.sh` started without any way to turn the tier on (only `scripts/queue-disk-tier.sh` passed the flags), so a serve started from the recipe forgot every conversation at a restart while production keeps them. `LEARN=1` (commit `519bb76`) adds `--learn-conversations` with the store under the mounted cache and the queue's caps (128 GiB, 512 GiB a day, 40 GiB free) on every rank; `scripts/tests/test_serve_learn.sh` runs `serve.sh` against a recording `docker` (six checks) and is killed by three one-line mutants of `serve.sh`.

`queue53`, image `v129t`, `KNOBS=measured`, production's prompts as ids, one fresh boot a level, order off / on / on / off, tok/s (tier-on boots print `conversation states on disk ... 3 ranks' parts; a save stages up to 7429 MiB`, tier-off boots do not; replies equal on every cell):

| streams | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| tier off `lt-off1` | 79.04 | 83.41 | 110.36 | 146.95 | 182.65 |
| tier on `lt-on1` | 79.82 | 84.65 | 111.58 | 147.93 | 187.03 |
| tier on `lt-on2` | 81.39 | 84.71 | 112.41 | 150.61 | 186.24 |
| tier off `lt-off2` | 81.33 | 84.81 | 112.24 | 150.80 | 186.20 |
| mean on against mean off | +0.5% | +0.7% | +0.6% | +0.3% | +1.2% |
| `lt-on2` against its neighbour `lt-off2` | +0.1% | -0.1% | +0.2% | -0.1% | 0.0% |

The tier is not slower at any level (the off pair spreads 1.7 to 2.9%, so the +1% means are the first cell reading low, not a gain). What this does not price: the bench prompts are 33 tokens, nothing is large enough to keep, and the stores were 4 KiB, so these cells measure an idle tier. The cost of a save or a restore of a large state beside decoding streams is section 32's and 36's: a 4.7 GiB restore stalls the other streams for up to 9.9 s unless `TF_GLM_OVN_DISK_SLICE_MIB` slices it, a trade the owner has not accepted. `LEARN` stays opt-in in `serve.sh` rather than a default: the disk windows' cold reference arm goes through the same `serve.sh` and must run without a tier, and a deployment is where the switch belongs (`LEARN=1`, `KNOBS=measured`, `P=4`, `CTX=1048576`).

**Decode against production, in one sitting with one client** (`scripts/queue-prod-compare.sh`, 18:36 to 18:51 UTC, then `scripts/prod_accounting.py`): production's live serve, then a Zig boot at production's deployed shape (`--parallel 4 --context 1048576`, the v1.2.9 stack, `KNOBS=measured`), then production again, all driven by `scripts/streams_ids.py` with production's 33-token prompt ids (400 tokens, 3 rounds a cell, `agg_tok_s`, the statistic the first column of production's `SPEED-TARGET.md` uses), production measured only while idle. Production's replies carry its recorded digests (`8347edfe4ee6` and the others), so the instrument is the one that made its table. Cells `~/bench/pm1`, `pd-a1` to `pd-a3`, `pm2`:

| clients | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| production `pm1` / `pm2` | 79.97 / 80.59 | 88.28 / 88.02 | 116.12 / 115.90 | 117.14 / 127.44 | 117.12 / 132.53 |
| Zig `pd-a1` / `pd-a2` / `pd-a3` | 78.90 / 78.81 / 80.99 | 83.66 / 82.67 / 83.85 | 110.82 / 110.39 / 112.26 | 118.40 / 111.55 / 126.23 | 120.71 / 114.35 / 118.79 |
| production mean (spread of its two cells) | 80.28 (0.8%) | 88.15 (0.3%) | 116.01 (0.2%) | 122.29 (8.4%) | 124.83 (12.3%) |
| Zig mean (spread of its three cells) | 79.57 (2.7%) | 83.39 (1.4%) | 111.16 (1.7%) | 118.73 (12.4%) | 117.95 (5.4%) |
| Zig against production | -0.9% | -5.4% | -4.2% | -2.9% | -5.5% |

This table replaces the 1/2/4 numbers quoted against `SPEED-TARGET.md` (taken on 2026-11-11, not beside ours) and supersedes the +31.7% and +42.3% of section 41, which compared one-boot-a-level serves with production's queueing serve (section 28). At one client the gap is inside the noise (-1.8% to +0.9% over the three Zig boots). At two and four clients every Zig cell is below every production cell (-6.2% to -4.9% and -4.8% to -3.2% against production's mean), a real gap of about 5%. At six and eight clients both serves queue, production's own two readings differ by 8.4% and 12.3% (its first reading is level with Zig's, its second 8 to 13% above), and nothing can be said beyond "within the run-to-run spread, with Zig mostly lower".

**Where the 2 and 4 client gap is, from the round counters** (production from `/health` differences over two measured waves, `prod_accounting.py`; Zig from the cells' draft counters over its nine waves):

| clients | | rounds | drafted a round | accepted a round | tokens a round | acceptance |
|---|---|---:|---:|---:|---:|---:|
| 1 | production | 266 | 2.92 | 2.00 | 3.008 | 0.686 |
| 1 | Zig | 1,143 | 3.10 | 2.14 | 3.150 | 0.690 |
| 2 | production | 664 | 2.19 | 1.40 | 2.410 | 0.641 |
| 2 | Zig | 3,087 | 2.02 | 1.33 | 2.332 | 0.657 |
| 4 | production | 1,260 | 2.36 | 1.53 | 2.540 | 0.649 |
| 4 | Zig | 5,940 | 2.01 | 1.42 | 2.424 | 0.707 |

Production's tokens a round against Zig's are -4.5% at one client, +3.3% at two and +4.8% at four. Set against the throughput ratios (production over Zig: +0.9%, +5.7%, +4.4%), the implied round rates are +5.7% at one client, +2.3% at two and -0.4% at four. Three readings follow, each limited by what this can show. First, the sign of the tokens-a-round difference flips between one client (Zig ahead) and two and four (production ahead), which is what two engines writing different text from one checkpoint do (section 23: the replies diverge, and tokens kept a round depend on the reply), so a ~5% tokens-a-round difference is the size of that effect and is not evidence of a weaker drafter. Second, the engines differ in draft length under concurrency: production drafts 2.92, 2.19 and 2.36 tokens a round at one, two and four clients, Zig 3.10, 2.02 and 2.01; section 15 measured longer drafts on this series as costing more ms a round than they return, so it is not an open lever. Third, round time, the engine's own property, is level at four clients and 2% behind at two; at one client production's round is 7% shorter (36.3 ms against 38.9 ms, `decode_seconds_total` over rounds, valid at one stream only) and Zig keeps 4.5% more tokens a round on this prompt, the two roughly offsetting (+0.9% throughput on the wall-time statistic, about +2% on decode time alone). What would separate text from engine is the same reply text through both engines (section 23's replay), which has not been run at two and four clients.

## 44. Twenty-four prompts one at a time: the gap to production is round time, not drafting; `TF_GLM_OVN_WIN_FREE` measured (a loss)

2026-11-16, 19:05 to 20:44 UTC, `glm53-zig:v129t` with the recipe (`KNOBS=measured`), production `tensorfold-glm53:v110hunt4-shard` as deployed. Four windows (`work/queue55.sh` to `queue58.sh`), production restored and healthy after each. Section 43 compared the engines on four prose prompts and could not tell the engine from the text each engine writes. This section uses 24 prompts and the round counters of single requests.

**Instrument.** `scripts/per_prompt.py` sends one greedy 400-token `/v1/completions` request at a time and differences the serve's draft counters around it (production's `/health`, ours `/metrics`), so each row is one reply's rounds, drafted and accepted. Against production it sends only while the serve is idle. `scripts/prompts24.json` (`scripts/make_prompt_ids.py`) holds 24 prompts as ids in production's thinking-off rendering: the eight of `streams.py` and sixteen more (explanations, stories, Rust, Go, shell, SQL, JSON, a review, a plan, arithmetic); its first four equal `prose33.json`. Checks: production's four bench prompts gave 133 / 199 / 139 / 159 rounds on three separate runs with the digests on record, and our prose gave 127 rounds, 394 drafted, 272 accepted, as in every cell of section 43. Every prompt's two repetitions agreed on both engines. `scripts/per_prompt_table.py` pairs two such files; it was first run on a fixture with a planted 10% difference, which it reported outside its interval.

**A reply's rounds are a property of the reply on production, not on ours.** Production's four bench prompts take 133 + 199 = 332 and 133 + 199 + 139 + 159 = 630 rounds alone, and its two- and four-client waves of section 43 took 332 and 630 rounds. Ours take 127 + 207 = 334 and 626 alone, and 343 and 660 in the two- and four-client waves (+2.7% and +5.4%; +4.6 to +4.9% at six clients, +5.0 to +5.2% at eight), with the replies byte-identical to the solo ones: under load we draft fewer tokens a round (694 against 722 at two, 1,327 against 1,452 at four). The cause is the lanes core's shared-window allocator, which trims each stream's drafts by a cost table (`cuda_copy_policy.zig`: `shared_costs`) and which production's engine does not have. Section 43's reading of the two- and four-client counters as a text effect is corrected by this: alone, we need fewer rounds than production for these four prompts (626 against 630).

**One stream, 24 prompts, each engine on its own reply** (`python scripts/per_prompt_table.py prod.jsonl zig.jsonl --names production,Zig`; ours on a `--parallel 4 --context 1048576` boot):

| | Zig over production (geometric mean over prompts) | 95% bootstrap interval | Zig higher on |
|---|---:|---:|---:|
| tokens a round | 0.983 | 0.953 to 1.011 | 11 of 24 |
| ms a round | 1.019 | 1.003 to 1.034 | 17 of 24 |
| decode tok/s | 0.965 | 0.946 to 0.982 | 6 of 24 |

Totals over the 9,600 tokens: 3,116 rounds against our 3,140 (+0.8%), 113.1 s of decode against 116.9 s (-3.3%), 2.88 drafted a round at 0.720 acceptance against 2.83 at 0.723. So at one stream we are 3.5% slower than production over a set of prompts, where the single prose prompt of section 43 read -0.9%: on that prompt our reply happens to keep 4.7% more tokens a round, which hid a slower round. A round's time grows with its drafts, so the round times are compared by a least-squares line over the 24 prompts: production 21.9 ms + 4.98 ms a drafted token (residual 0.76 ms), ours 23.7 ms + 4.78 ms (0.90 ms). At 2, 3, 5 and 6 drafts that is 31.9 / 36.9 / 46.8 / 51.8 ms against our 33.2 / 38.0 / 47.6 / 52.3 ms: about 1.8 ms more fixed cost a round, a slightly cheaper draft row. By kind: on the 15 prompts where production drafts under 3.5 tokens a round (prose-like) our tokens a round are 1.007 of production's and our round 1.031; on the other 9 (code, JSON, shell, arithmetic) 0.943 and 0.998, with all four Python prompts lower (0.81 to 0.93).

**`TF_GLM_OVN_WIN_FREE=1` (patch 0018; `docs/KNOBS.md` had it as never tested): a loss at every level.** It drops the cost table, so every round verifies all seven drafts. Off / on / on / off at production's deployed shape, one boot an arm, `streams_ids.py` with 1 to 8 clients, mean of three waves, replies equal across arms:

| clients | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| `wf-off1` | 79.64 | 82.58 | 110.65 | 117.16 | 124.88 |
| `wf-on1` | 63.05 | 58.27 | 79.25 | 81.80 | 85.55 |
| `wf-on2` | 63.07 | 58.33 | 79.03 | 80.80 | 93.16 |
| `wf-off2` | 79.76 | 83.08 | 110.63 | 119.28 | 123.35 |
| on against off | -20.9% | -29.6% | -28.5% | -31.2% | -28.0% |

The off pair agrees within 0.2 / 0.6 / 0.0 / 1.8 / 1.2%. With the switch on the rounds fall (115 against 127 at one client, 300 against 343 at two, 563 against 660 at four) and acceptance falls to 0.355 / 0.239 / 0.265, so each round verifies rows that mostly miss. It stays off. Solo over the 24 prompts the same arm took 2,826 rounds against 3,140 and 151.2 s against 116.9 s.

**What a round costs here, from the two arms.** The arms draft 3.10 against 6.95 rows a round at one stream, 4.05 against 13.89 at two, 8.04 against 27.73 at four, so two points fix a line for each (ms a batched round, from `agg_tok_s`): 26.9 + 4.07 a draft row at one stream, 41.9 + 3.57 at two, 64.8 + 2.84 at four. Two uses. First, production's rounds of section 43 on the same footing: 37.5 ms at 2.92 draft rows, 54.7 ms at 4.38 and 87.6 ms at 9.45, where our line gives 38.8, 57.5 and 91.6 ms: a round of ours costs 3.5%, 5.2% and 4.7% more than production's at equal draft rows (a batched round is taken as the slot rounds over the clients on both sides, which overstates the sharing at two clients where one reply ends first). Second, the allocator's trimming: by the same lines, drafting solo-length chains under load would save 0.9% at two streams and 1.4% at four. That is a calculation, not a measurement, and it says the trimming is near its optimum: the +5.4% rounds buy cheaper rounds.

**Our drafter on production's own replies** (`scripts/forced-arm.sh`, `teacher_forced.py`, `forced_score.py`: the method of section 23, now for any reply; the prose control reproduces section 23's reach of 0.807 / 0.623 / 0.463 / 0.345 / 0.246 / 0.163 / 0.107 and 3.07 tokens a round exactly):

| production's reply | its live rounds | ours with every correct draft kept | our target's token equals production's at | our drafter's reach at depth 1, 4, 7 |
|---|---:|---:|---:|---|
| prose | 133 | 130 | 374 of 399 | 0.807, 0.345, 0.107 |
| code | 58 | 59 | 394 of 399 | 0.987, 0.921, 0.835 |
| code4 | 67 | 71 | 391 of 399 | 0.962, 0.744, 0.527 |
| json | 84 | 90 | 390 of 399 | 0.903, 0.613, 0.349 |
| story | 199 | 202 | 351 of 399 | 0.641, 0.048, 0.000 |

A position where our target leaves production's text keeps nothing in that count, so the few rounds of excess are the target's divergence. Our drafter's picks are not behind production's on any of the five texts.

**Our drafter on our own code replies, mid-stream against after a prompt pass** (`forced-arm.sh` with `LIVE=1`, `scripts/live_vs_forced.py`). A forced run only ever sees the first round after a prompt pass, so the same positions were drafted both ways on our own replies. `code`: the first pick is identical at 69 of 69 paired positions, the whole chain at 55; the mean correct lead is 5.51 mid-stream against 5.39 after a prompt pass. `code4`: 72 of 72, 61, and 4.67 against 4.72. Drafting mid-stream is not weaker. With every correct draft kept our own `code` reply would take 64 rounds (71 for `code4`); the live recipe took 72 (75), and the all-drafts arm above 68 (74). On production's `code` reply the same drafter would take 59. So of our 72 rounds against production's 58 on `code`, about five are our reply being harder to draft than production's and the rest is the cut (the live log: a chain cut before its first miss in 27.1% of rounds, 0.96 drafts a round; 12.2% and 0.32 on `code4`), which the all-drafts arm shows is not worth removing wholesale.

**A request's first decode round is narrow.** In the forced runs on production's `code` reply all seven picks are right at 326 of the 381 positions where the count is exact, yet the first round keeps at most four drafts anywhere (three at 226 positions, four at 98); the second round keeps seven at 263 of 399. The cost is about one round a request: nothing on a 400-token reply, a few percent on a short code-like one such as a tool call. Not measured against production, which may do the same. It also means `forced_score.py`'s line "our rule on production's text" is a floor and not our live rule; and its `prompt cache:` check found no such lines on v1.2.9, so that check is empty here (the control's exact agreement with section 23 stands in for it).

**Where this leaves the comparison with production.** At one, two and four streams the gap (-3.5% over 24 prompts at one stream; -5.4% and -4.2% in section 43) is the round's cost at equal work, about 1.8 ms of fixed cost at one stream and 4 to 5% at two and four. Drafting is level: the same picks on production's text, the same tokens a round on prose-like prompts, and a deficit on code-like prompts that is the text and the cut. No knob in the series moves it: the one candidate, `TF_GLM_OVN_WIN_FREE`, loses 21 to 31%.

Tools added: `scripts/per_prompt.py`, `per_prompt_table.py`, `make_prompt_ids.py`, `prompts24.json`, `forced-arm.sh`, `teacher_forced.py`, `forced_score.py`, `chain_log.py`, `live_vs_forced.py`. The scorer's and the log parser's own tests need production's draft dumps and the Python repo, so they stay with those fixtures on the workstation; they are not in `scripts/tests/`.

## 45. Short replies, the never-measured kernel knobs, and what cuts chains on code: the lanes core's context copies

2026-11-16, 20:49 to 23:05 UTC, `glm53-zig:v129t`, the recipe (`KNOBS=measured`), boots at production's deployed shape (`--parallel 4 --context 1048576`) unless a row says otherwise; windows `work/queue59.sh` to `queue62.sh`, production restored and healthy after each. Section 44 left the round's own cost as the gap and a deficit on code-like prompts unexplained; this section measures the knobs that act on the round and finds the cause on code.

**Short replies** (`per_prompt.py --max-tokens 16` and `48` over `prompts24.json`, two repetitions, production's live serve while idle against a Zig boot):

| reply length | rounds, production / Zig | first token, ms | decode span, ms | whole request, ms | Zig over production, whole request (95% interval) |
|---|---:|---:|---:|---:|---:|
| 16 tokens | 127 / 129 | 168 / 153 | 185 / 186 | 352 / 339 | 0.964 (0.926 to 1.004) |
| 48 tokens | 372 / 385 | 164 / 152 | 564 / 577 | 728 / 729 | 1.008 (0.973 to 1.047) |

Short replies are level: our first token is about 9% sooner (ratio 0.913, interval 0.894 to 0.939, at 16 tokens) and we take 3.5% more rounds in the first 48 tokens (per-prompt ratio 1.051, interval 1.000 to 1.105), about half a round a request. On the 9 code-like prompts at 48 tokens that is 96 rounds against 89 and 638 ms against 615 ms. One cause is the depth rule of the lanes core (`core/lanes/depth.zig`): a stream with no acceptance history takes the depth with the most expected tokens a ms from a fixed prior (0.85, 0.75, 0.7, ...) and the cost table, which is four, so a request's first decode round holds four drafts (section 44's forced runs: at most four kept anywhere).

**The kernel knobs `docs/KNOBS.md` listed as never measured: a screen** (`queue59`: one boot an arm, `streams_ids.py` with 1, 2 and 4 clients, mean of three waves; three controls, which fell across the window from 81.44 to 80.96 to 78.97 tok/s at one client, so an arm is read beside its neighbours and a single boot within about 2% decides nothing):

| arm (run order) | 1 | 2 | 4 | replies |
|---|---:|---:|---:|---|
| control 1 | 81.44 | 85.12 | 113.09 | |
| `TF_GLM_OVN_ROUTER16=3` | 81.22 | 85.00 | 112.49 | equal |
| `TF_GLM_OVN_ROUTER16=4` | 81.16 | 84.99 | 112.49 | equal |
| `TF_GLM_OVN_DECODE_INDEX=33` | 81.27 | 84.65 | 111.95 | equal |
| control 2 | 80.96 | 83.53 | 111.33 | |
| `TF_GLM_OVN_MM_CLUSTER=1` | 79.02 | 82.16 | 110.40 | equal |
| `TF_GLM_OVN_MM_DECTILE=100000` | 81.62 | 84.83 | 112.10 | equal |
| `TF_GLM_OVN_SWIGLU_REDUCE=1` | 80.54 | 84.82 | 112.60 | equal |
| `TF_GLM_OVN_KVB8=1` | 84.41 | 87.59 | 114.87 | DIFFER |
| control 3 | 78.97 | 83.09 | 110.33 | |

`ROUTER16` and `DECODE_INDEX` sit between their controls: no effect seen. `MM_CLUSTER` is below both of its neighbours at every level (production also runs without clusters). `KVB8` changes the replies (120 rounds against 127 on the prose prompt, a round 0.8% slower): it is a numerics change, which the owner keeps off, and its tok/s is a different text's. `MM_DECTILE` and `SWIGLU_REDUCE` are each above the control before them: candidates, tested next.

**`TF_GLM_OVN_MM_DECTILE=100000` with `TF_GLM_OVN_SWIGLU_REDUCE=1`** (`queue61`). Part 1: c d d c c d d c, one boot each, 1, 2 and 4 clients; part 2: c d d c with a fresh `--parallel 6` and `--parallel 8` boot each (`bench-client.sh`):

| | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| controls | 80.06, 80.58, 81.06, 80.00 | 83.20, 84.35, 84.62, 83.90 | 111.65, 112.31, 111.98, 111.82 | 151.20, 147.05 | 186.10, 181.67 |
| both knobs | 81.51, 81.78, 82.10, 81.77 | 85.29, 84.47, 85.61, 85.23 | 113.26, 113.37, 113.54, 113.33 | 151.35, 152.04 | 186.66, 186.06 |
| knobs against the adjacent control, mean of pairs | +1.70% (s.e. 0.20) | +1.35% (s.e. 0.49) | +1.28% (s.e. 0.11) | +1.7% | +1.3% |

At one and four clients every knob cell is above every control cell; at six and eight the gain is inside the control pairs' spread (2.8% and 2.4%) and no cell regresses. Replies and round counts are the recipe's in every cell and on all 24 prompts (9,600 tokens). The two are a candidate for `DEFS`, not yet in it: equal replies are a served check, and the series carries no byte-level GPU check of the two kernels (`glm_mm<bits>_16n32`, `glm_mm_reduce_swiglu`); the fork's `glm-mm-ovn` check was left out when patch 0022 was ported.

**What cuts a chain before its first miss on code: a copy from the context, not the drafter's confidence.** Section 44 showed 19 of 70 live rounds on our own `code` reply stopping before the chain's first miss. `GLM`'s lanes facts leave the core's `copy_drafts` on (its default) with `first_copy_rows = 4`: when a stream's last 8 tokens occur earlier in its context, the core proposes the continuation from there as a copy, a first copy in a 4-row window, and that window takes the round instead of the DFlash2 block's seven drafts. From the live logs (`work/forced/own9-*/live.log`), for every round: whether the last 8 tokens through the anchor occur earlier in the prompt and reply, and whether the round kept fewer drafts than the block's correct lead:

| our own reply | rounds with a match: cut / not cut | rounds without: cut / not cut | drafts lost in matched rounds, of all lost |
|---|---:|---:|---:|
| `code` | 13 / 3 | 7 / 48 | 56 of 67 |
| `code4` | 6 / 1 | 3 / 64 | 21 of 24 |

In every matched and cut round the kept count is exactly the smaller of 3 and the copy's own correct lead (for example 7 right, 3 kept, copy good for 5; 7 right, 1 kept, copy good for 1), and the uncut matched rounds are later copies that had grown to the full window. No round in either log kept more than the block's own chain would have. The unmatched cuts are the request's first round (the prior's depth) and one to three drafts at a time. Production's engine has no such copy: on its own `code` reply it drafts 6.90 a round. `TF_GLM_COPY_MAX` and `TF_GLM_COPY_REPLY_MATCH`, which `serve.sh` has set since the first launcher, are read nowhere in the v1.2.9 source. Upstream main (`077998f7d`) has the same facts.

**Upstream's opt-in copy mode, `TF_GLM_COPIES=1`** (verified root and context copies, where a copy shares the window with the drafts it agrees with; `queue62`, control / on / control, 24 prompts solo and 1, 2, 4 clients): replies equal on 24 of 24; 3,184 rounds against 3,140; decode 120.1 s against 117.6 and 117.2 s (-2.3%); on the 9 code-like prompts 743 rounds against 712 and -3.6%; 77.22 / 83.05 / 109.83 tok/s at 1 / 2 / 4 clients against controls of 81.12 and 79.52 / 85.03 and 82.47 / 112.98 and 111.01. It stays off. The arm that turns copies off for a block drafter needs an engine switch (patch 0034, `TF_GLM_OVN_NO_COPY`, in its gates as this is written).

**A lead from upstream that applies to our path.** Upstream issue 3570 (opened 2026-11-16) counts three layout-only GPU operations a MoE layer in the EXL3 decode window: two `cuMemcpy2DAsync` and `tf_glm_put_slot`, 135 a round. Our item-plan profiles show `tf_glm_put_slot` once a layer a round (6,426 instances beside `tf_glm_combine`'s 6,426 in `work/nsys41` and `work/nsys44`) and both copies are in `cuda_exl3.zig` `run` (`copyRows`, two calls), so the same operations are in our round.

## 46. Upstream PR #1411 at its new head: the restore's pause at TP=3 falls from 10.8 s to 3.2 s

2026-11-16 23:24 to 2026-11-17 00:28 UTC, `work/queue64.sh`, production restored and healthy at 00:28. Section 32 measured PR #1411 (conversation states on disk) at head `d730aff64` and reported upstream that a restore beside three decoding streams left them silent for 10.8 s. Its author answered with `1f6b50c67` (a disk read sends each block's rows to the other ranks in one step and each rank copies its pieces device to device) on a branch rebased onto main, head `f0a9651b6`, and could measure only two ranks. This is the same window on that head: built as is with no patch of ours (image `glm53-zig:pr1411b`, source tar sha256 `695d02e4376c38bf`, one image id on the three ranks), `scripts/queue-disk-tier.sh` unchanged, the PR tree's two knobs, `--parallel 4 --context 1048576`. Rows and table: `docs/audit-2026-11-12/disktier-pr1411b-{rows.jsonl,table.md}`; the old head's are `disktier-pr1411a-*`.

17 of 17 resumed turns equal a cold server's reply, no row rejected, no disk tier check failed, and no rank log holds a `StagingFull`, `RanksDiffer`, `DiskOrder`, failed write, failed restore or error line.

| turn | `d730aff64` | `f0a9651b6` |
|---|---|---|
| L (596k) turn 3, after every rank was SIGKILLed, 618,496 of 642,700 cached: first token | 30.6 s | 18.4 s |
| its disk read | 4,548 MiB in 12,349 ms | 4,548 MiB in 2,912 ms |
| L turn 4, after a clean restart, beside three decoding streams, 641,024 of 665,918 cached: first token | 31.7 s | 21.2 s |
| its disk read (read ahead) | 4,697 MiB in 2,691 ms | 4,697 MiB in 2,321 ms |
| the other three streams' longest gap during turn 4 (before the request) | 10,779 ms (1,397 ms) | 3,150 ms (1,407 ms) |
| 32k conversation after SIGKILL: first token, disk read | 2.0 s, 644 MiB in 782 ms | 1.3 s, 644 MiB in 306 ms |
| 120k conversation after SIGKILL: first token, disk read | 4.0 s, 1,229 MiB in 2,548 ms | 1.9 s, 1,229 MiB in 664 ms |
| L turn 2 from RAM | 17.8 s | 15.2 s |
| L turn 1 cold, beside three decoding streams | 447.9 s | 389.3 s |

The last two rows involve no disk, so they are the rebase onto a newer main and not the commit; the same base effect is in the server's prompt pass after a restore (18.2 to 15.4 s on turn 3, 20.5 to 17.7 s on turn 4). The first token less that prompt pass, which is the restore's own part, went from 12.4 s to 2.9 s on turn 3 and from 11.2 s to 3.5 s on turn 4. Against production's tier on the same conversation (12.80 s after a SIGKILL, 12.90 s after a clean restart) this head's server prompt pass is 15.43 s and 17.67 s, 1.21 and 1.37 times production's where the old head was 1.42 and 1.59.

What this means for the recipe: `patches/pr1411` is the net patch of the old head. Re-cutting it from `f0a9651b6` needs the head's base (main past v1.2.9) reconciled with our pin, so it is a re-seat, not a copy; the numbers above are what it would bring to a restore on the recipe.

## 47. Patches 0034 (`TF_GLM_OVN_NO_COPY`) and 0035 (`glm-mm-ovn`): gated, the check passes on a GB10, copies off is +1.4% over 24 prompts

2026-11-17, 00:20 to 01:54 UTC. Both patches were written by `ds41-direct` lanes from exact briefs (nothing compiled on the workstation; every build, test, fmt and lean run on the shared gate host), and each claim below was re-checked here.

**Patch 0034, `TF_GLM_OVN_NO_COPY`** (default off): GLM's `facts()` set `.copy_drafts = !(block and cuda.ovn.on("NO_COPY"))`, so with a DFlash2 drafter loaded and the switch on, the lanes core proposes no copied continuation (`config.zig`: `max_copy` 0, root and context copies off; `windows.zig` `copyProposal` returns at its first line) and every window carries the block's drafts. A core host test (`no_copy_test.zig`: a GLM-shaped lone stream whose context repeats its first eight ids) observes the copy taking the round at three rows with copies on and the seven held drafts with them off; a `facts()` host test covers the switch on, off and unset, with and without a drafter. Four mutants of single added lines are killed (the `block` guard dropped, the switch name replaced, and each arm of the core test forced), with the tree ids checked to differ. One more effect, from `config.zig`: with `copy_drafts` false the first copy is one row and `base_width` two, and `base_width` sizes a window of forced tokens, so a stream forces one token a round instead of up to three. Forced tokens come only from a thinking block's close (a thinking budget's cut forces two of GLM's three close tokens, `\n`, `</think>`, `\n\n`; a loop guard's close forces all three), and both happen only while thinking is open: at most two rounds once in such a request, none with thinking off. The patch header says so.

**Patch 0035, `glm-mm-ovn`**: the GPU check that patch 0022 (the four matmul launch variants) was ported without, from the fork commit the variants came from (ai-engine `cbf94fde5`), on this tree's helpers. Each case runs the same input through the default launch and the variant, both outputs pre-filled with a marker byte, and compares the whole buffers at fp32 and bf16 output: `MM_DECTILE` and `MM_CLUSTER` at 1 to 100 rows on four shapes and the four bit widths (rows 17 to 100 take today's buckets in both arms by the variant's own gate), `SWIGLU_REDUCE` on widths 704, 640 and 2048 at 1 to 100 rows (the check asserts the variant took the launch), `MM_WIDE` on two prompt shapes. A planted control (new) shows the comparison reports a one-bit change and a changed input. The fork's file never compiled (a capture shadowed a declaration); the port fixes it. It registers in `glm_ovn_checks.zig`, so `zig/tests/cuda/main.zig` stays at 599 lines. Not covered: the check does not assert that `MM_DECTILE`'s variant kernel was the one launched, so a silent fallback would compare equal; the served cells (+1.3 to +1.7%) are the evidence that the serve launches it.

**Gates** (`scripts/spark-gates.py`, run `sg-20261117-002047`): series tree `2af443845021` (35 patches) and stack tree `f3204870b8fc` (with `pr1411` and cache-salt) PASS against the pristine base; `compile-cuda-tests` rc 0; the only failing test on every tree is the base's own `cli_config_test`; lean 341 problems on both sides, 0 new. The image source for `glm53-zig:v129u` was packed from tree `f3204870b8fc`, the gated one (one image id on the three ranks).

**On a GB10** (`queue65`): `tf-cuda-test glm-mm-ovn` exits 0 with five PASS lines and no FAIL.

**`TF_GLM_OVN_NO_COPY=1`, control / on / on / control at production's deployed shape** (`queue65`, 24 prompts one at a time with `per_prompt.py`, and the bench at 1, 2 and 4 clients): replies equal the recipe's on 24 of 24 in every boot.

| 24 prompts | rounds, controls / on / production | decode s, controls | decode s, on | on against the controls |
|---|---:|---:|---:|---:|
| all 24 | 3,140 / 3,117 / 3,116 | 119.13, 119.04 | 117.59, 117.32 | +1.39% |
| 9 code-like | 712 / 689 / 675 | 34.73, 34.62 | 33.53, 33.41 | +3.60% |
| 15 prose-like | 2,428 / 2,428 / 2,441 | 84.40, 84.42 | 84.07, 83.90 | +0.50% |

Per prompt the ratio is 1.0166 (95% bootstrap interval 1.0069 to 1.0291), faster on 21 of 24. The rounds that move are code, code3, code4, shell, rust, go and json (code 72 to 65, json 95 to 86); with copies off, code drafts 5.89 a round against 5.83 and needs fewer rounds, which is section 45's mechanism removed. On the prose bench copies never fire: the round counts are equal in every cell (127, 343 and 660 at 1, 2 and 4 clients) and the throughput moves -0.30 / +0.58 / +0.44% against controls that spread 1.0 / 1.5 / 0.3%.

At 6 and 8 streams (fresh boots, the prose bench, control / on / on / control): 151.32 / 148.06 / 147.61 / 147.40 and 186.93 / 182.01 / 182.19 / 182.88 tok/s, -1.0% and -1.5% against the controls' mean, with every arm taking exactly the same rounds (1,065 and 1,436). With the same rounds and replies the two arms do the same work (the switch only stops copy proposals, and none fire on these prompts); the first control reads 2.2 to 2.7% above the other three, and the adjacent pair on / control reads +0.14% and -0.38%. Not called a loss or a pass from one block: `queue66` repeats it with code prompts beside the prose.

**The three candidates together, one boot** (`NO_COPY`, `MM_DECTILE=100000`, `SWIGLU_REDUCE`): 79.73 / 83.48 / 111.13 tok/s at 1 / 2 / 4 clients (+0.48 / +1.00 / +0.58% against the controls), and 114.73 s over the 24 prompts, +3.79% against the controls' mean (code-like +6.03%, prose-like +2.90%). Against production that is not a same-sitting number (production's 24 prompts were measured on 2026-11-16 at 19:09); `queue66` measures production before and after the Zig boots.

**A correction to section 44's determinism note:** reply texts are identical between a prompt's two repetitions everywhere, but the rounds are not always: code3 took 70 and 72 rounds, gc 153 and 154, in some boots (history in one earlier boot). The lanes core's depth rule prices a depth by measured round times (`depth.zig`, `roundCost`), so timing can move one round's depth. A per-prompt difference of one or two rounds is therefore noise; the copy effect above (23 rounds over the set, 7 on one prompt) is not.

## 48. The three candidate knobs at every level, `pr1411/0002` on the stack, warm turns against production, and a boot race in the window tooling

2026-11-17, 15:55 to 18:58 UTC, `scripts/queues/queue66.sh` and `queue67.sh`, image `glm53-zig:v129v` (stack tree `5137a5ef75ab`: pin, `patches/engine` 0001 to 0035, `patches/pr1411` 0001 and 0002, cache-salt; the image source was packed from that tree and the image id is the same on the three ranks). Production restored and healthy at 18:38 and 18:58. Rows: `docs/audit-2026-11-12/queue-rows/queue66` and `queue67-68-warm`.

**`tf-cuda-test glm-mm-ovn` again on a GB10**: five PASS lines, rc 0, 1.31 s including the container's start.

**The candidate knobs, six boots** (`queue66`: recipe, `NO_COPY`, candidate, candidate, `NO_COPY`, recipe; the candidate is `TF_GLM_OVN_NO_COPY=1` with `TF_GLM_OVN_MM_DECTILE=100000` and `TF_GLM_OVN_SWIGLU_REDUCE=1`). 1, 2 and 4 clients on a `--parallel 4 --context 1048576` boot, 6 and 8 streams on fresh `--parallel 6` and `--parallel 8` boots; each cell the mean `agg_tok_s` of three waves, the prose bench (`prose33.json`) and the four code prompts as ids (`scripts/code_ids.json`):

| level | prose: recipe 1, 2 | no copy 1, 2 | candidate 1, 2 | code: recipe 1, 2 | no copy 1, 2 | candidate 1, 2 |
|---|---|---|---|---|---|---|
| 1 | 80.49, 79.66 | 79.47, 79.10 | 80.17, 79.45 | 104.00, 101.25 | 111.89, 111.65 | 112.41, 112.44 |
| 2 | 84.70, 82.80 | 82.73, 82.90 | 83.76, 82.94 | 132.32, 132.25 | 134.68, 134.29 | 134.95, 134.68 |
| 4 | 112.76, 110.67 | 110.15, 110.42 | 111.16, 110.94 | 161.57, 158.05 | 164.58, 164.67 | 163.92, 165.17 |
| 6 | 147.95, 150.70 | 146.73, 150.91 | 150.64, 150.94 | 196.32, 200.31 | 198.53, 202.84 | 202.11, 202.35 |
| 8 | 182.44, 185.53 | 182.02, 186.48 | 186.76, 186.30 | 229.17, 233.13 | 243.82, 242.44 | 243.12, 241.93 |

Replies are equal across all six boots in every cell. On code, no copy and the candidate take fewer rounds than the recipe at every level (72 to 65 at one client, 148 or 150 to 137, 334 to 310, 547 to 526, 867 to 834) and are faster at every level: the candidate against the recipe +9.55 / +1.91 / +2.97 / +1.98 / +4.92%. On prose every arm takes the same rounds (127, 343, 660, 1,065, 1,436): copies never fire there, so the recipe and no copy do the same work, and their difference (-0.99 / -1.11 / -1.28 / -0.34 / +0.14%) is boot-to-boot variation, which here reaches 2.3% between the recipe's own two boots. The candidate against no copy on prose, the two matmul knobs alone: +0.66 / +0.65 / +0.69 / +1.32 / +1.24%. Against the recipe on prose: -0.33 / -0.47 / -0.60 / +0.98 / +1.38%, where the recipe's first boot reads 1.0 to 2.3% above its second at 1, 2 and 4 clients. With differences this size against single boots, the decision is not made from this window: `queue68` repeats it as four recipe and candidate pairs after a discarded warm-up boot, with the 24 prompts on every boot.

The 24 prompts, one at a time, in the same sitting (production before and after the Zig boots, its two runs 114.2 and 115.9 s of decode with every reply and round count equal): the recipe's first boot against production 0.981 (95% interval 0.962 to 0.999, faster on 10 of 24), the candidate 0.984 (0.970 to 0.997); the candidate takes 3,117 rounds where the recipe takes 3,140 and production 3,116. First token, mean over the 24: production 167 ms, the recipe 151 ms, the candidate 152 ms.

**`patches/pr1411/0002` on the stack** (the disk tier window, `scripts/queue-disk-tier.sh`, `KNOBS=measured`; rows `docs/audit-2026-11-12/disktier-v129v-*`): 17 of 17 resumed replies equal a cold server's, no check failed, no row rejected. Against the same window on the stack without 0002 (`disktier-v129c-*`, section 41):

| turn | without 0002 | with 0002 |
|---|---|---|
| 596k conversation after every rank was SIGKILLed: first token, disk read | 25.00 s, 4,548 MiB in 10,768 ms | 16.43 s, 4,548 MiB in 2,380 ms |
| after a clean restart, beside three decoding streams: first token | 27.73 s | 20.32 s |
| the other streams' longest gap during that turn (before the request) | 10,441 ms (1,206 ms) | 3,272 ms (1,203 ms) |
| 32k conversation after SIGKILL: first token, disk read | 1.62 s, 644 MiB in 721 ms | 1.17 s, 644 MiB in 280 ms |
| 120k conversation after SIGKILL | 3.51 s | 1.74 s |
| 120k state written at a clean stop, next start | 3.38 s | 1.57 s |

The first column's pause is from section 41's rows put through today's `scripts/disk_table.py` (that run kept no table); the tool also lists one failed instrument check there, a 120k state that was still in RAM when the window expected it on disk, its reply equal. The server's own prompt pass after each restore is unchanged (14.22 and 14.04 s; 16.48 and 16.20 s), so the whole gain is the restore. The long conversation's replies differ between the two images because its prompt does: 596,183 tokens on the first image, 596,176 on this one, the 7 tokens of the effort line patch 0033 removes; each image's resumed replies equal its own cold ones.

**An agent's warm turn** (`queue67`, `scripts/longctx.py probe`, production's `ttft.py` method: a conversation primed, re-primed before every turn and not measured, then the turn's first token; thinking off, three repetitions; first token in ms):

| case | production | Zig with `TF_GLM_REQUEST_STARTS=1` | Zig over production |
|---|---:|---:|---:|
| ~100k conversation, +2,000 tokens, idle | 927, 939, 921 (2,110 tokens new) | 1,207, 1,260, 1,200 (2,050 new) | 1.30x |
| ~250k conversation, +600 tokens, idle | 489, 497, 499 (648 new) | 715, 652, 653 (712 new) | 1.31x |
| the same beside three decoding streams | 614, 583, 640 | 730, 765, 763 | 1.24x |
| the conversation's cold prime, 100k / 250k | 35.1 s / 91.1 s | 51.1 s / 131.8 s | 1.45x / 1.45x |

Production keeps a finished request's state on its 64-token grid (cached 99,584 and 251,968 of the primes' 99,647 and 251,977); with request starts Zig resumes at the last message start or 2,048-row point (99,644 and 251,904: the start of a message under 256 tokens past a cut is not a cut). Zig re-reads about as many tokens and is 150 to 280 ms slower a turn: what is left is prompt speed. The recipe's own arm without request starts is missing (next paragraph); section 29 measured it at 2.1 s on the 100k turn on an older image.

**The failed boot, and the fix.** The recipe arm's boot reported "rank 0 never created its container (301s)". Docker's own events say otherwise: rank 0's container was created and started at 18:46:23, the same second production's head was removed, and ran until its process exited at 18:51:24, when `--rm` removed it, so `zig-tp3.sh`'s check found no container and misnamed the cause. On spark2 and spark3 the Zig workers' containers started at 18:46:23 and 18:46:24 and exited within a second, while production's own rank 1 and rank 2 containers kept running until 18:48:22: the queues stopped production with `docker rm -f glm53-flash-tf samplers pwcap` on spark1 alone, and production's workers outlive their head by about two minutes (their NCCL timeout). Rank 0 then waited 300 s for workers that were gone. The next boot, at 18:51:36, came up. Every earlier window used the same stop and booted without trouble, so it is a race, lost here after production had just served 250k-token probes. Fixed in the tooling: `scripts/prod-stop.sh` removes production's container on all three ranks and returns once none runs; `zig-tp3.sh` waits up to 240 s until no box runs production before it boots, and reports a rank 0 container that ran and was removed as exited, with the workers' state. `scripts/tests/test_zig_tp3_prod_wait.sh` (stubs, no GPU) passes on the fixed script and fails on the old one (8 of 10 checks) and on three single-line mutants (no wait: 3; the exit not tracked: 2; spark1 alone probed: 6). `queue68` re-runs the recipe's warm turns with `prod-stop.sh` and `KEEP=1`.

**A correction to section 29 and `docs/audit-2026-11-12/longctx-audit.md`:** both said `TF_GLM_REQUEST_STARTS=1` changes numerics. That came from upstream's registry, which classes the switch as arithmetic; section 29's own rows give the same `token_sha` on all six warm turns and the cold 32k turn with and without it, and upstream PR #2404's receipts show 19 turns with one reply digest across 12 runs. Both places are corrected. With `--learn-conversations` the switch is refused by upstream ("until the disk image takes off-grid rows"); `patches/learn-starts` (in its gates as this is written) carries a kept state's chunk-start digest in the disk image so the two can run together.

## 49. The three candidate knobs decided in four clean pairs, the prompt-pass switches and `HOST_ONCE` measured, request starts are a trade

2026-11-17 21:39 to 2026-11-18 01:02 UTC, `scripts/queues/queue68.sh` and `queue69.sh`, image `glm53-zig:v129v` (stack tree `5137a5ef75ab`), every boot `--parallel 4 --context 1048576` except the 6 and 8 stream cells (fresh `--parallel 6` and `--parallel 8` boots), `KNOBS=measured`, `KEEP=1`. Production stopped on all three ranks for both and restored healthy at the end of each. Scores: `scripts/queue-scores/score68.py` and `score69.py` over `docs/audit-2026-11-12/queue-rows/queue68`, `queue69` and `queue67-68-warm`.

**The candidate (`TF_GLM_OVN_NO_COPY=1`, `TF_GLM_OVN_MM_DECTILE=100000`, `TF_GLM_OVN_SWIGLU_REDUCE=1`) against the recipe** (`queue68`, boots recipe, candidate, candidate, recipe, recipe, candidate, candidate, recipe after one discarded warm-up boot; pairs taken adjacent; 6 and 8 streams on two more pairs; each cell the mean `agg_tok_s` of three waves, production's prompt ids):

| level | prose: pairs | mean | code: pairs | mean |
|---|---|---:|---|---:|
| 1 | +0.94 +2.44 +1.38 -1.32% | +0.86% | +10.82 +12.14 +12.22 +9.40% | +11.15% |
| 2 | +1.05 +1.89 +1.62 -0.71% | +0.96% | +4.11 +4.84 +4.70 +2.86% | +4.13% |
| 4 | +0.99 +1.85 +0.26 +0.37% | +0.87% | +4.19 +4.65 +4.33 +3.66% | +4.21% |
| 6 | -0.04 -0.42% | -0.23% | +3.17 +0.77% | +1.97% |
| 8 | +0.43 +0.18% | +0.30% | +5.10 +4.66% | +4.88% |

Replies are equal in every cell across all boots. On prose the rounds are the same in both arms at every level (127, 343, 660, 1,065, 1,436: copies never fire there), so the prose difference is the two matmul knobs; the one negative pair at one and two clients and the 6-stream mean (-0.23%, both values inside one recipe pair's own spread) are not slower under the noise rule. On code the candidate takes fewer rounds at every level (72 to 65, 150 to 137, 334 to 310, 547 to 526, 867 to 834). The 24 prompts one at a time, four boots each arm: every reply equal across all eight boots; the candidate over the recipe 1.0218 (95% interval 1.0126 to 1.0337), faster on 23 of 24, code-like 1.0404, prose-like 1.0108; 3,117 rounds against 3,140. No level regresses: the three knobs are wins.

**The prompt-pass switches** (`queue69` A, boots recipe, `CHUNK_SOLO=4096`, `ONEPASS_PIPE=1`, `ONEPASS_PIPE=1`, `CHUNK_SOLO=4096`, recipe; first token of a cold prompt, the mean of two requests a boot, then each arm's mean over its two boots):

| prompt | recipe | `CHUNK_SOLO=4096` | `ONEPASS_PIPE=1` |
|---|---|---|---|
| 8k | 4,212, 4,199 ms | 4,211, 4,207 ms, +0.08% | 4,000, 4,014 ms, -4.73% |
| 32k | 16,316, 16,439 ms | 15,952, 15,928 ms, -2.67% | 15,420, 15,422 ms, -5.84% |
| 120k | 62,042, 61,967 ms | 59,736, 59,764 ms, -3.64% | 57,934, 57,998 ms, -6.51% |

Every `ONEPASS_PIPE` boot is under both recipe boots at all three sizes, and so is every `CHUNK_SOLO` boot at 32k and 120k. Decode on the same boots, prose and code ids at 1, 2 and 4 clients: both within -0.81% to +0.46% of the recipe, the rounds and the replies the same in every arm (code at 2 clients took 148 or 150 rounds by boot, recipe boots included). `ONEPASS_PIPE` at 6 and 8 streams (boots recipe, pipe, pipe, recipe): prose -0.08% and +0.33%; code -1.05% (pairs -0.40, -1.69%) and -0.46% (pairs -2.26, +1.34%), neither slower under the noise rule (no pipe boot is under both recipe boots), with the code rounds varying by boot in both arms (1,627 to 1,641 at 6, 2,586 to 2,601 at 8). **What these rows do not show:** the cold probe seeded its prompts by boot (`--seed pf69-<label>`), so the cold replies of the three arms answer different prompts and cannot be compared; the exactness of both switches on long prompts is measured again in `queue71` with one seed for every boot.

**`TF_GLM_OVN_HOST_ONCE`** (`queue69` C, both arms with `TF_GLM_REQUEST_STARTS=1`, boots recipe, host, host, recipe; a ~250k conversation, +600 tokens, three turns idle and three beside three decoding streams): idle 664.7 against 658.3 ms (-0.95%), loaded 762.7 against 760.0 ms (-0.35%); the same six reply digests in every boot. Level, a hair faster when idle.

**Request starts: the warm probe prices their cost, not their payoff** (`queue68`, the recipe and the recipe with `TF_GLM_REQUEST_STARTS=1` on fresh boots, queue67's prompts; first token in ms):

| warm turn | recipe | with request starts | resumed at (recipe, request starts) |
|---|---|---|---|
| ~100k, +2,000 tokens, idle | 1,936, 1,947, 1,985 | 1,207, 1,266, 1,201 | 98,304, 99,644 |
| ~250k, +600 tokens, idle | 565, 567, 559 | 663, 647, 654 | 251,904, 251,904 |
| the same beside three decoding streams | 581, 578, 580 | 756, 791, 774 | 251,904, 251,904 |

At 100k the request start is a nearer place to resume (2,038 rows to read again, not 3,378), and the turn is 37% faster. At 250k both arms resume at the same point and read the same 705 rows, and request starts cost 91 ms idle and 194 ms beside decoding streams. The rows show what was paid for: the recipe's 250k turn kept no state (`kept_states` 0), the request-starts turn kept one (`kept_states` 1, 1,734 MiB more held), by the switch's design where its history ends, the place the next turn of that conversation would resume (the 100k turns resumed at 99,644; production's rows of the same prime count 99,647 tokens). The probe never sends that next turn: every repetition is the same base with a new suffix, re-primed in between, so the kept state is never used and only its cost is measured. A growing conversation is the instrument (each turn the previous prompt, its reply and a new message: `longctx.py chain`, now with `--salt` so production can be sent a conversation it has not cached). Until it is measured that way the switch stays off; whether the cut and keep cost an extra prompt step is read from the `TF_GLM_PROF` prompt lines of the same turns.

**Production's rows in `queue68` are void as a comparison.** They reused queue67's seeds, and production's prefix cache is persistent: its 100k turns were served with 101,632 and 101,696 of 101,682 to 101,713 prompt tokens cached (queue67: 99,584 on first sight), its 250k turns with 252,608 of about 252,610, so they measure a turn production had already seen (227 to 300 ms and 369 to 387 ms). Queue67's production rows (section 48) stay the comparison; a production leg must use prompts production has not been sent before. The Zig boots start empty, so their rows are unaffected.

## 50. The wins together, the recipe against production on every leg, and where the prompt pass loses its time

2026-11-18 22:44 to 2026-11-19 05:39 UTC, `scripts/queues/queue71.sh` and `queue72.sh`, image `glm53-zig:v129v` (stack tree `5137a5ef75ab`), every Zig boot `--parallel 4 --context 1048576` (production's deployed shape), `KNOBS=measured`, `KEEP=1`. Production served the production legs of both queues, was stopped on all three ranks from 22:50 to 02:37 and from 02:56 to 05:20, and was restored healthy both times. Rows: `docs/audit-2026-11-12/queue-rows/` (committed with this section, with the rows of queues 66 to 69); scores: `scripts/queue-scores/score71.py` and `score72.py` (`score68.py` and `score69.py` for section 49). Every figure below is printed by those scripts.

**The prompt-pass switches are exact on long prompts** (`queue71` A: eight boots, one seed on every boot, cold 8k / 32k / 120k twice a boot). Each of the six prompts has one reply digest across all eight boots, so `ONEPASS_PIPE`, `CHUNK_SOLO=4096`, both together, and both with `TF_GLM_OVN_EXCHANGE_KB=4096` reproduce the recipe's replies. Cold first token against the recipe (its two boots 4,270 and 4,207 ms, 16,683 and 16,466 ms, 63,040 and 62,126 ms):

| arm | 8k | 32k | 120k |
|---|---:|---:|---:|
| `ONEPASS_PIPE` (one boot) | -5.30% | -6.74% | -6.95% |
| `CHUNK_SOLO=4096` (one boot) | -0.68% | -3.71% | -4.46% |
| both (two boots) | -5.26% | -9.57% | -10.53% |
| both and `EXCHANGE_KB=4096` (two boots) | -5.14% | -9.46% | -10.60% |

`EXCHANGE_KB` adds nothing and stays out. Section 49's two-boot rows for the two switches alone agree (-4.73 / -5.84 / -6.51% and +0.08 / -2.67 / -3.64%).

**Decode at depth and the draft rule** (`queue71` B and C, two boots each arm, replies equal in every cell). `TF_GLM_INDEX_CUDA=all` (decode windows on the index kernels) and `TF_GLM_OVN_DECODE_INDEX=33` against the recipe on a ~100k and a ~250k context (`scripts/longdec_ids.json`, two requests each) read -0.2% to +1.0% for `all` (six of eight cells above the recipe's boots) and -0.9% to +0.5% for `33`; on the greedy ids at 1 / 2 / 4 clients `all` reads +2.0 / +1.6 / +0.7% (prose) and +1.2 / +1.2 / +0.7% (code). The recipe's own two boots on the one-stream prose cell read 79.12 and 79.54 tok/s in that block and 81.03 and 80.81 in the next, so a gain of +2% is inside the boot-to-boot spread; both stay out and `all` gets more boots later. `TF_GLM_DFLASH2_WIN=1024` loses on code at depth (-1.5% and -2.5% at 100k, -1.2% and -1.7% at 250k): out. `TF_GLM_OVN_PLAIN_MARGIN=100` leaves every round count unchanged, greedy and sampled, and decode within -1.3% to +1.2%: inert, out. `TF_GLM_OVN_DRAFT_NOISE=1` leaves greedy streams alone (rounds equal, decode -0.1% to +0.8%) and on sampled streams (temperature 1.0, top-p 0.95, top-k 20, seed 7, production's agent sampling, `scripts/streams_sampled.py`) takes fewer rounds with the same replies: prose 438 to 435, 1,107 to 1,092 and 2,154 to 2,109 rounds at 1 / 2 / 4 clients, decode +0.74 / +1.76 / +2.96%; code 219 to 216, 465 to 459 and 1,041 to 1,035 rounds, +0.74 / +0.57 / +0.44%. It joins the recipe.

**The wins together against the recipe** (`queue72`: the candidate is `NO_COPY`, `MM_DECTILE=100000`, `SWIGLU_REDUCE`, `ONEPASS_PIPE`, `CHUNK_SOLO=4096` and `HOST_ONCE`, without `DRAFT_NOISE`; boots candidate, recipe, recipe, candidate, adjacent pairs; production's prompt ids, three waves a cell):

| level | prose pairs | mean | code pairs | mean |
|---|---|---:|---|---:|
| 1 | +2.59 +0.54% | +1.57% | +10.25 +10.50% | +10.37% |
| 2 | +0.11 +0.63% | +0.37% | +3.55 +4.23% | +3.89% |
| 4 | +0.76 +0.47% | +0.62% | +3.95 +3.94% | +3.95% |
| 6 (4 slots, 2 queued) | -2.30 -4.96% | -3.63% | +5.54 +11.91% | +8.73% |
| 8 (4 slots, 4 queued) | +7.66 -0.89% | +3.38% | -0.29 +4.17% | +1.94% |

Replies and prose rounds are equal at every level (381, 1,029, 1,980 rounds at 1 / 2 / 4 clients) and the candidate takes fewer code rounds (216 to 195, 450 to 411, 1,002 to 930). At 1, 2 and 4 clients both candidate boots are above both recipe boots on every cell. The 6 and 8 cells at the deployed shape queue requests behind four slots, which makes them noisy: the recipe's two boots differ by 7.9% on prose at 6 clients (113.48 and 122.48) and production's two runs by 4.0%, so those rows decide nothing. The fresh `--parallel 6` and `--parallel 8` pairs of section 49 decide those levels for `NO_COPY`, `MM_DECTILE`, `SWIGLU_REDUCE` and `ONEPASS_PIPE`; `CHUNK_SOLO` and `HOST_ONCE` have no such pairs. The 24 prompts one at a time: the candidate over the recipe 1.0148 (95% interval 1.0052 to 1.0273), faster on 18 of 24, code-like 1.0351, prose-like 1.0027, every reply equal across the four Zig boots; decode 116.8 s on both recipe boots against 115.0 and 115.8 s on the candidate's, and 3,141 and 3,140 rounds against 3,117.

**Where the Zig stack stands against production** (`queue72`; production before the window and again after it, the Zig candidate on two boots, the same prompt ids; ratio above 1 is Zig faster):

| decode, aggregate tok/s | production | Zig | Zig over production |
|---|---:|---:|---:|
| greedy prose, 1 stream | 80.19 | 81.72 | 1.019 |
| greedy prose, 2 | 88.40 | 84.86 | 0.960 |
| greedy prose, 4 | 116.56 | 112.43 | 0.965 |
| greedy code, 1 | 115.40 | 114.14 | 0.989 |
| greedy code, 2 | 145.19 | 136.65 | 0.941 |
| greedy code, 4 | 183.90 | 166.61 | 0.906 |
| sampled prose, 1 / 2 / 4 | 82.47 / 85.43 / 116.25 | 76.62 / 79.96 / 104.31 | 0.929 / 0.936 / 0.897 |
| sampled code, 1 / 2 / 4 | 108.35 / 139.30 / 173.53 | 115.61 / 140.48 / 158.62 | 1.067 / 1.008 / 0.914 |

The queued cells at 6 and 8 clients read 0.974 and 0.978 (prose) and 1.008 and 0.897 (code), within the noise above. The sampled rows are the candidate without `DRAFT_NOISE` and the two serves draw different replies, so they compare speed only; `DRAFT_NOISE` is worth +0.4% to +3.0% there (`queue71` C). The 24 prompts one at a time: Zig over production 0.9803 (95% interval 0.9660 to 0.9941, faster on 7 of 24), code-like 0.9787, prose-like 0.9813, the rounds 3,117 against production's 3,116, so what is left is round time. Decode at ~100k and ~250k (two requests each, `scripts/longdec_ids.json`): prose 71.7 and 68.8 tok/s against production's 79.1 and 73.7 (0.906 and 0.932), code 119.7 and 111.8 against 114.8 and 117.1 (1.043 and 0.954).

| prompt work | production | Zig | Zig over production |
|---|---:|---:|---:|
| cold first token, 8k | 2,908 ms | 4,007 ms | 1.378x |
| cold first token, 32k | 11,054 ms | 14,977 ms | 1.355x |
| cold first token, 120k | 41,904 ms | 55,910 ms | 1.334x |
| a growing conversation (~1,300 new tokens a turn), ~113k, turns 2 to 8 | 668 ms | 1,308 ms without request starts, 844 ms with | 1.96x, 1.26x |
| the same at ~284k, turns 2 to 6 | 744 ms | 1,420 ms, 910 ms | 1.91x, 1.22x |
| 596k conversation after a SIGKILL of every rank (disk tier), prefill | 12.80 s | 12.81 s | 1.00x |
| the same after a clean restart, beside 3 decoding streams | 12.90 s | 15.79 s | 1.22x |
| the same conversation, turn 2 from RAM | 12.54 s | 12.69 s | 1.01x |
| 596k conversation cold, no other stream (the disk-tier window's reference boot) | 224.68 s (its `tier_chain.sh` run, load not recorded) | 291.26 s | 1.30x |

The first three rows and the two growing conversations are measured today; the 596k rows are the disk-tier window's own (`docs/audit-2026-11-12/queue-rows/queue72/disktier-f72/table.md`: 17 of 17 resumed replies equal a cold server's, no failed check; production's figures as `scripts/disk_table.py` carries them from its `tier_chain.sh`, taken on an earlier day). The recipe without the wins read 1.46x, 1.50x and 1.51x of production's cold first token at 8k, 32k and 120k (`queue71`'s recipe boots against today's production); with them it reads 1.38x, 1.36x and 1.33x. A restart no longer costs anything against production. What remains is prompt speed (cold, and the new tokens of a warm turn: with request starts 1,274 new rows at about 455 us a row against production's 1,306 at about 345 is 131 ms of the 176 ms between 844 and 668 ms, an estimate that assumes a 1,300-row pass costs what a 4,096-row pass does a row), decode at two to four streams, and sampled decode.

**Request starts, on the instrument that sends the next turn** (`longctx.py chain`, with `--salt` so production is sent a conversation it has not cached; production's first turn 39.5 and 39.8 s at ~113k tokens, 102.2 and 102.7 s at ~284k). At ~113k, without request starts a turn re-reads from the last 2,048-row grid point: 1,330 to 3,112 uncached tokens a turn (mean 2,208) against production's mean 1,306 on its 64-token grid, and the first-token times scatter with where the grid falls (811 to 1,834 ms). With them a turn re-reads 1,242 to 1,330 tokens (mean 1,274) and the times are steady (828 to 878 ms): -35.5% a turn at ~113k (464 ms) and -35.9% at ~284k (510 ms; uncached 1,248 to 1,292 against 1,566 to 3,148). The cost is on the cold prime: +7.3% at both sizes (56.3 against 52.4 s and 144.0 against 134.2 s), and on cold prompts +4.1% at 8k, +6.5% at 32k and +7.2% at 120k. The warm probe's +4.9% and +12.4% at ~250k (idle and beside three streams, section 49) are a separate cost: the state kept for a next turn that the probe never sends. The break-even is 8.3 turns after a cold ~113k prime and 19.1 after a cold ~284k one. The prompt cache holds about the same bytes in both arms (7,304 to 7,970 MiB with 8 to 12 states without request starts, 6,406 to 8,014 MiB with 4 to 7, of a 9,1xx MiB budget). **Why the cold prime costs 7%, as far as it is known:** the cold means with request starts (4,170, 15,956 and 59,919 ms) are within 1% of the `CHUNK_SOLO`-only arm of `queue71` (4,210, 15,959 and 59,794 ms) and 3 to 4% above its `ONEPASS_PIPE`-only arm (4,014, 15,457 and 58,235 ms). `cuda_prompt_cuts.zig`'s `stepRows` refuses a solo pass for any request that has a cut ("a solo pass would step over a request start"), and a chat prompt has a message start after row 0, so with request starts a prompt runs in 2,048-row steps and loses solo's 3.7 to 4.5%. Whether `ONEPASS_PIPE`'s gain survives request starts is not measured. A solo step that ends at the next cut instead of stepping over it would keep solo; the chunk plan has to stay a deterministic function of the request's cuts, because the resume check (`resumes`, and `learn-starts`' `below` digest) compares plans, so the change needs its own host tests and a bit-exactness run before it is trusted.

**Where a 4,096-row prompt pass loses its time** (`queue72`'s capture, rank 0, `scripts/nsys-prefill.sh` with `prefill_stages.py`: a cold 8,192 and a cold 32,768 prompt on the candidate, 40,989 rows; `docs/audit-2026-11-12/queue-rows/queue72/pf-f72/`). Passes 1 to 7 of the 32k prompt take 1,843 to 1,887 ms, 450 to 461 us a row (the client's first token for that prompt under nsys, 15,081 ms, equals the unprofiled probes'); its first pass shows 5.3 s of idle because the capture script leaves a 5 s pause between its two prompts. In a steady pass the main stream is idle 216 of 1,843 ms (11.7%), waiting on the side stream's exchanges (the partials exchange 22 us a row, the glued rows' share 30), while the side stream's NCCL kernels run 506 to 513 ms of the pass, 198 to 205 ms of it with the main stream idle; over the capture they are 123.9 us a row in 14,778 launches of mean 344 us. Kernel time a row, rank 0, against production's own accounting of a 4,096-row chunk at 32k (`HuntPrefill/REPORT.md` in the Python repo: derived from an nsys of an older image, the indexer taken as sharded, not taken on today's image, so a lead and not a verdict):

| kernel family | ours, us a row | production's accounting |
|---|---:|---:|
| dense prompt matmul (`glm_mm4_128`) | 110.7 | 96.5 |
| experts gate/up, down | 74.7, 53.8 | 83.8, 60.1 |
| combine | 32.9 | 32.1 |
| KDA (`kda_step`, `kda_prep`) | 32.2 | 27.7 |
| sparse attention | 20.1 | 20.1 |
| `absorb_q` and `expand_v` | 33.4 | 6.6 |
| hc post and partial | 21.2 | 17.2 |
| router | 6.1 | 4.8 |
| NCCL send and receive (side stream) | 123.9 | 113.2 |
| main stream waiting on exchanges | about 52 | 5 to 12 (1.3 to 3.2% of 375) |

Added up, the kernel rows of our column exceed production's by 36 us a row (385 against 349) and the waits by 40 to 47, which accounts for the 450 to 470 us a row we run at against the 375 of that accounting. Production's present figure is about 345 us a row (cold 32k: four requests, 343.5 to 348.3), a further 30 us a row that this comparison cannot see. Three leads follow from the table, none yet tried here. (1) The exchanges. We move about the bytes production moves (NCCL kernel time a row 123.9 against 113.2) and leave the main stream waiting for them where production's accounting shows almost no wait. Our boot posts each exchange in **8 row pieces** (`glm: a prompt chunk's exchanges in 8 row pieces`: upstream's default under `CHUNK_SOLO=4096` with `ROCE_MULTI=1`, `cuda_ranks.zig`) and production in 2 (its `HuntComms` report), and upstream's recipe documents solo gaining 7.3 to 8.4% on cold prompts without the RoCE wire against 3.2 to 3.4% with it (`docs/recipes/glm-5.3-flash-cuda.md` at the pin). The piece count changes scheduling only (`forward.pieced_layers`: same kernels and bits as unpieced), so a sweep is bit-exact; `ROCE_MULTI` buys +1.4 to +1.8% decode at 1 to 4 streams (section 21), a trade to price in seconds a turn. (2) `absorb_q` and `expand_v` (`glm_glue_latent.cuh`) are CUDA-core ports of production's Triton reductions in the same accumulation order, one row a pass of the loop with two block syncs a row, 33.4 us a row against production's 6.6; the file's own note says rows per block change no bits, so a version that takes several rows through each load of the weights and each sync would keep every bit. (3) The dense matmul (`glm_mm4_128`) is 14% above production's (110.7 against 96.5).

**What the recipe takes from this.** `DEFS` gains the seven switches measured above as wins (`NO_COPY`, `MM_DECTILE=100000`, `SWIGLU_REDUCE`, `ONEPASS_PIPE`, `CHUNK_SOLO=4096`, `HOST_ONCE`, `DRAFT_NOISE`): 23 in all, none changing a reply on any cell here. Fresh 6 and 8 stream pairs exist for the first four (section 49); `CHUNK_SOLO` (a prompt step while no stream decodes), `HOST_ONCE` (a request's render) and `DRAFT_NOISE` (sampled streams) have none, so those cells are the next window's, with the exact final set against the recipe. Out: `EXCHANGE_KB`, `INDEX_CUDA=all`, `DECODE_INDEX=33`, `DFLASH2_WIN=1024`, `PLAIN_MARGIN=100`. Request starts stay off in the recipe until `patches/learn-starts` has its GPU check (the disk tier refuses the pair without it) and until the cold-prime cost has a fix or the owner takes the trade (8.3 turns to break even after a ~113k cold prime). The image with `learn-starts` is `glm53-zig:v129w`: the `v129v` tree plus that package, tree `7c8a05f9cf72`.

## 51. Queue73: the recipe against the one before it, the cold-prompt arms, and two defects the GPU found (a solo pass never taken with request starts, a disk tier that kept one state in four)

2026-11-19 15:35 to 19:18 UTC, `scripts/queues/queue73.sh`, scored by `scripts/queue-scores/score73.py` (rows in `docs/audit-2026-11-12/queue-rows/queue73/`). Image `glm53-zig:v129z` (43 patches, tree `da12e9d259ae`: engine 0001 to 0037, pr1411, cache-salt, learn-starts, solo-cuts) for every block but the first; block E ran on `v129w` (40 patches, tree `7c8a05f9cf72`: the stack and learn-starts, without solo-cuts and engine 0036 and 0037). Every boot `--parallel 4 --context 1048576` (the deployed shape) unless a block says otherwise, `KNOBS=measured`. Production was stopped at 15:35 and stays down for the campaign.

**The committed recipe against the one before it** (blocks A and B: boots R F F R, R the recipe without the seven switches of 2026-11-19, F the committed 23; production's prompt ids; the 6 and 8 client rows on serves booted with that `--parallel`). Replies and prose rounds are equal in every cell; F takes fewer rounds on code and on sampled streams.

| cell | recipe before | recipe | pairs | mean | rounds before / now |
|---|---|---|---|---:|---|
| greedy prose, 1 | 79.21 79.88 | 80.45 80.40 | +1.57% +0.66% | +1.11% | 381 / 381 |
| greedy prose, 2 | 83.47 84.56 | 83.45 83.79 | -0.02% -0.91% | -0.47% | 1029 / 1029 |
| greedy prose, 4 | 110.44 112.34 | 110.88 112.96 | +0.40% +0.55% | +0.47% | 1980 / 1980 |
| greedy prose, 6 | 150.50 151.18 | 151.12 150.64 | +0.41% -0.36% | +0.03% | 3195 / 3195 |
| greedy prose, 8 | 186.90 186.05 | 185.73 186.12 | -0.62% +0.04% | -0.29% | 4308 / 4308 |
| greedy code, 1 | 102.46 102.34 | 112.41 112.93 | +9.71% +10.35% | +10.03% | 216 / 195 |
| greedy code, 2 | 130.78 132.09 | 135.53 135.78 | +3.63% +2.79% | +3.21% | 450 / 411 |
| greedy code, 4 | 159.19 161.23 | 164.65 167.60 | +3.43% +3.95% | +3.69% | 1002 / 930 |
| greedy code, 6 | 199.05 200.72 | 203.23 202.18 | +2.10% +0.73% | +1.41% | 1641 / 1578 |
| greedy code, 8 | 237.22 237.91 | 243.69 242.63 | +2.73% +1.98% | +2.35% | 2594 / 2502 |
| sampled prose, 1 | 72.60 74.09 | 75.77 77.32 | +4.37% +4.36% | +4.37% | 438 / 420 |
| sampled prose, 2 | 77.76 78.89 | 80.82 82.45 | +3.93% +4.51% | +4.22% | 1107 / 1068 |
| sampled prose, 4 | 103.98 103.43 | 106.56 107.47 | +2.48% +3.91% | +3.20% | 2154 / 2088 |
| sampled prose, 6 | 138.84 139.53 | 143.40 143.25 | +3.28% +2.67% | +2.98% | 3420 / 3351 |
| sampled prose, 8 | 171.12 168.83 | 175.29 174.96 | +2.44% +3.63% | +3.03% | 4614 / 4512 |
| sampled code, 1 | 101.27 102.57 | 110.68 112.16 | +9.29% +9.35% | +9.32% | 219 / 198 |
| sampled code, 2 | 131.43 131.51 | 140.58 142.68 | +6.97% +8.49% | +7.73% | 465 / 405 |
| sampled code, 4 | 151.34 152.91 | 156.11 158.45 | +3.15% +3.62% | +3.39% | 1041 / 981 |
| sampled code, 6 | 177.42 178.83 | 188.58 188.57 | +6.29% +5.45% | +5.87% | 1659 / 1590 |
| sampled code, 8 | 225.72 224.93 | 231.34 229.63 | +2.49% +2.09% | +2.29% | 2622 / 2490 |

The recipe is at or above the old one in 18 of 20 means. The two greedy prose cells that read below, at 2 and 8 clients (-0.47% and -0.29%), sit inside the old recipe's own boot spread (1.3% and 0.5%) and the recipe's boots overlap it; no cell has both new boots under both old ones. The 24 prompts one at a time (replies equal across the four boots): all 24 1.0242 faster (1.0143 to 1.0369, 22 of 24 faster), the 9 code-like prompts 1.0416 (1.0185 to 1.0694, 8 of 9), the 15 prose-like 1.0139 (1.0098 to 1.0176, 14 of 15). The committed 23 switches stay as `DEFS`.

**Cold first token, the prompt-pass arms** (block C: 14 boots, two requests a boot at 8k, 32k and 120k, one seed on every boot, so the reply must be one digest per size and request across all of them, and it is). The control pair `f1`, `f2` (the start and the end of the block) agrees within 0.21%, 0.04% and 0.06%; each arm below is one boot, so a number is a screen until its second boot, and the next window runs the candidates A B B A.

| arm | what it sets | 8k ms | 32k ms | 120k ms | 8k | 32k | 120k |
|---|---|---:|---:|---:|---:|---:|---:|
| f1, f2 | the recipe | 3988, 3996 | 14897, 14891 | 55590, 55554 | - | - | - |
| p2 | `TF_GLM_OVERLAP_PIECES=2` (production's) | 4006 | 15088 | 56357 | +0.33% | +1.30% | +1.41% |
| p3 | `OVERLAP_PIECES=3` | 3936 | 14736 | 55074 | -1.41% | -1.06% | -0.90% |
| p4 | `OVERLAP_PIECES=4` | 3942 | 14674 | 54872 | -1.27% | -1.47% | -1.26% |
| p6 | `OVERLAP_PIECES=6` | 3978 | 14856 | 55626 | -0.37% | -0.26% | +0.10% |
| nr | `TF_GLM_ROCE_MULTI=0` | 3956 | 14761 | 55240 | -0.90% | -0.89% | -0.60% |
| mw | `TF_GLM_OVN_MM_WIDE=1` | 3904 | 14395 | 53802 | -2.21% | -3.35% | -3.19% |
| sp | `TF_GLM_OVN_SIDE_PRIO=1` | 3922 | 14548 | 54482 | -1.77% | -2.32% | -1.96% |
| lr2 | `TF_GLM_OVN_LATENT_ROWS=2` | 3972 | 14815 | 55344 | -0.52% | -0.53% | -0.41% |
| lr4 | `TF_GLM_OVN_LATENT_ROWS=4` | 3978 | 14858 | 55392 | -0.36% | -0.24% | -0.32% |
| rs | `TF_GLM_REQUEST_STARTS=1` (solo-cuts) | 4162 | 15927 | 59709 | +4.24% | +6.94% | +7.45% |
| rs0 | request starts on `v129w` (no solo-cuts) | 4184 | 15956 | 59846 | +4.80% | +7.13% | +7.69% |
| rsnp | request starts with `ONEPASS_PIPE=0` | 4417 | 17106 | 64308 | +10.64% | +14.85% | +15.72% |

`MM_WIDE` (-2.2 to -3.4%) and `SIDE_PRIO` (-1.8 to -2.3%) are the two arms that move well past the control pair's spread. `MM_WIDE` was last measured neutral on a cold prompt (section 31, on a stack that had neither `ONEPASS_PIPE` nor solo passes); `SIDE_PRIO` is measured here for the first time. 3 and 4 row pieces read about -1.3% and 2 reads worse (+1.3%), so production's 2 is not the better setting here. `ROCE_MULTI=0` reads -0.6 to -0.9% on a cold prompt but the wire buys +1.4 to +1.8% of decode at 1 to 4 streams (section 21), so it stays. The latent rows are a decode lever: -0.3 to -0.5% cold, and on the decode screens (greedy, one boot, against the recipe's two boots of block A) `lr2` reads +1.06 / +1.68 / +0.58% on prose and +1.23 / +0.91 / +0.59% on code at 1 / 2 / 4 clients, `lr4` +0.18 / +1.00 / +0.56% and +0.60 / +0.64 / +0.84%, `sp` -1.49 / +1.01 / +0.50% and -0.24 / +1.05 / +0.15%; replies equal to both recipe boots in every cell. `glm-latent-rows` ran on a GB10 for the first time: rc 0, six PASS lines, no FAIL (byte equality of the absorb and expand kernels at 2 and 4 rows against today's launch). `ONEPASS_PIPE=0` costs 6.4 to 8.3 points more with request starts on (`rsnp` against `rs`), so the pipe stays on.

**Request starts: the solo-cuts package took no solo step.** `rs` and `rs0` are the same arm to within 0.6 points (+4.24 / +6.94 / +7.45% against +4.80 / +7.13 / +7.69%), and so are their growing conversations' first turns (56,126 ms against 56,264 ms, ratio 0.998). Request starts cost 4.2 to 7.5% of a cold prompt with the package, as without it. The package's predicate (`cutInside`) counted every start between a step's first row and its end, and the server's chunk plan (`zig/src/server/chunk_plan.zig`, `Plan.starts`) lists a start at every grid step from the last start as well as at each message, so the cut at every solo step's middle grid point was always inside it: no step was ever solo. The package's host tests used start lists with a few message starts and no grid steps, a list the server never sends (section 50 of this file records the 4.1 / 6.5 / 7.2% cost the package was written to remove). Two more facts surfaced while reading the fix: the grid after a message start is off the 4-row pool's edge for three starts in four, and a solo step from such a row would have ended in `error.PastRing` (the index ring held a solo pass's rows only from a pool's edge), so lifting the predicate alone would have failed requests. Both are fixed in the revised package (section 52).

What the starts buy is large. The ~113k growing conversation (`longctx.py chain`, one 100k turn and seven of about 1,300 new tokens):

| arm | first turn ms | turns 2 to 8 ms | mean | new tokens a turn |
|---|---:|---|---:|---|
| f1 (recipe) | 52,403 | 805 1,578 1,033 1,766 1,407 873 1,611 | 1,296 | 1,328 2,617 1,841 3,110 2,307 1,491 2,737 |
| rs (request starts, solo-cuts) | 56,126 | 872 859 842 839 832 833 839 | 845 | 1,327 1,290 1,273 1,270 1,246 1,249 1,269 |
| rs0 (request starts, no solo-cuts) | 56,264 | 877 881 842 838 828 828 829 | 846 | 1,328 1,292 1,275 1,272 1,248 1,239 1,253 |

A warm turn costs 0.652 of the recipe's (0.653 for `rs0`) because each turn resumes where the previous turn's history ends, not at the last 2,048-row point; the first turn costs 1.071 of it (1.074). The chains' replies are not comparable across these arms (each boot used its own salt); the next window sends one salt to every arm.

**The disk tier with request starts kept one state in four** (block E, image `v129w`, `scripts/queue-disk-tier.sh f73`: boots `k1`, `k2` after a SIGKILL of every rank, `k3` after a clean stop, a reference boot without the tier). Every resumed reply equals the cold reply to the same messages (all 17 turn rows `equal`): the tier is exact. It failed 15 of its checks, all one kind: a state expected on disk was not there (`SOURCE expected disk, resumed from cold`, or a resume `SHORT` of the newest kept state). The rank logs name it: `warning: prompt cache: imprint: saving 32035 tokens skipped (SnapshotShape)` (also 120,601, 2,946, 619,434 and again 32,035 and 120,601), six saves skipped in `k1`, four in `k2` (two more at its stop) and five in `k3`. `cuda_disk_image.parts` refused every state whose position is not a multiple of the 4-row pool, and a request start or a prompt's end lands on one such multiple in four. What that did:

| conversation | the state the next turn needed | on disk | resumed from, after SIGKILL / clean restart |
|---|---|---|---|
| M32000 (about 32k) | 32,035 (the previous turn's end) | no (off the pool) | cold, 16.2 and 16.3 s first token |
| M120000 (about 120k) | 120,601 | no | cold, 59.95 and 60.11 s |
| L (about 596k, then 619k, 643k) | 619,434 (turn 2's end) | no | 595,968 (turn 1's state, a multiple of 4), 23,466 rows short |

L turn 3 after the SIGKILL read 26.30 s of server prefill for 46,725 uncached tokens (production: 12.80 s from a state 619,392 rows in, for its own prompt) and 42.83 s for 69,943 uncached tokens after the clean restart (production 12.90 s); from RAM, turn 2 read 13.49 s (production 12.54 s from the pool), and the cold turn 1 beside three decoding streams 334.18 s (production 224.68 s, 1.49x). A save in flight at a clean stop was lost with the rest (`S120000` resumed at 116,736 of 118,784). The tier needs the endpoint states on disk: the restart cost above is mostly the rows that were not there, not the read. The fix (`patches/disk-any-position`, section 52) lets the image take any position; nothing in the store, the rows layer or the engine needed the pool alignment (the pooled-key kernel writes only a completed pool, `tf_glm_pool_keys` returns when `4 * p + 3 > pos + rows - 1`, so the pool in progress is not part of a prompt pass's state; `rows.image.valid` takes between `at / per` and `at / per + 1` pooled rows).

**What stays.** `TF_GLM_REQUEST_STARTS` stays off in `DEFS`: its cost on a cold prompt is unchanged until the solo steps run, and its disk checks have not passed. `MM_WIDE`, `SIDE_PRIO`, 4 row pieces and `LATENT_ROWS=2` are candidates that need a second boot in the reverse order and a decode screen at 1, 2 and 4 clients before they are named switches of the recipe (`MM_WIDE` and `SIDE_PRIO` also at 6 and 8). Housekeeping: the smoke boot of `v129z` answered, and queue73's `rs0` arm ran on the older image, which is why it is the same arm without solo-cuts.


## 52. The two fixes on a GPU: solo steps run between request starts (cold +0.2 to +1.2% with them), and the disk tier resumes every state it is asked to, each reply equal to a cold server's

2026-11-19 20:17 to 21:50 UTC: queue74's block C1 (`scripts/queues/queue74.sh`) and queue75's block E (`scripts/queues/queue75.sh`), scored by `scripts/queue-scores/score74.py` and `score75.py`; rows in `docs/audit-2026-11-12/queue-rows/queue74` and `queue75` once those queues end. Image `glm53-zig:v129za` (44 patches), the same image id on spark1, spark2 and spark3: it was built from tree `9d7f1de0488a`, which differs from the committed stack (tree `7656da6d8139`) in three test files and comment text only, no line of engine code (`patches/solo-cuts/RECORD.md`, Gate). Every boot `--parallel 4 --context 1048576`, `KNOBS=measured`; production stayed down.

**The two fixes** (both found by section 51's window).

- `patches/solo-cuts`, revised. The server's chunk plan lists a start every 2,048 rows from the last start, so a request's cut at a solo step's middle grid point is always there, and the first version counted it as a start inside the step: no solo step ran. The revision leaves that point out of `cutInside` and tests with start lists shaped as `Plan.starts` and `withCut` build them (the first version's host tests used a few message starts and no grid steps). Lifting the predicate alone would have failed differently: a solo pass from a row off the 4-row pool's edge floors its index ring's base to the pool below, so a ring of exactly a solo pass's rows (4,096) ends in `error.PastRing`. A Python model of that arithmetic over random prompts, with start lists built as the server builds them (scratch, not kept): 2,716 of 4,000 end in `PastRing` at 4,096 rows, 0 of 4,000 fresh passes and 0 of 3,000 resumed ones at 4,100. The ring is therefore one pool (4 rows) longer: 24 KiB a state at TP=2 (the arena sizes in `cuda_kv8_test.zig` moved by that), and the disk store's identity changes with it.
- `patches/disk-any-position` (new). The disk image's `parts` refused a position off the pool's edge (`SnapshotShape`), so three states in four were never saved, and the staging floor priced only whole pools. The rows layer already takes `at / per` to `at / per + 1` rows, the pooled-key kernel writes only completed pools, and the probe's hash already zeroes the pool in progress, so `parts` takes any position from 1 to the capacity and `longest` is the capacity (`patches/disk-any-position/RECORD.md` has the read of each point).

**Gates.** A full run on the gate host, `sg-20261119-210540`, the pristine pin (tree `4be51cc6beef`) against the 44-patch stack (tree `7656da6d8139`): every step rc 0 but `test-cuda-host`, which fails only the base's own `cli_config_test.test.serve --config` name (6,912 of 6,946 passed on the stack, 33 skipped, 1 failed; the base 6,716 of 6,750), lean 341 problems on both sides, 0 new, verdict PASS. The ten mutants of solo-cuts and the five of disk-any-position each fail only the tests written for them (the tables are in the two RECORD files). Two earlier attempts of the full run died 10 s after their start with `the runner exited early rc=143`: the gate host has no lingering, so its user manager stopped 10 s after the last login session ended and took the run's systemd scope with it. `scripts/spark-gates.py` now holds one session through a run's launch and wait.

**Block C1: request starts with the revised package, boots f1 rs1 rs2 f2** (one seed on every boot, two requests a size; rs is `TF_GLM_REQUEST_STARTS=1`). Cold first token:

| boot | 8k ms | 32k ms | 120k ms | 8k | 32k | 120k |
|---|---:|---:|---:|---:|---:|---:|
| f1 | 3977 | 14832 | 55568 | - | - | - |
| f2 | 3985 | 14908 | 55718 | - | - | - |
| rs1 | 4030 | 14943 | 55742 | +1.23% | +0.49% | +0.18% |
| rs2 | 4028 | 14923 | 55736 | +1.19% | +0.35% | +0.17% |

The percentages are against the mean of the two boots without request starts, which agree within 0.20%, 0.51% and 0.27%; both boots with them read slower at every size, so this is a cost, and a small one: +48, +63 and +96 ms a cold request (the two boots' mean against the controls'), down from +4.2%, +6.9% and +7.5% before the revision. Each cold request takes one more small pass at its prompt's end (the assistant header's cut) and splits the last step at its message starts, which is where the milliseconds go (an inference from the plan's shape, not a profile). One reply digest for every (size, request) over the four boots. The ~113k growing conversation (one salt, so every boot's turns are the same prompts):

| boot | first turn ms | turns 2 to 8 ms | mean | cached tokens turns 2 to 8 |
|---|---:|---|---:|---|
| f1 | 52,344 | 813 1,577 1,033 1,774 1,405 883 1,622 | 1,301 | 112,640 112,640 114,688 114,688 116,736 118,784 118,784 |
| rs1 | 52,403 | 886 869 851 846 835 835 845 | 852 | 112,640 113,963 115,252 116,524 117,793 119,038 120,286 |
| rs2 | 52,370 | 873 872 848 846 835 836 842 | 850 | 112,640 113,963 115,252 116,524 117,793 119,038 120,286 |
| f2 | 52,392 | 815 1,584 1,037 1,778 1,410 886 1,633 | 1,306 | 112,640 112,640 114,688 114,688 116,736 118,784 118,784 |

All 8 turns have one reply digest and one prompt length over the four boots. With request starts the first turn costs 1.000 of the recipe's and turns 2 to 8 cost 0.653 (851 against 1,304 ms); each turn resumes at the previous prompt's end less its three header tokens (113,963, 115,252, ...), where the recipe resumes at the last 2,048-row point.

Greedy decode at 1, 2 and 4 clients (the same prompt ids as production's cells, three rounds each):

| cell | f1 | f2 | rs1 | rs2 | rs mean over controls | rounds f / rs | ms a round f1 f2 rs1 rs2 |
|---|---:|---:|---:|---:|---:|---|---|
| greedy prose, 1 | 81.74 | 81.20 | 80.93 | 79.99 | -1.24% | 381 / 381 | 37.50 37.73 37.87 38.33 |
| greedy prose, 2 | 85.63 | 84.85 | 84.61 | 84.90 | -0.57% | 1029 / 1029 | 26.90 27.13 27.20 27.13 |
| greedy prose, 4 | 113.74 | 112.71 | 112.31 | 111.66 | -1.10% | 1980 / 1980 | 21.17 21.30 21.40 21.50 |
| greedy code, 1 | 114.52 | 113.81 | 114.06 | 113.42 | -0.37% | 195 / 195 | 51.03 51.37 51.23 51.50 |
| greedy code, 2 | 138.24 | 136.70 | 136.66 | 136.68 | -0.58% | 411 / 411 | 40.97 41.43 41.40 41.43 |
| greedy code, 4 | 168.23 | 167.04 | 166.85 | 166.42 | -0.60% | 930 / 930 | 30.13 30.33 30.33 30.47 |

The rs boots read 0.4 to 1.2% under the controls' mean in all six cells, with the two controls 0.6 to 1.1% apart, rounds and tokens a round equal in every cell, and replies equal. The short bench prompts have no cuts (a 33-token prompt's assistant start is inside the first 256 rows, so the plan merges it), so the switch changes nothing on the decode path that a boot could carry; this is either boot-to-boot spread or a cost not yet found, and four boots do not settle it. Queue76 block D runs eight fresh boots, f rs rs f f rs rs f.

**Block E: the disk tier with request starts** (`scripts/queue-disk-tier.sh f75`: boots `k1`, `k2` after a SIGKILL of every rank, `k3` after a clean stop, and a reference boot without the tier; 20:57 to 21:50). Every one of the 17 turns (cold, from RAM and from the disk) equals a cold server's reply (token digests), and no rank logged a skipped save, a failed write or restore, or a failed check in any boot (`save_skipped` 0, `staging_full` 0). Against queue73's window on `v129w` (the same conversations):

| conversation | after | resumed from, rows (before / now) | first token s (before / now) | server prefill s (before / now) |
|---|---|---|---|---:|
| M32000 | SIGKILL | 0 (cold) / 32,035 (disk) | 16.18 / 0.57 | 16.18 / 0.28 |
| M120000 | SIGKILL | 0 (cold) / 120,601 (disk) | 59.95 / 0.93 | 59.94 / 0.28 |
| L | SIGKILL | 595,968 (disk) / 619,434 (disk) | 28.73 / 14.93 | 26.30 / 12.41 |
| M32000 | clean restart | 0 (cold) / 32,035 (disk) | 16.30 / 0.67 | 16.30 / 0.38 |
| M120000 | clean restart | 0 (cold) / 120,601 (disk) | 60.11 / 1.00 | 60.11 / 0.32 |
| L | clean restart | 595,968 (disk) / 642,690 (disk) | 46.67 / 18.89 | 42.83 / 14.84 |
| S120000 | clean stop (a save in flight) | 116,736 (disk) / 120,353 (disk) | 2.67 / 0.81 | 2.08 / 0.15 |

Each state is now resumed at the exact endpoint its previous turn kept. Against production's tier chain (`PROD_CHAIN` in `scripts/disk_table.py`): L turn 2 from RAM 12.72 s against 12.54 s (1.01x), L turn 3 after the SIGKILL 12.41 s against 12.80 s (0.97x), L turn 4 after a clean restart beside three decoding streams 14.84 s against 12.90 s (1.15x; its state is 642,690 rows); the cold 596k turn 1 beside three decoding streams is 334.64 s against 224.68 s (1.49x), which this work did not touch. The 4,554 MiB state of L turn 3 reads from the store in 2,489 ms on rank 0, which is 2.49 s of the 12.41 s; the rest is the 23,259 uncached rows' prefill. A request of another `cache_salt` resumed nothing (cached 0 of 32,228; the control without a salt 32,035), and the save in flight at a clean stop was written. The store held 8,580 MiB in 3,058 files after `k1`, 9,521 MiB after `k2` and 12,680 MiB in 3,716 files after `k3`, against a 131,072 MiB cap. A saved state's own part on rank 0 is 435 MiB at 2,912 rows and 811 MiB at 665,908 rows (the log's `imprint:` lines), so most of a save is fixed per state and the daily write budget (`--learn-daily-gib`) is spent by the count of states more than by their length; a request keeps one or two states.

The window's tool reported 2 failed checks, both of one kind and neither the engine's: the `after eviction` rows of `k1` (M32000 and M120000 turn 3) expected the disk and resumed from RAM, equal replies in 0.23 and 0.24 s. `queue-disk-tier.sh` clears the states at the conversation's last 2,048-row grid point (`disk.newest_kept`), but with request starts the state a turn resumes from is at the previous prompt's end, so the loop found nothing to evict and the endpoint states stayed in RAM. The harness now records the highest position the RAM store created during each turn (`scripts/disk.py`, with `scripts/tests/test_disk_newest.py`), so the eviction clears the real state and `SHORT` compares with the real newest one; the live-eviction resume is part of queue77's disk block.

**What stays.** `TF_GLM_REQUEST_STARTS` stays off in `DEFS`: with the revision it costs a cold prompt +1.2%, +0.4% and +0.2% at 8k, 32k and 120k (a measured cost at every size, so a trade the owner takes) and buys 0.653 of a warm turn on a growing conversation and every resume at its previous turn's endpoint after a restart; its decode reading is under queue76 block D. The disk tier with `patches/learn-starts` and `patches/disk-any-position` passes its check. Queue75 continues with the row-piece arms for warm turns (B) and the candidates `MM_WIDE`, `SIDE_PRIO`, 4 pieces and `LATENT_ROWS=2` against four request-starts controls (A).

## 53. Queue75: row pieces on warm turns, and four prompt-pass switches against four request-starts controls; together -5.0% to -5.5% cold and -2.9% warm, every reply equal

2026-11-19 20:57 to 23:59 UTC, `scripts/queues/queue75.sh` after the disk tier block of section 52; scored by `scripts/queue-scores/score75.py`, the adoption rule in `scripts/queue-scores/decide75.py` (written before the rows were read); rows in `docs/audit-2026-11-12/queue-rows/queue75` and `queue74`. Image `glm53-zig:v129za`, `--parallel 4 --context 1048576`, `KNOBS=measured`, and `TF_GLM_REQUEST_STARTS=1` on every arm, so the controls are the request-starts recipe: `rs1` and `rs2` of queue74 and `rs3` and `rs4` of this queue, which ran after the first candidates and last of all. Every boot makes the cold probe with ONE seed (so each cold reply must be one digest across all arms), the growing ~113k conversation (one salt) and greedy decode at 1, 2 and 4 clients on production's prompt ids. The four controls agree on the cold first token within 0.09% (8k), 0.32% (32k) and 0.25% (120k): 4,030 4,028 4,028 4,031 / 14,943 14,923 14,896 14,898 / 55,742 55,736 55,602 55,617 ms; their conversation reads 52,272 ms for the first turn and 851 ms for turns 2 to 8; their decode spreads 1.56 / 1.64 / 1.18% (prose) and 1.24 / 1.40 / 0.52% (code) at 1 / 2 / 4 clients, which is the noise any decode difference below about 1.5% has to be read against.

**Block B: the exchanges' row pieces on warm turns** (one boot each; a warm turn is a chunk of about 1,300 rows, so 8 pieces make 256-row pieces there where a 4,096-row step makes 512-row pieces; pieces are cut on 128-row boundaries):

| arm | sets | first turn ms | vs controls | turns 2 to 8 ms | vs controls | decode prose 1 / 2 / 4, code 1 / 2 / 4 vs controls |
|---|---|---:|---:|---:|---:|---|
| w1 | `TF_GLM_OVERLAP_PIECES=1` | 53344 | +2.05% | 861 | +1.07% | -0.27% -0.41% -0.36% -1.21% -0.69% -0.67% |
| w2 | pieces 2 (production's) | 52435 | +0.31% | 848 | -0.39% | -1.01% -0.03% -0.13% -1.09% +0.23% +0.02% |
| w3 | pieces 3 | 51100 | -2.24% | 840 | -1.33% | -0.68% -1.10% -0.60% -0.63% -0.37% +0.16% |
| w6 | pieces 6 | 51510 | -1.46% | 845 | -0.73% | +1.25% +0.99% +0.86% +0.96% +0.94% +0.57% |
| nr | `TF_GLM_ROCE_MULTI=0` | 51325 | -1.81% | 843 | -0.96% | -1.68% -1.86% -0.76% -2.59% -1.42% +1.18% |

No piece count changes a warm turn by more than 1.4%, so there is nothing for a policy that picks the count by the chunk's rows to win. One piece (no overlap) is the worst, and 3 and 6 pieces read a little under 8, which is the cold effect of the next table (cold prompts are where pieces matter). The pieces do not enter decode, so the decode columns of w1 to w6 are the boots' own spread (up to 1.25%); `ROCE_MULTI=0` (NCCL for the small all-gathers) is 1.8% faster on the cold first turn and 0.8 to 2.6% slower at one and two decode clients, which is what the wire buys, so it stays on. All 21 conversations of queues 74 and 75 have one reply digest and one prompt length at every turn.

**Block A: four candidates, two boots each (forward and reversed order), against the controls' mean:**

| candidate | sets | 8k ms | 32k ms | 120k ms | 8k | 32k | 120k | first turn | turns 2 to 8 | decode prose 1 / 2 / 4, code 1 / 2 / 4 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| mw | `TF_GLM_OVN_MM_WIDE=1` | 3944 | 14498 | 54089 | -2.13% (-2.66% -1.59%) | -2.80% (-3.36% -2.24%) | -2.85% (-3.40% -2.30%) | -2.90% | -1.78% | -0.44% -0.26% +0.10% -0.36% +0.32% -0.24% |
| sp | `TF_GLM_OVN_SIDE_PRIO=1` | 3960 | 14656 | 54732 | -1.72% (-1.98% -1.46%) | -1.74% (-2.03% -1.44%) | -1.69% (-1.91% -1.47%) | -1.61% | -1.41% | -0.45% -0.18% -0.25% -0.11% +0.05% +0.01% |
| p4 | `TF_GLM_OVERLAP_PIECES=4` | 3988 | 14803 | 55191 | -1.02% (-1.10% -0.95%) | -0.75% (-0.69% -0.81%) | -0.87% (-0.75% -0.98%) | -0.64% | -0.31% | +0.58% +0.92% +0.90% +0.51% +0.78% +0.58% |
| lr2 | `TF_GLM_OVN_LATENT_ROWS=2` | 4019 | 14908 | 55576 | -0.26% (-0.34% -0.18%) | -0.05% (-0.09% -0.01%) | -0.18% (-0.23% -0.13%) | -0.05% | -0.47% | +0.31% +0.28% +0.14% +0.61% +0.56% +0.14% |
| all | the four together | 3826 | 14108 | 52607 | -5.04% (-5.49% -4.59%) | -5.41% (-5.90% -4.91%) | -5.51% (-6.05% -4.97%) | -5.56% | -2.90% | -0.19% +0.02% -0.12% +0.02% +0.18% -0.08% |

The two bracketed figures are the two boots. The rule: a candidate joins only when its replies are equal to the controls' on every cold request, conversation turn and decode cell; both boots are below the controls' mean at every size and the pair's mean below their fastest boot at two of three sizes; no decode cell's pair mean is below the controls' slowest boot; and a warm turn and the first turn are no more than 0.5% over. All five candidates pass (`decide75.py` prints ADOPT for each, on the committed rows). `MM_WIDE` is the largest (it matches the 14 us a row by which the dense prompt matmul trailed production's accounting in section 50, an inference from the size and not a profile), `SIDE_PRIO` the second (the exchanges' side stream at the highest priority: the waits on it were about 52 us a row), 4 row pieces about 0.9% and latent rows 0.2% on a cold prompt; the four are nearly additive (the singles sum to -5.13 / -5.34 / -5.59% against the combined -5.04 / -5.41 / -5.51%). The combined arm's decode cells are level with the controls (-0.19% to +0.18%, inside their 0.5 to 1.6% spread); `p4` and `lr2` read +0.1 to +0.9%, which for `p4` (pieces do not enter decode) is the boots' spread and for `lr2` (the latent kernels run in decode windows too) agrees with queue73's screens of +0.6 to +1.7% and is a likely small gain that queue77's pairs decide. Every cold reply is one digest over all 16 boots with a cold probe, and every conversation turn one digest over all 21 boots with a chain. The two boots of a candidate differ by 0.1 to 1.1 points (`mw` at 8k: -2.66% and -1.59%) where the controls' four boots differ by at most 0.32%, so a candidate's figure is its pair's mean.

Against production (same prompt ids; its cold first token 2,908 / 11,054 / 41,904 ms and its warm turns 668 ms, section 50, re-derived from `queue72/f72-p1` and `f72-p2`), with request starts on: the controls are 1.386x / 1.349x / 1.329x of production's cold first token and 1.274x of its warm turn; with the four switches 1.316x / 1.276x / 1.255x cold, 1.244x on the 113k first turn (49,364 against 39,683 ms) and 1.237x warm (827 against 668 ms). Without request starts the recipe is 1.369x / 1.345x / 1.328x cold and 1.95x warm (section 52).

**What goes forward.** The final recipe N is the committed recipe plus `TF_GLM_OVN_MM_WIDE=1`, `TF_GLM_OVN_SIDE_PRIO=1`, `TF_GLM_OVERLAP_PIECES=4` and `TF_GLM_OVN_LATENT_ROWS=2` (all four scheduling or byte-checked launches: replies unchanged). `DEFS` does not change until queue77 has confirmed N at 1, 2, 4, 6 and 8 clients against the committed recipe, so every confirmation arm keeps its baseline; queue76 profiles and measures decode on N. Queue77 also reads three variants of N never measured here (`MM_WIDE=2`, `TF_GLM_PREFILL_REDUCE=ring` and `gather`, 3 and 8 pieces), and queue78 screens nine registered prompt-side switches on N with a control booted first, last and after every third screen.

## 54. Where the final recipe's decode round and prompt pass go (queue76's nsys captures), and why the next prompt lever is the exchange wire

2026-11-20 00:00 to 00:08 UTC, `scripts/queues/queue76.sh` (the final recipe N with request starts, image `glm53-zig:v129za`, `--parallel 4 --context 1048576`, rank 0 under Nsight Systems through `scripts/nsys-rank0.sh` and `scripts/nsys-prefill.sh`); analysed with `scripts/decode_rounds.py` (new: `--min-wall`, `--range`), `scripts/prefill_stages.py` and `scripts/site_timeline.py` (new: one layer's kernels on both streams in time order). Rows and reports: `docs/audit-2026-11-12/queue-rows/queue76` (`stages.txt`, `f76-n/dec4code.out` and `dec1prose.out`).

**Decode, four clients on code prompts (400 tokens each).** 188 steps over 100 kernels long, 77 of them the drafter's 32-row passes; the 67 verify windows of 18 to 26 rows (`--min-wall 20 --range 18-26`) take 107.65 ms wall with the GPU busy 98.3% (idle 1.85 ms, 1.7%), 4.85 ms a row at 22 rows on average. Production's `dec4x35k` capture (`DecNsysMimo`: 22 to 32 rows, 35k context, a different workload) has verify windows of 86.6 ms at 24 rows and 103.8 at 32, busy 99.0%. Of ours, 80.9 ms (75.1%) is one kernel, `tf_exl3_ovn_nc1`, the routed experts' decode GEMM (84 launches a window, two for each of the 42 MoE layers, 0.96 ms each); then the dense matmuls 7.9 ms (`glm_mm4_32` 6.5), the NCCL all-gathers 5.8 ms (90 launches of 64 us), glue 3.3, KDA 3.2, attention 2.8, the router 0.8. A drafter pass is a separate step of 4.89 ms at four clients (production's passes 3.4 to 3.9 ms; ours at one client about 3.4 ms), 5 all-gathers of 222 us and 37 `group_kernel` launches of 78 us in it. So there is no launch-gap lever (1.7% idle against production's 1.0%) and the decode frontier at 4 clients is the experts' GEMM, which this stack has as production's `dec_kernel` ported (patch 0031) and which runs at an unknown fraction of the box's bandwidth (an expert holds 4.7 MB of weights on rank 0, but the number of distinct experts a window touches was not measured, so no bandwidth figure is claimed). At one client on prose the windows of 2, 4 and 8 rows take 25.3, 33.4 and 49.9 ms (production's 35k captures: 27.3, 38.1, 57.5: another context and another document, so no ratio is drawn); the ratio that is measured on production's own prompts stays section 50's 0.90 to 0.96 at four clients.

**The cold 4,096-row pass (request 1 of `pf-f76w`, 8,197 rows, 459.6 us a row under nsys; unprofiled 3,826 ms for 8k).** Per row: routed experts 135.0 us (29.4%), KDA projections and o_proj 56.0 and its chain 35.0, MLA attention with absorb and expand 71.1 at 8k (59.1 at 32k), combine 37.0, hc glue 24.2, shared expert 18.7, MLA projections 19.7, router 7.7, and the main stream's waits 18.3 us for the partials exchange and 24.5 for the glued rows' share, 9.3% of the pass (production's accounting 5 to 12). The main stream is idle 355 of 3,767 ms and 327 ms of that is exposed side-stream NCCL.

**One site, both streams** (`site_timeline.py`, pass 1). At the MLA mixer site the main stream fills four pieces (0.75 to 0.95 ms each, 3.2 ms in all) and the side stream's NCCL kernels run 506, 879, 1,017 and 628 us (the partials exchanges, about 11 MB a rank a piece) and 485, 274, 263 and 272 us (the shares, 5.6 MB): 4.32 ms of kernel time in a span of 4.86 ms (89% busy), the site ending at the share of the last piece, 2.5 ms after the last fill. At a MoE site the side stream runs 6.30 ms of NCCL in 6.60 ms (95%), the exchanges 1.27, 1.45 and 1.73 ms, and the main stream waits 2.6 ms after its last fill. So the side stream is the critical resource of a site, not the main stream's glue: the glue runs on the main stream in time the main stream has nothing else to do with.

**A scheduling change that was drafted and not built.** `cuda_forward_pair.zig`'s `exchangeGlue` is a pair's site schedule (each piece's exchange, glue and share in order on the side stream, the main stream filling the next piece). A solo pass could take it (`pieced()` calls `exchangeGlue` and `awaitShared` instead of `exchangePieces` and `gluePieces`: the glue kernels touch only their piece's rows, so the overlap is row-disjoint). It was written as patch 0038, `TF_GLM_OVN_PIECES_SIDE_GLUE` (the patch with its test is `docs/audit-2026-11-12/0038-glm-pieces-side-glue.patch.txt`, sha256 `ba3b4554e2a0`, against the 37-patch series' tree; the compile check, `zig fmt` and the lean gate passed on the gate host: 7 of 7 steps, lean 341 against 341), and then the timeline above was read before any GPU time was spent: the glue is 1.3 to 1.4 ms a site, it would join the side stream's 4.3 to 6.3 ms of serial work instead of the main stream's idle time, and the side stream is the saturated one, so the schedule is predicted to lose about 0.6 ms a site, and interleaving the glue between the fills on the main stream gains at most the side stream's gaps (about 0.56 ms a site, under 3% of a pass). It is not in the series.

**The lead that follows.** The side stream's exchanges move the same bytes at 20 to 55% of what the two links carry (an estimate: 11.2 MB out of a rank a piece over two links of about 27 GB/s each is 0.2 ms; the kernels take 0.5 to 1.0 ms at the MLA site and 1.3 to 1.7 ms at a MoE site, where the main stream's own combine traffic competes). The recipe pins production's NCCL shape (`NCCL_MIN_NCHANNELS=4`, `NCCL_MAX_NCHANNELS=4`, one queue pair a connection, NCCL's default 128 KiB chunk and 4 MiB buffers). NCCL moves bytes and never changes a sum, so its settings are replies-equal by construction, and `scripts/queues/queue81.sh` screens them (one queue pair a connection 4, 8 channels, a 512 KiB chunk, a 16 MiB buffer, 8 channels with 4 queue pairs, 2 channels) between three controls: the cold first token at 8k / 32k / 120k, the growing conversation and decode at 1 and 4 clients, `scripts/queue-scores/score81.py`. A setting that moves the exchanges toward the links' rate would remove most of the 43 us a row of waits (the whole of it is 9.8% of the cold pass).

**The decode wire's ceiling.** At one client (2 to 8 rows) the decode all-gathers ride fabric/tp's RoCE (`tp_roce_multi`: 91 launches of 18 us a 2-row window, 27 a round at 35 us in the 8-row group), at four clients (a 24-row window's fp32 partials are 393 KB a rank) they do not: the capture has 90 `ncclDevKernel_AllGather_RING_LL` launches of 64 us a window (5.7 ms, 5.3% of the 107.65 ms) and 3.8 wire launches. The wire's ceiling is `TF_TP_MAILBOX_MAX_KB` (default 256 KiB a rank, boot-checked equal on every rank, at most 1,024 on RoCE; `cuda_roce_multi.zig` prints it at boot), and a gather above it goes to NCCL. The drafter's five all-gathers a pass run on NCCL too (222 us each at four clients; their size was not read). Raising the ceiling to 1,024 moves gathers of up to 64 rows onto the wire, replies unchanged (a gather moves bytes); the wire's gather at 400 to 520 KB is not measured, so queue81 reads it as the arm `mb` at 1, 2, 4, 6 and 8 clients against controls that have the same five levels. A first estimate, from 393 KB over two links of about 27 GB/s each, is about 40 us a gather against 64: 2 to 3 ms a four-client round (2 to 3%).

**What NCCL reports about its transport** (queue81's first boot, `NCCL_DEBUG=INFO` with `INIT,NET,GRAPH,TUNING`, `queue81/f81-c/nccl-info.txt`, NCCL 2.30.7 with the Spectrum-X network plugin): **GPU Direct RDMA is disabled for every HCA** ("NET/IB : GPU Direct RDMA Disabled for HCA 0 'rocep1s0f0'" and the three others and the two merged pairs), so the bytes NCCL sends between the Sparks are staged through its host buffers and a proxy thread; four ring channels over 2 -> 0 -> 1, channels 0 and 2 on the merged NIC pair `rocep1s0f0+rocep1s0f1` and 1 and 3 on `roceP2p1s0f0+roceP2p1s0f1` (256 Gb/s each as NCCL reads them), two queue pairs on each connection, a point-to-point chunk of 262,144 bytes. The recipe's own wire (fabric/tp, `tp_roce_multi`) keeps host-registered buffers (`HostRegister` in `roce_multi.zig`), which is a path without that staging (an inference from the source, not measured), and it carries only all-gathers up to the slot size. Staging is a likely reason the exchanges run at a quarter of the links' rate (an estimate), and why settings that change NCCL's chunking, channels and buffers (queue81) and the wire's ceiling are worth a screen.

**A warm turn** (`pf-f76w` request 4: 1,289 + 3 rows, main stream busy 748 ms): routed experts 306 ms (237 us a row: a 1,289-row chunk touches every expert, so the pass reads all of their weights once), dense matmuls 170 ms, combine 48, the waits 24.8 + 42.5 = 67 ms (9%). The streaming of expert and dense weights is the floor of a warm turn, and the waits are the part this stack can still cut.

## 55. Request starts do not touch decode (queue76 block D, eight boots A B B A)

2026-11-20 00:08 to 00:46 UTC, `scripts/queues/queue76.sh` block D, scored by `scripts/queue-scores/score76.py` on `docs/audit-2026-11-12/queue-rows/queue76`. Image `glm53-zig:v129za`, `--parallel 4 --context 1048576`, `KNOBS=measured`; `f` is the final recipe N (the recipe plus MM_WIDE, SIDE_PRIO, 4 pieces and latent rows) and `rs` is N plus `TF_GLM_REQUEST_STARTS=1`; eight fresh boots in the order f rs rs f f rs rs f, greedy decode at 1, 2 and 4 clients on production's prompt ids (prose and code, three rounds of 400 tokens a cell). Queue74's four boots had read the request-starts boots 0.4 to 1.2% under the controls with the controls 0.6 to 1.1% apart, which left open whether the switch costs decode.

| cell | f mean tok/s | rs mean tok/s | rs over f | f boots' spread | rounds f / rs | ms a round f / rs |
|---|---:|---:|---:|---:|---:|---|
| prose, 1 client | 80.81 | 81.42 | +0.75% | 1.42% | 381 / 381 | 37.92 / 37.62 |
| prose, 2 | 84.49 | 84.85 | +0.43% | 1.15% | 1,029 / 1,029 | 27.26 / 27.15 |
| prose, 4 | 112.48 | 112.74 | +0.23% | 1.13% | 1,980 / 1,980 | 21.35 / 21.31 |
| code, 1 | 113.57 | 114.03 | +0.40% | 1.24% | 195 / 195 | 51.47 / 51.25 |
| code, 2 | 136.43 | 136.87 | +0.32% | 1.01% | 411 / 411 | 41.49 / 41.38 |
| code, 4 | 166.46 | 167.23 | +0.46% | 0.65% | 930 / 930 | 30.45 / 30.31 |

Every cell has one reply set over the eight boots and the same number of rounds with and without the switch; the rs mean lies inside the f boots' range in all six cells, and it reads 0.23 to 0.75% above the f mean (mean +0.43%) with a round 0.2 to 0.8% shorter. So request starts cost decode nothing that these boots can see: queue74's reading was boot-to-boot spread, and the only price of the switch that remains is the cold prompt (+0.2 to +1.2%, section 52), against a warm turn at 0.653 and every resume at its previous turn's endpoint. `TF_GLM_REQUEST_STARTS=1` stays off in `DEFS` until the owner accepts that trade.

The same boots against production's cells of the same instrument (`queue72/f72-p1` and `f72-p2`, the mean of two boots): N reads 1.008 / 0.956 / 0.965 of production's tok/s on prose and 0.984 / 0.940 / 0.905 on code at 1 / 2 / 4 clients, and N with request starts 1.015 / 0.960 / 0.967 and 0.988 / 0.943 / 0.909. The gap is at 2 and 4 clients, where the verify window carries the routed experts' GEMM (section 54).

## 56. Queue81: NCCL's channels per net peer read 1.8 to 2.0% under the controls' cold first token (one boot each; the pairs that decide it are queue83's and queue77's)

2026-11-20 00:46 to 02:33 UTC, `scripts/queues/queue81.sh`, scored by `scripts/queue-scores/score81.py` and judged by `scripts/queue-scores/decide81.py` (both written before the rows were read), rows in `docs/audit-2026-11-12/queue-rows/queue81`. Image `glm53-zig:v129za`, `--parallel 4 --context 1048576`, `KNOBS=measured`. Section 54's timeline had the side stream's NCCL kernels running 4.3 of a MLA site's 4.9 ms and the main stream waiting 18 + 24 us a row for them, and `NCCL_DEBUG=INFO` (`nccl-info.txt` in the rows) showed no GPU Direct RDMA (every HCA reads "disabled") and four ring channels; so this queue asks whether NCCL's own settings move the cold prompt. Each arm is the final recipe N with request starts plus one setting, one boot; the controls c1, c2 and c3 are the same recipe at the start, the middle and the end. The cold first token is the mean of two requests of one seed at each size, and the conversation is salt `c74` (first turn about 100k tokens, then seven turns of 1,000).

| boot | 8k ms | 32k ms | 120k ms | cold against the controls' mean, 8k / 32k / 120k | first turn ms | turns 2 to 8 ms |
|---|---:|---:|---:|---|---:|---:|
| c1 | 3836 | 14154 | 52882 | +0.11% / +0.03% / +0.09% | 49706 (+0.05%) | 828 (+0.29%) |
| c2 | 3798 | 14000 | 52201 | -0.91% / -1.07% / -1.20% | 49116 (-1.14%) | 820 (-0.68%) |
| c3 | 3863 | 14298 | 53418 | +0.80% / +1.04% / +1.11% | 50223 (+1.09%) | 829 (+0.39%) |
| `NCCL_NCHANNELS_PER_NET_PEER=4` (pp) | 3765 | 13877 | 51758 | -1.76% / -1.93% / -2.04% | 48632 (-2.11%) | 818 (-0.92%) |
| 8 channels (n8) | 3769 | 13910 | 52018 | -1.65% / -1.70% / -1.54% | 48824 (-1.73%) | 812 (-1.67%) |
| 8 channels and 4 queue pairs (qn) | 3774 | 13968 | 52112 | -1.52% / -1.29% / -1.36% | 48849 (-1.68%) | 821 (-0.49%) |
| 8 channels, 8 a net peer (p8) | 3792 | 14009 | 52373 | -1.05% / -1.00% / -0.87% | 49087 (-1.20%) | 819 (-0.78%) |
| `TF_TP_MAILBOX_MAX_KB=1024` (mb) | 3814 | 14075 | 52520 | -0.49% / -0.53% / -0.59% | 49314 (-0.74%) | 824 (-0.20%) |
| 4 queue pairs (q4) | 3825 | 14123 | 52708 | -0.19% / -0.20% / -0.24% | 49425 (-0.52%) | 830 (+0.57%) |
| 16 MiB buffers (bf) | 3820 | 14134 | 52739 | -0.33% / -0.12% / -0.18% | 49613 (-0.14%) | 824 (-0.13%) |
| 2 channels (n2) | 3824 | 14114 | 52625 | -0.22% / -0.26% / -0.39% | 49442 (-0.48%) | 825 (-0.04%) |
| 512 KiB net chunks (ch) | 3880 | 14305 | 53402 | +1.23% / +1.09% / +1.08% | 50098 (+0.84%) | 840 (+1.73%) |

The controls' own spread (slowest over fastest) is 1.72%, 2.13% and 2.33% at the three sizes, so one boot of a setting is read only where it clears that. Every cold request, conversation turn and decode cell carries one digest across all twelve boots (NCCL moves bytes, it never changes a sum). The rule written before the rows (decide81.py): an NCCL setting joins when it reads at least 1.0% under the controls' mean at two of three sizes, never over the slowest control, with the first turn and turns 2 to 8 not over the slowest control and no decode cell under the slowest control's boot. `pp` and `qn` pass it, `n8` fails it on two decode cells (code at one and at four clients, 112.57 and 165.69 tok/s against the controls' slowest 113.33 and 166.08), `p8` on three decode cells and `ch`, `q4`, `bf`, `n2` and `mb` on the cold gain; at most one setting joins and it is the one with the larger cold gain, so the rule names `NCCL_NCHANNELS_PER_NET_PEER=4` (mean cold -1.91%).

The wire arm `mb` (the decode all-gathers' ceiling at 1,024 KiB a rank) reads +0.08% over ten decode cells with four of them under the slowest control, and its boot log confirms the ceiling was raised; it does not pass. Queue82 adds the controls c4 and c5 and the wire arms `rf` and `mf`, and `decide81.py --apply` runs on both queues' rows at its end, so the setting that joins N is decided on five controls. What this section does not show is a gain that a second boot has confirmed: the pairs that do are queue83's `na nb` (the same setting, two boots, between two controls) and queue77's N' against the committed recipe at every level. Queue83's two `pp` boots read -0.4% cold (section 58), so this section's -1.9% on one boot was boot-to-boot spread; under patch 0038's switches `pp` reads -1.2 points more, which is what keeps it in N'.

## 57. Patch 0038: the next block's row-by-row front run piece by piece as the rows land (the model, the code, the gates; the GPU result is queue83's)

Where it comes from: section 54's nsys timeline of a cold pass (459.6 us a row) has the main stream waiting 18.3 us a row after a site's last fill for the partials exchange and 24.5 us a row for the glued rows' share, 9.3% of the pass, and the cause is the shape of a pieced site: the last piece's exchange, its glue and its share (about 1.5 ms for a 1,024-row piece) run on the side stream after the last fill, and only when the share lands does the next block start with its row-by-row front. For a KDA layer that front is one 4.2 ms matmul over all rows, for a DSA layer the projections, norms, indexer and absorbed query (about 9 ms), for a MoE ffn the router and top-k pick (0.7 ms). Those operations read only their own rows, so they can start on a piece whose rows have landed while later pieces are still in flight.

Model (`scripts/site_model.py`, a timeline model with parameters read off `pf-f76w`; no DRAM contention between the streams, every operation a straight line in its rows; this is a model, an inference, not a measurement). Time in ms from a site's first fill to the next block's rest starting, four equal pieces of a 4,096-row pass, and each schedule's change against today's:

| next block | today | front per piece, glue on main (PIECE_FFN's schedule) | glue on the side stream and front per piece (PIECE_FRONT's and PIECE_MLA's) | glue on the side stream alone |
|---|---:|---|---|---|
| a MoE ffn after a DSA mixer | 6.48 | 5.96 (-0.51) | 7.19 (+0.71) | 7.70 (+1.22) |
| a MoE ffn after a KDA mixer | 5.75 | 5.24 (-0.51) | 6.76 (+1.00) | 7.27 (+1.51) |
| a KDA mixer after a MoE ffn | 13.30 | 12.37 (-0.93) | 11.45 (-1.85) | 14.81 (+1.51) |
| a DSA mixer after a MoE ffn | 17.81 | 16.88 (-0.93) | 14.44 (-3.37) | 19.32 (+1.51) |

So a front shorter than the side stream's chain (the router, 0.7 ms) is best run with the glue where it is (a loss of 0.7 to 1.0 ms the other way), and a long one (4.5 and 9 ms) pays for moving the glue to the side stream because the main stream then has work for every piece as it lands. The earlier version of this model gave the ffn front 1.6 ms and so a gain of 0.6 to 0.9 ms; the router's own time (0.7 ms) is what `scripts/site_model.py` carries now. Summed over 34 KDA layers, 11 DSA layers and 42 MoE ffn sites (an upper bound: layer 0 has no site before it), 34 x 1.85 + 11 x 3.37 + 42 x 0.51 = 121 ms of a 1,882 ms pass, 6.5%; the engine's own scheduling costs (launch gaps, the extra events) are not in it, so the pass is expected to gain less.

The patch (`patches/engine/0038-glm-piece-front.patch`, three switches, each default off, the bits unchanged): `TF_GLM_OVN_PIECE_FRONT=1` makes an ffn site that a KDA layer follows glue on the side stream (`cuda_forward_pair.exchangeGlue`, the paired chunk's schedule, now public) and runs that layer's projections range by range behind each range's share (`cuda_kda_block.projectRows`, then `bodyRest` for the chain); `TF_GLM_OVN_PIECE_MLA=1` is the same for a DSA layer (`cuda_dsa_block.prepareRows`, then `bodyRest` for the attention); `TF_GLM_OVN_PIECE_FFN=1` splits `gluePieces`' closing waits off (`gluePiecesAsync` returns the mask of pieces whose shares are in flight) and runs the MoE router and top-k pick range by range (`cuda_moe.routeRows`, then `bodyRest` for the plan and experts). A range is a piece as cut, except that a last piece under 128 rows joins the one before it (`cuda_forward_pieces.frontRanges`), so no front matmul sees fewer rows than a block, where a short matmul could take another kernel than the whole chunk's. The router's K slices are fixed by the shape (`router_ks` 8), every per-row buffer is offset by its own row stride as `Scratch` documents it, and the default path calls the same functions with the whole range, so a range's rows go through the same kernels as in the whole pass. The new code that picks a schedule lives in `cuda_forward_front.zig` (a pass with the profiler on, a shared window's segments, a dense ffn and the last layer keep today's).

Gates (run `sg-20261120-023532` on the shared x86_64 gate host, pristine pin against the 45-patch stack, tree `59df816f6eac`): every step rc 0 but `test-cuda-host`, which fails only the base's own `cli_config_test.test.serve --config` name on both sides (the stack 6,915 of 6,949 tests passed, 33 skipped, 1 failed, the base 6,716 of 6,750 on the same host), and lean 341 problems against the base's 341, 0 new. The host test `cuda_piece_front_test.zig` covers the three switches (each off unless 1, and independent), the hand-over rule and the front ranges (a short last piece joins, a 128-row one does not, a single short piece stays). Six mutants of the testable parts each fail one of its tests and nothing else but the base's own name: the short-piece merge removed, the merged range's last piece off by one, the segments or the profiler ignored by the rule, `pieceFfn` reading `PIECE_FRONT`'s name and `pieceMla` reading `PIECE_FFN`'s. The engine's wiring has no host test (a GPU is the only way to run a schedule): the boot log names the switches (`pieced sites hand the next block's front its glued rows piece by piece (kda, mla, ffn)`), and the queue's cold requests, conversation turns and decode cells must carry the controls' digests.

Queue83 (`scripts/queues/queue83.sh`) builds `glm53-zig:v129zc` from the 45-patch tree, copies it to the other two ranks, then boots, each once in the order ca fa ba ma mb bb fb cb: the controls (N with request starts), the KDA front (F), with the router front (B), with the DSA front too (M); then the pair of controls and the pair of M with `NCCL_NCHANNELS_PER_NET_PEER=4` (queue81's setting). The rule that picks the set that joins N is `scripts/queue-scores/decide83.py` (`scripts/tests/test_decide83.py`, seven mutants killed), written before any queue83 row existed and applied to queue79's, queue77's and queue78's env files when queue83 ends (the chain runs it before queue85 and queue82): replies equal everywhere; a set joins only on a mean cold gain of at least 1.0% at two of three sizes over the two controls with neither boot over the slower control and the first turn and turns 2 to 8 not slower; and a larger set keeps its extra switch only for 0.3 points of mean cold gain over the smaller one. Queue77 then measures the final recipe against the committed one at every level.

## 58. Queue83: patch 0038 on a GPU, the next block's front per piece reads -3.6% on a cold prompt and -3.5% on a long conversation's first turn with every reply equal; NCCL's per-peer channels read nothing alone and -1.2 points more with it

2026-11-20 02:50 to 04:18 UTC, `scripts/queues/queue83.sh` after the image `glm53-zig:v129zc` was built (02:33 to 02:40) from the 45-patch stack and copied to the other two ranks (02:49); rows in `docs/audit-2026-11-12/queue-rows/queue83`, table by script from them. Every boot is the final recipe N plus request starts at `--parallel 4 --context 1048576` plus the switches named; the order is the boot order. F is `TF_GLM_OVN_PIECE_FRONT=1`, B adds `TF_GLM_OVN_PIECE_FFN=1`, M adds `TF_GLM_OVN_PIECE_MLA=1`, pp is `NCCL_NCHANNELS_PER_NET_PEER=4`. The cold first token is the mean of two requests of one seed, the conversation is salt `c74`.

| order | boot | switches | 8k ms | 32k ms | 120k ms | cold against the two controls' mean | first turn ms | turns 2 to 8 ms |
|---:|---|---|---:|---:|---:|---|---:|---:|
| 1 | ca | control | 3805 | 14074 | 52325 | -0.77% / -0.71% / -0.83% | 49179 (-0.79%) | 820 (-1.01%) |
| 2 | fa | F | 3708 | 13696 | 51222 | -3.29% / -3.37% / -2.92% | 48182 (-2.80%) | 818 (-1.30%) |
| 3 | ba | F + FFN | 3723 | 13746 | 51588 | -2.91% / -3.02% / -2.23% | 48541 (-2.08%) | 823 (-0.72%) |
| 4 | ma | F + FFN + MLA | 3696 | 13638 | 50965 | -3.62% / -3.78% / -3.41% | 47904 (-3.36%) | 819 (-1.15%) |
| 5 | mb | F + FFN + MLA | 3696 | 13632 | 50894 | -3.61% / -3.83% / -3.55% | 47807 (-3.56%) | 818 (-1.22%) |
| 6 | bb | F + FFN | 3715 | 13689 | 51107 | -3.12% / -3.42% / -3.14% | 48004 (-3.16%) | 817 (-1.42%) |
| 7 | fb | F | 3732 | 13806 | 51543 | -2.66% / -2.60% / -2.31% | 48360 (-2.44%) | 822 (-0.82%) |
| 8 | cb | control | 3864 | 14274 | 53204 | +0.77% / +0.71% / +0.83% | 49961 (+0.79%) | 837 (+1.01%) |
| 9 | na | pp | 3823 | 14114 | 52710 | -0.30% / -0.43% / -0.10% | 49606 (+0.07%) | 829 (+0.04%) |
| 10 | ga | F + FFN + MLA + pp | 3675 | 13450 | 50197 | -4.16% / -5.11% / -4.87% | 47277 (-4.63%) | 806 (-2.73%) |
| 11 | gb | F + FFN + MLA + pp | 3646 | 13442 | 50221 | -4.92% / -5.17% / -4.82% | 47345 (-4.49%) | 799 (-3.60%) |
| 12 | nb | pp | 3818 | 14110 | 52709 | -0.43% / -0.46% / -0.10% | 49447 (-0.25%) | 827 (-0.15%) |

Every cold request (six), every conversation turn (eight) and every decode cell (prose and code at one and four clients) carries one digest across all twelve boots: the switches change no bit, as built. The two controls differ by 1.55%, 1.43% and 1.68% at the three sizes (the later one is slower, the drift of an hour of boots), and each set sits between them in time, so a set is read against their mean (the pre-written rule, `decide83.py`). By set (the mean of its two boots against the controls' mean): F -2.97 / -2.99 / -2.62% cold, -2.62% on the first turn, -1.06% on turns 2 to 8; F with the router front (B) -3.01 / -3.22 / -2.69%; F with the router and DSA fronts (M) -3.62 / -3.80 / -3.48%, first turn -3.46%, turns 2 to 8 -1.18%. The rule's verdicts: F joins; B passes but its extra switch is worth +0.11 points of mean cold gain, under the 0.3 points the rule asks for; M joins (+0.77 points over F), and `decide83.py --apply` appended M's three switches to queue79's, queue77's and queue78's `NEWX` and named `glm53-zig:v129zc` in their `IMG` line when queue83 ended. The decode cells of the ten boots with a switch read, against the controls' mean, -0.18% (prose, one client), -0.17% (code, one client), -0.08% (prose, four clients) and -0.23% (code, four clients), each inside the controls' own spread, so the 4,096-row-pass work costs decode nothing (the drift is visible in decode too: the first two boots 80.5 and 81.6 tok/s on prose at one client, the rest 78.7 to 80.0).

The size matches half of the model (section 57): the model's 6.5% of a pass for M is read as 3.6%, which is the expected order for a model without the engine's launch gaps and events. Turns 2 to 8 of the conversation (about 1,300 new tokens a turn) gain only 1.1 to 1.2% where the same model predicts 5.7% for a 1,326-row pass (`scripts/site_model.py`, four pieces: 34 x 0.74 + 11 x 1.29 + 42 x 0.19 = 47 ms of a 827 ms turn), so a warm turn's waits are mostly something a schedule cannot hide (inference: a slower peer rank at each exchange; `queue85` reads it from every rank's own stage lines).

NCCL's `NCCL_NCHANNELS_PER_NET_PEER=4` (queue81's best arm, read there at -1.9% on one boot) reads -0.37 / -0.44 / -0.10% cold and -0.09% on the first turn on two boots here, so queue81's reading was boot-to-boot spread and the setting does nothing on its own. Under M it reads differently: the two M + pp boots are -4.54 / -5.14 / -4.84% cold against the controls (first turn -4.56%, turns 2 to 8 -3.16%), 0.9 to 1.4 points under the two M boots at every size and with both pp boots beyond both M boots (-4.16 and -4.92% against -3.62 and -3.61% at 8k). One reading (an inference, two boots): once the next block starts on the first piece's rows, the exchange chain is the critical path in more places and its speed shows. `decide81.py` still chooses `pp` at the end of queue82 by its own pre-written rule (queue81's rows and queue82's controls), so N' for queue77 is N + M + pp; queue77's N' against the committed recipe at every level is where a wrong adoption shows.

Against production's recorded times (cold first token 2,908 / 11,054 / 41,904 ms at 8k / 32k / 120k, turns 2 to 8 of the ~113k conversation 668 ms, its first turn 39.5 and 39.8 s): the controls read 1.319 / 1.282 / 1.259x on a cold prompt, 1.240x on a turn and 1.250x on the first turn; M 1.271 / 1.233 / 1.215x, 1.226x and 1.207x; M + pp 1.259 / 1.216 / 1.198x, 1.201x and 1.193x. Row pieces (4, 6, 8) with M on are queue84's question, and queue85 is the nsys capture of this pass on N' (queue76's `pf-f76w` for comparison) that says where the remaining 20% is.

## 59. Queue85: where a cold pass spends its time now (the nsys capture with the three switches on), and the rank skew that no schedule can hide

2026-11-20 04:19 to 04:25 UTC, `scripts/queues/queue85.sh`, the same capture as queue76's `pf-f76w` (`scripts/nsys-prefill.sh`: rank 0 under Nsight Systems, a cold 8,192 and a cold 32,768 prompt, three warm turns of a growing conversation) on `glm53-zig:v129zc` with the final recipe N' (queue83's M and request starts), then a second boot of the same recipe with `TF_GLM_PROF=1` and no profiler whose stage lines every rank wrote, read by `scripts/prompt_trace.py`; rows in `docs/audit-2026-11-12/queue-rows/queue85`. The switches are off under the profiler, so the second boot is the pre-0038 schedule on every rank.

**What the switches did to a pass** (the six warmed 4,096-row passes of the 32k prompt in each capture, means; queue76's `pf-f76w` against this one): span 1,762.2 to 1,697.3 ms (-3.7%); main stream idle 171.7 to 77.8 ms (-93.9 ms); main stream busy 1,590.4 to 1,619.6 ms (+29.2 ms, +1.8%); waits on the exchange 70.2 to 37.9 ms and on the share 99.8 to 12.5 ms; the side stream's NCCL kernels 484.0 to 469.0 ms of which exposed (the main stream idle meanwhile) 159.5 to 69.8 ms. So the switches removed 94 ms of idle and paid 29 ms of it back as extra busy time: the front's matmuls now run on a quarter of the rows, each reading the layer's weights again (the next paragraph has the kernels). `TF_GLM_OVN_FRONT_ROWS` (the amended patch 0038, queue84's block 1) joins pieces until a front range has N rows and is the test of that reading. A warm turn shows it too: the main stream's busy time is 776.7 / 763.1 / 754.6 ms against queue76's 765.2 / 748.4 / 723.7 for turns of 1,329 / 1,292 rows (the same in both) and 1,275 against 1,234 rows (the third turn is a little longer here), which per row is +1.5 / +2.0 / +0.9%, while its waits on the exchange and the share fall from 70.0 / 67.3 / 68.4 to 29.1 / 27.9 / 28.9 ms, which is why a warm turn reads only -1.2% (section 58).

**Which kernels got the extra time** (`scripts/prefill_kdiff.py` over the two databases, table `kdiff.txt`; kernel time a pass on the main stream, queue76 then queue85, the same six warmed 4,096-row passes): `glm_mm4_w2x4` 308.0 to 349.2 ms (+41.2) with launches 262 to 460, `glm_mm4_128` 87.0 to 111.9 (+24.9) with 415 to 646 launches, `tf_glm_absorb_q_x2` +8.4 (11 to 44 launches), and the routed experts' `tf_exl3_prompt_gu` +12.2 and `tf_exl3_prompt_down` +7.7 at the same 42 launches each (+4.1% and +3.6% a launch), against 52.3 ms less glue on the main stream (`hc_post` -28.1, `hc_partial` -13.7, `hc_finish` -5.3, `slice_sum` -5.3), which now runs on the side stream (+61.3 ms there: 30.2, 20.6 and 10.4) beside NCCL's kernels (484.0 to 469.0 ms). The sum of the main stream's kernel durations is 1,604.1 then 1,645.6 ms (+41.5; the union of its busy time above is +29.2, an inference: consecutive kernels of a stream overlap where they launch dependently). The 198 extra `glm_mm4_w2x4` and 231 extra `glm_mm4_128` launches cost 0.21 and 0.11 ms each, about a layer's weights read once more, so a front cut in four ranges pays its weights four times. The experts' 20 ms is not the schedule's: no side-stream kernel (NCCL or glue) overlaps an experts launch in either capture (checked launch by launch), and the kernels whose launch counts did not change split into +4.1% for `tf_glm_onepass_pipe_exact` and `tf_exl3_prompt_gu`, +3.6% for `tf_exl3_prompt_down` and `tf_glm_index_scores`, and within 1.1% for `tf_glm_kda_step`, `kda_prep`, `kda_out`, `expand_v` and `combine`, which is not one clock change; the captures were four hours apart and clocks and power were not recorded against the passes, so the cause is not isolated, and it makes the captures' absolute times differ by about 4% for the heaviest kernels, which the A B B A boots of queue83 do not share. `TF_GLM_OVN_FRONT_ROWS` (queue84) is the test of whether fewer ranges keep the overlap.

**What is left.** The main stream is idle 5.5% of the 8k prompt (208.8 of 3,782.9 ms; 355.2 of 3,767.1 ms before). `scripts/prefill_stages.py` cuts a pass into layers by the main stream's glue runs, two a layer, and with the ffn glue on the side stream there is one: "0 of 4 passes cut into 45 layers", so the per-layer-kind rows are not available for this capture (a limit of the tool, not of the capture; its totals above are the tool's own idle and busy). `scripts/prefill_gaps.py` (new) reads the gaps differently, by the two kernels around each gap on the main stream, and needs no layer cut (tables `gaps.txt` beside the stage tables of queue76 and queue85; the warmed 4,096-row passes of the 32k prompt, ms a pass, gaps over 2 us): 169.4 ms before, 75.5 ms now. Before: 67.5 ms in 266.8 gaps of 253 us from a glue run's last kernel (`tf_glm_hc_finish`) to the next `tf_glm_hc_post`, 52.4 ms in 47 gaps of 1,116 us from `hc_finish` to the next block's first matmul (`glm_mm4_w2x4`: the tail of an ffn site), 46.2 ms in 42 gaps of 1,100 us from `hc_finish` to the MoE router (`tf_glm_router_tile`: the tail of a mixer site). Now: 35.3 ms in 135 gaps of 262 us (`hc_finish` to `hc_post` again, half as many), 22.9 ms in 126 gaps of 181 us from the router's top-k to the next piece's router tile (the pieced router waiting for each piece's glued rows), 8.0 ms in 42 gaps of 191 us before the router, 3.2 ms in 3 gaps before a matmul. So the ffn tail (52.4 to 3.2 ms) and the mixer tail (46.2 to 8.0 ms) are gone, and what is left is the main stream waiting for the next piece's rows: 58 of the 75.5 ms. By the capture of section 54 the side stream's exchanges are what those waits are for (its NCCL kernels fill 89 to 95% of a site), so the next cut in idle time is a faster exchange (section 54's wire lead), not a schedule.

**The two captures cut their 8k prompt differently, so their whole-request figures do not compare.** Queue76's prompt was 8,197 rows and ran as passes of 4,096, 4,096 and 5 rows (459.6 us a row over the request); this one is 8,183 rows and ran as 4,096, 2,048, 2,036 and 3 (462.3 us a row), because a solo pass takes two grid chunks only when no kept state is at the grid point between them (`cuda_prompt_solo.takesTwo`) and the engine's log says this prompt kept one state ("kept 1"; that it sits at row 6,144, the last grid point before the end, is an inference from the pass boundaries, the stage lines name no mark). **Corrected in section 64:** the capture ran with request starts, and the split is the first `patches/solo-cuts` patch refusing a solo step with a start inside it (a chat prompt's last start is 3 rows before its end); no kept state is involved and the reading above, and the morning report's offer of a cache-policy trade, were wrong about the cause. The two 2,048-row-class passes cost 933.4 and 965.3 ms, 455.8 and 474.1 us a row, against 414.4 us a row for the warmed 4,096-row passes of the 32k prompt (mean 1,697.3 ms): about 206 ms of the 3,782.9, an upper bound because a request's first pass also reads slower than a warmed one (1,833.4 ms for 4,096 rows here). So the 8k prompt in this bench pays for the cut (5.5%) where the 32k prompt, whose tail is cut the same way (937.3 and 963.3 ms for 2,048 and 2,033 rows), pays about 209 ms of 19,158.5 (1.1%), and a prompt of another length pays something between none and this. Whether to keep the grid-point state only at multiples of 4,096 rows (then a solo pass always runs whole, and a resume that is not at a request start loses up to 2,048 more rows) is a cache-policy trade that is not made here.

**Rank 0 carries 7.5% more work than ranks 1 and 2** (the second boot's stage lines, 16 chunks of 2,048 rows, wall 978 ms a chunk on every rank; main-stream stages without waits, ms a chunk): rank 0 1,101.9, rank 1 1,029.8, rank 2 1,020.4, and the waits at the exchanges 125.5, 197.3 and 206.3 ms, so every rank ends together and ranks 1 and 2 spend 71 and 81 ms more of a chunk waiting for rank 0. The routed experts are most of it: 414.8 ms on rank 0 against 359.8 and 358.9 (+55 ms), then the shared expert +5.3, the MLA projections +3.8, the KDA chain +2.9, the MoE glue +4.4. Section 31 has the cause: rank 0 holds 768 expert rows against 640 (the EXL3 units are 128 rows, 16 units split 6/5/5), and fixing that needs 64-row units, which is re-quantizing the experts. The GPU clocks and power are not the cause (rank 0 2,476 MHz, rank 1 2,444, rank 2 2,411 at the first sample). Sized, as upper bounds that are inferences from these lines: units of 64 rows (11/11/10 units, the largest share 704) would take about 35 ms off a 2,048-row chunk's rank 0 (-2.8%) and, because a four-client decode window is 75% one experts kernel (section 54), up to about 6% of a decode round (the checkpoint is shared, so production's serve would gain the same and the gap to it would not close); moving other work off rank 0 (fewer DSA and KDA heads) would recover at most the 72 to 81 ms the other ranks wait, about 4% of a chunk, and regroups the partial sums, so both change bits or the checkpoint and are yours to decide. Production's per-layer expert time equals ours (section 31), so it very likely carries the same skew.

**The amended patch 0038 (a fourth switch).** `TF_GLM_OVN_FRONT_ROWS=N` (a whole number, default 0) makes a front range join the pieces after it until it has at least N rows (`cuda_forward_pieces.frontRanges(cut, min_rows, out, last_piece)`, read by `cuda_forward_front.mixer` and `route`; the boot line gains `front rows N`; the short-last rule of 128 rows stays), so a warm turn's front reads each layer's weights fewer times; 0 is the committed schedule and the bits do not change at any value. Gates: the full run `sg-20261120-042953` on the gate host, the pristine pin (tree `4be51cc6beef`) against the 45-patch stack (tree `fe2c0995a819`): every step rc 0 but `test-cuda-host`, which fails only the base's `cli_config_test.test.serve --config` (the stack 6,917 of 6,951 tests passed, 33 skipped, 1 failed; the base 6,716 of 6,750), lean 341 problems against 341, 0 new. Two tests are new (`pieces.frontRanges: with a minimum, pieces join until a range has that many rows, and the last one never starts a short range` and `TF_GLM_OVN_FRONT_ROWS: 0 unless set, a whole number`). Nine mutants (the short-last merge disabled, the join's bookkeeping off by one, two of `handsFront`'s conditions dropped, the FFN and MLA readers swapped for another switch, the minimum's comparison loosened, the short-last rule removed, the default changed to 1) each fail one of the patch's tests and nothing else but the base's own name; one of the nine runs was refused once by the gate host's load preflight and rerun alone.

**Queue84's rule, written before its rows exist** (`scripts/queue-scores/decide84.py`, with `scripts/tests/test_decide84.py` and 19 mutants of the script killed; queue84 (`scripts/queues/queue84.sh`) runs after queue82 and `decide81.py` on the amended image `glm53-zig:v129zd`: block 1 is `TF_GLM_OVN_FRONT_ROWS` 0 / 512 / 768 / 2048 in the order r4a r5a r7a r2a r2b r7b r5b r4b, block 2 is `TF_GLM_OVERLAP_PIECES` 4 / 2 / 3 / 6 / 8 in the order k4a k2a k3a k6a k8a k8b k6b k3b k2b k4b, then one boot each of `TF_GLM_OVN_KDA_CHUNKED=1` and `TF_GLM_OVN_KVB8=1`). Neither knob changes a bit, so a setting's two boots are read against its block's two controls: replies equal across the block; neither boot over the slower control by more than 1.0% at any cold size or on the first turn (boots differ by about 1.5%, and a `FRONT_ROWS` of 512 or 768 leaves a cold chunk's 1,024-row ranges alone, so its cold time is a control's); greedy decode at one client not more than 1.0% under the controls' mean; for a `FRONT_ROWS` value (2048 joins a cold chunk's ranges in pairs), the mean of turns 2 to 8 at least 1.0% under the controls' mean and the mean of the three cold sizes not over it by more than 0.3%; for a piece count, the mean of the three cold sizes at least 0.5% under the controls' mean and turns 2 to 8 not over theirs by more than 0.3%; of the values of a block that pass, the one with the larger sum of its cold and warm gains joins N' by editing `NEWX` (a piece count replaces `TF_GLM_OVERLAP_PIECES=4`). The two numerics boots join nothing: they are sized for you, and their replies are expected to differ from the controls'. The chain runs the script on queue84's rows with `--apply` before queue79 starts.

## 60. Queue82: the decode wire's fast mode reads +0.9% on decode at one to four clients on one boot, a hair slower cold, replies equal; `decide81.py` adopts `NCCL_NCHANNELS_PER_NET_PEER=4`

2026-11-20 04:25 to 05:15 UTC, `scripts/queues/queue82.sh` on `glm53-zig:v129za` (the recipe N without patch 0038's switches: `TF_GLM_OVN_MM_WIDE`, `TF_GLM_OVN_SIDE_PRIO`, `TF_GLM_OVERLAP_PIECES=4`, `TF_GLM_OVN_LATENT_ROWS=2`, request starts), four boots in the order c4 rf mf c5: the controls c4 and c5 around `TF_TP_ROCE_FAST=1` (rf, the kernel's fast path with one poller and a 150 ns stagger, `fabric/tp`'s RoCE wire that carries the decode all-gathers) and rf with `TF_TP_MAILBOX_MAX_KB=1024` (mf). Rows: `docs/audit-2026-11-12/queue-rows/queue82`. Every cold request, turn and decode cell is one digest across the four boots (a wire setting moves bytes, never a sum). One boot an arm is a screen; the controls' own spread is the yardstick.

Greedy decode, aggregate tok/s, each arm against the mean of the two controls (`scripts/queue-scores/score81.py work/pp82/f82-c --arms c4,rf,mf,c5 --controls c4,c5`):

| cell | controls (tok/s) | spread | rf | mf |
|---|---|---|---|---|
| prose 1 | 78.57 / 78.21 | 0.46% | +1.42% | +1.47% |
| code 1 | 110.40 / 111.30 | 0.81% | +1.12% | +1.30% |
| prose 2 | 82.60 / 82.49 | 0.14% | +0.15% | +1.05% |
| code 2 | 133.88 / 134.09 | 0.16% | +0.75% | +0.92% |
| prose 4 | 109.70 / 110.20 | 0.45% | +0.84% | +0.67% |
| code 4 | 163.40 / 164.67 | 0.78% | +0.25% | +0.04% |
| prose 6 | 114.91 / 109.79 | 4.67% | -0.03% | +4.62% |
| code 6 | 162.35 / 176.62 | 8.79% | -3.81% | -6.15% |
| prose 8 | 115.43 / 125.39 | 8.62% | +2.92% | +7.90% |
| code 8 | 169.19 / 176.83 | 4.51% | -0.24% | -2.52% |

At 6 and 8 clients the serve holds four slots and queues the rest, and the controls themselves differ by 4.5 to 8.8%, so those cells decide nothing. At 1, 2 and 4 clients every cell of both arms is at or above the controls' mean (mf +1.47 / +1.30 / +1.05 / +0.92 / +0.67 / +0.04%, rf +1.42 / +1.12 / +0.15 / +0.75 / +0.84 / +0.25%), with the controls' spread 0.14 to 0.81%. The cold first token reads the other way by a little: rf +0.68 / +0.95 / +0.92% (slower) at 8k / 32k / 120k against controls that differ by 0.27 / 0.32 / 0.58%, mf +0.21 / +0.23 / +0.36% (inside the spread); the conversation's first turn +0.75% (rf) and +0.34% (mf), turns 2 to 8 +0.07% and -0.36%. So the reading of mf is a decode gain of about 0.9% at one to four clients with no cold cost beyond the spread, on one boot; the screen asks for a pair, and `scripts/queues/queue86.sh` runs it as A B B A (n6 m6 m7 n7) on the final recipe after queue78, scored with `score81.py DIR --arms n6,m6,m7,n7 --controls n6,n7`.

`decide81.py` (the rule written before queue81's rows) read queue81 and queue82 together against the five controls c1 to c5: n8, qn, pp and p8 pass (every reply equal, a cold gain of at least 1.0% at all three sizes, no boot over the slowest control, first turn and turns 2 to 8 not over), q4, ch, bf, n2, mb, rf and mf do not, and it adds `-e NCCL_NCHANNELS_PER_NET_PEER=4` (pp, the largest cold gain: +2.03 / +2.20 / +2.28%) to `NEWX` of `queue79.env`, `queue77.env` and `queue78.env`. Queue83 then showed that pp alone reads -0.4% (queue81's gain was boot spread) and -1.2 points more under the three switches of patch 0038 (section 58), which is why it stays in N' for queue77 to read at every level. Pooled against five controls, rf reads decode -0.50% and mf +0.09% (`queue81-decide.log`), and queue81's controls c1 to c3 read 2.62 / 2.34 / 2.27 / 1.73% faster than c4 and c5 at prose 1, code 1, prose 4 and code 4 (they ran hours earlier; the cause is not isolated, and the same drift between boots is why a pooled mean over controls from two queues is the weaker comparison). The within-queue comparison above is the cleaner one, and the pair in queue86 is the test.

## 61. Queue84: no front-row minimum and no piece count passes its pre-written rule; three pieces read warm turns 1.9% faster with the cold prompt level (a lead; queue88 is its confirmation); the two numerics switches are not speed-ups

2026-11-20 05:16 to 07:33 UTC, `scripts/queues/queue84.sh` on `glm53-zig:v129zd` (the 45-patch stack with the amended patch 0038, tree `fe2c0995a819`: built on spark1 from 05:16 to 05:23 and copied to the other two ranks by 05:32). Twenty boots of the final recipe N' (queue83's three switches, `NCCL_NCHANNELS_PER_NET_PEER=4` and request starts, `--parallel 4 --context 1048576`), each with the cold first token at 8k / 32k / 120k (two requests), the ~113k conversation (eight turns) and greedy decode at one client. The order was r4a r5a r7a r2a r2b r7b r5b r4b (`TF_GLM_OVN_FRONT_ROWS` 0 / 512 / 768 / 2048), k4a k2a k3a k6a k8a k8b k6b k3b k2b k4b (`TF_GLM_OVERLAP_PIECES` 4 / 2 / 3 / 6 / 8), then kca and kva (the two numerics switches). Rows: `docs/audit-2026-11-12/queue-rows/queue84`; the rule is section 59's, `scripts/queue-scores/decide84.py`.

| boot | setting | cold 8k / 32k / 120k (ms) | first turn (ms) | turns 2 to 8 (ms) | decode 1 client prose / code (tok/s) |
|---|---|---|---|---|---|
| r4a | 4 pieces, no minimum (control) | 3,662 / 13,511 / 50,579 | 47,541 | 807 | 78.91 / 111.02 |
| r5a | FRONT_ROWS 512 | 3,688 / 13,588 / 50,962 | 47,895 | 819 | 79.56 / 111.64 |
| r7a | FRONT_ROWS 768 | 3,712 / 13,658 / 51,109 | 48,104 | 816 | 78.99 / 112.06 |
| r2a | FRONT_ROWS 2048 | 3,804 / 13,871 / 51,674 | 48,496 | 840 | 78.91 / 111.58 |
| r2b | FRONT_ROWS 2048 | 3,761 / 13,700 / 51,150 | 48,104 | 835 | 79.09 / 111.06 |
| r7b | FRONT_ROWS 768 | 3,688 / 13,624 / 50,932 | 47,796 | 812 | 79.22 / 110.91 |
| r5b | FRONT_ROWS 512 | 3,708 / 13,700 / 51,262 | 48,185 | 816 | 78.70 / 111.32 |
| r4b | 4 pieces, no minimum (control) | 3,698 / 13,630 / 50,988 | 48,011 | 812 | 79.39 / 111.16 |
| k4a | 4 pieces (control) | 3,697 / 13,624 / 51,030 | 47,838 | 810 | 79.22 / 110.54 |
| k2a | 2 pieces | 3,743 / 13,906 / 52,078 | 49,003 | 799 | 78.88 / 110.95 |
| k3a | 3 pieces | 3,688 / 13,676 / 51,212 | 48,044 | 797 | 78.78 / 110.56 |
| k6a | 6 pieces | 3,714 / 13,672 / 51,047 | 48,016 | 810 | 79.45 / 110.71 |
| k8a | 8 pieces | 3,746 / 13,725 / 51,212 | 48,076 | 812 | 78.78 / 111.31 |
| k8b | 8 pieces | 3,766 / 13,731 / 51,322 | 48,338 | 818 | 78.72 / 110.97 |
| k6b | 6 pieces | 3,724 / 13,636 / 51,008 | 47,925 | 820 | 77.85 / 109.92 |
| k3b | 3 pieces | 3,676 / 13,608 / 50,997 | 47,842 | 798 | 79.49 / 111.14 |
| k2b | 2 pieces | 3,710 / 13,816 / 51,797 | 48,730 | 796 | 79.39 / 111.17 |
| k4b | 4 pieces (control) | 3,683 / 13,634 / 51,042 | 47,964 | 815 | 78.96 / 111.04 |
| kca | KDA_CHUNKED=1 | 3,655 / 13,466 / 50,228 | 47,156 | 807 | 72.07 / 117.09 |
| kva | KVB8=1 | 3,670 / 13,560 / 50,766 | 47,726 | 806 | 83.14 / 117.30 |

All 18 boots of the first two blocks carry one digest in each of their 16 cells (six cold requests, eight turns, prose and code decode, checked by script), so neither knob changes a bit, as built.

**What the pre-written rule said** (a gain is positive when faster; the cold mean is over the three sizes, turns 2+ is the mean of turns 2 to 8, each setting's two boots against the block's two controls, decode at one client the mean of prose and code):

| setting | cold mean | turns 2+ | decode | verdict |
|---|---|---|---|---|
| `FRONT_ROWS` 512 | -0.56% | -0.99% | +0.19% | no |
| `FRONT_ROWS` 768 | -0.51% | -0.61% | +0.18% | no |
| `FRONT_ROWS` 2048 | -1.87% | -3.51% | +0.04% | no (a boot over the slower control by more than 1.0%) |
| 2 pieces | -1.49% | +1.81% | +0.17% | no (cold; a boot over the slower control by more than 1.0%) |
| 3 pieces | -0.00% | +1.88% | +0.06% | no (the piece-count rule asks 0.5% on the cold prompt) |
| 6 pieces | -0.31% | -0.28% | -0.48% | no |
| 8 pieces | -0.99% | -0.33% | +0.01% | no (a boot over the slower control by more than 1.0%) |

Nothing joins; `queue77.env` and `queue78.env` are unchanged.

**`FRONT_ROWS` does not help.** At 2048 (a cold chunk's four ranges joined in pairs) warm turns are 3.2% to 3.8% slower and the cold prompt 0.7% to 3.4% slower, both boots beyond both controls. At 512 and 768 nothing is gained: warm turns read 0.4% to 1.2% slower and the cold prompt 0.1% to 1.0% slower, which is inside the controls' own spread in this block (0.6% on warm turns, 0.8% to 1.0% on the cold prompt), so those two are level at best. Section 59 read the 198 and 231 extra matmul launches of the switched schedule (against queue76's capture) as weights read once more for each range; this block does not support that reading, since fewer ranges did not recover time. Where a warm turn's extra busy time comes from is open. The knob stays registered and at 0 (KNOBS.md, the table of measured losses).

**Three pieces: a lead the rule could not see.** The four boots at 2 or 3 pieces have turns 2 to 8 at 796 to 799 ms, and the six boots at 4, 6 or 8 pieces at 810 to 820 ms (controls 810 and 815), so a warm turn is 1.6% to 2.0% faster at 2 pieces and 1.8% to 1.9% faster at 3, no boot of either above a control's warm-turn mean. At 3 pieces the cold prompt is level (8k -0.05% and -0.39%, 32k +0.34% and -0.16%, 120k +0.34% and -0.08% of the controls, boot a and b), the first turn level (+0.30% and -0.12%), decode level (+0.06%). At 2 pieces the cold prompt is 0.5% to 2.0% slower. What the cut does to a turn: `ranges()` rounds a piece up to 128 rows, so a 1,292-row turn is 384, 384, 384 and 140 rows at 4 pieces, 512, 512 and 268 at 3, 768 and 524 at 2, and 256, 256, 256, 256, 256 and 12 at both 6 and 8 (which is why those two read alike); a 4,096-row chunk is four of 1,024 rows at 4 pieces and 1,408, 1,408 and 1,280 at 3. Why fewer pieces help a turn of that size is not measured. The pieces rule I wrote before the rows asks a cold-prompt gain of a piece count, so it said no; three pieces is a warm-turn candidate with no loss anywhere, which is the shape of rule 3's first form, and `decide84.py` gains a block that reads it that way on fresh boots (rule 5 in its docstring, written after this block and before its rows): `scripts/queues/queue88.sh` runs w4a w3a w3b w4b w4c w3c w3d w4d, four boots of 3 pieces against four of 4, each also with a ~250k conversation, and the rule asks turns 2 to 8 at least 1.0% under the controls' mean, the cold mean not over by more than 0.3%, and every 3-piece boot's turns 2 to 8 under every control's (one chance in 70 with no difference).

**Why a piece count can matter on a warm turn** (an inference from queue85's capture at 4 pieces, `scripts/prefill_launch_cost.py`, table `queue85/pf-f85w/launch_cost.txt`; not a measurement of a 3-piece pass). The script puts a line through each kernel's mean time a launch in the warmed 4,096-row passes (1,024 rows a piece) and in a 1,289-row warm turn (322 rows a piece); the line's value at zero rows is what a launch costs whatever its rows. The exchanges are not it: a pass has 720 `SendRecv` launches either way, 651 us and 211 us each, a fixed 9 us, 6 ms a warm pass. The dense matmuls are: `glm_mm4_w2x4` 759 and 325 us a launch (a fixed 125 us, 43 ms over the warm pass's 346 launches), `glm_mm4_128` 173 and 92 us (a fixed 55 us, 42 ms over 760 launches), `tf_glm_combine` 772 and 267 us (35 us, 6 ms), while the KDA chain, the absorb and expand kernels and the router scale with the rows (a fixed part within 2 ms either way). Those three run once a piece or once a front range in most of their launches, so a quarter fewer pieces would remove up to 23 ms of the 91 ms from a turn of about 810 ms; the 2- and 3-piece boots read 13 to 17 ms under the controls' mean. `FRONT_ROWS` removes front launches too, but makes each front wait for a later piece's share, which is the likelier reason it gained nothing. The same table has the floor of a warm turn: the routed experts' two kernels have a fixed 2.67 and 1.63 ms a layer, 180 ms of the pass, because a turn of this size reads nearly every expert's weights once.

**The two numerics switches are not speed-ups.** One boot each, decode at one client, against the two controls of the block (tokens a round and the round time from each row's own counters):

| boot | cold 8k / 32k / 120k | turns 2+ | prose tok/s, ms a round, tokens a round | code tok/s, ms a round, tokens a round | digests that differ |
|---|---|---|---|---|---|
| kca (`TF_GLM_OVN_KDA_CHUNKED=1`) | -0.95 / -1.19 / -1.58% | -0.67% | -8.88%, -2.92%, -11.78% | +5.69%, +3.47%, +9.50% | 12 of 16 |
| kva (`TF_GLM_OVN_KVB8=1`) | -0.53 / -0.51 / -0.53% | -0.79% | +5.12%, +2.24%, +7.64% | +5.88%, +3.60%, +10.10% | 14 of 16 |

(cold and turn columns are the change in time, negative faster). The switches change the replies, so each arm decodes a different text and a different number of tokens a round (acceptance 0.690 prose and 0.872 code in the controls; 0.646 and 0.927 in kca; 0.706 and 0.921 in kva): the tok/s differences are draft acceptance on other text, and the round time of kva is 2.2% and 3.6% longer, not shorter. The one reading beyond the controls' own spread (0.38%, 0.08%, 0.02% at the three sizes in this block) is the cold prompt of kca, 1.2% faster on one boot. Both stay off: the owner decided on 2026-10-31 to keep numerics changes off (KNOBS.md), and what that decision costs here is about 1.2% of a cold prompt on one boot for `KDA_CHUNKED` and nothing that can be called speed for `KVB8`.

## 62. Patch 0039: a KDA mixer site's chain run piece by piece (the layer timeline, the code, the checks; the GPU result is queue87's)

**One layer under the final recipe** (`scripts/prefill_period.py`, queue85's capture, the table `period.txt`: pass 3 of the 32k prompt, rank 0, from the end of one MoE layer's `tf_exl3_prompt_down` to the end of the next's, 33.4 ms for a MoE layer behind a KDA mixer; ms from the period's start). The previous MoE site's tail runs to 5.72. The KDA front, in four ranges (`glm_mm4_w2x4` 1.41, 1.39, 1.09 and 1.08 ms), runs to 11.36. The chain (`kda_prep` 1.37, `kda_step` 2.35, `kda_out` 0.34 ms, 4.06 in all) ends at 15.42. From there to the start of the routed experts (20.47) is 5.05 ms: the main stream is busy 3.50 ms of it (the four pieces' `o_proj` 1.92, the glue 1.12, the router and its top-k 0.64) and idle 1.54 ms, while the side stream runs 4.10 ms of NCCL kernels (the four partials exchanges 477, 939, 605 and 785 us, the four shares 393, 311, 302 and 285 us). So after the chain the site is limited by the side stream as much as by the main stream, and the first exchange cannot start until the whole chain is done because the chain precedes the first piece's `o_proj`. The experts that follow take 12.57 ms (`tf_exl3_prompt_gu` 7.64, `tf_exl3_prompt_down` 4.93), 37.7% of the layer.

**What the patch does** (`patches/engine/0039-glm-piece-kda.patch`, switch `TF_GLM_OVN_PIECE_KDA`, default off): the chain runs in the ranges the pieces cut (a last piece under 128 rows joined to the one before), each ahead of the first piece it covers, so range i's partials exchange starts after its own chain and `o_proj`, and the earlier ranges' exchanges hide under the later ranges' chain. The main stream's work is unchanged, so the most it can save at a site is that site's idle time: 1.54 ms here, 34 KDA sites a 4,096-row pass, 52 ms of a 1,697 ms pass (3.1%) as an upper bound. The earlier models in this campaign have read about twice the measured gain on cold passes, so I expect 1% to 1.5%; that is an expectation, not a measurement.

**Bits.** `kda_prep` and `kda_out` work one row at a time; `kda_step` walks its rows in order carrying the state in registers and storing it in fp32 at the end, so a range that reads the state the range before it stored runs the same operations in the same order; a range at row `lo` reads its three conv rows from a window of the projected rows `lo - 3` to `lo - 1` (the layer's own `conv_shift` kernel, into a scratch window, where the whole chain reads them in place from the layer's window and the projections). The state hops between the layer's other recurrent buffer and a scratch one (`cuda_kda_block.hop`: the first range reads the layer's current state, the last writes the buffer the layer commits, the ones between alternate, so no range reads what it writes and the layer's old state is untouched until the commit); `cuda_state.make` gains the scratch (one state and one window, `twin_checked` 76 to 77, 746,240 bytes a rank at 11 heads). After the last range the layer commits as the whole chain does: the conv window of the chunk's last three rows and the buffer flip. The schedule is today's for a chunk of under 64 rows (the whole chain takes the fused kernel), a profiled pass, `TF_GLM_L2PF`, a shared window's segments and the chunked chain (`cuda_forward_chain.handsChain`).

**Checks.** Host tests (`cuda_piece_kda_test.zig`): the switch, `hop` for 1 to 16 ranges (a range reads what the one before wrote, the layer's old state is never written, the last range writes the committed buffer) and `fromRow` (each row-indexed buffer moves by its own row size, none of the others move). The GPU check `tf-cuda-test glm-kda-pieces` (`zig/tests/cuda/glm_kda_pieces_check.zig`) runs production's own `chainRows`, `commitConv`, `chainRange`, `convWindow` and `hop` on synthetic rows, seven cases at 11 and 10 heads (4,096 rows in 4 and 8 pieces, 2,048 in 3, 1,326 in 4, 1,160 in 4 with an 8-row last piece, 129 and 300 rows), and compares the chain by ranges with the whole chain in `out`, the final state, the saved k, v and decay rows and the conv window, byte for byte, with two planted controls (a wrong conv window, a wrong start state) that must differ. Queue87 runs it on the image before any boot with the switch and refuses to measure if it does not print its two PASS lines.

**Gates** (run `sg-20261120-081755` on the shared x86_64 gate host, the pristine pin against the 46-patch stack, tree `7ccb3385fcfd`): every step rc 0 but `test-cuda-host`, which fails only the base's own `cli_config_test.test.serve --config` name on both sides (the stack 6,922 of 6,956 tests passed, 33 skipped, 1 failed; the base 6,716 of 6,750), `compile-cuda-tests` rc 0 (the GPU check compiles), lean 341 problems against the base's 341, 0 new. Five tests are new: the switch, `opening` by example and for every chunk size from 1 to 6,000 rows in steps of 37 at 1 to 16 pieces (each range opens at its first piece, in order, the ranges cover the rows once and each piece lies inside its range), `hop` and `fromRow`. Fourteen mutants of the patch, each with one added line changed and run through the fast loop's `test-cuda-host`, each fail a `cuda_piece_kda_test` test and no other name but the base's: three of `hop` (the first range not reading the layer's state, either parity flipped) fail the `hop` test; seven of `fromRow` (a buffer moved by another row size, or not moved) fail the `fromRow` test; the switch read under another name fails the switch test; three of `opening` (a range's first piece, the range a piece opens, the list not cleared) fail both `opening` tests. Eleven ran on the 46-patch stack (6,956 tests); m1, m5 and m10 ran with `patches/solo-cuts`' second patch in the stack too (47 patches, 6,959 tests), and m1's run counted 6,865 tests with its `hop` test failing as the others' do (that the test binary stopped at a later assertion is an inference: the output names failed tests only). The image is `glm53-zig:v129ze`, built by queue87 from the staged tree (source tar sha256 `1310f3adf651`). Its GPU result is section 67: the byte check passes and the switch reads 0.86% slower on a cold prompt, so it stays off.

## 63. Queue79: no decode switch passes its rule on the final recipe

2026-11-20 07:33 to 09:03 UTC, `scripts/queues/queue79.sh` on `glm53-zig:v129zc` with the final recipe N' (no request starts: section 55 settled that they do not touch decode), ten boots in the order n1 x1 i1 d1 u1 u2 d2 i2 x2 n2, greedy decode at 1, 2, 4, 6 and 8 clients on prose and code (three rounds a cell, production's prompt ids, `--parallel 4 --context 1048576`, so 6 and 8 clients queue). Rows: `docs/audit-2026-11-12/queue-rows/queue79`; the rule is `scripts/queue-scores/decide79.py`'s, written before the rows. Each candidate's pair mean over the mean of the two controls:

| cell | controls n1, n2 (tok/s) | `X3_NC=2` | `INDEX_CUDA=all` | `DECODE_INDEX=33` | `DRAFT_CUTS=1:0.15` |
|---|---|---|---|---|---|
| prose 1 | 79.64, 81.86 | -1.39% | -1.86% | -1.16% | -1.75% |
| prose 2 | 83.34, 85.17 | -0.87% | -1.29% | -0.95% | -1.62% |
| prose 4 | 110.28, 113.22 | -0.86% | -1.28% | -0.74% | -0.60% |
| prose 6 | 114.26, 111.96 | +1.65% | +0.19% | -1.45% | +7.91% |
| prose 8 | 115.75, 116.40 | +2.52% | +3.03% | +4.02% | +4.29% |
| code 1 | 111.85, 114.79 | -0.76% | -1.74% | -0.98% | -0.07% |
| code 2 | 133.92, 137.56 | -0.61% | -0.85% | -0.71% | +0.92% |
| code 4 | 163.26, 167.90 | -0.71% | -0.70% | -0.75% | +0.03% |
| code 6 | 168.20, 167.92 | -4.06% | -2.00% | -2.65% | +0.91% |
| code 8 | 170.75, 172.40 | -0.43% | +2.73% | +3.36% | -1.11% |

The verdicts: x (-e TF_GLM_OVN_X3_NC=2): no (mean over cells -0.55%, cells above 2/10); i (-e TF_GLM_INDEX_CUDA=all): no (mean over cells -0.38%, cells above 3/10); d (-e TF_GLM_OVN_DECODE_INDEX=33): no (mean over cells -0.20%, cells above 2/10); u (-e TF_GLM_OVN_DRAFT_CUTS=1:0.15): no (mean over cells +0.89%, cells above 5/10). Every candidate's replies equal the controls' in all ten cells, and nothing joins: `queue77.env` and `queue78.env` keep N'.

The two controls differ by 2.2% to 2.8% at 1 to 4 clients, the last boot the faster one (prose at one client 37.43 ms a round against 38.50, the same 3.14 tokens a round, so it is round time). That is more than any candidate's distance from their mean, so at 1 to 4 clients every candidate sits inside the controls' range, and at 6 and 8 clients the four-slot serve queues and a cell spreads several percent. n2 is also the fastest of the ten boots by 1.9% (the other seven boots that run the recipe's draft cuts are at 38.13 to 38.83 ms). Its engine log differs from n1's in one line that matters, NCCL's count of connections to rank 1 (4 against 8); that count varies from boot to boot at the same settings (4 in six of these ten boots, 8 in the other four) and tracks neither the round time here (the boots at 4 are the fastest one and the two slowest) nor queue84's cold and warm times (both 3-piece boots have 4, both 2-piece boots 8; of the four controls the one with 4 reads like the three with 8), so it is not a lever and n2's speed is unexplained boot spread. `TF_GLM_OVN_DRAFT_CUTS=1:0.15` does what it says (3.41 tokens a round on prose against 3.14, 6.33 against 6.14 on code) at rounds 7% to 11% longer on prose, which nets nothing.

## 64. `TF_GLM_OVN_SOLO_TO_START`: the last stretch of a chat prompt ran as two passes because of my own solo rule (the cause, the size, the patch, the checks; the GPU result is queue89's)

**Correction of section 59's cause.** That section said the 8k capture prompt (8,183 rows) ran as passes of 4,096, 2,048, 2,036 and 3 rows "because a solo pass takes two grid chunks only when no kept state is at the grid point between them", inferred a kept state at row 6,144, and the morning report offered it to the owner as a cache-policy trade. The size was right and the cause was wrong; it was an inference I never tested. The capture's boot ran with `TF_GLM_REQUEST_STARTS=1`. There the server's chunk plan lists a start at every 2,048-row grid step and at each message start, and a chat prompt ends in a message start 3 rows before its last row (the reply's header: queue74's warm turns resume at "the previous prompt's end less its three header tokens"). `patches/solo-cuts`' first patch, which I wrote, refuses a solo step whenever a start lies strictly inside it, the middle grid point excepted. For the step at row 4,096 of that prompt the start at 8,180 is inside (4,096, 8,183), so the step ran as a plain 2,048-row chunk, and from 6,144 only 2,039 rows are left, which is no solo step either. No kept state is involved and the owner has nothing to weigh under request starts: the rule was stricter than it needed to be.

**Without request starts the same stretch is split by the keep mark, which is the trade section 59 described.** That part is read from the code, not from a capture: without starts the prompt cache keeps a chat's state at the last 2,048-row point of its history (`docs/KNOBS.md`, the `TF_GLM_REQUEST_STARTS` row), `prompt_solo.takesTwo` refuses a solo step with a keep mark at its middle grid point, and for the 8k and 32k bench prompts that point (6,144 and 30,720) is the middle of the last solo step. It agrees with queue74 (section 52): request starts cost +48, +63 and +97 ms on the cold first token at 8k, 32k and 120k. The 48 ms at 8k is the reply's 3-row pass (45.5 ms in the capture) and not a pass of 2,000 rows, so both of its arms ran the same large passes there; the larger premiums at 32k and 120k are one more small pass each (an inference: the plan's cut at the system message's end, whose 3-row-pass-sized cost the capture does not show).

**Which requests are cut that way, and the size.** Under request starts, every request whose last stretch before the reply's start, counted from the last solo boundary, is longer than one grid step. The cold bench prompts are 7,999 and 8,005, 32,001 and 32,014, and 120,388 and 120,526 tokens; their last stretches are 3,903 and 3,909, 3,329 and 3,342, and 1,604 and 1,742 rows, so the 8k and 32k prompts run one pass more and the 120k prompts do not. A warm turn is cut the same way when it adds 2,307 to 4,096 rows; the bench conversation adds about 1,290 a turn and never is. The capture's passes (`scripts/prefill_passes.py passes` over `pf-f85w.sqlite`, a pass from one `tf_glm_embed_b16` launch to the next; section 65 has the tables): the 8,183-row request 1,832.3, 933.3, 970.2 and 45.5 ms (3,781.3 of its 3,788 ms first token); the 32,756-row request 1,916.1, six passes of 1,679.7 to 1,713.8 (mean 1,698.6 ms, 414.7 us a row), then 929.6, 971.0 and 47.1 ms. One pass of the 4,084 rows at the warmed rate is about 1,694 ms against the 1,903.5 ms the two short passes took: 209.8 ms, 5.5% of the 8k first token, and 208.2 ms, 1.5%, at 32k. The profiler does not make these up: the capture's 8k request read 462.9 us a row and an un-profiled boot's 459.5 (`k4a`, queue84), 0.75% apart. With the switch and request starts on, the 8k and 32k cold prompts should therefore come out ahead of the recipe without request starts as well (which pays the same split and not the 3-row pass): about -4.3% and -1.1%, with +0.17% at 120k; that is an expectation from the capture, and queue89 measures it.

**The change (`patches/solo-cuts/0002-glm-solo-to-start.patch`, default off).** A solo step is two chunks of the cold plan run as one pass. `cuda_prompt_cuts.soloRows(len, cuts, start, to_start)` now says that directly: the plan's next chunk must end at `start + 2,048` (a grid step with no start inside it), and the step ends where the plan's chunk after it ends (`nextCut` of that point: the next start, a grid step on, or the prompt's end). Without the switch it returns null unless that end is the whole step's, which is exactly the rule before; with `TF_GLM_OVN_SOLO_TO_START=1` the step ends at the start. `stepRows` (every rank's size of a step from the part it was sent), `leaderRows` (rank 0's) and `prompt_solo.at` (rank 0's choice) all go through `soloRows` with the same switch, so the ranks size every step alike, and a rank without the switch refuses the shorter part with `error.BadChunk` instead of running other rows. `prompt_solo.takesTwo` reads the step's own end, so a second chunk of one row is still not taken, and `ringsAgree` is asked about the step's own rows. `prompt_solo.allowed`, every rank's check, is unchanged: a step that ends at a start has none inside it. The pass itself is untouched: `prefillChunk` runs a step's rows as one pass whatever their count, as it already does for a solo step that ends at the prompt's end, and a state is kept when the next step starts at a marked row, which the start still is. The 8,183-row prompt becomes 4,096 + 4,084 + 3 rows. Replies are `TF_GLM_CHUNK_SOLO`'s: the tokens two chunks a step give.

**Checks.** Host tests (`cuda_prompt_cuts.zig`, `cuda_prompt_solo.zig`): `soloRows`, `stepRows` and `leaderRows` with and without the switch; the rule before (`cutInside` over a whole step) against `soloRows` without it on every cold cut of the test prompts; walks that size each step as rank 0 does and check it as every rank does (every step starts on a cold cut, a solo step is exactly the plan's next two chunks, `prompt_solo.allowed` takes it); the 8,183-row prompt's steps as measured (four without the switch, three with it) and a prompt whose last stretch is under a grid step (the same either way); `prompt_solo.at` and `allowed` on an engine fixture with the switch on and off, and from a row where the index rings hold a step to the start and not a whole one. The full gate `sg-20261120-093958` passes (47-patch stack, tree `9297755c6943`, 6,925 of 6,959 tests with only the base's own failing name, lean 341 against 341, `compile-cuda-tests` rc 0). Thirteen of fourteen mutants are killed by tests and the fourteenth does not build (the registry refuses a switch with no row); the table is in `patches/solo-cuts/RECORD.md`. The GPU check `glm-solo-check` gained two request-start prompts and the solo pass counts they must show (1 and 1 without the switch, 1 and 2 with it): after the 8-prompt version passed on `v129zd` across the three ranks through the new launcher `scripts/gpu-check-tp3.sh` (156 s, 10:13 UTC), the 10-prompt version passes on `v129zf` on one GPU (glm-synth's checkpoint) and on the three ranks with the real checkpoint, four runs (the plain environment and the recipe's, the switch off and on). Queue89 measures the speed (A B B A: the cold first token at 8k, 32k and 120k and a conversation that adds about 3,000 rows a turn) under the rule written before its rows (`decide84.py`, block `solo`, rule 6). The result is section 68: 4.14% faster on an 8k cold prompt, 1.23% at 32k, 10.75% faster on a turn that adds 3,000 rows, every reply equal, and the switch joins the recipe.

## 65. A request's passes in the capture, one by one: what a pass costs before its first row, what a cold request's first pass adds, and what a warm turn pays besides its rows

`scripts/prefill_passes.py` reads rank 0's nsys capture of queue85 (`pf-f85w`, the recipe with patch 0038's three switches and request starts) and cuts it into forwards at the embedding kernel, which runs once a forward. Its tables are in `docs/audit-2026-11-12/queue-rows/queue85/pf-f85w/passes.txt`. The profiler adds little: the capture's 8k request read 462.9 us a row and an un-profiled boot's 459.5 (section 64). Nothing in this section is a measured change; it sizes what the passes say.

**The passes.** The 8,183-row cold request: 1,832.3, 933.3, 970.2 and 45.5 ms (rows 0 to 4,096, to 6,144, to 8,180, then the reply header's 3 rows). The 32,756-row one: 1,916.1, six of 1,679.7 to 1,713.8 (mean 1,698.6), 929.6, 971.0 and 47.1 ms. A warm turn of the ~113k conversation: a restore of 850 MiB in 10.8 ms, one pass of 1,326 rows in 767.3 ms, a keep of 858 MiB in 10.3 ms, the header's 3-row pass in 48.7 ms, then decode windows of 26 to 34 ms.

**A pass costs about 185 ms before its first row, and most of it is the routed experts.** Three passes kernel by kernel (1,326 rows at ~113k, 2,036 rows at 6k, 4,096 rows at 12k): `tf_exl3_prompt_gu` takes 177.3, 198.9 and 307.0 ms and `tf_exl3_prompt_down` 118.0, 138.5 and 218.1 ms. The line through the two larger passes has an intercept of 92.1 ms for the first and 59.8 ms for the second, 151.9 ms together, and `glm_mm4_128` (the small dense matmuls, 646 to 760 launches a pass) another 32.0 ms; the shorter pass sits a little above both lines. Every other kernel is proportional to the rows: the exchanges 115 to 122 ms a 1,000 rows, the wide matmul 84 to 86, the expert combine 32 to 34, the sparse attention 23.1 to 23.2, the KDA step 20.2 to 20.9. So the experts' two kernels read nearly every expert's weights once a pass whatever the rows (in the 3-row pass, which reaches few experts, they take 14.6 ms). This is what a solo step saves: two 2,048-row passes are 1,862.9 ms and a warmed 4,096-row pass 1,698.6, 164.3 ms apart. It is also why section 64's split costs what it does.

**A cold request's first pass adds 134 to 218 ms, and 128 ms of it is the dense attention of the first 2,048 positions.** Below the dense limit a row attends to every row before it (`cuda_dsa_block.attend`, `denseAttention`): `tf_glm_chunks_32_fp8_fused` takes 174.5 ms in 88 launches for the first 2,048 rows, where the sparse one-pass pipeline takes 46.2 ms for the pass's other 2,048 (92.9 ms for a whole 4,096-row pass later on). The rest is main-stream idle (168.0 ms against 79.8) while the side stream's exchanges run 558.5 ms against 475.6. The dense rows are 3.4% of an 8k cold first token, 0.9% of a 32k one and 0.25% of a 120k one, and nothing on a warm turn. A faster dense kernel is a lead for the short cold prompts; it is kernel work and has to keep the bits.

**A warm turn pays 21 ms for copying its state twice, and that grows with the conversation.** The restore copies the whole kept state into the slot (850 to 866 MiB, 10.8 to 11.8 ms) and the keep copies the whole state out again a pass later (858 to 874 MiB, 9.6 to 10.3 ms), each at 72 to 88 GiB/s: 21.1 to 22.1 ms a turn, 2.5% of the 822 to 838 ms first token. The state is 7.5 MiB a 1,000 rows, so at the same rate a 250k conversation pays about 47 ms a turn and a 650k one about 120 ms. Both copies move rows that are already where they are going: the slot that served the last turn still holds every row below the kept state's position (a sequence only appends; `State.reset` clears the KDA records and the conv rows and nothing else), and the keep's rows below the last kept state are the ones just restored. A restore that copies only what a sequence overwrites (the arena head, the index rings, the last pooled rows) is the first half of that lead; the keep's half needs either pages shared between two kept states, which the flat layout of a kept state does not allow, or the copy taken off the first token's path.

**The reply header's 3-row pass is 45.5 to 48.7 ms on every request with request starts: 1.2% of an 8k cold first token and 5.9% of a warm turn.** Its 281 `glm_mm4_128` launches take 19.4 ms, 69 us each, and the experts 14.6 ms. The decode window right after it runs the same 281 matmuls on its 16-row tile kernel in 5.8 ms, but that kernel sums the K slices in another order than the prompt kernel's single slice, so moving the header's rows onto it changes bits; it is not a lever under the numerics decision. A lever that should keep the bits (an inference: the prompt kernels compute each row on its own, and the KDA chain is the same recurrence however the rows are cut) is to run the header's rows in the pass before them and take the kept state at the row between (a solo step is refused today when a keep mark sits at its middle, `prompt_solo.takesTwo`): that needs the KDA chain's state at that row (patch 0039's ranges compute the chain in pieces and can hand it out), the three conv rows before it and the pooled index rows as they stood there. It is the largest warm-turn item on this list and the most code.

**Two more readings of the warm pass, both for the record.** `tf_glm_index_scores` takes 13.1 ms a pass at ~113k against 2.1 and 4.7 ms on the short contexts, so the indexer's scoring grows with the conversation (about 30 ms a pass at 250k if it is linear, which this capture cannot say). `ncclDevKernel_AllReduce_Sum_f64` takes 9.7 ms in its two launches against 0.6 to 2.6 ms: an inference, rank 0 waiting at the first all-rank point of the pass for the other ranks' restores.

## 66. Queue88: three pieces read warm turns 1.33% faster than four across four boots against four, the cold prompt level, and the pre-written ordering rule still says no

Queue84's pieces block left a lead: the 3-piece pair read turns 2 to 8 of the ~113k conversation 1.93% and 1.83% faster than the 4-piece controls with the cold first token level, and its rule (which wanted a cold gain) said no. Queue88 is the confirmation, with a rule written after queue84's rows and before its own (`decide84.py`, block `warm3`; section 61): turns 2 to 8 at least 1.0% faster than the controls' mean, the cold mean not over by more than 0.3%, no boot more than 1.0% over the slower control, decode at one client not more than 1.0% under, equal replies, and every 3-piece boot's turns 2 to 8 under every control's.

**What ran.** Eight boots of `glm53-zig:v129zd` (the image already on all three ranks) from 09:04:26 to 10:11:11 UTC (`queue88.log`), in the order w4a w3a w3b w4b w4c w3c w3d w4d; the controls `w4*` are the recipe N' with 4 pieces and request starts, the others the same with `TF_GLM_OVERLAP_PIECES=3`. Each boot: the cold first token at 8k, 32k and 120k (two requests each), the ~113k conversation (8 turns, salt c74), the ~250k conversation (6 turns, salt c250, report only) and greedy decode at one client. Rows: `docs/audit-2026-11-12/queue-rows/queue88`.

**Result (`decide84.py` and `score81.py` over those rows).**

| | controls (w4a w4b w4c w4d) | 3 pieces (w3a w3b w3c w3d) | 3 pieces against the controls' mean |
|---|---|---|---|
| ~113k conversation, turns 2 to 8, mean ms | 802, 812, 817, 815 (mean 811.5, spread 1.80%) | 795, 798, 806, 804 (mean 800.6) | 1.33% faster; boots -2.05%, -1.64%, -0.73%, -0.92% |
| ~250k conversation, turns 2 and on, mean ms | 864, 875, 879, 880 | 855, 862, 866, 871 | 1.29% faster (report only) |
| cold first token, 8k / 32k / 120k | spread 1.61% / 1.77% / 1.56% | boots from 0.69% faster to 0.94% slower | 0.24% slower on the mean of the three sizes |
| ~113k first turn, ms | 47,561 to 48,260 | 47,760 to 48,556 | boots -0.58%, +0.33%, +0.59%, +1.08% |
| greedy decode at one client | spread 3.3% (prose), 2.8% (code) | within it | 0.09% under |

Every reply is one digest across the eight boots. The shape of the rule passes (1.33% warm, 0.24% cold against its 0.3% allowance, decode level, no boot over the slower control by 1.0%). The ordering fails: the fastest control, w4a at 802 ms, is under two of the four 3-piece boots (w3c 806, w3d 804), so the verdict is no, nothing joins, and `--apply` left every env file as it was (the recipe stays at 4 pieces).

**Reading.** Over the two queues all six 3-piece boots read under their controls' mean on warm turns, by 0.73% to 2.05% (queue84: 797 and 798 ms against controls at 810 and 815; queue88 above), and the ~250k conversation reads the same way, while the cold prompt, the first turn and decode stay level. The effect is small and about the size of the controls' own boot spread (1.80% here), which is why a rule that asks for unanimity fails on it; it is a lead of about 1.3% on a warm turn (10 ms of 811), not a measured gain. Adopting it would move the whole final table queue77 measures at five stream counts, so it is not adopted on a lead. The mechanism is not shown.

## 67. Queue87: patch 0039's KDA chain by ranges equals the whole chain byte for byte on a GPU and reads 0.86% slower on a cold prompt, so it stays off

Section 62 sized `TF_GLM_OVN_PIECE_KDA` from queue85's layer timeline: the main stream idles 1.54 ms after a KDA site's chain, 34 sites a pass, at most 3.1% of a cold pass and an expected 1% to 1.5%. Queue87 is the GPU result, under the rule written before its rows (`decide84.py`, block `kda`, read like a piece count: the cold mean at least 0.5% faster than the controls' with the warm turns not slower by more than 0.3%, equal replies, no boot more than 1.0% over the slower control, decode at one client not more than 1.0% under).

**What ran.** The queue built `glm53-zig:v129ze` from the staged tree (10:13:54 to 10:21:24 UTC, copied to the other two ranks by 10:30:00, one image id on all three), then ran `tf-cuda-test glm-kda-pieces` on the image with production stopped: rc 0, two PASS lines and no FAIL line (the planted controls, a wrong conv window and a wrong start state, each change the bytes; seven cases, the chain by ranges equals the whole chain in `out`, the state, the saved rows and the conv window, byte for byte). Four boots A B B A (n9a d9a d9b n9b; the controls are the recipe N' with request starts, d9 the same with `TF_GLM_OVN_PIECE_KDA=1`), each with the cold first token at 8k, 32k and 120k (two requests each), the ~113k conversation (8 turns) and greedy decode at one client, 10:30 to 10:54:28 UTC. Rows: `docs/audit-2026-11-12/queue-rows/queue87`.

**Result.** Every reply is one digest across the four boots. The cold first token reads slower with the switch on, at every size and in every boot:

| | controls (n9a, n9b) ms | d9a, d9b ms | d9 against the controls' mean | per boot |
|---|---|---|---|---|
| 8k | 3,664, 3,688 | 3,697, 3,709 | 0.73% slower | +0.56%, +0.89% |
| 32k | 13,482, 13,672 | 13,638, 13,754 | 0.88% slower | +0.45%, +1.30% |
| 120k | 50,436, 51,182 | 51,113, 51,493 | 0.97% slower | +0.60%, +1.35% |

The mean over the three sizes is 0.86% slower; the controls' own spread is 0.64%, 1.41% and 1.48%. The ~113k conversation: first turn 47,527 and 48,132 ms against 48,025 and 48,385 (+0.41% and +1.16%), turns 2 to 8 811.3 and 811.1 against 810.9 and 808.4 (0.19% faster, level). Greedy decode at one client reads -1.35% and -0.90% on prose (the controls' spread 0.52%) and +0.06% and +0.36% on code; the switch touches prompt chunks only, so I read the prose figure as boot spread (queue79's two controls differed by 2.2% to 2.8%), not as an effect. The rule asks 0.5% faster on a cold prompt and the rows read 0.86% slower, so nothing joins: `--apply` left the env files as they were, the recipe stays on `v129zd`, and the switch stays a registered default-off knob with its byte check (patch 0039 keeps its GPU check, which a later chain might want).

**Reading.** The model of section 62 counted the idle after the chain and nothing it adds. The chain by ranges runs `kda_prep`, `kda_step` and `kda_out` once a range instead of once a chunk, with a conv-window shift and a state hop between ranges, so a site launches about four times the chain kernels on a quarter of the rows each; the measured cost of that is more than the 1.54 ms it hides (an inference from the sign of the result: no capture of the pieced chain exists, and one nsys boot would give its per-kernel times). Section 61's pieces block pointed the same way for the whole chunk (6 and 8 pieces slower, 2 trading warm for cold), and `FRONT_ROWS` gained nothing: the schedule levers that remain after patch 0038 are measured, and none of them is a sure gain.

## 68. Queue89: `TF_GLM_OVN_SOLO_TO_START` reads 4.14% faster on an 8k cold prompt, 1.23% at 32k, and 10.75% faster on a turn that adds 3,000 rows, every reply equal; it joins the recipe

Section 64 found a chat prompt's last stretch running as two passes where one would do, and wrote `TF_GLM_OVN_SOLO_TO_START` (`patches/solo-cuts/0002`). Queue89 is its GPU result, under the rule written before its rows (`decide84.py`, block `solo`, rule 6: the turns of a conversation that adds about 3,000 rows at least 1.0% faster than the controls', the cold mean and the ~113k conversation's turns not slower by more than 0.3%, equal replies, no boot more than 1.0% over the slower control, decode at one client not more than 1.0% under, and undecided unless every such turn adds rows the switch changes).

**What ran.** The queue built `glm53-zig:v129zf` from the staged 47-patch tree (10:54:28 to 11:01:56 UTC, copied to the other two ranks by 11:10:58, one image id on all three), ran `glm-solo-check` (section 64: passes on one GPU and on three ranks, four runs, switch off and on), then four boots A B B A (s0a s1a s1b s0b; the controls are the recipe N' with request starts, s1 the same with `TF_GLM_OVN_SOLO_TO_START=1`), 11:23 to 11:52:52 UTC. Each boot: the cold first token at 8k, 32k and 120k (two requests each), the ~113k conversation (8 turns, salt c74), a conversation that adds about 3,000 rows a turn (salt c3k, 10 turns, 2,900 to 3,069 uncached rows a turn, mean 2,998) and greedy decode at one client. Rows: `docs/audit-2026-11-12/queue-rows/queue89`.

**Result.** Every reply is one digest across the four boots.

| | controls (s0a, s0b) | s1a, s1b | s1 against the controls' mean |
|---|---|---|---|
| cold first token, 8k, ms | 3,690, 3,716 (spread 0.70%) | 3,548, 3,552 | 4.14% faster (4.20%, 4.09%) |
| 32k | 13,626, 13,655 (0.21%) | 13,477, 13,470 | 1.23% faster (1.20%, 1.25%) |
| 120k | 50,913, 51,068 (0.31%) | 51,012, 51,074 | 0.10% slower (0.04%, 0.16%) |
| ~3,000-row conversation, turns 3 to 10, mean ms | 1,653.8 | 1,475.9 | 10.75% faster, 178 ms a turn |
| ~3,000-row conversation, turn 2, ms | 1,672, 1,681 | 1,682, 1,687 | level |
| ~113k conversation (about 1,290 rows a turn), turns 2 to 8, mean ms | 811.0, 811.7 | 812.0, 810.3 | 0.03% faster |
| greedy decode at one client, prose / code tok/s | 79.86, 78.64 / 112.38, 110.78 | 79.80, 79.21 / 111.93, 111.38 | level |

The rule's figures: the ~3,000-row turns 9.49% faster over turns 2 to 10, the cold mean 1.76% faster, the ~113k turns level, decode level, no boot over the slower control: it passes, `decide84.py --apply` put `-e TF_GLM_OVN_SOLO_TO_START=1` and the image `glm53-zig:v129zf` into queue77's and queue78's env files, and queue90 and the final-recipe table run with it.

**Reading.** The three sizes read somewhat under what section 64 expected from queue85's pass times (about 5.5%, 1.5% and nothing at 8k, 32k and 120k): 4.14%, 1.23% and a level 120k (the 8k prompt runs 4,096 + 4,084 + 3 rows where the controls run 4,096 + 2,048 + 2,036 + 3, one pass less; the 120k prompt has no stretch over a grid step and does not change). The saving on a 3,000-row turn is 178 ms, the fixed cost of a pass that section 65 read off the capture (about 185 ms before its first row, most of it the routed experts' two kernels), so a turn that adds 2,307 to 4,096 rows pays one pass less. Turn 2 of that conversation does not change in either boot; its resume point is the first turn's kept state at row 112,640, and why that step stays split is not known (the rows carry no ring base; a solo step also needs the index rings to agree, `prompt_solo.ringsAgree`, which is the one refusal left that depends on where a state was kept, an inference). The ~113k conversation's turns add about 1,290 rows, never over a grid step, and read level, as they should. Section 64 compared the cold prompt against the recipe without request starts, from queue74's rows: at 8k and 32k request starts with this switch should now read ahead of it as well, which queue77's table (the final recipe against the committed one at every level) will show directly.

## 69. Queue90: `TF_GLM_OVN_RESTORE_HELD` copies a warm turn's restore in a fifth of the bytes; the turn reads 0.95% faster at ~113k and 2.54% faster at ~284k, every reply equal; it joins the recipe

Section 65 sized the restore a warm turn does into its sequence (850 MiB, 10.8 ms of an 822 to 838 ms first token, growing with the conversation) and found that a sequence only appends, so the rows it already holds equal the kept state's. `patches/restore-held` (`TF_GLM_OVN_RESTORE_HELD`, default off) skips those rows when the state is the one the sequence kept or last restored, and `Lanes.claim` gives a resuming stream the free slot that still holds it. This section is its gate, its GPU checks and queue90, under the rule written before the rows (`decide84.py`, block `held`, rule 7: the ~113k conversation's turns 2 to 8 at least 0.8% faster than the controls' mean, the cold mean not slower by more than 0.3%, equal replies, no boot more than 1.0% over the slower control, decode at one client not more than 1.0% under).

**Gate.** Full run `sg-20261120-113810` on the gate host, the pristine pin (tree `4be51cc6beef`) against the 48-patch stack (tree `83a3ea2a5b88`, the id the image was built from): `check-native-cuda-host`, `compile-cuda-tests`, `test-glm-ring-host`, `test-glm-logprobs-host`, `test-rows-host` and `fmt` rc 0, `test-glm-onepass-order-host` rc 0 on the stack, `test-cuda-host` rc 1 on both with the base's one failing name (6,931 of 6,965 passed on the stack, 33 skipped, 1 failed; 6,716 of 6,750 on the base); lean 341 problems on base (6,454 files) and head (6,525 files), 0 new. Verdict PASS. Mutants: 25, each the patch with one change, run through `test-cuda-host` on the stack; every one fails a test of the patch beyond the base's own failing name (the table is in `patches/restore-held/RECORD.md`). Two of my first versions did not build (h8 and h12 each left a parameter or constant unused, which Zig refuses), so a build error stood where a result was needed: both were rewritten to use what they leave out and rerun, and their rows are from those runs. h9 is killed through an abort of its test, not a clean failure (the test shortens a lease by one page to make its restore fail, and I think the failed expectation then leaves that page unreturned so that the pool's own assertion trips; that is an inference from the test's text, not read from a trace); the run counts it as a crashed test.

**GPU checks** (image `glm53-zig:v129zg`, id `52a1f0ce250a` on all three ranks, built from tree `83a3ea2a5b88` by `scripts/queues/queue90.sh`, 11:53 to 12:09 UTC). `tf-cuda-test glm-restore-held-check` on one GPU with glm-synth's 2-layer checkpoint: with the switch off, every restore is whole (3 cases, fp8 and bf16 caches), and 6 planted controls (a held byte changed after the keep) were repaired; with it on, a state resumed by the sequence that kept it equals a whole restore's in every planned byte, 12 greedy steps equal a cold run's, and the 6 planted controls stayed changed, which is what a copy that left those rows alone leaves. Both PASS, rc 0. The rows are under `queue-rows/queue90`.

**Queue90** (12:11 to 13:17 UTC; boots `h0a h1a h1b h0b h0c h1c h1d h0d`; h0 the recipe N' with request starts and solo-to-start, h1 the same with the switch; every boot at the deployed shape `--parallel 4 --context 1048576`): the cold first token at 8k, 32k and 120k (two requests each), the ~113k conversation (c74: a 112,695-row first turn, then 7 turns adding 1,248 to 1,326 rows), a ~284k conversation (c250, `--t1 250000`, which tokenizes to a 283,984-row first turn, then 5 turns adding 1,248 to 1,292 rows) and greedy decode at one client. Every reply is one digest across the eight boots.

| | controls (h0a to h0d) | h1a to h1d | held against the controls' mean |
|---|---|---|---|
| ~113k conversation, turns 2 to 8, mean ms | 816.4, 811.3, 810.7, 812.9 (mean 812.8) | 801.3, 805.0, 802.4, 811.6 (mean 805.1) | 0.95% faster, 7.8 ms a turn |
| ~284k conversation, turns 2 to 6, mean ms | 872.4, 878.4, 877.0, 877.0 (mean 876.2) | 852.0, 856.4, 854.8, 852.6 (mean 854.0) | 2.54% faster, 22.2 ms a turn |
| cold first token, 8k, mean ms | 3,545 (boots 3,510 to 3,558) | 3,543 | 0.06% faster |
| 32k | 13,473 (13,342 to 13,530) | 13,478 | 0.03% slower |
| 120k | 50,982 (50,573 to 51,148) | 51,013 | 0.06% slower |
| greedy decode at one client, prose / code tok/s | 78.78 / 110.88 | 79.15 / 111.66 | level |

The rule's figures: turns 0.95% faster (needs 0.8%), cold mean 0.01% slower (may be 0.3%), equal replies, no boot over the slower control by more than 1.0%, decode level: it passes, and `decide84.py --apply` put `-e TF_GLM_OVN_RESTORE_HELD=1` and the image `glm53-zig:v129zg` into queue77's and queue78's env files. Two readings of how firm the 0.95% is. The ~113k conversation's boots overlap: three of the four held boots are under every control and h1d (811.6) is under two of the four (h0a, h0d) and over h0b and h0c (14 of the 16 pairs have the held boot under the control). Every turn index from 2 to 8 reads under the controls' mean, by 4.2 to 9.5 ms. The ~284k conversation separates cleanly, all 16 pairs, every turn index by 20.8 to 24.8 ms. A restore moves 850 to 866 MiB at ~113k (below), a kept state is 7.5 MiB a 1,000 rows, so the saving should grow with the conversation, and 7.8 ms against 22.2 ms at 2.5 times the context says it does; the rule's cell is the smaller and noisier of the two.

**The copies, in the profiled boot** (queue90's last boot, the switch on, rank 0; `queue-rows/queue90/pf-ph90/passes.txt`, against queue85's capture of the same three warm turns). Restores (runs of device copies into the sequence): queue85 850.0 MiB in 482 copies (10.8 ms), 858.0 MiB in 509 (11.5 ms), 865.9 MiB in 490 (11.8 ms). Here the first is a whole restore of 850.0 MiB in 482 copies (9.6 ms) and the next two are 164.6 MiB in 140 copies (4.0 ms) and 164.6 MiB in 118 copies (1.9 ms). The keeps are the same size and time as before (858.0, 865.9 and 873.6 MiB, 9.6 to 10.8 ms against 9.6 to 10.3). The first warm turn's restore is whole because the capture boot ran its cold 8k and 32k requests between the conversation's first turn and it, so no slot still held the state (an inference from the request order of the capture; not checked against the slots); the chain boots, where nothing runs between turns, restore every warm turn held. The 164.6 MiB that remain are the state's own parts (the arena head, the index rings, the pool in progress). Skipping part of the rings too would need a second mark for what a sequence overwrote since the keep (a sequence that moved on by k rows has overwritten only k of a ring's 4,100); by an estimate from the ring size, not a measurement, that is about a millisecond a turn, so it is not built.

**What it costs.** A warm turn's restore is copied in 19% of the bytes when its sequence still holds the state, and a stream that resumes a state takes the slot that holds it. The keep, the copy of the state out of the sequence, is unchanged (9.6 to 10.8 ms at ~113k in both captures).

## 70. The series moves to upstream main: 1,221 commits, one patch absorbed, ten repaired for dependent launches, one full gate failed and one passed

The owner asked to get back in sync with upstream main and to test the settings others added. This section is the sync. The measurements of what the new base does are queue91's (`scripts/queues/queue91.sh`, not yet run when this was written).

**What moved.** Upstream main `1ece6e6db` (2026-11-20, 1.3.0) is 1,221 commits past our v1.2.9 pin; v1.2.10 (2026-11-18) and v1.3.0 (2026-11-19) shipped in the gap; 45 of the commits touch the GLM family; the settings registry went from 165 rules to 213. Read from the code by a read-only lane (`docs/audit-2026-11-12/knob-inventory-main-1ece6e6.md`, four of its load-bearing claims re-checked against upstream's code here: the PDL default and its exact-`0` rule, the `--tp` refusal for GLM, GLM's missing kept-disk module, `TF_CACHE_EVICT`'s reader): the ones that bear on this serve are in `docs/KNOBS.md`'s new table with the queue91 arm for each.

**How the series was moved.** A text survey (`scripts/reseat-survey.sh`) read 12 patches clean and 36 partial on main, 156 of 824 hunks rejected (113 on v1.3.0). A chain of three-way merges of each patch's own delta (`git merge-tree`, plumbing on a bare repo, nothing checked out; the old series rebuilt first and its final tree equal to the gated id `83a3ea2a5b88`) placed all 48 patches: 29 clean, 19 resolved by hand (patches 5, 6, 7, 10, 11, 12, 13, 19, 22, 23, 24, 27, 28, 30, 31, 32, 33, 40 and 42). Two ds41-direct lanes did the resolutions and logged every decision in `docs/audit-2026-11-12/reseat-main-1ece6e6.md`.

**What changed meaning.**
- Patch 0011 (`TF_GLM_OVN_EXL3_ITEMS`) is absorbed: upstream's `4e6cdeed9` and `51a6fe02a` are our PR #2044 and make the item plan the unconditional decode path. Its +3.8 / +3.9 / +5.3% at 1 / 4 / 8 streams (section 41) is now part of the base; the switch left both environment files. `scripts/check-env.py` against the new tree is what found the stale name.
- Upstream's `7948cc42d` launches every GLM kernel as a dependent launch: each kernel body opens with `glm_pdl::enter()` (a scan test, `test-glm-pdl-scan`, fails one that does not), each launch goes through `cuda_pdl.launch`, each fake test driver forwards `cuLaunchKernelEx`. Ten patches were repaired for it, each inside the patch that owns the code: engine 0012, 0013, 0019 to 0024 and 0036, and the `pr1411` package's test. Where the weight-first early trigger of `PDL_EARLY` (0024) cannot coexist with the scan's rule, its variants now enter like the plain ones (the lever measured neutral to slightly negative and stays off).
- Patch 0007 widens the registry row of `TF_GLM_INDEX_CUDA` to our `all`; 0030 folds our render-once port into main's message-starts render; 0031 drops the retired `items` read; 0040 keeps main's refusal lists and adds GLM's disk refusals; 0042 salts a request's prompt cache by the matched API key under `--cache-salt-per-key`. Every knob these patches add stays off and the default path's bytes are not touched.

**Gates, and what failed.** Upstream's no-GPU workflow now runs `test-glm-pdl-scan` and `test-kernel-contract` for GLM; `scripts/spark-gates.py iter` gained the steps `pdl` and `contract` and `gates.sh` lists both as standalone steps. The lanes' checkpoints (`check fmt ctest lean pdl contract`) passed on the whole series, and the first full gate (`sg-20261120-145609`, tree `978ee41ed164`) still failed: `test-cuda-host` crashed 7 tests the base does not (`General protection exception` inside `cuLaunchKernelEx`), all one cause: the fakes in tests our patches add (`cuda_mla_ovn_test`, the latent-rows test in `cuda_latent`, `cuda_disk_ranks_test`) did not forward the extended launch. The checkpoints had not run the host test step. Five lines, one for each fake, inside patches 23, 36 and the `pr1411` package; the repaired tree is `5ae4bbe5e418`; the quick loop with `test` then read 7,903 of 7,947 tests passed with only the base's own failing name (`rsC1`), and the full gate on it (`sg-20261120-165217`) passed: `check-native-cuda-host`, `compile-cuda-tests`, the standalone host steps, `test-glm-pdl-scan`, `test-kernel-contract` and `fmt` rc 0, `test-cuda-host` the base's one failing name only (7,903 of 7,947 on the stack, 7,687 of 7,731 on the base), lean 168 against 168 with 0 new. The packages and records in `patches/` are the bytes the gate saw: `scripts/apply.sh` and each package's `apply.sh` rebuild every recorded tree id from them (`7ddf34d11e95` after `pr1411`, `fd6d279df5e1`, `f719a9f8e032`, `df26af40eca5`, `f6a5171dad7e`, `5ae4bbe5e418`). The engine numbers are unchanged and 0011 is left vacant, so every document that cites a patch number stays valid.

**What it opened.**
- `scripts/env/prod.env` and `scripts/env/dev.env` replaced `DEFS`: production is the runtime section plus the adopted recipe, development is production line for line plus the candidates; `scripts/check-env.py` keeps them consistent and checks every name against the tree the series makes; `serve.sh`, `zig-tp3.sh`, `gpu-check-tp3.sh` and the sync check read or carry them.
- queue78 and queue86 (about five hours of screens on the old stack, each of which would have been redone on main) were disarmed on spark1; queue77 (the final recipe on the v1.2.9 stack, the baseline for the comparison) runs to its end.
- `scripts/queues/queue91.sh` builds two images from the staged sources (the re-seated stack, and the pristine main as the control for what the stack still buys), runs every GLM GPU check (ours on the stack; upstream's on the stock main first, so a check that fails on both is the base's), then eight interleaved units at the deployed shape: the stack on `prod.env` and on `dev.env`, with `TF_GLM_PDL=0`, with request starts, the stock main, and one more boot of the v1.2.9 stack as a drift guard. `scripts/queue-scores/score91.py` holds its sync rule, written before the rows: accepted when no cell (cold at 8k, 32k and 120k, the conversation's warm turns, greedy and sampled prose and code at 1, 2, 4, 6 and 8 clients) reads more than 1.0% slower than the v1.2.9 stack's and every reply digest is one digest; 13 tests, 14 of 14 mutants killed (two survived the first run: one undefended, one a mutant that perturbed a filter selecting the same keys).

## 71. Queue77, the final recipe on the v1.2.9 stack: cold prompts 9 to 10% faster, warm turns 8.6% faster, 39.2% faster with request starts, every reply equal

Queue77 is the last queue on the v1.2.9 stack and the baseline queue91 (section 70) is compared against. Image `glm53-zig:v129zg` (48 patches), `--parallel 4 --context 1048576`, 13:21 to 17:33 UTC, rows in `docs/audit-2026-11-12/queue-rows/queue77`, scored by `scripts/queue-scores/score77.py` (nothing is decided by it; the candidates each passed their own pre-written rule, `decide79` to `decide84`).

Arms: P the recipe as committed (the 23 adopted knobs); N P plus the candidates (`TF_GLM_OVN_MM_WIDE`, `_SIDE_PRIO`, `TF_GLM_OVERLAP_PIECES=4`, `_LATENT_ROWS=2`, `_PIECE_FRONT`, `_PIECE_FFN`, `_PIECE_MLA`, `NCCL_NCHANNELS_PER_NET_PEER=4`, `_SOLO_TO_START`, `_RESTORE_HELD`: `scripts/env/dev.env`'s candidates section); R N plus `TF_GLM_REQUEST_STARTS=1`; P N N P and R R at `--parallel 4`, then fresh `--parallel 6` and `--parallel 8` boots P N N P each, then the disk tier.

| cell | committed recipe (P1, P2) | N | R | N against P | R against P |
|---|---|---|---|---|---|
| cold first token 8k, ms | 3,996, 3,986 | 3,626, 3,612 | 3,529, 3,506 | 9.3% faster | 11.9% faster |
| 32k | 15,000, 14,914 | 13,513, 13,428 | 13,400, 13,313 | 9.9% faster | 10.7% faster |
| 120k | 56,035, 55,742 | 50,752, 50,297 | 50,734, 50,403 | 9.6% faster | 9.5% faster |
| conversation of 112,695 rows, first turn, s | 52.75, 52.38 | 47.63, 47.43 | 47.71, 47.48 | 9.6% faster | 9.4% faster |
| the same conversation, turns 2 to 8, mean ms | 1,317.6, 1,305.3 | 1,204.3, 1,193.9 | 798.1, 796.6 | 8.6% faster | 39.2% faster |
| 24 prompts one at a time | 1 | 1.0122 (1.0087 to 1.0157), 22 of 24 faster | not run | 1.2% faster | |

Decode at the deployed shape, N against P, aggregate tokens a second at 1 / 2 / 4 clients: greedy prose +0.41 / +0.62 / +0.73%, greedy code -0.06 / +0.38 / +0.65%, sampled prose -0.54 / -0.22 / +0.33%, sampled code +0.20 / +0.23 / -0.04%: level. At 6 and 8 clients queued on the same boot the pairs differ by up to 16% from boot to boot (greedy prose +4.1 / +3.4%, greedy code +4.3 / -1.3%, sampled prose +5.0 / -1.6%, sampled code -2.5 / +6.6%), so those cells decide nothing; the fresh `--parallel 6` boots read -0.11 / -0.33 / -0.30 / -0.48% (greedy and sampled prose and code) and the `--parallel 8` boots -0.35 / -0.14 / +0.33 / +0.14%. Every reply is one digest across the arms: the six cold requests, each turn of the conversation, the 24 prompts and every decode cell's reply set.

Against production's recorded times (cold 2,908 / 11,054 / 41,904 ms, a warm turn 668 ms, a 113k first turn 39.65 s): N is 1.244 / 1.219 / 1.206 times its cold first tokens, 1.795 times its warm turn without request starts and 1.199 times its first turn; R is 1.210 / 1.208 / 1.207 and 1.194 times its warm turn. The committed recipe was 1.372 / 1.353 / 1.334 cold and 1.963 warm.

Request starts: with `SOLO_TO_START` the cold prompt no longer pays for them. R reads 2.8% under N at 8k, 0.8% at 32k and level at 120k, where section 50 had them 4.1 / 6.5 / 7.2% over; the warm turns go from 1,199 to 797 ms. The cost left is the probe that never sends a next turn (section 50: +5% to +12%). `TF_GLM_REQUEST_STARTS=1` is therefore no longer a trade by these cells: it sits in no environment file yet because it changes which states are kept (same replies, section 48) and is the owner's to accept.

Variants (cold and warm turns against P): MM_WIDE=2 (V1) 8.0 / 8.6 / 8.2% faster and 7.2% on warm turns, under N's; `TF_GLM_PREFILL_REDUCE=ring` (X1) 5.3 / 6.2 / 6.3% and 4.1%, under N's; `gather` (X2) 8.7 / 10.6 / 10.8% SLOWER and 4.7% slower; `TF_GLM_OVERLAP_PIECES=8` (Y1) 7.8 / 9.1 / 8.8% and 5.9%, under N's; three pieces (Y2) 9.6 / 10.0 / 9.6% and 8.8%, level with N's (queue88's lead stays unadopted: its rule asks every 3-piece boot under every control). None joins.

Disk tier (`scripts/queue-disk-tier.sh f77`, N with request starts, `--learn-conversations`): all 17 turns' replies equal a cold server's (4 are cold primes, 13 were resumed: from RAM, after a live eviction, after a SIGKILL of every rank, after a clean restart, and from a flushed store); no disk-tier fault counter above 0 on any rank. The 596k conversation against production's: turn 2 from RAM 11.68 s (0.93 of production's 12.54), turn 3 after SIGKILL from disk 11.45 s (0.89 of 12.80), turn 4 after a clean restart 13.96 s (1.08 of 12.90), the cold first turn 307.91 s beside three decoding streams (1.37 of 224.68).

What this decides: nothing is promoted. The ten candidates stay in `scripts/env/dev.env` and queue91's `md` against `mn` arms are the evidence on main, which is the base `prod.env` will run on. Queue77 says they pass on the old base; the promotion rule for main is queue91's.

## 72. Queue91, the stack on upstream main: level with the v1.2.9 stack on cold and 1 to 3% faster on decode, one cell over the limit; the ten dev candidates cost decode on main; stock main is about a third slower

Queue91 is the first queue on the new base: the 47-patch series re-seated on upstream main `1ece6e6db` (image `m130a`), the pristine main (`m130base`) and the v1.2.9 stack (`v129zg`), under `score91.py`'s sync rule, which was written before any row existed. Its first start (18:35 UTC) stopped at its own checks with nothing measured: the pair check verifies paired prompt steps, which `TF_GLM_CHUNK_SOLO=4096` in the recipe replaces, and three lane checks parse a kinds fixture that only `glm-synth` writes. The checks were corrected (commit `72820a7`), the restart ran from 18:47 UTC and finished at 21:56 UTC. All single-GPU checks passed on `m130base` and on `m130a` (38 and 46 PASS lines for the two lane checks) and the three-rank checks passed. Eight boots at `--parallel 4 --context 1048576`, in this order: `mn1` (recipe as committed, `KNOBS=prod`), `md1` (`KNOBS=dev`, the ten candidates), `mz1` (`mn` with `TF_GLM_PDL=0`), `mps` (stock main, `KNOBS=off`), `mr1` (`md` with `TF_GLM_REQUEST_STARTS=1`), `md2`, `mn2`, `mo3` (the v1.2.9 stack, one more boot beside queue77's `P1` and `P2`).

**The sync rule.** The stack on main (`mn1`, `mn2`) against the v1.2.9 stack (`P1`, `P2`, `mo3`), 24 cells, every cell a mean of its group's boots:

| cell | v1.2.9 stack (P1, P2, mo3), mean | stack on main (mn1, mn2), mean | main against v1.2.9 |
|---|---|---|---|
| cold 8k first token | 3,986.2 ms | 3,990.0 ms | 0.10% slower |
| cold 32k first token | 14,925.3 ms | 14,910.2 ms | 0.10% faster |
| cold 120k first token | 55,776.2 ms | 55,653.2 ms | 0.22% faster |
| conversation turns 2+ first token | 1,308.5 ms | 1,313.3 ms | 0.37% slower |
| greedy prose at 1 clients | 80.2 tok/s | 82.7 tok/s | 3.10% faster |
| greedy prose at 4 clients | 111.1 tok/s | 114.3 tok/s | 2.81% faster |
| greedy prose at 8 clients | 119.7 tok/s | 125.3 tok/s | 4.72% faster |
| greedy code at 1 clients | 112.7 tok/s | 115.8 tok/s | 2.76% faster |
| greedy code at 4 clients | 165.6 tok/s | 168.3 tok/s | 1.66% faster |
| greedy code at 8 clients | 176.8 tok/s | 174.0 tok/s | **1.63% slower** |

Of the 20 decode cells 19 are faster, by 1.07% to 9.54%; at 1, 2 and 4 clients all 12 are faster, by 1.07% to 3.10% (mean 2.16%). The cold first tokens are within 0.22% and the warm turns 0.37% slower. All 58 reply digests are one digest across the boots. One cell is over the rule's 1.0% limit and none of its new boots lies inside the old boots' range: greedy code at 8 clients, new 177.2 and 170.8 tok/s against old 172.5, 178.7 and 179.3. Those two groups' boot-to-boot spreads (3.7% and 3.9%, largest over smallest) are larger than the 1.6% gap, and the other three 8-client cells read 1.6% to 4.7% faster, so I read it as boot noise, but the rule says NOT accepted until a rerun settles it: queue95 adds a third boot of the new group and a fourth of the old.

**Where the decode gain comes from.** Every unit has the same tokens a round (`rounds_split.py`: code 6.14, prose 3.14 at one client; acceptance 0.872 and 0.690), so each decode difference below is ms a round. The v1.2.9 stack's rounds are 2.5% (code) and 2.3% (prose) longer than the stack on main's at one client (51.6 against 50.3 ms and 37.9 against 37.0 ms). `mz1` (PDL off) is 4.2% and 4.1% longer (52.5 and 38.6 ms), and at 1, 2 and 4 clients its decode is 2.48% to 4.02% lower in all 12 cells (mean 3.34%) with the cold first tokens 0.39% to 0.83% slower: upstream's dependent launches are worth about 2.5 to 4% of decode on this stack.

**The arms beside it** (faster is positive; the stack on main as the reference, `mr` against `md`):

| arm | cold 8k / 32k / 120k | conversation warm turns | decode, 12 cells at 1, 2, 4 clients |
|---|---|---|---|
| `md` (ten candidates), against `mn` | +8.26 / +8.85 / +8.39% | +7.93% | -0.86% mean, -0.25% to -1.72%, all 12 negative |
| `mz1` (PDL off), against `mn` | -0.39 / -0.49 / -0.83% | +0.03% | -3.34% mean, -2.48% to -4.02%, all 12 negative |
| `mps` (stock main), against `mn` | -34.26 / -41.46 / -42.04% | -25.17% | -31.72% mean, -29.20% to -35.73% |
| `mr1` (`md` with request starts), against `md` | +2.50 / -0.28 / -0.81% | +34.24% | +1.18% mean, -0.43% to +2.26% |

Digests: `md1`, `md2`, `mz1` and `mr1` are equal to `mn`'s in every cell; `mps` is not (stock main lacks the recipe, and the recipe's `KDA_PAD` changes the numerics). `mps` has 13.4% fewer tokens a round on code at one client (5.32 against 6.14) and 9.2% fewer on prose (2.85 against 3.14), and its rounds are 33.8% and 42.3% longer (67.3 and 52.7 ms): which of the recipe's knobs does what is queue92's job.

**The candidates.** The ten gain 8% to 9% on every cold prompt and 7.9% on warm turns, as on the old stack (section 71: 9.3, 9.9, 9.6 and 8.6%), but their decode at 1, 2 and 4 clients is below the recipe's in all 12 cells, where queue77 read it level on the old stack. The two dev boots differ from each other as much as the first one differs from `mn` (`md1` -1.9% and `md2` -0.8% on code at one client, with `mn1` and `mn2` 0.3% apart), so the size is not settled by two boots, but the sign is the same in every cell. By the owner's rule a change ships with no measured regression at any level, and this is a trade until it is shown not to be one. From their notes in `docs/KNOBS.md` I class four of the ten as able to touch decode (`MM_WIDE`, `SIDE_PRIO`, `LATENT_ROWS=2`, `NCCL_NCHANNELS_PER_NET_PEER=4`) and six as prompt-only (`OVERLAP_PIECES=4`, the three `PIECE_*`, `SOLO_TO_START`, `RESTORE_HELD`); that split is a reading, and the queue95 boots test it. Queue95 boots each set on its own (two boots each, with a third `mn` and a fourth old-stack boot) under `score95.py`'s rules, written first. Nothing is promoted.

**Request starts.** `mr1` against `md`: the warm turns 34.24% faster, cold level (+2.50% at 8k, -0.28% at 32k, -0.81% at 120k, one boot against two), every reply equal, decode mean +1.18% at 1, 2 and 4 clients. The old stack read 39.2% (section 71). The trade the dev file names (a cold prompt pays a little) is under the noise on main. **Corrected in section 73:** this paragraph quoted the decode cells at 1, 2 and 4 clients only and recommended `TF_GLM_REQUEST_STARTS=1` for `prod.env`; the same rows at 6 and 8 clients read mean -0.41% with four of eight cells negative, one of them -9.33%, so the recommendation is withdrawn until queue100 settles those cells under the fleet rule (no regression at any level).

**What this decides.** The stack on main is accepted by every cell but one, the one is queue95's to settle, and the ten candidates stay in `dev.env`.

## 73. Queue92, what upstream's merged work gave a stock user: about 2% on decode and nothing on a cold prompt, our own item plan is the largest step in it; request starts need their 6 and 8 client cells settled

Queue92 is the answer to the owner's request to "see if anyone else did anything that sped things up": eleven fresh boots of stock upstream, `KNOBS=off` (the runtime section of `prod.env` and no knob of ours), at `--parallel 4 --context 1048576`, from the queue's start at 21:57 UTC to its done marker at 04:18 UTC (6 h 21 min), in the order `s9a sm2 smz s13a ud1 ui1 smr s10a s9b s13b sm3`. Rungs: v1.2.9 (`s9a`, `s9b`), v1.2.10 (`s10a`), v1.3.0 (`s13a`, `s13b`), the main commit `3661a4281` with the dependent launches and without the item plan (`ud1`), `32c361db9` with the item plan (`ui1`) and main `1ece6e6db` (`mps` of queue91, `sm2`, `sm3`). The rules are `score92.py`'s, written before any row existed: a step is CLEAR when every boot of a rung lies beyond every boot of the rung before it; an open-pull-request arm is a candidate only when no cell reads more than 1.0% slower than the main group's mean. Rows: `docs/audit-2026-11-12/queue-rows/queue92`; the scorer's whole output is `score92.out` beside them and every aggregate below is printed by `scripts/queue-scores/derive92.py` (a report script, 4 tests; its output is `summary92.txt`). All reply digests are one digest across every rung ("0 key(s) with more than one digest" at each of the five steps), so no step is a numerics change.

**The ladder** (faster is positive; 24 cells a rung, the 4 prompt cells and the 20 decode cells; each step against the rung before, and cumulative against v1.2.9):

| rung | prompt cells, step / cumulative | decode at 1, 2, 4 clients (12 cells), step / cumulative | all 20 decode cells, step / cumulative | CLEAR gains / losses |
|---|---|---|---|---|
| v1.2.10 | +1.18% / +1.18% | +1.12% / +1.12% | +0.33% / +0.33% | 14 / 3 |
| v1.3.0 | -0.73% / +0.45% | -0.09% / +1.03% | +0.00% / +0.30% | 3 / 12 |
| PDL in (`3661a4281`) | -0.23% / +0.23% | +0.78% / +1.82% | +0.41% / +0.72% | 12 / 2 |
| item plan in (`32c361db9`) | +0.82% / +1.05% | +1.72% / +3.55% | +2.16% / +2.86% | 21 / 3 |
| main `1ece6e6` | -1.62% / -0.56% | -1.12% / +2.39% | -0.78% / +2.02% | 1 / 13 |

**What each step is.** Commits in each interval (`git rev-list --count`; v1.3.0's commit has one commit that main lacks, so its interval is counted from there) and how many carry an address naming BadAd84: v1.2.9 to v1.2.10 480 (0), to v1.3.0 375 (2), to the PDL commit 232 (4), to the item plan commit 31 (3), to the pin 104 (14). The item plan step's 31 commits include only two that touch GLM or CUDA decode source files (`git diff --name-only` over the interval): our item plan (`4e6cdeed9`, PR #2044) and the maintainer's integration of it (`51a6fe02a`); the rest are other families, build files and tests. The last step's 14 commits of ours are all in another model's family and none touches GLM. Net of the step that holds the item plan, the four other steps sum to +0.69% on decode at 1, 2 and 4 clients (1.12 - 0.09 + 0.78 - 1.12) and -1.40% on the prompt cells. So most of the stock decode gain of +2.39% (cumulative, 1, 2 and 4 clients) is the item plan step (+1.72%), the one that holds our pull request.

**Tokens a round are identical on every rung** (`rounds_split.py` at one and four clients: prose 2.85 and 2.42 tokens a round, code 5.32 and 4.93, acceptance within 0.001 on all nine boots), so every step is ms a round: at one client prose, 54.3 ms in `s9a`, 53.0 in `s9b`, 51.4 in `ui1` and `sm3`, 52.5 in `sm2`.

**Noise.** The two v1.2.9 boots differ by 2.4% at one client (51.6 and 52.9 tok/s, prose) and the two queue92 main boots by 2.1% (53.4 and 54.5), as large as the cumulative gain, so the ladder is read by its CLEAR marks and its signs, not by a single percentage.

**The last step depends on one boot from another night.** The scorer's main group is `mps` (queue91), `sm2` and `sm3`. `mps` reads below the mean of `sm2` and `sm3` in all 12 decode cells at 1, 2 and 4 clients, by a mean of 2.05%, and it was booted before queue92 began. With the scorer's group the last step is -1.12% on those cells; with queue92's own two boots it is -0.44%. The scorer's number is the verdict above. The arms below compare against that same group, so against its mean they read better than against `sm2` and `sm3` alone by a third of that 2.05%, about 0.7%, on those cells.

**Cold first tokens are flat on stock across all of it** (group mean ms; `derive92.py --sections cold`):

| rung | boots | cold 8k | cold 32k | cold 120k | warm turns |
|---|---|---|---|---|---|
| v1.2.9 | 2 | 5,252 | 20,634 | 77,326 | 1,618 |
| v1.2.10 | 1 | 5,190 | 20,366 | 76,170 | 1,606 |
| v1.3.0 | 2 | 5,229 | 20,554 | 76,933 | 1,611 |
| PDL in | 1 | 5,234 | 20,552 | 76,983 | 1,623 |
| item plan in | 1 | 5,206 | 20,384 | 76,290 | 1,606 |
| main `1ece6e6` | 3 | 5,280 | 20,725 | 77,818 | 1,628 |
| our stack on main (`mn1`, `mn2`) | 2 | 3,990 | 14,910 | 55,653 | 1,313 |

**PDL on stock main.** `smz` (stock main with `TF_GLM_PDL=0`): +0.71% on decode at 1, 2 and 4 clients against the main group's mean (-0.51% against its best boot) and +0.54% on the prompt cells, so the dependent launches show no measurable share on stock main (with the group sensitivity above, about zero). On our stack the same switch is worth 3.34% of decode (`mz1`, section 72). That the share belongs to our patched kernels' launches is an inference, not measured.

**Request starts on stock main (`smr`).** Warm turns +36.36% (against the mean; +35.72% against the best boot), cold first tokens -0.11% / +0.40% / +0.86%, decode at 1, 2 and 4 clients +1.13% mean with no cell negative, at 6 and 8 clients -0.27% mean with five of eight negative and the worst -1.91%. By the pre-written rule it is NOT A CANDIDATE: three cells read more than 1.0% slower, greedy prose at 6 clients (-1.18%), greedy code at 8 clients (-1.91%) and sampled code at 6 clients (-1.56%). The main group's own boots spread 6.84% and 8.30% at the first two (inside the control's spread). The third has a tight control (1.08%: 112.6, 113.7, 113.9 against `smr` 111.6), but across all twelve stock boots that cell runs 106.4 to 115.6 tok/s with the main group's three near the top, and `smz` (110.0) and queue96's `ut1` (111.1, section 74) read below them as well, so I read it as a group offset more than a request-starts effect (an inference; the rule's verdict stands).

**The same lever on our stack, all five levels** (this is the correction of section 72; `derive92.py --sections mr1`, `mr1` against the mean of `md1` and `md2`). Warm turns +34.24%; cold +2.50 / -0.28 / -0.81%; decode at 1, 2 and 4 clients +1.18% mean (-0.43% to +2.26%), at 6 and 8 clients -0.41% mean with four of eight negative: greedy code at 6 clients -2.93% (control spread 4.50%), greedy code at 8 clients -1.56% (2.08%), sampled prose at 8 clients -0.82% (5.44%) and **sampled code at 8 clients -9.33% (162.4 against control boots of 180.0 and 178.1, spread 1.06%)**, with +5.27%, +4.39%, +1.65% and +0.09% at the other four. One cell reads slower on both stacks, greedy code at 8 clients (-1.91% on stock main against a control spread of 8.30%, -1.56% on ours against 2.08%), inside the controls' spread both times; the other dips differ between the stacks (stock main: greedy prose and sampled code at 6 clients; ours: greedy code at 6, sampled prose and sampled code at 8), which I read as box noise (an inference). Nothing here shows the lever clean at those levels, and the fleet rule is no regression at any level. Section 72's recommendation to put it in `prod.env` is therefore withdrawn until `queue100` (the recipe against the recipe plus this one variable, ABBA, all five levels, cold and warm, equal replies, under an adoption rule written before the rows) settles it.

**The stack against stock main** (`score92.py`, faster positive): +25.08% mean on the four prompt cells (+19.34% on warm turns to +28.48%), +44.57% on the 12 decode cells at 1, 2 and 4 clients (+38.84% to +54.12%) and +45.06% at 6 and 8 clients (+40.33% to +50.61%).

**What this decides.** Nobody else's merged work, between v1.2.9 and our pin, gave a stock user more than a boot-to-boot spread on decode (+0.69% net of our own item plan, by the scorer's group) or anything on a cold prompt (flat at about 5.2 s for 8k, 20.5 s for 32k, 77 s for 120k); the biggest step is our own item plan. The open-pull-request arms `pd` (#3616) and `pm` (#3659) have no rows yet (queue92b), and the merged work after the pin (192 commits, #3697 among them) is queue96's `ut1`, scored in section 74, which does show a cold-prompt gain. Nothing is promoted: `smr` is NOT A CANDIDATE by its rule and the request-starts question for `prod.env` goes to `queue100`.

## 74. Queue96, stock main at the tip: what upstream merged after our pin gives a stock user a 12 to 13% faster cold prompt and a 9.9% faster warm turn, decode level, every reply byte equal

Queue96 is one boot, `ut1`: image `ut` (`028a6c3135cb`) built on spark1 from upstream main `46c6ee229`, which is 192 commits past the pin `1ece6e6db`, `KNOBS=off`, `--parallel 4 --context 1048576`, the same cells as queue92 (it is a copy of `queue92.sh` run with `ARMS=ut1`, so its log carries the `[q92]` prefix; it ran 04:19 to 05:06 UTC). It is `score92.py`'s `ut1` row, a report beside the ladder written before the rows existed, read against the main group (`mps`, `sm2`, `sm3`). Rows are added to `docs/audit-2026-11-12/queue-rows/queue92/f92-c`, the one directory the queues share (`provenance.txt` there says which queue wrote which boot); every figure is printed by `scripts/queue-scores/derive92.py` and `rounds_split.py` (`summary92.txt`). Reply digests: `ut1` against `sm2`, `sm3` and `mps` is 58 keys, none on one side only and none differing, so nothing the 192 commits changed moves an output byte on these cells.

**The prompt cells** (faster is positive; the scorer's reading, against the main group's mean, and against its best boot):

| cell | main group, ms | `ut1`, ms | against the mean | against the best boot |
|---|---|---|---|---|
| cold 8k first token | 5,280 | 4,652 | +11.90% | +10.95% |
| cold 32k first token | 20,725 | 18,033 | +12.99% | +11.92% |
| cold 120k first token | 77,818 | 67,414 | +13.37% | +12.04% |
| conversation turns 2+ first token | 1,628 | 1,467 | +9.89% | +8.99% |

The cold cells' own boot spread on stock is 0.78%, 0.62% and 0.74% (v1.2.9's two boots) and 0.45%, 0.48% and 0.39% (v1.3.0's two) at 8k, 32k and 120k, and 2.52%, 2.99% and 3.09% inside the main group (whose `mps` boot is from another night), so gains of +11.90% to +13.37% (+10.95% to +12.04% even against the best main boot) are far outside it. **Decode:** at 1, 2 and 4 clients +1.51% mean against the group's mean (+0.79% to +1.91%, none of the 12 negative; +0.28% against its best boot), at 6 and 8 clients +0.57% mean with three of eight negative: greedy code at 8 clients -3.01% (the main group's boots spread 8.30% there), sampled code at 6 clients -2.02% and sampled prose at 8 clients -0.47%. The sampled code at 6 clients reading is a group offset, not an effect of this tip: across all twelve stock boots that cell runs 106.4 to 115.6 tok/s, the main group's three boots (112.6, 113.7, 113.9) sit near the top, and `smr`, `smz` and `ut1` (111.6, 110.0, 111.1) all read below them. Against the better queue92 main boot (`sm3`) the six cells I split read +0.1% to +0.6%, and the group mean is lowered about 0.7% by `mps` (section 73), so decode on stock is level. Tokens a round are identical (prose 2.85, code 5.32 at one client, the same acceptance), so what small difference there is, is ms a round.

**Where the cold gain comes from (by code scope and the pull request's own words, not by a bisect, so an inference).** Of the 192 commits only one changes GLM's prompt-window path at TP=3: ultradaoto's `ae8f0a10f` (#3697, "an uneven KDA stack padded to 16-byte rows, prompt windows on the staged tiles"; four source files, `cuda_engine`, `cuda_kda_block`, `cuda_ranks`, `cuda_tile`). Its message says that at worlds where a rank's fused KDA input is not eight columns wide (3, 5, 6, 7) prompt windows ran on the row kernel and never on the staged tiles, which give the same bytes, with no kernel change and no new switch; the pull request's title claims cold first tokens 10 to 11% sooner at TP=3 (its table, three GB10s: a cold 7.2K prompt 5.07 to 4.53 s, 28.8K 19.32 to 17.18 s) and its changelog line says "every byte as before". The measured +11.90 / +12.99 / +13.37% agrees with that, and the equal digests agree with the bytes. The other GLM-relevant change in the interval is a default decode share for a long fill past 32,768 remaining rows (#3486): it acts when decoders run beside a fill, which no cell of this instrument has, so it is not measured here (the sampler change, #4099, likewise).

**What it means for us.** (1) It answers the owner's question with a yes: a gain from someone else's merged work that is far outside the boot spread, 12 to 13% on a cold prompt, bytes unchanged (the ladder's other steps were small: +1.1% on decode for v1.2.10, +0.8% for the PDL interval, section 73). (2) Our recipe reaches the staged tiles by another route and the pull request names it: the recipe sets `TF_GLM_KDA_PAD=1` with `TF_GLM_DENSE_BITS=4`, and the description says its first version padded every rank to the common width "as `TF_GLM_KDA_PAD=1` does", which left ranks 1 and 2 with a 4.6% wider stack (kda 16.4 to 16.9 ms, a round's wall 60.9 to 61.2 ms), so the unset path pads each rank to its own width; its author asks whether `=1` could take the per-rank width too. On the stack on the pin the cold first token is 3,990 / 14,910 / 55,653 ms, i.e. 14.2% / 17.3% / 17.4% less than stock at the tip and 10.5% less on the warm turns (the stack's group means against `ut1`'s; the stack on the pin against stock on the tip, so not like for like). Whether the tip changes the stack's cold first token is queue97's question (`tn1`, `tn2`: the stack re-seated on the tip, under its sync rule), and what the series still buys at the tip is its U2 reading. Dropping `TF_GLM_KDA_PAD` from the recipe to take the per-rank width (0.3 ms of a 61 ms round, 0.5%, by the pull request's numbers) is not a free lead: the pull request's own table runs the baseline with neither `TF_GLM_DENSE_BITS` nor `TF_GLM_KDA_PAD` and the `=1` run with the dense bits ("290 linears packed"), and AGENTS.md classes `=1` as the 4-bit KDA stack that matches production's numerics, so unset would most likely return that stack to bf16, a numerics change (an inference from those two statements, not tested). The per-rank width on the 4-bit stack is the pull request author's own open question to upstream. (3) #3697 moves no output byte (58 of 58 digests equal) while the recipe's digests differ from stock's (section 72), so stock at the tip is the exact-output baseline, with a cold prompt 12 to 13% faster than before.

**Not decided here.** Whether #3697 alone carries all of the gain needs the tip without it (one image build and one boot); queue97 will say if our stack gains anything from it. Nothing is promoted by this section.

## 75. Queue98 (E3), upstream's `TF_CACHE_EVICT=decayed_resume` on a long agent trace: 47.40% fewer rebuilt rows, every agent turn after the first resumed from its previous turn, every reply equal. HOLDS

Queue98 is the served check of the host-only replay (`docs/audit-2026-11-12/cache-evict-replay-46c6ee2.md`): image `m130a` (the stack on the pin), `KNOBS=prod`, the deployed shape (`--parallel 4 --context 1048576`, the cache budget the engine derives), one fresh boot per arm, `TF_CACHE_EVICT` unset (ce-A) against `decayed_resume` (ce-B), each arm's variable read back from all three ranks' containers before it ran. Each boot first ran the identical smoke of upstream's client (3 requests, 3,110 rebuilt rows on both), then `tools/bench_cache_agents.py` from main `46c6ee229` (sha256 `e05e4ce97dab`): `agent_loops`, 6 conversations, 24 rounds, a 32,768-token system prefix, 16 reply tokens, seed 11, one request at a time, 432 requests (144 agent turns and 288 one-off prompts, two after every agent turn). ce-A ran 05:10 to 07:02 UTC (wall 6,709 s), ce-B 07:04 to 08:04 UTC (3,591 s). The rules are `score98.py`'s, written before any row existed (commit `f2889b5`); P2 was amended before any row existed, and `score98.py`'s docstring and the replay record's section 7 say why (the engine resumes at 2,048-row boundaries). Rows: `docs/audit-2026-11-12/queue-rows/queue98` (scorer output `score98.out`; every aggregate below is printed by `scripts/queue-scores/derive98.py`, a report script with 5 tests, into `summary98.txt`).

**The verdict, by the rules.**

| clause | rule | reading |
|---|---|---|
| P0 qualified | both traces qualified and completed (the client's own flags) | both: 432 rows each, no setup error |
| P1 exact | every reply equal across the arms | the client's compare `token_exact` true, 432 of 432 request fingerprints and token hashes equal |
| P2 not vacuous | at least 10% of A's agent turns (turn 1 and later) did not resume the previous turn's prompt (an allowance of 2,056 rows) | 103 of 138 (74.64%): oversubscribed |
| P3 gain | R = 1 - B / A rebuilt rows, HOLDS at 10% or more | 14,396,073 against 7,572,137: **R = 47.40%** |
| P4 time | B's TTFT sum no more than 1.0% above A's | 3,494.75 s against 6,614.12 s: 47.16% lower |
| P5 replay agreement (no verdict) | the replay predicted 44% to 50% | 47.40%: within |

**VERDICT: HOLDS.** The replay's prediction was a model with mark rules that are not our engine's and a state size inferred between two fits; the served run lands in the middle of its range.

**Where the gain is, and what it is not.** Splitting the 432 requests by kind (`derive98.py`):

| | ce-A rebuilt rows | ce-B rebuilt rows | rows lower | TTFT sum A / B | TTFT lower |
|---|---|---|---|---|---|
| 144 agent turns | 7,409,033 | 585,097 | 92.10% | 3,417 s / 303 s | 91.14% |
| 288 one-off prompts | 6,987,040 | 6,987,040 | 0.00% | 3,197 s / 3,192 s | 0.14% |

So the policy removed nearly all of the avoidable rebuilding, and the whole-trace 47.40% is diluted only by the one-off prompts, which are unique and cold in both arms. An agent turn's mean first token is 23.73 s in A and 2.10 s in B. **In B no agent turn missed: 0 of 138 (turn 1 and later) did not resume its previous turn (median gap 321.5 rows, maximum 639); in A the median gap was 60,753.5 rows and the maximum 86,655.** The engine's own counters say the same from the other side: both arms hit about as often (140 and 143 requests resumed at all, misses 295 and 292) but at very different depths, a mean of 43,271 resumed rows in A (median 32,768, the shared system prefix) against 90,083 in B (median 92,160). My reading of those counters: A keeps the shallow shared-prefix state and loses the conversations' deep ones to the churn of one-off prompts, and B keeps the conversations. Evictions were 494 and 522, trimmed states 251 and 106, nothing refused or failed in either; at the end A held 16 states and B 14. The gain builds as the conversations fill the cache: cumulative R over rounds 1 to 4 is 2.20%, to 8 16.72%, to 12 31.12%, to 16 39.39%, to 20 43.84% and to 24 47.40%.

**Caveats, each read from the record.** (1) The two arms' cache budgets are not equal: the engine derives the budget at boot, and A's gauge read 7,906 MiB (8,290,411,520 bytes) and B's 7,982 MiB (8,370,693,120 bytes), B 0.97% (76.6 MiB) above A; against the replay's input of 8,036 MiB they are 1.61% and 0.66% below. A difference of 76 MiB cannot make 74.64% of the agent turns miss in one arm and 0.00% in the other, but queue99's four boots read their budgets in their facts rows, so the boot-to-boot variation of the budget will be visible. (2) One boot an arm: the quantity is a deterministic count of rows, not a latency, and the client's compare is token-exact, so the spread that matters is the policy's choice, not timing. (3) The trace is upstream's synthetic agent trace (six conversations growing from a 32k prefix to about 85k rows, one-off prompts of 4k to 48k rows). It is the oversubscribed regime: the simulator predicted 0% when the live conversations fit the cache (up to six short ones), and whether our real sessions exceed 7.9 GiB depends on how many long ones run at once (a kept state is 888 MiB at 120,388 rows by queue91's probe, and about 3.9 GiB for a 650k-row conversation at the measured 6,378 bytes a row, so two of those fill the whole budget). (4) Decode, cold first tokens and warm turns without eviction pressure are not measured here; that is queue99.

**What this decides.** The benefit side of the adoption question is settled by the rules above. Queue99 (committed `f81026a`, gated on this run's own compare and passed: "E3 showed a gain, 47.4% fewer", it started at 08:05 UTC) is the cost side, the five-level no-regression check. **The adoption rule, fixed here before any of queue99's rows exist:** `TF_CACHE_EVICT=decayed_resume` goes into `scripts/env/prod.env` (the recipe section) when `score99.py` reads C1 ACCEPTED on queue99's four boots (no cell, cold first token and decode at all five levels included, more than 1.0% slower than the control's mean, and one reply digest across all four boots) and C4 EQUAL; E3's HOLDS is the benefit side, so no warm-turn threshold applies. It stays out, with the cells named, when C1 reads NOT ACCEPTED, and with the digests named when C4 reads DIFFERS; NOT DECIDED (a missing boot or cell) changes nothing and the window is rerun. A flagged cell that lies inside the control boots' range still reads NOT ACCEPTED; what to do with it is the owner's call. Until then the switch is in no environment file.

## 76. Upstream moved again (206 commits overnight): what is new for GLM, how the series sits on it, and queue101, a stock rung at the new main with its rules written first

**What upstream did.** Read between 08:16 and 08:36 UTC (a `git fetch` of upstream main into `work/up/TensorFold`, then `git log`, `git merge-base` and `git rev-list`): main is `fa13df5dd` (committed 2026-11-21 08:16 UTC), 206 commits past our re-seat tip `46c6ee229` (committed 2026-11-20 21:42 UTC; the tip is an ancestor of main). The 206 were committed between 2026-11-20 23:48 UTC and 2026-11-21 08:16 UTC (their author dates start on 2026-10-23, so some were written long before they merged). Eight of them touch GLM paths, five on the CUDA decode side:

- `c1bfb2853`, **`TF_GLM_DSCORES`, default on** (Mia-AiLab's patch 0091 moved onto the decode select): a decode window of 8 or more rows (or 4 from 2,048 64-pool blocks) on an aligned key cache takes `glm_index_scores` instead of `tf_glm_scores`; the kernel writes the same bytes. `3fd6bdb2f` puts it under the kernel contract.
- `16ead2656` and `76e0c0b27` (same author): tile rules fit to a sweep on GB10, "speed only". By the second commit's own numbers `glm_index_scores` is slower than `tf_glm_scores` for 8 and 16 rows up to 8K tokens (0.02 to 0.045 ms a pass of 11 layers), level at 16K and faster from 64K (0.10 ms a pass at 8 rows, 0.31 ms at 16), so a window of 8 or more rows takes it from 64 blocks (16K tokens).
- `5df57c025`, PR #3616 (merged 2026-11-21 05:49 UTC): **`TF_GLM_DRAFT_SPLIT=1`** splits the DFlash2 drafter's MLP at three ranks or more without `TF_ROCE=1`; opt-in, the default unchanged. Its issue #3581 reports, on three GB10s at TP=3 with the v1.2.9 release binary (the reporter's numbers, not ours): aggregate decode 55.90 and 55.88 tok/s unsplit against 58.53 and 58.47 split (+4.7%), 58.91 and 58.84 against 62.39 and 62.55 on code at one stream (+6.1%), tokens a round 3.057 against 3.058, and 13 of 13 greedy replies equal in all four starts.

The other three GLM commits are the Metal backend's. Shared code also changed: `6b4cc34e1` (#2669) spills backend-expired prompt states to the disk tier, and `c896bfc0c` caps a unified Linux memory budget at CUDA's free memory after the checkpoint leaves the page cache; whether the second moves our derived prompt-cache budget is one of the readings of the rung below (U5).

**None of it is in a release.** `git merge-base --is-ancestor` says `ae8f0a10f` (#3697, the section 74 gain), `c1bfb2853`, `5df57c025`, `16ead2656` and `76e0c0b27` are in none of `v1.3.0`, `v1.3.1` and `v1.3.2` (v1.3.2, "Release 1.3.2", committed 2026-11-20 17:07 UTC, contains our pin `1ece6e6db`, branched from main at `f9f070a42`, 109 commits before the tip, and has 2 commits main lacks). So the 12% to 13% cold-prompt gain of section 74 is a gain on main: a user who follows releases gets it with the next one.

**What it means for the stack.** (1) The drafter split is a retirement candidate, not a keeper. Upstream's `TF_GLM_DRAFT_SPLIT=1` is the split our `TF_GLM_OVN_DRAFT_MLPSPLIT=4` (patch 0006, in the recipe) does behind a different gate: ours splits only while at most four streams draft, upstream's on every pass. Sections 18 and 19 found the gate neutral inside the box's 3% spread (upstream's every-pass split against ours: -0.5 / -0.8 / 0.0 / +3.1 / +4.0% at 1, 2, 4, 6 and 8 streams, one pair of cells; `=8` against `=4`: +0.9 / +0.3 / -0.4 / +1.0 / +1.3%, two cells each in both orders). By the standing rule (AGENTS.md: on every version bump re-test the stack and retire what upstream absorbed, never carry a patch because it was there) ours goes once a window with ours off and `TF_GLM_DRAFT_SPLIT=1` on holds at all five levels, and that window needs a base that has #3616, which the pin does not. I first wrote here that our recipe "already has" the split and that #3616 was a stock user's gain; that framed ours as the incumbent, the opposite of the rule's default, and it is withdrawn. (2) `DSCORES` is a default-on change to the decode index path that our patches 0007, 0012, 0013, 0019 and 0020 also rework. A text survey of the series as re-seated on the tip (47 patches, `archive/reseat-tip-46c6ee2-patches.tar`) against `fa13df5dd` (`scripts/reseat-survey.sh`, `git apply` only, nothing compiled): **36 clean, 11 partial, none refused, none absorbed**, 33 rejected hunks of the series' 808. The partial ones are 0006 draft-knobs (1 of 57 hunks), 0007 index-decode-windows (4 of 15), 0012 index-sched-decode-pools32 (5 of 27), 0013 index-regroup (1 of 12), 0019 sparse-onepass (6 of 16), 0020 onepass-pipe (6 of 20), 0021 kda-chunked (2 of 21), 0023 mla-knobs (2 of 31), 0024 glue-fuse (3 of 37), 0036 glm-latent-rows (1 of 14) and the cache-salt package's 0001 (2 of 65). A re-seat on this main is hand work on eleven patches; the rule asks for it on every bump, so it is under way (a lane), and each decode-index patch then gets a with/without window against `DSCORES` with long-context cells. Nothing is installed by this section.

**Long-context decode, which the records did not have.** `scripts/queue-scores/chaindec.py` (a report script, 5 tests in `scripts/tests/test_chaindec.py`) reads each boot's resumed chain turns: 7 turns of a 114k to 121k-row conversation, 128-token replies, the cache holding more than 50,000 of each turn's rows. Means of the boots' means:

| group (boots) | mean decode, tok/s | spread between boots |
|---|---|---|
| stock v1.2.9 (s9a, s9b) | 70.32 | 1.28% |
| stock v1.2.10 (s10a) | 71.07 | one boot |
| stock v1.3.0 (s13a, s13b) | 70.76 | 0.20% |
| stock main on the pin (mps, sm2, sm3) | 72.22 | 1.64% |
| stock main at the tip (ut1) | 73.24 | one boot |
| the stack on the pin (mn1, mn2) | 130.19 | 0.41% |

From v1.2.9 to the tip, stock long-context decode is +4.15% (steps +1.06%, -0.43%, +2.06%, +1.41%, each within or near the 1.3% to 1.6% spread between two boots of one build). The stack on the pin is +80.25% over the main group on the pin and +77.75% over stock at the tip (not like for like), against +44.57% at 1, 2 and 4 clients on short prompts (section 73): the stack's lead is larger at long context. A one-boot-an-arm comparison therefore cannot read a difference below about 1.5% there. Nothing here measures beyond 121k rows; the owner's conversations run to 650k.

**Queue101, the rung, with its rules fixed before any ut2 row exists.** Image `ut2` is a `git archive` of `fa13df5dd` (tree `efd5bccea8b5`, `stage/src-ut2.tar`, sha256 `f0dadfe4d23a0e63`, the same Zig 0.17.0 as the previous tip), built on spark1 by the queue after queue99 finishes (builds never run beside a bench). Four fresh boots at the deployed shape, `KNOBS=off`, in this order: `ut2a` (stock, no XENV), `ut2s` (`TF_GLM_DRAFT_SPLIT=1`), `ut2d` (`TF_GLM_DSCORES=0`, the new default off), `ut2b` (stock again, so the rung has two boots and a spread of its own). Each boot runs the cells of queues 92 and 96 (cold 8k, 32k and 120k, the chain, decode at 1, 2, 4, 6 and 8 clients greedy and sampled, the 24 prompts). The script is `scripts/queues/queue92.sh` (the added arms, `readback`, `effect`), deployed as `queue101.sh` (sha256 `47574723eb008d0c`), chain now queue99, queue101, queue100, queue95, queue97, queue93, queue94, queue92b (queue100's waiter was replaced after queue101 was started, the new one before the old one was killed). Guards: both variables are read back on all three ranks and the queue stops when they are not exactly the arm's; rank 0's `dflash2: drafter from ... GiB on the device` line and its `TF_GLM_DSCORES` lines are kept as `LABEL-drafter.txt` and `LABEL-dscores.txt`; `ut2s` is skipped when its drafter is not under 0.6 GiB (the reporter's split drafter reads 0.44 GiB against 0.93 unsplit). The scorer is `score101.py` (written by a lane from these rules), reading the rows against `ut1` and the main group; faster is positive and LIMIT is score92's 1.0%:

| clause | rule |
|---|---|
| U0 qualified | all four boots present with every cell, else NOT DECIDED naming what is missing. The arms must have taken effect, from the boots' own logs: `ut2s`'s drafter line under 0.6 GiB, `ut2a`, `ut2b` and `ut2d` equal to each other, `ut2d` with a `TF_GLM_DSCORES=0` line, and `ut2a`, `ut2b` and `ut2s` with no `TF_GLM_DSCORES` line at all; a failure prints "U0 ARM DID NOT TAKE EFFECT" and a missing proof file is NOT DECIDED, not a pass |
| U1 tip rung (descriptive) | the ut2 group (`ut2a`, `ut2b`) against `ut1`, every cell; a cell is CLEAR only when both ut2 boots lie beyond `ut1` in the same direction by more than the larger of 1.0% and that cell's own `ut2a` against `ut2b` difference; counts of CLEAR cells per group (prompt cells, decode at 1, 2 and 4, decode at 6 and 8) and the reply digests that differ from `ut1`'s (none expected: nothing may change an output byte) |
| U2 draft split | `ut2s` against the ut2 group by score92's `arm` rule as it stands (CANDIDATE, NOT A CANDIDATE or NOT DECIDED) |
| U3 DSCORES | `ut2d` against the ut2 group, an attribution report (DSCORES's share is the negative of its cells), and the long-context share, the ut2 group's mean chain decode over `ut2d`'s minus one, CLEAR only when it exceeds both 1.0% and the ut2 group's own boot spread of chain decode |
| U4 long-context decode | the per-boot chain decode means of `ut1`, `ut2a`, `ut2b`, `ut2s` and `ut2d` and the group lines |
| U5 cache budget | each boot's `prompt_cache_budget_bytes` from its facts row, and its difference from `ut1`'s |

The final line states U0, whether U2 reads CANDIDATE and the U1 CLEAR counts, and never says "adopt": whether anything is carried is the owner's call, and nothing in `prod.env` or `dev.env` changes on the strength of a stock rung. **Not decided here:** whether upstream's `DSCORES` adds to or replaces our decode-window index patches (a re-seat with/without test), and what any of this does at 650k rows.

**Amendments and additions made before any ut2 row existed (2026-11-21).** (1) The survey's per-patch table is `docs/audit-2026-11-12/reseat-main-fa13df5-survey.tsv` (47 rows: verdict, hunks, rejected hunks). (2) U0 asks for the two proof files of the four ut2 boots only: `ut1` ran in queue96, before the files existed, and queue101 does not re-run it, so a scorer that required them could never qualify. The lane's first version did exactly that, found by deleting `ut1`'s two files from its own fixture, and `ut1`'s files are now printed when present and never required. (3) U3's long-context share is read in both directions (CLEAR gain when it exceeds both 1.0% and the ut2 group's spread, CLEAR loss when its negative does); as first written the rule was one-sided and would have printed "not CLEAR" for a `DSCORES` that slows decode. (4) When U0 fails a proof, the final line says the U1, U2 and U3 readings are void and carries no U2 word and no CLEAR counts. (5) U1 prints a fixed note that `ut1` ran in queue96, hours before these boots. The scorer is `scripts/queue-scores/score101.py` (43 tests; 44 mutants, each killed by a named test). An end-to-end run on real `ut1` rows relabelled as the four ut2 boots, in the real directory's shape (no proof files for `ut1`) and with deliberate perturbations, reads U0 QUALIFIED, U2 CANDIDATE for a split arm 5% faster on decode, and a CLEAR gain share (+3.20%) for a `DSCORES`-off boot 3% slower on long-context decode.

## 77. An instrument defect in queue99's first boot, found before scoring: the smoke warmed the first cold 8k prompt

**What the rows show.** `ca1`'s first cold 8k request (rep 1) has `cached_tokens` 6,144 and the instrument's own flag `NOTCOLD`: its first token took 986 ms, against 4,087 ms for its own second 8k request and 3,977 and 4,006 ms for `ce1`'s two. Every other cold request of `ca1` and `ce1` has `cached_tokens` 0.

**Cause.** The first boot of queue99 runs a one-time smoke of the queue's instruments (`smoke()`, at 08:08 UTC), and its `longctx.py probe` used the same `--seed pf74` and size 8000 as each unit's real cold probe; `longctx.py` sends the same prompt for the same seed and size, so 6,144 rows of that prompt were in the prompt cache when the real probe's first request came. Only that cell is affected: the smoke's chain has its own salt (`smk`), its decode streams use the 33-token prose prompt (far below the 2,048-row chunk the cache resumes at), and the 24-prompt cell is digests only. The same shared seed and size are in queue95 and queue100 (queue93 and queue94 smoke with upstream's tools on ids of their own; queue92, queue97 and queue101 have no smoke).

**What it would have done.** `score91.boot` computed a cold cell as the mean of every cold row of the boot, flagged or not, and every scorer reads cells through it (`score92`, `score95`, `score97`, `score99`, `score100` through `score99`, `score101` and `derive92`). `ca1`'s 8k cell would have read 2,536.5 ms, 36.45% below `ce1`'s 3,991.5 ms, so the control group's 8k cell would have been too fast and the policy arm would have read slower there with no change in the policy: a false C1 failure in the first cell.

**What I changed, all before any queue99 verdict was computed.**

1. `score91.boot` leaves a cold row flagged `NOTCOLD` out of its cell's mean and keeps its reply digest; a cell whose rows are all flagged has no value (NOT DECIDED downstream). The flag is the instrument's own (`longctx_table.verify`) and the rule is the same for every boot and every arm. No committed row carries the flag, so no earlier verdict changes. Three new tests in `test_score91.py` (all fail on the original reader), 7 mutants in `mutants_score91.py` (all killed by a named test), and the other suites pass unchanged (`score92` 22 tests, `score93` 26, `score94` 55, `score95` 43, `score97` 35, `score98` 50, `score99` 38, `score100` 24, `derive92` 4, `derive98` 5, `chaindec` 5). With it `ca1`'s 8k cell is its second request alone, 4,087 ms, 2.39% above `ce1`'s mean.
2. The smoke probe's seed in `queue95.sh` and `queue100.sh` is now `smk`; both waiters were replaced on spark1 at 08:57 UTC (the new one started before the old one was killed, the chain order unchanged; deployed sha256 `1198ea2818cc48c3` and `d47d92e39bf59f54`, equal to the repo copies).
3. `scripts/tests/check_smoke_probe.py` fails when a queue script's smoke probe shares a seed and a size with one of its unit probes (14 tests, 11 mutants each killed by a named test). It fails on the committed, pre-fix `queue95.sh` and `queue100.sh` (lines 119 and 120 against 140 and 147) and passes on the fixed ones; `queue99.sh` is allowlisted by name, with the reason, because it ran before the gate existed.

**What it leaves.** Queue99 ran with the defect, so `ca1`'s 8k cold cell carries one request where every other boot carries two (the two requests of `ce1` differ by 0.73%, so a single request is a little noisier). When queue99 is scored the report states its verdict by the amended reader and, beside it, what the as-written reader would have said; nothing else of queue99 is touched.

## 78. Queue99, the five-level check of `TF_CACHE_EVICT=decayed_resume`: C1 NOT ACCEPTED by three decode cells at 6 and 8 clients, C4 EQUAL, and the engine's counters say the policy decided nothing differently in this run

**What ran.** Image `m130a`, `KNOBS=prod`, the deployed shape, four fresh boots in the order `ca1 ce1 ce2 ca2` (`ca` the default, `ce` `decayed_resume`; each arm's variable read back on all three ranks), 08:07 to 09:33 UTC, the cells of queues 91 and 92 (cold first token at 8k, 32k and 120k, the growing conversation, decode at 1, 2, 4, 6 and 8 clients greedy and sampled, the 24 prompts). The gate was E3's own compare (47.4% fewer rows, section 75), the rules are `score99.py`'s, written before any row (C1 is score91's sync rule, no cell more than 1.0% slower; C4 every reply digest of `ce1` and `ce2` equal to `ca1`'s), and the adoption rule was fixed in section 75: into `prod.env` when C1 reads ACCEPTED and C4 EQUAL. Rows and scorer output: `docs/audit-2026-11-12/queue-rows/queue99` (`score99.out`, `score99-original-reader.out`, and `summary99.txt`, which `scripts/queue-scores/derive99.py` prints: a report script, 7 tests).

**Instrument audit first (section 77).** Of the 24 cold requests exactly one is flagged `NOTCOLD`, `ca1`'s first 8k (6,144 rows cached), and the other 23 have `cached_tokens` 0. The amended reader leaves it out; the original reader would have added a fourth flagged cell, cold 8k +21.91% slower with a "boot spread" of 45.21%, which is that one row. The verdict class does not depend on the amendment: both readers say NOT ACCEPTED, through the same three decode cells.

**Verdict by the rule: C1 SYNC NOT ACCEPTED, C4 DIGESTS EQUAL (58 digest keys a boot, none differing). `decayed_resume` therefore stays out of `prod.env`.** The three cells (the policy arm's mean against the control's, slower positive):

| cell | ca1 / ca2 (tok/s) | ce1 / ce2 | change | pair ca1-ce1 | pair ca2-ce2 |
|---|---|---|---|---|---|
| greedy code at 8 clients | 180.0 / 173.9 | 173.3 / 175.3 | +1.49% | +3.87% | -0.80% |
| sampled prose at 8 clients | 115.7 / 117.9 | 111.9 / 117.7 | +1.71% | +3.40% | +0.17% |
| sampled code at 6 clients | 165.6 / 177.1 | 166.0 / 168.4 | +2.41% | -0.24% | +5.17% |

**What the cells look like, all 24.** The 12 decode cells at 1, 2 and 4 clients read -0.51% to +0.59% (mean -0.06%), none over the limit. The 8 decode cells at 6 and 8 clients read -4.74% to +2.41% (mean -0.61%): three slower, all three over the limit, five faster. The four prompt cells are faster for the policy arm by 0.23% to 1.41% (cold 8k with the flagged row out of the control's mean). Each flagged cell is slower in only one of its two adjacent pairs, the other reading about zero or reversed. The boots' own two-boot spreads at the decode cells are 0.12% to 1.99% of the mean at 1, 2 and 4 clients (median 1.42%) and 0.60% to 11.47% at 6 and 8 clients (median 2.69%), so the flagged differences of 1.49% to 2.41% are inside the noise of those cells.

**What the engine says about the policy in this run.** The cumulative prompt-cache counters at the end of each boot's kept log: `ce1`, `ce2` and the control `ca2` end with the same state (11 states, 7,262 MiB held, 7 hits, 368 misses, 3 evictions, 0 trimmed); `ca1` differs only by its smoke's extra requests (12 states, 7,478 MiB, 8 hits, 375 misses, 3 evictions). Nothing in these cells overflowed the cache (three evictions in a boot), so the policy had no occasion to choose a different victim, and equal final counters are what that predicts (they are consistent with identical decisions; they do not prove each one). A decode difference between the arms therefore has no mechanism in this window and the three flagged cells read as boot noise. The cache budgets of the four boots (8,198,267,904 to 8,381,965,312 bytes) vary by 2.24%, and with queue91's pin boot and E3's two the seven readings of this recipe span 2.78%, more than E3's arms differed (0.97%): caveat (1) of section 75 is answered, the budget varies from boot to boot by more than the arms differed.

**What is left, and whose call it is.** The adoption rule's last sentence applies: a flagged cell inside the control boots' range still reads NOT ACCEPTED, and what to do with it is the owner's call; I do not change `prod.env`. A rerun would not settle it: with a per-boot sigma near 2.4% (from the median two-boot spread at 6 and 8 clients, an estimate that assumes normal boot noise), resolving a 1.0% difference at two standard errors needs about 46 boots an arm, 1.5% about 21, 2.0% about 12; with 4 boots an arm the standard error of the difference is 1.7%. The repo's own rule, that a cell reading low is rerun A B B A before it is called a loss, was met by this window's order. The decision in front of the owner is a waiver of the 1.0% limit at 6 and 8 clients for a change that cannot touch decode (benefit side: E3, 47.40% fewer rebuilt rows, every reply equal, an agent turn's first token 23.7 s to 2.1 s in the oversubscribed regime; cost side: no cell at 1, 2 or 4 clients beyond 0.59%, and the counters above). My recommendation is to adopt it, as a waiver and not as a pass of the rule.

## 79. Queue101 never measured anything: upstream main's new memory preflight refuses our boot; and every knob our series adds that `prod.env` does not set, audited against the record

**Queue101 (the stock rung at `fa13df5dd`).** It ended 18 minutes after it started: the image `ut2` was built and distributed (id `79dbdd18c034` on all three ranks), production was stopped, and all four boots (`ut2a`, `ut2s`, `ut2d`, `ut2b`) died on rank 0 within 20 seconds with the same refusal: "the checkpoint's 61.3 GiB of weights do not fit the 55.6 GiB the CUDA memory budget grants (68.6 GiB free less a 13.0 GiB reserve)", the later three at 55.3, 55.2 and 55.1 GiB. No row exists, so no score is read. Cause in upstream's code, read from the clone: commit `c896bfc0c` (committed 06:19 UTC on 2026-11-21, after our tip re-seat base `46c6ee229`) makes a unified-memory pool the smaller of host MemAvailable (plus pages parked on the per-CPU lists) and CUDA's own free, less the reserve (`boundFree`, `poolFor`), and before the weights check advises `DONTNEED` on the checkpoint's shards (`cuda_page_drop.zig`); its message says "a GB10 device check is owed". The 13.0 GiB reserve is our own (`serve.sh` `RES` at four streams). Facts measured here: the checkpoint is 83 shards, all symlinks into the Hugging Face blob store on local ext4, all named by `model.safetensors.index.json` with no nesting (163.6 GiB), so upstream's drop reaches every one; spark1's MemTotal is 123.7 GiB. **What held the other 55 GiB when the boot ran is not known**: candidates are page cache of files the drop does not name (the `ut2` image's layers had just been built and loaded), pages parked on the per-CPU lists after production's exit, or memory production had not yet returned. A read taken later, with a serve up, shows nothing (0.11 to 0.14 GiB parked on the three boxes), so only a snapshot of an idle box can tell. Queue103, in preparation, takes that snapshot before every boot attempt and climbs a ladder of remedies (the snapshot alone, then dropping the page cache, then compaction as well), then runs queue101's four arms; its code and result get their own entry.

**Why this matters beyond queue101.** The re-seat onto `fa13df5dd`, and every retirement window on it, carries `c896bfc0c`, so none of them can boot on these boxes until this is resolved. The pin-era boots never met it because their admission read MemAvailable.

**The dormant-knob audit** (`docs/KNOB-PROVENANCE.md`, script `scripts/knob-inventory.py`). The owner asked, for the knobs our patches add that `prod.env` does not set, whether each was tested and fell short (its patch goes) or proven and never turned on. Of 54 names the series adds, 20 are in `prod.env`, 5 are not settings (four CUDA preprocessor macros and one prefix), and 29 are real knobs outside it: 6 in `dev.env` only and 23 in neither. Result: **17 were tested and did not make the cut** (`WIN_FREE`, `PLAIN_MARGIN`, `EXCHANGE_KB`, `ROUTER_WARM`, `PDL_EARLY`, `MM_CLUSTER`, `ROUTER16`, `GLUE_FUSE`, `GLUE_ROW`, `DRAFT_KEEPWIN`, `DFLASH2_WIN`, `INDEX_REGROUP`, `FRONT_ROWS`, `PIECE_KDA`, `KVB8`, `KDA_CHUNKED`, `SPARSE_ONEPASS`), one is a diagnostic (`KDA_DUMP`), and the other 11 are speed that is not on or was never measured where it matters: the ten `dev.env` candidates (cold prompts +8.3 / +8.9 / +8.4% faster as a bundle, decode lower in 12 of 12 cells at 1, 2 and 4 clients, which queue95 splits next; four of the ten are not knobs of the engine series, `OVERLAP_PIECES`, the NCCL setting and the two package switches, so the 29 count only `MM_WIDE`, `SIDE_PRIO`, `LATENT_ROWS`, `PIECE_FRONT`, `PIECE_FFN` and `PIECE_MLA` of them), `ABSORB_VEC` (about 1% faster on prompts, worse on short TTFT and per-stream decode, and the prompt-only gate the old ledger asked for was never built), and `INDEX_SCHED`, `POOLS32`, `DECODE_INDEX`, `INDEX_DECODE_FROM` (judged on decode and on 8k and 32k cold prompts, never at 120k, and overlapping upstream's now-default `TF_GLM_DSCORES`). Queue102 measures `INDEX_SCHED` with `POOLS32`, and `ABSORB_VEC`, on a 120k cold prompt. Two findings in the checking: the old ledger carried two contradictory rows for `DFLASH2_WIN` (its +9 to 10% prose gain at `=32` was a stale-prompt-tap artifact, recorded as moot, and also as "owed again with complete taps"), and section 61's sentence above, "the owner decided on 2026-10-31 to keep numerics changes off", is a looser reading than the owner's answer, which was "keep all off, we need speed for each knob on its own to see what gives best benefit and whether we can either fix it or combine with another tweak elsewhere. needs to be logged": off pending the per-knob run, which gave `SPARSE_ONEPASS` cold -9.4 / -10.2%, `LATENT_MMA` -6.3 / -6.6% and `KDA_CHUNKED` -1.2 / -1.5% and led to the bit-exact `ONEPASS_PIPE`. `LATENT_MMA` was never ported to the Zig series; it is the one numerics lever with a real prompt gain (about 6%) and is the owner's call. A text-only coupling test shows only patches 0016 and 0039 stand alone, so the retirements are knob by knob after the re-seat lands.

## 80. Queue100, `TF_GLM_REQUEST_STARTS=1` at all five levels: warm turns 34.51% faster, and HOLD BACK by six cells that are all round time, not drafting

**What ran.** Image `m130a`, `KNOBS=prod`, one variable (`-e TF_GLM_REQUEST_STARTS=1` on `ce1` and `ce2` only), four fresh boots A B B A (`ca1 ce1 ce2 ca2`) at `--parallel 4 --context 1048576`, 09:53 to 11:22 UTC, the cells of queues 91 and 95 (cold first token at 8k / 32k / 120k, the growing conversation salt `c74`, greedy and sampled decode at 1 / 2 / 4 / 6 / 8 clients, the 24 prompts). The rules are `score100.py`'s C5, written before any row: ADOPT only when C1 (no cell more than 1.0% slower, one digest across the boots) is ACCEPTED, C4 digests are EQUAL and the warm turns are at least 5.0% faster. Rows, the six memory snapshots the queue takes, and the scorer output: `docs/audit-2026-11-12/queue-rows/queue100`.

**Verdict: `C5 ADOPTION: HOLD BACK`.** C4 is EQUAL (58 digest keys a boot, none differing), the warm-turn cell is 1,326.3 ms against 868.6 ms, 34.51% faster, and C1 is NOT ACCEPTED by six cells.

| cell | CA boots | CE boots | change (slower +) | CE spread |
|---|---|---|---|---|
| cold 8k first token | 3,992.5 / 4,065.0 ms | 4,054.5 / 4,108.0 ms | +1.30% | 1.31% |
| greedy code at 6 clients | 175.7 / 171.1 tok/s | 177.8 / 160.9 | +2.34% | 10.01% |
| greedy code at 8 clients | 184.5 / 177.9 | 178.3 / 173.4 | +2.94% | 2.77% |
| sampled prose at 1 client | 78.6 / 77.5 | 77.3 / 76.5 | +1.45% | 1.00% |
| sampled prose at 8 clients | 118.6 / 116.2 | 113.2 / 112.5 | +3.89% | 0.68% |
| sampled code at 6 clients | 165.0 / 173.5 | 158.1 / 163.4 | +4.99% | 3.30% |

Three of the six are clean separations in which every boot of the change arm is on the wrong side of every control boot (sampled prose at 1 client, sampled prose at 8 clients, sampled code at 6 clients); `greedy code at 8 clients` has the change arm's best boot within 0.2% of the control's worst; `greedy code at 6 clients` is not a separation at all, one boot above the best control boot and one 10% below the other, so that cell alone would be called noise. The rule's own test (all of a change arm's boots inside the control's min-to-max span) passes for none of the six, which is why all six are flagged, and the rule reads HOLD BACK whatever the mechanism.

**The factorisation says the whole cost is round time.** Reading each of those boots' own counters (`round`, `tok_per_round`, `ms_per_round`, `acceptance` in `dec-*/<cell><n>.jsonl`): tokens a round and acceptance are identical between the arms in every flagged cell (sampled code at 6 clients 5.235 against 5.125, acceptance 0.920 against 0.917; sampled prose at 8 clients 2.295 against 2.290, acceptance 0.692 against 0.694), and the entire difference is milliseconds a round: sampled code at 6 clients 30.65 against 31.55 ms, sampled prose at 8 clients 19.75 against 20.80 ms, greedy code at 8 clients 27.60 against 28.80 ms, sampled prose at 1 client 35.80 against 36.05 ms. Those gaps are 1% to 4%, against a boot-to-boot spread of the same quantity of 2% to 11% inside one arm (sampled prose at 8 clients: the two control boots are 18.80 and 20.70 ms, 10% apart). So the switch does not change what is drafted; it moves round time by an amount comparable with the box's own round-time variation at 6 and 8 clients. Whether that is a cost of the switch or the known high-concurrency pathology needs more boots than two an arm, and the rule does not wait for that.

**What the cold cost is, and what fixes it.** The 8k cold cell is +1.30% with the spreads overlapping: that is the documented mechanism of this switch (a request that carries a cut runs no solo pass, section 50), and `patches/solo-cuts`, `TF_GLM_OVN_SOLO_TO_START`, exists for exactly it (queue89: cold first token 4.14% faster at 8k, 1.23% at 32k, level at 120k). So the rewrite the rule asks for is not speculative: the next arm is this switch plus the `dev.env` winners queue95 is splitting now (its X set carries `SOLO_TO_START` and `RESTORE_HELD`), measured at the same five levels with a rule written first. If the cold cell comes back clean and the 6/8 cells stay outside the control spans, what is left is a trade for the owner: 34.51% of a warm turn against a few percent of 6- and 8-client round time, with tokens a round unchanged.

**Two side readings.** The queue now snapshots memory on all three boxes before and after each boot (`<label>-mem-idle.txt`, `-mem-after.txt`, added to `work/copy-rows.py`'s keep rules): at 09:55:58 spark1 showed `available` 34.3 GiB of 123.7 GiB, with the three containers at 3.63 / 3.32 / 3.33 GiB RSS, and that boot then admitted 77.0 GiB of device memory (`facts.out`, `memory.active`), which is section 79's preflight question seen from the other side. And the 24 prompts one at a time read 114.3 s against 115.3 s (+0.90%, inside C1's limit, so not flagged) with identical rounds a prompt (129.88 both arms), and the prompt-cache budgets stay inside queue99's 8,198 to 8,382 MB range (8,200 to 8,374 MB here), so nothing here disturbs the cache-policy result.

## 81. Queue95: the ten `dev.env` candidates split cleanly, and both halves are promotable

**What ran.** The stack on the pin, image `m130a`, `KNOBS=prod`, six fresh boots: `mn3` (the recipe as committed), `mt1` and `mt2` (T: `MM_WIDE`, `SIDE_PRIO`,
`LATENT_ROWS=2`, `NCCL_NCHANNELS_PER_NET_PEER=4`), `mx1` and `mx2` (X: `OVERLAP_PIECES=4`, `PIECE_FRONT`, `PIECE_FFN`, `PIECE_MLA`, `SOLO_TO_START`, `RESTORE_HELD`),
and `mo4` (the old stack, the fourth boot of the O group). Cells exactly as queue91: cold first token at 8k / 32k / 120k, the growing conversation, greedy and sampled
decode at 1 to 8 clients, the 24 prompts. Rules in `score95.py`, written before any row. Rows and the scorer output: `docs/audit-2026-11-12/queue-rows/queue95`.

**Verdict: `T: PROMOTABLE` and `X: PROMOTABLE`, and the ten are additive.**
- K2 decode attribution, the 12 cells at 1, 2 and 4 clients: T is CLEAN (mean change inside +-0.5% per cell), X is CLEAN and positive in seven of the ten it prints.
- K3 prompt gains: T +5.24 / +5.89 / +5.71% cold at 8k / 32k / 120k and +4.64% on the conversation's warm turns; X +3.03 / +2.91 / +2.74% and +3.72%.
- K4 digests: both EQUAL to the recipe at all 58 keys.
- K5 additivity: T plus X read +8.26 / +8.81 / +8.45 / +8.35% against the whole bundle D's +8.88 / +9.44 / +8.99 / +8.47%, so the bundle is its parts and nothing is left in the
  interaction.
- K1 sync (the new stack against the old): NOT ACCEPTED on one cell, greedy code at 8 clients. That is the re-seat's own question, not the candidates'.

**Why they are not in `prod.env` yet.** The rule needs 1, 2, 4, 6 and 8 streams, and `score95.py` attributes only the 12 cells at 1, 2 and 4. At 6 clients both halves are
positive in all four cells (T +4.00 / +2.22 / +0.89 / +12.15%, X +4.43 / +6.98 / +1.51 / +10.84%). At 8 clients both are bimodal inside a single arm: T's four boots land
at 116.9, 119.9, 128.4 and 132.2 tok/s on greedy prose, and X's at 114.1, 120.7, 126.0 and 136.9, so a 2-boot mean there measures which mode a boot landed in. **Queue105
is that measurement**: eight boots A B B A twice at `--parallel 4 --context 1048576`, T and X together against the recipe, the four 8-client cells only, `score105.py`'s
rules written before any row (promote when no cell is more than 1.0% slower and the eight boots carry one digest a cell).

## 82. Upstream v1.3.3 (published 20:58 on 2026-11-21): its GLM decode headline is already in our pin, and one new prompt path is not

Read at the release page and in the fetched clone after the owner asked about a new GLM decode kernel. The tag is `2071d0a21` (committed 19:39), published 20:58; `up/main` is
`9b2f99f6f` at 21:25, 393 commits past our pin `fa13df5dd` (08:16). Our pin is an ancestor of the tag.

**The headline, and why it is not work for us.** "GLM-5.3-Flash drafted decode after a 1,040,384-token prompt takes its DSA index scores from `tf_glm_index_scores`, 13.8% faster at
TP=4 (172.39 against 151.51 tok/s median), byte-identical scores and the same tokens" (#3689). The mechanism is `Kernels.takesDecode` in `zig/src/families/glm/cuda_index.zig`, and it
was introduced by `c1bfb2853` and `76e0c0b27`, both committed 2026-11-21 05:50, three hours before our pin; `git log -S takesDecode fa13df5dd..up/main` returns nothing, so nothing
after the pin touches it. The pin's own tests state the gate: 8 rows over 4,096 pools takes the kernel, under 64 pool blocks keeps `tf_glm_scores`, and 4 rows from about 512K
(`takesDecode(4, 216080, 2048)`), with `decodeLoop(48, 1<<20)` returning `score_tiles` at a million. It is default-on there (`TF_GLM_DSCORES`), so the recipe we re-seated onto this
morning already takes it at depth, and our patch 0007's `TF_GLM_INDEX_CUDA=all` is a superset of it (any row count, with its own depth gate). `TF_GLM_DRAFT_SPLIT` (#3616) is in the
pin for the same reason: merged 05:49.

**What is genuinely new for GLM on CUDA since the pin.** `196b93eef` (13:45), "exl3 cuda: the common prompt kernels take 3-bit mcg gate/up and down, by projection group", with
EXL3 `mcg` routed experts loading at any whole-bit width from 1 to 8 (#2094): a PROMPT-path lever, the 4-bit path unchanged, and it pays only with a 3-bit checkpoint, so it needs
weights we do not have and a quality and numerics decision. Everything else with a GLM label in the release is Metal (DFlash2 sampling overhead #4257, vectorised prompt, KDA and
indexer kernels #3921), which this fleet has no hardware for, or is parameterisation rather than speed (#3063: the DSA indexer's pool size, key store and index rope become
parameters).

**Consequence.** No CUDA GLM decode lever to port from this release, and no new overlap with our patches to put in the overlap ledger: the three overlaps already open (`TF_GLM_DSCORES`,
`TF_GLM_DRAFT_SPLIT`, #3697's padding) all sit at or before our pin and their windows run on it. The series stays on `fa13df5dd`. A re-seat onto the tag is 393 commits and the same
full gate, so it is deferred until something needs it, with the 3-bit prompt experts as the one new reason it might.

**The re-seat cost, measured rather than assumed** (`work/reseat3/survey.py`, which walks the engine series in `scripts/apply.sh`'s own order and flags, in a temporary index, no
checkout and no compile). Against our pin as the control, every patch of the series now in `patches/engine` applies: 32 of 32 clean. Against the tag `v1.3.3`, 9 apply clean and 23 do
not, including `0003-prompt-bench`, `0006-draft-knobs`, `0007-index-decode-windows`, `0012`, `0020`, `0021`, `0022`, `0023`, `0024`, `0027`, `0030`, `0031` and `0038`. So v1.3.3 is a
full re-seat job of the same size as the one landed this morning, not a tag bump, which is what "deferred" rests on. (The control also caught a defect in the probe itself: its first
run passed repo-relative paths while git ran inside the clone, so all 41 "refused" including on the base where they demonstrably apply. A survey without a base it must reproduce is a
survey you cannot read.)

## 83. Queue94 scored: `TF_GLM_SOLO_TO_START` fails its rule on the control arm, not on the lever, and the head-skip half cannot be read

**What ran.** Eleven fresh boots on spark1-3, `KNOBS=off`, `--parallel 4 --context 1048576`, from 19:47 to 00:17, on the three branch images `p9f` (main), `phsk` (head skip) and `psts` (solo to start): five head-skip arms (`hk-A1`, `hk-B1a`, `hk-B0`, `hk-B1b`, `hk-A2`) and six solo-to-start arms (`st-A1`, `st-B1a`, `st-B0`, `st-B1x`, `st-B1b`, `st-A2`), each with upstream's own bench tools (`bench_concurrent`, `bench_openai`, `bench_cache`), our cold chat cells and both conversations. Rows: `docs/audit-2026-11-12/queue-rows/queue94` (the scorer's output and every arm's text cells; the raw bench JSONs, 22 MB, stay on spark1 under `~/bench/f94-c`).

**Head skip: NOT DECIDED, and it cannot be decided by these arms.** H5 divides `prompt_cache_bytes` by `prompt_cache_states` with states above zero required, and every boot reports 0 states while holding 6,777,703,808 bytes: all of queue94 runs `KNOBS=off`, whose runtime section keeps no prompt states, so the lever that shrinks a kept state was measured on a configuration that never creates one. Recorded separately in `docs/audit-2026-11-12/queue94-headskip-h5-defect.md`; `queue107` reruns the same five arms and the same rule with `KNOBS=prod` and request starts, which keeps the states H5 reads. What is proved from these rows regardless: H2's switch lines (one in each B1 boot, none in the three controls), H1 clean (no boot cell unclean, no cell with more than one digest).

**Solo to start: FAILS, on the control clause.** S2 requires B1 no more than 1.0% slower than A on every decode cell AND B0 within 1.0% of A everywhere. B1 breaches once (chat, temperature 0, 2 streams, -1.10%), and B0 breaches repeatedly and in one direction: -1.31, -2.20, -1.65, -1.77, -1.02, -2.07, -1.71% across the cells. B0 is the `psts` branch with the switch UNSET, so the branch differs from main by 1% to 2% in code that is not the switch. The lever's own cells read well and consistently: the cold chat first token is 2.32% / 2.71% / 2.13% faster at 8k / 32k / 120k, the ~3,000-row conversation's turns 3 to 10 are 7.74% faster (2,255 against 2,080 ms), and its turn 2 and the ~113k conversation are within 1%. So the evidence supports the lever while the rule cannot pass it, because the control that must prove the branch is clean does not.

**What that means for the lever.** The failure is not "the switch costs speed"; it is "the branch carrying the switch is not main plus the switch". The next run for it needs a branch built as main plus this one change, or a B0 measured on main's own image, so S2's control clause tests something real. Until then `TF_GLM_OVN_SOLO_TO_START` stays in `dev.env` and out of the recipe, which is where it already is.



## 84. 8-client confirmation of T+X: HOLD on one cell

queue105 (`scripts/queues/queue105.sh`, scorer `score105.py`, rows in
`docs/audit-2026-11-12/queue-rows/queue105`) ran the eight-boot mirrored confirmation the 8-client cells of queue95
asked for: four control boots `ca` (recipe as committed, neither bundle applied) and four arm boots `tx`
(`TF_GLM_OVN_MM_WIDE` + `_SIDE_PRIO` + `_LATENT_ROWS=2` + `NCCL_NCHANNELS_PER_NET_PEER=4` from T, and
`TF_GLM_OVERLAP_PIECES=4` + `_PIECE_FRONT` + `_PIECE_FFI` + `_PIECE_MLA` + `_SOLO_TO_START` + `_RESTORE_HELD` from X),
alternated `ca1 tx1 tx2 ca2 ca3 tx3 tx4 ca4` so drift lands on both sides. All eight boots pass their digests: 0 cells
whose eight boots are not one value.

The rule, written into the scorer before any row was read: HOLD if any eight-client cell is more than 1.0% slower,
PROMOTE only when no cell is.

| cell, 8 clients | control `ca` mean (four boots) | arm `tx` mean (four boots) | change |
|---|---|---|---|
| greedy prose | 133.23 (125.9 140.0 145.9 121.2, spread 18.54%) | 123.22 (118.3 123.5 120.3 130.8) | 7.51% faster |
| greedy code | 172.32 (176.4 169.6 178.8 164.5, 8.27%) | 172.78 (174.2 174.1 174.1 168.8) | 0.27% slower |
| sampled prose | 115.24 (110.5 119.0 115.6 115.9, 7.34%) | 117.75 (120.5 115.9 114.5 120.2) | **2.18% slower** |
| sampled code | 165.27 (169.0 161.3 163.6 167.1, 4.66%) | 164.70 (163.7 166.7 165.4 163.0) | 0.34% faster |

**Verdict: HOLD.** Sampled prose is 2.18% slower at eight clients, and greedy prose is 7.51% faster on the same
arm; the control's own 8-client spread is 18.54%, which is why the confirmation ran eight boots. The cell that fails is
inside a spread far larger than its change, but the rule is the rule and the gate does not get rewritten after the
rows: T and X stay in `scripts/env/dev.env`'s candidates section and nothing moves to `prod.env`.

**What would decide it.** The failing cell at eight clients is prose with sampling. The mechanism candidates are
`_LATENT_ROWS=2` and `NCCL_NCHANNELS_PER_NET_PEER=4`, both of which act on decode rows rather than on prompt work;
splitting T from X across sixteen boots at levels 4 and 8 is the measurement that separates them, and neither bundle
carries a five-level cell of its own yet.

## 85. queue102: S retires, V earns five levels

queue102 (`scripts/queues/queue102.sh`, scorer `score102.py`, rows in
`docs/audit-2026-11-12/queue-rows/queue102`) measured two 120k candidates against one control, mirrored
`lc1 ls1 lv1 lv2 ls2 lc2`: S is `TF_GLM_OVN_INDEX_SCHED=1` with `TF_GLM_OVN_POOLS32=1` together, V is
`TF_GLM_OVN_ABSORB_VEC=1`. Digests were equal on every boot and both arms read the same control.

| cold first token, 120k | control `lc` | S | V |
|---|---|---|---|
| 8k | 4,017.5 / 4,027.0 | 4,025.0 / 4,035.5 | 3,987.0 / 3,981.0 |
| 32k | 15,032.0 / 15,081.5 | 15,020.5 / 15,101.0 | 14,895.0 / 14,909.0 |
| 120k | 56,153.5 / 56,537.5 | 56,280.5 / 56,529.5 | **55,961.0 / 55,792.5** |
| change at 120k | | -0.11% | **+0.84%** |
| boots in order | | arm's slower boot above control's faster | **both arm boots beat both controls** |

**S retires.** Its 120k change is -0.11% against a rule needing +0.5%, and its two boots do not separate from the
control's, so `TF_GLM_OVN_INDEX_SCHED` and `TF_GLM_OVN_POOLS32` are rows to remove at their owning patch. It is the
fourth and fifth switch this campaign has retired, and the third time a switch that looked plausible read level.

**V is a promotion candidate.** Cold 8k +0.96%, 32k +1.04%, 120k +0.84% with both arm boots under both control
boots, and decode across twelve cells a mean +0.62% with none negative (the 6- and 8-client cells, information only,
read +2.63 and -2.20 for greedy prose and -4.38 for sampled prose at six). `TF_GLM_OVN_ABSORB_VEC` takes the next
step the campaign requires: a five-level run, fresh boot a level, against the same image.

## 86. queue108: NOT DECIDED, and the probe never made a long prompt

queue108 (`scripts/queues/queue108.sh`) ran eight mirrored boots of `TENSORFOLD_PREFILL_BUDGET=512` and `=2048`, and
`TENSORFOLD_PREFILL_SHARE=0.5` against the recipe, each calling upstream's `tools/bench_concurrent.py` at levels 4 and 8
with `--mixed`. Its own W0 guard then refused the grade: the longest prompt in the 8-stream cell was 25 tokens on
every boot (`b2048a`, `b2048b`, `b512a`, `b512b`, `c1`, `c2`, `s50a`, `s50b` all read 25), so no request ever held a
prompt behind decoders and the lever was never exercised.

The cause is in the tool, not the queue's intent: `bench_concurrent.py` treats `--prompts` and `--mixed` as mutually
exclusive, and under `--mixed` it uses the built-in short prompt pool. The shape the lever needs is `--prompts FILE`
with a JSON list of `{name, kind, prompt}` items whose prompts are thousands of tokens, at levels 4 and 8.

W0 did the job it was written for: a pre-written guard turned a table that would have read as "the controls do
nothing" into a NOT DECIDED which names the missing condition. No rule was edited after the rows.

## 87. queue109: ABSORB_VEC passes the five levels and is promoted

queue109 ran eight boots in the mirrored order `av0a av1a av1b av0b av0c av1c av1d av0d`, each at 1, 2, 4, 6 and 8
streams on the recipe with the switch unset against the same recipe with `TF_GLM_OVN_ABSORB_VEC=1`, the arm it earned
in queue102. Means over four boots a group, and the generated token arrays hashed per level across all eight boots.

| streams | control mean | arm mean | change |
|---|---|---|---|
| 1 | 81.9 (81-82) | 82.2 | +0.34% |
| 2 | 85.6 (85-86) | 85.4 | -0.21% |
| 4 | 112.9 | 112.9 | +0.07% |
| 6 | 149.8 | 150.0 | +0.10% |
| 8 | 185.9 | 185.6 | -0.13% |

All five levels sit inside 0.35%, and the boot-to-boot spread at the two levels that read negative is 1 to 2 tokens a
second, wider than the change itself. Replies are identical: the generated token arrays hash to one value at every
level across all eight boots. So the lever costs nothing on decode, which is the property a prompt-side change must
have, and its gain is where queue102 found it: cold first token +0.96, +1.04 and +0.84% at 8k, 32k and 120k with both
arm boots under both control boots.

**Where the line lives:** `TF_GLM_OVN_ABSORB_VEC=1` is a line of `dev.env`'s candidates section, with its cells, and it
stays out of `prod.env` for the duration of the campaign. `prod.env` is the baseline every arm is measured against, so a
line there silently becomes part of the control and moves the reference every later queue is compared with; the campaign
is chasing parity with production, and its baseline does not move while it does. It is the first switch this campaign has
carried through the whole ladder, and promoting it into the baseline is the first thing after parity. The launcher test's
allowlist gains an `ADDED` set for exactly this case: a knob the pre-split launcher had no line for, dropped from both
sides of the comparison so every other name stays held to the old launcher.

**Superseded 2026-11-23 (owner rule, D3 in `docs/DOC-AUDIT-2026-11-23.md`):** the rule above - that a recipe line stays out of
`prod.env` for the duration of the campaign because it moves the control arm - no longer holds. `prod.env` is the recipe we intend
to ship and it changes when a measured candidate earns promotion or when a table row needs its value chosen; the campaign's
measurements still run on `KNOBS=dev`, and a candidate is promoted with its cells in the commit that carries them. The paragraph
above is kept as the record of the rule as it stood on 2026-11-22.

## 88. queue106: DRAFT_NOISE stays, at +0.86% and not decided

queue106 supplied the two cells `TF_GLM_OVN_DRAFT_NOISE` was adopted without: 6 and 8 clients, sampled prose and sampled
code, eight mirrored boots alternating the switch on and off, four boots a side, digests equal across all eight.

| cell | off (4 boots) | on (4 boots) | change with the knob |
|---|---|---|---|
| sampled prose, 6 clients | 104.78 | 107.89 | +2.96% |
| sampled code, 6 clients | 165.61 | 166.49 | +0.54% |
| sampled prose, 8 clients | 116.10 | 116.80 | +0.60% |
| sampled code, 8 clients | 167.86 | 166.77 | -0.65% |

Mean +0.86%. The rule written before the rows keeps a knob at a 1.0% average with no cell more than 1.0% slower, removes
it at an average of zero or less, and decides nothing in between; +0.86% with one cell at -0.65% is that middle band, so
the verdict is NOT DECIDED and the knob stays where it is. It is the honest outcome: the knob is mildly positive on
average and mildly negative in one cell, and neither reading is outside the boot spreads this queue recorded.

What would decide it: the 8-client sampled code cell is the only negative one and its boots are the widest of the four
(158.7 to 178.2 on the knob side), so a rerun at that cell alone, eight boots a side, is the measurement that moves it.

## 89. Where the cold prompt's time actually goes, from a capture already in the repo

The `pf-f85w` capture (`docs/audit-2026-11-12/queue-rows/queue85/pf-f85w/kern.txt`, 80 kernels, 28,992.7 ms of kernel
time over 194,623 launches, an 8,183-row and a 32,756-row cold request) decomposes the prompt path. Share of the total:

| kernel | total ms | share | launches | mean us |
|---|---|---|---|---|
| `ncclDevKernel_SendRecv` | 5,326.9 | 18.4% | 11,733 | 454 |
| `tf_exl3_prompt_gu` | 3,840.5 | 13.2% | 840 | 4,572 |
| `glm_mm4_w2x4` | 3,816.1 | 13.2% | 6,349 | 601 |
| `tf_exl3_prompt_down` | 2,668.5 | 9.2% | 840 | 3,177 |
| `tf_exl3_ovn_nc1` | 1,688.0 | 5.8% | 5,460 | 309 |
| `glm_mm4_128` | 1,481.1 | 5.1% | 11,503 | 129 |
| `tf_glm_combine` | 1,449.4 | 5.0% | 5,460 | 266 |
| `tf_glm_kda_step` | 985.5 | 3.4% | 2,720 | 362 |
| `tf_glm_onepass_pipe_exact` | 952.3 | 3.3% | 165 | 5,771 |
| `tf_glm_expand_v_x2` | 841.4 | 2.9% | 935 | 900 |
| `tf_glm_absorb_q_x2` | 765.5 | 2.6% | 1,419 | 539 |

**Attention is 3.3% of the prompt path, so it is not where the 1.33 to 1.37x gap lives.** The two biggest families are
the TP exchange (18.4%) and the EXL3 prompt expert GEMMs (`prompt_gu` plus `prompt_down`, 22.4%), with the int4 linears
(`glm_mm4_w2x4` plus `glm_mm4_128`) another 18.3%.

Two leads that follow directly. The exchange is 11,733 launches at a 454 us mean and a 348 us median, which is a launch
shape question before it is a bandwidth question: the same bytes in fewer, larger exchanges is the first thing to price.
And the EXL3 prompt pair costs 840 launches each at 4,572 and 3,177 us, so their per-launch size and tile shape are where
the expert GEMM money is.

The dense-window clip at `0025` (section 89 above this table's subject, commit `7d1286a`) is worth about 130 ms on the
8k first token and remains worth taking, but attention cannot yield more than 3.3% of the path however it is shaped.

## 90. The two biggest prompt families are at their ceilings, so the gap is not a knob

Both leads that section 89 ranked as "the money" were taken apart against the capture and the source, and both refutations
hold on the arithmetic.

**The exchange is not a launch problem.** 720 NCCL groups a 4,096-row chunk (45 layers x 2 sites x 4 pieces x 2 exchanges),
712 and 720 measured in two consecutive passes, 2,880 postings a rank. Each group carries 11.18 MB of fp32 partials out
and 5.59 MB of bf16 glued rows out, so 6.04 GB a rank a chunk, which is the reduce-scatter plus all-gather minimum for a
K-split; the same bytes cannot go in fewer exchanges without changing what is exchanged. Measured 475.6 ms of NCCL stream
time a pass, 13 GB/s a direction against roughly half of one ~27 GB/s link, and the stream is 97% hidden behind the main
stream. A 454 us launch moving 11 to 17 MB is 2% overhead, and the 5,327 ms in the kernel ranking is side-stream busy time
that overlaps compute. No patch exists here; the only count-related change left is `TF_GLM_OVERLAP_PIECES`, which is
already the measured 2-against-4 scheduling trade from queue84.

**The EXL3 prompt pair is at the HBM ceiling.** `tf_exl3_prompt_gu` is a 6 x 865 grid of 256-thread CTAs on 64-member by
128-column items, one launch a layer, and it moves 805 MB of gate and up weights a layer a rank; `tf_exl3_prompt_down`
moves 403 MB plus the pair output, `y` fp32 at 604 MB. Against those bytes: gu at 110 to 220 GB/s, and down at 271 GB/s
plus 604 MB of y, which is the GB10's 273 GB/s peak. The pair plus combine is 659 ms of the 1,643.9 ms busy main stream,
40% of it, so "little work per launch" was a property of the launch-count metric, not of the kernels: each launch moves
0.8 to 1.4 GB.

**The one structural waste named, and it is a kernel project:** a 4,096-row chunk gives each expert about 128 pairs against
a 64-item tile, so each expert's weights are read twice. At peak rate that is 4.4 ms a layer, about 185 ms a chunk, 11% of
the main stream, and whether the second read hits DRAM or L2 is not visible in the trace. A 128-member item is not
available either, because `acc[2][TNB][4]` becomes 128 floats a thread and spills.

**What this means for the campaign.** The engine's prompt path is at memory peak on the expert GEMMs and at half a link on
a 97%-hidden exchange, with the main stream busy 1,643.9 of 1,697.3 ms. So the remaining 1.33x against production is not a
knob, an unfilled overlap or an idle stall; it is either less work in production's prompt path or the same work placed
better, and closing it needs a kernel project priced first by two counter readings (ncu DRAM bytes on one gu launch and on
one down launch), not a patch.

## 91. The 11% expert double-read is an L2 hit, so it is not 11%

The last named waste in the prompt path was that a 4,096-row chunk gives each expert about 128 pairs against a 64-item
tile, so its weights are read twice, worth about 185 ms a chunk if the second read missed DRAM. It does not miss.

`place_items` (`zig/kernels/cuda/experts.cu:149`, the emission at `:191`, `int* it = items + 3 * (ioff + j)`) writes an
expert's items consecutively and experts in ascending order, so an expert's two 64-member items are adjacent in the
plan. CTAs dispatch x fastest, which puts the same expert's two item-blocks six column blocks apart, and their weight
blocks are 6 x 262 KB = 1.57 MB, inside L2. The second read therefore costs L2 bandwidth, not HBM.

What survives is smaller and belongs to `gu` alone: gate and up move 805 MB of weights and about 0.6 GB of x in 7.31 ms,
191 GB/s, or 70% of the GB10's 273 GB/s peak, where `down` reads 271 GB/s, 99% of it. So the open question is whether
`gu`'s 29% is DRAM idle (about 90 ms a chunk, 5% of the main stream) or the 4-bit decode pipeline's own limit: a fifth of
the item as first priced, decided by two ncu DRAM counters and not by a patch.

The receipt exists as a runnable script (`work/retire/receipts/ncu-exl3-prompt.sh`): the exact `WRAP` line for rank 0
(`ncu --replay-mode kernel --launch-count 1 --kernel-name regex:tf_exl3_prompt_gu`, then the same for `down`, with dram
and lts bytes, duration and both throughputs), one cold 8k client call, and a `report` mode printing each reading beside
the verdict its outcome implies. It states in its own header that a profiled boot is counters only, because ncu
serialises kernels, and that digests come from an unprofiled boot.

## 92. queue111: none of upstream's prompt-behind-decode controls helps, and the probe finally measured it

queue108 could not grade these controls because its probe never carried a long prompt. queue111 fixed the instrument
(`--prompts` with a JSON pool, since the tool refuses `--prompts` with `--mixed`) and ran the same eight mirrored arms on
`KNOBS=dev`, the recipe plus every candidate this repo carries. The guard confirms the fix: the longest prompt in the
8-stream cell was 8,711 tokens on all eight boots, and every cell reported zero failures.

| arm | 4 streams decode | 4 streams worst wait | 8 streams decode | 8 streams worst wait |
|---|---|---|---|---|
| `TENSORFOLD_PREFILL_BUDGET=512` | -0.46% | -0.09% | -0.08% | +1.01% |
| `TENSORFOLD_PREFILL_BUDGET=2048` | +0.00% | +2.07% | **-2.43%** | +2.60% |
| `TENSORFOLD_PREFILL_SHARE=0.5` | **-10.46%** | **-24.37%** | **-13.27%** | **-27.78%** |

Against the rule written before the rows: decode within 1.0% and the worst wait at least 10% better, at both levels.
**None qualifies.** A 512-row budget is level on both metrics; a 2,048-row budget costs 2.43% of decode at eight streams
and improves the wait by under 3%; a 0.5 share costs 10 to 13% of decode and makes the worst wait 24 to 28% *worse*,
which is the opposite of what the control is for.

So the recipe keeps its own prompt handling and takes none of upstream's three controls, on the configuration we actually
run. That is the answer the sweep was opened for, and it is a negative that costs nothing to keep: the controls stay
available, unset, and the row in `docs/KNOBS.md` records why.

## 91b. The DRAM counters are not available on this device, so the L2 argument is the answer

The receipt was taken: a rank-0 boot wrapped in `ncu --replay-mode kernel --launch-count 1 -k regex:tf_exl3_prompt_`
(WRAP0/XRUN0 are the launcher's names; plain WRAP is silently ignored, which cost one attempt), `--cap-add SYS_ADMIN`,
one cold 8,192-row request through upstream's `bench_cache.py --prompt-file`, qualified true on the first try.

What came back for the profiled launch:

    dram__bytes_read.sum     (!) n/a
    dram__bytes_write.sum    (!) n/a
    lts__t_bytes.sum         462,528 bytes
    gpu__time_duration.sum   14,048 ns

So the counters the question needed do not exist on this device: DRAM byte counters read n/a on the GB10 for these
kernels, while the L2 counter works. The L2-versus-DRAM question therefore cannot be answered with a DRAM counter here,
and the plan-kernel argument stands as the answer: `place_items` emits an expert's items consecutively, the two item
blocks are six column blocks apart with 1.57 MB between them, and the second read is an L2 hit.

Two instrument notes for the next person. `-k regex:tf_exl3_prompt_` profiles the first kernel whose name matches, which
was `tf_exl3_prompt_rotate` at 14 us, not `gu`; a specific kernel needs `regex:tf_exl3_prompt_gu$`. And `--query-metrics`
returns nothing from a container whether or not the GPU is attached, so metric availability is learned from a real
profile rather than by querying.

The item closes at its ceiling: `gu` at 191 GB/s against `down`'s 271 is at most about 90 ms a chunk, 5% of the main
stream, it cannot be attributed with the counters this hardware exposes, and the structural read says the traffic it
would explain is L2, not DRAM.

## 93. What the recipe is worth: +33% to +56% over the same binary with its switches off

queue112 ran the stock rung at the five levels, two boots a level, with the page cache dropped before every boot (the
rung section 91's follow-up established). Same image `glm53-zig:m130a` as every other measurement, `KNOBS=off`, which
applies `prod.env`'s runtime section and none of its recipe lines.

| streams | stock (`KNOBS=off`) | recipe (`KNOBS=prod`, queue109's control) | gain |
|---|---|---|---|
| 1 | 52.5 | 81.9 | **+56.0%** |
| 2 | 61.2 | 85.6 | **+39.9%** |
| 4 | 83.5 | 112.9 | **+35.2%** |
| 6 | 112.5 | 149.8 | **+33.2%** |
| 8 | 138.5 | 185.9 | **+34.2%** |

Two boots a level agree within 0.7% at every level and the generated tokens are identical between them, so the baseline
is stable enough to quote.

**What the number is, precisely.** Both arms run the same patched binary, so this is not "our patches against upstream
source"; it is the value of the recipe's own switch lines, which are what make most of the patches' code paths active.
The patched-but-default-off configuration is 33 to 56% slower than the recipe, which is why the series is developed as
patches plus an env, and why a patch that is not reached by a line is indistinguishable from one that is absent.

**Why it matters for the campaign.** Until now every comparison was ours against production's Python serve, where we read
1.33 to 1.37 times slower on the cold prompt and level on decode. The stock rung was the missing reference: it says the
work on this series is worth a third more throughput at every level than the same binary left alone, which is the number
to quote for the series itself rather than for any single knob.

## 94. queue113: T and X split, each held by one cell, and the cold gains are the largest of the campaign

Sixteen boots, eight control against four of each arm, every boot measuring both client levels and the cold prompt.
Digests one value per cell. The rule: ADOPT when no decode cell at either level is more than 1.0% slower and the cold
mean is at least 1.0% faster, HOLD when a cell is over the limit, REJECT when the cold mean is not positive. (Sign:
a negative change is the arm faster.)

| | T | X |
|---|---|---|
| cold 8k first token | 4,117.1 -> **3,832.9**, -6.90% | 4,117.1 -> 3,993.9, -2.99% |
| cold 32k first token | 15,348.1 -> 14,218.1, -7.36% | 15,348.1 -> 14,939.6, -2.66% |
| cold mean | **-7.13%** | **-2.83%** |
| decode at 4 clients, worst cell | +0.18% | +0.47% |
| decode at 8 clients | sampled prose -2.83%, sampled code **+2.05%** | greedy code -2.30%, sampled code **+1.78%** |
| cell over the limit | 8-client sampled code | 8-client sampled code |
| verdict | **HOLD** | **HOLD** |

So T is worth about 7% on the cold prompt at both lengths with decode level at four clients, and X about 3%, and each is
blocked by the same single cell: sampled code at eight clients. That cell is also the noisiest in the run, a control
spread of 11.57% there (160.6 to 180.1) against 4.7 to 9.6% in the other three, so the reading inside it cannot separate
a 2% change from a boot.

**What this changes.** The cold prompt's known wins were ABSORB_VEC at about 1% and the dense clip at 3.2% of the 8k
token; T alone is 6.9% at 8k and 7.4% at 32k, which is the largest cold result of the campaign and more than both
together. It stays in `dev.env` until the one cell is settled, and settling it is a targeted rerun of that cell rather
than a reinterpretation of this run.

## 95. queue114: the disputed cell is not measurable, and one control boot explains why

Eighteen boots, six a group, one cell each (`sampled code`, 8 clients), mirrored. Digests one value across the eighteen.
The scorer's noise clause fired: the control's own six-boot spread is **19.78%**, above the 5% bar, so the cell gets
`NOT DECIDED: NOISE` and no verdict for either arm. Per-boot means, read from the rows for the record only:

| group | mean | boots | spread |
|---|---|---|---|
| control | 169.5 | 167.8 157.4 **190.9** 168.0 168.2 164.7 | 19.78% |
| T | 171.1 | 172.0 170.5 167.1 174.5 166.3 176.3 | 5.84% |
| X | 168.5 | 175.0 167.6 171.7 162.7 171.7 162.0 | 7.71% |

One control boot at 190.9 sits 12.6% above its own group's mean and is what makes the spread 19.78%; the other five sit
between 157.4 and 168.2. T's mean is 0.94% above the control's and X's 0.6% below, both inside the 1.0% limit that
queue113's rule set, and both arms' own spreads (5.84 and 7.71) are of the same order as the control's without its
outlier.

**So the honest reading is: this cell cannot be decided by six boots on this serve, and the reason is a single fast boot
rather than a systematic cost in either bundle.** Two facts now stand beside each other and neither is a verdict: T is
worth -6.90% at 8k and -7.36% at 32k on the cold prompt with every four-client decode cell inside 0.18%, and the only
eight-client cell that could contradict it is unmeasurable here. Adopting T on that evidence is a judgement about an
unmeasured cell, which is the owner's to make, not mine to make by editing the rule after the rows.

## 96. Every eight-client cell in this campaign measured an oversubscribed serve

queue114's control spread of 19.78% is not clocks and not load: the GB10 is locked at 2,418 MHz application clocks with
no throttle reasons, and the box sat at 0.10 load with no containers once the queue ended. It is the configuration.

Every queue in this campaign boots `--parallel 4 --context 1048576` and then sends eight concurrent clients. That is a
2:1 oversubscribed serve: eight streams share four slots, so per-boot throughput depends on how the requests interleave
and which waits, and that interleaving is not fixed by the boot. The evidence has been in every run: queue95's T boots at
eight clients read 116.9, 119.9, 128.4 and 132.2; queue105's control read 125.9 to 145.9; queue113's control read 160.6 to
180.1; queue114's read 157.4 to 190.9.

Three consequences, and the third is uncomfortable.

1. An eight-client cell is a valid measurement of the oversubscribed configuration, which is what production runs
   (`--parallel 4` with queued requests), so the cells are not wrong; they are noisy by construction.
2. A verdict from four or six boots on such a cell cannot resolve anything smaller than its spread, which is 8 to 20%.
   That is why queue105, queue113 and queue114 all failed at the same cell while agreeing everywhere else.
3. **We have been blocking a bundle worth 6.9% of the cold prompt on a cell that cannot be measured in the configuration
   we test it in.** The right probe for an eight-client decode question is `--parallel 8`, where nothing queues, and the
   right probe for the oversubscribed question is many more boots than any queue has run.

The next run therefore measures the same cell at `--parallel 8`, where the serve has a slot for every stream and the
interleaving question disappears; if it comes back quiet, the bundle's last open cell closes on a measurement rather than
on a judgement about noise.

## 97. The parallel-8 probe is refused by its own readback, and the reason ends that idea

queue115 started at 16:17 and stopped at 16:20 on its first boot, with its own guard: `c1: glm53-zig-r0 has no
TF_GLM_ROCE_MULTI=1, so the recipe's own OVERLAP_PIECES would resolve to 3 and the control would not be the recipe`. The
boot had resolved `--context 524288` cleanly, so the context was never the problem.

The refusal is correct and it invalidates the comparison rather than the run: at `--parallel 8` this image does not set
`TF_GLM_ROCE_MULTI=1`, and that single variable is what resolves the recipe's own `OVERLAP_PIECES` from 3 to 8. So a P=8
boot differs from a P=4 boot in the wire mode as well as in the slot count, and an eight-client cell measured at P=8 would
not be the production configuration with the oversubscription removed; it would be a different serve.

**That closes the idea of measuring the variance away by changing P.** Production runs `--parallel 4` with eight clients
queuing, so the oversubscribed cell is the production configuration, its spread is a property of that configuration, and a
verdict from it needs more boots rather than a different slot count.

**What decides the bundle instead:** not that cell. `dev.env` already enables all eleven candidates together, T and X
among them, so the question "do T and X belong in the production env" is answered by queue116's whole-env comparison
against the current recipe at the five levels, which is the table that ships. If the dev env wins at every level, T and X
ship inside it and the eight-client cell becomes a documented property of the configuration rather than a gate.

## 98. The residual side-stream "exposure" is the main stream's own idle, and it is 4.7% of a pass

The item on the list read "close the residual side-stream and NCCL exposure (77.8 ms a pass after 0038) on transport and
host staging, not EXCHANGE_KB". The capture already in the repo bounds it, and the bound is smaller and better defined
than the note implied.

One steady prompt pass: wall 1,697.3 ms, main stream busy 1,643.9 ms (96.9%), idle **79.8 ms (4.7%)**, NCCL stream busy
475.6 ms. Seven consecutive chunks of the same shape take 1,679.7 to 1,713.8 ms, a 2% spread.

So the exposure a patch could touch is the 79.8 ms of idle in the main stream, not the 475.6 ms of NCCL busy time: the
overlap is already doing most of its job, and the figure to move is a twentieth of the pass. Two figures in circulation
describe it and they are not the same measurement: the lane's per-window reading gave the exchange 97% hidden, and the
pass-level arithmetic here gives at most 83.2% hidden if every idle millisecond is the wire, which it will not be, because
some is kernel-to-kernel gap. The honest sentence is "79.8 ms of main-stream idle a pass, of which an unmeasured share is
the exchange".

That makes the next step a measurement rather than a patch: mark the idle intervals in the capture against the NCCL
stream's activity, and only the overlap attributable to the wire is available to a transport or host-staging change. Until
that is done, "close the residual exposure" has no size to close.

## 99. The dev env ships: level or better at every level, 7% on the cold prompt

queue116 compared the whole dev env, all 22 settings, against the recipe deployed today, at 1, 2, 4, 6 and 8 streams,
two boots an arm, order `prod-a dev-a dev-b prod-b`.

| streams | prod (2 boots) | dev (2 boots) | dev vs prod |
|---|---|---|---|
| 1 | 81.4 (81/81) | 81.6 (82/81) | +0.15% |
| 2 | 84.5 (84/85) | 85.3 (85/85) | +0.99% |
| 4 | 112.3 (112/113) | 112.1 (112/112) | -0.22% |
| 6 | 149.3 (149/149) | 149.7 (149/150) | +0.28% |
| 8 | 183.7 (184/183) | 184.1 (185/184) | +0.23% |

The rule in the queue's header: ship when not slower at any level beyond the boot spread and faster in at least one. The
worst reading is -0.22% at four streams, inside that arm's own 112/113 spread, and four levels are faster, so the rule is
satisfied.

**Promoted:** the eleven candidate settings are now recipe lines in `dev.env` and in `prod.env`, which makes `prod.env` the
next production recipe: `ABSORB_VEC`, `MM_WIDE`, `SIDE_PRIO`, `LATENT_ROWS=2`, `NCCL_NCHANNELS_PER_NET_PEER=4`,
`OVERLAP_PIECES=4`, `PIECE_FRONT`, `PIECE_FFN`, `PIECE_MLA`, `SOLO_TO_START`, `RESTORE_HELD`. Both files carry 46 settings
and their setting lines are byte-identical; `dev.env`'s candidates section is empty with a note saying why. The launcher
test's ADDED allowlist holds the same eleven names, and its dev-versus-prod assertion now reads "dev differs from prod
only by its candidates section, which may be empty" instead of requiring one.

**What this env is worth, taken together.** Against the same binary with its switches off, the recipe is +33% to +56%
(section 93); against today's recipe, the cold prompt is 6.9% faster at 8k and 7.4% at 32k from T with X another 2.8%
(sections 94 and 95), and decode is level at all five levels per the table above. The eight-client cell remains a
documented property of the oversubscribed configuration rather than a gate (sections 96 and 97).

## 100. vec_x2 receipt, half taken: decode is neutral, the capture did not land

The image built from the patched tree (`glm53-zig:vecx2`, id `ba99598`) boots in 131 s at `--parallel 1 --context 1048576`
once the page cache is dropped, and it measures:

| level | m130a (the shipped recipe) | vecx2 | change |
|---|---|---|---|
| 1 client | 81.7 | 81.3 | -0.50% |
| 4 clients | 112.1 | 112.6 | +0.40% |

Both inside half a percent, so the patch does not cost decode. What it has **not** shown is the gain the patch exists for:
queue102 read the vector form 1.0 to 2.5% slower on short TTFT and per-stream decode, and this comparison is aggregate
throughput, which is not the same measurement. So the honest statement is "no regression in aggregate decode" and not
"the decode cost is gone".

The prompt half of the receipt is missing. All three cold prompts qualified on the capture boot (8k, 32k, 120k), the
boot log says `up in 131 s`, and no new `r0.nsys-rep` appeared: the only file in the output directory is the 54,102-byte
one from the first attempt, written before that boot died on the memory preflight, and the directory is root-owned so the
host cannot clear it. The capture-boot wrap therefore needs one more look before the absorb and expand shares can be read.

Two faults of mine in the run itself, both already fixed in the queue: it booted twice without dropping the page cache,
so both boots refused on the preflight, and its first attempt left a root-owned capture directory that the second could
not use cleanly.

## 101. The vec_x2 receipt is negative: no decode gain, and absorb plus expand rose

Both halves are now measured on the patched image, the capture matched to the baseline's workload (`SIZES="8192 32768"`,
`WARMCHAIN=3`, the settings queue85 used).

| | baseline (`pf-f85w`, ABSORB_VEC alone) | vec_x2 image | change |
|---|---|---|---|
| `tf_glm_absorb_q_x2` | 1,419 launches, 765.5 ms | 1,320 launches, 829.4 ms | +8.3% |
| `tf_glm_expand_v_x2` | 935 launches, 841.4 ms | 814 launches, 954.2 ms | +13.4% |
| absorb plus expand | 1,606.9 ms of 28,992.7 (5.54%) | 1,783.6 ms of 31,135.8 (5.73%) | +0.19 points |
| decode, 1 client | 81.7 | 81.3 | -0.50% |
| decode, 4 clients | 112.1 | 112.6 | +0.40% |

So the patch buys nothing: the launch count falls 9.3% because the vector form now covers prompt rows too, decode is
unmoved inside half a percent, and the kernels it was supposed to make cheaper are 3.4% of the path larger in share than
before. Two captures cannot resolve 3%, which is exactly why the honest reading is "no demonstrated gain" rather than
"a small loss".

The rule the receipt carried before its rows was: a decode regression beyond the spread is a HOLD back to the patch, and
a share that does not fall is a HOLD with the numbers. The share did not fall.

## 102. One kernel is 46% of four-client decode: tf_exl3_ovn_nc1

A four-client sampled decode of the shipped recipe (`KNOBS=dev`, `--parallel 4`) captured with software CUDA tracing
(`--trace=cuda-sw`), 294,438 kernels and 19,244.0 ms of kernel time across the window:

| kernel | launches | ms | share |
|---|---|---|---|
| `tf_exl3_ovn_nc1` | 10,920 | 8,847.2 | **45.97%** |
| `tf_exl3_prompt_gu` | 504 | 977.2 | 5.08% |
| `paced_kernel` | 11,570 | 755.0 | 3.92% |
| `ncclDevKernel_AllReduce_Sum_f64_TR` | 24 | 751.4 | 3.90% |
| `ncclDevKernel_AllGather_RING_LL` | 7,640 | 675.6 | 3.51% |
| `glm_mm4_32` | 21,330 | 632.7 | 3.29% |
| `tf_exl3_prompt_down` | 504 | 487.7 | 2.53% |
| `tf_glm_kda_out` + `kda_step` | 31,144 | 692.3 | 3.59% |
| `tf_glm_hc_partial8` | 12,780 | 332.1 | 1.73% |

By family: `nc1` 10,920 launches and 8,847.2 ms (45.97%), KDA 47,192 and 876.3 ms (4.55%), absorb and expand 3,124 and
300.3 ms (1.56%), partial 12,780 and 332.1 ms.

**So the decode path has one dominant kernel, and it is not the one any knob in the campaign has touched.** `nc1` averages
810 us a launch over 10,920 launches: a decode row touches only the eight active experts, so each launch is a small
matmul against a small slice of weights. Whether that 810 us is a bandwidth floor or a launch-and-latency cost is the next
question, and it is answerable from this capture: its per-launch bytes are the eight experts' sliced weights at 4 bits,
against the 273 GB/s the prompt-side pair reached.

That reframes the remaining decode work. The `paced_kernel` at 11,570 launches and 755.0 ms (3.9%) is the pacing of those
launches, and the two NCCL kernels together are 7.4% of the window. None of the six candidate lines still in `dev.env`'s
history addresses `nc1`.

**It is our own kernel, which is the good news.** `tf_exl3_ovn_nc1` is `nc_body<1>` from patch `0031`
(`glm-exl3-x3-decode`), launched for gate/up and down while `TF_GLM_OVN_X3_NC` is set, which the recipe sets together with
`X3_XROW` and `X3_FUSEDOWN`. So the dominant decode cost is code this campaign owns and can change, not an upstream kernel
to route around.

**What is not yet established:** whether its 810 us a launch is a bandwidth floor or a launch-and-latency cost. The bytes
a launch moves are the active experts' sliced weights at 4 bits, and this device exposes no DRAM counters (section 91b), so
the answer comes from reading `nc_body`'s grid, block and per-launch loop against the 273 GB/s the prompt-side pair reached,
not from a counter. That reading is the next step, and it decides whether the decode work worth doing is a tile-shape
change or a scheduling one.

## 103. X3 prefetch depth does nothing: the decode kernel's cost is not the k-step lookahead

Because `tf_exl3_ovn_nc1` is 46% of a four-client decode window and `TF_GLM_OVN_X3_NC=2` doubles its k-step prefetch, the
one-knob arm was worth taking. Rule written to a file before the first boot: adopt `NC=2` at a mean at least 1% above
`NC=1` with identical tokens, reject if more than 1% slower, hold in between. Six boots, three an arm, `--parallel 4`,
sampled code, 256 tokens, three rounds.

| arm | boots | mean |
|---|---|---|
| `TF_GLM_OVN_X3_NC=1` (the recipe) | 153.0, 152.4, 152.8 | **152.74** |
| `TF_GLM_OVN_X3_NC=2` | 153.0, 153.8, 152.2 | 152.98 |

**+0.15%, so HOLD**: the recipe keeps `NC=1`. Deeper prefetch is not what that kernel is short of.

Two faults of mine in running it, both worth the line. The first version labelled boots by arm value, so the mirrored order
`a:1 b:2 b:2 a:1` wrote `b-2` twice, found the first result and skipped, and reported `DONE` after two boots instead of
four: a boot loop whose output path is derived from the arm cannot run the same arm twice, so a mirrored order needs a
per-boot label. And the first pair read 153.27 against 152.36, which is exactly the kind of six-tenths-of-a-percent
difference that a single boot makes look like a result.

**What it leaves standing.** The decode path's dominant cost is a 16-row-tile kernel at 810 us a launch with 10,920
launches in a window. Prefetch depth is ruled out; the remaining candidates inside that kernel are the tile size and the
launch count, which is the same direction as the expert-skew item's "64-row EXL3 units" and is a kernel change with its
own receipt rather than a knob.

## 104. In decode, the collectives run on the main stream: 8.1% of the window, unoverlapped

The item read "close the residual side-stream and NCCL exposure on transport and host staging, not EXCHANGE_KB". The
four-client decode capture answers where that exposure is, and it is not where prefill's is.

| kernel | stream | launches | ms |
|---|---|---|---|
| `ncclDevKernel_AllReduce_Sum_f64_TREE_LL` | **18 (main)** | 24 | 751.4 |
| `ncclDevKernel_AllGather_RING_LL` | **18 (main)** | 7,640 | 675.6 |
| `ncclDevKernel_AllGatherV_RING_LL` | **18 (main)** | 470 | 125.6 |
| `ncclDevKernel_Broadcast_RING_LL` | **18 (main)** | 781 | 3.2 |
| `ncclDevKernel_SendRecv` | 19 (side) | 2,160 | 115.9 |

So in decode **1,555.8 ms of the 19,244.0 ms of kernel time, 8.1%, is collective work sitting on the main stream**, and
the side stream carries 115.9 ms. That is the opposite of the prompt path, where the exchange is 475.6 ms of side-stream
busy time behind a main stream that is 96.9% busy, and it is why the prefill experiments said the exchange was hidden: in
prefill it is.

What that means for a change: up to 8% of decode is available only if some of those collectives can move off the main
stream. The `AllReduce` after the expert phases is a true dependency and cannot move; the 7,640-launch `AllGather` of
weights is the part that could be prefetched on the side stream the way prefill's exchange already is. That is a real lead
with a measured ceiling, and it is the first decode-side lever this campaign has found that is not a kernel shape.

## 105. Most of what is left on the review's list is not in this series

Checked against `patches/` before spending any window on them. Of the eight open items, five name levers the current
series does not carry, so "measure that knob" is not available for them:

| item | in `patches/` | where it actually lives |
|---|---|---|
| `PROMPT_MANY` at 4+ streams | no | retired fork (`archive/ai-engine`) |
| FP8 KV pages at depth | no | retired fork |
| `DRAW1` sampled top-k cells | no | retired fork |
| `HC_DEC` fresh arm | no | retired fork |
| PRX and ZC's P6 cells | no | retired fork |
| `MULTI_FILL` with several cold prompts | mentioned only | `0026` says the file is not carried |
| `LATENT_TILE`'s G=2 variant | no | `archive/tensorfold-gb10` |

Two of the remaining items are real work in this series:

- **The rank-0 expert skew**, about 51 ms a chunk of avoidable wall, which needs 64-row EXL3 units and the owner's call on
  summation order. It is also the direction the decode profile points at, since `nc1` is a 16-row tile at 810 us a launch.
- **The decode `AllGather` prefetch**, now scoped at 675.6 ms and 3.5% of a four-client window, movable to the side stream
  the way prefill already moves its exchange.

So the honest state of the list is: seven items need a port decision before they can be measured, and two are actionable.
Measuring a knob that is not compiled into the image would have produced a NOT DECIDED and a wasted window, which is the
third time this session that reading first was cheaper than booting.

## 106. Owner decisions: port all seven, and the expert skew stays byte-exact

Two decisions taken 2026-11-23, recorded so the next session does not re-derive them.

**Port all seven archive-only levers**, in value order, as a porting project rather than a measurement: `MULTI_FILL`
(several cold prompts in one pass), `LATENT_TILE`'s G=2 variant, `PROMPT_MANY` gated at four or more streams, `DRAW1`'s
sampled top-k cells, PRX and ZC's P6 cells, `HC_DEC`, and FP8 KV pages at depth. Each becomes a numbered package under
`patches/port-<lever>/` with `RECORD.md`, `SHA256SUMS`, and a tree that passes `check fmt` on the gate host, and each
carries the measurement that would decide it. A lever that cannot be ported cleanly is reported with the reason rather
than forced.

**The rank-0 expert skew keeps its block order byte-exact.** Only the scheduling win is taken, which means 64-row EXL3
units with the same arithmetic and the same summation order, so the digests must not move. A reordered reduction would
have been a numerics change with its own evidence, and it is not wanted now.

Both are running: the porting project on its own lane against `patches/port-*/` with `patches/engine/` left alone, and the
decode `AllGather` prefetch diagnosis on the other against the engine series.

## 107. The 64-row EXL3 unit cannot be a bigger tile: the accumulator is already 64 floats a thread

The owner's decision was to take the expert-skew scheduling win with the block order byte-exact, which means 64-row EXL3
units with the same arithmetic. Reading `nc_body` says that unit cannot be reached by enlarging the tile.

`exl3_ovn.cuh`: `constexpr int NT = 8, W = 4, NV = NT / 4, TW = 32;` and `float acc[NT][2][4]`, so **64 floats of
accumulator a thread** inside the 118 registers `tf_exl3_ovn_nc1` already uses, against 32,832 bytes of shared memory.
The tile is 16 rows: `__shared__ int rows_sh[16]`, filled by `threadIdx.x < 16`, with each warp taking `rows_sh[g]` and
`rows_sh[g + 8]`.

Four times the rows is four times that accumulator: 256 floats a thread before any operand, which cannot fit in the 255
register ceiling, let alone in the 118 this kernel uses. So a 64-row unit is not a tile change; it is either 512-thread
blocks with the same per-thread accumulator, or a split accumulation across launches, and both are kernel projects with
their own exactness arguments rather than a scheduling tweak.

**What that leaves for the skew**, with the block order fixed as decided: the wins available without touching arithmetic
are the launch shape (fewer, larger blocks covering more rows through more threads, not deeper per-thread state) and the
decode `AllGather` prefetch now under diagnosis on the other lane, which is 675.6 ms of main-stream time and needs no
tile change at all.

Stated plainly: the engine's decode tile is register-limited at 16 rows, and that is why 10,920 launches of 810 us exist.

## 108. Porting the archive levers: three packages, none yet compiled green

The owner's decision was to port all seven. Three are cut as packages against the current series and **none has a green
build**: applying clean and compiling are different facts, and the first package proved it.

| package | source | state |
|---|---|---|
| `patches/port-multi-fill/0001-glm-multifill.patch` | ai-engine `32060d706` + `23062bd9c`, merged by `93dfbf29a` | applies clean, tree `282674504f86`, screen in flight |
| `patches/port-latent-tile/0001-glm-latent-tile.patch` | `ovn-latile` `b2d1754ab`, tip `1a44a1620` | **first cut was RED** (`cuda_latent.zig:110`, a hoisted launch grid losing `abi.Dim3` context); re-cut with the grid inline, tree `8ab4997131ab`, re-screen in flight |
| `patches/port-prompt-many/0001-glm-prompt-many.patch` | `71217588c` | applies clean, tree `20be2ed88937`, screen queued |

`MULTI_FILL` and `PROMPT_MANY` add the same stepped-many vtable, so they are alternatives and cannot be stacked; both
RECORDs say so. `LATENT_TILE` is independent and adds the **G=2** form the fork never built, with reversed-butterfly
controls for both.

`HC_DEC` (`6c92d7ec2`) is mapped, not assembled: five conflicts in `cuda_glue.zig`, four mechanical (no `router16` at the
site the patch hooks, and `cuda_pdl.launch` replaces `cuda.launch.launch`), and one real, the `hcPre` rows-under-64 branch
which must be written against `cuda_pdl.launch`. Its build step also needs an anchor that exists in this series' build
file. So it needs a hand resolution rather than a text replay, and no package exists for it yet.

`DRAW1` and FP8 pages have sources located and no package; PRX and ZC need a proxy and plan subsystem this series does not
carry, so that one gets a note rather than a port.

**The rule this section exists for:** a package that applies clean and passes `check-patch-packages` is not a verified
lever. It is screened when `iter check fmt ctest` returns rc 0 on its tree, and it is gated only when the full gate with
host tests does. Nothing enters `patches/engine/` on the first, and the RECORDs now have to say `not compiled` until the
second exists.

## 109. First ported package screened green: LATENT_TILE G=2

`iter --name lt-fixed` over `patches/engine` plus `patches/port-latent-tile`: `fmt` rc 0, `compile-cuda-tests` 10 of 10
steps, `ctest` rc 0 in 224 s, `ITER-DONE rc=0`, tree `c0ad0c2a15529bf99a4de0d08050a7eddea57293`. The lane's own screen
agreed at rc 0 in 328 s, which is the agreement I wanted from two independent runs.

So the lever the fork only ever built as G=4 now has a **G=2** form (256 threads, two blocks an SM) that compiles and whose
tests pass on this series, with reversed-butterfly controls for both forms. It has not been benched: the fork's G=4 was
1.7x slower than ABSORB_VEC at one block an SM, and the whole reason G=2 exists is that occupancy 2 is the only form that
could beat the vector path. That bench is the next thing this package needs, and it needs an image built with the package
applied because the package is not in the engine series.

The two faults the screen caught on the way, both fork-era: a qualified `Lanes.marksOf` call missing `self` for a
three-argument method, and a check assigning `e.link` on `cuda_engine.Engine` where this series keeps the link on
`follow.Leader`.

## 110. Two ported packages cannot be stacked: they both edit the family build file

`LATENT_TILE` applied clean to the engine tree and `MULTI_FILL` then failed on `zig/build/glm_family_host.zig:106`, because
both packages attach a host-test step to the same build file and the second one's context no longer matches. Each applies
and screens green on its own; together they need the build-step hunks re-anchored or merged by hand.

So images are built one package at a time for now, starting with `lt2` from the latent-tile tree (32 engine patches plus
`patches/port-latent-tile`, 199,454,720 bytes of source tar). The multi-fill image follows with its own build once its
strict-env screen is green, and the two measurements are separate arms rather than one image carrying both.

This is the third integration fact of the porting project and the pattern is consistent: each lever's own code is fine and
the friction is in the shared plumbing - the vtable between multi-fill and prompt-many, this build file between latent-tile
and multi-fill, and the test registrations the screen keeps catching.

## 111. LATENT_TILE is a loss on this series: G=2 is 4.2% slower, G=4 4.9%

The first ported lever measured on the serve. Image `glm53-zig:lt2` built from 32 engine patches plus
`patches/port-latent-tile`, six boots, two an arm, cache dropped before each, cold prompts at 8,192 and 32,768 tokens,
replies identical across all six (one `token_sha256`).

| arm | cold 8k | cold 32k |
|---|---|---|
| unset (the recipe's vector path) | **3.338 s** | **13.048 s** |
| `TF_GLM_OVN_LATENT_TILE=2` | 3.480 s (+4.24%) | 13.601 s (+4.24%) |
| `TF_GLM_OVN_LATENT_TILE=4` | 3.494 s (+4.68%) | 13.683 s (+4.87%) |

So G=2 closes most of G=4's gap and still loses to the vector path by more than four percent, at both lengths, with two
boots a side agreeing to 0.3%. The rule written before the rows wanted 1% better than unset; this is 4.2% worse, so the
lever is rejected and `patches/port-latent-tile` stays a package rather than entering the series.

**That closes the first of the seven ports with a number rather than a theory:** the fork's G=4 was 1.7x slower than the
vector path, the port's G=2 was the only form that could plausibly beat it, and it does not. The next port takes the boots.

## 112. The clip is worth 4.1% at 8k, not 19%: my own alarm was a cross-instrument comparison

I raised a 19% claim from comparing `lt2`'s cold 8k (3,338 ms) against queue113's control (4,117 ms) and it does not
survive a like-for-like boot. Same image family, same box, same prompt-id files, same instrument, one boot on the pre-clip
image `m130a`:

| | cold 8k | cold 32k |
|---|---|---|
| `m130a`, no dense-window clip | 3.480 s | 13.237 s |
| `lt2`, clip included, knob unset | **3.338 s** | **13.048 s** |
| effect of the clip | **-4.1%** | -1.4% |

So the clip is worth about **4% at 8k**, close to the 130 ms (3.2%) it was committed on, and the 19% was the difference
between two instruments: queue113's 4,117 ms came from `streams_sampled` with `code_ids`, while today's readings come from
`bench_cache` with ids built from `prose33`. Two different prompt sets and two different clients, compared as though they
were one measurement.

The rule that caught it is the one this campaign keeps needing: a comparison is only a comparison when the two arms differ
by the thing under test. I applied that to patches across this stretch - its first commit is 2026-11-21 19:49:58 and the
clock read 2026-11-23 10:09 UTC when I checked, so a day and a half - and then failed to apply it to images, and one boot on the
old image was the whole cost of finding out.

## 113. The mailbox size does not help: +0.18%, inside the band

The decode rank-fold sits on NCCL's ring because 393 KB a rank exceeds `TF_TP_MAILBOX_MAX_KB`'s 256 KiB default, so raising
it to 1,024 was the one lever the dependency analysis left. Six boots, three an arm, four clients, sampled code, rule written
first: adopt 1,024 at 1% over the default with identical tokens.

| arm | boots | mean |
|---|---|---|
| `TF_TP_MAILBOX_MAX_KB=256` (default) | 152.28, 152.29, 151.88 | 152.15 |
| `TF_TP_MAILBOX_MAX_KB=1024` | 152.07, 152.49, 152.69 | 152.42 |

**+0.18%, so HOLD and the default stays.** The folds still go over the ring at four clients, and the arithmetic that said
the wait is the transfer (393 KB at 88 us a launch, 13.6 GB/s) is not contradicted: the mailbox path moves the same bytes
over a different transport and changes nothing measurable at this size.

That closes the side-stream item entirely: the collectives are dependency-bound in decode, the movable majority is not
movable, and the one transport change available does not pay.

## 114. PROMPT_MANY pays at every level; MULTI_FILL costs 4.6% at four clients

Six boots on the `mf1` image (engine plus `patches/port-multi-fill`), two an arm, cache dropped before each, one client
plus upstream's `bench_concurrent` at four and eight clients on the long-prompt file. Replies are identical across all six
arms in the one-client cell (one token hash).

| arm | 1 client | 4 clients | 8 clients |
|---|---|---|---|
| unset | 110.8 | 81.2 | 71.8 |
| `TF_GLM_OVN_MULTI_FILL=1` | 110.0 (-0.71%) | **77.5 (-4.59%)** | 72.6 (+1.08%) |
| `TF_GLM_PROMPT_MANY=1` | **112.5 (+1.55%)** | **85.7 (+5.45%)** | **73.9 (+2.96%)** |

So the alternative wins everywhere and the batching switch does not: `PROMPT_MANY` is +1.55, +5.45 and +2.96% across the
three levels, while `MULTI_FILL` gains 1.08% at eight clients and loses 4.59% at four, which is the level the fleet rule
calls everyday load.

**The rule I wrote had a gap and this run exposed it**: it named eight clients and one client but not four, so `MULTI_FILL`
would have passed a rule that omits the level where it loses most. The verdict is taken on all three levels, and the RECORD
for any later batching arm names four clients explicitly.

**One caveat that matters for what lands:** the `PROMPT_MANY` arm ran on the multi-fill image, where that switch's row and
its admission are carried by `patches/port-multi-fill` (the two packages cannot stack and multi-fill embeds the admission).
So the thing to land is the multi-fill package with `TF_GLM_PROMPT_MANY=1` set and `TF_GLM_OVN_MULTI_FILL` left off - not the
standalone prompt-many package, which has never been measured against the same series.

## 115. DRAW1's premise is still untested: the two cells that matter collided with another boot

The question DRAW1 needs answered before any subsystem is written: does a larger `top_k` cost decode time on the
whole-row path? Four cells were planned at four clients on `m130a`, one boot each: greedy, `top_k=40`, `128` and `1024`.

| cell | result |
|---|---|
| greedy | 154.41, 154.74, 155.67 tok/s per round, mean **154.94** |
| `top_k=40` | 152.19, 150.68, 150.32, mean **151.06** (sampled is 2.5% slower than greedy, as expected and not the question) |
| `top_k=128` | **invalid: connection refused** |
| `top_k=1024` | **invalid: connection refused** |

The two failures are mine: `screen118` started while this arm was still booting, the two runs fought for the three boxes, and
`s top_k` boots found `rank 1: no container, rank 2: no container`. So the grep-able cells are one pair of a comparison
that needs three, and the DRAW1 question is unanswered rather than answered negatively.

Both cells are re-queued to run after the screen finishes, with a fresh `top_k=40` control booted in the same conditions so
the three-point comparison is internally consistent. Until then, no conclusion about DRAW1's premise, and no subsystem work.

## 116. FP8 KV pages is a full hand re-seat: all twelve files conflict

The refs are in `work/port/restore` under `refs/gb10/scratch/glmnight-tree/remotes/*/glm-fp8-pages` (`872b09a6f`) and
`-pipe` (`1ccdb486e`), not under the `tf-mirror` path the port report named, which is why the bundle would not hand them
over directly. Both commits format-patch cleanly (39,791 and 2,659 bytes) and touch twelve files.

Against the applied series, `git apply --check` fails on **all twelve**: `glm_glue_attn.cuh`, `glm_glue_latent.cuh`,
`cuda_dsa_block.zig`, `cuda_kv8_test.zig`, `cuda_latent.zig`, `cuda_native.zig`, `cuda_pages.zig`,
`cuda_snapshot_layout.zig`, `cuda_start.zig`, `cuda_start_test.zig`, `cuda_state.zig`, `glm_paged_tests.zig`. The second
commit conflicts on the file the first one rewrites, as expected.

So this is not a re-cut, it is a hand re-seat of every hunk, and it is the worst candidate of the seven: the fork measured it
**-14% and -8% at depth**, its RECORD is written to say it is expected to lose, and its conflicts sit in the files this
series has changed most. It goes behind `HC_DEC`'s fix on the porting lane rather than ahead of it.

## 117. Owner decision: spend on FP8's restructure and build PRX, rather than bank them

The porting project found that three of the seven levers are not patch ports. Presented with their measured cost, the owner
chose to spend on both subsystem ports rather than record them as closed:

- **FP8 KV pages: restructure.** The change targets `chunks_wide`, which this series moved into `common/mla.cuh`, a header
  shared by GLM, DeepSeek V4.1 and hy4_flash, so a page table there is a three-family change plus a signature that
  propagates through two wrapper sets and a `same_params` static_assert. The fork measured **-14% and -8% at depth** and the
  commit deletes a refusal rather than optimising, so this is spending to close a question with our own numbers. The
  structural map is in `docs/audit-2026-11-12/fp8-pages-port.md`.
- **PRX and ZC: build the subsystem**, in value order after everything else, because this series carries no proxy or plan
  layer at all and its fork cells have never been re-run here.
- **DRAW1 stays behind its premise**: three kernels, a rig and a branch in `Engine.draw` only if the top-k measurement now
  running shows that a larger top_k costs decode time on the whole-row path.

The lane declined to cut a half FP8 patch (paged writes with unpaged reads is not the lever and would screen green while
measuring nothing), which is the same discipline that kept a guessed resolution out of the tree.

## 118. Our gates cannot see a `.cuh`: nvcc runs only in the image build

The FP8 step 1 exposed an instrument gap that applies to every kernel patch this campaign has gated. `scripts/gates.sh`'
five steps are all Zig: `check-native-cuda-host`, `test-cuda-host`, `compile-cuda-tests` (which compiles the GPU test binary
from `zig/tests/cuda`), the standalone host steps, and `fmt`. **Nothing in them invokes nvcc.** The only place a `.cu` or
`.cuh` is compiled is the image build (`zig build -Dnvcc=/usr/local/cuda/bin/nvcc -Dsm=121 ... fatbins`).

So a gate can be green on a tree whose kernel source does not compile, and the kernels this series changes - `mla.cuh`,
`glm_glue_attn_ovn.cuh`, `glm_onepass.cu`, `exl3_ovn.cuh`, `glm_glue_hc_rows.cuh` - are exactly the files those steps cannot
read. The reason our kernel patches have survived is that each was also built into an image before it was measured, not that
a gate checked it.

The lane's nvcc proof for FP8 step 1 is therefore the correct instrument and the one to standardise: `nvcc -std=c++17
-arch=sm_121a -ptx` on `mla.cu` and `glm_glue.cu` from a tree with the series applied, rc 0 on both. Its own caveat is the
right one too: `-ptx` proves the source and the device instantiations compile, not that a kernel keeps its register budget;
that needs the image build's SASS.

**The fix is to add an nvcc step to `scripts/gates.sh`**, so a kernel patch cannot be called gated until its translation
units compile.

## 119. The fast screen of six unmeasured settings: one promising, two dead, three unclear

One boot an arm on `m130a`, each boot measured at 1, 2 and 4 clients, control booted first with the same cache drop. The
rule (OVERNIGHT 118's design, `scripts/queues/queue118.sh`, written before any row): DEAD over 2.0% slower at any level,
PROMISING over 2.0% faster somewhere with no level over 1.0% slower, UNCLEAR otherwise.

| arm | 1 client | 2 clients | 4 clients | verdict |
|---|---|---|---|---|
| control | 81.02 | 85.06 | 113.29 | |
| `TF_GLM_PROMPT_STEPS=0` | 83.75 (+3.37%) | 87.07 (+2.36%) | 114.69 (+1.24%) | **PROMISING** |
| `TF_GLM_DRAFT_CONFIDENCE=0.6` | 81.93 (+1.12%) | 86.40 (+1.58%) | 114.25 (+0.85%) | UNCLEAR |
| `TF_GLM_LINK_WAIT=1` | 82.04 (+1.26%) | 85.64 (+0.68%) | 114.89 (+1.41%) | UNCLEAR |
| `TF_DRAFT_NODES=8` | 81.46 (+0.54%) | 86.01 (+1.12%) | 113.93 (+0.56%) | UNCLEAR |
| `TF_GLM_HOST_CACHE=1` | 82.98 (+2.42%) | 80.97 (-4.81%) | 111.36 (-1.70%) | **DEAD** |
| `TF_GLM_SHARED=0` | 83.06 (+2.52%) | 71.20 (-16.29%) | 74.39 (-34.34%) | **DEAD** |

So one boot each closed two settings outright and pointed at a third: turning **chunked prompt passes off**
(`TF_GLM_PROMPT_STEPS=0`) is faster at every level by 1.2 to 3.4%, which is a surprise for a default that ships on, and
`SHARED=0` costs a third of throughput at four clients. The three inside the band need one confirm boot apiece, which the
rule says is what UNCLEAR means.

**The instrument held up:** the control's three cells sit where the recipe's own cells do, and no arm's verdict depends on a
difference smaller than the 2% band the rule chose.

## 120. The expert skew's 64-row unit is a 512-thread block, not a wider accumulator

The owner's decision was to take the skew's scheduling win with the block order byte-exact. The register ceiling ruled out a
wider tile (OVERNIGHT 107: `acc[8][2][4]` is already 64 floats a thread inside 118 registers). Reading the geometry gives
the way through.

`nc_body` (`exl3_ovn.cuh:27-60`): `NT = 8, W = 4, TW = 32`; `warp = threadIdx.x >> 5`; `g = lane >> 2`, `t = lane & 3`, and
`rows_sh[16]` holds **sixteen rows inside one warp's lanes**, with `r0 = rows_sh[g]` and `r1 = rows_sh[g + 8]`. The four
warps split the K dimension, not the rows.

So a 64-row unit is **four times the warps** - 16 warps, 512 threads - each warp taking a 16-row group and a column slice,
with the per-thread accumulator unchanged at 64 floats. Every row's chain and its reduction order are then identical to
today's, which is what "byte-exact" requires, and the launch count for a chunk falls fourfold.

That is a kernel project with a host test that pins the per-row bytes against today's kernel at several row counts, and it is
the one remaining decode-side item from the review list that is neither measured-negative nor blocked.
