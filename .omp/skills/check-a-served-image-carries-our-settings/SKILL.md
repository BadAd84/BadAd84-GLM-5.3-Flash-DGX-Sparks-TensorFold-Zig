---
name: check-a-served-image-carries-our-settings
description: "Use at every promotion or rebase: prove every setting in our env files still exists in the engine binary we serve, by comparing the served binary's own strings, and put each launcher flag through the parser rather than --help."
---

# Prove an env setting still exists in the engine we actually serve

Use at every promotion, and after every rebase. A setting our env file sets that the engine no longer has is **silently
ignored**: the serve runs without it while the env says it is on, so the cells describe a serve nobody ships.

## The two oracles, and the one that lies

**Env rows: the served binary's own strings.** The settings table of `platform/environment.zig` is compiled into the
binary, so the image is the oracle - not a local tree, which may predate the image or be missing packages.

```bash
docker run --rm --entrypoint sh IMAGE -c 'strings /opt/tensorfold/native/bin/tensorfold-native' \
  | grep -oE '^(TF|TENSORFOLD)_[A-Z0-9_]+$' | sort -u > image-env.txt
python scripts/check-env-in-image.py --image-names image-env.txt --env scripts/env/prod.env --env scripts/env/dev.env
```

**Launcher flags: the parser, never `--help`.** A flag can be accepted and still be absent from the help text:
`--kv-cache` is accepted by the engine and does not appear in `serve --help` at all. Put the flag through the parser with
a deliberately incomplete command line and read the error:

- `unrecognized arguments: --flag` - gone, retire it.
- `error: the following arguments are required: model` - accepted, keep it.

## Reading the findings

Filter to `TF_*` and `TENSORFOLD_*`; the engine never reads `NCCL_*`, `HF_*` or other library variables and the container
must carry them, so they are not findings.

Every remaining finding is one of three classes, and they are told apart by evidence, not by shape:

1. **A package the image does not carry.** The env sets a switch whose patch is not in the image. Real, and the reason a
   dev image must be the union of everything that won rather than one package at a time.
2. **A row the engine dropped.** Real. Retire the line from both env files and the register in the commit that removes
   it, and record which upstream commit absorbed it if one did.
3. **An extraction artifact.** Names can be stored in a form `strings` misses: cross-check against
   `tensorfold-native capabilities --json`, which lists the dynamic settings the engine honours (it names
   `TENSORFOLD_PARALLEL`, for example). A name the capabilities output honours is not missing.

## Reconcile against the tree as well

The image check answers "does the engine have it". The coverage gate answers "is every row of the table set and
recorded", against the tree the image was built from, and it is the detector for `STALE` register lines.

```bash
python scripts/env/check-env-coverage.py --table <tree>/zig/src/platform/environment.zig \
  --prod scripts/env/prod.env --dev scripts/env/dev.env --register scripts/env/register.env --scopes glm,cuda,common
```

Order matters when you rebuild that tree: patch packages do not apply in arbitrary sequence - `port-multi-fill` refuses
on top of `pr1411` - so apply them in the manifest's order and rebuild clean rather than stacking onto a tree that
already carries another package.

## Report

State the count checked, the count missing, and each missing name with its class. "Eight of 107 absent, of which two are
a package this image lacks, two are extraction artifacts and four need a row-by-row look" is a usable result; "the env is
clean" is not.
