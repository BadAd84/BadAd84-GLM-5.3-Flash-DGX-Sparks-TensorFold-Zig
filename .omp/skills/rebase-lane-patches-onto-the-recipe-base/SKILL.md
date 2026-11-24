---
name: rebase-lane-patches-onto-the-recipe-base
description: "Port our lane patches onto a fresh upstream TensorFold/MiaAI recipe base and prove the port is faithful, when patches conflict because the base moved or because a shipped image already contains a different revision."
---

# Rebase lane patches onto the recipe base, and prove it

Use when a patch we carry no longer applies (base moved, or a shipped image carries a different revision), or when asked whether our patches apply upstream.

## 1. Build the real base, never the bare engine tag

The MiaAI recipe repo holds no engine source: `patches/*.patch` are applied with `patch -p0` against site-packages paths of the form `tensorfold/...`, and several files (e.g. `families/glm5_next/cuda/dflash2_multi.py`) exist only *after* the recipe's own patches. So:

```
# in WSL (Linux line endings), never a Windows clone
git clone https://github.com/ashhart/TensorFold.git tf && git -C tf checkout v0.6.0
cp -r tf/src/tensorfold base/tensorfold
cd base && for p in <recipe>/patches/*.patch; do patch -p0 --forward < "$p"; done
```

The recipe has no tags: a version is a commit (v1.10 = 684ce9b, 96 patches; bf5f945 tip = 123). Confirm every patch applies (`applied 96, failed 0`); a nonzero count means the tag is not the base.

## 2. Apply the ports in their recorded order

`sync/ORDER` is authoritative: it encodes real dependencies (expert-rotate's anchor is a line shard-agreement adds). Apply every entry, then the lane patches you are porting.

## 3. Resolve conflicts by re-anchoring, not by fuzz

`patch --fuzz` will place a hunk in a plausible spot and change behaviour silently. Instead take the `.rej`, decide per hunk whether it is an insertion (re-anchor on a stable nearby line, add `import os` or any other missing preamble), a docstring change, or a real semantic merge.

## 4. Prove the port against the shipped image

The built image already contains the correctly ported file. Compare line by line: every non-comment line you introduced that references the knob must exist verbatim in the image's copy.

```
docker run --rm -v /out --entrypoint sh <img> -c 'cp families/glm5_next/cuda/x.py /out/'
# then: added = lines mentioning the knob; missing = [l for l in added if l.strip() not in image_copy]
```

Zero missing is the bar. A nonzero number usually means you ported the wrong patch revision: check what the env var actually needs (`POOLED_PACK=2` is the scales-plane revision, not the earlier one).

## 5. Publish the result as a patch against that base

`diff -u` the ported tree against the base and store it with a README that states, per file, what applied and what did not, plus the gates still owed (bit-exactness with the knob off, 0/1/2 settings, then the five-level speed run).

## Pitfalls that cost real time

- A Windows `git clone` materialises CRLF and every patch then fails with "different line endings"; `core.autocrlf=false` plus `git rm -r --cached . && git reset --hard` did not fix it here. Do the work in WSL/home.
- Patch paths are mixed: some use `--- tensorfold/...`, others `--- b/tensorfold/...`, so the strip level differs per patch. Read the header before applying.
- One logical change can be several patches; the older revision may be the one lying around. Check the env value the candidate sets before choosing.
