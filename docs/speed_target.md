# speed_target.md - the production Python engine's numbers, the parity target

Measured on the LIVE production serve, as deployed: spark1-3, `glm53-flash-tf` (the Mia-AI-Lab
TensorFold Python recipe, tf-v110 stack), TP=3, `--parallel 4`, thinking on, the EXL3 4bpw checkpoint
at rev `078455ffe`, the DFlash2 drafter. Production was otherwise idle (its request counter flat)
while the cells ran.

Instrument: the same one the Zig arms are measured with, `scripts/streams.py 8888 <N> --kind prose
--max-tokens 400 --rounds 3`, run from spark1 against `127.0.0.1:8888`. Aggregate tok/s is measured
across the N streams of a round while all of them decode; TTFT is the first content chunk per stream.

## The target (production, Python, tf-v110, --parallel 4)

| streams | aggregate tok/s | TTFT (ms) |
|---:|---:|---|
| 1 | 83.43 | 122 |
| 2 | 91.07 | 157 / 156 |
| 4 | 119.97 | 228 / 228 |
| 6 | 111.99 | 232 / 232 / 230 |
| 8 | 136.18 | 128 / 332 / 9710 |

Its reply digests (`8347edfe4ee6` / `66b9fe5c1ea4`) are the Python engine's own tokens; the Zig stack
answers these prompts with different tokens (`3ec88b6418f7` / `c36689783326`). Speed is the parity
target here; token-for-token agreement across the two engines is not claimed.

Note the serve's own `--parallel 4`: beyond four streams the requests queue, which is production's
real behaviour and is the number to match. That shows in the cells: six streams dips to 111.99 before
eight recovers 136.18, and the eight-stream TTFT has a 9.7 s outlier where a request waited for a slot.

## The comparison caveat that decides the gap

Production runs the DFlash2 drafter (speculative decode), and every Zig number in the table below was
measured with DRAFTER=0. At low stream counts the drafter is worth roughly 1.5x to 2x, so the raw
difference (production 83.4 at one stream against the Zig 49.7) is not yet a code gap; the Zig stack
must be measured with drafts on before the gap is attributed. That arm is the next measurement.

## Where the Zig stack stands against it

From `docs/BENCH.md` (same instrument, same prompts, TP=3 on spark1-3, DRAFTER=0, KNOBS=off unless
stated):

| streams | production (Python) | Zig 39 patches, drafts on | delta | Zig stock pin | Zig 39 patches, drafts off |
|---:|---:|---:|---:|---:|---:|
| 1 | 83.43 | 51.28 | -38.6% | 49.69 | 48.95 |
| 2 | 91.07 | 59.46 | -34.7% | 54.72 | 54.78 |
| 4 | 119.97 | 81.42 | -32.1% | 72.34 | 72.54 |
| 6 | 111.99 | 108.05 | -3.5% | 90.77 | 93.04 |
| 8 | 136.18 | 134.45 | -1.3% | 109.35 | 110.95 |

The shape of the gap is the useful result: at six and eight streams the Zig stack is at parity (within
1.3 to 3.5 percent) and at one to four streams production is 32 to 39 percent ahead. The drafts-on arm
also runs L2PF/PREFILL_ROWS/FILL_ROWS off (it predates their addition to the measured set), so those
three pin knobs are unmeasured headroom here. The low-concurrency lead matches production's
cache-and-keeps family (`CACHE_ENTRIES`, `KEEP_PER_CHAT`, `KEPT_BYTES_GIB`), which the Zig tree does not
have at all, on top of the prefill/overlap knobs.

Parity work: the gap per level is the production column minus the best bit-exact Zig column at that
level; the coverage and the open levers are tracked in PORT-LEDGER and BENCH.

## What production runs that the Zig recipe does not (the port queue)

Read from production's own launcher env (`~/v110ots.env` and `start-tp3.sh` on spark1; `TF_GLM_`)
and its container environment. None of these are in serve.sh's DEFS, so with `KNOBS=off` the Zig
stack runs without any of them, and that is the parity gap to close:

| knob | production value | tier | what it is |
|---|---|---|
| `TF_GLM_MULTI_WINDOW` | `32` | era | several decode windows in flight |
| `TF_GLM_DRAFT_WIDE` | `2176:prompt` | python | the drafter's wide prompt window |
| `TF_GLM_L2PF` | `1` | L2 weight prefetch beside decode windows |
| `TF_GLM_INDEXER_SHARD` | `prefill` | python | the indexer's sharded prefill |
| `TF_GLM_PREFILL_OVERLAP` | `2` | python | overlapping prefill work |
| `TF_GLM_EXL3_LOADS` | `nc` | EXL3 load path |
| `TF_GLM_EXL3_DEC_ORDER` | `1` | decode order |
| `TF_GLM_EXPERT_ROTATE` | `10,16,16` | era | expert rotation per rank |
| `TF_GLM_POOLED_PACK` | `2` | python | pooled packing |
| `TF_GLM_KEEP_PER_CHAT` | `2` | python | kept states per chat |
| `TF_GLM_KEPT_BYTES_GIB` | `8` | python | kept-state budget |
| `TF_GLM_KV_SHARD` | `1` | python | KV sharding across ranks |
| `TF_GLM_CACHE_ENTRIES` | `96` | python | prompt-cache entries |
| `TF_GLM_FILL_FAST_MS` | `400` | era | fill scheduling |
| `TF_GLM_PREFILL_ROWS` / `TF_GLM_FILL_ROWS` | `4096` | prompt pass rows |
| `TF_GLM_STREAM_SMOOTH` | `0` | python | stream smoothing off |
| `KV_POOL_GIB` | `31` | python | KV pool at boot |
| `DISPLAY_KV_MIB` / `DISPLAY_KV_BACKEND` | `2032` / `dispram` | python | the display-KV overlay (absent at the pin) |
| `SPILL_GIB` | `120` | python | the spill tier (the pin has `--spill-gib`/`--snapshot-dir` only) |

Tiers, by exact-name grep of the clean pin and the newer era tree (`ai-engine` fair-base): **pin** = the
pinned upstream already implements it, so it is an env switch today; **era** = absent at the pin but
implemented in the newer Zig tree, so the port has a reference; **python** = present only in the
production Python stack. Where the knobs stand at the pinned upstream (measured by grepping the clean pin tree, `work/pin/tree`,
for each name): only `TF_GLM_L2PF`, `TF_GLM_PREFILL_ROWS` and `TF_GLM_FILL_ROWS` exist there; the other
fourteen are absent from the whole pin, so they are not a wiring job in our GLM path but code the recipe
carries that upstream does not. Each is a port item: carry the knob's code as a numbered patch, prove it
bit-exact where the knob is numeric-only, and A/B it at 1/2/4/6/8 before it joins the measured set. The parked rows in
PORT-LEDGER already name several (MULTI_WINDOW, DRAFT_WIDE, the disk family); this table is the
target's own list, which is why it lives with the numbers.
