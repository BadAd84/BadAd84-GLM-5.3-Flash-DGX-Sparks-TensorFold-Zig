# Why each knob our patches add has the value it has (2026-11-23)

The owner's question, first asked of the v1.2.9 series: for the knobs our patches added, was each one tested and found not good enough, or did we find the speed, add the setting, and
then never turn it on? This file answers it knob by knob from the record. It is current state: when a knob's status changes, its row changes.

**Every knob below that still exists is now a LINE of `scripts/env/prod.env` and `scripts/env/dev.env`** (owner 2026-11-23): a measured value in the recipe, or the engine's own
default in the completeness block, with one verdict per row in `scripts/env/register.env` (`docs/ENV-REGISTER.md`). So this dossier is no longer "what is outside `prod.env`": it is
the record of what decided each value, and the cells behind the ones that are debt. A knob whose patch and registry row have left the series is marked as retired; it is no longer
a setting of this engine and its cells below are the record of why it went.

**Scope** (`python scripts/knob-inventory.py`, upstream clone at `work/up/TensorFold`): the engine series adds 54 `TF_` names that upstream's pin lacks. 5 of them are not settings
(`TF_EXL3_OVN_BLOCKS` and `TF_GLM_HC_FINISH_PDL`, `_HC_GLUE`, `_HC_ROW` are CUDA preprocessor macros; `TF_GLM_OVN` is a prefix). Of the rest: the 32 rows the recipe sets with a
measurement, the rows the completeness block sets at their default, and the names that left with their patch (each marked). `TF_GLM_REQUEST_STARTS` and `TF_GLM_COPIES` are
upstream's switches, not ours, and neither is set.

**Sign convention.** A first-token or turn time that is negative is FASTER (it fell). A decode tokens-a-second change that is negative is SLOWER. Each row says which it quotes.

**Sources.** The retired engine's speed ledger (`docs/SPEEDUPS.md` of the `ai-engine` repo, kept whole in `archive/ai-engine`): its tables "Trades kept", "Killed by measurement" and
"Won so far", run labels in backticks. This repo's `docs/KNOBS.md` and the OVERNIGHT sections (s17 and so on). The owner's answers in the `ai-engine` and Zig sessions (quoted below).

## A. Tested, did not make the cut: retired, or set off at the engine's default

A name marked † is retired: its patch, registry row and reader have left the series (class F), so it is no longer a setting of this engine. The rest of this table are
settings that exist and are set at the engine's default, off, with their loss as the reason (debt in the register).

