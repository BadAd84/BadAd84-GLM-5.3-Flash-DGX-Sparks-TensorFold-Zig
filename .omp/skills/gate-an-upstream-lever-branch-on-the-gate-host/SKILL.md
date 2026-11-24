---
name: gate-an-upstream-lever-branch-on-the-gate-host
description: "Gate and mutant-test a branch cut for an upstream TensorFold PR on the shared gate host via spark-gates.py iter (zig:STEP, saturated host, mutants that must compile); also dry-run a GPU queue's checks before its first window."
---

# Gate an upstream lever branch (GLM Zig repo) without compiling locally

Nothing compiles on the laptop or in WSL. Branches `up/LEVER` live in `work/up/wt-LEVER` (clone `work/up/TensorFold`); the gate host is the orca box through `python scripts/spark-gates.py` from the TOP-LEVEL Windows shell with `SPARK_GATES_HOST=adam@orca.ots-int.net` and `SPARK_GATES_SSH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg`.

## Full gate
`git -C work/up/wt-LEVER format-patch -o work/up/out/LEVER origin/main`, then
`iter --name LEVER --max-load 40 --pin-repo work/up/TensorFold --pin <cut sha> --dir work/up/out/LEVER check fmt ctest lean pdl contract test`.
Read `~/spark-gates/iter-LEVER/*.log` on the host. `test` ends `Build Summary: N/N steps succeeded; X/Y tests passed`; `failed command: .../test --listen=-` lines are the contract and planted-control fixtures' own non-zero runs, a real failure is `error: '<name>' failed`. The `test` step alone takes 30 to 50 minutes on the loaded host. The gate's `tree id` must equal `git rev-parse up/LEVER^{tree}`; pack the images' source with `git archive` of that branch so the bench measures the gated bytes.

## Mutants (one line each, each killed by a named test)
- `iter ... --dir <branch patches> --dir work/up/mutants/mN zig:test-glm-<lever>-host` runs ONE build step (`zig:STEP`, names are lower case, digits, hyphens). Use your own slot `--name` (the gating slot is locked while its `test` runs). Run the unmutated branch with the same step first: that control must pass.
- The host is shared with another session's docker Rust mutation runs, so load 40 to 46 is normal and the preflight refuses on `--max-load` and on memory under `--mem-max` (default 14 GiB). For single-step runs pass `--max-load 90 --mem-max 7` and retry a refused preflight (rc 4) instead of looping through the list. Do not stack more `test-cuda-host` builds: three of them at `-j6` saturate it.
- A mutant must COMPILE. Zig 0.17 rejects an unused parameter or local (`error: unused function parameter`): a build failure with no named test is not a kill. Keep `_ = e; _ = slot;` in the mutated body. A test name with an apostrophe breaks a naive `'([^']+)'` parse.
- Tests that exist only inside `test-cuda-host` (settings registry, `GLM strict env`) get a HARNESS patch dir applied to control and mutant, not to the branch, that adds `b.step("test-...-mut", ...)` with `.filters = &.{"GLM strict env:"}` after the lever's own step line (example: `work/up/mutants/harness/0001-strict-env-step.patch`).
- A survivor: first ask whether the mutated line is dead; a wiring line (environment to lanes in `finishRank`) is live but host-unreachable, so make it reachable (inject `get`) or add a rank-0 startup log line the receipts can grep, and say which.

## Housekeeping
Remove your own finished `~/spark-gates/iter-*` slots and `sg-*/{trees,home}` (check `ps` first); they cost 10 to 20 GiB.

## Before the first GPU window of a queue
Dry-run EVERY check the queue lists against its usage text (`zig/tests/cuda/main_usage.zig`) and fixture on the synthetic `glm-synth` checkpoint. A check list written from memory failed 4 of 8 on its first run and stopped the queue with nothing measured: `glm-pair-check` verifies paired prompt steps that `TF_GLM_CHUNK_SOLO=4096` replaces, so it runs with the runtime environment only; `glm-shared-check`, `glm-lanes-concurrent` and `glm-lanes-cover` parse `{capacity, kinds}` from `dc.json`, which only `glm-synth` writes, so they run on that checkpoint on one GPU (`<ckpt> <ckpt>/dc.json 0 1 <idfile>`), never on the real checkpoint with a capacity-only `dc.json` (`MissingField`).
