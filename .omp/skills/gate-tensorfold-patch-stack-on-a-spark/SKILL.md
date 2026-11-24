---
name: gate-tensorfold-patch-stack-on-a-spark
description: "Gate a TensorFold patch series or package on a Spark (aarch64) when compiling on the workstation is banned; check, fmt, test-cuda-host, lean, gate-names, tree ids."
---

Use for GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig (and sibling serve repos) whenever a patch set must be compiled or tested. The owner banned all compiling on the laptop/WSL (2026-11-15); text work (git apply, tree ids, sha256) stays local.

Procedure (spark5 = adam@192.168.99.15, zig at ~/tools/zig-aarch64-linux-0.17.0, 20 cores; spark1-3 only outside GPU windows):
1. Locally: `git -C work/parity/tree archive --format=tar <tag>` (read only) and a tar of the patch dirs. Never write into work/parity/tree.
2. scp both plus a runner script file to the Spark, run it detached (setsid nohup) writing a log with a DONE marker. Run ssh/scp from the TOP-LEVEL shell (python or bash tool), not from a script run through WSL (no agent, no known_hosts there). Every ssh takes `< /dev/null`.
3. On the Spark build each tree: extract the archive, `git init; git add -f -A; commit`, then `git apply --whitespace=nowarn --index` each patch in file-name order, then `git add -f -A; git write-tree`. USE `git add -f`: `git add -A` skips tracked files that .gitignore matches (649 .log files in the pin) and the tree id will not equal the recorded one even though the content is the same.
4. Run `scripts/gates.sh TREE NAME` (picks ~/tools/zig-$(uname -m)-linux-<.zig-version>; GATE_JOBS=8; nice 10), then `scripts/gate-names.sh BASE HEAD` and `scripts/lean.sh BASE_TREE HEAD_TREE NAME`. A pristine pin has its own failures on aarch64 (v1.2.9: cli_config_test 'serve --config: expand reads the file...' and listener 'accepted IPv4 and IPv6 TCP streams disable Nagle...'); compare names against the base run, never counts (cached run steps make counts incomparable across trees).
5. Green means: every step rc 0 except test-cuda-host whose failing names are a subset of the base's, gate-names rc 0, lean 0 new, tree ids equal the recorded ones. A tree that fails to COMPILE has no failing test names: gate-names.sh now prints BUILD FAILED and exits 1; never read '0 failing names' without rc 0 on every step.
6. Fast loop for compile errors: rebuild the tree and run only `zig build check-native-cuda-host -j8` (about 65 s) and `zig fmt --check zig/`; fix each defect inside the patch that owns it (re-cut that patch), never an integration patch; check every prefix of a series.
Timing: base gates 8 minutes, three trees plus names and lean about 15 minutes. A multi-lane run on one machine needs one owner per scratch worktree (two runs sharing a worktree path fail).
