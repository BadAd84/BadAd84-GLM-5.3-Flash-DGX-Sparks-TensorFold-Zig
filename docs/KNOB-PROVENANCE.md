# Why each knob our patches add is, or is not, in the recipe (2026-11-21)

The owner's question: for the knobs our patches added that `scripts/env/prod.env` does not set, was each one tested and found not good enough (so its patch goes), or did we find
the speed, add the setting, and then never turn it on? This file answers it knob by knob from the record. It is current state: when a knob's status changes, its row changes.

**Scope** (`python scripts/knob-inventory.py`, upstream clone at `work/up/TensorFold`): the engine series adds 54 `TF_` names that upstream's pin lacks. 20 are in `prod.env`.
5 of the rest are not settings (`TF_EXL3_OVN_BLOCKS` and `TF_GLM_HC_FINISH_PDL`, `_HC_GLUE`, `_HC_ROW` are CUDA preprocessor macros; `TF_GLM_OVN` is a prefix). That leaves
**29 real knobs outside `prod.env`: 6 only in `dev.env` and 23 in neither.** The classes below cover all 29.

**Sign convention.** A first-token or turn time that is negative is FASTER (it fell). A decode tokens-a-second change that is negative is SLOWER. Each row says which it quotes.

**Sources.** The retired engine's speed ledger (`docs/SPEEDUPS.md` of the `ai-engine` repo, kept whole in `archive/ai-engine`): its tables "Trades kept", "Killed by measurement" and
"Won so far", run labels in backticks. This repo's `docs/KNOBS.md` and the OVERNIGHT sections (s17 and so on). The owner's answers in the `ai-engine` and Zig sessions (quoted below).

## A. Tested, did not make the cut: the knob (and where nothing else needs it, the patch) goes

