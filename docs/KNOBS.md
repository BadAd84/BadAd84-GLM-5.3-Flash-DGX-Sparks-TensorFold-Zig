# The recipe's knobs: what is set, what is not, and what is known about each (current state, 2026-11-18)

`KNOBS=measured` in `scripts/serve.sh` sets the `DEFS` list below on top of an image built from `patches/engine/` (pin v1.2.9, 35 patches) and the packages `patches/pr1411` and `patches/cache-salt`. Cells measured on the v1.2.9 stack are in OVERNIGHT sections 41 to 49; the older ones (sections 17 to 36) were measured on the v1.2.7 stack.
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
| `TF_GLM_OVN_ROUTER16` (3 and 4), `TF_GLM_OVN_DECODE_INDEX=33` | one boot each at 1 / 2 / 4 clients, between their two controls at every level, replies equal: a screen, no effect seen | section 45 |

## Registered, not set, measured: a loss (stays off)

| knob | what the cells say | where |
|---|---|---|
| `TF_GLM_OVN_WIN_FREE` | -20.9 / -29.6 / -28.5 / -31.2 / -28.0% at 1 / 2 / 4 / 6 / 8 clients, off / on / on / off at production's deployed shape, replies equal: every round verifies all seven drafts and acceptance falls to 0.24 to 0.36 | OVERNIGHT section 44 |
| `TF_GLM_OVN_MM_CLUSTER=1` | one boot, 79.02 / 82.16 / 110.40 against the controls before and after it (80.96 and 78.97 / 83.53 and 83.09 / 111.33 and 110.33): below both at one and two clients, replies equal; a screen | section 45 |
| `TF_GLM_COPIES=1` (upstream's opt-in copies) | 24 prompts solo: 3,184 rounds against 3,140, decode -2.3% (-3.6% on code-like prompts), replies equal | section 45 |

## Registered, not set, measured wins (they join `DEFS` together, after `queue71`'s runs)

| knob | cells | still to measure |
|---|---|---|
| `TF_GLM_OVN_NO_COPY` (patch 0034), `TF_GLM_OVN_MM_DECTILE=100000`, `TF_GLM_OVN_SWIGLU_REDUCE=1` | together against the recipe, four adjacent pairs at 1 / 2 / 4 clients and two at 6 / 8 streams: prose +0.86 / +0.96 / +0.87 / -0.23 / +0.30%, code +11.15 / +4.13 / +4.21 / +1.97 / +4.88%, replies equal everywhere, no cell slower under the noise rule; 24 prompts 1.0218 (1.0126 to 1.0337), 23 of 24 faster (section 49; the knobs one by one: sections 45, 47 and 48) | none |
| `TF_GLM_OVN_ONEPASS_PIPE` | cold first token -4.73 / -5.84 / -6.51% at 8k / 32k / 120k (every boot under both recipe boots); decode level at 1 / 2 / 4 / 6 / 8 streams, replies equal on the decode cells (section 49; section 31 before) | its replies on long prompts against the recipe's, one seed for every boot (`queue71`; queue69's cold prompts were seeded by boot) |
| `TF_GLM_CHUNK_SOLO=4096` (upstream) | cold first token +0.08 / -2.67 / -3.64% at 8k / 32k / 120k; decode level at 1 / 2 / 4 (section 49) | as above, and with `ONEPASS_PIPE` and with `TF_GLM_OVN_EXCHANGE_KB=4096` (`queue71`) |
| `TF_GLM_OVN_HOST_ONCE` | a warm turn at ~250k with request starts: -0.95% idle, -0.35% beside three decoding streams, replies equal (section 49) | none for its own path (the rewind probe of a warm turn) |

## Registered, not set, no cell yet (`queue71` measures them)

