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

## What the draft accounting says the gap is (2026-11-11)

First real numbers from `streams.py`'s draft record, full stack (39 patches), drafts on, one stream:

| round | agg tok/s | acceptance | tok/round | ms/round | drafted | accepted |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 50.89 | 0.596 | 2.68 | 52.3 | 421 | 251 |
| 1 | 51.13 | 0.596 | 2.68 | 52.1 | 421 | 251 |
| 2 | 50.87 | 0.596 | 2.68 | 52.3 | 421 | 251 |

**The drafter is not the problem.** 59.6% of drafts land and a round yields 2.68 tokens, both in the band Mia's
own records publish (60-64% and ~2.15). With 2.68 tokens a round, 50.9 tok/s means a 52.3 ms round; production's
83.4 tok/s at the same token-per-round would be a round of roughly 32 ms. **The one-to-four-stream gap is
per-round decode latency**, which is exactly where production's decode-path knobs live: EXL3 decode order, the
multi-window decode, its fused EXL3 decode and the window geometries. That is the target for the decode-side
port work, and acceptance is a healthy variable to hold fixed while chasing it.

## The comparison caveat that decides the gap

Production runs the DFlash2 drafter (speculative decode), and every Zig number in the table below was
measured with DRAFTER=0. At low stream counts the drafter is worth roughly 1.5x to 2x, so the raw
difference (production 83.4 at one stream against the Zig 49.7) is not yet a code gap; the Zig stack
must be measured with drafts on before the gap is attributed. That arm is the next measurement.

## Where the Zig stack stands against it

Current cells (2026-11-21): the recipe as committed on the pin, image `m130a`, `KNOBS=prod`, the boots of queue91 (`mn1`, `mn2`) and queue95 (`mn3`), three rounds a cell, the
campaign's own field (`agg_tok_s`, which is what `scripts/queue-scores/score91.py` reads). The production column is the MEAN of that serve's three rounds per level, in the same field:
its own run wrote `agg_tok_s` and `decode_agg_tok_s` per round (`work/drafter-lever/spark1/bench/pyprod/P<n>.out`, three rounds a file), and the earlier version of this table quoted
round 2's `decode_agg_tok_s` against our `agg_tok_s`, which is two different fields and, at six clients, one round of three whose own spread is 10%. Rows:
`docs/audit-2026-11-12/queue-rows/queue91/f91-c`, `.../queue95/f95-c`.

| streams | production, `agg_tok_s` mean of 3 rounds | Zig recipe, 2026-11-21 | delta |
|---:|---:|---:|---:|
| 1 | 81.73 | 82.72 | +1.20% |
| 2 | 89.22 | 85.85 | -3.78% |
| 4 | 117.98 | 114.27 | -3.14% |
| 6 | 114.78 | 114.68 | -0.09% |
| 8 | 131.28 | 125.32 | -4.54% |

