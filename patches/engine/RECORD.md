# RECORD.md - the v1.2.9 engine series (lane V129A)

What it is: the recipe's engine patch series re-seated on upstream TensorFold v1.2.9, applied in file-name order by
`apply.sh` (this directory) or by `scripts/apply.sh` once the series lands in `patches/engine/`. Nothing in the engine
tree is edited outside these files.

Base: `ashhart/TensorFold` at `6b9de695104b6b8b30c20458da87ac06c9480289` (tag `v1.2.9`).

Where it comes from: the v1.2.7 series in `patches/engine/` (36 patches, tree
`2a07e8cff17123a4fad350f5fb1213fcdb93e28e`), each patch's own delta played onto v1.2.9 with a three-way merge against
the pre-image it was written for (`work/V129A/reseat.py`), then every conflict settled against the upstream commit
that moved the code. The old-side series was rebuilt first from the v1.2.7 pin (commit a patch) so each patch's own
delta, not the series' net change, is what moved.

Retired on this base (absorbed by upstream; each with the commit that absorbed it and the proof, in
`work/V129A/REPORT.md`):

| old patch | upstream commit | why it is gone |
|---|---|---|
| 0001 logit-gather-blocks | 5cd52c7a8, 5b927e2bf | the gather, its staging buffer and the admission accounting are v1.2.9's |
| 0013 forward-pieces-split | 1ba369792 | Pieces, cuts, row_step, max_pieces and ranges moved to cuda_forward_pieces.zig and re-exported |
| 0029 exl3-chunk-rows | 8978c4357 | a prompt pass runs in calls of up to prompt_rows (4,096) rows, so a 2,048-row chunk is one call |
| 0036 exl3-prompt-ey-direct | 8978c4357, dc4aef0ec | the prompt down kernel writes the caller's slot rows; exl3_prompt.Scratch has no staged y |

Proof the series rebuilds and its gates (2026-11-16): applying the 33 patches to the tag with plain `git apply --cached` on
a pristine index gives tree `c08dd8eade958dd857c180593e0e383e12c7e044` (the `series-check.sh` method);
`patches/pr1411/apply.sh --check` on that tree gives `fde9658728dd6ca086e96dc37f0d82cbb060cd07` and
`patches/cache-salt/apply.sh --check` on that one gives the stack `e946a74361ca54f02c3baee5437786a1c4dbfe73`.
`scripts/spark-gates.py` built both trees from these files on a shared x86_64 host and got the same ids; series and stack
PASS against the pristine base (every step rc 0 but `test-cuda-host`, which fails only the base's own `cli_config_test`
serve --config test; no new failing name; lean 0 new).

