# TF_GLM_OVN_MLA_FUSEMERGE=1 fails to boot: root cause, fix, launch-contract audit (2026-11-12)

Lane `MlaBootFix`. Series `patches/engine/0001..0033` on v1.2.7 (`93a2e93ecebff8aa52b88e58c5dd222516e69c5f`),
tree `93a99447e7030697ca29b93cc1410871bb34c98a` (rebuilt here from the patch files by `work/mlafix/mf.py build`,
every prefix tree equal to `work/reseat/series.tsv`). No GPU work was done; the kernel facts below come from this
workstation's nvcc 13.3 with the build's own flags (`work/mlafix/kcheck.py`, sm_121, `-Xptxas=-v` and
`cuobjdump -elf`), reports in `work/mlafix/k/final/`.

## 1. Root cause

The failing launch, from the boot log: `cuLaunchKernel: CUDA_ERROR_INVALID_VALUE (1) invalid argument; kernel
tf_glm_chunks_32_fp8_skip, grid 16x1x1, block 256x1x1, shared 101120 B`.

**It is not shared memory.** It is the argument list. The two FP8 bounded entries 0025 adds declare the fork's
FP8-on-pages parameter list, two parameters longer than the list the host passes:

| | parameters | bytes | where |
|---|---|---|---|
| `tf_glm_chunks_16_fp8_skip`, `tf_glm_chunks_32_fp8_skip` (0025) | 16, ending `const int* pt, int64_t pstep` | 120 | `glm_glue_attn_ovn.cuh:304-317`; cuobjdump EIATTR_KPARAM_INFO |
| `tf_glm_chunks_16_fp8`, `tf_glm_chunks_32_fp8` (upstream) | 14 | 104 | `glm_glue_attn.cuh:24-37` |
| what `latent.chunks()` passes for an FP8 cache | 14 (`pt`, `pstep` only when `scales == 0`) | 104 | `cuda_latent.zig:118-126` |

`latent.chunks()` is upstream's function; 0025 only changes which function it picks (`cuda_latent.zig:111-117`),
so with `set.mla.skip` on an FP8 latent cache it launches a 16-parameter kernel with 14 arguments.
`cuda.Args.pointers()` writes `ptrs[0 .. count]` only (`zig/src/cuda/launch.zig:57-61`) and `ptrs` is
`undefined` (`launch.zig:28`), so the driver reads `kernelParams[14]` and `[15]` from whatever the stack held. In
an `-Doptimize=fast` image (`scripts/build-image.sh:20,40`) nothing initialises them. [INFERENCE] Null slots
(untouched stack) are refused by the driver as `CUDA_ERROR_INVALID_VALUE`, which is the boot failure; a non-null
stale address would instead hand the kernel a junk `pt` and send its FP8 fetch down the fork's page branch
(`if (pt && ok)` in `glm_attn_ovn::chunks`), so the launch could also succeed and read the wrong memory.

The rest of the error line fits this shape: 16 rows ([INFERENCE] a drafter window, from the boot stage); `headBlockOf(16, 22)` is 32
(`cuda_latent.zig:21-24`, TP=3's 17-24 heads widen from 5 rows), `cdiv(22, 32)` = 1 head block, one chunk; FUSEMERGE=1
fuses from 64 rows (`cuda_glue.zig:18-21`, `prompt_rows`), so 16 rows take the bounded (skip) form; the cache is FP8.

**Why the arguments and nothing else.** With the switch off the same call takes `tf_glm_chunks_32_fp8`
(`cuda_latent.zig:115`) with the same grid, block and 101,120 B, its attribute raised the same way (`cuda_glue.zig:126`),
and that image boots. The failing entry differs from it in one launch-relevant property, its parameter list (16
against 14); its registers are fewer (160 against 163 at sm_121, `work/mlafix/k/final/report.txt`).

**When it entered.** Not the re-seat and not 0032. The pin's upstream FP8 entries already took 14 parameters
(pin `glm_glue_attn.cuh:230-241`) and the pin's `chunks()` already passed the 14-argument FP8 list (pin
`cuda_latent.zig:98-106`). The fork's FP8 fetch reads pages through `pt` and `pstep` (0032's header,
`0032-fp8-tile-ahead.patch:72-75`, which also records that "FP8 on pages is an unported feature here"), and the OVN
entries 0025 took from the fork carry those two parameters. They were never adapted to this tree's FP8 list, so every
MLA_FUSEMERGE launch of a bounded FP8 entry since 0025 was grafted has had two missing arguments. The BF16 entries match.

