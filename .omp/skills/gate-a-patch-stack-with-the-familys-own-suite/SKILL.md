---
name: gate-a-patch-stack-with-the-familys-own-suite
description: "Before claiming a patch stack green: run the family's own host test step, baseline the pristine pin first, and pin patch line endings to LF."
---

# Gate a patch stack with the family's own suite

Applies when a repo applies numbered `.patch` files onto a pinned upstream commit and
each patch is claimed proven.

## 1. The wrong gates look green

Compile-only and adjacent-suite steps do not compile the family's host tests. On
TensorFold, `check-native-cuda-host` and `test-lane-api-host` both passed while
`test-cuda-host` failed 9 binaries with 27 named failures. Whatever the repo's family
step is called (`test-<family>-host`, `test-cuda-host`), THAT is the gate for a family
patch.

## 2. Baseline the pin before attributing anything

Run the same step on a pristine checkout of the pinned sha. Upstream may be red on the
machine (golden-digest tests are environment-sensitive). Compare failing-test NAME
sets, never counts:

```
grep -E "^error: '" <log> | sed "s/ exited.*//" | sort -u
```

Only names absent from the pin's set are regressions. Confirm the test files are even
in the pin's graph (`ls zig/<file>` plus a grep in `zig/build/*.zig`) before claiming
"pin green, stack red".

## 3. Two traps that cost a cycle each

- **CRLF in patch files.** `git checkout -- patches/` under `core.autocrlf` can restore
  `*.patch` with CRLF; every hunk line then reads as trailing whitespace and the whole
  stack fails from 0001 onward. Pin it: `*.patch text eol=lf` in `.gitattributes`, then
  normalise any already-converted files.
- **Never `git checkout -- <file>` in a worktree whose stack is applied but uncommitted.**
  That reverts the file to the pin, not to the patched state. Rebuild by re-applying the
  patches.

## 4. Prefer one corrective patch to regenerating many

Rebuilding individual patch files from tree states cascades: one header mismatch makes
0001 fail and every later patch then fails on context. A single corrective patch whose
receipt names the owning patch per hunk is the lower-risk artifact, and it keeps the
provenance readable.

## 5. Report the measured pair

State the baseline and the current numbers together (binaries and named failures), and
name every remaining failure in the repo's ledger. A count that improved (27 -> 11) is
not a clean gate.
