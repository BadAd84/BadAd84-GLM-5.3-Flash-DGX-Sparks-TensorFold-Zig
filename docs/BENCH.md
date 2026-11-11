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

(filled from the runs)
