# PORT-LEFTOVER.md - what the fork has that the port lacks

`docs/PATCH-AUDIT.md` read the port against the pin: what the patches take away. This is the other direction: what the
fork (`ai-engine`, ref `fork-ssh/ovn-up` 595e28743944) changed against its own upstream base (`9b2991d122c7`) that our
tree does not have. The pin is 140 upstream commits past that base.

Instrument: `scripts/port-leftover.py ../ai-engine 9b2991d12 fork-ssh/ovn-up <tree>`. On the tree through 0042 plus
the item plan: 186 files, 479 hunks the fork rewrote and we left as upstream wrote them, 3,783 fork lines we lack.
Four read-only lanes classified every hunk of every file (2026-11-12); their full reports with file and line for
each claim are in `docs/audit-2026-11-12/leftover-*.md`. Nothing here was run on a GPU by the audit: each speed
figure is the fork's own from its commit message and needs our A/B before it is quoted as ours.

Counts by class (hunks): step and state 32 files; forward and kernels 46 files, 348 hunks (7 defect, 18 speed, 25
superseded by the pin, 216 unported features, 39 cosmetic); core and native 55 files, 240 hunks (5 defect, 63
speed, 10 superseded, 134 unported, 32 cosmetic); tests 53 files (5 defect candidates, 11 gate gaps).

## Defects

