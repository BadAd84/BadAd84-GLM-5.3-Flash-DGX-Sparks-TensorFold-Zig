---
name: reseat-a-patch-series-onto-moved-upstream
description: "Carry a numbered engine patch series onto a much newer upstream base with git apply --3way, then prove the re-seat is complete, not merely green."
---

# reseat-a-patch-series-onto-moved-upstream

one skill: re-seat a patch series onto a moved upstream base

Merged from 16 skill(s): audit-a-reseat-for-silently-partial-patches, hand-port-a-patch-stack-onto-moved-upstream, port-a-kernel-patch-series-onto-a-rebuilt-base, port-diverged-third-party-patch-series, port-ots-patch-onto-new-upstream-base, port-ots-patch-stack-onto-moved-upstream, port-ots-patches-onto-rebased-upstream, prove-a-reseat-is-complete-not-just-green, re-seat-a-patch-series-with-a-three-way-merge, reseat-a-patch-series-onto-a-moved-base, reseat-a-patch-series-onto-a-moved-upstream, reseat-a-patch-series-onto-moved-upstream, reseat-a-patch-series-with-three-way-merges, reseat-patch-series-by-chained-merge-tree, reseat-patch-series-by-merge-tree-chain, restore-a-partially-applied-patch-series.

# Hand-porting a patch stack onto a moved upstream

For a fork pinned at an old upstream commit whose local patches mostly no longer apply (measured: 21 of 26 failed after 1,102 upstream commits). A rebase cannot work; each patch needs re-deriving against the new code.

## 1. Measure before touching anything

```sh
cd <upstream-clone> && git fetch origin --prune --tags
git rev-list --count <pin>..origin/<default-branch>
git diff --shortstat <pin> origin/<default-branch>
git diff --name-only <pin> origin/<default-branch> | cut -d/ -f1-2 | sort | uniq -c | sort -rn | head
# migrations/DB deltas decide whether the upgrade needs a data plan, not just a rebuild
git diff --name-status <pin> origin/<default-branch> -- <db dir> | grep -cE '^A.*(migration|\.sql$)'
```

Check the default branch name first (`git ls-remote --symref origin HEAD`); upstreams rename it. Also check release tags: a tag whose commit is behind your pin means master is the only forward target.

## 2. Triage every patch: applies / drifted / obsolete

Test each patch independently against a clean worktree of the new tip:

```sh
git worktree add --detach /tmp/base origin/<default-branch>
cd /tmp/base && git apply --check <patch>   # per patch
```

For each failure, decide which it is by reading the NEW code, not the patch:

- **Obsolete** - upstream now does the same thing (different names). Grep the new tree for the behaviour (e.g. the leak you fixed, the gate you relaxed). Evidence, not intuition: `grep -n '<symbol>' <file>`. Example findings: a `thread/read` transcript our patch bounded is no longer sent at all; a lifecycle restriction our patch relaxed was deleted with its whole policy file.
- **Drifted** - the fix is still needed, the target moved. Note whether only *part* of the patch is obsolete (e.g. upstream stopped loading heavy columns per row, so only the single-flight guard was still worth porting).

## 3. Port by anchor, one patch at a time, asserting exact matches

Write a small Python script per patch that asserts each anchor matches exactly once before writing:

```python
def sub(old, new, count=1):
    global s
    n = s.count(old)
    if n != count: sys.exit(f"anchor matched {n}, expected {count}: {old[:80]!r}")
    s = s.replace(old, new, count)
```

Read the new target first (its class may be renamed, its function split, its call site moved) and anchor on the *new* text. Keep the patch's comment explaining WHY, updated for the new shape.

### Traps, each measured

- **`git apply -C0` silently misplaces hunks.** With zero context it matched a lookalike line inside an unrelated route function and inserted the patch there. It typechecked only because the injected code was syntactically valid. Always `git diff` immediately after any fuzzy apply and read the hunks; when in doubt, revert and hand-port. Use `-C1`/-C2 for genuinely near-identical files (that worked for a UI patch), never `-C0` for logic.
- **Extracting a new file from a patch**: for a creation hunk take the `+` lines. For a *modification* of a file added by an earlier patch, rebuild the post-image from ` ` and `+` lines of every hunk. Regions of a file that no hunk touches are NOT included - a test file reconstructed this way lost its setup loop. Prefer writing the file by hand when the post-image looks short.
- **A test asserting the very invariant you change** is legitimate to update, with a comment naming the patch (e.g. upstream asserted a 4,096-event window that our trim deliberately shrinks to 512).
- **Test doubles**: a mock `QueryClient`/client that lacks `setQueryData`/`getQueriesData` fails only once our code writes through the client. Add the no-op method to the specific mock (find a unique anchor; the same mock shape often repeats many times, so a blanket replace creates duplicate keys).

## 4. Generated artifacts: regenerate, never hand-patch

Patch hunks for generated JSON never apply. Regenerate, and mind the ordering:

- The generator may read the **compiled** package (`dist/`), not `src/`. Running `generate:...` before `build:typescript` silently reproduces the OLD content, and the build's `--check` then fails with "is stale".
- So: full tree copy into the build image, `build:typescript`, then `node scripts/generate-semantic-contracts.mjs`, then copy the artifacts back and confirm with `--check`.

## 5. Verify inside the production image

The production image keeps `tsc` and `vitest`; its test fixtures are pruned, so copy them from the tree.

```sh
docker build --target production -t <img> <tree>          # Rust + UI + server is the real gate
docker run --rm -u root -v <tree>:/src:ro --entrypoint sh <img> -c '
  cp /src/<changed files> <same path>
  cp -a /src/<pkg>/test/fixtures/. <pkg>/test/fixtures/   # pruned in the image
  npx tsc --noEmit -p .                                   # per touched package
  npx vitest run <suites for the touched areas>
'
```

A suite that fails on a missing fixture is an environment gap, not a code failure - check the error before "fixing" code.

## 6. Record the outcome durably, per patch

Export the series (`git format-patch <tip>..HEAD`) plus a ledger that names, for each patch: ported (with the port note), or obsolete (with the evidence). A patch stack that spans sessions cannot live only in a worktree on one box. State the remaining operational gates in the ledger: migration rehearsal on a copy of the DB, and a runtime soak of whatever area failed the last upgrade attempt.

# Porting a patch series onto a rebuilt base

For moving our knobs/patches from an older engine stack onto the current upstream recipe, and proving it before it ships.

## 1. Build the reference base twice over

- engine source at the tag the recipe pins (e.g. TensorFold v0.6.0), materialised in WSL so line endings are LF (a Windows clone gives CRLF and every patch fails with "different line endings")
- apply the recipe's own patches with `patch -p0` from the recipe commit that matches the version we run (find it in CHANGELOG.md), then our ports in `sync/ORDER`
- the result is what the hunt images are built from; diffing production's tree against it is what tells you what is ours

