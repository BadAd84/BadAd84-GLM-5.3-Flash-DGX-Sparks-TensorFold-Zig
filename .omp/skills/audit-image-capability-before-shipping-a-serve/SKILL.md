---
name: audit-image-capability-before-shipping-a-serve
description: "Before shipping a different serve image (or claiming a knob applies), verify each knob's support inside the IMAGE and check shared paths through the container's mounts, not the host's"
---

# Audit image capability before shipping a serve

Shipping a candidate image silently trades capabilities. Two checks settle it in minutes, and both have been got wrong by reading source trees instead.

## 1. Does the image read the knob?

Use the image, not the tree: a built image can lack code the checkout carries.

```
docker run --rm --network none --entrypoint sh <img> -c \
  'for k in TF_GLM_KV_TIER TF_GLM_KV_TIER_GIB TF_GLM_DRAFT_WIDE TF_GLM_POOLED_PACK; do \
     echo "$k: $(grep -rl "$k" /usr/local/lib/python3.12/dist-packages/tensorfold | wc -l)"; done'
```

Run it for the production image and the candidate side by side, and write the table into the report. A harness that refuses an arm with "<img> never reads <KNOB>" is reporting exactly this, and it is usually right about the image and wrong about the tree.

Measured 2026-11-04: production `v110-ots124` read the whole NVMe tier (path plus GIB cap, backlog, min-free guard, 5 files) and neither candidate knob; the hunt images read both knobs and only the tier PATH (no cap, no backlog, no guard). "Ship the candidate" would have dropped the tier's disk guard; "production plus the two knobs" was impossible without a port.

## 2. Does the shared path exist where the code writes?

A serve run in a container sees `/cache` as whatever the container mounts there. Read it from the container's own mounts:

```
docker inspect <container> --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
```

Measured: `/cache` was `~/.cache/tensorfold-glm53/<image hash>`, so a per-run tier folder `/cache/kvtier-<run>` lives at `~/.cache/tensorfold-glm53/*/kvtier-<run>` for EVERY image hash. A wipe aimed at a host `/cache` removed nothing, no error, and the comparison then mixed wiped and unwiped boots.

Wipe it where it lives, for every hash:

```
docker run --rm -v "$HOME/.cache/tensorfold-glm53:/c" --entrypoint sh <img> -c 'rm -rf /c/*/kvtier-<run>'
```

## 3. Prove both, on the box

- Unit-test the env construction offline (cut the function out, stub its neighbours, assert the prod arm keeps its cap with the path rewritten and the other arms get the run path).
- Then watch the live run: boot 1 creates the folder, and it is gone before boot 2 starts. If it survives, the wipe is aimed at the wrong path and every later boot may resume from an earlier boot's state, which is unequal work and invalidates the timings.

## 4. Write down the trade before shipping

A shipping line names the image, the knobs it honours, and the capability it gives up. "Candidate plus knobs" is not a plan when the image does not read them.