| # | what | reached by | fork commit | status |
|---|---|---|---|---|
| D1 | A paired prompt step wrote past the index rings | default, long lone prompt | part of `85df341ed` | fixed: patch 0042 |
| D2 | `chunkEnd` does not return to the 2,048 grid after a mark or resume, so no later step pairs (0042 refuses them all when the start is off the 4-row pool) | default, any prompt with a kept state in front | `cfa2cd93c` | lane prompt-step 01 |
| D3 | A logit gather posts one NCCL broadcast a row a rank; at three ranks a prompt-logprobs pass past about 100 rows never leaves `ncclGroupEnd` (a pin defect) | default at TP=3, `prompt_logprobs` | `0a77dcd7d` | lane sampler-guards 01 |
| D4 | `canBatch` admits a prompt with a cache mark inside it; the batched pass fires no mark and the state is not kept (the pin was safe through `snap_grid`, which 0007 removed) | default, two or more fresh prompts at once | `03138041e` | lane prompt-step 04 |
| D5 | The whole-pass `prefillFn` steps in fixed 2,048 rows and fires only marks on those starts | `TF_GLM_PROMPT_STEPS=0` and core callers of `backend.prefill` | `1b4bd2975` | lane prompt-step 03 |
| D6 | `TF_GLM_OVN_ONEPASS_PIPE` scales only 16 of 512 dims (pre-fix kernel ported) | knob | `dd426c1a1` | lane kernels-decode 04 |
| D7 | `TF_GLM_OVN_ONE_CHUNK` cannot be switched on: never opened, its KDA capture hook has no caller, `keepsInside` reads a field our engine lacks | knob | several | lane prompt-step 06 |
| D8 | `TF_GLM_OVN_DRAFT_EDGE`, `_NOISE` and `_BETA`'s noise are read and never used (the selector kept the pin's form) | knob | to find | lane kernels-decode 05 |
| D9 | `TF_GLM_OVN_REPLY_PREFILL`'s background pass can evict another conversation's latest kept state | knob | `c9468e336` | lane sampler-guards 02 |
| D10 | The follower binds a slot on a `.disk` step | unreachable today (no disk tier) | to find | lane prompt-step 05 |
| D11 | `df_sumw` runs every draft round at three ranks with no kernel contract record | default (a gate hole, no behaviour) | - | lane kernels-decode 06 |
| D12 | `glm_index_ovn_check.zig` and `glm_index_regroup_check.zig` cannot compile (their base's declarations are not `pub`) and no check of patches 0005, 0008, 0009, 0010 is registered in `main.zig` | build hazard, dead gates | - | lane sampler-guards 03 |

## Speed leads the fork has on by default

| # | what | where it lands | fork's own figure | fork commit | status |
|---|---|---|---|---|---|
| S1 | One-shot RoCE gather at worlds 2 to 4. The pin's gather refuses any world but 2, so at three ranks every small all-gather of a decode round is an NCCL collective: about 100 launches and 3.9 ms of kernel time a round in our profile | decode round | none | `060465305`, `1470a3c86`, `07dfdd046`, `57353178e` | applies clean; image `roce1` queued |
| S2 | DFlash2 ingests complete prompt taps at more than one rank (with the default split reduce each rank's drafter saw a stale residual for the other ranks' rows: two thirds of its prompt context at TP=3) | tokens a round after a prompt | none | `57c9f1367`, `f7b884fbd` | lane drafter-taps (first: is it in the pin) |
| S3 | The MTP head's prompt absorb is skipped when a drafter is loaded | cold prompt pass, kept-state size | 61-86 ms of each 1.5-1.8 s chunk, 4.0-4.7% of a cold pass | `a8ccc5c81` | lane prompt-step 02 |
| S4 | FP8 latent keys fetched a tile ahead in 8-byte loads | prompt MLA stage, decode chunk kernel | about 220 ms of a 2,048-row chunk | `450b9519c` | lane kernels-decode 01 |
| S5 | The EXL3 prompt experts take a whole chunk in one call (each expert's weights read once a chunk, not twice) | prompt pass | none; +270 MiB a rank | `0aec07b2f` | lane kernels-decode 02 |
| S6 | Pairing restored after an unaligned start (same change as D2) | cold prompt pass | 0 paired steps before on 8k / 33k / 134k prompts; pairing measures 1.6-2.6% of a cold pass here | `cfa2cd93c` | lane prompt-step 01 |
| S7 | Prompt chunks of 4,096 rows | prompt pass | none | `85df341ed` | after D2 lands |
| S8 | Render and tokenize a request once | host time before the prompt pass | 91 to 41 ms at 650k tokens, 25 to 10-13 ms at 200k | `ef81b4a49` | lane host-once |
| S9 | Shared windows made after the page pool (a larger KV page pool) | capacity | none | `d1661d165`, `d77dc922e` | open; tied to an unported knob |

Knob-gated levers on the hottest kernel (`tf_exl3_grouped_1`, 20.5 ms of a 42.8 ms round with the pad): `TF_EXL3_DEC_ORDER`
(`46b46550f`, "+1-3% decode" in the MiaAI recipe; lane kernels-decode 03), and the unported `TF_GLM_OVN_X3_NC`, `_X3_FUSEDOWN`,
`_X3_XROW`, `_X3_ROTEXPERT` family (`7d41fa9b7`, `ca8479639`, `95a3e51cb`), which needs `exl3_ovn.cuh`.

## Gate gaps (ported behaviour with no test)

From `leftover-tests.md` section 2, lane sampler-guards 03: the two index checks and the reply-prefill check registered;
`error.PastRing`'s unit test (`glm_ring_host.zig`); the shared-window check at 5 to 8 rows a stream; the rows grid round
trip on the I/O worker; the quiesce drain test; a snapshot kept past the index rings. With lane prompt-step: the
whole-pass `chunkEnd` test and the `canBatch` mark test.

## Where each item stands after the port lanes

Five lanes ported the list in private trees, one patch a fork commit; their reports are `docs/audit-2026-11-12/port-*.md`.
Stacked on the tree through 0042 in one integration tree (25 patches, one import-line merge by hand), the CPU gates
read: `check-native-cuda-host` 0, `compile-cuda-tests` 0, `zig fmt` 0, `test-cuda-host` the pin's own 26 failing
names and 62 more tests passing, the four standalone host steps 0, lean 116 problems against the pin's 116 (0 new).
None of these patches is in `patches/engine` until its GPU cells are in.

| item | patch (lane order) | fork commit | GPU receipt |
|---|---|---|---|
| lean: 11 multi-line comments from 0032, 0038, 0042 | lean-comments | - | none needed (no code) |
| D2 / S6 chunk grid | prompt-step 01 | `cfa2cd93c`, log line from `50bf69eb6` | image `ps1` queued |
| S3 MTP head skip with a drafter | prompt-step 02 | `a8ccc5c81` | image `ps2` queued |
| D5 whole pass steps at marks | prompt-step 03 | `1b4bd2975` | image `ps6` queued (knob-off digests) |
| D4 no batch with an interior mark | prompt-step 04 | `03138041e` | image `ps6` queued |
| D10 follower `.disk` bind | prompt-step 05 | `a3c043cca` | none possible (no disk tier) |
| D7 `ONE_CHUNK` wiring | prompt-step 06 | `083da32bb`, `7d01784c3`, `a6f5615d4` | image `ps6`, then the knob arm on `all1` |
| S4 FP8 keys a tile ahead | kernels-decode 01 | `450b9519c` | image `k1` queued |
| S5 EXL3 prompt experts a whole chunk (+146 MiB a rank as served) | kernels-decode 02 | `0aec07b2f` | image `k2` queued |
| `TF_EXL3_DEC_ORDER` knob | kernels-decode 03 | `46b46550f` | arms on `all1` queued |
| D6 one-pass pipe scale | kernels-decode 04 | `dd426c1a1` | knob arm on `all1` |
| D8 draft edge and noise | kernels-decode 05 | `39304587f`, `6f3127df8` | image `all1` (unset digest) |
| D11 `df_sumw` record | kernels-decode 06 | `09edd1ce0` | a fatbin build against the record |
| D3 logit gather, one block a rank | sampler-guards 01 | `0a77dcd7d` | a TP=3 `prompt_logprobs` request over 128 tokens |
| D9 reply-prefill eviction guard | sampler-guards 02 | `c9468e336` | knob arm on `all1`; `glm-reply-prefill-check` |
| D12 GPU checks compile and are registered | sampler-guards 03 | - | the three checks run on a Spark |
| gate gaps: PastRing test, window width, rows worker, quiesce drain, snapshot past rings | sampler-guards 04-07 | - | none needed (host tests) |
| S8 render and tokenize once | host-once 01-03 | `ef81b4a49` | measured on the laptop: `chat.prepare` 63.35 to 35.89 ms at 637k ids, 20.72 to 11.57 at 215k, ids identical; `all1` for digests |
| S1 RoCE gather at worlds 2 to 4 | lane roce (splitting `roce.zig` under 600 lines) | `060465305` and three | `roce1`: +2.0% and +1.7% at one and two streams against the same image on NCCL, level at four to eight; with the pad +2.8% and +3.2%; ABBA at six and eight queued |
| S2 complete prompt taps | no patch | - | already in the pin: upstream merged it as `2f894e0bb`; our tree's tap files are byte-identical to the pin's |
| S7 4,096-row prompt chunks, S9 shared windows after the pool | not started | `85df341ed`; `d1661d165` | - |

Three more defects the port lanes found by compiling or tracing, each with its patch:

- **`TF_GLM_OVN_GLUE_FUSE` gave wrong replies** (patch 0022): the fork changed `post` to take the buffer and passes
  the fused one at the last layer; the port kept the old signature, so the last layer's FFN contribution was missing
  from the window's final hidden state. Decode windows only, knob on. Lane drafter-taps 01 (`3423859e7`).
- **`TF_GLM_OVN_DRAFT_KEEPWIN` did nothing on the `MULTI_FILL` path** (patch 0023): a resumed piece restarted the
  drafter instead of restoring its kept window. Lane drafter-taps 02.
- **`glm_reply_prefill_check.zig` had never compiled** (patch 0008): it called `chunkOf` with an argument our tree
  does not have, and nothing imported the file. Lane sampler-guards 03.

One lane test was wrong and only the combined gate showed it: the fork's `canBatch` test uses a 2,088-token prompt,
which our 2,048-row chunk refuses for its length before the mark is looked at. Re-derived for a prompt inside one chunk.
`scripts/gates.sh` now runs `compile-cuda-tests` and the four standalone host steps, which is how it was found.
