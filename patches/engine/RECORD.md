# RECORD.md - patches/engine

What it is: the recipe's engine patch stack, applied in file-name order by `scripts/apply.sh` to a pristine
checkout of the pinned upstream engine. Nothing in the engine tree is edited outside these files.

Base: `ashhart/TensorFold` at `9c9bf542cc87ec21f44cee720fc4f1c056f8c905` (`v1.2.4-242`, `scripts/config.sh` `TF_REF`).

| patches | source | edited by us |
|---|---|---|
| 0001-0031 | our fork `ai-engine` (OTS Gitea), the commit range each patch's header names, ported onto the pin | yes: hand-ported, squashed a patch |
| 0032-0039 | written here: build and correctness repairs of the port (each header names the patch it repairs and its receipt) | ours |
| 0040 | written here: restores the pin's own lines that 0003 replaced | ours |
| 0041 | written here: restores the pin's lines, or the fork's where the pin has no such code, found by `docs/PATCH-AUDIT.md` | ours |

Proof the stack rebuilds: a clone of the pin with every patch applied in order by `git apply` gives a tree with 0
paths differing from the working tree the patches were cut from (checked 2026-11-11).

Hashes: `SHA256SUMS`, one line a patch, checked by `scripts/check-patch-packages.sh`.
