---
name: guard-a-long-running-serve-against-disk-fill
description: "Defend a long-running local inference/app serve whose cache grows on disk (KV offload, artifacts, logs) from filling the volume and silently killing both the service and its watcher. Use after any \"serve died overnight with no logs\" incident, or before leaving a cache-writing serve unattended."
---

# Guard a long-running serve against disk fill

Use when a local serve writes a growing cache to disk (NVMe KV offload, mmap tier, artifacts, logs).
Measured incident (GLM-5.3-Flash on 2x DGX Spark, 2026-09-20): both nodes hit **0 bytes free** - the
offload cache has **no eviction** and grew 201 GB (head) / 206 GB (worker) in under a day, because the
boot prune was AGE-based (14 d) and nothing was ever old enough.

## The part that bites: a full disk disables your observability

The watchdog was **alive and looping** the whole 12 h outage, but `log()` could not append - its log
stops mid-line at the instant of the fill, and no forensics were captured. So:

- **The guard MUST NOT depend on the thing it protects, nor on the watcher.** Install it as an
  independent systemd `--user` timer (needs `loginctl enable-linger`), one per node, guarding its own
  local disk - never rely on a cross-node ssh in the steady-state path.
- Do not read "serve down + no watchdog log lines" as "the watchdog is broken". Check `df` first.

## Threshold: above the SERVICE's own boot gate, not a round number

Find the service's startup free-space gate first (GLM: `capacity_bytes = 40 GiB`; a boot **refuses**
below it). A guard that settles at "10 GB headroom" then trades a full disk for an **unbootable** one.
Rule: `threshold = boot_gate + headroom` (GLM: 40 + 10 = **50 GB**, knob `GLM_WD_MIN_FREE_GB`).

## Design that worked

- **One implementation of the deletion fact**, called from everywhere:
  - `glm-kv-prune.sh <mmin-expr>` - the only place that knows *how* to delete (files are root-owned ->
    do it in the serve image; **use `--network none`**, because docker's own netns setup
    (`/.tmp-resolv.conf...`) fails with ENOSPC on a nearly-full volume - this blocked the first
    recovery attempt).
  - `glm-disk-guard.sh [--both]` - the policy: escalate, stopping as soon as free >= threshold:
    prune blocks `-mmin +360` (>6 h) -> `+15` -> `+0` (all). Cost when healthy: one `df` = **4 ms**.
- **PRIMARY** = 60 s timer per node. **BELTS** = run `--both` before every boot (`spark-model glm start`
  hook) and before every watchdog restart (recover/DOWN paths) - a restart on a full volume cannot
  succeed. Keep the schedule single-owner: don't also re-check every watcher tick.
- **Captures must record disk state** (`df -h` + cache-dir `du`) or the next incident is undiagnosable.
- Add a "did I stop the guard?" check to the failure path: `systemctl --user list-timers <guard>`.

## Verify (never test against the live cache)

Prove escalation on a **dummy dir**, so the running serve's blocks are untouched:

```bash
T=/tmp/gdtest; mkdir -p "$T/k/r0"; touch -d '3 days ago' "$T/old.bin"; touch "$T/new.bin"
GLM53_KVCACHE_DIR="$T" GLM_WD_MIN_FREE_GB=99999 ~/.local/bin/glm-disk-guard.sh   # must escalate to 0 files
GLM53_KVCACHE_DIR="$T" GLM_WD_MIN_FREE_GB=99999 ~/.local/bin/glm-disk-guard.sh --both  # worker reachable
~/.local/bin/glm-disk-guard.sh   # steady state: silent + ~4ms
```

Then confirm: timers `active` on every node, boot hook present, and the serve healthy by a **live
generation**, not `/health`.

## SSOT + keeping it honest

Concrete instance live since 2026-09-21 (GLM serve): `glm5.3-flash-dev/scripts/glm53/{glm-disk-guard,glm-kv-prune}.sh`
+ `systemd/glm-disk-guard.{service,timer}` (on both Sparks), documented in
`glm5.3-flash-dev/docs/GLM53-FLASH-PRODUCTION-STACK.md` §5 "Disk guard". After changing any of it, refresh
`glm5.3-flash-dev/docs/spark-live-state.json` (`scripts/refresh-spark-state.sh`) and run
`glm5.3-flash-dev/scripts/check-doc-inventory.sh` - the guard's threshold/version are asserted there.

## Do not delete

- Weights, and any sibling model's staged DATA (GLM incident: `~/.cache/vllm-dsv41-flash-exl3/engram-src`
  = 190 GB of DSV4.1 data that looks like a cache and is not).
- Prefer clearing caches first; docker images are the secondary hog (89 GB / 18 images; superseded test
  images ~45 GB). A node at 0 needs **both** its cache pruned and its images cleaned.
- Cache is throwaway: clearing costs warm-session restore speed only, never correctness.
