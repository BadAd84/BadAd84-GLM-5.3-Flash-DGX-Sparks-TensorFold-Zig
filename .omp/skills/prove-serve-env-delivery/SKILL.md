---
name: prove-serve-env-delivery
description: "Prove a model serve's environment of record is deliverable: launcher forward filter, boot-and-diff, unset semantics, and the production-image guard."
---

# Prove a serve's env of record is deliverable

An env file that states every engine setting can still be undeliverable: the launcher may filter names out, or the container may carry values from another source. Prove delivery with a boot, not by reading the file.

## 1. Find what the launcher forwards
The recipe `start.sh` pattern is the contract, e.g.
`env | grep -E '^(TENSORFOLD|TF_FLASHNEXT)_[A-Z0-9_]+='`. List every stated name that does not match: those can never reach the container. Cross-check against the engine's own table (`zig/src/platform/environment.zig`) so a dropped name with a real reader is a defect, not a doc artefact.

## 2. Source the file the way the launcher does
`set -a; . /path/dev.env; set +a`, then the launcher with `LOCK_HOLDER=0` on the box's GPU lock. `export NAME` with no value does not unset; `unset NAME` is real absence and the only off for some validators (e.g. names whose `valid(n)` refuses 0).

## 3. Diff in both directions
`docker inspect <c> --format '{{json .Config.Env}}'` against the file: report carried-equal / differ / absent-in-namespace, each `unset` line absent, and the engine table's match / mismatch / not-carried. Require 0 differ and 0 absent for every forwardable name, and say how many names are not forwardable at all.

## 4. Widening a filter is a behaviour change until proven neutral
A widened filter delivers values that were previously absent. For each such name, read its reader and prove the stated value equals the absence path (`get(...) orelse X`, a clamped or derived default, or a family that never reads it). Then boot A/B on the same image: the env differs only by those names, the engine's window self-check is equal, and fixed-prompt replies are identical. None of these is optional.

## 5. The production drift check needs identity, not a name
GPU windows reuse the production container name. Before comparing anything to `prod.env`, verify the container's image is the pinned production image and refuse otherwise; a check that trusts the name reports a window's dev env as production drift.

## Gates
- stated name not forwardable -> fail (not an advisory); the fix is the launcher or re-homing the row.
- any differ/absent on a forwardable name -> fail.
- `unset` name present in the container -> fail.
