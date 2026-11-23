# RECORD.md - patches/port-hc-dec

## Base: upstream main `fa13df5dd1fdd23ada775510a464c9aa03a39e09`, then the 32 patches of `patches/engine/`

Applies to the engine series alone. `apply.sh --check` on tree `59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450` gives
tree `192917176b03d3f92ed5d24421da15ae25c01ac1`, rc 0, nothing written.

Source: `archive/ai-engine`, branch `ovn-up`, commit `6c92d7ec2e56e0e16a0276de444566ea338d646c` (2026-10-30): "glm glue:
TF_GLM_OVN_HC_ROWS=16|32 and TF_GLM_OVN_HC_DEC, hc mixing with fewer weight reads" (11 files, 743 insertions). The kernel
header `glm_glue_hc_rows.cuh` is carried byte for byte.

The text was edited by hand rather than replayed, because the fork's post-image meets three things this series does not
have at that site:

- ROUTER16 is retired here, so the fork's insertion point (its field and its loader) is gone; the two optional-kernel
  groups are loaded by a new `hcLoad()` called from `Kernels.loadOvn`, before the `if (!ovn) return k` early return so
  the optionals are null rather than undefined when the knobs are off.
- Launches go through `cuda_pdl.launch`, which applies TF_GLM_PDL itself; the fork's `cuda.launch.launch` calls and
  explicit `.pdl = set.pdl_early` flags are dropped, and `hc_partial8_pdl` / `hc_partial48_pdl` keep their roles.
- The build step is attached to `test-glm-keep-seqs-host` (the anchor the fork used does not exist here).

Not carried: the fork's GPU reference checks (`glm_ref_hc_rows.zig`, `glm_ref_ovn.zig`) and `glm_hc_bench.zig`. The first
needs the forked `glm_ref_tests` registry this series does not have; the bench and the reference check are the two files a
reviewer should add if the arm is worth keeping. Carried: `cuda_hc_ovn_test.zig` (the host receipt: which mixing kernel a
call launches, its grid, shared bytes and arguments at 16 and 32 prompt rows, HC_DEC's 288-thread launch, and the
knobs-off paths), plus `test-glm-hc-host` and the `TF_GLM_OVN_HC_` filter. Its three routing tests - off, HC_ROWS at every
row count, HC_DEC under 64 rows with 64 on today's path - are the package's receipt for the routing, not a smoke check.

The third fork-era assumption this package hit, found by those three tests: the fork's mixing launches were plain
(`cuda.launch.launch`), while this series launches hc_pre's partial kernels through `cuda_pdl.launch`, which is dependent
under TF_GLM_PDL (default on). So `hcRow` keeps this series' plain launches for both today's and the new R-row kernel
(changing them would alter the default path), while hcPre's paths are all dependent and the receipt compares `l.ex`
against `pdl or cuda_pdl.on()` rather than against `pdl`. A port that flips either side is a default-path change or a
false receipt; this one does neither.

Rows added to `zig/src/platform/environment.zig`: `TF_GLM_OVN_HC_ROWS` (`.u64`, `.only = &.{ 0, 16, 32 }`) and
`TF_GLM_OVN_HC_DEC` (`.flag`). Both are `TF_GLM_OVN_`-prefixed, so the strict-env test's non-OVN count is unchanged, but
any enumeration of the speed-hunt knobs must list them.

Gate: not yet taken. `python scripts/spark-gates.py iter --name hc-t1 --pin fa13df5dd1fdd23ada775510a464c9aa03a39e09
--dir patches/engine,patches/port-hc-dec check fmt test ctest --max-load 14`. The full step set is needed: the host test
and the two environment rows are what a compile-only screen cannot see.

## The measurement that decides it

A fresh arm on the current series, because the fork's cells predate the re-seat. HC_DEC: `TF_GLM_OVN_HC_DEC=1` against
unset at 1, 2, 4, 6 and 8 streams, replies equal (the fork read +1.0% at P8 and +0.4% at P4, cold inside its A/A floor).
HC_ROWS: `=16` and `=32` on cold 8k / 32k / 120k prompt cells, replies equal, with GLUE_ROW on and off. A decode
regression at any level kills HC_DEC under the repo's rule regardless of the P8 cell.

Patches, in file-name order:

- `0001-glm-hc-dec.patch`

## Screen

`screened: check fmt test ctest rc 0` on tree `e1f52b62b7a2e14bf00f3da08df06ae37cb34669`, run `iter --name hc-t3`:
`fmt` rc 0, `test-cuda-host` 7,993 of 8,036 with 43 skipped and no failures, `compile-cuda-tests` 10 of 10, `ctest` rc 0,
`ITER-DONE rc=0`. The three routing tests (`TF_GLM_OVN_HC_ROWS and _HC_DEC off`, `TF_GLM_OVN_HC_ROWS`, `TF_GLM_OVN_HC_DEC`)
are the package's receipt for the routing, not a smoke check: they failed on the first two cuts and pass now that `hcRow` is
back on `cuda.launch.launch` and the assertions follow this series' dependent-launch convention.
