# The recipe's knobs: what is set, what is not, and what is known about each (current state, 2026-11-15)

`KNOBS=measured` in `scripts/serve.sh` sets the `DEFS` list below on top of an image built from `patches/engine/` (pin v1.2.9, 33 patches; the cells below were measured on the v1.2.7 stack of 36 patches, the v1.2.9 stack has not been measured on a GPU, see OVERNIGHT section 37).
Production on the Sparks is the Python stack and takes none of it. A knob is set only when its cells show no regression at 1, 2, 4, 6 and 8
streams (the repo rule); cells are in `docs/OVERNIGHT-2026-11-12.md` (OVERNIGHT below). Every name is a row of the `.glm` scope of
`zig/src/platform/environment.zig`; an unregistered `TF_GLM_*` name is refused at boot, so `DEFS` must follow the patch set it runs on.

## Set by `DEFS` (16 knobs) and added by `serve.sh`

`TF_GLM_KDA_PAD`, `TF_GLM_OVN_KEPT_WALK`, `TF_GLM_OVN_DRAFT_ONEPASS`, `TF_GLM_OVN_DRAFT_DOWN4`, `TF_GLM_OVN_DRAFT_MLPSPLIT=4`, `TF_GLM_OVN_MLA_FUSEMERGE`, `TF_GLM_OVN_DRAFT_EDGE=0.6`,
`TF_GLM_OVN_DRAFT_BETA=2`, `TF_GLM_OVN_DRAFT_CUTS=1:0.3`, `TF_EXL3_DEC_ORDER`, `TF_GLM_OVN_EXL3_ITEMS` (decode windows on our 16-pair item plan: on v1.2.7 the default path, on v1.2.9 a switch because upstream's
default is its compact 1024-row calls), `TF_GLM_OVN_X3_NC`, `TF_GLM_OVN_X3_XROW`, `TF_GLM_OVN_X3_FUSEDOWN`, `TF_GLM_OVN_KEEP_SEQS` (OVERNIGHT sections 30 and 34), `TF_GLM_OVN_OFF_EFFORT_LINE`.
The three-rank RoCE wire (`TF_GLM_ROCE_MULTI`, `TF_TP_MASTER`, `TF_TP_KERNEL_IMAGE`) is added when `--parallel` is at most 4, the world is above 1 and the fatbin exists.

`TF_GLM_OVN_OFF_EFFORT_LINE` sets no speed cell: it is a prompt change, not a kernel one. Thinking off, GLM-5.3's chat template leaves out its default `Reasoning Effort: Max` system line, exactly as production's Python engine renders it (prompts.py `thinking_off`), so the served prompt for the bench prose prompt is the same 33 tokens production sends instead of 40; a request that names `low` or `high` keeps its line and thinking on renders as before. Replies are therefore NOT token-identical to the knob-off serve, by design.

On v1.2.9 with every rank on the recipe `serve.sh` sets (OVERNIGHT section 41, arms against the mean of two controls): `TF_GLM_OVN_EXL3_ITEMS=1` is worth +3.8% at one stream, +3.9% at four and +5.3% at eight over upstream's compact decode path; `TF_GLM_OVN_KEEP_SEQS=1` +0.5% at one stream (inside the controls' 1.3% spread), +2.3% at four and +4.5% at eight. Both stay set; the X3 switches only act on the item plan. With them the stack decodes at parity with the v1.2.7 stack (section 41).

## Registered, not set, measured: no regression and no gain (stays out)

| knob | what the cells say | where |
|---|---|---|
| `TF_GLM_OVN_MM_WIDE`, `TF_GLM_OVN_SPARSE_ONEPASS`, `TF_GLM_OVN_INDEX_SCHED`, `TF_GLM_OVN_POOLS32`, `TF_GLM_OVN_INDEX_REGROUP` | within +-1% at every level of decode | OVERNIGHT section 17 |
| `TF_GLM_OVN_GLUE_FUSE`, `TF_GLM_OVN_ROUTER_WARM` | -2% in first cells, -0.6 to +1.4% repeated: neutral | section 17 |
| `TF_GLM_OVN_DRAFT_KEEPWIN` | +8.6 / +6.5 / +5.9 / +6.5 / +6.0% against +8.1 / +6.1 / +5.5 / +6.0 / +4.2% without: inside the noise | section 17 |
| `TF_GLM_OVN_PDL_EARLY` | -0.6 / -0.9 / 0.0 / -0.1 / +0.5% (first cells), -0.4 / -0.4 / -0.3 / -0.1 / +0.3% repeated | section 20, table `is-pdl` |
| `TF_GLM_OVN_GLUE_ROW`, `TF_GLM_OVN_ABSORB_VEC`, `TF_GLM_OVN_MM_WIDE`, `TF_GLM_OVN_INDEX_SCHED` on cold prompts | first token at 8k / 32k within +-1.4% of the control (the control pair itself differs by 2%) | section 31 |

