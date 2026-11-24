---
name: verify-a-base-vs-head-gate-sees-two-trees
description: "Prove a lint/gate really compares base against head, not one tree twice (identical file counts are the tell); use before quoting any 0-new result."
---

# Verify a base-versus-head gate sees two trees

Use when you are about to quote "0 new" from a repo gate, or when a gate's two sides report suspiciously equal numbers.

## The failure this prevents

A checker that derives its root from `__file__` (TensorFold's `tools/zig/lean_check.py` uses
`Path(__file__).resolve().parents[2]`) ignores the cwd. Running the worktree's copy from inside an extracted base
directory therefore scans the WORKTREE twice. Both sides print the same count and the "0 new" is meaningless.
Measured twice in one day ("424 vs 424", "740 vs 740"), both accepted at first.

## Procedure

1. Extract each side into its own directory (base: `git archive <base> | tar -x -C $BASE`, head likewise).
2. Run each side's OWN copy from inside its own tree:
   `(cd $BASE && python $BASE/tools/zig/lean_check.py > base.txt)`
   `(cd $HEAD && python $HEAD/tools/zig/lean_check.py > head.txt)`
3. Print both counts. **Identical file counts are a failure of the harness, not a clean pair** - a real pair differs by
   at least the files the change adds or removes.
4. `diff` the two lists, then run the repo's comparator (`lean_new.py base.txt head.txt`) and quote its line.
5. Record the base sha beside the counts; upstream main moves hourly, and a fork trunk measured against current main
   will show inherited problems until it is rebased.

## Also check

- Keep filesystem paths consistent between the shell and the interpreter: in WSL bash, `/tmp/x` and Windows
  `C:/tmp/x` are different files, and a missing base list fails the comparator with `FileNotFoundError`.
- If the comparator reports a NEGATIVE delta (head has fewer problems than base), say so instead of "0 new"; it means
  the base has since gained problems the head does not have.
