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

## State

Phase 1 (clean pin, drafts on) = the `pin-drafts` cell. Phase 2 (env batches on the pin) =
`pin-b1-l2pf`, `pin-b2-rows`, `pin-b3-fill`, running as `work/batches.sh`. Phase 3 arms are built from
the block table above once those land.
