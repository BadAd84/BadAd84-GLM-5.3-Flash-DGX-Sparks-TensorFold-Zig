---
name: verify-every-rank-recipe-before-blaming-a-pin
description: "Multi-box TP serve shows a decode regression after a pin or engine change: prove every rank runs the same recipe files, then compare per-rank kernel launch lists, before hunting knobs or source."
---

Use when a TP=N serve (GLM Zig on spark1-3, DSV4.1 pairs, any head plus workers) measures slower after a pin move, rebase or image change, and knob arms come back flat.

1. Hash the recipe files on EVERY box before reading a single number: serve.sh, config.sh, launchers, clients. Print the hashes in the queue log. A driver that runs rank 0 from the head's copy but starts workers from the workers' own copies (zig-tp3.sh did) lets worker files drift for days. Fix by pushing the files to each worker at every boot, plus a gate that exits 1 on drift (scripts/check-spark-sync.py).
2. Flat knob arms in a recipe you have not verified prove nothing: an arm of a switch the base recipe never set is a comparison of two off states. Check the effective env of each rank in its boot log first.
3. Measure the image A B B A in one window with the same recipe on both sides; the control pair must bracket the test pair within about 1%.
4. Name the cause from kernel launch lists, not totals: nsys per rank (scripts/nsys-rank0.sh for the head, nsys-rank.sh RANK for a worker, WRAP1/XRUN1 in zig-tp3.sh), diff by kernel name and launch count. Per MoE call the compact path launches tf_exl3_group, experts_rot_in, two tf_exl3_grouped_1, down_combine; the item plan launches plan_kernel, prompt_rotate, two tf_exl3_ovn_nc1. A rank whose kernel set differs from rank 0's is on another recipe.
5. TF_GLM_PROF per rank (bench-client.sh keeps r0, r1, r2 logs) separates a slower rank from slower collectives: kernels that spin on peers inflate when a peer is late, so read each rank's stage times for the same call.
6. Re-take every row measured while a rank was stale (cold prompt, disk tier, arms) and mark the old sections superseded in their headings, not only in an erratum.
