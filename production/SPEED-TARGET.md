# SPEED-TARGET.md - what the production GLM serve measures (the target to match or beat)

The serve: `tensorfold-glm53:v110hunt4-shard` with `production/launch/v110ots.env` (the env of record since
2026-11-10), TP=3 on spark1-3, `--parallel 4`, thinking on, vision on, the EXL3 4bpw checkpoint at rev `078455ffe647`
and the DFlash2 drafter at rev `bf582e4eacc1` (`PRODUCTION.md`). Every number below is copied from a file that
exists, named under its table. A metric with no such file says "not measured" and names the instrument that would
measure it.

## 1. Decode and first token at 1, 2, 4, 6 and 8 streams

One run on 2026-11-11 (cell files written 11:59 to 12:02 UTC), the Zig repo's instrument against the live serve from
spark1, production otherwise idle (its request counter flat, as `docs/speed_target.md` there records):
`scripts/streams.py 8888 <N> --kind prose --max-tokens 400 --rounds 3`. Every stream asks for 400 tokens; the
prompts are `prose`, `story`, `facts` and `prose2`, repeated past four streams. The serve keeps its own
`--parallel 4` at every level, so at 6 and 8 streams two or four requests wait for a slot. The cells are in
`production/target/pyprod/P<N>.jsonl` (copied from the head's `~/bench/pyprod/`), three rounds a level; the table is
their mean.

| streams | aggregate tok/s | decode aggregate tok/s | decode per stream tok/s (min to max) | first token ms |
|---:|---:|---:|---:|---|
| 1 | 81.73 | 83.62 | 83.62 (83.43 to 83.83) | 121 to 122 |
| 2 | 89.22 | 90.42 | 52.21 (44.65 to 59.47) | 101 to 239 |
| 4 | 117.98 | 119.69 | 34.10 (29.83 to 37.36) | 225 to 228 |
| 6 | 114.78 | 115.56 | 37.39 (25.49 to 50.10) | 129 to 332; the 6 that waited for a slot 9,807 to 11,894 |
| 8 | 131.28 | 131.96 | 37.25 (27.61 to 43.32) | 128 to 332; the 12 that waited for a slot 9,555 to 14,858 |

Aggregate is the instrument's `agg_tok_s` (tokens over the round's wall time), decode aggregate its
`decode_agg_tok_s`, decode per stream its `per_stream`, first token its `ttft_ms`. Every reply is the same in every
round and at every level: `8347edfe4ee6` (prose), `66b9fe5c1ea4` (story), `8ab1a46288e5` (facts), `c01484b25e1f`
(prose2).

The same cells, as the Zig repo publishes them:

- `docs/speed_target.md` at `db314e5` (2026-11-12), the table the Zig arms are compared with: the last round's decode
  aggregate and its first streams' first-token times.

  | streams | aggregate tok/s | first token ms |
  |---:|---:|---|
  | 1 | 83.43 | 122 |
  | 2 | 91.07 | 157 / 156 |
  | 4 | 119.97 | 228 / 228 |
  | 6 | 111.99 | 232 / 232 / 230 |
  | 8 | 136.18 | 128 / 332 / 9710 |

- `docs/OVERNIGHT-2026-11-12.md` (the `pyprod` row, first at `64b8b6a`) and the README's production row: 81.73 /
  89.22 / 117.98 / 114.78 / 131.28 tok/s at 1 / 2 / 4 / 6 / 8 streams, the mean aggregate of the three rounds.

## 2. The one-stream round

From the Zig repo's `docs/OVERNIGHT-2026-11-12.md` section 15 (added in `e329a82`): production's own `/health`
counters around five identical 400-token requests, one stream, prose prompt, greedy, 2026-11-12.

| rounds | drafts a round | tokens a round | acceptance | ms a round | decode tok/s |
|---:|---:|---:|---:|---:|---:|
| 133 | 2.92 | 3.01 | 0.686 | 35.6 | 80.8 |

The same document's section 11 first read 31.9 ms a round from counters that included other requests; section 15
withdraws that reading.

## 3. First token on long prompts, and resuming a long conversation

From this repo's internal notes of 2026-11-10 (`int-docs/MORNING-2026-11-10.md` and `int-docs/resume-2026-11-08.md`,
not published), measured on the live serve after the env of record was set. The notes do not name the instrument for
the first table.

| case | load | first token |
|---|---|---:|
| cold 1k prompt | idle | 0.54 s |
| cold 8k prompt | idle | 2.82 s |
| cold 32k prompt | idle | 10.93 s |
| cold 120k prompt | idle | 42.86 s |
| warm turn | beside 3 decoding streams | 1.217 s (three samples) |
| warm turn | idle | not measured on this serve |
| cold prompt | beside decoding streams | not measured on this serve |

A growing conversation (`tier_chain.sh shard v110ots.env`, main's `scripts/glm53/v110/tier_chain.sh`), the same day:

| turn | prefill |
|---|---:|
| 1, cold at ~596k tokens | 224.68 s |
| 2, from the pool | 12.54 s |
| 3, after every rank was killed with SIGKILL (resumed from the spill tier, 619,392 tokens cached) | 12.80 s |
| 4, after a clean restart | 12.90 s |

The missing cases, and these again on a fresh run: main's `scripts/glm53/v110/ttft.py` (run by `qual_image.sh`)
measures cold 1k / 8k / 32k / 120k prompts and a warm agent turn, idle and beside three decoding streams.

## 4. Memory

From the internal speed-hunt notes of 2026-11-10 (sections 9.52 and 9.53), on this image with the env of record:

| what | value |
|---|---|
| KV pool at `--parallel 4` | 14,407,680 tokens, three parts of 4,802,560 (unsharded it would be 5,369,856) |
| memory available a node after boot, spark1 / spark2 / spark3 | 18.6 / 20.2 / 21.2 GiB |
| the same under four conversations growing to ~850k tokens, turn 12 of 12 (flat from turn 8) | 14.7 / 17.1 / 17.5 GiB |
| kept prompt states' memory budget (`TF_GLM_KEPT_BYTES_GIB`) | 8 GiB |
| the pool at `--parallel` 1, 2, 6 and 8 | not measured on this serve |

The pool is sized at boot: `/health`'s `pool_tokens` after a fresh boot at each level gives it.

## 5. Boot time

Not measured on this image. Main's `scripts/glm53/v110/hunt/deploy/perpatch_run.sh` (its `boot()`) prints the seconds
from start to the first `/health` 200 for every boot it makes.

## 6. RigMark

Not measured on this image and env: the last RigMark runs were of `v110hunt4` with the env of 2026-11-05, before the
fix and shard images and the 2026-11-10 settings. Main's `scripts/glm53/v110/rigmark_run.sh` runs it, at TP=3 and at
1, 2, 4, 6 and 8 streams with one comparison ID a sweep (main's `AGENTS.md`, the RigMark rule).
