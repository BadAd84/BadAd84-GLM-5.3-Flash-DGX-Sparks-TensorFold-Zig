---
name: check-a-patch-against-a-served-image
description: "Use when asked whether a patch applies to a served model image (our recipe stack, a hunt image, production), before any rebase or port claim."
---

# Check a patch against the image that serves

Answers "does this patch apply to <serve>?" in one command, inside the image, without touching a working tree.

## Why not git apply on a clone

- The MiaAI-Lab recipe repo carries `patches/` and start scripts, not the engine source, so a clone of it has no files to
  patch. Its `scripts/prepare.sh` applies `patches/*.patch` with `patch -p0 --forward` against site-packages, which means a
  recipe-compatible patch is rooted at `tensorfold/...`.
- A Windows git clone materialises sources with CRLF while the patches are LF, so every hunk reports "different line endings".
  That reads exactly like a version conflict and is not one. Cost: an hour chasing the wrong cause.
- Pinning a tag is only right if the tag matches what the recipe is assembled on; the recipe adds files of its own
  (`dflash2_multi.py` arrives in patch 0027), so the bare engine tag lacks targets the patch expects.

## Procedure

1. Copy the patch files to the box (`scp` them into `~/upcheck-patches`).
2. Dry run inside the image, site-packages as the working directory, patches mounted read-only:

```
docker run --rm -v /home/adam/upcheck-patches:/p:ro --entrypoint sh tensorfold-glm53:v110-ots124 \
  -c 'cd /usr/local/lib/python3.12/dist-packages && for f in /p/*.patch; do echo "== $(basename $f)"; \
      patch -p0 --dry-run --forward < $f 2>&1 | grep -E "FAILED|checking file|Hunk #.*succeeded" | head -6; done'
```

3. Read the result per hunk: a patch whose hunks all succeed, even at an offset, is portable with a refresh; any FAILED
   hunk means the target text differs and the patch needs a rebase onto that tree, not a fresh `-p` value.

## Report the shape, not a verdict word

Give the hunks (`5 hunks, 3 fail at 135/447/459`), the files, and the offsets. A one-word "no" hides whether the port is
three hunks of rebase or a rewrite.

## Measured

2026-11-04, our two candidate knobs against `tensorfold-glm53:v110-ots124`: `DrafterBuckets-1-draft-wide` fails 3 of 5 hunks
in `dflash2_multi.py`, `PooledKeys-1-packed-pooled-keys` fails 1 of 3 in `geometry.py` with the rest at offsets -8 and -13.
Both were cut against the hunt stack, so the same upstream changes exist in a different textual order.
