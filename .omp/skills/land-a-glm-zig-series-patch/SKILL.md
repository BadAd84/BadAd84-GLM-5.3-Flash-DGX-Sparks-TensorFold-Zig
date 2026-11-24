---
name: land-a-glm-zig-series-patch
description: "Use to add a default-off patch or package to the GLM Zig TensorFold repo: cut from pre/tree copies, tree ids, gate-host iter plus mutants, image build and dist, queue deploy, records. Not for upstream PRs."
---

# Land a default-off patch in the GLM Zig repo (patches/engine or a package on top)

Measured on 2026-11-19 across solo-cuts (a package), engine 0036 and 0037. Times: a gate-host `iter` 3 to 8 minutes after the first one, a full `gates` run about 18 minutes, an image build about 8 minutes on spark1, distribution to spark2 and spark3 about 10 minutes.

## 0. Where it goes
- A numbered default-off knob or kernel with its own switch: `patches/engine/00NN-...patch` (every downstream RECORD tree id then changes: update the notes in pr1411, learn-starts and every later package).
- A behaviour change that edits files the packages already touch, or may be dropped after its GPU check: its own package dir (`patches/<name>/` with `RECORD.md`, `SHA256SUMS`, a copy of `patches/learn-starts/apply.sh`), applied last. No other record changes.

## 1. Work on small copies, never the whole tree
- Make `work/<Name>/pre/` (files as they are at the series state) and `work/<Name>/tree/` (the edited copies) inside the repo's gitignored `work/`; the edit tool cannot reach WSL paths, the Windows side can.
- Pre-images from a series tree: copy the newest WSL stack tree, `git apply -R` the packages last-first (working tree only), check its tree id equals the one `patches/engine/RECORD.md` names.
- Tree ids: `GIT_INDEX_FILE=$(mktemp)` (removed first), `git read-tree <pin>`, `git apply --cached` each patch in order, `git write-tree`. For a working tree stage only the paths of `git ls-files -m` and `-o --exclude-standard` with `git update-index`. NEVER `git add -A` (a hook interrupts it).

## 2. Edit rules that bit
- Comments single line, <= 120 columns, no two comment lines in a row (lean problem); no em dashes anywhere.
- A new test file only runs if `zig/src/families/glm/cuda.zig`'s test block lists it. A host test of a switch: `cuda.ovn.fake("NAME", "1")` with `defer cuda.ovn.fake("NAME", null)`; `Engine` can be built as `var e: Engine = undefined` with only the fields the function reads set.
- Each `TF_GLM_OVN_*` switch needs a registry row in `zig/src/platform/environment.zig` and a line in `docs/environment.md`; an unregistered `TF_GLM_*` name is refused at boot. Put new rows after the previous patch's row, away from pr1411's context lines.
- Zig refuses unused parameters and unreachable code: mutants must still compile.

## 3. Cut and verify
- `bash scripts/mkpatch.sh OUT HEADER PRE TREE PATH...` (header ends with `---` and a blank line; new files work). Then `git apply --check` on the pre copies, `cmp` the applied result against `tree/`, and compute the ids over engine plus all packages in order and again with the patch applied last (both ids must be equal).

## 4. Gates (never compile on the laptop)
- `python scripts/spark-gates.py iter --pin <pin> --dir a,b,c --name <slot> check fmt test lean` through a wrapper that waits for gate-host load < 8. Expected: only the pin's own `cli_config_test` case fails, lean 0 new. Then a full `gates --tree base --tree stack=... --expect stack=<id>` for the final tree.
- Mutants: for each decision the patch makes, change one line of the patch text in a copy (same line count), and run `iter --dir <mutantdir>,<packages> test`. For an engine patch the mutant dir holds all the engine patches with one replaced. Each mutant must fail exactly its own tests; a survivor means the wiring has no test (say so in the record).

## 5. Image and queue
- Tar the patched tree without `.git`, copy it out of WSL to a Windows path, scp at the top-level shell (WSL has no known_hosts), then on spark1 `build-image.sh TAG src.tar` and `dist-image.sh TAG`; verify the same image id on all three ranks; delete superseded tags and WSL trees.
- A queue is replaced by staging into `stage/` then `mv`, but a running or waiting bash keeps the old inode: kill a waiting queue and start it again; print the sha of the local and remote copy.
- Production stays down for the campaign: no window, no veto, no restore at a queue's end.

## 6. Records and commit
- RECORD paragraph or table row with the tree ids and gate results re-derived from the logs, `SHA256SUMS`, `scripts/check-patch-packages.sh`, private-string and em-dash scan of the staged lines, signed commit with `-F` message file, explicit paths.
- Pitfalls: `set -euo pipefail` plus `grep -l ... | wc -l` aborts when nothing matches; the top-level bash is Windows-native and `bash script` runs in WSL; the edit tool refuses ranges it never displayed (re-read, or retry with the same tag).
