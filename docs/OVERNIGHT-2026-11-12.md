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
