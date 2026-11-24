---
name: port-knob-patches-onto-rebased-recipe
description: "When our serve knobs or lane patches must be carried onto a moved upstream recipe: establish series order, resolve rejects in parallel lanes, verify against the running image, distribute the image to every rank, then gate digests before timings."
---

# Port knob or lane patches onto a moved upstream recipe

Use when production is pinned to an older recipe and the work we want to keep lives as lane patches against a newer
base. Measured on the GLM serve, 2026-11-04, where the rebased base was the current recipe plus the ports that survived a
sync, and two knobs had to ride on top of it.

## Before touching a patch

1. Find the disposition of every production patch first. A sync account file that classifies each one as already upstream
   / ported / retired / later turns a 46-of-49 conflict wall into a short worklist, and prevents porting something upstream
   has already absorbed.
2. Check whether the later patch of a series assumes the earlier one. Applying the last patch alone inflated conflicts from
   18 to 34 hunks and pointed lanes at functions that did not exist on that tree.

## Resolving

3. Apply the patches with `patch -p0` against a tree whose root holds the package (`tensorfold/...`), which is the
   recipe's own convention, and keep the `.rej` files: they carry the intent for each failed hunk.
4. Give each lane exclusive ownership of files, never a shared tree, and tell it what to verify (`py_compile` for Python;
   for `.cu`, that every template parameter, constant and instantiation is present and that kernel and launcher argument
   lists agree positionally).
5. When a target function genuinely does not exist on the base, say so and realise the hunk's intent at the nearest live
   call site rather than inventing the function.

## Verifying a port (do this before any build)

6. Use the running image as the reference port: extract the file from that image and check every line the port adds that
   references the knob appears verbatim there. Faithful beats plausible; a hand-written diff that reads correctly can still
   be a rewrite.
7. Round-trip the finished patch: apply it to a fresh copy of the base, expect zero fuzz, and diff the result against the
   tree it came from. Both must be identical.

## Building and gating

8. Build the derived image by applying the patch inside the base image and committing, then check the module actually
   imports. Build it on EVERY rank: a serve with `PREPARE=0` refuses when the image is missing on any worker.
9. Gate replies before timings. Boot the same image with the feature off, at each variant, and at the shipped setting, and
   compare greedy digests. A layout change that moves a token is a defect, not a trade.
10. Measure the rebase separately from the work it carries: production against the rebased base, then the base against the
   candidate. Do not attribute a gain to newer upstream without that first cell; here it was neutral.

## Harness traps that cost time

- The level argument is a LIST of levels, each mirrored per arm, so `4 4 1 1` is sixteen boots with two arms, not three.
  A single level with `once` gives exactly one boot per arm, which is what a gate wants.
- An arm's env only reaches an image that reads it. Check the tree for the variable name before setting it; our disk tier
  was retired on the newer base and setting its variable there measured nothing.
