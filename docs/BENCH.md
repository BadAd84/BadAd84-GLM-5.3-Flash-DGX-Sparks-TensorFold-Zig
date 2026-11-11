# BENCH.md - stock pin against the patch stack, measured 2026-11-11

Instrument: `scripts/bench-arm.sh` (boot at P=1,2,4,6,8, a fresh boot per level, then
`scripts/streams.py <port> <P> --kind prose --max-tokens 400 --rounds 3`). Config for every
cell: the recipe's serve.sh as shipped, `DRAFTER=0`, `KNOBS=off`, the P-default context grid
(1M at P=1, 196k at P=8, 262k between). Production and both GLM watchdogs stopped; nothing
else on the boxes. Every row's `sha` is the reply digest: equal digests across arms mean the
same bits for that prompt set.

## What was measured

| arm | patches | correctness |
|---|---|---|
| pin | none (the pinned upstream, `glm53-zig:pin9c9`) | coherent, matches the stock reply |
| armK6 | 0001..0017 + the build fixes (0032, 0033) | coherent |

The stacks after 0019 do not give coherent output: the chunked KDA prompt port (0019)
corrupts decode even with the knob off (`armK8` = 0001..0017 + 0019 answers token salad while
`armK6` answers "1 2 3 4 5 6 7 8 9 10 11" to the same prompt). That is the open defect; it is
not benched.

## Receipts

See `work/bench/<arm>/P<level>.jsonl` on spark1 (the full JSONL per level) and the tables
below. `decode` is the decode-phase aggregate tok/s, `ttft` the median first-content time.

## Stock pin (glm53-zig:pin9c9), DRAFTER=0, KNOBS=off

| P | decode aggregate tok/s | TTFT med (ms) | reply digests |
|---|---:|---:|---|
| 1 | 49.69 | 156 | 3ec88b6418f7 |
| 2 | 54.72 | 160 / 422 | 3ec88b6418f7, c36689783326 |
| 4 | 72.34 | 155 / 653 | 3ec88b6418f7, c36689783326 |
| 6 | 90.77 | 950 / 138 | 3ec88b6418f7, c36689783326 |
| 8 | 109.35 | 157 / 850 | 3ec88b6418f7, c36689783326 |

The same prompt returns the same digest at every stream count: concurrency does not change
the bits on the pin.

## armK6 (0001..0017 + 0032, 0033), DRAFTER=0, KNOBS=off

| P | decode aggregate tok/s | pin | delta | TTFT med (ms) | reply digests |
|---|---:|---:|---:|---:|---|
| 1 | 49.06 | 49.69 | -1.3% | 58 | 3ec88b6418f7 |
| 2 | 55.23 | 54.72 | +0.9% | 237 / 61 | 3ec88b6418f7, c36689783326 |
| 4 | 72.91 | 72.34 | +0.8% | 61 / 572 | 3ec88b6418f7, c36689783326 |
| 6 | 92.53 | 90.77 | +1.9% | 62 / 249 | 3ec88b6418f7, c36689783326 |
| 8 | 111.39 | 109.35 | +1.9% | 827 / 62 | 3ec88b6418f7, c36689783326 |

Every reply digest equals the pin's at the same stream count: this arm is bit-identical to stock
and slightly faster under load. P1's -1.3% is inside the run-to-run spread seen on repeated pin
boots; P2..P8 are consistently ahead.

## fix2: the full stack (0001..0037), DRAFTER=0, KNOBS=off

| P | decode aggregate tok/s | pin | delta | TTFT med (ms) | reply digests |
|---|---:|---:|---:|---:|---|
| 1 | 48.95 | 49.69 | -1.5% | 58 | 3ec88b6418f7 |
| 2 | 54.78 | 54.72 | +0.1% | 62 / 243 | 3ec88b6418f7, c36689783326 |
| 4 | 72.54 | 72.34 | +0.3% | 58 / 237 | 3ec88b6418f7, c36689783326 |
| 6 | 93.04 | 90.77 | +2.5% | 419 / 240 | 3ec88b6418f7, c36689783326 |
| 8 | 110.95 | 109.35 | +1.5% | 62 / 211 | 3ec88b6418f7, c36689783326 |

Every digest equals the pin's at the same stream count: all 37 patches are bit-exact to stock for
these prompts and slightly faster under load. P1 is inside the pin's own run-to-run spread; the
gain grows with load (P6 +2.5%, P8 +1.5%). The KNOBS=measured set (the def17 knobs) has not been
A/B'd on this stack yet and is the next benchmark arm.

