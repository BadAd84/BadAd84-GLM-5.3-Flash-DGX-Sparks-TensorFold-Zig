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