## 2. Respect series order

A patch numbered later may assume an earlier one landed. Measured: PooledKeys-3 alone leaves 34 conflicting hunks against the base; PooledKeys-1 then -3 leaves 18. Always test the whole series in order before concluding a patch is unportable.

## 3. Resolve rejects by lane, in parallel

Give each agent exclusive files and tell it: apply the reject's intent by hand, adapt only context, never redesign; report hunk by hunk what the current file forced; `py_compile` every .py. Kernel files cannot be compiled locally, so demand structural evidence: kernel and launch argument lists agree positionally, every template value instantiated, brace balance, and a diff against the reference stack where every written line is byte-identical.

## 4. Prove the artefact, not the tree

`diff -u` the base against the finished tree into one patch, then round-trip it: apply to a fresh copy of the base with `patch -p0` and require zero fuzz and a byte-identical result. Grep that every line referencing each knob exists verbatim in the file the working image runs.

## 5. Build the image with a Dockerfile

Never `docker commit` a container started with an override: commit freezes the CONTAINER's config, so `--entrypoint sh` becomes the image's entrypoint and the serve runs the console script through a shell ("import: command not found", every boot fails). Use `FROM base`, `COPY` patches, `RUN patch -p0 && import check`, and verify `docker inspect --format '{{.Config.Entrypoint}}'` matches the base. Build on EVERY rank the serve spans; a missing image on one rank fails the boot with PREPARE=0.

## 6. Gate before timing

Boot the same image once per knob setting (off, and each mode) at P1 with a realdec-style probe and require identical digests: a layout change must not move tokens. Only then measure, and measure at concurrency levels 4 and 1 at least, because this class of change shows its gains on aggregate and not on a single stream.

# Porting an OTS patch onto a new upstream base

Use when upstream's recipe has moved and our `ots*.patch` files no longer apply. Measured on
TensorFold v0.6.0 with upstream at 124 patches and 49 OTS patches (2026-10-29).

## 1. Rebuild the base exactly, never approximate it

- `git clone --depth 1 --branch v0.6.0 https://github.com/ashhart/TensorFold.git base`
- Upstream's patch files address `tensorfold/...`, and in the v0.6.0 repo that tree lives at `src/tensorfold/`.
  So apply from `src/` with `patch -p0 --forward --batch` (NOT `git apply`, which has no fuzz and needs a clean
  index; NOT `-p1`).
- kindling spark-os has no host `patch`: run the loop in a container,
  `docker run --rm -v $PWD:/w -v /patches:/up debian:bookworm-slim bash -c 'apt-get update -qq && apt-get install -y -qq patch && cd /w/src && for p in /up/*.patch; do patch -p0 --forward --batch < $p; done'`.
- Success criterion is `ok=<all>` and zero `FAILED` lines; a clean base is `git status --short` empty and no `*.orig`.
- Some upstream patches ship in abbreviated form (`diff --git` straight into `@@` with no `---`/`+++`): GNU patch
  infers the filenames, `git apply` refuses. That is a reason to prefer GNU patch throughout.

## 2. Judge "already upstream" by applying, not by similarity

- Text-similarity matching overshoots: a patch at 40-60% signature coverage may be a reworked upstream
  equivalent, or may be ours-only. Apply our patch to the fresh base with `patch -p1 --forward --batch` and read
  the per-hunk result.
- `patch` exit 0 with "previously applied" can mean ONE file was already applied while others failed: always check
  for `*.rej` and count `FAILED`, not just the exit code.
- Confirm substance by symbol: grep the upstream patch set for a distinctive identifier from ours
  (`TF_GLM_*` flag, function name). A symbol hit is proof the feature landed, whatever the text.

## 3. Handle module-name collisions first