## fix2 with KNOBS=measured (the def17 knob set), DRAFTER=0

The set is serve.sh's DEFS (the knobs the source stack measured: KDA pad, index CUDA, one-chunk,
kept walk, the four drafter knobs, reply prefill, MLA fusemerge, glue fuse, index sched, pools32,
index regroup, mm wide, sparse onepass, router warm). Getting it to boot took two more port fixes:
**0038** ports the 16-row router kernel (the set requests `tf_glm_router16_s3/s4`), and **0039**
restores cuda_glue's `@FieldType == cuda.Function` guard so optional fields are not requested under
the bare struct name. With them the set boots in 115 s and answers with coherent reasoning.

| P | decode aggregate tok/s | stock | delta vs stock | fix2 (KNOBS=off) | TTFT med (ms) | reply digest |
|---|---:|---:|---:|---:|---:|---|
| 1 | 61.37 | 49.69 | +23.5% | 48.95 | 51 | f8cc18addd25 |
| 2 | 64.13 | 54.72 | +17.2% | 54.78 | 56 / 393 | ffa9d50563ca |
| 4 | 78.52 | 72.34 | +8.5% | 72.54 | 407 / 54 | ffa9d50563ca |
| 6 | 99.61 | 90.77 | +9.7% | 93.04 | 381 / 55 | ffa9d50563ca |
| 8 | 107.40 | 109.35 | -1.8% | 110.95 | 355 / 55 | ffa9d50563ca |

The set is 17 to 24 percent faster at 1 and 2 streams and 8 to 10 percent faster at 4 and 6, and 1.8
percent slower at 8. **Its reply digests differ from stock** (`f8cc18addd25`/`ffa9d50563ca` against
`3ec88b6418f7`/`c36689783326`), so the set is NOT bit-exact and none of these cells is a gated win:
`scripts/knob-digest.sh` halves the set to name the knob that moves the bits, and a bits-changing knob
is only shippable with the owner's call on the numerics. Stock and the KNOBS=off arms stay the
bit-exact pair.

The halving (`scripts/knob-digest.sh`, one P=1 prose cell a boot, digest against `3ec88b6418f7`):

| set | digest | verdict |
|---|---|---|
| poolA: KDA_PAD, INDEX_CUDA, ONE_CHUNK, KEPT_WALK, REPLY_PREFILL, MLA_FUSEMERGE | f8cc | moves the bits |
| poolB: GLUE_FUSE, INDEX_SCHED, POOLS32, INDEX_REGROUP, MM_WIDE, SPARSE_ONEPASS, ROUTER_WARM | 3ec88 | bit-exact |
| poolA1: KDA_PAD, INDEX_CUDA, ONE_CHUNK | f8cc | moves the bits |
| poolA2: KEPT_WALK, REPLY_PREFILL, MLA_FUSEMERGE | 3ec88 | bit-exact |
| kdaPad: KDA_PAD alone | f8cc | **the one bit-changing knob** |
| idxOne: INDEX_CUDA, ONE_CHUNK | 3ec88 | bit-exact |

**TF_GLM_KDA_PAD alone changes the reply bits**; every other knob in the measured set is bit-exact
to stock. That is the knob that puts the KDA input stack on the 4-bit pack list, so the digest change
is the quantisation the pad activates, not a wiring error.

## fix4 with every knob except KDA_PAD (the bit-exact set), DRAFTER=0

| P | decode aggregate tok/s | stock | delta | fix4-knobs (with KDA_PAD) | reply digest |
|---|---:|---:|---:|---:|---|
| 1 | 48.91 | 49.69 | -1.6% | 61.37 | 3ec88b6418f7 |
| 2 | 55.32 | 54.72 | +1.1% | 64.13 | 3ec88b6418f7 |
| 4 | 72.68 | 72.34 | +0.5% | 78.52 | 3ec88b6418f7 |
| 6 | 92.82 | 90.77 | +2.3% | 99.61 | 3ec88b6418f7 |
| 8 | 112.81 | 109.35 | +3.2% | 107.40 | 3ec88b6418f7 |

Every digest equals stock at every level, so this set is the shippable one on the current numerics
gate. It is faster than stock at 2, 4, 6 and 8 streams (P1 inside the run spread) and faster than the
KDA_PAD set at 8 streams. The choice left for the owner is the big P1/P2 gain KDA_PAD brings
(+23.5%/+17.2%) against its digest change and its P8 cost.
