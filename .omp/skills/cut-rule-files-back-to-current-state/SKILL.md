---
name: cut-rule-files-back-to-current-state
description: "Use when rule files have expired, superseded or box-specific content and must be cut back to current state: what to delete in what order, how to verify against live state, and how to prove the edit."
---

# Bringing rule files to current state

Use when the owner says a rule file has superseded or out-of-date content and wants only the current state.

## Delete in this order

1. **Expired future obligations.** A clause that promises a measurement on a date ("on ~1 Nov compute the usage/price and compare", "revisit after the experiment") is not a rule once the date passes. Delete it and keep whatever decision it produced.
2. **Exceptions superseded by a later directive.** Delete the exception and leave ONE sentence at the surviving rule naming which directive superseded it, so a reader cannot find both and pick.
3. **Box narratives.** Image tags, patch counts, launcher names, "production is TP=2 on spark4/5" - these age within days. Replace with the invariants that do not age (addresses, MACs, subnets, GID indices, ports, the concurrent-access rule) plus a pointer: the owning repo's `AGENTS.md` and each box's `~/INVENTORY.md` hold the volatile part.
4. **Enumerable scope lists.** "Applies to GLM on spark1-3, Qwen on spark4/spark6" drifts. Rewrite as "applies to every serve, on whichever box, whatever the model".

## Verify before deleting

The file's age is not evidence. Read the live state: `pct list` on the Proxmox host, `docker ps` per Spark, `systemctl list-units` inside a CT. Today's audit found a guest list missing three containers that exist, and one apparently-stale claim (Omnigent removed from CT106) that was in fact correct.

## Prove the edit

After the edits: `grep -c` for every removed marker (must be 0), and a line/section count per file to show nothing was truncated. Then re-read the section where a new cross-reference was added, to confirm the thing it points at is on the right side of it.

## Two rules, one subject

When a correction lands in one rule file and the same subject already lives in another, do not duplicate the wording: put the mechanical form where it is enforced (e.g. the fleet `AGENTS.md`) and a pointer from the narrative that motivated it. A duplicated rule will diverge.
