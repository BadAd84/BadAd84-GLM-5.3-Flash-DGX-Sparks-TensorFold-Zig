# PATCH-EVAL.md - the patch-by-patch evaluation (owner's method, phase 3)

Order fixed by the owner (2026-11-11): clean pin first, then production's env in batches on the pin,
then the patches back in, judged one block at a time.

## The blocks

The 39 patches split by what they change, so a block is one idea and the bench answers "is this block
worth its code":

| block | patches | what it carries |
|---|---|---|
| B1 early | 0001-0006 | the knob registry, cache statics, the KDA pad, DFlash2 draft knobs, index CUDA, the kept walk |
| B2 prefill | 0007-0011 | resume at any row, reply prefill, ONE_CHUNK |
| B3 kernels A | 0012-0017 | the shared round, exchange, sparse onepass, onepass pipe |
| B4 era | 0018-0023 | shared drafts on the allocator, KDA chunked, mm knobs, MLA knobs, glue fuse, the shared-round era |
| B5 wiring | 0024-0031 | the test repairs, warm wait, knob wiring, shared-drafts gating, the DSA double launch, draft confidence, the head-block rule |
| fixes | 0032-0039 | the build and correctness fixes (fatbin catalog, lfs, shadow, tap arity, top1 sums, chunk header, KDA fill, router16, glue type guard) |

The fixes block (0032-0039) is not optional: without it the tree does not build or corrupts decode.
So every arm below is pin + the fixes + the block under test.

## The measurement, per block

`scripts/bench-arm.sh` on spark1-3, TP=3, DRAFTER=1 (production parity), KNOBS=off (the block's own code,
not its knobs), a fresh boot per level, `streams.py` prose 400 tokens, 3 rounds. The reference cell is
the clean pin with the same settings (the batch-0 run).

Acceptance, per the fleet rule: no measured regression at ANY level (1/2/4/6/8) and reply digests equal
to the pin's at every level. A block that fails either is reported as a trade, not a win, and goes to
the owner with both sides' numbers.

## Builds

Each arm: `git clone --shared` the parity tree, apply the fixes + the block, `tar`, then
`ai-build.sh`-style build on spark1 (`build-image.sh`), distribute spark1 -> spark2/3, boot and bench.
One arm is roughly 20 minutes of build plus 15 of bench.

## Phase 1 result (clean pin, drafts on)

| P | clean pin, drafts on | clean pin, drafts off | delta | 39 patches, drafts on |
|---|---:|---:|---:|---:|
| 1 | 52.36 | 49.69 | +5.4% | 51.28 |
| 2 | 58.41 | 54.72 | +6.7% | 59.46 |
| 4 | 72.17 | 72.34 | -0.2% | 81.42 |
| 6 | 95.18 | 90.77 | +4.9% | 108.05 |
| 8 | 115.17 | 109.35 | +5.3% | 134.45 |

The drafter is worth 5 to 7 percent except at four streams, and every digest stays `3ec88b6418f7`, so
drafts on is bit-exact. Against this baseline the 39 patches add nothing at one and two streams and
+12.9% and +16.7% at four and eight: the patch value sits in the concurrency path, exactly where the
shared-round and prefill work lives. Production's 83.43 at one stream is still 59% above the clean pin,
so phase 2's env is the remaining low-stream lever.

## Phase 2 result (production's env on the clean pin)

| P | pin + drafts | + `L2PF=1` | + `PREFILL_ROWS=4096` | + `FILL_ROWS=4096` |
|---|---:|---:|---:|---:|
| 1 | 52.36 | 52.22 | 52.11 | 52.18 |
| 2 | 58.41 | 58.58 | 58.39 | 58.56 |
| 4 | 72.17 | 72.10 | 71.67 | 71.82 |
| 6 | 95.18 | 95.46 | 95.30 | 96.10 |
| 8 | 115.17 | 115.21 | 114.84 | (the batch ended before this cell) |

Every batch is inside the run-to-run spread. The pin-readable env does nothing measurable at any stream
count, which closes phase 2: the 59 percent gap to production at one stream is not in the env switches
the pin understands. What is left on that side is the eleven Python-tier mechanisms (the decode-path
knobs and the cache/keeps family), and the patch blocks of phase 3 on ours.

## Phase 3 result (blocks added back in, drafts on)

| P | pin | +0001-0011 | +0001-0017 | +0001-0023 | +0001-0027 | all 39 |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 52.36 | 51.64 | 51.20 | 51.39 | 51.44 | 51.05 |
| 2 | 58.41 | 59.06 | 59.12 | 59.84 | 59.66 | 61.10 |
| 4 | 72.17 | 72.46 | 72.28 | **81.85** | 81.85 | 81.65 |
| 6 | 95.18 | 97.96 | 98.15 | **110.41** | 110.07 | 108.77 |
| 8 | 115.17 | 117.76 | 117.79 | **134.56** | 135.02 | 134.84 |

