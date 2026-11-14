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
