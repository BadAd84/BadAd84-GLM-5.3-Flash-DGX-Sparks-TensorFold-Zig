# The recipe's knobs: what is set, what is not, and what is known about each (current state, 2026-11-19)

`KNOBS=measured` in `scripts/serve.sh` sets the `DEFS` list below on top of an image built from `patches/engine/` (pin v1.2.9, 36 patches) and the packages `patches/pr1411`, `patches/cache-salt`, `patches/learn-starts` and `patches/solo-cuts` (the last two gated, their GPU checks pending). Cells measured on the v1.2.9 stack are in OVERNIGHT sections 41 to 50; the older ones (sections 17 to 36) were measured on the v1.2.7 stack.
Production on the Sparks is the Python stack and takes none of it. A knob is set only when its cells show no regression at 1, 2, 4, 6 and 8
streams (the repo rule); cells are in `docs/OVERNIGHT-2026-11-12.md` (OVERNIGHT below). Every name is a row of the `.glm` scope of
`zig/src/platform/environment.zig`; an unregistered `TF_GLM_*` name is refused at boot, so `DEFS` must follow the patch set it runs on.

## Set by `DEFS` (23 knobs) and added by `serve.sh`

`TF_GLM_KDA_PAD`, `TF_GLM_OVN_KEPT_WALK`, `TF_GLM_OVN_DRAFT_ONEPASS`, `TF_GLM_OVN_DRAFT_DOWN4`, `TF_GLM_OVN_DRAFT_MLPSPLIT=4`, `TF_GLM_OVN_MLA_FUSEMERGE`, `TF_GLM_OVN_DRAFT_EDGE=0.6`,
`TF_GLM_OVN_DRAFT_BETA=2`, `TF_GLM_OVN_DRAFT_CUTS=1:0.3`, `TF_EXL3_DEC_ORDER`, `TF_GLM_OVN_EXL3_ITEMS` (decode windows on our 16-pair item plan: on v1.2.7 the default path, on v1.2.9 a switch because upstream's
default is its compact 1024-row calls), `TF_GLM_OVN_X3_NC`, `TF_GLM_OVN_X3_XROW`, `TF_GLM_OVN_X3_FUSEDOWN`, `TF_GLM_OVN_KEEP_SEQS` (OVERNIGHT sections 30 and 34), `TF_GLM_OVN_OFF_EFFORT_LINE`,
and, since 2026-11-19, the seven below.
The three-rank RoCE wire (`TF_GLM_ROCE_MULTI`, `TF_TP_MASTER`, `TF_TP_KERNEL_IMAGE`) is added when `--parallel` is at most 4, the world is above 1 and the fatbin exists.

`TF_GLM_OVN_OFF_EFFORT_LINE` sets no speed cell: it is a prompt change, not a kernel one. Thinking off, GLM-5.3's chat template leaves out its default `Reasoning Effort: Max` system line, exactly as production's Python engine renders it (prompts.py `thinking_off`), so the served prompt for the bench prose prompt is the same 33 tokens production sends instead of 40; a request that names `low` or `high` keeps its line and thinking on renders as before. Replies are therefore NOT token-identical to the knob-off serve, by design.

On v1.2.9 with every rank on the recipe `serve.sh` sets (OVERNIGHT section 41, arms against the mean of two controls): `TF_GLM_OVN_EXL3_ITEMS=1` is worth +3.8% at one stream, +3.9% at four and +5.3% at eight over upstream's compact decode path; `TF_GLM_OVN_KEEP_SEQS=1` +0.5% at one stream (inside the controls' 1.3% spread), +2.3% at four and +4.5% at eight. Both stay set; the X3 switches only act on the item plan. With them the stack decodes at parity with the v1.2.7 stack (section 41).

