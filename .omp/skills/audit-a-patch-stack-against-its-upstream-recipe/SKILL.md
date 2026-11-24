---
name: audit-a-patch-stack-against-its-upstream-recipe
description: "Prove what a tuned image actually is: rebuild the upstream recipe's reference tree at its pinned version, classify every local patch as applied/absorbed/retired, and diff the image's installed tree against the reference. Use when asked whether a production image matches upstream, or before rebasing a patch stack onto a newer upstream tip."
---

# Audit a tuned image's patch stack against its upstream recipe

Answers "is this image really upstream plus our patches, and which of our patches does upstream now do itself?" with content, not with claims.

## 1. Build the reference tree for the version the image is pinned to

Find the pin first; a moving tip is the wrong baseline.

```
# recipe repo (patch series + start scripts, no engine source)
git clone <recipe-repo> recipe && git -C recipe log --oneline -1
grep -nE 'TF_VERSION=\$\{TF_VERSION' recipe/scripts/config.sh      # engine version, e.g. v0.6.0
# the recipe has no tags: its version lives in CHANGELOG.md, so find the commit
grep -nE '^## v?[0-9]+\.[0-9]+' recipe/CHANGELOG.md | head
git -C recipe log --oneline -S '<version>' -- CHANGELOG.md | head
```

Then assemble: engine source at that version, with the recipe's patches applied with the recipe's own rule
(`prepare.sh`: `patch -p0` against site-packages, so the tree root must contain `tensorfold/`).

```
mkdir base && cp -r engine/src/tensorfold base/tensorfold
cd base && for p in recipe/patches/*.patch; do patch -p0 --forward --silent < "$p" || echo "FAIL $p"; done
```

All patches applying cleanly is the sanity check that the pin is right.

## 2. Extract the tree the image actually runs

```
docker run --rm -v $PWD/out:/out --entrypoint sh <image> -c \
  'cp -r /usr/local/lib/python3.12/dist-packages/tensorfold /out/prod'
tar -C out -czf prod.tgz prod          # 4 MB, cheap to move
```

## 3. Classify the differences

```
diff -rq -x '__pycache__' -x '*.orig' base/tensorfold out/prod            # files differing / added / absent
# map every differing file back to a patch
while read -r f; do grep -l "tensorfold/$f" local/*.patch || echo "UNEXPLAINED $f"; done < differing.txt
```

A clean audit has zero unexplained files. Absent files are usually READMEs dropped by the image build; say so rather than calling it drift.

## 4. Deciding what a rebase carries

If the project keeps an account file mapping each local patch to its fate, that file beats re-deriving anything: read it and report counts per kind (already upstream / ported / retired / undecided). Two traps this catches:

- a patch that "fails to apply" to the new base is often **absorbed upstream**, not broken;
- a patch may be **retired on purpose** because upstream replaced the mechanism (ours: a bespoke disk KV tier retired for upstream's `--spill-gib` spill tier), which changes what a behavioural comparison is measuring.

## Traps that cost real time

- **Never build the reference from a Windows git clone.** CRLF in the checkout makes `patch` fail with "different line endings" for dozens of patches at once, and `git checkout`/`reset --hard` will not rewrite them once the files are considered unchanged. Do the assembly in WSL/Linux, or clone with `core.autocrlf=false` into a fresh path.
- **Path prefixes vary per patch**: `a/`+`b/` needs `-p1`, a bare `tensorfold/...` diff needs `-p0`, and a diff rooted at the package (`cuda/foo.py`) needs `-p0 --directory=tensorfold`. A "No such file or directory" error is a prefix problem until proven otherwise.
- **`*.orig` files** are patch backups, not content; exclude them and `__pycache__` from every diff or the counts are noise.
- **Test applyability inside the real image** (`docker run ... patch -p0 --dry-run`) when the question is "does this apply to what we run"; the local clone may differ by build steps.
