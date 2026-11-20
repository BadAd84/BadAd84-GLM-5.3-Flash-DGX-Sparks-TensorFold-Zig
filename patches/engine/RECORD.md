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
| 0034 | - | glm lanes: TF_GLM_OVN_NO_COPY, a DFlash2 drafter's windows without copied continuations | `TF_GLM_OVN_NO_COPY` |
| 0035 | - | glm cuda tests: glm-mm-ovn, the matmul launch variants against the default launch byte for byte | - |
| 0036 | - | glm latent: TF_GLM_OVN_LATENT_ROWS, absorb_q and expand_v two and four rows a loop step | `TF_GLM_OVN_LATENT_ROWS` |
| 0037 | - | glm cuda: TF_GLM_OVN_SIDE_PRIO, the prompt exchanges' side stream at the highest priority without a pair | `TF_GLM_OVN_SIDE_PRIO` |
| 0038 | - | glm cuda: TF_GLM_OVN_PIECE_FRONT, _MLA, _FFN and FRONT_ROWS, the next block's row-by-row front run piece by piece as the rows land | `TF_GLM_OVN_PIECE_FRONT`, `TF_GLM_OVN_PIECE_MLA`, `TF_GLM_OVN_PIECE_FFN`, `TF_GLM_OVN_FRONT_ROWS` |
| 0039 | - | glm cuda: TF_GLM_OVN_PIECE_KDA, a KDA mixer site's chain run in the ranges the pieces cut, each ahead of its pieces' o_proj and exchange | `TF_GLM_OVN_PIECE_KDA` |

0033 is not a re-seat of a v1.2.7 patch: it is new here (2026-11-16), written on this base. Its row in
`zig/src/platform/environment.zig` sits after `TF_GLM_OVN_HOST_ONCE` rather than at the end of the `.glm` rows, so
`patches/pr1411`'s environment.zig and docs/environment.md hunks still apply on top of this series.

0034 is not a re-seat of a v1.2.7 patch either: it is new here (2026-11-16), written on this base. Its row in
`zig/src/platform/environment.zig` sits after `TF_GLM_OVN_WIN_FREE`'s, and its line in `docs/environment.md` after that
switch's, so `patches/pr1411`'s environment.zig and docs/environment.md hunks still apply on top of this series. The
34-patch series is tree `6363e6b5d3faab6646cd361cf357d24745764d62`; pr1411 then cache-salt make the stack
`5058123fa4f4f38637c0a5c023936b462cba453b` (the gate host's `git write-tree`, run sg-20261116-234035: series and stack
PASS against the pristine base, lean 0 new).

0035 is the GPU check that `0022-mm-knobs.patch` was ported without: `zig/tests/cuda/glm_mm_ovn_tests.zig` from the fork
commit the knobs came from (ai-engine `cbf94fde5`), on this tree's helpers, with a planted control the fork's file did
not have. It registers `glm-mm-ovn` in `zig/tests/cuda/glm_ovn_checks.zig`, so `zig/tests/cuda/main.zig` stays at 599
lines, and gives the host stub `zig/test_support/glm_mm_cuda.zig` the `cluster` field `cuda_mm.zig` names. No engine
file changes. The 35-patch series is tree `2af443845021d4b310032b3e51d81c38d6059df4` (run sg-20261116-230553: PASS
against the pristine base, `compile-cuda-tests` rc 0, lean 0 new); with pr1411 and cache-salt the stack is
`f3204870b8fce9de0731527420584b6893d3a2da` (38 patches; run sg-20261117-002047: series and stack PASS, lean 0 new).

0036 is new here too (2026-11-19), written on this base: it adds `tf_glm_absorb_q_x2`, `_x4`, `tf_glm_expand_v_x2` and
`_x4` to `zig/kernels/cuda/glm_glue_latent.cuh` (the same block and the same per-row chain, with 2 or 4 rows in flight
between one pair of syncs) and the switch that takes them on plain bf16 kv_b, and registers `glm-latent-rows` in
`zig/tests/cuda/glm_ovn_checks.zig`, so `zig/tests/cuda/main.zig` keeps its own line count. Its row in
`zig/src/platform/environment.zig` sits after `TF_GLM_OVN_KVB8`'s and its line in `docs/environment.md` after that
switch's, so `patches/pr1411`'s environment.zig and docs/environment.md hunks still apply on top. The 36-patch series is
tree `bb881628a1995a58308c64c44a9522e9e3c153d2`; pr1411 makes `da6fb412b415964303c93c18d7da9f98626c9b85`, cache-salt
`33247f87b97b2762424a0e5390cf86044be13268`, learn-starts `85d45758d73b66f75f6fbe38b0c58a9cde586008` and solo-cuts
`fc3526cde368da5a0a034794045c3bd5c1bf2814` (42 patches), each a `git write-tree` on a temporary index from the pin
(the gate host's own build reproduced the 41-patch id without solo-cuts, and the same id comes out with 0036 applied
after the packages). On the shared x86_64 gate host, `scripts/spark-gates.py iter` on the 41-patch stack without
solo-cuts got `check-native-cuda-host` 7 of 7 steps rc 0, `fmt` rc 0, `test-cuda-host` 6,904 of 6,938 tests passed with
only the base's own `cli_config_test.test.serve --config` name failing, and lean 341 problems against the base's 341,
0 new. An image built from that tree on spark1 with nvcc sm_121 compiled the glue fatbins and `tf-cuda-test`. With all the
packages (42 patches, tree `fc3526cde368`) a full run, `sg-20261119-101335`, passes against the pristine pin: every step rc 0
but `test-cuda-host`, which fails only the base's own name, and lean 0 new. The GPU check ran in queue73 (docs/OVERNIGHT-2026-11-12.md
section 51): one boot at 2 rows (and one at 4) read 0.3 to 0.5% under the control pair's cold first token at 8k, 32k and 120k, and
the decode screens at 2 rows read 0.6 to 1.7% above the control in 6 of 6 cells; the A B B A that decides it is queue75.

