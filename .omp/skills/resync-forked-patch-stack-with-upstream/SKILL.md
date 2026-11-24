---
name: resync-forked-patch-stack-with-upstream
description: "Resyncing a heavily patched fork against a fast-moving upstream (classify which local patches are already upstream, which are superseded, which need porting) using apply tests, not name or signature matching. Use when told to \"get back in sync\" before chasing further work."
---

# Resyncing a forked patch stack against upstream

Trigger: "we need to get back in sync with upstream", "our patches must still apply", or any plan to keep optimising on a base that has drifted.

Chasing work on a stale base is the wrong order. Measure the gap first: the answer is usually far smaller than the patch count suggests.

## 1. Reproduce the upstream base EXACTLY, patch for patch

Never assume the base; prove it. The upstream ship process is the authority for path levels and apply flags:

- Read their build script (`scripts/prepare.sh`, `start*.sh`) for the exact flags: e.g. `patch -p0 --forward` run from a directory whose parent contains the source tree, or applied into `site-packages` after `pip install git+<repo>@<tag>`.
- Rebuild the base on a **pristine** clone of the pinned tag, applying every upstream patch in filename order. Record `ok/fail`.
- Two failures that look like broken patches but are not:
  - **All fail instantly** = wrong `-p` level or a directory prefix mismatch (`src/tensorfold/...` vs `tensorfold/...`). Print ONE real error before changing anything else.
  - **Some fail after a partial run** = the tree was not clean. Start each run with `git checkout -- . && git clean -fdxq`, and verify `git status --short | wc -l` is 0.
- `git apply` is strict (no fuzz) and refuses some upstream-format patches that omit `---`/`+++` lines; GNU `patch --forward --batch` (fuzz 2) is what upstream actually uses. Use their tool.

## 2. Classify local patches by APPLYING them, never by name or text similarity

Apply every local patch to the reproduced base and record one of:

- `ALREADY` - "Reversed (or previously applied)".
- `APPLIED` - hunks land (still only means the text fits; see step 4).
- `PARTIAL/CONFLICT` - needs porting.

Text-signature matching gives false positives: a patch showing ±40-80% coverage can still be the same feature reworked upstream, and a 0% match can be a genuine port target. When in doubt, verify by **symbol**: take a distinctive flag/function name from the local patch and grep the upstream patch set for it. A flag found upstream under a new number means the feature is upstream, reworked - superseded, not lost.

## 3. Watch for the silent losses in the "superseded" bucket

Before retiring a local patch as "replaced by upstream X", read X for the guarantees the local patch added: integrity (fsync, CRC), bounded writes, ordering, error paths. Adopting the replacement must carry them, and replacement headers often say so (and credit the local work). A "superseded" that drops a correctness guarantee is a regression dressed as a sync.

## 4. Expect file-name collisions, not just context conflicts

Both sides often create the same module name for different concepts (e.g. our `cuda/shard.py` = indexer sharding vs upstream's `cuda/shard.py` = KV sharding). Symptom: every hunk rejects on one file. Resolve by renaming one side deliberately and recording the choice; do not "fix" contexts on a file that now means something else.

## 5. Port in value order, one at a time, behind gates

Per ported patch, in order of value not of number:

1. Apply to a fresh base + accepted set; read each `.rej` hunk against the current upstream code.
2. Keep the pre-port tree so the delta can be diffed.
3. Pass the CPU checks first (their `tools/*_check.py`, our `tests/host/*`), then the behavioural gate (a digest/acceptance suite), one patch at a time - a batch port cannot tell you which patch broke the bits.

## 6. Deliverables

- A reproduction script in the repo (patch the base in a container if the host lacks `patch`; a minimal image is enough), so the reconciliation is re-runnable in minutes.
- A committed table: patch -> already upstream / superseded (with what carries its guarantees) / clean / to port, with hunk counts.
- Repo gates run after adding the script (exec bit, docs inventory naming it, lint).