**Shared memory, checked for every entry (all OK).** Each chunk body lays out q (HB x 512), two 32-key tiles and p
(HB x 32) in bf16, then HB x 4 + 2 x HB floats: `wide_smem<HB>()` = 83,328 B at HB 16 and 101,120 B at HB 32
(`common/mla.cuh:41-44`, `glm_glue_attn_ovn.cuh:21-26` the same layout). Static shared is 0 B for all ten entries
(ptxas), so the need is the dynamic size alone. GB10's per-block opt-in is 99 KiB = 101,376 B (upstream's test
`zig/src/cuda/mla.zig:157-159` and 0023's `cuda_kda_chunk.zig:68-69` hold kernels to it), 256 B above the 32-head need.

| entry | params kernel / host | static | dynamic need | attribute (`cuda_glue.zig`) | launch (`cuda_latent.zig`) | verdict |
|---|---|---|---|---|---|---|
| `tf_glm_chunks_16` | 15 / 15 | 0 | 83,328 | 83,328 (:123) | 83,328 (:127) | OK |
| `tf_glm_chunks_32` | 15 / 15 | 0 | 101,120 | 101,120 (:124) | 101,120 (:127) | OK |
| `tf_glm_chunks_16_fp8` | 14 / 14 | 0 | 83,328 | 83,328 (:125) | 83,328 (:127) | OK |
| `tf_glm_chunks_32_fp8` | 14 / 14 | 0 | 101,120 | 101,120 (:126) | 101,120 (:127) | OK |
| `tf_glm_chunks_16_skip` | 15 / 15 | 0 | 83,328 | 83,328 (:128) | 83,328 (:127) | OK |
| `tf_glm_chunks_32_skip` | 15 / 15 | 0 | 101,120 | 101,120 (:129) | 101,120 (:127) | OK |
| `tf_glm_chunks_16_fp8_skip` | **16 / 14** | 0 | 83,328 | 83,328 (:130) | 83,328 (:127) | **BROKEN: arguments** |
| `tf_glm_chunks_32_fp8_skip` | **16 / 14** | 0 | 101,120 | 101,120 (:131) | 101,120 (:127) | **BROKEN: arguments** |
| `tf_glm_chunks_32_fused` | 14 / 14 | 0 | 101,120 | 101,120 (:132) | 101,120 (:145) | OK |
| `tf_glm_chunks_32_fp8_fused` | 15 / 15 | 0 | 101,120 | 101,120 (:133) | 101,120 (:145) | OK (see below) |

The attribute is raised whenever the skip handles exist: `Kernels.load` passes `Mla.wanted()` (`cuda_glue.zig:108-110`),
which is true for any nonzero MLA_FUSEMERGE (`zig/src/cuda/ovn.zig:31-33`), the same condition under which
`Mla.read()` sets `skip` (`cuda_glue.zig:18-21`).

`tf_glm_chunks_32_fp8_fused` matches its host list in count and layout, but `fused()` (`cuda_latent.zig:137-146`)
lacks the `Fp8OnPages` refusal `chunks()` has (`:110`), so the fused FP8 kernel is the one place left where a page
table could reach the fork's FP8 page branch. Unreachable today (the FP8 writer refuses pages first,
`cuda_latent.zig:77-80`), and closed by the fix below.

## 2. The fix (inside 0025, the lever that brought the entries)

`work/mlafix/0001..0033-*.patch` is the whole series; drop it over `patches/engine/` with `work/mlafix/SHA256SUMS`
and `work/mlafix/RECORD.md`. Built by `work/mlafix/series.py` from index files and trees only (no commit): 0001..0024
are the current files, 0025's tree is the current one with four files set over it, 0026..0033 are the current texts
re-applied with plain `git apply --cached` and re-emitted as `git diff-tree -p --full-index`. 31 of the 33 files come
out byte for byte as they are now; **0025** carries the fix, and **0027** differs only in its `cuda_latent.zig` index
line and two hunk offsets (+6 lines, the longer `fused()`). 0032 needs no change: it touches `common/mla.cuh` and
`pending_133.zig`, never the OVN file, and none of its claims moves. Final tree
`7d98e90edd1f2ae411e9f5df218229634d8b4cb4` (was `93a99447`).

What changes in 0025 (its header gains a paragraph saying so):

- `glm_glue_attn_ovn.cuh`: `tf_glm_chunks_16_fp8_skip` and `_32_fp8_skip` take `tf_glm_chunks_*_fp8`'s 14 parameters
  and pass `nullptr, 0` for the page table, exactly as the default FP8 entries pass them to `chunks_wide`.
