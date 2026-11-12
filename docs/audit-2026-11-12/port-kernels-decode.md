> `PortKernelsDecode` is running a newer turn. The output below is from its PREVIOUS run (published 8m30s ago), not the current one. Live progress: `history://PortKernelsDecode`; its next result auto-delivers to its owner.LANE `kernels-decode`: six patches cut, gates run and compared, verify-tree diff 0.

# Per port

### 01 `work/ports/kernels-decode/01-fp8-tile-ahead.patch`
- Fork sha `450b9519c` "glm cuda: FP8 latent keys fetched a tile ahead, in 8-byte loads".
- Files: `zig/kernels/cuda/glm_glue_attn.cuh` (5 hunks, +53/-25).
- **Hand-ported.** `git apply --check` was not even attempted as a whole: our `chunks_wide` FP8 arm is slab-only (no `pt` handling at all) while the fork's base arm carries page addressing, so every one of the five hunks has different `-` lines. Ported by hand: `load_kv` becomes BF16-only with the fork's comment; the `fetch`/`store` pair, `PER`, `pre_c`, `pre_s` added after it; the entry's `fetch(0) store(0) fetch(1) commit()` branch; the `store(tile+1) / fetch(tile+2)` block after the loop's barrier; the tail `commit()` guarded by `!FP8`.
- **Left out:** the `pt`/`pstep` page arm inside `fetch` (FP8 on pages is refused by `cuda_start.zig` and `cuda_latent.zig`). Also dropped the fork's `const float* row_scales = scales + src` hoist, which only exists to carry that arm, keeping our `scales[src]`. The fork's two-line comment is one line, with the 256-thread half moved onto `PER`'s own line, for the lean gate.
- **Bit-identity, expression by expression** (in the header in full): the `uint2` load reads the same eight bytes little-endian so the four code pairs are the pin's `j = 0,2,4,6` and the load is 8-byte aligned (`src * LW`, LW 512); `!ok` still gives bits 0 and scale 1.0; the convert chain and `__fmul_rn` operands are unchanged; `__floats2bfloat162_rn` is `__float2bfloat16_rn` of each half, the same round to nearest even; one `uint4` covers exactly `dst[wide(key,u)+0..7]` in the same element order at a 16-byte-aligned address; `PER` is 8 and `idx = t + p*256` is the pin's strided set because all four wrappers are `__launch_bounds__(256)`; `store(tile+1)` writes the buffer whose last reader was `tile-1`, two `__syncthreads()` back.
- **Records:** none edited. The fork's commit touches one file and its `glm_kv_pending.zig` at `ovn-up` still reads 64 and 128/127/130, exactly as ours does, so the commit message's "98 to 126" and "128 to 163" are a different build's numbers and are not transcribable here. Named as a GPU obligation instead.
- `.cuh`, **not compiled locally**.

