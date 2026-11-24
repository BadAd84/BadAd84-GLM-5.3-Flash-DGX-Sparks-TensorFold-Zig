---
name: verify-image-against-upstream-recipe
description: "Verify what a served docker image actually contains against the MiaAI recipe baseline, attribute every file difference to a patch, and dry-run a candidate patch inside the image."
---

# Verify a served image against the upstream recipe, and test whether a patch applies to it

Use when you must state what a served image actually is, or whether a patch applies to it: comparisons, port
estimates, "does our stack equal upstream" claims. Never answer either from trees we happen to have on the box.

## 1. Get the right baseline, not the bare engine

The MiaAI recipe applies its `patches/*.patch` with `patch -p0 --forward` against SITE-PACKAGES, and its patches add
files (e.g. `dflash2_multi.py`) that do not exist in the engine tag at all. So the baseline is: engine tag +
recipe patches at the matching recipe commit.

- engine: `git clone https://github.com/ashhart/TensorFold.git`, `git checkout v0.6.0`
- recipe commit for a version: `git -C <recipe> log --oneline -S "<version>" -- CHANGELOG.md` (v1.10 = 684ce9b, 96
  patches; tip bf5f945 has 123)
- assemble: `git -C <recipe> archive <sha> | tar -x -C <dir>`; `cp -r tf/src/tensorfold <base>/tensorfold`; then
  `for p in <dir>/patches/*.patch; do patch -p0 --forward --silent < "$p"; done` inside `<base>`. Expect 0 failures.

Do this in WSL/Linux, never on a Windows checkout: files come back CRLF and every hunk reports "different line
endings" (that failure is the checkout, not the patch).

## 2. Extract the served tree and diff

```
docker run --rm -v ~/upcmp:/out --entrypoint sh <image> -c 'cp -r /usr/local/lib/python3.12/dist-packages/tensorfold /out/prod'
tar -C ~/upcmp -czf ~/upcmp/prod.tgz prod     # then copy to the analysis host
diff -rq -x __pycache__ -x '*.orig' <base>/tensorfold <prod>/prod
```

`*.orig` files are `patch` backups inside the baked image; `__pycache__` is noise. Report three lists: modified,
only-in-image (our additions), only-in-base (anything we are missing).

## 3. Attribute every difference, or say so

```
for f in <each differing/added path>; do grep -l "tensorfold/$f" scripts/glm53/v110/ots*.patch; done
```

Any file with no hit is unexplained drift and must be reported as such, not glossed. Then count distinct patches that
cover the set, because the applied-patch count in the docs drifts (49 vs the 21 a doc claimed).

## 4. Testing whether a patch applies to the image

Do it inside the image, where the tree is LF and complete:

```
docker run --rm -v ~/patches:/p:ro --entrypoint sh <image> -c \
  'cd /usr/local/lib/python3.12/dist-packages && patch -p0 --dry-run --forward < /p/x.patch'
```

Read the hunk lines: "H x FAILED" plus offsets is the answer. A patch cut against a synced base will often apply to
the recipe base and NOT to production, because the same upstream changes landed there in a different order; that is a
rebase, so quote the failing hunks rather than saying "does not apply".

## 5. Then state the comparison honestly

If production is pinned to an older recipe version than the tip, the gap is upstream patches, not our work: say which
baseline each claim uses (`v1.10` 684ce9b or the tip) and quote both shas in any receipt.