`TF_GLM_OVN_PLAIN_MARGIN=100` (the core's margin 1.05 becomes 1.00) and `TF_GLM_OVN_DRAFT_NOISE=1` (a sampled stream's draft picks with the target's keyed Gumbel draws; the greedy bench cannot see it, so `scripts/streams_sampled.py` measures it at production's agent sampling) at 1 / 2 / 4 clients greedy and sampled; `TF_GLM_DFLASH2_WIN=1024`, `TF_GLM_INDEX_CUDA=all` (decode windows on the index kernels) and `TF_GLM_OVN_DECODE_INDEX=33` on decode at ~100k and ~250k deep (`scripts/longdec_ids.json`) and at 1 / 2 / 4 clients: the last two were only screened on 33-token prompts (sections 17 and 45), where a decode window is shallow; `TF_GLM_OVN_EXCHANGE_KB=4096` with `TF_GLM_CHUNK_SOLO=4096` on cold prompts. `TF_GLM_INDEX_DECODE_FROM` gates `all` by depth and is measured only if `all` needs a gate.
`TF_GLM_OVN_KDA_CHUNKED` changes numerics (the owner decided on 2026-10-31 to keep numerics changes off), and so does `TF_GLM_OVN_KVB8` (section 45: the replies differ; 84.41 / 87.59 / 114.87 tok/s on its own text); `TF_GLM_OVN_ONEPASS_EXACT` is retired.

## Upstream's switches the recipe does not set

| switch | what it does | state |
|---|---|---|
| `TF_GLM_REQUEST_STARTS=1` | a chat's next turn resumes where its previous turn's history ends, not at the last 2,048-row point | same replies (sections 29 and 48); a trade (section 49): a warm turn at ~100k 1,225 against 1,956 ms, at ~250k 655 against 564 ms idle and 774 against 580 ms beside three decoding streams, where both arms resume at the same point; refused with `--learn-conversations` by upstream until `patches/learn-starts` (in its gates) lands |
| `TF_GLM_CHUNK_SOLO=4096` | while no stream decodes, a prompt step is one 4,096-row forward (weights read once for both chunks), prompt buffers sized for it | a measured win on cold prompts (table above, section 49); section 29's "no gain" ran with 8 wire pieces and is confounded (section 31) |
| `TF_GLM_COPIES=1` | verified root and context copies | a loss (table above) |

## Not knobs of `DEFS`: the packages and their switches

| package | switch | state |
|---|---|---|
| `patches/pr1411` (GLM disk tier) | `--learn-conversations --learn-dir DIR --learn-gib N` (per rank, every rank the same), or `LEARN=1` in `serve.sh` (default 0) | correct at TP=3 (OVERNIGHT sections 32 and 35); `scripts/queue-disk-tier.sh` passes the flags itself, `LEARN=1` is the recipe's way to deploy it and costs no decode speed while idle (section 43); a deployment is `LEARN=1 KNOBS=measured P=4 CTX=1048576` |
| `patches/pr1411` 0013 | `TF_GLM_OVN_DISK_SLICE_MIB=N`, default 0 | a trade, not a default (OVERNIGHT section 36): the other streams' worst gap during a 4.7 GiB restore and the restoring turn's first token are 9,874 ms and 28.2 s off, 2,061 ms and 41.8 s at 32 MiB, 1,982 ms and 35.8 s at 64 MiB, 4,602 ms and 32.9 s at 128 MiB, 3,397 ms and 31.7 s at 256 MiB (one run each) |
| `patches/cache-salt` | `cache_salt` on a request; `--cache-salt-per-key` | salt honoured without the option (OVERNIGHT section 35); the option is unset |

## Absorbed by upstream v1.2.9 (landed 2026-11-15; OVERNIGHT section 37)

Four patches of ours are retired because v1.2.9 has the behaviour: the logit gather (upstream `5cd52c7a8`, `5b927e2bf`), the forward pieces split (`1ba369792`), the 2,048-row expert chunk
(`8978c4357`) and `EY_DIRECT` (`8978c4357`, `dc4aef0ec`: the prompt chunk writes the slot rows itself, so its knob left `DEFS`). `TF_GLM_INDEX_CUDA` is upstream's default (`8fe15871c`) and also left `DEFS`.
Upstream's own defaults on v1.2.9 need no setting: `TF_GLM_DSEL`, and `TF_GLM_PROMPT_PAIR=1` (while no stream decodes, a prompt step takes two 2,048-row chunks, each one's exchanges under the other's compute; the kernels still run on 2,048 rows, and pairing is refused while a pass has request starts). Overlaps kept for with/without windows instead of dropped on text: our decode-window index patches against
`TF_GLM_DSEL`, the item plan against compact decode, `MLPSPLIT` against upstream's drafter split, `SPARSE_ONEPASS` against the new prompt plan, the X3 decode knobs, and the glue gather on the collective path.