0037 is new here as well (2026-11-19): `zig/src/families/glm/cuda_forward_pieces.zig`'s `Pieces.init` made the prompt exchanges' side
stream at the highest priority only for a pair (`TF_GLM_PROMPT_PAIR`, whose twin a server with solo passes does not hold), so the
recipe's server ran it at the default priority. `TF_GLM_OVN_SIDE_PRIO=1` gives it the pair's priority without a pair: `Pieces.high(pair)`
is `pair` or the switch, and the engine passes its result to `Pieces.init` and logs the priority at boot when the switch set it.
Scheduling only; the bits are the same, and the default path is the code as it was. The host test is `cuda_side_prio_test.zig`
(listed in `cuda.zig`'s test block); the engine's wiring has no host test, and its boot log line is what names it on a GPU. The
registry row follows `TF_GLM_OVN_LATENT_ROWS`'s and the docs line follows that switch's, so `patches/pr1411`'s hunks still apply on top.
The 37-patch series is tree `d674e199cf6d97f7ac84a374c83153baabc911ed`; pr1411 and cache-salt make `4a72871f89fac64631c9b6701d0d121ed8dde79a`,
learn-starts `098a8968dc83c191e71c67bc3a9a13da9545a52c`, solo-cuts (revised 2026-11-19, it grows the index ring) `b0ae14df04d750dfbc217d13efc9a998d0ac6ac8`
(43 patches) and disk-any-position `7656da6d8139b1b139ad0262bd3bb812897b0665` (44 patches); the gate host's own build of the same lists
reproduced the 44-patch id. A full run on the shared x86_64 gate host, `sg-20261119-210540`, passes against the pristine pin for that
stack: every step rc 0 but `test-cuda-host`, which fails only the base's own `cli_config_test.test.serve --config` name (6,912 of
6,946 tests passed, 33 skipped), and lean 341 problems against the base's 341, 0 new. Three mutants of `Pieces.high` (the switch
ignored, a pair ignored, always high) each fail the new test and nothing else. `TF_GLM_OVN_SIDE_PRIO=1` read 1.8%, 2.3% and 2.0% under
the control pair's cold first token at 8k, 32k and 120k on one boot (queue73); the A B B A that decides it is queue75.

