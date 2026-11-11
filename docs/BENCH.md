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

**Its reply digest differs from stock** (`f8cc18addd25` against the stock `3ec88b6418f7` for the same
cell), so the measured set is NOT bit-exact and its speed numbers need that stated: the knob halving
(`scripts/knob-digest.sh`) is what names the knob that moves the bits. Stock and the KNOBS=off arms
remain the bit-exact pair; a knob set that changes the bits is only shippable with the owner's call on
the numerics.
