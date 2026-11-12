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

`scripts/gates.sh` runs the README's gates from WSL. On the tree through 0042: `check-native-cuda-host` exit 0,
`zig fmt --check zig/` exit 0, `test-cuda-host` 5,553 of 5,606 passed with 26 named failures, every one a
file-permission, symlink or FIFO test (`auth*`, `benchmark_*`, `request_log`, `drama_voice_tool`, `slide_key`) that a
tree on the Windows-mounted filesystem cannot pass; none is in the GLM family. The unpatched pin run in the same
place fails the same 26 names (5,494 of 5,547 passed) and `scripts/gate-names.sh pin fix6` prints no name that only
the stack fails, so the stack through 0042 is at the pin's result with 59 more tests, all passing.
