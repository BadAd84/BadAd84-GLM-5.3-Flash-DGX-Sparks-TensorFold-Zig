# RECORD.md - patches/engine

What it is: the recipe's engine patch series, applied in file-name order by `scripts/apply.sh` to a pristine
checkout of the pinned upstream engine. Nothing in the engine tree is edited outside these files.

Base: `ashhart/TensorFold` at `93a2e93ecebff8aa52b88e58c5dd222516e69c5f` (tag `v1.2.7`, `scripts/config.sh` `TF_REF`).

Where it comes from: our earlier series on the pin `9c9bf542` (itself ports of our fork `ai-engine` and of upstream
PR #2044), folded so each patch is one lever with its repairs inside it (`docs/audit-2026-11-12/fold-series.md`), then
re-seated on v1.2.7 (`docs/audit-2026-11-12/reseat-v127.md`: what upstream changed under each patch, and the decision
for each). Every patch header names its provenance and its receipts. Every switch defaults off, is a row of the
`.glm` or `.cuda` scope of `zig/src/platform/environment.zig`, and has a line in `docs/environment.md`.

Proof the series rebuilds: `scripts/apply.sh` on the tag gives tree `93a99447e7030697ca29b93cc1410871bb34c98a`; all
patches apply with plain `git apply --check`, no file passes 600 lines at any prefix, and lean base against head is
386 problems against 386. With every switch off the image decodes 51.55 / 60.88 / 83.11 / 111.63 / 137.43 tok/s at
1 / 2 / 4 / 6 / 8 streams against 50.16 / 58.57 / 79.23 / 106.37 / 129.66 on the clean tag, replies byte-identical
(`docs/OVERNIGHT-2026-11-12.md` section 13).

| patch | subject | switches it registers |
|---|---|---|
| 0001 | glm cuda: a logit gather broadcasts one block a rank, not one a row | - |
| 0002 | glm tests: the shared-window check sizes its rows from the engine, not a literal 4 | - |
| 0003 | core and server: the disk grid on the I/O worker, and a quiesce drain test | - |
| 0004 | host: the prompt-bench step, so request preparation can be timed on this tree | - |
| 0005 | core: the TF_GLM_OVN knob registry | - |
| 0006 | glm: TF_GLM_KDA_PAD pads the KDA input stack at one width | `TF_GLM_KDA_DUMP` |
| 0007 | glm: the DFlash2 draft knobs (TF_GLM_OVN_DRAFT_*) | `TF_GLM_DFLASH2_WIN`, `TF_GLM_OVN_DRAFT_ONEPASS`, `TF_GLM_OVN_DRAFT_DOWN4`, `TF_GLM_OVN_DRAFT_KEEPWIN`, `TF_GLM_OVN_DRAFT_MLPSPLIT`, `TF_GLM_OVN_DRAFT_EDGE`, `TF_GLM_OVN_DRAFT_BETA`, `TF_GLM_OVN_DRAFT_NOISE`, `TF_GLM_OVN_DRAFT_CUTS` |
| 0008 | glm cuda: the index kernels take decode windows (TF_GLM_INDEX_CUDA) | `TF_GLM_INDEX_DECODE_FROM` |
| 0009 | core: kept-state walks gated by the last id (TF_GLM_OVN_KEPT_WALK) | `TF_GLM_OVN_KEPT_WALK` |
| 0010 | glm cuda: a pass the rebased index ring cannot hold is refused, not written past it | - |
| 0011 | glm checks: the OVN check commands in their own table beside main.zig's | - |
| 0012 | glm exl3: decode windows on the 16-pair item plan | - |
| 0013 | glm forward: the prompt pieces' ranges and events beside the pieced exchanges | - |
| 0014 | glm cuda: TF_GLM_OVN_DECODE_INDEX, _INDEX_SCHED, _POOLS32 | `TF_GLM_OVN_DECODE_INDEX`, `TF_GLM_OVN_INDEX_SCHED`, `TF_GLM_OVN_POOLS32` |
| 0015 | glm index: TF_GLM_OVN_INDEX_REGROUP, the reduce-scatter head sum | `TF_GLM_OVN_INDEX_REGROUP` |
| 0016 | glm lanes: the stepped prompt pass in its own file beside cuda_lanes.zig | - |
| 0017 | lanes: TF_GLM_OVN_PLAIN_MARGIN, the draft-over-plain margin as a knob | `TF_GLM_OVN_PLAIN_MARGIN` |
| 0018 | glm relay: TF_GLM_OVN_EXCHANGE_KB, a direct exchange posted in pieces | `TF_GLM_OVN_EXCHANGE_KB` |
| 0019 | glm: TF_GLM_OVN_ROUTER_WARM warms the router kernels at boot | `TF_GLM_OVN_ROUTER_WARM` |
| 0020 | glm lanes: TF_GLM_OVN_WIN_FREE, shared rounds fill with no cost model | `TF_GLM_OVN_WIN_FREE` |
| 0021 | glm cuda: TF_GLM_OVN_SPARSE_ONEPASS, production's prompt sparse attention | `TF_GLM_OVN_SPARSE_ONEPASS` |
| 0022 | glm: TF_GLM_OVN_ONEPASS_PIPE, the one-pass pipeline with bit-exact switches | `TF_GLM_OVN_ONEPASS_PIPE`, `TF_GLM_OVN_ONEPASS_EXACT`, `TF_GLM_OVN_MLA_FUSEMERGE`, `TF_GLM_OVN_ABSORB_VEC`, `TF_GLM_OVN_KVB8` |
| 0023 | glm cuda: TF_GLM_OVN_KDA_CHUNKED, production's chunked KDA prompt kernel | `TF_GLM_OVN_KDA_CHUNKED` |
| 0024 | glm cuda: TF_GLM_OVN_MM_WIDE, _SWIGLU_REDUCE, _MM_CLUSTER, _MM_DECTILE | `TF_GLM_OVN_MM_WIDE`, `TF_GLM_OVN_MM_CLUSTER`, `TF_GLM_OVN_MM_DECTILE`, `TF_GLM_OVN_ROUTER16`, `TF_GLM_OVN_SWIGLU_REDUCE` |
| 0025 | glm cuda: TF_GLM_OVN_MLA_FUSEMERGE, _ABSORB_VEC, _KVB8 | - |
| 0026 | glm cuda: TF_GLM_OVN_GLUE_FUSE, _GLUE_ROW, _PDL_EARLY | `TF_GLM_OVN_GLUE_FUSE`, `TF_GLM_OVN_GLUE_ROW`, `TF_GLM_OVN_PDL_EARLY` |
| 0027 | glm latent: the head block takes the head count back (test-cuda-host green) | - |
| 0028 | glm cuda: the MTP head's own passes run only without a DFlash2 drafter | - |
| 0029 | glm cuda: the EXL3 prompt experts take a whole 2,048-row chunk in one call | - |
| 0030 | exl3: TF_EXL3_DEC_ORDER launches each k slice's blocks before the items | `TF_EXL3_DEC_ORDER` |
| 0031 | host: byte equality by indexOfDiff, and a string index that stops counting at it | - |
| 0032 | glm cuda: FP8 latent keys fetched a tile ahead, in 8-byte loads | - |
| 0033 | server: render and tokenize a request once, and TF_GLM_OVN_HOST_ONCE | `TF_GLM_OVN_HOST_ONCE` |

Hashes: `SHA256SUMS`, one line a patch, checked by `scripts/check-patch-packages.sh`.