0038 is new here too (2026-11-20): a prompt chunk's pieced site ends in a tail (the last piece's exchange, glue and share on the side stream while the main
stream waits, 18.3 + 24.5 us a row of a cold pass in queue76's nsys capture) before the next block's row-by-row front starts. `TF_GLM_OVN_PIECE_FRONT=1` and
`TF_GLM_OVN_PIECE_MLA=1` glue an ffn site's pieces on the side stream (`cuda_forward_pair.exchangeGlue`, now public) and run the next KDA or DSA layer's front
range by range behind each range's share (`cuda_kda_block.projectRows`, `cuda_dsa_block.prepareRows`, then each block's `bodyRest`); `TF_GLM_OVN_PIECE_FFN=1`
splits `gluePieces`' closing waits off and runs a MoE router range by range (`cuda_moe.routeRows`, `bodyRest`). The schedule-picking code is
`cuda_forward_front.zig`; a last piece under 128 rows joins the one before it, and `TF_GLM_OVN_FRONT_ROWS=N` (default 0) joins pieces until a front range has at
least N rows (a front's matmuls read their weights once a range). Default off, the bits unchanged (the default path calls the same functions with
the whole range). The host test is `cuda_piece_front_test.zig` (listed in `cuda.zig`'s test block); the registry rows follow `TF_GLM_OVN_SIDE_PRIO`'s, so
`patches/pr1411`'s hunks still apply on top. The 38-patch series with the packages is the 45-patch stack, tree `fe2c0995a819fa3f2dafb7d1a5bcaf54bf02d6d7`;
a full run on the shared x86_64 gate host, `sg-20261120-042953`, passes against the pristine pin for that stack: every step rc 0 but `test-cuda-host`, which
fails only the base's own `cli_config_test.test.serve --config` name (6,917 of 6,951 tests passed, 33 skipped, against the base's 6,716 of 6,750), and lean
341 problems against the base's 341, 0 new. Nine mutants of `handsFront`, `frontRanges` (the short-last merge, the join bookkeeping, the minimum) and the four switch readers each fail one of the new tests and nothing else but the base's own name.
Queue83 read the three schedule switches on a GPU (OVERNIGHT section 58: -3.6% cold, every reply equal); `TF_GLM_OVN_FRONT_ROWS` was read in queue84 and gains nothing (section 61: 512 and 768 level inside the controls' spread, 2048 3.2% to 3.8% slower on warm turns), so it stays 0.

0039 is new here too (2026-11-20): at a KDA mixer site of a prompt chunk the whole chain (`kda_prep`, `kda_step`, `kda_out`: 4.06 ms for 4,096 rows, 34 of the 45 sites) runs before the first
piece's o_proj, so the first partials exchange starts only after it, and the side stream's exchanges, glue and shares (4.10 ms of NCCL kernels) outlast the main stream's work: in queue85's timeline the
main stream idles 1.54 ms of the 5.05 ms after the chain. `TF_GLM_OVN_PIECE_KDA=1` runs the chain in the ranges the pieces cut (`cuda_kda_block.chainRange`, every row-indexed buffer moved down by
`fromRow`; `cuda_forward_chain.exchange` and `opening` say which range's chain precedes which piece; `exchangePieces` is split into `exchangePiece` per piece), each ahead of the first piece it covers. A range at row
`lo` reads its three conv rows from a window of the projected rows (the layer's `conv_shift` kernel into a scratch window), the recurrent state hops between the layer's other buffer and a scratch one
(`hop`), and the layer commits after the last range as the whole chain does; `cuda_state.make` gains that scratch (`twin_checked` 76 to 77). The schedule is today's for a chunk under 64 rows,
a profiled pass, `TF_GLM_L2PF`, shared segments and the chunked chain. The host tests are `cuda_piece_kda_test.zig` (the switch, `hop` for 1 to 16 ranges, `fromRow`, and the range bookkeeping for every chunk
size and piece count); the GPU check is `tf-cuda-test glm-kda-pieces` (byte equality of the chain by ranges against the whole chain, seven cases, two planted controls), which queue87 runs on the image before it
measures. The 39-patch series with the packages is the 46-patch stack, tree `7ccb3385fcfd587178a0def044174a14575641b8`; the full run `sg-20261120-081755` on the shared x86_64 gate host passes against the pristine pin: every step rc 0 but `test-cuda-host`, which fails only the base's own
`cli_config_test.test.serve --config` name (6,922 of 6,956 tests passed, 33 skipped, against the base's 6,716 of 6,750), `compile-cuda-tests` builds the GPU check, and lean is 341 problems against the base's 341, 0 new. Fourteen mutants of the patch, each with one added line changed and run through the fast loop's `test-cuda-host`, each fail a `cuda_piece_kda_test` test and no other name but the base's: three of `hop` (the first range not reading the layer's state, either parity flipped) fail the `hop` test; seven of `fromRow` (a buffer moved by another row size, or not moved) fail the `fromRow` test; the switch read under another name fails the switch test; three of `opening` (a range's first piece, the range a piece opens, the list not cleared) fail both `opening` tests. Eleven ran on the 46-patch stack (6,956 tests); m1, m5 and m10 ran with `patches/solo-cuts`' second patch in the stack too (47 patches, 6,959 tests), and m1's run counted 6,865 tests with its `hop` test failing as the others' do (that the test binary stopped at a later assertion is an inference: the output names failed tests only). On a GPU (queue87, OVERNIGHT section 67, image `v129ze`): `tf-cuda-test glm-kda-pieces` passes (2 PASS lines, rc 0), every reply equals the recipe's, and the cold first token reads 0.73%, 0.88% and 0.97% slower at 8k, 32k and 120k (turns 2 to 8 of a ~113k conversation level), so the switch stays off.
No GPU run has read it yet: queue87 does (OVERNIGHT sections 61 and 62).

Every switch still defaults off and is a row of the `.glm` scope of `zig/src/platform/environment.zig` (TF_GLM_OVN_*
through `cuda/ovn.zig`), with a line in `docs/environment.md`. Every kept patch keeps its own header (source, what
changed, receipts) and gains one line naming how it was re-seated; a patch whose hunks moved by hand says which
upstream change moved them.

Hashes: `SHA256SUMS`, one line a patch, checked by `series-check.sh` (and by `scripts/check-patch-packages.sh` once the
directory sits under a package root).