| knob (patch) | what the cells said |
|---|---|
| `TF_GLM_OVN_WIN_FREE`† (0018) | decode -20.9 / -29.6 / -28.5 / -31.2 / -28.0% at 1 / 2 / 4 / 6 / 8 clients, replies equal, acceptance 0.24 to 0.36 (s44); retired engine on the flipped defaults: short decode -6.2% at 6 streams, -5.8% at 8, forks -15% (`wf8`) |
| `TF_GLM_OVN_PLAIN_MARGIN`† (0015) | every round count unchanged, decode -1.3% to +1.2% (s50); retired engine: two ABBAs at 8 streams flat (`pm`) |
| `TF_GLM_OVN_EXCHANGE_KB=4096` (0016) | on top of `CHUNK_SOLO` and `ONEPASS_PIPE` the cold first token is -5.14 / -9.46 / -10.60% against -5.26 / -9.57 / -10.53% without it (s50); retired engine cold 8k 2.376 / 2.373 s against 2.361 / 2.363 s (`xkb8k`) |
| `TF_GLM_OVN_ROUTER_WARM`† (0017) | retired engine at 1 stream: decode -0.5% short and -0.5% forks, both boots (`rwarm`); s17 neutral (-2% in first cells, -0.6 to +1.4% repeated) |
| `TF_GLM_OVN_PDL_EARLY` (0020) | decode -0.6 / -0.9 / 0.0 / -0.1 / +0.5% (first cells) and -0.4 / -0.4 / -0.3 / -0.1 / +0.3% (repeated) at 1 / 2 / 4 / 6 / 8 (s20, `is-pdl`); retired engine: alone it gains nothing at 2 streams and costs per-stream short decode -2.7% at 4 (`railsparts`); upstream's default `TF_GLM_PDL` is the same launch attribute |
| `TF_GLM_OVN_MM_CLUSTER=1` (0022) | one boot, 79.02 / 82.16 / 110.40 tok/s against the control boots' means 79.97 / 83.31 / 110.83 at 1 / 2 / 4 clients: -1.2 / -1.4 / -0.4% (computed here from the s45 control values), replies equal; retired engine level at 1 and 4 streams (`ovn4b`) |
| `TF_GLM_OVN_ROUTER16`† 3 and 4 (0022, used by 0024) | one boot each at 1 / 2 / 4 clients, between its two controls at every level, replies equal (s45); retired engine level at 1 and 4 streams (`ovn4b`) |
| `TF_GLM_OVN_GLUE_FUSE=32` (0024) | retired engine decode -0.3% at 1 stream and -1.3% at 4 (`ovn4b`); s17 -2% in the first cells, -0.6 to +1.4% repeated |
| `TF_GLM_OVN_GLUE_ROW` (0024) | cold first token at 8k / 32k within +-1.4% of a control whose pair differs by 2% (s31); the related `HC_ROWS=16` lost in the retired engine (`p14parts`) |
| `TF_GLM_OVN_DRAFT_KEEPWIN`† (0006) | decode +8.6 / +6.5 / +5.9 / +6.5 / +6.0% against +8.1 / +6.1 / +5.5 / +6.0 / +4.2% without it: inside the noise (s17) |
| `TF_GLM_DFLASH2_WIN`† (0006) | the default 2,048 is the no-op. `=1024`: code decode at about 100k and 250k depth -1.5% and -2.5%, -1.2% and -1.7% (s50). The retired engine's `=32` prose +9 to 10% was measured while the drafter's prompt taps were stale; with complete taps (fixed since) more context helps and the sweep was recorded as moot |
| `TF_GLM_OVN_INDEX_REGROUP`† (0013) | alone, cold 32k -0.3% and about 200k cold -0.2%, forks TTFT +2.6% (`p14parts`): the kernel is 4.2 to 5.2% faster and the prompt pass does not show it |
| `TF_GLM_OVN_FRONT_ROWS` (0038) | 2,048: warm turns 3.2% to 3.8% slower and cold 0.7% to 3.4% slower; 512 and 768 no gain (s61) |
| `TF_GLM_OVN_PIECE_KDA`† (0039) | cold first token +0.73 / +0.88 / +0.97% (slower) at 8k / 32k / 120k, turns 2 to 8 level (s67). No other patch needs it |
| `TF_GLM_OVN_KVB8` (rows in 0020, code in 0023) | changes replies (s45); cold -0.53 / -0.51 / -0.53% (faster), 14 of 16 reply digests differ, rounds 2.2% and 3.6% longer (s61) |
| `TF_GLM_OVN_KDA_CHUNKED`† (0021) | changes replies; cold -0.95 / -1.19 / -1.58% (faster) with 12 of 16 digests differing (s61); retired engine alone cold -1.2 / -1.5%, GSM8K 283 of 300 against 282 (`pnsolo`) |
| `TF_GLM_OVN_SPARSE_ONEPASS`† (0019) | changes replies; retired engine alone cold -9.4 / -10.2% at 32k / 133k (`pnsolo`). `ONEPASS_PIPE` (patch 0020, in `prod.env`) is the same pipeline with today's bytes: retired engine cold -9.8% at 32k and 200k, this recipe -5.30 / -6.74 / -6.95% at 8k / 32k / 120k (s50). 0019 is a build prerequisite of 0020, so only its knob and routing can go |

`TF_GLM_KDA_DUMP` (0005) is not a speed lever: it writes the KDA input stack to a file for the pad's FP64 gate, and goes with that gate, not with this list.

## B. Benefit measured: promoted, or blocked by a named cell

Every row here has a measured gain and a decision on its value; none is a switch someone forgot.

