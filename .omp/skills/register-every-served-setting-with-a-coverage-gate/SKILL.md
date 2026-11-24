---
name: register-every-served-setting-with-a-coverage-gate
description: "Use when a serve's env must cover every setting the engine reads with an EXPLICIT value (no setting unset; the engine default written down counts, a note does not): build the worklist from the engine's read sites, gate on absence, and treat a missing setting as a hard stop at every rebase."
---

# Register every setting the served engine reads

An env file listing only measured gains silently inherits every other default the base carries. A newer base can add a default-on clause that exists in no env file at all, and its cost then reads as an "engine difference" while nobody can see it.

## What to build, in the serve repo

1. **The authoritative list is the engine's own settings table** (for TensorFold: `zig/src/platform/environment.zig`, one row per setting with `name`, `scope`, `kind`, `forms`). Parse it field by field: a row carrying an optional field (`trim`, `no_word`) is invisible to a whole-row regex, and that blind spot once read 31 of 82 rows as if they were all.
2. **Measure coverage against the tree the SERVE runs, not a working clone.** The image's `tf.tree.manifest` label gives the tree id; reproduce it from a manifest of the source you think served. A green register against a 13,001-entry series tree while the image serves a 12,622-entry tree hid 17 missing settings.
3. **Every in-scope setting is SET in the env, explicitly.** The engine's own default written out counts; a note in a register does not, because the boot honours whatever the base chose. A missing setting is a hard stop at the rebase that introduced it.
4. **Verdicts are annotations, not satisfaction:** carried (with a measurement), default-ok (the engine's own value, with its read site), debt (counted, a lead), unreachable (with the reason). The gate fails on absence, on a note-only setting, on a worklist line not moved into the env, and (strict) on a name the served tree does not read.

## The absence trap, measured

A bare `export NAME` is neither presence nor absence, and it cannot clear an image-baked `ENV`. Where the launcher builds the container env by iterating the shell's exported names and passing `-e "$name=${!name}"`, a name the shell never sets generates no `-e` at all, so the image's value passes through; a name the shell sets to empty passes an empty string, which a presence test still sees as present. The honest forms are `unset NAME` (real absence, and the image's value then passes through, so absence still requires an image that does not bake it) and `export NAME=value` (an override). Gate all of it: `NO-VALUE`, `IMAGE-BAKED`, `DUPLICATE`, and `PASSAGE-LOST` for a name the launcher filter never forwards.

## A refresh script, run at every re-seat

Keep existing verdicts verbatim and append a worklist line for each new table row, with the literal default from the engine's `read(T, "NAME", default)` site and the file it came from. A new upstream knob then lands as a visible entry or a failing check, never as a silent default. Classify by reading the read site, not the name: diagnostics, capacity floors and other-family paths cannot move a round and settle without an arm.

## Rules that keep it honest

- Debt is counted and printed on every run; it is not permission, and the count should fall.
- A verdict line cites a `work/` or `docs/` evidence path; an uncited verdict fails like an uncited export.
- A setting the served tree cannot read is the same class of defect as a tier flag that silently does nothing.

## Measured case

Upstream's `shared_stop = 0.6` (TensorFold `cuda_lanes_draft.zig:26`, 2026-11-10) limited greedy drafting beside another stream, appeared in no env file, and did not exist in the older production engine, so an unset switch cost 7 to 11 percent at two to eight streams and 54 percent of a prose-throughput gap for two days. The first complete env boot then found the two follow-on traps above: a wrong-tree measurement and an image-baked `TENSORFOLD_CUDA_KERNELS` that defeated a valueless export and refused fp8 KV at boot.
