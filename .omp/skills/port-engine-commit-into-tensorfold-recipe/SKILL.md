---
name: port-engine-commit-into-tensorfold-recipe
description: "Port one ai-engine OTS commit into a TensorFold recipe repo as a numbered patch: extract, graft onto the pin, prove with the real gates, land with a receipt."
---

# Port a commit into a recipe repo

Loop for turning one ai-engine OTS commit into `patches/engine/NNNN-*.patch` in a recipe
repo (`ots/GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig` and siblings). Proven over 31 patches;
the gate and conflict rules below are the parts that cost the most to learn.

## 1. Bases

- Recipe pin lives in `scripts/config.sh` (`TF_REF`). Never bump it for upstream movement alone.
- Cut a patch's body from a **committed** base: `git worktree add --detach <wt> <pin>`, apply
  patches `0001..N-1`, commit, then copy the changed files and `git diff`. Diffing against the
  pin makes the body swallow every earlier patch; diffing a dirty worktree produces a body that
  will not re-apply.
- Verify the base before cutting: the file the next patch targets must be at its pre-patch
  state, and era-only files (e.g. `cuda_forward_fronts.zig`) must be absent.

## 2. Graft, do not take whole files

- `git apply --3way <commit-diff>` first. Conflicts mean the pin evolved at the same site.
- NEVER take whole files from the source-commit tree: it drags pre-pin eras back and silently
deletes upstream work (lost `propose`, `solo_rows`, `twin`, `piecesOf`). Instead restore the file
to pin+stack state and graft only the knob's hunks.
- Take THEIRS only where the conflict **is** the change under test; take OURS plus theirs'
additions where the pin has newer design (solo/pair, KV-share marks, L2PF).
- After resolving, sweep the tree for leftover conflict markers:
  `grep -rn '^<<<<<<<\|^=======$\|^>>>>>>>' zig/src zig/kernels`. A stray marker produces a
  cascade of phantom "declarations are not allowed between container fields" errors that look
  like a brace bug in an unrelated struct.

## 3. Gates (the part that matters)

Run on the applied tree, in this order:

    zig build check-native-cuda-host      # compile only
    zig build test-cuda-host              # THE gate for family patches
    zig fmt --check zig/                  # whole tree, not touched files
    python tools/zig/lean_check.py        # base list and head list, diffed with lean_new.py
    fatbins for any .cu/.cuh change

- `check-native-cuda-host` and `test-lane-api-host` do NOT compile family host tests. Green in
  them says nothing about the model's suite.
- `lean_check.py` resolves its root from `__file__`, so run **each side's own copy**
  (`(cd $BASE && python $BASE/tools/zig/lean_check.py)`); otherwise both sides scan one tree and
  report identical counts, which is the tell that the gate is meaningless.
- Comments: one line, <=120 columns. Files: <=600 lines; move a cohesive unit out rather than
  growing one. Attribution for third-party kernels stays in the header.
- fatbins: a `-gencode=compute_121,code=sm_121` compile of every fatbin catches nvcc errors that
  no zig step runs (upstream moves `cp_async_*`/`ldmatrix_x4` into `common/` and knob kernels
  still call the old names).

## 4. Prove the knob is actually wired

After applying, grep the knob name in `zig/src` (not just its test): a receipted knob whose read
never lands in `facts()` or a runtime branch is dead. Five knobs (WIN_FREE, DEPTH_FULL, SHARED_COPY,
SHARED_DRAFTS, PLAIN_MARGIN) were receipted green and read nowhere. Also check for duplicated
calls introduced by a hook insertion (a `sparseAttentionFormat` pair made every DSA prompt pass
run attention twice).

## 5. Land

- Patch file = receipt header (source commit, mechanism, default-off statement, measured gates)
  followed by the body. Pin `*.patch` and `*.sh` to `eol=lf` in `.gitattributes`; a CRLF patch
  fails every hunk with "trailing whitespace".
- Commit with `git commit -S -F <file>`, staging explicit paths. Add a ledger row in the same
  push so `PORT-LEDGER.md` never contradicts the tree.
- Ledger states current state only: what is landed (with its gates), what is parked and why,
  and the acceptance criteria. Delete superseded paragraphs rather than keeping both.