Cold first token is where the gap actually is: production 2,908 / 11,054 / 41,904 ms against 3,990 / 14,910 / 55,653 ms at 8k / 32k / 120k, so 1.08 / 3.86 / 13.75 seconds behind
(OVERNIGHT section 72, the two-boot figures; with queue95's third boot of the same image and recipe the deficit is 1.11 / 3.95 / 14.12 s). A warm turn of a ~113k conversation is
1,313 ms against 668 ms (section 72), and 1,326 against 869 ms on queue100's control arm (section 80).

The shape of the gap, as corrected: decode at one stream is 1.2% AHEAD, at two and four it is about 3% behind, at six it is level, and at eight it is 4.5% behind with that cell's own
spread larger than the deficit (production's three rounds there are 129.36, 128.71 and 135.77 on `agg_tok_s`). **The prompt path is the real gap**, not decode: a cold 120k prompt is
about 14 s behind production and a warm resumed turn is about 2x it. The 11 November table of 39-patch drafts-off values, which called six and eight streams parity and one to four
32% to 39% behind, was measured on the v1.2.9-era stack before the draft, X3, item-plan and prompt work landed; it is superseded and its numbers are in git history.

Parity work: the gap per level is the production column minus the best bit-exact Zig column at that
level; the coverage and the open levers are tracked in PORT-LEDGER and BENCH.

## What production runs that the Zig recipe does not (the port queue)

Read from production's own launcher env (`~/v110ots.env` and `start-tp3.sh` on spark1; `TF_GLM_`)
and its container environment. None of these are in serve.sh's DEFS, so with `KNOBS=off` the Zig
stack runs without any of them, and that is the parity gap to close:

| knob | production value | tier | what it is |
|---|---|---|
| `TF_GLM_MULTI_WINDOW` | `32` | python | several decode windows in flight; with EXL3_DEC_ORDER this is the decode path the one-to-four-stream gap points at |
| `TF_GLM_DRAFT_WIDE` | `2176:prompt` | python | the wide prompt-chunk drafter (production notes 9.47-9.48): a drafter-path lever for the drafts-on runs, which is where the low-stream cells live |
| `TF_GLM_L2PF` | `1` | L2 weight prefetch beside decode windows |
| `TF_GLM_INDEXER_SHARD` | `prefill` | python | the indexer's prompt scoring split over ranks: production measures -12.8% cold at ~605k and -22% on a warm turn at ~596k, bits identical, so a long-context win that cannot move a 400-token cell |
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

Also measured: **cache and kept-state policy IS part of the warm-turn gap, though cache reuse at the pin was not.** The pin's serve already exposed `--prompt-cache-gib` and
`--prompt-cache-disk` and our boots log a 16 GiB prompt cache, so both engines keep prompt states, and the one-stream decode difference is in the decode path. But the warm resumed
turn is the largest single deficit (about 2x production), and two upstream switches move exactly it: `TF_CACHE_EVICT=decayed_resume` rebuilt 47.40% fewer prompt rows on six concurrent
conversations (14,396,073 to 7,572,137), cut the summed first-token times 47.16% and took an agent turn's mean first token from 23.7 s to 2.1 s, with 103 of 138 agent turns losing their
conversation's state without it and none with it (section 75); `TF_GLM_REQUEST_STARTS=1` takes 34.51% off a warm turn (section 80). Neither is the recipe's value: `TF_CACHE_EVICT` is set to its other word, `main`,
held by three 6- and 8-client decode cells inside their own spread (section 78), and `TF_GLM_REQUEST_STARTS` is set in no file at
all, held by six cells, one of them the cold 8k that `patches/solo-cuts` exists to fix (section 80); it is upstream's switch, not a
row of our table, so the env files do not carry it.

Tiers, by exact-name grep of the clean pin and the newer era tree (`ai-engine` fair-base): **pin** = the
pinned upstream already implements it, so it is an env switch today; **era** = absent at the pin but
implemented in the newer Zig tree, so the port has a reference; **python** = present only in the
production Python stack.

**This table is an 11 November snapshot and its absence count is obsolete.** It has 19 rows (two of them
pairs), three of which existed at the pin, so the earlier sentence here, "the other fourteen are absent",
never described it, and several rows have since been ported, adopted or superseded by upstream itself
(`TF_GLM_EXL3_DEC_ORDER`, kept states, `CHUNK_SOLO`, the GLM disk tier, request starts, `TF_GLM_DSCORES`
for the decode index, and upstream #3697's per-rank KDA padding). The current list of what is ours and what
upstream now does itself is the overlap ledger in `docs/KNOBS.md` and the per-patch audit in
`work/absorb/ABSORPTION.md`; a row of this table is a lead to check against those, not a current gap.

## The round-time target, as their production states it (MiaAI-Lab AGENT-v2, 2026-11-11)

Their served decode round, from their own agentic-session log: 13.66 ms a round for 2.75 tokens (201 tok/s),
64% of offered drafts landing. Their accounting of that round:

| part | their cost |
|---|---:|
| plain decode step (no drafter), short / 200K / 690K | 7.05 / 7.72 / 8.56 ms |
| each extra verify row | ~1.2 ms |
| DFlash2 drafter | ~1.1 ms |
| sampling and host work | ~1 ms |

Their conclusion, which is the shape of our problem too: the per-step FIXED cost (per-layer-site glue) matters
more than per-row cost, because 1 ms off the plain step is ~+8% real decode while 0.1 ms off each verify row is
only ~+2%.

Against that, ours at the same moment (11 November) was a verify round of 20.1 ms at one row (their 7.05) and a DFlash2 draft pass of 26.2 ms (their 1.1). **That 26.2 ms figure is
superseded and should not be used to rank work:** later captures put our drafter step at 3.40 ms against their 2.3 (OVERNIGHT section 24) and find drafting level between the arms
(section 44), and the drafter's acceptance is in theirs and ours' band (section 44). What is left of the one-row gap is the fixed per-site machinery of the decode step, not the
drafter; the prompt path, measured separately above, is the larger deficit.