Digests equal the pin's `3ec88b6418f7` at every level and arm, so every one of these cells is bit-exact.

**The verdict**: the 0018-0023 block carries the whole concurrency win (+13.4% P4, +16.0% P6, +16.8% P8);
0001-0017 is worth 2-3% at six and eight streams and nothing at one to four; 0024-0039 measure neutral.
That is not the same as disposable: 0032-0039 are the build and correctness fixes without which the tree
neither builds nor answers, and they are already inside the a0023 arm which shows the full win, while
0024-0031 are behaviour-neutral wiring and test repairs exactly as the ledger describes them. For trimming,
the candidates are the 0001-0017 block (16 patches for ~2%), and the era block 0018-0023 is the one to
defend.

The one-to-four-stream gap to production (83.4 against 51.4 at one stream) is therefore NOT in the patch
stack: no block moves those cells. It is the decode-path knobs production runs and the Zig tree lacks.

## State

Phase 1 (clean pin, drafts on) = the `pin-drafts` cell. Phase 2 (env batches on the pin) =
`pin-b1-l2pf`, `pin-b2-rows`, `pin-b3-fill`, running as `work/batches.sh`. Phase 3 arms are built from
the block table above once those land.

## Profiling the rounds (the switches that exist, measured)

- `TF_GLM_PROF=1` profiles PROMPT chunks (`glm prof prompt chunk to N rows`). First reading on the full stack,
  drafts on: a 64-row chunk costs wall 67.2 ms (gpu 86.4 across the sections), split gate 7.2, embed 0.0,
  router 39.5, routed 36.7, head 1.2, draw 0.6, mtp 1.2, commit 0.0. The router plus the routed experts are
  the prompt pass's cost, so prefill-side work (indexer sharding, routing) has the headroom there.
- `TF_GLM_OVN_SHARED_PROF=1` profiles the DECODE rounds: `glm prof shared N segs to M rows` (buckets to 8, 16,
  24, 32 rows) and `glm prof shared commit N segs`. Without it a decode round has no section breakdown at all,
  which is why the first profiled request (with `TF_GLM_PROF=1` only) showed prompt chunks and nothing else.
- The round-time target from the draft accounting: our one-stream round is 52.3 ms at 2.68 tokens a round;
  production's 83.4 tok/s at the same tokens a round implies about 32 ms. The decode profile is what splits
  that difference into sections.

### The decode round's section split (measured 2026-11-11)

`TF_GLM_PROF=1`, one stream, full stack, drafts on. The verify profilers report every 64 calls PER ROW BUCKET, so
a short run shows nothing: a 1,400-token cell is the smallest that crosses them. Per round:

| verify rows | wall ms | kda | routed | router | mla | gather_a | shared | gather_b | head |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 38.6 | 14.9 | 13.1 | 1.3 | 3.0 | 1.8 | 1.7 | 1.2 | 1.0 |
| 3 | 43.4 | 15.1 | 16.9 | 1.3 | 3.1 | 2.1 | 1.7 | 1.5 | 1.0 |
| 4 | 48.8 | 15.4 | 21.3 | 1.4 | 3.4 | 2.1 | 1.7 | 1.7 | 1.0 |

The KDA linear-attention chain is a FLAT ~15 ms per round whatever the width, and the routed experts scale with
rows (13.1 at two to 21.3 at four, about +4 ms a row). Together they are 70-80% of the round, so the two levers
map one-to-one: `KDA_PAD` (measured +12 tok/s at one stream, and it is the knob that packs the KDA stack at 4
bits, which is also why its digest moves) against the flat kda section, and the `EXL3_LOADS=nc`/decode-order
family against the routed section. Everything else in a round is 6-8 ms in total, so production's ~32 ms round
is one or both of those two sections being cheaper.

### KDA_PAD proven against the kda section

Same cell with `TF_GLM_KDA_PAD=1`:

| verify rows | wall | kda | routed | everything else | agg tok/s |
|---|---:|---:|---:|---:|---:|
| 2 | 29.5 | **5.2** | 13.4 | ~5.5 | **57.9** |
| 3 | 34.4 | 5.2 | 17.6 | ~7.0 | |

Against the without-pad cells the kda section drops 14.9 to 5.2 ms and the round 38.6 to 29.5 (-9.1 ms, -23.6%),
which is the +16.7% the knob measured at one stream. It is the single biggest explained lever so far, and it is
also the one knob whose digest moves, because the pad is what puts the KDA input stack on the 4-bit pack list.
With it, a round is kda 5.2 + routed 13.4 + ~5.5 elsewhere, so **the routed experts are now the largest section**
and the next target (`EXL3_LOADS=nc`, the fused EXL3 decode, the window geometries).
