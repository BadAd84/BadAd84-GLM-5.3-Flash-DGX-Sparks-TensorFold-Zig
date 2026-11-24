---
name: make-external-kv-delete-safe-on-glm-spark
description: "Diagnose and fix the GLM-5.3-Flash 2x-DGX-Spark crash where deleting NVMe KV-cache files under a live serve kills the engine (stale HIT - fatal load), and prove the fix with the discriminating suites. Use when a Spark serve dies mid-session with '[Errno 2] No such file' / EngineDeadError on r0/r1 .bin files, when changing the disk guard or the nvme_direct offload overlay, or before touching anything that deletes KV cache files."
---

# Make an external KV-cache delete survivable on the GLM Spark serve

Serve: spark1 `:8889`, guard + watchdog are systemd --user units; overlay tree `~/glm53-current`.

## The failure class
`NvmeDirectManager` (`overlay/kvoffload/nvme_direct.py`, our graft of PR#232) caches every positive
`exists()` in `_exists`, and the spec asserts the invariant *"Files are never evicted while the server
runs; nothing to pin"*. Any external deleter (our own disk guard, an age prune, a manual
`glm-kv-prune.sh`) breaks that: the deleted block still reads as a **HIT**, the load job reads a
missing file, and `get_finished()` **raises** for a failed load -> EngineCore dies, every in-flight
session dies, the head exits 0 and the watchdog only notices 20 min later.
Symptom: `RuntimeError: Worker failed with error '[Errno 2] No such file or directory: .../r1/<x>/...bin'`.

## Diagnose (do these in order)
1. `docker inspect` the head: `StartedAt`/`ExitCode` - an exit 0 with `OOMKilled=false` is this class.
2. **Docker logs are UTC; the shell and the guard/watchdog logs are Europe/London.** Convert before
you attribute a cause (05:30 BST read as 04:30 in `docker logs`).
3. The watchdog log names the event: `metrics unreachable for 40 samples -> capture + starting glm`
(then the capture dir `~/crash-capture-<ts>/`).
4. Prove the asymmetry: take the missing hash from the traceback (+ its 3-char dir), then check both
ranks - head `~/.cache/vllm-glm53-flash/kv-nvme/<key>/r0/<x>/` and worker `.../r1/<x>/` (via
`ssh adam@192.168.100.11`). r0 present + r1 gone = a per-node prune stranded one rank's half.
5. Correlate the prune time from `~/glm-disk-guard.log` on EACH node (the worker's own timer logs
`local:` in ITS file). Note the hash must match the current version-keyed cache root.

## Fix (three layers; keep all three)
1. **Paired pruning** in `glm-disk-guard.sh`: ONE cutoff from the pair's LOWEST free space, applied to
every reachable node; never a subset while the engine is up (defer instead); worker timer removed;
serve probe on the head's address with a localhost fallback; a worker-side run drops to local-only.
2. **Cache-reset handshake**: while the engine is up, `POST /reset_prefix_cache?reset_external=true`
(our `[glm53-cache-reset]` patch -> `connector.reset_cache()` -> `_exists.clear()`) BEFORE deleting and
again after; if it will not confirm (it refuses with "blocks still in use" during long requests)
DEFER and retry next tick. Emergency floor must sit ABOVE the 40 GiB boot gate (42), not below it.
3. **`patch_lookup_reverify.py`**: `lookup()` re-stats instead of trusting the cached positive and
`prepare_store()` stops skipping deleted blocks; kill switch `GLM53_KV_LOOKUP_REVERIFY=0` (the A/B
mutant). Needs a restart to take effect; the file is bind-mounted so a fresh container sees it.

## Prove it (each suite must FAIL on the unpatched artifact)
- glm5.3-flash-dev `scripts/glm53/test-disk-guard.sh [mutant-path]` - offline stubs for df/curl/ssh/prune, 17 checks;
  the pre-fix guard fails 11. Pass the mutant as a POSITIONAL ARG (a `GUARD=... bash test.sh` prefix is
  silently dropped by this harness's top-level bash, so the suite passes on the unmutated script).
- `scripts/glm53/test_nvme_direct_stale.py` - `docker cp` into the serving container and run it there:
  pre-patch `HIT`/`keys_to_store=0`, post-patch `MISS`/`1`.
- `scripts/glm53/kvoff_delete_ab.py <seed> <tokens> [flood] [ndel]` - live attack. **It needs a flood**:
  the GPU pool is 546,082 tokens, so a small target stays resident and deleting its files proves
  nothing (measured: 8 and 500 verified deletions of a 72k/240k prefix SURVIVED on unpatched code).
  Verify each deletion (a positive control is printed) - `rm -f` on a wrong path exits 0.
- Then bring the patch live: `systemctl --user stop glm-watchdog` + stop the guard timer, restart via
  `~/arm_boot.sh 1 nocoop`, prove with a real completion (health endpoints lie), re-run the unit test
  in the container, then re-enable BOTH supervisors.

## Traps that cost hours
- `pkill -f <literal>` self-matches the ssh shell - bracket the pattern (`[a]rm_boot.sh`).
- Hard-killing containers MID-REQUEST can hang the next boot at `Breakable CUDA graph enabled`; a clean
  retry (kill start.sh, `docker rm -f` both ranks, `glm-mem-hygiene.sh` both nodes, re-boot) fixes it.
  Do NOT call a boot "stuck" from log silence: check `docker exec <c> ps -eo etime,cmd` for an active
  NVRTC/JIT build (patch_spinwait.py + humming) or a safetensors load.
- The boot belt lives in `spark-model glm start` and the watchdog, NOT in `arm_boot.sh`, so free space
  must be pruned by hand before an `arm_boot` boot.
- Re-enable the watchdog AND the guard timer afterwards; forgetting leaves the serve unguarded.
