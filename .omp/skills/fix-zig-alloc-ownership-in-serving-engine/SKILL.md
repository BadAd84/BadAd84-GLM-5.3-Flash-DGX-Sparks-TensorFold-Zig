---
name: fix-zig-alloc-ownership-in-serving-engine
description: "Collapse duplicated allocations in a Zig serving engine safely, with leak-count gating; use when memory work needs two slice fields to share one buffer"
---

# Fixing Zig allocator ownership in a serving engine

Use when a memory fix collapses duplicated allocations (two slices that hold the same data) or
touches any Entry ownership in an engine with hot-path allocators. This is the pattern that took
three failed attempts and 100+ leaks on TensorFold's prompt_cache before it worked.

## The rule that matters

Free by OWNERSHIP CASE, never by field name. When one buffer backs two slice fields:

```zig
pub fn freeE(e) void {
    if (e.own.len > 0) {
        free(e.own);                      // backs `tokens`, and `last` unless replaced
        if (e.last_own) |l| free(l);      // a resume's or learned entry's own dupe
    } else {
        free(e.tokens);                   // no shared buffer: tokens is its own dupe
        if (e.last_own) |l| free(l) else free(e.last);  // ...and last is too
    }
}
```

Fields: `own: []u32 = &.{}` (shared buffer, default empty) and `last_own: ?[]u32 = null`
(set when a resume or learn replaces `last` with a separate allocation).

## The three cases that break naive versions

1. **A learned/recalled entry owns TWO separate dupes** (tokens and last, no shared buffer). If
   `free` only handles `own`, it leaks the tokens dupe. This is the 6->17->30 leak jump.
2. **A resume replaces `last` only.** The new dupe is separate (`last_own`), but the OLD `last`
   may alias `own`; freeing it is a double-free / use-after-free on `tokens`.
3. **Tests build Entry literals directly** with two dupes and never set `own`. `free` must still
   free their `last`, or the tier suite reports leaks that look like engine bugs. Never patch the
   tests to fit the allocator - make `free` cover the legal states.

## Gating procedure (do it in this order)

1. `zig fmt --check <file>` (the repo gate; fix formatting before tests, since gate scripts run fmt first).
2. `zig test -lc <module>.zig` and require **rc=0 AND zero "leaked" matches in stderr**. rc alone is
   not enough - a run can print leaks and still exit 0 in some build modes. Count the stdout/stderr
   separately: `cmd 2>/tmp/e.err >/tmp/e.out; echo rc=$? leaks=$(grep -c leaked /tmp/e.err)`.
3. Run the module's dedicated tier/integration test file too - it exercises the paths the unit
   tests miss (this is where the learned-entry leak showed up).
4. Only then the full host suite for the tree.

## Build the tree faithfully, off the serving box

If the serving box is in use, reconstruct the exact patched tree in a separate environment
(`git worktree add <dir> <pinned-sha>` + apply the recipe's patch series in order) and run the
suite there. A multi-minute compile beside a live serve trips memory guards and kills the serve.
Check the fork's build step names first (`zig build -l`); a fork may have `test` instead of
`test-cuda-host`.

## Anti-patterns that cost the night

- Editing the file across a stash/checkout cycle so several patch scripts overlap: nobody can
  reason about the state and every fix regresses another case. Revert to the committed file and
  apply ONE patch in ONE pass.
- Fixing one leak at a time from stack frames: the stack shows where the leaked allocation was
  MADE, not which branch failed to free it. Read the ownership cases instead.
- Changing the tests to match the implementation. The tests are the specification of the legal
  states.