| patch | from (v1.2.7) | subject | switches it registers |
|---|---|---|---|
| 0001 | 0002 | glm tests: the shared-window check sizes its rows from the engine, not a literal 4 | - |
| 0002 | 0003 | core and server: the disk grid on the I/O worker, and a quiesce drain test | - |
| 0003 | 0004 | host: the prompt-bench step, so request preparation can be timed on this tree | - |
| 0004 | 0005 | core: the TF_GLM_OVN knob registry | - |
| 0005 | 0006 | glm: TF_GLM_KDA_PAD pads the KDA input stack at one width | `TF_GLM_KDA_DUMP` |
| 0006 | 0007 | glm: the DFlash2 draft knobs (TF_GLM_OVN_DRAFT_*) | `TF_GLM_DFLASH2_WIN`, `TF_GLM_OVN_DRAFT_ONEPASS`, `TF_GLM_OVN_DRAFT_DOWN4`, `TF_GLM_OVN_DRAFT_KEEPWIN`, `TF_GLM_OVN_DRAFT_MLPSPLIT`, `TF_GLM_OVN_DRAFT_EDGE`, `TF_GLM_OVN_DRAFT_BETA`, `TF_GLM_OVN_DRAFT_NOISE`, `TF_GLM_OVN_DRAFT_CUTS` |
| 0007 | 0008 | glm cuda: the index kernels take decode windows (TF_GLM_INDEX_CUDA) | `TF_GLM_INDEX_DECODE_FROM` |
| 0008 | 0009 | core: kept-state walks gated by the last id (TF_GLM_OVN_KEPT_WALK) | `TF_GLM_OVN_KEPT_WALK` |
| 0009 | 0010 | glm cuda: a pass the rebased index ring cannot hold is refused, not written past it | - |
| 0010 | 0011 | glm checks: the OVN check commands in their own table beside main.zig's | - |
| 0011 | 0012 | glm exl3: decode windows on the 16-pair item plan (TF_GLM_OVN_EXL3_ITEMS, default off) | `TF_GLM_OVN_EXL3_ITEMS` |
| 0012 | 0014 | glm cuda: TF_GLM_OVN_DECODE_INDEX, _INDEX_SCHED, _POOLS32 | `TF_GLM_OVN_DECODE_INDEX`, `TF_GLM_OVN_INDEX_SCHED`, `TF_GLM_OVN_POOLS32` |
| 0013 | 0015 | glm index: TF_GLM_OVN_INDEX_REGROUP, the reduce-scatter head sum | `TF_GLM_OVN_INDEX_REGROUP` |
| 0014 | 0016 | glm lanes: the stepped prompt pass in its own file beside cuda_lanes.zig | - |
| 0015 | 0017 | lanes: TF_GLM_OVN_PLAIN_MARGIN, the draft-over-plain margin as a knob | `TF_GLM_OVN_PLAIN_MARGIN` |
| 0016 | 0018 | glm relay: TF_GLM_OVN_EXCHANGE_KB, a direct exchange posted in pieces | `TF_GLM_OVN_EXCHANGE_KB` |
| 0017 | 0019 | glm: TF_GLM_OVN_ROUTER_WARM warms the router kernels at boot | `TF_GLM_OVN_ROUTER_WARM` |
| 0018 | 0020 | glm lanes: TF_GLM_OVN_WIN_FREE, shared rounds fill with no cost model | `TF_GLM_OVN_WIN_FREE` |
| 0019 | 0021 | glm cuda: TF_GLM_OVN_SPARSE_ONEPASS, production's prompt sparse attention | `TF_GLM_OVN_SPARSE_ONEPASS` |
| 0020 | 0022 | glm: TF_GLM_OVN_ONEPASS_PIPE, the one-pass pipeline with bit-exact switches | `TF_GLM_OVN_ONEPASS_PIPE`, `TF_GLM_OVN_MLA_FUSEMERGE`, `TF_GLM_OVN_ABSORB_VEC`, `TF_GLM_OVN_KVB8` |
| 0021 | 0023 | glm cuda: TF_GLM_OVN_KDA_CHUNKED, production's chunked KDA prompt kernel | `TF_GLM_OVN_KDA_CHUNKED` |
| 0022 | 0024 | glm cuda: TF_GLM_OVN_MM_WIDE, _SWIGLU_REDUCE, _MM_CLUSTER, _MM_DECTILE | `TF_GLM_OVN_MM_WIDE`, `TF_GLM_OVN_MM_CLUSTER`, `TF_GLM_OVN_MM_DECTILE`, `TF_GLM_OVN_ROUTER16`, `TF_GLM_OVN_SWIGLU_REDUCE` |
| 0023 | 0025 | glm cuda: TF_GLM_OVN_MLA_FUSEMERGE, _ABSORB_VEC, _KVB8 | - |
| 0024 | 0026 | glm cuda: TF_GLM_OVN_GLUE_FUSE, _GLUE_ROW, _PDL_EARLY | `TF_GLM_OVN_GLUE_FUSE`, `TF_GLM_OVN_GLUE_ROW`, `TF_GLM_OVN_PDL_EARLY` |
| 0025 | 0027 | glm latent: the head block takes the head count back (test-cuda-host green) | - |
| 0026 | 0028 | glm cuda: the MTP head's own passes run only without a DFlash2 drafter | - |
| 0027 | 0030 | exl3: TF_EXL3_DEC_ORDER launches each k slice's blocks before the items | `TF_EXL3_DEC_ORDER` |
| 0028 | 0031 | host: byte equality by indexOfDiff, and a string index that stops counting at it | - |
| 0029 | 0032 | glm cuda: FP8 latent keys fetched a tile ahead, in 8-byte loads | - |
| 0030 | 0033 | server: render and tokenize a request once, and TF_GLM_OVN_HOST_ONCE | `TF_GLM_OVN_HOST_ONCE` |
| 0031 | 0034 | glm exl3: TF_GLM_OVN_X3_NC, X3_XROW and X3_FUSEDOWN, production's decode kernels on the item plan | `TF_GLM_OVN_X3_NC`, `TF_GLM_OVN_X3_XROW`, `TF_GLM_OVN_X3_FUSEDOWN` |
| 0032 | 0035 | glm cuda: TF_GLM_OVN_KEEP_SEQS, a released stream's sequence stays for the next request on its slot | `TF_GLM_OVN_KEEP_SEQS` |
| 0033 | - | server: TF_GLM_OVN_OFF_EFFORT_LINE, a thinking-off GLM-5.3 prompt without its default effort line | `TF_GLM_OVN_OFF_EFFORT_LINE` |

0033 is not a re-seat of a v1.2.7 patch: it is new here (2026-11-16), written on this base. Its row in
`zig/src/platform/environment.zig` sits after `TF_GLM_OVN_HOST_ONCE` rather than at the end of the `.glm` rows, so
`patches/pr1411`'s environment.zig and docs/environment.md hunks still apply on top of this series.

Every switch still defaults off and is a row of the `.glm` scope of `zig/src/platform/environment.zig` (TF_GLM_OVN_*
through `cuda/ovn.zig`), with a line in `docs/environment.md`. Every kept patch keeps its own header (source, what
changed, receipts) and gains one line naming how it was re-seated; a patch whose hunks moved by hand says which
upstream change moved them.

Hashes: `SHA256SUMS`, one line a patch, checked by `series-check.sh` (and by `scripts/check-patch-packages.sh` once the
directory sits under a package root).