| knob (patch) | what the cells said |
|---|---|
| `TF_GLM_OVN_WIN_FREE` (0018) | decode -20.9 / -29.6 / -28.5 / -31.2 / -28.0% at 1 / 2 / 4 / 6 / 8 clients, replies equal, acceptance 0.24 to 0.36 (s44); retired engine on the flipped defaults: short decode -6.2% at 6 streams, -5.8% at 8, forks -15% (`wf8`) |
| `TF_GLM_OVN_PLAIN_MARGIN` (0015) | every round count unchanged, decode -1.3% to +1.2% (s50); retired engine: two ABBAs at 8 streams flat (`pm`) |
| `TF_GLM_OVN_EXCHANGE_KB=4096` (0016) | on top of `CHUNK_SOLO` and `ONEPASS_PIPE` the cold first token is -5.14 / -9.46 / -10.60% against -5.26 / -9.57 / -10.53% without it (s50); retired engine cold 8k 2.376 / 2.373 s against 2.361 / 2.363 s (`xkb8k`) |
| `TF_GLM_OVN_ROUTER_WARM` (0017) | retired engine at 1 stream: decode -0.5% short and -0.5% forks, both boots (`rwarm`); s17 neutral (-2% in first cells, -0.6 to +1.4% repeated) |
| `TF_GLM_OVN_PDL_EARLY` (0020) | decode -0.6 / -0.9 / 0.0 / -0.1 / +0.5% (first cells) and -0.4 / -0.4 / -0.3 / -0.1 / +0.3% (repeated) at 1 / 2 / 4 / 6 / 8 (s20, `is-pdl`); retired engine: alone it gains nothing at 2 streams and costs per-stream short decode -2.7% at 4 (`railsparts`); upstream's default `TF_GLM_PDL` is the same launch attribute |
| `TF_GLM_OVN_MM_CLUSTER=1` (0022) | one boot, 79.02 / 82.16 / 110.40 tok/s against the control boots' means 79.97 / 83.31 / 110.83 at 1 / 2 / 4 clients: -1.2 / -1.4 / -0.4% (computed here from the s45 control values), replies equal; retired engine level at 1 and 4 streams (`ovn4b`) |
| `TF_GLM_OVN_ROUTER16` 3 and 4 (0022, used by 0024) | one boot each at 1 / 2 / 4 clients, between its two controls at every level, replies equal (s45); retired engine level at 1 and 4 streams (`ovn4b`) |
| `TF_GLM_OVN_GLUE_FUSE=32` (0024) | retired engine decode -0.3% at 1 stream and -1.3% at 4 (`ovn4b`); s17 -2% in the first cells, -0.6 to +1.4% repeated |
| `TF_GLM_OVN_GLUE_ROW` (0024) | cold first token at 8k / 32k within +-1.4% of a control whose pair differs by 2% (s31); the related `HC_ROWS=16` lost in the retired engine (`p14parts`) |
| `TF_GLM_OVN_DRAFT_KEEPWIN` (0006) | decode +8.6 / +6.5 / +5.9 / +6.5 / +6.0% against +8.1 / +6.1 / +5.5 / +6.0 / +4.2% without it: inside the noise (s17) |
| `TF_GLM_DFLASH2_WIN` (0006) | the default 2,048 is the no-op. `=1024`: code decode at about 100k and 250k depth -1.5% and -2.5%, -1.2% and -1.7% (s50). The retired engine's `=32` prose +9 to 10% was measured while the drafter's prompt taps were stale; with complete taps (fixed since) more context helps and the sweep was recorded as moot |
| `TF_GLM_OVN_INDEX_REGROUP` (0013) | alone, cold 32k -0.3% and about 200k cold -0.2%, forks TTFT +2.6% (`p14parts`): the kernel is 4.2 to 5.2% faster and the prompt pass does not show it |
| `TF_GLM_OVN_FRONT_ROWS` (0038) | 2,048: warm turns 3.2% to 3.8% slower and cold 0.7% to 3.4% slower; 512 and 768 no gain (s61) |
| `TF_GLM_OVN_PIECE_KDA` (0039) | cold first token +0.73 / +0.88 / +0.97% (slower) at 8k / 32k / 120k, turns 2 to 8 level (s67). No other patch needs it |
| `TF_GLM_OVN_KVB8` (rows in 0020, code in 0023) | changes replies (s45); cold -0.53 / -0.51 / -0.53% (faster), 14 of 16 reply digests differ, rounds 2.2% and 3.6% longer (s61) |
| `TF_GLM_OVN_KDA_CHUNKED` (0021) | changes replies; cold -0.95 / -1.19 / -1.58% (faster) with 12 of 16 digests differing (s61); retired engine alone cold -1.2 / -1.5%, GSM8K 283 of 300 against 282 (`pnsolo`) |
| `TF_GLM_OVN_SPARSE_ONEPASS` (0019) | changes replies; retired engine alone cold -9.4 / -10.2% at 32k / 133k (`pnsolo`). `ONEPASS_PIPE` (patch 0020, in `prod.env`) is the same pipeline with today's bytes: retired engine cold -9.8% at 32k and 200k, this recipe -5.30 / -6.74 / -6.95% at 8k / 32k / 120k (s50). 0019 is a build prerequisite of 0020, so only its knob and routing can go |

`TF_GLM_KDA_DUMP` (0005) is not a speed lever: it writes the KDA input stack to a file for the pad's FP64 gate, and goes with that gate, not with this list.

## B. Proven faster, not turned on

