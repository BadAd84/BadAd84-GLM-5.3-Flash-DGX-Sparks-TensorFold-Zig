# Long-context support on the Zig GLM serve: what v1.2.7 plus the 34-patch series does for production's section 3 to 5 cases

From the `LongCtxHarness` lane's read of the source (tree `f5495931b233`, the tree image `rs2x3` was built from); every path is `zig/src/...`.
No measurement is in this file: the measurements are `docs/OVERNIGHT-2026-11-12.md` section 29.

| production case | Zig serve | evidence |
|---|---|---|
| cold prompts of 1k to 120k tokens, idle | supported | |
| warm turn, idle and beside decoding streams | supported, resumes only at 2,048-row cut points | `families/glm/cuda_native.zig:27-35`, `cuda_lanes.zig:354-364`; message-start cuts need `TF_GLM_REQUEST_STARTS=1`, off by default; upstream's registry classes it arithmetic (`core/profile.zig:141`), but its replies measured identical to the switch off (OVERNIGHT section 29's rows; upstream PR #2404's receipts: 19 turns, one reply digest across 12 runs) |
| cold prompt beside decoding streams | supported | |
| cold fill of a ~596k-token conversation | only where one stream's window holds it | with `--kv-cache fp8` each stream gets a fixed window of `--context` rows; a shared page pool needs bf16 and fp8 with pages is refused (`glm/cuda_start.zig:51-57`, `core/profile.zig:148`); prompt plus max_tokens beyond the window is refused (`server/chat.zig:158-164`, `cuda_lanes.zig:258`) |
| turn 2 resumed from kept states | supported while the kept-state budget holds the state | a kept state is a full copy of the prefix (`glm/cuda_snapshots.zig:99-134`), 6,380 B a token a rank: 11 DSA layers x (512 latent + 4 scale + 64 index-key bytes) (`cuda_snapshot_layout.zig:86-95`), about 3.5 GiB at 596k tokens; budget defaults to half the room left after the streams with a 16 GiB floor (`native/cuda_memory.zig:185-191`, `cuda_kv_pool.zig:228`) |
| resume after every rank is SIGKILLed or after a clean restart | **not supported** | kept states live in device memory, or pinned host memory with `TF_GLM_HOST_CACHE=1` (`cuda_snapshot_pages.zig:12-15`); GLM has no disk image, so `--spill-gib` and `--learn-conversations` are refused at open (`native/cuda_refusal.zig:57,62`, test `:276-284`; this runs first, `native/cuda.zig:178`) |
| KV pool tokens on `/health` | not reported | `server/status_routes.zig:29-67` has no `pool_tokens`; `/metrics` `prompt_cache_budget_bytes` (`metrics.zig:177-185`) and the startup line stand in |
| longest context at P=1 | 1,048,576 tokens | the checkpoint's `max_position_embeddings`; a larger `--context` is refused (`native/cuda.zig:187-191`); usable prompt is `--context` minus max_tokens (`chat.zig:161-163`) |

## Boot for a like-for-like serve

`IMAGE=glm53-zig:rs2x3 KNOBS=measured bash zig-tp3.sh 4 1048576`. No tier flag can be passed: `--snapshot-dir /spill` is refused while
parsing (only `none` is accepted, `server/cli.zig:121,311-313`), `--spill-highwater`, `--spill-min-tokens` and `--spill-min-free-gib` do
not exist (`cli.zig:296`), and `--spill-gib 120` is refused when the model opens (`cli.zig:542-547`). Production's other settings with no
counterpart: `TF_GLM_KV_SHARD=1` (no match in `zig/src`), the pool settings `TF_GLM_CACHE_GIB`, `KEPT_BYTES_GIB`, `CACHE_ENTRIES` and
`KEEP_PER_CHAT`, and `PREFILL_ROWS=4096` (ours passes 2,048 rows, `cuda_state.zig:19`; the nearest knob is `TF_GLM_CHUNK_SOLO=4096`,
`cuda_ranks.zig:20,92-97`). `scripts/serve.sh` does not pass `--vision`. Production's `INDEXER_SHARD=prefill` has a counterpart:
`TF_GLM_INDEX_SPLIT` is on by default from row 2048 (`cuda_ranks.zig:22`).

## Requests beyond `--parallel` slots

They queue as production's do: the lane host admits the head of the queue when a lane frees (`core/lane_host.zig:338-380`,
`lane_host_admit.zig:11-41`); HTTP admission limits default to off (`server/request_admission.zig:12-14`).

## Gaps: production serves these, this engine cannot

1. No resume after a crash or restart (no disk tier).
2. Kept states are full copies on every rank in a separate budget, not part of a shared sharded pool.
3. Prompt passes are 2,048 rows, production's 4,096.
4. Warm turns resume only at 2,048-row cut points unless `TF_GLM_REQUEST_STARTS` is on.
5. No `pool_tokens` on `/health`.
6. A ~600k conversation does not fit `serve.sh`'s default four-stream window of 262,144; at the deployed shape four fp8 windows of 1M rows
   need about 6.2 GiB each a rank (derived), and the shape booted in the window.