## Registered, not set, a measured win without the five-level decode cells (candidate)

| knob | cells | missing |
|---|---|---|
| `TF_GLM_OVN_ONEPASS_PIPE` | cold first token -4.6% at 8k, -5.6% at 32k, replies equal (two boots each, section 31); exact by design | decode at 1, 2, 4, 6 and 8 streams |

## Registered, not set, no cell in `docs/OVERNIGHT-2026-1*.md`, `docs/BENCH.md` or `README.md`

`TF_GLM_OVN_HOST_ONCE`, `TF_GLM_OVN_KVB8`, `TF_GLM_OVN_KDA_CHUNKED`, `TF_GLM_OVN_DECODE_INDEX`, `TF_GLM_OVN_PLAIN_MARGIN`, `TF_GLM_OVN_DRAFT_NOISE`, `TF_GLM_OVN_WIN_FREE`,
`TF_GLM_OVN_ROUTER16`, `TF_GLM_OVN_SWIGLU_REDUCE`, `TF_GLM_OVN_MM_CLUSTER`, `TF_GLM_OVN_MM_DECTILE`, `TF_GLM_OVN_EXCHANGE_KB`, `TF_GLM_DFLASH2_WIN`, `TF_GLM_INDEX_DECODE_FROM`.
Each is untested here, not known neutral. `TF_GLM_OVN_KDA_CHUNKED` changes numerics (the owner decided on 2026-10-31 to keep numerics changes off); `TF_GLM_OVN_ONEPASS_EXACT` is retired.

## Not knobs of `DEFS`: the packages and their switches

| package | switch | state |
|---|---|---|
| `patches/pr1411` (GLM disk tier) | `--learn-conversations --learn-dir DIR --learn-gib N` (per rank, every rank the same) | passed only by `scripts/queue-disk-tier.sh`; correct at TP=3 (OVERNIGHT sections 32 and 35) |
| `patches/pr1411` 0013 | `TF_GLM_OVN_DISK_SLICE_MIB=N`, default 0 | a trade, not a default (OVERNIGHT section 36): the other streams' worst gap during a 4.7 GiB restore and the restoring turn's first token are 9,874 ms and 28.2 s off, 2,061 ms and 41.8 s at 32 MiB, 1,982 ms and 35.8 s at 64 MiB, 4,602 ms and 32.9 s at 128 MiB, 3,397 ms and 31.7 s at 256 MiB (one run each) |
| `patches/cache-salt` | `cache_salt` on a request; `--cache-salt-per-key` | salt honoured without the option (OVERNIGHT section 35); the option is unset |

## Absorbed by upstream v1.2.9 (landed 2026-11-15; OVERNIGHT section 37)

Four patches of ours are retired because v1.2.9 has the behaviour: the logit gather (upstream `5cd52c7a8`, `5b927e2bf`), the forward pieces split (`1ba369792`), the 2,048-row expert chunk
(`8978c4357`) and `EY_DIRECT` (`8978c4357`, `dc4aef0ec`: the prompt chunk writes the slot rows itself, so its knob left `DEFS`). `TF_GLM_INDEX_CUDA` is upstream's default (`8fe15871c`) and also left `DEFS`.
Upstream's own defaults on v1.2.9 (`TF_GLM_DSEL`, 4,096-row prompt passes) need no setting. Overlaps kept for with/without windows instead of dropped on text: our decode-window index patches against
`TF_GLM_DSEL`, the item plan against compact decode, `MLPSPLIT` against upstream's drafter split, `SPARSE_ONEPASS` against the new prompt plan, the X3 decode knobs, and the glue gather on the collective path.