| knob | the speed, and why it is off |
|---|---|
| the ten `dev.env` candidates: `MM_WIDE`, `SIDE_PRIO`, `OVERLAP_PIECES=4`, `LATENT_ROWS=2`, `PIECE_FRONT`, `PIECE_FFN`, `PIECE_MLA`, `NCCL_NCHANNELS_PER_NET_PEER=4`, `SOLO_TO_START`, `RESTORE_HELD` | together, on main (queue91, s72): cold first token +8.3 / +8.9 / +8.4% faster at 8k / 32k / 120k, warm turns +7.9% faster, replies equal. Off because as a bundle decode at 1, 2 and 4 clients reads lower in 12 of 12 cells (mean 0.86%), and the repo rule allows no regression at any level. Alone (s51, s53): `MM_WIDE` cold -2.1 to -3.4%, `SIDE_PRIO` -1.7 to -2.3%, `LATENT_ROWS=2` -0.05 to -0.5%. **Queue95 splits the four that can touch decode from the six that cannot; it runs next after queue100** |
| `TF_GLM_REQUEST_STARTS=1` (upstream's) | warm turns 34% to 36% faster; its cost is +4 to +7% on a cold prime and not-clean 6- and 8-client decode cells (KNOBS.md). Waits on queue100 |
| `TF_GLM_OVN_ABSORB_VEC` (rows in 0020, code in 0023) | byte-identical. Retired engine at 1 stream (`vec2`): cold 32k -1.0% and 200k cold -1.0% (faster), warm turns -0.7% to -2.0% (faster). At 2 to 8 streams (`vecv`): cold 32k 1.1%, 200k 0.9% and the warm next turn 1.3% faster, but short TTFT 1.7% worse, round-3 TTFT 2.5% worse and per-stream decode 1.0% slower. The ledger's own remedy, the vector loads on prompt rows only, was never built, and the knob was never measured at 120k on this recipe. Queue102 measures it |
| `TF_CACHE_EVICT=decayed_resume` (upstream's) | 47.40% fewer rows rebuilt (queue98, s75); the five-level check (queue99, s78) is NOT ACCEPTED by three 6- and 8-client decode cells inside the box's noise. A waiver is the owner's call |

## C. Never measured where it could matter

`TF_GLM_OVN_INDEX_SCHED` (production's prompt scorer schedule) and `TF_GLM_OVN_POOLS32` (patch 0012) act on the DSA indexer's prompt scoring, whose cost grows with the context. They
were read on decode cells and on cold 8k and 32k prompts only (s17, s31), never on a 120k cold prompt. `TF_GLM_INDEX_CUDA=all`, `TF_GLM_INDEX_DECODE_FROM` (0007) and
`TF_GLM_OVN_DECODE_INDEX` (0012) route decode windows to the index kernels at depth: at 100k and 250k they read -0.2% to +1.0% (`all`) and -0.9% to +0.5% (`33`), inside the boot spread
(s50), and on the final recipe they fail the rule written first (s63); upstream's `TF_GLM_DSCORES` (default on in main) now does that job, so they are retirement candidates for a
long-context decode window on a base that has it. **Queue102 measures `INDEX_SCHED` with `POOLS32` and `ABSORB_VEC` at 120k now.**

## D. The 31 October decision, and the three levers it named

The `ai-engine` session, 2026-10-31 10:12 to 10:16, asked the owner about production's prompt numerics (`KDA_CHUNKED` + `SPARSE_ONEPASS` + `LATENT_MMA`: cold prompts -19% at 32k and -20%
at 133k together, GSM8K 1,242 to 1,238 of 1,319, p = 0.59, replies change). The answer, verbatim: "keep all off, we need speed for each knob on its own to see what gives best benefit and
whether we can either fix it or combine with another tweak elsewhere. needs to be logged". It is off *pending the per-knob run*, not a standing ban on numerics changes; the earlier
wording in KNOBS.md said the owner "decided to keep numerics changes off", which is looser than that. The per-knob run (`pnsolo`) gave: `SPARSE_ONEPASS` cold -9.4 / -10.2%,
`LATENT_MMA` -6.3 / -6.6%, `KDA_CHUNKED` -1.2 / -1.5%. What was then done with each: `SPARSE_ONEPASS` became the bit-exact `ONEPASS_PIPE` (in `prod.env`); `LATENT_MMA`'s speed is
the tensor core, no exact form can use it, and the exact forms gave `ABSORB_VEC` (about 1%) and `LATENT_TILE` (1.7 times slower than `ABSORB_VEC`, killed); `KDA_CHUNKED` stayed at
1% to 1.6% with changed replies. `LATENT_MMA`, `SEG_PASS`, `DECODE_SHARD` and `PK8` were never ported to the Zig series (patch 0020's header). `LATENT_MMA` is the one numerics
lever with a real prompt gain (about 6%) and a numerics change: the owner's call.

## E. What happens to class A

Whole patches cannot simply be deleted: the re-seat found 0019 is a build prerequisite of the active 0020, removing 0024 would switch the active `ONEPASS_PIPE` from its exact kernel to
the chunk kernel, and 0021 sits under every later `bodyProfile` edit (`work/reseat2/DECISIONS.md`). A text-only test (skip one patch, apply the other 37 in a temporary index with the two
append-only tables excluded) shows `0016` and `0039` stand alone, `0015` and `0018` break one or two later patches on adjacent lines, `0017` breaks four, and `0019`, `0021` and
`0024` break 11, 9 and 3. So the A set comes out knob by knob, after the re-seat onto upstream main lands, each removal gated, and each retired patch stays recoverable from this
repository's history. Class C and the `ABSORB_VEC` gate are decided by queue102 first.
