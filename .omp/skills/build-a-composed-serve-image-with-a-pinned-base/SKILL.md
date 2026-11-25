---
name: build-a-composed-serve-image-with-a-pinned-base
description: "Use when an image build applies two patch sets that are cut against different bases (a recipe's set plus ours) and fails in the patch loop: pin the base the series expects, skip the set that does not belong, and read the failing layer via a debug RUN instead of relaunching."
---

# Building a composed serve image when two patch sets disagree about the base

The situation: `~/work/zbuild/build.sh TAG [PATCH...]` builds a TensorFold image from a recipe clone plus
the given OTS patches. It sources `~/qwen-zig/scripts/config.sh`, whose `TF_REF` is the **recipe's** base
(e.g. `eab85828`, its comment says v1.1.4), and its Dockerfile applies the recipe's `patches/*.patch` and
then your patches to that one tree. Our series was cut against a different base (`1ece6e6d`).

## What fails, and what it means

`git apply` in the recipe loop fails on a text file with "patch does not apply". Six distinct causes each
produce that identical message, and four of them cost a launch each to tell apart:

1. **The tree is not your base.** The build arg `TF_REF` is passed to `docker build`, but a `config.sh`
   that assigns `TF_REF="${TF_REF:-...}"` and is *sourced* inside a script whose `docker build` runs in the
   same shell is not the issue; the issue is that the value you exported before `bash build.sh` is what the
   Dockerfile receives, and if only the config's default was changed the fetch still takes the default.
   **Verify the tree inside the layer, not outside**: add a debug `RUN` that prints `git rev-parse HEAD`
   immediately before the apply loop. A debug stage that prints `eab85828` while you patch `1ece6e6d` is
   the whole answer, and no amount of reproducing the apply outside can show it.
2. **The context file is one you already modified.** Generating the no-op/patch from a copy that already
   carries your edit (appended comment) makes its context your edit, and the target tree does not have it.
   Check with `git hash-object file` against the blob the remote tree holds.
3. **The patch directory's glob does not match.** `set -euo pipefail` plus `cp .../patches/*.patch` exits
   when the directory is empty. An empty-patch *file* is not a fix: `git apply` refuses it ("No valid
   patches in input") and the recipe loop's `|| exit 1` kills the build. Use a real one-line patch.
4. **A stale blend of two attempts.** Writing a placeholder twice by different methods (script, then
   heredoc) leaves a file that is the concatenation. Read it back with `cat -A` and check its byte count
   before launching; a six-line patch is ~190 bytes, not 400.
5. **Line endings.** A sums/patch file written through a tool that forces CRLF fails a `$`-anchored grep
   and some apply paths. Pin `*.patch eol=lf` if the repo has a `.gitattributes` policy.
6. **`--3way` needs the files in the index.** Applying a patch three-way into a tree built by plain
   `git apply` fails with "does not exist in index" until you `git add -- <the patch's own paths>`.

## The method that works

1. Pin the base the series expects in the config the build sources (an explicit edit to `scripts/config.sh`
   in your own clone, not an exported variable), and confirm with a debug `RUN` that prints `git rev-parse
   HEAD` before the loop.
2. Skip the set that does not belong by pointing the script's recipe-clone path at your own directory and
   giving it exactly one real one-line patch (a comment appended to a file the build never serves).
3. Read the failing layer rather than relaunching: the debug `RUN` output names the tree, the patch
   directory's contents and the exact file that refused. Eight launches were spent learning a fact one
   debug stage prints in twelve seconds.
4. Prove the artifact carries the lever afterwards: `strings /opt/tensorfold/bin/tensorfold | grep -c
   <SETTING_NAME>` inside the built image, because a series that applies to a tree is not the same claim
   as a binary that reads the new row.

## When not to fight it

If the recipe's own patch set and yours genuinely target two unrelated trees (`git merge-base
--is-ancestor ours theirs` says no, and your patches fail on theirs both plain and `--3way`), then no
base pinning fixes the build: either build without the recipe's set (this repo's series is complete
against its own base) or freshly re-cut your series onto the recipe's tree. That measurement, not more
launches, is what picks the route.
