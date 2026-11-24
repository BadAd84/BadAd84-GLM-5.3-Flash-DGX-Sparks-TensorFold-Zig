---
name: sync-downstream-patches-onto-moved-upstream
description: "Use when a downstream patch stack must be re-based onto an upstream that has moved (recipe/serve forks): reconcile by content, port only what is missing, and prove it end to end."
---

# Syncing a downstream patch stack onto a moved upstream

When upstream has moved far ahead (e.g. 123 patches against our 49) do NOT rebase patch by patch blindly. Reconcile
first, then port only the residue, then prove it end to end.

## 1. Reconcile by CONTENT, not by name

- Get the upstream set and the downstream set side by side. For each downstream patch, take its distinctive added
  lines (long, identifier-ish, not boilerplate) and test whether upstream's patches contain them. Coverage >= 40%
  means "already upstream"; low coverage plus a name match means the same feature reworked.
- Confirm the suspicious ones by symbol, never by credits: grep upstream for the flags/functions the patch introduces
  (`TF_GLM_*`, a function name). That is what settled 18 of ours as already present and 2 as no-ops.
- Buckets: already upstream (drop), superseded by an upstream replacement (drop, but check the replacement keeps the
  guarantees you added - grep it for fsync/CRC/isolation), ours-only (port), obsolete (drop).

## 2. Build the base mechanically, and prove the base itself

- Clone the pinned tag, then apply upstream's patches in order with `patch -p0 --forward` (upstream's own method) in a
  container if the host lacks `patch`. A fresh tree must give N/N applied, or the base is not reproducible.
- Path levels bite: upstream patch headers carry `tensorfold/...` while a source clone may keep it under `src/`. The
  first 100-failure run is a path-level error, not a patch error - print ONE real error before guessing.
- Clone into a UNIQUE directory per run. Container-written `__pycache__` is root-owned, `rm -rf` silently fails, and a
  reused tree makes `patch --forward` report every hunk as already applied (this produced 65 and then 124 spurious
  failures in one session).

## 3. Port the residue, one patch at a time, with three checks per hunk class

- For each rejected hunk ask, in this order: (a) already landed via another hunk of the same patch (duplicate), (b) the
  helper it needs already landed and only the call site is missing, (c) the target code moved or vanished (re-target it).
- RENAME COLLISIONS are the dangerous class. If downstream and upstream both own a module name (ours `cuda/shard.py`
  for the indexer, theirs for KV sharding), rename OURS and update every reference. A sed that only rewrites lines
  STARTING with `mod.` misses indented call sites - one survived into a built image and crashed on the first request
  with `AttributeError: module 'shard' has no attribute 'prefill_on'`.
- After each port run an ORPHAN check: every symbol the new code calls must have a definition somewhere in the tree
  (a half-applied hunk left a call to `_Signer`, which existed nowhere). Parameterise the checker by tree path.
- Record the apply ORDER in a file (e.g. `sync/ORDER`) and make both the build and the check read it - alphabetical
  globbing breaks real dependencies (patch A anchors on a line patch B adds).

## 4. Prove, then build, then measure

- End-to-end proof: pristine tag -> upstream patches -> downstream patches in ORDER -> `py_compile` EVERY python file
  -> the rename/orphan gates. Exit 0 or it is not synced.
- Keep ported patches OUT of any directory a build globs (`patches/ots[0-9]*.patch`), or the build picks up half-finished
  work; a subdir like `sync/` avoids it.
- Build the image from a LOCAL source checkout (`COPY tfsrc`, `pip install /opt/tf-src`), not `git+https`: an in-container
  clone died after 505 s with a TLS recv error and looked like a dependency failure.
- Assert the image before measuring anything: `docker inspect -f '{{.Config.Image}}' <container>` AND a content marker
  the new engine must show (e.g. upstream's `spill` fields and NO old `kv_tier_*` keys). A health read taken after a
  restore describes the RESTORED serve - that misattribution happened once and looked like a passing test.
- After a FRESH BOOT, time with reps >= 2: the first request pays first-use kernel compilation, and a one-rep comparison
  invented a -23% regression that ABBA showed to be -1.4%.

## 5. Swap discipline on a live box

- A swap script must be REPLAYABLE, not trap-dependent: write a marker file, and restore FIRST if it exists. A killed
  job skipped `trap restore EXIT` and left production down.
- Prefer launching the candidate by sourcing its env and running the recipe's start script from its own checkout, so the
  production launcher and `~/v110.env` symlink are never edited.
- Restore and verify at the end (`image + health 200`), and put every artifact (image, checkout, scratch trees, /tmp
  copies) in each box's `INVENTORY.md` in the same action, with removal commands.
