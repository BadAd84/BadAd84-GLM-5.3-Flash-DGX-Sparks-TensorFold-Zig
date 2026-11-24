---
name: audit-every-rank-recipe-before-a-multi-box-window
description: "Before or after any multi-box GPU window (TP=3 on spark1-3): prove every rank runs the repo's recipe; use when a build looks slower and knob arms stay flat."
---

## Why
A pin move looked 4 to 11% slower. Cause: stale copies of the launcher (serve.sh), first on the head and then on the workers. zig-tp3.sh runs rank 0 from the head's copy but starts ranks 1 and 2 from each worker's OWN ~/work/glm53-zig/serve.sh. Repairing one box left the other two stale. Knob arms were flat because every arm shared the stale recipe.

## Before a window
1. Hash the launcher on EVERY box and print the three hashes in the queue log: `sha256sum serve.sh` on spark1, spark2, spark3 (LF-normalised). They must be equal to the repo's.
2. Head: `python scripts/check-spark-sync.py adam@<head>` (top-level shell; exits 1 on drift). Workers: zig-tp3.sh copies serve.sh and config.sh at every boot.
3. Print the effective DEFS the rank booted with (boot log) when a knob matters.

## When a build is slower and knob arms are flat
1. Do not trust arms on an unverified recipe. Take an nsys kernel table per rank (scripts/nsys-rank0.sh for rank 0, scripts/nsys-rank.sh RANK for a worker) on both builds.
2. Compare kernel NAMES and launch counts per MoE call, not totals. A different name for the same role (tf_exl3_grouped_1 vs tf_exl3_ovn_nc1) is a different code path.
3. Compare stage times per rank with TF_GLM_PROF=1 (bench-client.sh keeps r0-, r1-, r2- logs). A rank whose compute differs while rank 0's does not points at that rank's launcher or env.
4. Check wall equals GPU time per rank: if yes, the cost is in kernels, not host stalls.
5. Only after all ranks match, A B B A the images with each test cell read against adjacent controls.

## Traps
- `pkill -f PATTERN` over ssh matches its own command line and kills the session; use `pgrep -f "[p]attern"`.
- bash here is WSL with no ssh agent; run ssh helpers from the top-level shell with SSH_AUTH_SOCK set.
- Scan a commit's added lines for private strings as a gate (`[ "$n" = 0 ] && git commit`), not by eye afterwards.