- `tf_glm_chunks_32_fp8_fused` drops `pt` and `pstep` too (15 to 13 parameters), and `glm_attn_ovn::chunks`' FP8
  fetch loses the fork's page branch (`page_rows`, `row_scales`, the `if (pt && ok)` block): it is now `chunks_wide`'s
  slab-only fetch line for line (`common/mla.cuh:85-98`), the same choice 0032 made for the default body
  (`0032-fp8-tile-ahead.patch:72-80`). With the page table null these lines computed `scales[src]` before too, so the
  bits do not move; the BF16 page addressing (`keys_at`) is untouched.
- `cuda_latent.zig` `fused()`: refuses an FP8 cache on pages (`error.Fp8OnPages`) as `chunks()` does, and passes
  `t.pt`, `t.ps` to the BF16 form only, then `nch`. Count and layout now equal each fused entry's list.
- A compile-time gate in the same header: `glm_attn_ovn::same_params` and four `static_assert`s that each bounded
  entry's function type equals its default form's (`decltype(tf_glm_chunks_16_fp8_skip)` against
  `decltype(tf_glm_chunks_16_fp8)`, and so on). Shown failing first: with the asserts added and the old lists kept,
  nvcc 13.3 stops with `static assertion failed with "tf_glm_chunks_16_fp8_skip and tf_glm_chunks_16_fp8 take one
  argument list"` and the same for `_32_` (`work/mlafix/k/planted/report.txt`), and passes the two BF16 pairs; with
  the fix it builds (`work/mlafix/k/fixed/report.txt`). The image build is the gate for `.cuh` files, so this stops
  the next upstream move of an FP8 signature before a boot.