Two patches may both create `cuda/<name>.py` for different features (ours DSA indexer sharding vs upstream's KV
sharding both wanted `shard.py`). Rename OURS (upstream's name is the one the rest of upstream imports), then
rewrite our patch: the file path, the import tuple, and every call site (`shard.foo(` -> `indexer_shard.foo(`),
while leaving fields such as `sel.shard` untouched. Keep both modules imported where both are used.

## 4. Resolve rejects by hand, one at a time

- Regenerate the rejects with the patch kept (`rm` the previous run's `*.rej` first, and do not delete them in the
  same loop that applies).
- Read the reject against the CURRENT upstream text (`sed -n` around the hunk) rather than our old file.
- The usual causes: an import line now carrying another module, or an inline block that upstream has since moved
  into a helper. When the helper already exists upstream with the same signature, the fix is to replace the block
  with the call (that is exactly what our patch did before the helper was split out).
- Verify with `python3 -m py_compile` on every touched file.

## 5. Emit and prove the ported patch

- Diff the port tree against the base, excluding noise:
  `diff -ruN -x '*.orig' -x '__pycache__' base/src port/src | sed -e 's|^--- base/src/|--- |' -e 's|^+++ port/src/|+++ |'`
  which yields upstream's `-p0` form (`--- tensorfold/...`).
- Proof, mandatory: copy the base to a fresh tree, apply the ported patch with `patch -p0 --forward --batch`, and
  require `rc=0` and zero `FAILED` hunks.
- Name it with the next free number (`ots0132-...`) and state in the commit which original patches it replaces, the
  rejects resolved and how, and the proof numbers.

## 6. Sequence and verify at the end

Port in value order, one commit per port; then build ONE image and run the digest harness (`firstreq.py`) plus the
acceptance suite. Patch application is not the verdict: bit-identical replies on the new base are.

# Porting our OTS patches onto a moved upstream base (GLM Spark recipe)

Use when upstream (`MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold`) has moved past our base and the
question is "are we in sync, do our patches still run". Measured on 2026-10-29 (49 OTS patches vs upstream's 124).

## 1. Rebuild the base, don't guess it

- Upstream pins TensorFold `v0.6.0`; the GitHub clone keeps the package under **`src/tensorfold/`**, while
  upstream patches address paths as **`tensorfold/...`**. So: clone at the tag, clean it
  (`git checkout -- . && git clean -fdxq`), then run `patch -p0 --forward --batch` **from `src/`**.
- Kindling spark-os has **no host `patch`**: patch inside a container,
  `docker run --rm -v <tree>:/w -v <patches>:/up debian:bookworm-slim bash -c 'apt-get update -qq && apt-get install -y -qq patch && cd /w/src && for p in /up/*.patch; do patch -p0 --forward --batch < $p; done'`.
- GNU `patch` is required, not `git apply`: some upstream patches are abbreviated (`diff --git` straight into
  `@@`, no `---`/`+++`) and `git apply` refuses them while `patch` infers the names.
- A clean base is the deliverable: `124/124 applied, 0 failed`. Copy it before every attempt
  (`cp -a base port`) so stacks are reproducible.

## 2. Classify our patches before porting any

Cheap signals, in this order:
- **content match**: for each of ours, take its distinctive added lines (>=40 chars) and see which upstream patch
  contains them. High coverage = already upstream (renumbered).
- **symbol match** is the decisive one, because upstream reworks the code: grep upstream `patches/*.patch` for the
  flags/function names ours introduces (`TF_GLM_*`, a unique helper name). If the behaviour is there under a new
  number, ours is **superseded, not lost** - say so with the mapping.
- **apply test**: `patch -p1 --forward --batch` on the base. "PARTIAL" often just means the code evolved; it is NOT
  proof the behaviour is missing. `patch` exiting 0 with "previously applied" for ONE file does not mean the whole
  patch is present - check for `.rej` files and hunk failures, never the exit code alone.

## 3. Porting a patch: reject classes

Apply on the accumulated stack, then read every `.rej` and classify:

- **real** - the change is genuinely absent: place it by hand against the new context.
- **already landed** - another hunk of the same patch put it in: verify by grepping the symbol, then drop the reject.
- **superseded** - the base implements the same thing better (e.g. our `_start`/`_feed`/`_finish` helpers vs the base's
  `_History` running hash): drop it and record the mapping.
- **obsolete** - the code it patched is gone (e.g. our `self.tier` vs the spill/disk path): drop it, and check the
  protection it provided still exists somewhere (for cache_salt it did, in the disk gate).

**Always check for orphan references after a partial apply.** A half-applied patch can leave a call to a symbol the
rejects were supposed to define (measured: `_Signer` referenced once, defined nowhere - a guaranteed runtime
`NameError`). `grep -c` each new symbol: one occurrence means a dangling reference.

## 4. Landing rules

- Ported patches go in **`scripts/glm53/v110/sync/`**, never `v110/`: `build_v110.sh` globs `v110/ots[0-9]*.patch`
  and would try to build them into the current image.
- Emit each port as `diff -ruN -x '*.orig' -x __pycache__ <prev-stack>/src <stack>/src`, then rewrite the two
  prefixes to bare `tensorfold/...` so it applies with `-p0`. Delete `*.orig` first: a base built with `patch` leaves
  them and they pollute the diff.
- Prove every port on a FRESH copy of the previous stack: `rc=0` and `0 FAILED` before committing. Compile the
  changed files (`py_compile` in a container if the host tree has no python3).
- Commit with explicit paths; a `git add` pathspec naming a file that was moved aborts the whole add and the commit
  lands empty-looking (measured).

## 5. Serial-apply hygiene

A tree that has already been patched is no longer a base: reapplying reports mass failures that look like reject
storms but are just an already-applied tree (measured: 65 "failures" from an uncleaned tree). Always rebuild the
base, or copy it, before measuring apply rates.

# Porting an OTS patch stack onto a rebased upstream

Measured on the glm5.3-flash-dev sync (2026-10-29): upstream main = 124 patches on TensorFold v0.6.0; our 49 old
patches reduced to 8 ports + 2 no-ops + 18 superseded.

## Build the base first, reproducibly

- Upstream patches address `tensorfold/...`; a v0.6.0 clone keeps them under `src/`, so apply with
  `patch -p0` **from `src/`** (or `git apply -p1 --directory=src/tensorfold`). Our patches are `a/tensorfold/...`:
  apply with `patch -p1` from `src/`.
- kindling spark-os has no host `patch`; do it in a container (`debian:bookworm-slim` + apt install patch).
- Start every port from a FRESH copy of the previous stack (`cp -a stack pN`), never a tree that already has rejects
  and `.orig` files: a dirty pre-image produces mass spurious failures.

## Classify before porting (four buckets)

1. **Already upstream** - match by symbol, not by credits: grep the base for the flag/function the patch introduces.
   Content-signature matching over-reports; a patch can show "CONFLICT" while its feature is fully present.
2. **Superseded** - the base has a better implementation (e.g. an incremental `_History` class replacing our
   `_start/_feed/_finish` helpers). Drop, but say why.
3. **No-op** - the change is already the value we want (a tuning constant): diffing the tree afterwards yields ZERO
   lines, which is the proof.
4. **Port** - the rest.

## Triage every rejected hunk by class

- **Already landed via another hunk** (very common): grep the symbol; if defined, discard the reject.
- **Target moved/removed**: e.g. `self.tier` no longer exists (a spill tier replaced it), `_from_disk` is gone, or the
  agreed-settings list now carries upstream's `shard.ON` instead of our `indexer_shard.SHARD_MODE`. Place against the
  LIVE code, not the reject's context.
- **Real, place by hand** against current context, with an assert that the anchor matches exactly once.

## The rename sweep (silent-wrong-code trap)

If a ported patch does `from . import shard` and upstream now ships its own `shard` module, the import resolves and the
feature guards the WRONG module. Rename ours (e.g. `indexer_shard`) across every ported patch and its call sites, and
note that our own module keeps a distinct name.

## Proofs to run for EVERY ported patch

1. `patch -p0 --forward --batch` on a fresh copy of the previous stack -> `rc=0` and zero `FAILED`.
2. `py_compile` every touched file, and compile the whole patched tree (a rename that parses wrongly is invisible to
   "patch applied").
3. Orphan check: for each symbol the landed hunks call, assert a definition exists somewhere (annotated dataclass
   fields count - match `^\s*name\s*[:=]`, not only `^name =`).
4. Save the delta as `diff -ruN` in `-p0` form into a directory the build glob cannot see (build scripts glob
   `patches/ots[0-9]*.patch`; keep ports in `sync/`), and note they are regenerated as `git diff` output when the base
   is final.

## Finish

Only after all patches are in: build ONE image, then `firstreq.py` for the digest against the known production value
and the acceptance suite. Patch-by-patch application is not verification.

# Re-seat a patch series onto a moved upstream base

Measured on the GLM Zig serve: 32 patches onto a base 1,094 commits ahead of the pin. Budget a day; the merge is
afternoon-sized and the compile loop is most of it.

## 1. Survey, then distrust the survey

`scripts/reseat-survey.sh REF OUTDIR patches/engine` gives verdicts per patch (clean / absorbed / partial / refused) and
a rejected-hunk count. Treat the count as an upper bound: `git apply --check` calls ordinary text drift a reject.

## 2. Three-way merge collapses the drift

Make a detached worktree of a clone that holds BOTH histories (a `--shared` clone of the project clone works):

git -C <clone> worktree add --detach <abs-path> REF
    git -C <abs-path> apply --3way <patch>      # per patch, in file-name order

Two traps, both measured:

- **Paths resolve from `-C`.** `-C <tree> apply patches/x.patch` looks for the patch inside the tree. Pass the patch
  as an ABSOLUTE path, and the worktree path as absolute too, or it lands inside the source clone.
- **Marker polarity:** `<<<<<<< ours` is the BASE and `>>>>>>> theirs` is the PATCH. "Take theirs" applies your patch.
  An "ours" side that is empty means the base does not have those lines at all.

## 3. Rebuild the settings table by union, never hunk by hunk

Row insertions from different patches land in the same region of `platform/environment.zig` and are dropped silently: 25
of 36 rows vanished this way. Instead, collect every added row line from the patch set, and insert the ones whose names
are absent from the merged file, then verify the count. Same for doc tables.

## 4. The compile loop is a call-site hunt

`zig build check-native-cuda-host` is the compile gate and it reports errors a few at a time. Expect these classes:

- **Upstream definitions your resolution deleted.** A type or function that the base already had (`Mla`, `compactKv`)
  disappears when a conflict block is replaced wholesale. Check the base file for the name first; restore verbatim.
- **Fields the merge put on the wrong struct**, or as a value where a pointer is needed (`load` returns a value, so the
  field is a value and the setter takes its address).
- **Call sites of changed APIs**: an extra argument (a salt, a scales pointer), a renamed helper (`width` becomes
  `sparse.width`), an expression that already yields the field's type.
- **Tests are call sites too, and are the last layer to break**: test fixtures need fields the new code reads, and
their own call sites need the new arity. Fix them in the same loop; `zig build test-cuda-host` is the gate that finds
  them (it compiles several suites), and it reports a step count plus a test tally, so read both.

Format only on the shared gate host (`zig fmt <files>` there, then scp the files back); never compile or format on the
workstation.

## 5. Record what the cycles taught

The repo's own doc (the upstream TODO / re-seat note) gets each trap with the error text that revealed it, so the next
re-seat is a checklist rather than a rediscovery.

## When
A series of numbered patches must be carried onto a new upstream base, and a plain `git apply` survey reports dozens of rejected hunks.

## Procedure

1. **Survey first**: the repo's survey tool reports clean / absorbed / partial / refused per patch. A patch that does not apply is not automatically redundant, and a patch that applies clean can still be wrong on the new base.
2. **Apply with `git apply --3way`**, not plain apply. It merges around the drift using the patch's index blobs, and collapses the rejected-hunk count by roughly 4x. If it reports "repository lacks the necessary blob", the clone lacks the fork's history: fetch it in.
3. **Know the polarity**: in the conflict markers `ours` is the BASE and `theirs` is the PATCH you are applying. Taking `theirs` accepts your patch.
4. **Check the base before replacing a block.** A block that starts inside a struct can carry upstream's own type or function definition after its closing brace; resolving to `theirs` then deletes it. Before any replacement, `git show <base>:<path> | grep <symbol>`; restore upstream definitions verbatim rather than reconstructing them.
5. **Never merge a settings table hunk by hunk.** Rows from different patches land in one region and are silently dropped. Rebuild the table as the union of the base file's rows plus every row the patches add that the file lacks, then assert the row count against the patches.
6. **Compile, then fix in rounds.** Each round is smaller. Expect: fields that moved between structs, value-versus-pointer mismatches around a loader that returns a value, renamed fields (a wrapper calling `mtp` where the base calls `head`), and argument lists that gained a parameter (a salt, a scales pointer).
7. **Then the tests speak the old API too**: launch-record assertions, argument tuples, fixture structs. Each is a call site to update. Re-derive assertions from the merged implementation; never edit them to make a build pass.
8. **Compare any remaining failure against a pristine base run** of the same suite before blaming the patches - it separates pre-existing base failures from regressions you introduced.

## Gates that must be green before it counts as current
Compile step, the family host suite, `zig fmt --check`, and the wide host suite. A failure count alone is not a verdict: read which tests fail and classify them.

## Trap
A stale `index.lock` inside a staged tree makes `git checkout` refuse and an applier write into a temporary index while the files never move, so every patch looks incompatible. A staged tree reporting a clean status at the wrong sha, or an empty `before:` line, is the tell.

# Re-seating a patch series onto a moved upstream base

Use when a numbered series (e.g. `patches/engine/*.patch`) must be carried onto current upstream `main` after the pin has moved far. The goal is a tree that compiles, passes the family host tests, and is `zig fmt` clean on the new base.

## 1. Survey, then do not trust the survey's size

`scripts/reseat-survey.sh REF OUTDIR PATCHDIR` reports `clean | absorbed | partial | refused` per patch and counts rejected hunks. Measured: 24 partial patches and 114 rejected hunks became **27 conflict blocks in 18 files** under `--3way`, because the patch blobs are reachable from the parity clone. So the survey picks the order and names the cost, and `--3way` decides the real work.

- `absorbed` (the reverse applies) means upstream already has it: retire the patch, do not port it.
- A patch that applies clean still needs a compile: text agreement is not API agreement.

## 2. Apply with `--3way`, one patch at a time, absolute paths

```
git -C <tree> apply --3way "$REPO/patches/engine/0001-x.patch"
```

- **Absolute paths for both the tree (`-C`) and the patch.** A relative patch path is resolved from the `-C` directory, so the apply silently does nothing or fails on a path that does not exist under the tree.
- Exit non-zero means conflicts were left as markers in the files; resolve after, or ideally per patch for attribution.

## 3. Conflict polarity, and the deletion trap

In `git apply --3way`, **`<<<<<<< ours` is the BASE and `>>>>>>> theirs` is the PATCH**. Taking "theirs" therefore applies our code. Two consequences:

- Where our patch adds a feature into a function upstream restructured, take upstream's body and layer our lines on it.
- **A resolution that replaces a whole block can delete something the BASE added** (a type, a helper, a struct's closing brace plus its next declaration). Before replacing a block, check the base file for what surrounds it; if a definition vanished, restore it verbatim from `<base>:<path>`.

## 4. Never merge a settings table hunk by hunk

Row insertions from different patches land in the same region of `platform/environment.zig` and hunk-wise merging silently drops them (25 of 36 rows vanished, and only three compile errors pointed at the table). Rebuild it by union:

1. Extract every added row from the patches: lines matching `+    .{ .name = "TF_..."` with a `.scope = .`.
2. Take the base's table and insert any row whose name is not already present.
3. Verify the count afterwards (grep the total and compare with base plus added).

## 5. The API ripple is most of the remaining work, and it comes in rounds

Expect several compile cycles. Each is a class of call site, and each must be fixed everywhere in the file, not where the compiler first complains:

- an extra argument on a function we extended (e.g. an E4M3 `sk` before `out`);
- a struct replacing a pointer in a `Set` or options literal (a field now `Glue.Mla` where a `?*const Mla` was passed);
- a renamed field (`mtp` to `head`) on engine fakes and fixtures;
- helpers added to a definition list (`switches`/`added`/`levers`) whose count assertion fails on one new row.

## 6. Format on the build host, fetch the files back

`zig fmt --check` over the tree is a gate, and the laptop must not run it. Run `zig fmt <files>` on the gate host and `scp` the formatted files back into the worktree; then re-check `zig fmt --check build.zig zig`.

## 7. A stale git lock looks exactly like a broken tree

A staged tree that reports a clean status at the wrong sha, an applier whose `before:` tree id is EMPTY, or `fatal: bad object HEAD`, is a `.git/index.lock` (or another `*.lock`) left by an interrupted git operation:

```
find <tree>/.git -name '*.lock' -delete
git -C <tree> checkout --detach <pin>
```

Check for a live git process first, then re-checkout and confirm `rev-parse HEAD` is the pin and the source directories are populated before applying anything.

## Acceptance

- `zig build check-native-cuda-host` rc 0
- the family host suite (`zig build test-glm-rev25-host`) rc 0
- `zig fmt --check build.zig zig` rc 0
- then the wider `test-cuda-host`, which will surface the remaining fixture and call-site work

# Re-seat a numbered patch series onto a moved upstream base

Goal: carry `patches/NNNN-*.patch` from an old pin onto a much newer upstream, with every patch either applying, ported faithfully, or retired with evidence.

## 1. Survey before touching anything

- `git apply --check` each patch to count rejects; a series that mostly rejects needs `--3way`.
- Record the drift count (commits between pin and new base) and each patch's reject count in a doc. That doc is the worklist.

## 2. Apply in order with three-way merges

- `git apply --3way <patch>`, patch by patch in file-name order, resolving markers before the next patch.
- **Polarity**: in the conflict markers, `ours` is the tree being patched (upstream base) and `theirs` is the incoming patch. Taking "theirs" applies the patch.
- Settings tables and registries: rebuild them by UNION (base rows plus every row the patches add that the file lacks), then verify the count with a grep. Hunk-by-hunk merging silently drops rows.
- Upstream renames bite: an enum value, a function arity or a mode name that moved makes later hunks reject wholesale. Fix call sites as the compiler names them, and re-read the patch's intent rather than the text.

## 3. The host suite is not the gate it looks like

Measured on a 32-patch re-seat: `test-cuda-host` returned 0 while the tree was missing 27 of the series' 47 new files and whole features. Hunk rejections that ADD declarations and files leave every CONSUMER in place, and the tested surface does not compile the consumers.

So, after the merge and before any measurement:

1. **File audit**: every `new file mode` path in the series must exist in the tree. Recover each by applying its `+++` hunk with `git apply --include=<path> <patch>` in patch order (later patches correct earlier ones, including removing orphaned doc comments).
2. **Declaration audit**: for each patch's added declarations, check the tree. Beware two measured flaws: a `pub`-only search counts present-but-private declarations as missing (the port then duplicates members), and widening the pattern over-counts context lines. Treat the audit as a coarse map, never as the verdict.
3. **Compile the other surface**: `compile-cuda-tests`, the image build, the host test binary that imports the checks. That is what names a genuinely missing declaration and its use site, one at a time.

## 4. Port from a tree where the series is whole

- Build the pre-merge reference: a worktree at the OLD pin, apply every patch (they were authored against it, so they apply cleanly). Keep it as a worktree; later sessions need it.
- For each missing declaration, copy the block from that tree. Not from the patch text, which does not tell you what the final form is.
- **One file per gate run.** A bulk append duplicates struct members: block-end detection must treat a single-line member as one line and must count nested braces.
- A declaration that embeds a blob (a fatbin, an embedded file) is two pieces: the const, and the build-step registration that produces it. Only the image build checks the second.
- Membership matters: top-level declarations append at EOF, struct members insert before the enclosing struct's closing brace.

## 5. Compare against the pristine base

- Run the same gate on the pristine base: a base that is green means every remaining failure is yours, and one that is red means it is inherited. Quote both.
- A green claim must name the surface it covers.

## 6. Launching long builds

- Verify a detached launch by the ARTIFACT: the log's mtime against `date` on the box, and the new identity a build prints (a tar sha). A `pkill -f <script name>` matches the launcher's own command line and kills it, so a stale log passes for a running build.
- Rebuild the input tar on the box (extract, overlay one file, re-tar) rather than re-uploading it.

# Re-seat a patch series with a chain of three-way merges (git merge-tree)

Use when the old base and the new base are far apart. A per-patch `git apply --reject` survey is only a lower bound; it cannot relocate hunks. This method merges each patch's own delta onto the new tree built so far.

## 1. Survey (text only)
`git apply --check` then `--reject` per patch in order on a checkout of the new base: counts clean / partial / refused / absorbed. Good for sizing, not for doing the work.

## 2. Build the old series as commits and prove it
Bare repo that shares the upstream clone's objects: `git clone --bare --shared UPSTREAM_CLONE repo.git`. No checkout anywhere.
For each patch i (series order): `GIT_INDEX_FILE=tmp git read-tree T(i-1)`; `git apply --cached --whitespace=nowarn patch`; `git write-tree`; `git commit-tree TREE -p T(i-1)`. T0 is the old base commit.
ORACLE: Tn's tree id must equal the tree id the old series was gated at (a recorded id). If it does not, the series order or a patch is wrong: stop.

## 3. The new chain
N0 = new base commit. For i = 1..n: `git merge-tree --write-tree --messages --merge-base=T(i-1) N(i-1) Ti`. Exit 0: first output line is the tree: `commit-tree` it with parent N(i-1). Exit 1: a tree with conflict markers inside; list paths with `--name-only`; stop at the first conflict and write a conflict folder with the marked files and ours/base/theirs copies of each conflicted path.
Append-only table files (docs rows, registry tables) can use `merge=union` through `$GIT_DIR/info/attributes` (works in a bare repo); the resolver then checks they read sensibly.

## 4. Resolve, amend, replay, emit
- Resolve: write the edited files, refuse any file that still has marker lines (`^(<{7}|={7}|>{7})( |$)`), put the blobs into an index read from the conflicted tree (`hash-object -w`, `update-index --cacheinfo`), `write-tree`, `commit-tree` onto N(i-1).
- Resolve rule per hunk: upstream already does it (absorbed: drop, name the commit, prove from both sides' code), upstream changed neighbouring code (keep upstream's, put ours on top), upstream removed or moved the code (follow it; if the lever no longer makes sense record it as OPEN, never drop silently).
- A compile error that belongs in patch I: amend N(I) (new tree from replaced blobs), then replay N(I+1).. as merge-tree cherry-picks with `--merge-base` = the old parent of each. Earlier hand resolutions survive when the amendment touches other files.
- Emit: `git diff --binary --full-index N(i-1) Ni` behind the old patch's header. A patch whose tree equals its parent's is absorbed (retire it).

## 5. Checkpoints
Compile on a remote host (never on the workstation if that is banned) at package boundaries and every ~6 patches; semantic breaks (renamed APIs, a new upstream rule or scan test) show only there. Read the upstream CI workflow for the touched area and run those steps too; a new upstream scan (for example every GPU kernel body must open with a dependent-launch wait) fails every kernel the patches add although every merge was textually clean.

## 6. Running it with subagent lanes
Put the loop, the resolution rules, the upstream conventions and the checkpoint commands in a BRIEF.md the lane reads; require a decisions-file entry per patch as it is placed. Exactly one lane owns the state files. A lane's 'completed' notice can be interim and the lane may keep writing: before starting a second lane check the state file's mtime, name an owner, keep the other read-only until an explicit HANDOVER (or 10 minutes without writes). Lanes stop at a request budget (about 200-300): ask for a stop at a clean point with the exact next command.

# Re-seat a patch series with a chain of three-way merges

Use when `git apply --reject` surveys (scripts/reseat-survey.sh) show many partial patches against the new upstream ref. Everything is plumbing on a bare repo: no checkout, nothing compiled locally.

## Steps
1. Bare repo sharing upstream's objects: `git clone --bare --shared <upstream clone> work/reseat/repo.git`. Add `info/attributes` with `docs/environment.md merge=union` (a table where both sides append rows).
2. Old chain T0..Tn: for each patch in the series' real application order (engine, then each package dir), `GIT_INDEX_FILE=tmp git read-tree T(i-1)`, `git apply --cached --whitespace=nowarn PATCH`, `git write-tree`, `git commit-tree -p T(i-1)`. ORACLE: the final tree id must equal the id the old series was gated at (here 83a3ea2a5b88a8eade1846f7f779d06bf6d96559); stop if not.
3. New chain: N0 = new upstream commit. For each i: `git merge-tree --write-tree --messages --merge-base=T(i-1) N(i-1) Ti` (exit 0 clean: commit the tree on N(i-1); exit 1 conflicts: stop). On a conflict write the merged tree's conflicted blobs (markers inside) plus ours/base/theirs copies of each conflicted path to a folder, resolve by editing, rebuild the tree with `update-index --cacheinfo` of the edited blobs, commit, continue.
4. A resolved patch whose tree equals its parent's is ABSORBED by upstream: say which upstream commit and which lines show it.
5. Compile fix that belongs in patch I: amend N(I), then replay later commits by merge-tree with base = old N(j-1), ours = new N(j-1), theirs = old N(j) (a cherry-pick without a worktree).
6. Emit patch j as `git diff --binary --full-index N(j-1) Nj` with the old patch header text in front. Keep the OLD patch numbers (leave a retired patch's number vacant) so documents that cite numbers stay valid.
7. Compile and test only on the gate host (scripts/spark-gates.py iter --pin NEWREF --dir work/reseat/out/stack check fmt ctest lean pdl contract test); checkpoint at package boundaries and at least every 6 patches. THE CHECKPOINT MUST INCLUDE `test` (the host test suite): without it a re-seat passed six steps and the full gate still failed 7 tests.
8. Before installing: the FULL gate (spark-gates.py gates --tree base --tree stack=DIR --expect stack=TREEID) must PASS; then rebuild every package's recorded tree id from the installed files with the repo's own apply scripts (not the lane's scratch).

## Pitfalls
- A merge of one patch against bare upstream alone (`indep`) shows modify/delete conflicts for files an earlier patch creates; they are artifacts, judge only the chain.
- Registry rows (platform/environment.zig) and the family env test conflict whenever both sides add rows at one spot; keep both, keep the test's group lists and counts right.
- New upstream conventions bite semantically without textual conflicts (here: every GLM CUDA kernel must open with glm_pdl::enter(); test-glm-pdl-scan; settings only through the registry; lean: single-line comments, files <= 600 lines). A rule that changes how every launch is made also breaks FAKE DRIVERS in tests your patches add (here: cuLaunchKernelEx must be forwarded by each fake, `cuda_pdl.forwardEx(plain)`), and the quick checkpoints without `test` do not see it: each crash is "General protection exception" inside the launch call.
- A merge that takes `ours` for a whole file can silently drop the patch's own import, usage line and dispatch when upstream made the same edit (no marker appears). After resolving a registry/dispatch-table file, diff it against the patch's own added lines.
- A mutant that removes a variable or parameter can fail to BUILD (Zig refuses unused locals and parameters): that is a build error, not a kill; rewrite it to keep what it leaves out in use.
- Delegated lanes log few decisions unless told per patch; ask for DECISIONS.md entries and verify with compile checkpoints and the full gate, never by the lane's word. Two lanes on one state file corrupt it: one owner at a time, handover by message.
- On Windows a python helper's output read in bash keeps a trailing CR (`$(python -c ...)`): strip it (`| tr -d '\r'`) before using it as a sha, or git says "Not a valid object name" and a scanner reads zero files.

Use when a repo's patch series (dozens of numbered .patch files cut against an old upstream pin) must be brought onto a newer base, and the survey already told you most patches apply "partial".

## 1. Measure before merging

`git apply --3way <patch>` needs the patch's blobs reachable from a clone that holds the fork's history. When they are, one pass over the whole series turns a survey's hundreds of rejected hunks into a bounded set of conflict blocks:

```
for f in patches/engine/*.patch; do git -C "$TREE" apply --3way "$f" || echo "$(basename $f) conflicted"; done
```

Then count what is left, per file, before resolving anything:

```
grep -rc '^<<<<<<<' "$TREE" --include=*.zig --include=*.cuh --include=*.md | awk -F: '$2>0'
```

Measured: 114 rejected hunks became 27 blocks in 18 files.

## 2. Know the polarity

In a three-way APPLY the markers mean the opposite of a branch merge: `<<<<<<< ours` is the BASE file as it stands, `>>>>>>> theirs` is the patch being applied. Classify every block first - "ours empty" (take theirs, mechanical) versus both sides populated (a real API merge) - before editing, so the mechanical ones go in one pass.

## 3. A settings table is rebuilt by union, never merged

Row insertions at the same anchor silently vanish: after a clean-looking merge, 25 of the 36 rows the patches add were missing from `platform/environment.zig`. Rebuild instead:

- collect every added row line from the patches (`+    .{ .name = "TF_..." ...`),
- keep the base file's rows,
- insert each collected row whose name the file does not have, before the array's closing brace.

## 4. Restore upstream definitions your replacement deleted

A conflict block can contain upstream's own `pub const X = struct {` opening or a whole helper function. Replacing the block with "theirs" deletes them, and the error surfaces much later (`use of undeclared identifier 'Mla'`). When a block ends mid-struct, re-add the closing `};` and the definition header, and pull the body verbatim from `git show <base>:<path>` rather than retyping it.

## 5. Expect call-site ripples

Merged APIs fail in this order on the gate host: a function gained an argument (pass the base's new one, e.g. a `salt`); a field moved to another struct (a `Set` reads `f.m.<field>`, so the field belongs on `Modules`); a value versus pointer mismatch (`load` returns a value, so the holder stores the value and the consumer takes its address); a helper renamed (`width` became `sparse.width`). Fix one cycle at a time and read the error rather than guessing.

## 6. Close the loop on the gate host

Compile with the repo's own check step (`zig build check-native-cuda-host`, `pr_check`, the family host test), then the named host tests. A brand-new row in a settings table also needs adding to whatever test asserts "every row is listed", or the count fails by exactly one.

## Traps that cost hours

- **A stale `index.lock`** makes `git checkout` refuse and `git apply` write only to a temporary index, so every patch reports "applied" while the working tree never moves. The tell: a clean `git status` at the wrong sha, or an empty `before:` line from a package applier. Remove `.git/index.lock` and re-check out.
- **`git -C DIR <cmd> <relative path>`** resolves the path against DIR, not your cwd - it silently creates worktrees in the wrong place and makes applies read nonexistent files. Pass absolute paths to both the worktree and the patch.

# Restore a partially applied patch series

Use when a numbered patch series was carried onto a newer upstream base with `git apply --3way` and
the result compiles or tests green, but the port may be incomplete. Symptom that starts this: an
image build or a wider compile gate fails on a file or member the host suite never compiles.

## Why a green suite proves nothing here

A three-way merge applies hunk by hunk. Hunks that CREATE a file, or that add a declaration block
whose context drifted, are rejected without failing the whole apply. A host test target that does
not compile that surface stays green while whole features are absent. Measured on a 32-patch series:
host suite green, yet 27 of 47 new files missing and several feature surfaces gone.

## Order of work

1. **Audit new files first.** Parse every patch for `new file mode` and check each path exists in
the tree. Recreate the absent ones in patch order with
   `git apply --include=<path> <patch>` for every patch that carries the file (later patches modify
   what earlier ones create). Re-audit until the count matches.
2. **Build the reference tree.** Worktree the pin the series was authored against, apply every patch
   there. It applies cleanly and is authoritative for what each patch means. Never reconstruct a
   declaration by reading patch text when a whole tree is available.
3. **Port one file at a time**, taking missing declarations from the reference tree, with the wider
   gate after each file. A bulk append duplicated struct members in three files at once.
4. **Classify by placement**: a declaration at column 0 appends at end of file; a struct member is
   inserted before its struct's closing brace (Zig and most languages allow any member order).
5. **Let the compiler pick the work**, not an audit. After each port the gate names the next missing
   symbol and its use site.

- **A `pub`-only audit calls present-but-private declarations missing.** Porting one then duplicates
  the member and the compiler rejects it. Search for the name at any visibility.
- **A widened audit over-counts**, matching declarations a patch only mentions in context lines.
- **Block extraction must brace-count from the declaration line.** A naive scan to the next line that
  is `}` or `};` over-runs a single-line member and duplicates its siblings.
- **Trust the reference tree's SIZE progression.** One file existed at four sizes across the work
  (patch 1 creating it, patches 2 and 3 extending it, a later patch pruning two orphaned comment
  lines). The final form is the one after ALL patches.
- **`pkill -f "<script> <tag>"` kills the SSH command line that runs it**, so a detached build never
  starts and the log stays stale. Launch without pkill, and confirm progress by the log's mtime
  against the box clock.
- **A worktree revert is local only.** A shared gate host keeps whatever was last shipped to it, so
  reset the gate host's copy before reading a gate result.

## Exit condition

The wider gate returns 0 (for a Zig engine: `zig build compile-cuda-tests`, plus the image build for
`.cu`/`.cuh`), the host suite still returns 0, and the file and declaration audits agree with the
reference tree.

# Proving a re-seat is complete, not merely green

A three-way re-seat (`git apply --3way` of a numbered series onto a much newer upstream base) can report success,
compile, and pass the host suite while whole files and whole declarations are missing. This is the procedure that
found 27 of 47 missing files and 42 missing declarations on a series that looked finished.

## 1. Which gate compiles which surface (learn this once per repo)

The failure hides in the gap between gates. On the TensorFold family:

| gate | compiles |
|---|---|
| `zig build test-cuda-host` | host tests only, **no** CUDA kernel surface |
| `zig build compile-cuda-tests` | the CUDA test binary, so `.zig` files under `zig/tests/cuda` |
| the image build | `.cu` / `.cuh` into fatbins, the only gate for kernel sources |

So "the host suite is green" says nothing about kernels. Write the table from the repo's own CI definition before
trusting any green, and never report green without naming which gate produced it.

## 2. Build a reference tree from the pin

The series applied cleanly to the pin it was authored against, so that tree is the authoritative source for every
declaration and every file, with no reinterpretation:

```
git worktree add --detach work/premerge <PIN>
cd work/premerge && for p in patches/engine/*.patch; do git apply "$p" || echo "FAILED $p"; done
```

Keep it in the repo's history so later sessions reuse it instead of re-deriving it.

## 3. Audit new files first

Every `new file mode` in the series must exist in the tree:

```python
for p in sorted(Path("patches/engine").glob("*.patch")):
    text = p.read_text(errors="replace")
    for m in re.finditer(r"^\+\+\+ b/(\S+)$", text, re.M):
        seg = text[max(0, m.start()-400):m.start()]
        if "new file mode" in seg and not (tree / m.group(1)).exists():
            report(p.name, m.group(1))
```

Twenty-seven of forty-seven were absent on a tree that compiled.

## 4. Audit declarations with the definition that has no false positives

Two definitions fail, both measured:

- `pub fn`/`pub const` only: counts a declaration that exists WITHOUT `pub` as missing. Porting it then duplicates
  the member and the gate rejects it.
- `(^|\s)(pub\s+)?(fn|const|var) NAME`: matches locals and context lines, over-counting (170 rows vs the true 42).

Use: a `pub` declaration the patch **adds** (`^\+`) in a `.zig` file, whose NAME is absent from that file at **any**
visibility:

```python
if not re.search(r"\b(fn|const|var) %s\b" % re.escape(name), body): report(...)
```

Then treat that number as a floor, not a proof: the compile gate names what it still cannot see.

## 5. Port per file, with the gate behind each file

- Take each declaration's block from the reference tree: scan from the declaration line, brace-count to depth 0, and
  include the contiguous `///` lines above it.
- Top-level declarations append; struct members insert before the enclosing struct's closing brace (Zig allows any
  member order).
- **Never bulk-append.** One bulk pass duplicated members in three files at once. One file, one gate run.
- The compile gate names private helpers too (`fn`, not `pub`), which no audit lists; port them as they appear.

## 6. Two traps that cost real time

- **`pkill -f "<script> <arg>"` matches the launching shell's own command line** and kills the launcher, so the job
  never starts and the log keeps its old timestamp. Verify a detached job by the log's mtime against the box clock,
  never by a matching process name.
- **Overwriting a tree while a build reads it** produces `cannot open .zig-cache/o/..._zcu.o` or `Skipping to next
  header` from a second `tar` writing the same path. The result is a fake code failure. Use a fresh tar name per
  ship, and wait for the previous job.

## 7. Also check: declarations that were dropped WITH their call site

A patch whose declaration and its only caller were both dropped leaves nothing that references it, so the tree
compiles and the audit (name-based) is the only thing that sees it. `keepsSequence`, the method an open pull request
adds, was absent from the series' own tree this way. A green build is not evidence a feature is present.

# Prove a re-seat is complete, not merely green

A three-way merge of a numbered patch series onto a much newer base reports success per file while silently dropping content. The gates that exist do not all compile the same surface, so a tree can be green on every gate you knew to run and still be missing whole files and declarations.

Measured on GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig, 32 patches onto a base 1,094 commits newer: `test-cuda-host` returned 0 while the series was missing **27 of its 47 new files** and **42 of its added declarations**. Only the image build named them, one gap per run.

## Which gate compiles which surface

| gate | surface | sees missing files/declarations? |
|---|---|---|
| `test-cuda-host` | host tests | no, compiles no CUDA kernel surface |
| `compile-cuda-tests` | the GPU test binary | yes for Zig-side declarations |
| the image build | `.cu` and `.cuh` via nvcc | yes, and it is the only one for kernels |

So after a re-seat: run `compile-cuda-tests`, and build the image before claiming the series is whole.

## Step 1: a reference tree, from the pin

Apply every patch to the base they were authored against (the pin), in a separate worktree. They apply cleanly there, so that tree holds the series' exact intent and is the authoritative source for any declaration's content.

Do not reconstruct content by reading hunks: take the whole declaration.

## Step 2: audit added declarations by NAME

For every patch, for every line it adds that declares `pub fn` / `pub const` / `pub var`, check whether that NAME exists in the target file **at any visibility**.

Two wrong definitions, both measured here:

- `pub`-only: counts a present-but-private declaration as missing, so porting it duplicates a member and the gate rejects it in one round.
- a loose pattern such as `(^|\s)(pub\s+)?(fn|const|var) name`: matches locals and context lines, inflating the true 42 to 170.

The shape that works: `^\+\s*pub (fn|const|var) (NAME)` on the patch side, `\b(fn|const|var) NAME\b` on the file side.

Beware the numerator too: at least one name on the list here (`keepsSequence`) was a method the series' own feature adds, so its absence meant the feature was partly missing from our tree, not only unmerged upstream.

## Step 3: port file by file, gate behind each batch

Append top-level declarations; insert members before the enclosing struct's closing brace (any order is legal in Zig). Detect a block's end by brace counting from the declaration line, and handle the single-line case explicitly, or you will capture the next line and duplicate members.

Expect **private helpers the audit never lists** to surface from the compiler as you go (`qakvRows`, `projectedRows` here). Port them too.

A bulk append across many files at once produced duplicate struct members in three files in a single attempt. Per-file with the gate is faster than a bulk pass plus bisect.

## Two self-inflicted traps, both measured

1. **Installing a reference-tree file over the tree's adapted copy** silently reverts every adaptation the tree had made (here a renamed enum value and two call-argument shapes). Two builds then failed on errors already fixed once. A file from the reference tree is the series' CONTENT, not the tree's; re-apply its adaptations in the same edit.
2. **`pkill -f "build-image.sh reseat"` matches the launching shell's own command line**, so the launcher kills itself and the build never starts; the log keeps its old timestamp. Settle whether a build is running by comparing the log's mtime against the box clock, not by a matching process name.

## Reporting

State the audit's DEFINITION with the number, since three definitions of the same audit gave 70, 170 and 42. A tree is complete when the audit reads zero AND the kernel gate passes, not when the tests are green.

# Port a diverged third-party patch series onto our fork

Use when upstream (a recipe repo, an engine fork) ships a series of patches and our tree has drifted, so patches no longer apply.

## Before touching anything

1. **Establish provenance per patch.** Fetch the upstream catalogue (e.g. `zig/patches/README.md`) and the commit that added each file (`api.github.com/repos/<org>/<repo>/commits?path=<file>`). Record author + PR + licence. Some files are carried from other recipes; the catalogue says so.
2. **Write the manifest first** (`docs/port/upstream-<thing>-series.md`): one row per patch with author, PR and effect. This is the attribution artifact, and it must exist before any file is copied.
3. **Store the upstream files verbatim** under `patches/<series>/sources/` so future upstream changes can be diffed against what we took.

## Applying

4. Clone our fork at the recorded BASE (read it from `engine/BASE`; do not trust docs).
5. Apply **one patch at a time** with `git apply -C1 --reject`, and after EACH patch copy the `.rej` files somewhere safe (`mkdir rej/<n>; cp $(find . -name '*.rej') rej/<n>/`). `git apply --reject` overwrites a file's `.rej` on the next failing patch, so without this the surviving set is only the last failure per file and hunks silently vanish.
6. **Never use `-C0`** for a feature merge: it matches context-free and can place hunks at the wrong location with no warning. `-C1` is the useful compromise (measurably fewer rejects than default).
7. Sort the rejects by area and hand/machine-merge them, keeping the fork's own patches intact. When a hunk is only the upstream base's idiom (`@intFromEnum` vs `@backingInt`, different comments), skip it and say so.

## Packaging back into the repo

8. Concatenate a provenance header (upstream repo, files, authors, PRs, commits, licence, "NOT OUR WORK - DO NOT SUBMIT UPSTREAM AS OURS", plus the exact list of our adaptations) with `git diff` of the merged tree into `patches/<series>/<NNNN>-<name>.patch`.
9. Register it in `patches/<series>/series` and VERIFY: clone a pristine BASE and `git apply --check` the final file (rc 0 required). Note in the series file if one patch subsumes another so nobody applies both.
10. Commit signed, and push the manifest + sources + series patch together.

## Honesty gates before calling it done

- Grep for symbols used but not defined (`for s in ...; do grep -rn "fn $s" ...; done`) - that is how a hidden missing section shows up.
- Record structural divergence explicitly: if our file predates an upstream redesign, say the hunks could not be placed by matching and name the stand-ins.
- State plainly what is unverified. A compile needs the target architecture (e.g. aarch64 GB10 image build, which also takes the GPU lock on those boxes), so a port can be correct-by-inspection and still unproven; never imply otherwise.
