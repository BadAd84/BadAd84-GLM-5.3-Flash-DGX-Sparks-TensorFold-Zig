# RECORD.md - patches/port-latent-tile

## Base: upstream main `fa13df5dd1fdd23ada775510a464c9aa03a39e09`, then the 32 patches of `patches/engine/`

Applies to the engine series alone (tree `59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450`), not to the six packages after it.

Source: `archive/ai-engine` (and the same ref in `archive/tensorfold-gb10`), branch `ovn-latile`
(`refs/heads/ovn-latile`; the laptop's `refs/laptop/remotes/fork-ssh/lead/latent-tile` = `1a44a1620131fcce5bfd55f4cdf2dc8e8c849753`),
commit `b2d1754ab7889e0207671440d46fab1a3bc53a5b` (the cherry-pick of `e5fd9cdc5603334809aa943914b7bd24377f1e9a`, 2026-11-01, whose
parent is `9a0d350eda8eec832a591444ebeaa7208dafaf2f`): "glm latent: TF_GLM_OVN_LATENT_TILE register-tiled absorb/expand (byte identical)".

The text was edited, because the review's open arm is a variant the fork never built and the series moved on:

- The kernel header instantiates **G=2** as well as the fork's G=4 (`tf_glm_absorb_tile_g2` / `tf_glm_expand_tile_g2`,
  `__launch_bounds__(256)`, two blocks an SM), with reversed-butterfly controls for both forms.
- The routing is written over this series' `absorbFn` / `expandFn` (`TF_GLM_OVN_LATENT_ROWS` x2/x4), which the fork's
  branch did not have; `LATENT_TILE` is read through the same `Mla` struct and registered row as LATENT_ROWS.
- The fork's `LATENT_MMA` precedence line and its `Mla.read` fields (`skip`, `seg`) are not carried: LATENT_MMA is not
  in this series. The GPU check is registered through this series' `glm_ovn_checks.zig` registry, not `main.zig`'s own
  table, and the fork's `.gitignore` hunk is dropped (this repo already ignores `work/`).

`apply.sh --check` against the engine series: `before: 59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450`, `checked 1 patch(es);
tree id: 81dd3fa6b4c30684622471e5685815a863283cc3`, rc 0, nothing written in the tree.

Gate: `python scripts/spark-gates.py iter --name port-latent-tile --pin fa13df5dd1fdd23ada775510a464c9aa03a39e09
--dir patches/engine,patches/port-latent-tile check fmt test ctest --max-load 14` was started on the gate host; its
verdict had not returned when this record was written (`check fmt test ctest`: build, host tests including the new
`TF_GLM_OVN_LATENT_TILE` tests, and the CUDA-test binary compile; it does not run the GPU check). Run the same command
to take the verdict.

## The measurement that decides it

`glm-latent-tile-bench` on spark1 (one GPU): base / vec / G=4 / G=2 ms per absorb and expand launch at 4,096 rows x 22
and 21 heads. The expected cell: **G=2 (256 threads, two blocks an SM) under G=4 and under base on absorb**, since the
fork's G=4 measured 1.7x slower than ABSORB_VEC at 94-98 registers and one block an SM, and G=2 is the only form with
occupancy 2. A serve-level tie-breaker is the cold prompt cell: `TF_GLM_OVN_LATENT_TILE=2` against `=4` against unset
at 8k / 32k / 120k, replies equal (the kernel is byte-identical by construction, and `glm-latent-tile-check` proves it
at both G).

Patches, in file-name order:

- `0001-glm-latent-tile.patch`