- A GPU check, `glm-mla-skip-check` (`zig/tests/cuda/glm_mla_skip_check.zig`, registered in `glm_ovn_checks.zig`
  beside 0025's other check, not `main.zig`): BF16 and FP8 caches, dense calls on 16- and 32-head blocks with dead key
  tiles in the last chunk, sparse calls at 3, 16 and 70 rows with counts at every chunk and tile edge (count 0
  included); each through `latent.attentionFormat` / `sparseAttentionFormat` with today's set, the bounded set
  (`skip`) and the fused set (`fuse_rows` 1), output bytes compared with today's; red control: a 1.5x scale must move
  the bytes. [INFERENCE, not run: no GPU work here] On the old 0025 its first FP8 bounded call would fail as the boot did.

nvcc 13.3 at sm_121 on the fixed header (`work/mlafix/k/fixed/report.txt`): the two bounded FP8 entries take 14
parameters, 104 B (`[8 x 12, 4, 4]`), the fused FP8 entry 13, 92 B, static shared 0 everywhere, registers 126
(16 FP8 bounded, was 128), 160 (32 FP8 bounded, unchanged), 250 (fused FP8, unchanged), no spills. At sm_80
(`work/mlafix/k/fixed80/report.txt`) the same lists, and `tf_glm_chunks_16_fp8_skip` no longer spills (146 registers,
0 B; the re-seat's `work/reseat/nvcc/report.txt` recorded 24 B on the old body).

A host test for shared bytes against attributes, as asked, would not have caught this defect: shared memory is right on
every path (section 1), and no host test can see a kernel's parameter list (the host gates build no fatbin). The two
checks above are the ones that fail on it.

## 3. The same class across the series' other knob kernels

Every kernel entry the series adds, read for its launch contract: dynamic shared need, the attribute, the launch's
value, static shared, and parameters against the host's arguments. Static shared and parameter lists are nvcc 13.3's
for sm_121 (`work/mlafix/k/final/report.txt`, `work/mlafix/k/final-glue/report.txt`); host lists counted from the
`Args.add` calls. GB10's per-block limit is 101,376 B; dynamic shared above 48 KiB needs the attribute.

| knob (patch) | entry | static | dynamic need | attribute | launch | params kernel / host | verdict |
|---|---|---|---|---|---|---|---|
| MM_WIDE (0024) | `glm_mm{4,6,8,16}_w2x4`, `_w4x4` | 0 | `Tile<B,128,WM,3,128>::SMEM` (`glm_mm.cu:76-88`): 62,208 / 68,352 / 74,496 / 99,072 | `tileShared(b, 128, 128, 3)` (`cuda_mm.zig:103`), the same | the same (`:242`) | 11 / 11, 68 B | OK |
| MM_CLUSTER (0024) | `glm_mm{B}_{16,32,64}c` | 0 | `Tile<B,bm,WM,3,64>::SMEM`, 12,672 to 49,536 | `sharedBytes(b, bm)` (`:114`) | the same (`:251`) | 11 / 11 | OK |
| MM_DECTILE (0024) | `glm_mm{B}_16n32` | 0 | `Tile<B,16,1,4,32>::SMEM`: 12,544 / 14,592 / 16,640 / 24,832 | `tileShared(b, 16, 32, 4)` (`:123`) | the same (`:255`) | 11 / 11 | OK |
| SWIGLU_REDUCE (0024) | `glm_mm_reduce_swiglu` | 0 | none | none needed | 0 (`:284`) | 6 / 6, 40 B | OK |
| ROUTER16 (0024) | `tf_glm_router16_s3`, `_s4` | 20,736 / 27,648 | none | none needed (static under 48 KiB) | 0 (`cuda_glue.zig:239`) | 8 / 8, 60 B | OK |
| GLUE_FUSE (0026) | `tf_glm_hc_glue` (+ `_f32w`, `_pdl`, `_f32w_pdl`) | 2,896 | none | none needed | 0 (`cuda_glue.zig:313`) | 18 / 18, 128 B | OK |
| GLUE_ROW (0026) | `tf_glm_hc_row`, `_f32w` | 8,368 | none | none needed | 0 (`:326`) | 16 / 16, 112 B | OK |
| PDL_EARLY (0026) | `hc_post_pdl`, `hc_partial8_pdl`, `hc_finish(_f32w)_pdl`, `rmsnorm_*_pdl` | 0 / 784 / 48 / 16-32 | none | none needed | 0 | each equals its base form's (8, 5, 13, 8) | OK |
| KDA_CHUNKED (0023) | `tf_glm_kda_chunk` | 0 | `sizeof(Smem)` 95,488 (`static_assert`, `glm_kda_chunk.cu`) | `smem_bytes` 95,488 (`cuda_kda_chunk.zig:27`) | `smem_bytes` (`:64`) | 20 / 20, 124 B | OK (255 registers, 12 B spill) |
| SPARSE_ONEPASS (0021) | `tf_glm_sparse_onepass` | 0 | `sizeof(Smem)` 100,416 (`static_assert`) | `smem` (`cuda_onepass.zig:28`) | `smem` (`:116`) | 10 / 10, 64 B | OK, 960 B under the limit |
| ONEPASS_PIPE (0022) | `tf_glm_onepass_pipe_{off,decode,scale,chunk,exact}` | 0 | `sizeof(SmemPipe)` 100,512 (`static_assert`) | `pipe_smem`, all five (`cuda_onepass.zig:77-81`) | `pipe_smem` (`:136`) | 10 / 10, 64 B | OK, 864 B under; `_chunk` and `_exact` spill 464 B |
| ONEPASS_EXACT (0022) | `tf_glm_onepass_exact` | - | - | - | `runExact` (`cuda_onepass.zig:120-127`) | no such entry in any `.cu` | INERT: `Set.onepass_exact` is never assigned, so the path is unreachable and the switch does nothing |
| DECODE_INDEX (0014) | `tf_glm_index_split` | 1,104 | none | none needed | 0 (`cuda_index.zig:186`) | 14 / 14, 96 B | OK |
| INDEX_SCHED (0014), INDEX_REGROUP (0015) | `tf_glm_index_scores_sched`, `_regroup` | 34,816 / 32,768 | none | none needed | 0 (`:164`) | 15 / 15, 108 B | OK |
| DRAFT_DOWN4 (0007) | `group_kernel<64,16,64,1,4,8,true,...>` | - | `LaneTile<64,16,64,1,4,8>::SMEM` 35,328 (F32 does not enter it, `qmm_frag.cuh:12-25`) | 35,328 (`cuda_q4.zig` `loadF32`) | 35,328 | the bf16 tile's signature (`qmm_group.cu:348`) | OK |
| ABSORB_VEC, KVB8 (0025) | `tf_glm_absorb_q_vec`, `expand_v_vec`, `absorb_q8`, `expand_v8` | 512 / 128 | none | none needed | 0 (`cuda_latent.zig:47-53`) | 6 / 6 (48 B), 7 / 7 (56 B) | OK |
| ROUTER_WARM (0019) | none of its own | | | | | | launches the router, MoE and mixer paths at boot; with MLA_FUSEMERGE and an FP8 cache its level-2 mixer warm (16 to 33 rows) would have met the same defect |

So the argument defect is confined to the two FP8 bounded entries, and no knob kernel is short of shared memory.
The one other finding is outside this class: TF_GLM_OVN_ONEPASS_EXACT is a registered switch with no kernel and no
assignment behind it (0022). It cannot fail a launch; it silently does nothing. Not changed here.

## 4. Checks (run here, outputs quoted)

- C: before the gates (`df -h /mnt/c`): 594 GB free.
- Plain `git apply --cached --check` of every emitted patch in order from v1.2.7, each applied and its tree compared
  with `work/mlafix/series.tsv` (`python work/mlafix/checks2.py apply`): 33 of 33 apply, failures 0, final tree
  `7d98e90edd1f2ae411e9f5df218229634d8b4cb4`. The 31 unchanged files rebuild the original prefix trees exactly
  (0001..0024 equal `work/reseat/series.tsv`'s trees).
- Line counts at every prefix, every file a patch touches (`checks2.py lines`): 147 files, 0 over 600 at any prefix;
  added comment lines past 120 columns 0; added comment lines directly after an added comment line 0. The files this
  fix touches end at 344 (`glm_glue_attn_ovn.cuh`), 181 (`cuda_latent.zig`), 35 (`glm_ovn_checks.zig`) and 109
  (`glm_mla_skip_check.zig`) lines.
- Forward-reference walk (`work/reseat/refs.py` through `checks2.py refs`): 5 flagged, the same 5 the re-seat recorded
  (`work/reseat/proof_refs_lean.txt`: `knob` in 0005 and 0007, `compares` in 0006, `onepass` in 0007 and 0011, local
  names); 0025 and 0027 clean.
- Lean, base against head (`bash scripts/lean.sh ~/mlafix/base ~/mlafix/tree mlafix`, the re-seat's final tree against
  this one, each scanned by its own `lean_check.py`): base 6,253 files, 386 problems; head 6,254 files (the new check),
  386 problems; 0 new.
- `bash scripts/gates.sh ~/mlafix/tree mlafix` (a copy on the WSL filesystem): check-native-cuda-host rc=0 (7/7 steps),
  test-cuda-host rc=0 (383/383 steps, 6,273 of 6,303 tests passed, 30 skipped), compile-cuda-tests rc=0 (10/10 steps:
  the GPU binary with `glm-mla-skip-check` compiles), test-glm-ring-host, test-glm-logprobs-host,
  test-glm-onepass-order-host and test-rows-host rc=0, `zig fmt --check zig/` rc=0. `GATES-DONE mlafix bad=0`.
- `bash scripts/gate-names.sh v127base mlafix`: v127base 0 failing names (6,177 of 6,207), mlafix 0 failing names;
  only mlafix fails: none.
- Package: `sha256sum -c work/mlafix/SHA256SUMS` 33 of 33 OK; no CR in any emitted file; only 0025 and 0027 differ
  from `patches/engine/` (`work/mlafix/sums.sh`).
- nvcc 13.3 (compile only): planted old lists with the new asserts fail on both FP8 pairs; the fixed header builds at
  sm_121 and sm_80 with the parameter lists in section 2.
- 0032's register receipt is current, not the pin's: `pending_133.zig` records `tf_glm_chunks_16_fp8` 148 (sm_80) and
  128 (sm_121), `tf_glm_chunks_32_fp8` 194 and 163; these compiles of this body read the same four numbers
  (`work/mlafix/k/fixed80/report.txt`, `work/mlafix/k/fixed/report.txt`).

## 5. The GPU proof (reserved to the main session)

The assignment keeps GPU work, the Spark boxes and `patches/engine/` out of this lane, so the proof on hardware is
the main session's: the files above dropped over `patches/engine/` (then `scripts/check-patch-packages.sh`), the image
built from tree `7d98e90e...` (which compiles the new `static_assert`s), `tf-cuda-test glm-mla-skip-check` on one GPU
(its pass line reads `... on 28 calls; the control differs`; a FAIL line names the arm, cache and shape, a launch error
is logged by `cuda.launch` with the kernel and its grid), and the TP=3 boot with `TF_GLM_OVN_MLA_FUSEMERGE=1
TF_GLM_KDA_PAD=1` and the drafter on, whose digests compare with the knob-off pad digests (BENCH.md records the knob
bit-exact at the pin) before any speed cell.

## Files

- `work/mlafix/0001..0033-*.patch`, `SHA256SUMS`, `RECORD.md`, `series.tsv` (trees before and after each patch).
- `work/mlafix/new25/` the four files set over 0025's tree; `work/mlafix/series.py` the build and emit;
  `checks2.py`, `mf.py`, `lib.py` (shim for the re-seat's `refs.py`), `kcheck.py` (nvcc resources and parameter
  lists), `fmt.sh`, `run-gates.sh`, `sums.sh`, `wslstate.sh`; `k/{final,final-glue,planted,fixed,fixed80}/report.txt`.
