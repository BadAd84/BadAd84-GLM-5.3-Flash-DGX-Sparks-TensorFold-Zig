---
name: gate-a-zig-patch-series-on-a-spark
description: "Gate a patch series on upstream TensorFold on a Spark (compiling on the workstation is banned): ship pin + patches by ssh, build trees, run gates.sh, gate-names, lean there."
---

## When
Any time a TensorFold patch series, package or re-seat needs compile, test, fmt or lean results. Owner rule (2026-11-15): NOTHING compiles on the laptop or its WSL, with or without a lock or cap. Text work (git apply, merge-file, tree ids, sha256) stays local.

## Procedure
1. Run the shipping from the TOP-LEVEL shell with the system `python` (it has the ssh agent: `export SSH_AUTH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg`). A script run by `bash` goes to WSL, which has no agent or known_hosts ("Host key verification failed").
2. Host: spark5 (`adam@192.168.99.15`) has `~/tools/zig-aarch64-linux-0.17.0`, 20 cores, 123 GB; a full pass of three trees takes about 15 minutes, a `check-native-cuda-host` about 65 s. Use spark1 only outside a GPU window. No GPU lock is needed for CPU gates.
3. Ship: `git archive` of the pin tag from the read-only object store (`work/parity/tree`), a tarball of patch files and `scripts/{gates,gate-names,lean}.sh`; on the Spark build the tree with `git init`, `git add -f -A`, commit, then `git apply --whitespace=nowarn --index` per patch in file-name order.
4. Tree ids: use `git add -f -A` before `git write-tree`. `git add -A` skips tracked files that `.gitignore` matches (about 650 `.log` files in the archive), so its id never equals the lanes' id even though the content is the same.
5. Run `scripts/gates.sh TREE NAME` (picks the toolchain by `uname -m`; `GATE_JOBS=8`, `nice -n 10`), then `gate-names.sh BASE HEAD` and `lean.sh BASE HEAD NAME`. The pristine v1.2.9 base itself fails two tests on aarch64 (`cli_config_test` serve --config expand, `listener` Nagle); compare names, never counts.
6. A gate is green only when every step has rc 0 AND failing names match the base. `gate-names.sh` now exits 1 with BUILD FAILED on a compile error in the head log; before that a tree that did not compile reported "0 failing names".
7. Counts do not compare across warm and cold caches (cached run steps contribute nothing): use failing names, or a fresh `--cache-dir` per tree.

## Scripts (scratch in the repo's gitignored work/, promote when generic)
`work/spark_gates.py HOST` (builds base/head/stack, runs the whole pass detached, log `~/v129/run.log` on the Spark) and `work/spark_iter.py SERIES_DIR [check] [fmt] [test] [lean]` (rebuild one tree from a series dir and run quick steps; it needs `~/v129/base.tar` and `~/v129/trees/base`, which spark_gates.py prepares).

## Lanes
A lane brief must say the ban and give this loop; a lane that cannot gate reports "not run". A lane's own claim that a compile error was fixed is not evidence until the Spark compiles the exact tree id.