The seven that joined on 2026-11-19 (OVERNIGHT sections 45 to 50; replies equal to the recipe's on every cell):

| knob | cells |
|---|---|
| `TF_GLM_OVN_NO_COPY` (patch 0034), `TF_GLM_OVN_MM_DECTILE=100000`, `TF_GLM_OVN_SWIGLU_REDUCE=1` | together against the recipe, four adjacent pairs at 1 / 2 / 4 clients and two at fresh 6 / 8 stream boots: prose +0.86 / +0.96 / +0.87 / -0.23 / +0.30%, code +11.15 / +4.13 / +4.21 / +1.97 / +4.88%, no cell slower under the noise rule; 24 prompts 1.0218 (1.0126 to 1.0337), 23 of 24 faster (section 49). Confirmed with the six together at the deployed shape (section 50): prose +1.57 / +0.37 / +0.62%, code +10.37 / +3.89 / +3.95% at 1 / 2 / 4, 24 prompts 1.0148 |
| `TF_GLM_OVN_ONEPASS_PIPE` | cold first token -5.30 / -6.74 / -6.95% at 8k / 32k / 120k (queue71, one boot; section 49's two boots: -4.73 / -5.84 / -6.51%); decode level at 1 / 2 / 4 / 6 / 8 streams; every cold reply equal across eight boots on one seed |
| `TF_GLM_CHUNK_SOLO=4096` (upstream) | cold first token -0.68 / -3.71 / -4.46% alone, -5.26 / -9.57 / -10.53% with `ONEPASS_PIPE` (two boots); decode level at 1 / 2 / 4; replies equal. It acts only while no stream decodes, and is refused for a request with request starts (OVERNIGHT section 50) |
| `TF_GLM_OVN_HOST_ONCE` | a warm turn at ~250k with request starts: -0.95% idle, -0.35% beside three decoding streams, replies equal (section 49) |
| `TF_GLM_OVN_DRAFT_NOISE=1` | greedy streams never read it (rounds equal, decode -0.1% to +0.8%); sampled at production's agent sampling (temperature 1.0, top-p 0.95, top-k 20, seed 7): fewer rounds with equal replies, prose +0.74 / +1.76 / +2.96%, code +0.74 / +0.57 / +0.44% at 1 / 2 / 4 clients (section 50). Its 6 and 8 stream sampled cells are open |

## Registered, not set, measured: no regression and no gain (stays out)

| knob | what the cells say | where |
|---|---|---|
| `TF_GLM_OVN_MM_WIDE`, `TF_GLM_OVN_SPARSE_ONEPASS`, `TF_GLM_OVN_INDEX_SCHED`, `TF_GLM_OVN_POOLS32`, `TF_GLM_OVN_INDEX_REGROUP` | within +-1% at every level of decode | OVERNIGHT section 17 |
| `TF_GLM_OVN_GLUE_FUSE`, `TF_GLM_OVN_ROUTER_WARM` | -2% in first cells, -0.6 to +1.4% repeated: neutral | section 17 |
| `TF_GLM_OVN_DRAFT_KEEPWIN` | +8.6 / +6.5 / +5.9 / +6.5 / +6.0% against +8.1 / +6.1 / +5.5 / +6.0 / +4.2% without: inside the noise | section 17 |
| `TF_GLM_OVN_PDL_EARLY` | -0.6 / -0.9 / 0.0 / -0.1 / +0.5% (first cells), -0.4 / -0.4 / -0.3 / -0.1 / +0.3% repeated | section 20, table `is-pdl` |
| `TF_GLM_OVN_GLUE_ROW`, `TF_GLM_OVN_ABSORB_VEC`, `TF_GLM_OVN_MM_WIDE`, `TF_GLM_OVN_INDEX_SCHED` on cold prompts | first token at 8k / 32k within +-1.4% of the control (the control pair itself differs by 2%) | section 31 |
| `TF_GLM_OVN_ROUTER16` (3 and 4) | one boot each at 1 / 2 / 4 clients, between their two controls at every level, replies equal: a screen, no effect seen | section 45 |
| `TF_GLM_OVN_EXCHANGE_KB=4096` | on top of `CHUNK_SOLO` and `ONEPASS_PIPE`: -5.14 / -9.46 / -10.60% against -5.26 / -9.57 / -10.53% without it, replies equal: nothing | section 50 |
| `TF_GLM_OVN_PLAIN_MARGIN=100` | every round count unchanged, greedy and sampled; decode -1.3% to +1.2%: inert on these prompts | section 50 |
| `TF_GLM_INDEX_CUDA=all`, `TF_GLM_OVN_DECODE_INDEX=33` | at ~100k and ~250k depth -0.2% to +1.0% (`all`) and -0.9% to +0.5% (`33`); at 1 / 2 / 4 clients `all` +2.0 / +1.6 / +0.7% prose and +1.2 / +1.2 / +0.7% code, `33` +1.5 / +0.8 / +0.5% and +1.4 / +0.6 / +0.6%, replies equal; the recipe's own boots on the one-stream prose cell spread 79.12 to 81.03, so these gains are inside the boot spread: undecided, more boots | section 50 |

## Registered, not set, measured: a loss (stays off)

| knob | what the cells say | where |
|---|---|---|
| `TF_GLM_OVN_WIN_FREE` | -20.9 / -29.6 / -28.5 / -31.2 / -28.0% at 1 / 2 / 4 / 6 / 8 clients, off / on / on / off at production's deployed shape, replies equal: every round verifies all seven drafts and acceptance falls to 0.24 to 0.36 | OVERNIGHT section 44 |
| `TF_GLM_OVN_MM_CLUSTER=1` | one boot, 79.02 / 82.16 / 110.40 against the controls before and after it (80.96 and 78.97 / 83.53 and 83.09 / 111.33 and 110.33): below both at one and two clients, replies equal; a screen | section 45 |
| `TF_GLM_COPIES=1` (upstream's opt-in copies) | 24 prompts solo: 3,184 rounds against 3,140, decode -2.3% (-3.6% on code-like prompts), replies equal | section 45 |
| `TF_GLM_DFLASH2_WIN=1024` | code at ~100k and ~250k depth -1.5% and -2.5%, -1.2% and -1.7%; prose and short prompts level | section 50 |

## Open: measured in part, or not yet

`TF_GLM_OVERLAP_PIECES` (upstream's default is 8 under `CHUNK_SOLO=4096` with `ROCE_MULTI=1`, which is what the recipe boots with; production runs 2) and `TF_GLM_ROCE_MULTI` itself on cold prompts (upstream's recipe documents solo gaining 7.3 to 8.4% without the wire and 3.2 to 3.4% with it; the wire buys +1.4 to +1.8% decode at 1 to 4 streams, section 21): both change scheduling only and have never been swept on this stack. `TF_GLM_INDEX_DECODE_FROM` gates `INDEX_CUDA=all` by depth and is measured only if `all` needs a gate. `TF_GLM_OVN_KDA_CHUNKED` changes numerics (the owner decided on 2026-10-31 to keep numerics changes off), and so does `TF_GLM_OVN_KVB8` (section 45: the replies differ; 84.41 / 87.59 / 114.87 tok/s on its own text); `TF_GLM_OVN_ONEPASS_EXACT` is retired.

## Upstream's switches the recipe does not set

| switch | what it does | state |
|---|---|---|
| `TF_GLM_REQUEST_STARTS=1` | a chat's next turn resumes where its previous turn's history ends, not at the last 2,048-row point | same replies (sections 29 and 48). On a growing conversation (`longctx.py chain`, section 50): -35.5% a turn at ~113k and -35.9% at ~284k, uncached tokens a turn 1,274 against 2,208 (production 1,306); the cost is +7% on a cold prime (+4.1 / +6.5 / +7.2% cold at 8k / 32k / 120k) because a request with a cut ran no solo pass, and +5% / +12% on a warm probe that never sends the next turn. Break-even 8.3 turns after a cold ~113k prime. `patches/solo-cuts` lets a solo step run between the cuts (2026-11-19: gated, GPU check pending) and `patches/learn-starts` lifts upstream's refusal with `--learn-conversations` (gated, GPU check pending); off until both checks have run and the cold cost is measured with the fix |
| `TF_GLM_COPIES=1` | verified root and context copies | a loss (table above) |

## Not knobs of `DEFS`: the packages and their switches

| package | switch | state |
|---|---|---|
| `patches/pr1411` (GLM disk tier) | `--learn-conversations --learn-dir DIR --learn-gib N` (per rank, every rank the same), or `LEARN=1` in `serve.sh` (default 0) | correct at TP=3 (OVERNIGHT sections 32 and 35); `scripts/queue-disk-tier.sh` passes the flags itself, `LEARN=1` is the recipe's way to deploy it and costs no decode speed while idle (section 43); a deployment is `LEARN=1 KNOBS=measured P=4 CTX=1048576` |
| `patches/pr1411` 0013 | `TF_GLM_OVN_DISK_SLICE_MIB=N`, default 0 | a trade, not a default (OVERNIGHT section 36): the other streams' worst gap during a 4.7 GiB restore and the restoring turn's first token are 9,874 ms and 28.2 s off, 2,061 ms and 41.8 s at 32 MiB, 1,982 ms and 35.8 s at 64 MiB, 4,602 ms and 32.9 s at 128 MiB, 3,397 ms and 31.7 s at 256 MiB (one run each) |
| `patches/cache-salt` | `cache_salt` on a request; `--cache-salt-per-key` | salt honoured without the option (OVERNIGHT section 35); the option is unset |
| `patches/solo-cuts` | none (acts under `TF_GLM_CHUNK_SOLO=4096` with `TF_GLM_REQUEST_STARTS=1`) | gated 2026-11-19 (host tests, mutants m1 to m8); GPU check in `scripts/queues/queue73.sh`: cold first token and replies with request starts, against the same image's solo-only arm and the image without the patch |
| `patches/engine/0036` | `TF_GLM_OVN_LATENT_ROWS=2` or `4`, default 0 | gated 2026-11-19, no GPU run yet: `glm-latent-rows` (byte equality of the absorb and expand kernels at 2 and 4 rows a step against today's launch) and the cold first token arms are in `scripts/queues/queue73.sh` |
| `patches/engine/0038` | `TF_GLM_OVN_PIECE_FRONT=1`, `TF_GLM_OVN_PIECE_MLA=1`, `TF_GLM_OVN_PIECE_FFN=1`, default 0 | gated 2026-11-20 (full gate run, six mutants); on a GPU in queue83 (OVERNIGHT section 58, two boots each, every reply equal, decode level): the three together read -3.6 / -3.8 / -3.5% cold at 8k / 32k / 120k, -3.5% on a ~113k conversation's first turn and -1.2% on its turns 2 to 8; the KDA front alone -3.0 / -3.0 / -2.6%, the router front adds 0.1 points. Joins the final recipe N' (queue77 measures it at every level) |

## Absorbed by upstream v1.2.9 (landed 2026-11-15; OVERNIGHT section 37)

Four patches of ours are retired because v1.2.9 has the behaviour: the logit gather (upstream `5cd52c7a8`, `5b927e2bf`), the forward pieces split (`1ba369792`), the 2,048-row expert chunk
(`8978c4357`) and `EY_DIRECT` (`8978c4357`, `dc4aef0ec`: the prompt chunk writes the slot rows itself, so its knob left `DEFS`). `TF_GLM_INDEX_CUDA` is upstream's default (`8fe15871c`) and also left `DEFS`.
Upstream's own defaults on v1.2.9 need no setting: `TF_GLM_DSEL`, and `TF_GLM_PROMPT_PAIR=1` (while no stream decodes, a prompt step takes two 2,048-row chunks, each one's exchanges under the other's compute; the kernels still run on 2,048 rows, and pairing is refused while a pass has request starts). Overlaps kept for with/without windows instead of dropped on text: our decode-window index patches against
`TF_GLM_DSEL`, the item plan against compact decode, `MLPSPLIT` against upstream's drafter split, `SPARSE_ONEPASS` against the new prompt plan, the X3 decode knobs, and the glue gather on the collective path.