| knob | the speed, and where the value stands |
|---|---|
| the ten `dev.env` candidates: `MM_WIDE`, `SIDE_PRIO`, `OVERLAP_PIECES=4`, `LATENT_ROWS=2`, `PIECE_FRONT`, `PIECE_FFN`, `PIECE_MLA`, `NCCL_NCHANNELS_PER_NET_PEER=4`, `SOLO_TO_START`, `RESTORE_HELD`, with `ABSORB_VEC` | **Promoted into the recipe on 2026-11-22** (queue116 receipts, KNOBS sections 94 and 95: the whole dev env against the recipe read +0.15 / +0.99 / -0.22 / +0.28 / +0.23% at 1 / 2 / 4 / 6 / 8 streams, every level inside the boot spread, and the cold prompt 6.9% faster at 8k and 7.4% at 32k). The history behind it: together on main (queue91, s72) they read cold +8.3 / +8.9 / +8.4% faster and warm turns +7.9% faster with decode lower in 12 of 12 cells (mean 0.86%), which the repo rule refused as a bundle; queue95 split the four that can touch decode from the six that cannot, and queue116's receipts are the promotion's cells |
| `TF_GLM_REQUEST_STARTS=1` (upstream's) | warm turns 34% to 36% faster; its cost is +4 to +7% on a cold prime and not-clean 6- and 8-client decode cells (KNOBS.md). Not set, and not a row of our table: it waits on queue100 |
| `TF_GLM_OVN_ABSORB_VEC` (rows in 0020, code in 0023) | byte-identical; **in the recipe since 2026-11-22** with the ten above. Its own cells: retired engine at 1 stream (`vec2`) cold 32k and 200k -1.0% (faster), warm turns -0.7% to -2.0% (faster); at 2 to 8 streams (`vecv`) cold 32k +1.1%, 200k +0.9%, warm next turn +1.3% faster, short TTFT 1.7% worse (one ledger reading); queue102's 120k cells now confirm the promoted value rather than gate it |
| `TF_CACHE_EVICT=decayed_resume` (upstream's word value) | 47.40% fewer rows rebuilt (queue98, s75); the five-level check (queue99, s78) is NOT ACCEPTED by three 6- and 8-client decode cells inside the box's noise, so the recipe sets the row's other word, `main`, as a measured default. A waiver for `decayed_resume` is the owner's call |

## C. Never measured where it could matter

`TF_GLM_INDEX_CUDA=all`, `TF_GLM_INDEX_DECODE_FROM` (0007) and `TF_GLM_OVN_DECODE_INDEX` (0012) route decode windows to the index kernels at depth: at 100k and 250k they read
-0.2% to +1.0% (`all`) and -0.9% to +0.5% (`33`), inside the boot spread (s50), and on the final recipe they fail the rule written first (s63); upstream's `TF_GLM_DSCORES`
(default on in main) now does that job, so `all` and `33` are retirement candidates for a long-context decode window on a base that has it. Their rows are set at the engine's
defaults (`TF_GLM_INDEX_CUDA=1`, `TF_GLM_INDEX_DECODE_FROM=0`, `TF_GLM_OVN_DECODE_INDEX=0`) and are debt in the register. `INDEX_SCHED` and `POOLS32` left the series on
2026-11-22 (class F), so queue102's `INDEX_SCHED` arm no longer has a setting to measure.

## D. The 31 October decision, and the three levers it named

The `ai-engine` session, 2026-10-31 10:12 to 10:16, asked the owner about production's prompt numerics (`KDA_CHUNKED` + `SPARSE_ONEPASS` + `LATENT_MMA`: cold prompts -19% at 32k and -20%
at 133k together, GSM8K 1,242 to 1,238 of 1,319, p = 0.59, replies change). The answer, verbatim: "keep all off, we need speed for each knob on its own to see what gives best benefit and
whether we can either fix it or combine with another tweak elsewhere. needs to be logged". It is off *pending the per-knob run*, not a standing ban on numerics changes; the earlier
wording in KNOBS.md said the owner "decided to keep numerics changes off", which is looser than that. The per-knob run (`pnsolo`) gave: `SPARSE_ONEPASS` cold -9.4 / -10.2%,
`LATENT_MMA` -6.3 / -6.6%, `KDA_CHUNKED` -1.2 / -1.5%. What was then done with each: `SPARSE_ONEPASS` became the bit-exact `ONEPASS_PIPE` (in `prod.env`); `LATENT_MMA`'s speed is
the tensor core, no exact form can use it, and the exact forms gave `ABSORB_VEC` (about 1%) and `LATENT_TILE` (1.7 times slower than `ABSORB_VEC`, killed); `KDA_CHUNKED` stayed at
1% to 1.6% with changed replies. `LATENT_MMA`, `SEG_PASS`, `DECODE_SHARD` and `PK8` were never ported to the Zig series (patch 0020's header). `LATENT_MMA` is the one numerics
lever with a real prompt gain (about 6%) and a numerics change: the owner's call.

## E. What happens to class A (the plan as written before it ran; class F is what happened)

Whole patches cannot simply be deleted: the re-seat found 0019 is a build prerequisite of the active 0020, removing 0024 would switch the active `ONEPASS_PIPE` from its exact kernel to
the chunk kernel, and 0021 sits under every later `bodyProfile` edit (`work/reseat2/DECISIONS.md`). A text-only test (skip one patch, apply the other 37 in a temporary index with the two
append-only tables excluded) shows `0016` and `0039` stand alone, `0015` and `0018` break one or two later patches on adjacent lines, `0017` breaks four, and `0019`, `0021` and
`0024` break 11, 9 and 3. So the A set comes out knob by knob, after the re-seat onto upstream main lands, each removal gated, and each retired patch stays recoverable from this
repository's history. Class C and the `ABSORB_VEC` gate are decided by queue102 first.

## F. Retired 2026-11-21

Every class A switch whose patch was deleted whole, or whose switch was cut out of the patch that stays, left the series
on this date: `INDEX_REGROUP` (0013), `PLAIN_MARGIN` (0015), `EXCHANGE_KB` (0016), `ROUTER_WARM` (0017), `WIN_FREE`
(0018), `PIECE_KDA` (0039), `DRAFT_KEEPWIN` and `DFLASH2_WIN` (0006), `SPARSE_ONEPASS` (0019), `KDA_CHUNKED` (0021),
`MM_CLUSTER` and `ROUTER16` (0022). The cells above are the reason each one went. Still inside the series, on purpose:
`KVB8` (0023) and `FRONT_ROWS` (0038), whose removal is this dossier's next step, and the class B and C knobs.

Withdrawn 2026-11-22: the registry rows and doc rows of WIN_FREE, PLAIN_MARGIN, EXCHANGE_KB,
ROUTER_WARM and INDEX_REGROUP left `0020` (their code had already gone), so those five are no longer
accepted names at boot and are not settings of this engine: docs/KNOB-PROVENANCE.md class A is
their record. Engine tree `59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450`, whole stack `aaa0859cd487c032f0e3c10ac1b38041e0b4b33f` (gate run sg-20261122-090022).

Withdrawn 2026-11-22 (second pass): SPARSE_ONEPASS's last comment, ROUTER16's dead field and its two unlaunched
entry points, and INDEX_SCHED and POOLS32's rows, readers and doc rows left the series at their owning patches
(`0020`, `0022`, `0012`). DECODE_INDEX and the whole index path stay. Engine tree `59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450`, whole stack `aaa0859cd487c032f0e3c10ac1b38041e0b4b33f`
(gate run sg-20261122-090022, PASS).

2026-11-22: `tf_glm_hc_partial8_pdl` now instantiates `partial8<true>` (it launched `<false>`, so the PDL_EARLY arm's
dependent wait never existed). Default path untouched. Engine tree `59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450`, whole stack `aaa0859cd487c032f0e3c10ac1b38041e0b4b33f`, gate run sg-20261122-090022 PASS.

2026-11-22 (second pass): `0023` had its identity tile block removed (byte-identical by construction) and `0024` now
instantiates `partial8<true>`. Engine tree `59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450`, whole stack `aaa0859cd487c032f0e3c10ac1b38041e0b4b33f`, gate run sg-20261122-090022 PASS.

2026-11-22 (third pass): patches 0019 and 0020 skip the speculative next-tile QK block on the last tile (low-value
speed candidate, receipts in their headers). Engine tree `59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450`, whole stack `aaa0859cd487c032f0e3c10ac1b38041e0b4b33f`, gate run sg-20261122-090022 PASS.

2026-11-22 (fourth pass): `0025` bounds the dense call to the rows the select leaves alone (a 4,096-row first
chunk no longer runs dense attention over the 2,045 rows the sparse pass rewrites). Engine tree
`59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450`, whole stack `aaa0859cd487c032f0e3c10ac1b38041e0b4b33f`, gate run sg-20261122-090022 PASS.