### 02 `02-exl3-chunk-rows.patch`
- Fork sha `0aec07b2f`. Files: `zig/src/families/glm/cuda_exl3.zig` (2 hunks, +12/-5).
- **Applied clean** (`git apply --check` rc=0), only the doc comment reflowed to one line for the lean gate.
- Completes no patch of ours: `cuda_exl3.zig` is a pin file that 0001 to 0042 do not touch.
- Every `chunk_rows` use checked: the `run()` loop, `picksBytes`, `scratchBytes`, `cap`, and the existing picks test's range.
- **Extra bytes a rank** (from `exl3_prompt.sizes` and `picksBytes`, dims 4096, a 2,048-row prompt buffer, GLM's prompt path being the fused one):

  | rank share | gate and up share a rotation | they do not |
  |---|---|---|
  | 640 | +153,124,864 B (146.0 MiB) | +278,953,984 B (266.0 MiB) |
  | 768 | +155,222,016 B (148.0 MiB) | +281,051,136 B (268.0 MiB) |

  32,768 B of each is the picks buffer. `weights.exl3_shx` defaults true, so the left column is ours; the fork's "~270 MiB" is the right column. A twin prompt buffer set adds nothing (`Buffers.make` zeroes every size not in `twin_at`, and the four EXL3 sizes are not there). Decode windows unchanged.
- **Added, not in the fork:** a test that the arena holds a whole chunk over TP=3's two shares, TP=2 and TP=1 and both rotation layouts. It fails on the pin's 1,024.

### 03 `03-exl3-dec-order.patch`
- Fork sha `46b46550f`. Files: `zig/kernels/cuda/exl3_grouped.cuh`, `zig/kernels/cuda/exl3_experts.cu`, `zig/src/cuda/exl3_experts.zig`, `zig/tests/cuda/contract_exl3_grouped.zig` (7 hunks, +27/-12).
- **Hand-ported**, `git apply --check` refused both files. Reasons: `GroupedArgs` and `grouped_body` live in `exl3_grouped.cuh` here (the pin moved them out of `exl3_experts.cu`), and our three entry points carry a fourth template argument `GROUPED_LOAD`.
- **Left out:** the fork's three `tf_exl3_grouped_p0/p1/p2` lines (TF_EXL3_PIPE), which this tree does not have, and with them the fork's `if (pipe()) e.grouped_pipe[...]` selector.
- **Changed from the fork:** `decOrder()` caches in a file-scope optional. The fork calls it twice a launch and the two grouped launches run once a layer a step, so on a 92-layer TP=3 round that is several hundred `getenv` scans a step **on the default path**, which would contaminate the A/B the knob exists for. Same idiom the fork uses for `TF_EXL3_SPLITK`.
- **Added, not in the fork:** the `ord` argument in `contract_exl3_grouped.zig`'s hand-built arg list, whose comment claims launch.zig add order. The fork left its copy one field short. Harmless either way (the struct stays 128 bytes: ten pointers plus eleven ints already pad to 128, twelve ints is still 128) but the comment would otherwise be false.
- **Unset is today's launch, verified at the source, not assumed:** `grep` shows `exl3_grouped.cuh` contains no `gridDim` or `blockIdx` read at all, so `grouped_body` sees only its `u`, `nblock`, `zz` parameters and the swap is a pure relabelling with the grid swapped to match.
- **Collision with `work/p41/0042-exl3-decode-items.patch`:** both rewrite the same two `launch_.launch` statements in `exl3_experts.zig`. That patch renames the grid x from `maxu` to `nx` and z from `mt` to `mtu`, and replaces the trailing `@as(i32,0)` / `@as(i32,-1)` adds with `std_a` / `skip_a`. Mine adds an `ord` add after those two and replaces grid x and y with `gx` / `gy`. Landing both needs one merged grid expression a launch (`if (ord == 1) w / 128 else nx`) and the `ord` add after `skip_a`. Nothing else overlaps: the item plan's other hunks are in scratch sizing and the epilogue.
- `.cuh` and `.cu` **not compiled locally**; `contract_exl3_grouped.zig` is in the GPU test binary, which `compile-cuda-tests` does compile (rc=0).

### 04 `04-onepass-pipe-scale.patch`
- Fork sha `dd426c1a1`. Files: `zig/kernels/cuda/glm_onepass_pipe.cuh`, `zig/src/families/glm/cuda_onepass_order_test.zig` (new), `zig/build/glm_family_host.zig` (4 hunks, +239/-4).
- **Hand-placed**, one line plus its comment. The defect premise was checked here rather than taken from the commit: `glm_onepass_common.cuh`'s `raw_load` has `if (id[i] >= 0 && lane == 0)` and leaves `s` at 1.0 in lanes 1 to 31.
- **The reset check is in**; the base check is not. `zig/tests/cuda/glm_onepass_exact_check.zig` does not exist in this tree, so there is no arm to add to it. `cuda_onepass_order_test.zig` is taken whole (it arrived in the fork with `d9c599a8b`, which 0017 did not bring; `dd426c1a1` adds its second test) and registered the way the fork registers it, so it runs in `test-cuda-host`: `test-glm-onepass-order-host` rc=0. Both of its tests are about kernels we ship (`tf_glm_onepass_exact`, the pipe's CHUNK switch).

### 05 `05-draft-edge-noise.patch`
- Fork sha `39304587f` (found with `git log -S'k.edge * dot'`), its `dflash_select.zig` hunk, plus the capture rename from `6f3127df8`. Files: `zig/src/families/glm/dflash_select.zig` (5 hunks, +54/-13).
- **The commit's hunk applied clean** (`git apply --check` rc=0). The rename is **not** cosmetic as the audit called it: the hunk adds `const k = &dr.knobs` at function scope and the `n == 0` arm captures a loop index named `k`, which Zig refuses for shadowing. After both, the file is byte-identical to the fork's at `ovn-up` apart from the added test.
- **Unset selects as today, from the arithmetic:** `Knobs{}` has `edge` 1.0, `noise` 0, `noisy` false; `1.0 * x` is exact for every finite x, subnormal and infinity on host f32 with no flush, so `c[m].v + k.edge * dot` has the pin's bits; `keyed` is `if (k.noise > 0) q.sampling else null`, so with noise 0 the whole Gumbel block and `inv_t` are unreachable and `key[m]` is `sc[m]`, making the pick comparison the pin's with the same ties; `z` still sums over an untouched `sc`.
- **Added, not in the fork:** a host test driving `select()` with a synthetic drafter where one candidate wins on the logit and the other on the codebook score. Unset picks the codebook winner (today's rule), `DRAFT_EDGE=0` picks the logit winner, which is what proves the knob reaches the selector. This is the only executable evidence available for the port.

### 06 `06-df-sumw-record.patch`
- Fork sha `09edd1ce0` "glm cuda: KEEPWIN reads no drafter with the knob off; df_sumw record" (the kernel itself came with `39304587f`, ported by 0004). Files: `zig/src/core/contract/glm_cuda_records.zig` (1 hunk, +1).
- **A plain record, not a pending one**, and the reasoning is in the header: `later_pending` exists to suppress a usage until a toolchain newer than 13.2 (that is what `glm_l2pf_pending.zig` and `glm_kv_pending.zig` are for), whereas `df_sumw` was measured by the fork with the same nvcc 13.0 as the rest of that file and every other `glm_dflash` kernel here is in that plain list. Placed between `df_sum2` and `df_top16_part`, which makes our record order match the fork's line for line.
- The five figures are the fork's measurement, quotable because the kernel body is byte-identical between the two trees (`awk`-extracted and diffed), and the launch shape is read off that body. Named for re-measurement if our fatbin build differs.

# Gates

| step | baseline `fix6` | `kernels-decode` |
|---|---|---|
| `zig build check-native-cuda-host` | rc=0 | **rc=0** |
| `zig build test-cuda-host` | rc=1, 26 failing names | **rc=1, 26 failing names** |
| `zig fmt --check zig/` | rc=0 | **rc=0** |
| `zig build compile-cuda-tests` | not in baseline | **rc=0** |
| `zig build test-glm-onepass-order-host` | step does not exist | **rc=0** |
| lean, files / problems | 5991 / 127 | **5992 / 127, 0 new** |

`scripts/gate-names.sh fix6 kernels-decode`: `only kernels-decode fails: none` / `only fix6 fails: none`, rc=0. The 26 are the baseline's file-permission, symlink and FIFO tests. The two lean file counts differ by exactly the one file this lane adds, so the two sides really were two trees.

Two gate findings were mine and are fixed, not waived. The first run failed `fmt` and the compile with `dflash_select.zig:81: binary operator '*' has whitespace on one side, but not the other`: my test used `[_]i32{-1} ** (M * CW)`, which this Zig refuses to parse, so the whole glm module failed to build. Rewritten with `@splat`, the form the ported fork file already uses. The second was the lean gate: three new multi-line comments (mine in `glm_glue_attn.cuh` and `exl3_experts.zig`, and the fork's own two-line comment in `cuda_exl3.zig`), all collapsed to one line, which is why patch 02 no longer carries the fork's comment text verbatim.

Verify tree: `arm-tree.sh 42` into a second tree, the six patches applied in order by `git apply`, `diff -rq --exclude=.git` against the lane tree gives **0 differing paths**. Tree deleted.

# Doubts, stated plainly

1. **Port 01 is the one I would hold back if only one could go.** It is a rewrite of the default decode and prompt attention path for our KV format, it cannot be compiled here, and the bit-identity argument is mine rather than a measurement. It is strongly supported: `glm_glue_attn_ovn.cuh` in this tree already carries this exact `fetch`/`store` pair (0021 brought it), so the shape is known to compile under our nvcc and to be the fork's own. But nothing local proves the byte equality, and the register growth the fork reports (to 163 on `chunks_32_fp8`) is close enough to spilling that a different compiler could behave differently.
2. **Port 01 leaves the two FP8 fetch lambdas asymmetric.** After this patch `chunks_wide`'s `fetch` is slab-only while `glm_attn_ovn::chunks`'s is slab-or-pages. Both arms are dead today (FP8 on pages is refused at two places), but a reader diffing the pair will find the difference, and whoever lands FP8 on pages must remember `chunks_wide`.
3. **Port 02's memory number is computed from the project's formulas, not measured on a device.** The new test pins the identity between `scratchBytes` and `prompt.bytes`, not the magnitude. The direction of the risk is allocation failure at the served context, which is why that is first on its GPU list, ahead of the digest.
4. **Port 02's shx column is a judgement about the checkpoint.** `exl3_shx` defaults true and is cleared per layer from the loaded scales, so whether the serve pays 146 or 266 MiB is a runtime fact I cannot read here. Both are in the header.
5. **Port 03 touches lines the pending item-plan patch also touches** (above). Whichever lands second needs a hand merge of two grid expressions; neither patch is wrong on its own.
6. **Port 03's cached `decOrder` is a deliberate deviation from the fork.** If the parent would rather have the fork's lines exactly, the change is three lines and I would still argue against it.
7. **Port 04 ships a file from a commit nobody asked for.** `cuda_onepass_order_test.zig` arrived in the fork with `d9c599a8b`, and `dd426c1a1` only adds its second test. I took the whole file because the reset check has no other home and because its first test covers `tf_glm_onepass_exact`, which we do ship. If the parent wants strictly this commit, the file and its build registration come out and the kernel line stands alone.
8. **Port 04's base check is missing and that matters.** Without `pipe-off == tf_glm_sparse_onepass`, a future pipe mismatch cannot be told apart from a copy bug in the pipeline base, which is precisely the separation the fork added. The pieces exist here (`PipeKernels` loads `off`), so it is writable by someone with a device.
9. **Port 05's new test uses an `undefined` `df.Drafter` with seven fields filled.** It is correct for `select()` as written today; a future `select()` that reads an eighth field would read `0xAA` fill rather than fail cleanly.
10. **Port 06 quotes the fork's register figures.** Source identity makes them defensible, not measured here.
11. Ports 01, 03 and 04 contain `.cu`/`.cuh` edits that nothing local compiles. Each was read twice after editing, and each file's brace balance and column limits were checked mechanically.

# What each patch needs from a GPU run

- **01**: byte equality of `tf_glm_chunks_16_fp8` and `_32_fp8` against the pre-patch build, dense and sparse, at counts straddling tile and chunk edges including zero and a partly dead tile; then register and spill receipts on nvcc 13.3 sm_121a to replace the stale 64 and 128/127/130 in `glm_kv_pending.zig` and `measurements/pending_133.zig`; then the prompt MLA stage time (the fork claims about 220 ms of a 2,048-row chunk).
- **02**: boot at the served context first, to prove the pool absorbs about 150 MiB a rank, then a prompt reply digest equal to the pre-patch build.
- **03**: a reply digest with the knob unset equal to the pre-patch build (nothing here is compiled, so the relabelling argument needs confirming), then `TF_EXL3_DEC_ORDER=1` with the same digest and the routed stage against its 13.94 ms baseline. Both grouped launches take the knob, so measuring only gate and up misses half.
- **04**: the base arm the patch could not add (`pipe-off` against `tf_glm_sparse_onepass`, byte for byte), then `pipe-exact` against the chunk programs plus merge, remembering the fork's warning that a residual of a few words a row is the one-pass warp layout's P-sum tree and not this fix, while a magnitude difference is; then an unset-knob digest.
- **05**: an unset-knob drafted digest at several stream counts, then, if the knobs are to be used, `DRAFT_EDGE` and `DRAFT_NOISE` measured on draft acceptance a round rather than tokens a second, with sampled requests only (a greedy request carries no `Req.sampling`, so `DRAFT_NOISE` cannot reach it).
- **06**: nothing for correctness. A fatbin build that compiles `glm_dflash` for the recorded SMs and checks `df_sumw` against these five figures, which is the receipt the line exists to demand.