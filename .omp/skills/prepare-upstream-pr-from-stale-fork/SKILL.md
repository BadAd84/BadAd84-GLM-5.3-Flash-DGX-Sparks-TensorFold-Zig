---
name: prepare-upstream-pr-from-stale-fork
description: "Preparing/rebasing an upstream (TensorFold) PR from a stale fork, verifying a Windows worktree is not CRLF-poisoned, and running upstream's own CUDA host gates on Linux"
---

# Prepare an upstream PR from a stale fork

Measured on TensorFold (`ashhart/TensorFold`) from the `ai-engine` fork, 2026-10-27.

## 1. Establish the real upstream tip - never trust a local mirror ref

A local `mirror/main` ref can be months stale. In this repo `mirror/main` = `0efbd447` and had
**no** CUDA GLM family, while the true tip `c6df96cf` had every file (`cuda_kda_block.zig`,
`cuda_tile.zig`, `cuda_state.zig`, `docs/recipes/glm-5.3-flash-cuda.md`). Concluding "upstream
lacks X" from the mirror was wrong and load-bearing.

```sh
# from a box with internet (a Spark works)
git ls-remote https://github.com/ashhart/TensorFold main
# locally
git remote add upstream https://github.com/ashhart/TensorFold
git fetch upstream main
git rev-list --count <our-base>..upstream/main     # 202 in this case
```

## 2. Read their CONTRIBUTING before cutting branches

TensorFold's rules that shape the work:

- Start from `main`; **one change per pull request**; open an ISSUE first for a new family,
  backend or arithmetic change (accumulation-order changes count as arithmetic).
- ATC coordination: `atc overlap --json` before opening a PR, claim a session, read
  `docs/atc/SKILL.md`.
- Gates: `zig build test test-golden -Dcpu=apple_m1`, `zig build test-cuda-host`,
  `zig build check-native-cuda-host` (compile the real native CUDA server, no GPU).
- Receipts: a real GB10 run under `docs/receipts/<name>/` with README + metrics + SHA256SUMS.
  "Compile success alone does not qualify a GPU."

## 3. Rebase as one branch per PR

```sh
git worktree add --detach <wt> upstream/main
git -C <wt> checkout -B pr-<topic> upstream/main
git -C <wt> cherry-pick <commits>
```

- Expect **subsumption**: when upstream reworded the same line, the merge takes the better
  message and a later narrow commit becomes empty - `git cherry-pick --skip` it, do not keep a
  no-op commit.
- When squashing a tested series, prove the result is the same tree:
  `git diff --stat <tested-tip> HEAD` must print nothing.
- Generate the standalone patch too (`git diff <pre-feature-commit> <tip>`) and record in the
  note which base it applies to and which files the target tree must already have.

## 4. A Windows-created worktree is probably CRLF-poisoned - check before believing any failure

Upstream guards patch kernel sources by exact string (`geometry_source.zig`: `once()`/`function()`
require an anchor to appear exactly once). A CRLF checkout makes them abort with
`error.HybridGeometrySourceChanged`, which looks exactly like your change broke the build.

```sh
git config core.autocrlf false
# count tracked files carrying CRLF (binaries will legitimately show up)
python3 - <<'PY'
import subprocess, pathlib
files=[f for f in subprocess.run(["git","ls-files"],capture_output=True,text=True).stdout.split("\n") if f]
bad=[f for f in files if b'\r\n' in open(pathlib.Path(f),'rb').read(200000)]
print(len(bad),"of",len(files))
PY
# re-materialise from the index (nothing must be uncommitted)
git status --porcelain | wc -l      # must be 0
git ls-files -z | xargs -0 rm -f
git checkout -- .
```

Measured: 2,272 of 8,694 files were CRLF; after re-materialising, 16 remained and all were
binaries. `check-native-cuda-host` then exited 0 where it had aborted.

## 5. Run the gates on Linux, not on the Windows checkout

- `zig build` from Windows and then from WSL in the same tree collides: WSL gets
  `failed to rename compilation results ... AccessDenied` on `.zig-cache`.
- Give WSL its own caches: `ZIG_GLOBAL_CACHE_DIR=~/zc-global zig build <step> --cache-dir ~/zc-local`.
- A git worktree's `.git` file holds a WINDOWS path, so **WSL git cannot operate in it**
  (`fatal: not a git repository: .../C:/Users/...`). Switch branches with Windows git, run zig in WSL.

## 6. Attribute test failures against a baseline, always

Run the same step on plain `upstream/main` in the same tree and compare counts AND names:
ours 3,540/3,577 (28 fail) vs upstream 3,541/3,576 (26 fail) - a raw total cannot tell you whether
your rebase added failures. Diff the failing test names, not the summary line.

## 7. Keep measured-negative work out of the submission

A fork branch carries experiments. On this tree `TF_GLM_L2PF` and `TF_EXL3_PIPE` measured slower at
every stream count; they must never appear in an upstream PR even though they sit on the same branch.
Split the delta commit by commit and state explicitly which commits are excluded and why.
