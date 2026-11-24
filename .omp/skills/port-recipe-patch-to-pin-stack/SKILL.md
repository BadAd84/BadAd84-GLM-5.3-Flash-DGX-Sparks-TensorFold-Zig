---
name: port-recipe-patch-to-pin-stack
description: "Porting an ai-engine knob commit into the GLM Zig recipe repo as a numbered .patch file: worktree setup, graft conflict rules, gate set, fresh-apply proof, landing and dual push."
---

# Porting a patch into the GLM Zig recipe stack

Context: recipe repo `C:/Users/Adam/Gitea/GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig` (patches/engine/000N-*.patch applied in order on the engine pin in scripts/config.sh). ai-engine (`C:/Users/Adam/Gitea/ai-engine`, trunk `merge-wt`) is the source of commits.

## Loop

1. **Locate the commit(s)** in merge-wt: `git log --no-merges --format='%h %s' 9c9bf542..HEAD --grep=...`. One patch = one knob; a knob that spans commits squashes.
2. **Dependency order first**: read the commit message and `git show --stat`. If it touches a mechanism the pin lacks (e.g. REPLY_PREFILL needed any-row snapshots), port the prerequisite FIRST - an era-mismatch shows up as unresolvable conflicts, not merge failures.
3. **Worktree**: `git -C work/aie/merge-wt worktree add --detach work/aie/pN 9c9bf542` (run from an existing dir; the target dir must not be the cwd). Apply the whole current stack from the recipe repo, commit as one step (`git add <explicit paths>`; never -A).
4. **Apply**: `git diff SRC^ SRC -- ':!zig/tests/cuda/main.zig' > scratch/x.patch` (exclude main.zig - its refs are hand-added last; exclude files the pin does not have). `git -c rerere.enabled=false apply --3way` - NEVER trust a stale rerere resolution.
5. **Conflict rules**: (a) if theirs is the change under test and it REPLACES pin machinery (snap_grid -> any-row), take theirs but keep pin-only conditions visible in ours (images.matches, own_only, pieces) by unioning; (b) if ours is pin-only design (KV share keeps/marksOf, prompt_solo), graft theirs' new function BESIDE it; (c) duplicate function names after a union = drop the older body, keep the newer signature; (d) missing helper after a splice (drafterIdle, moot) = re-add it with its import.
6. **Gates, in this order**: `zig.exe build check-native-cuda-host` (0 errors); whole-tree `zig fmt --check zig/`; lean via EACH SIDE'S OWN copy of tools/zig/lean_check.py (the tool resolves ROOT from its own path - running the base with the head's copy scans the same tree twice and reports identical counts; a real base/head pair always differs by >=1 file), then `lean_new.py base.txt head.txt` = 0 new; `test-lane-api-host` when core/lane files changed (rc=0, ~90 s); `scripts/engine/fatbins.cmd <tree>` when any .cu changed (grep the log for `failure`).
7. **Lean findings**: single-line every comment to <=120 cols. Attribution comments in third-party-derived .cuh files are COMPRESSED, not deleted. A file pushed past 600 lines gets a cohesive block moved to a companion module with the helpers it needs exposed pub (see cuda_lanes_step.zig).
8. **Stage + patch**: `git add <explicit paths>`, `git diff --cached --binary > body.patch`, prepend the receipt header (source sha, mechanism, measurement with the docs row, knob default, gates). Land as patches/engine/000N-<name>.patch.
9. **Fresh-apply proof**: new worktree at the pin, apply ALL patches in order, re-run compile + fmt + lean. Never land on the graft tree's word alone.
10. **Land**: recipe repo commit via `git commit -S -F <file>` (Windows-side path, NOT /tmp - git is Git-for-Windows), explicit path staging, dual push (origin main + the BadAd84- GitHub mirror). Delete the used candidates WIP.

## Traps

- `git commit -F /tmp/...` fails: write the message file under work/scratch (Windows path).
- `git apply --3way` is atomic on a dirty index: commit the stack first.
- A failed --3way can roll back silently; check `git status --porcelain | grep '^UU'` and `git diff HEAD --stat` after.
- The bash tool cannot start in a directory that does not exist - create worktrees from an existing cwd.
- Fatbin nvcc failures do not print diagnostics into the fatbins log; reproduce with the harness's exact command line (it sets vcvars64 PATH itself - an ad-hoc shell lacks cl.exe).
- Era comments (multi-line doc blocks) from source commits fail the lean rule; keep one line, move detail to the patch receipt.
