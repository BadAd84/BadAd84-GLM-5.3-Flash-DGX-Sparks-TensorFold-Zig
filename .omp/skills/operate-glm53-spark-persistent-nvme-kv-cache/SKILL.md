---
name: operate-glm53-spark-persistent-nvme-kv-cache
description: "Operate, qualify, and troubleshoot the restart-persistent NVMe KV prefix cache on the GLM-5.3-Flash 2x DGX Spark serve (NvmeDirectOffloadingSpec grafted on PR#58, version-keyed root, root-container prune) - session-resume in seconds instead of re-prefill. Use when enabling/disabling it, after a tree/image change, when a boot refuses on the capacity gate, when disk fills, or to re-prove restore correctness."
---

# Persistent NVMe KV cache on the GLM-5.3-Flash 2x Spark serve

What it does: evicted/cold prefixes are restored from per-node NVMe files instead of re-prefilled, and the
files SURVIVE serve restarts. Measured: 60k-token session 5.2s after a full restart vs 74.9s cold,
byte-identical; a 288k session restored in 8.3s. Lives in `~/glm53-current` on spark1 (worker spark2 =
192.168.100.11 mesh), serve on :8889.

## Pieces (all already wired; do not re-derive)
- `overlay/patch_kv_offload_groups.py` (PR#58: hybrid-group fixes for the OffloadingConnector, 27 anchored
  edits, `KVOFF_PATCH_HOST` in start.sh, kill switch `GLM53_SKIP_KV_OFFLOAD_GROUPS_PATCH=1`).
- `overlay/kvoffload/nvme_direct.py` (PR#232's `NvmeDirectOffloadingSpec`, out-of-tree; bind-mounted at
  `vllm/v1/kv_offload/nvme_direct.py` on BOTH ranks via `NVMEDIRECT_SPEC_HOST`). No CPU tier, chunk-per-file
  `r<rank>/<hash[:3]>/<hash>.bin`, lookups = file existence on rank 0.
- `overlay/patch_none_hash_seed.py` (ours): pins vLLM's `NONE_HASH` from `GLM53_NONE_HASH_SEED` so block
  hashes are stable across restarts WITHOUT `PYTHONHASHSEED` (which breaks Triton JIT keys mid-collective).
- start.sh `[ots-kvcache-key]`: `.env` EXTRA_ARGS keeps the literal `@@KVCACHE_ROOT@@`; at the top of
  `launch_cluster` it becomes `kv-nvme/<sha256(git HEAD|image Id|sha(exl3 overlay)|MODEL_REVISION|
  DFLASH_REVISION|KV_CACHE_DTYPE)[:12]>` so any stack change starts an EMPTY cache (never stale KV). It must
  run inside launch_cluster - those vars are not set right after `.env` is sourced.
- Prune at every boot on both nodes: `_ots_kvcache_prune local|<worker>` deletes `*.bin` older than
  `GLM53_KVCACHE_PRUNE_DAYS` (3) INSIDE a root container (`docker run -v <dir>:/kv --entrypoint sh $IMAGE`)
  because the files are root-owned; adam-level rm/find fails on them.
- `~/.local/bin/glm-disk-guard.sh` + `glm-kv-prune.sh` (+ `glm-disk-guard.timer`, 60s, EACH node): the
  free-space guard that bounds the cache while the model serves (see "Disk guard" below).

## .env (production)
```
EXTRA_ARGS='--kv-cache-memory-bytes 12884901888 --kv-transfer-config {"kv_connector":"OffloadingConnector","kv_role":"kv_both","kv_connector_extra_config":{"spec_name":"NvmeDirectOffloadingSpec","spec_module_path":"vllm.v1.kv_offload.nvme_direct","root_dir":"@@KVCACHE_ROOT@@","n_io_threads":8,"capacity_bytes":42949672960}} --enable-cumem-allocator'
GLM53_NONE_HASH_SEED=ots-glm53-2026
GLM53_KVCACHE_PRUNE_DAYS=3
GLM53_OFFLOAD_MMAP_DIR=          # the old #58 mmap tier stays EMPTY/off
```
Keep `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (launcher default) + `--enable-cumem-allocator`.
NEVER set expandable_segments False on GB10 (wedged both Sparks upstream, power cycle) and NEVER set
PYTHONHASHSEED. Host dirs: `~/.cache/vllm-glm53-flash/kv-nvme/<key>/r<rank>/` on BOTH nodes.

## Disable
Remove `--kv-transfer-config ...` and `--enable-cumem-allocator` from EXTRA_ARGS; restart (`~/arm_boot.sh 1
nocoop`). Overlays stay inert without the connector flag.

## Boot refuses: "NVMe prefix-cache target ... has X GiB free; Y GiB required"
`capacity_bytes` is a FREE-SPACE gate on the target volume at boot, not a usage cap. Simplest fix:
`~/.local/bin/glm-disk-guard.sh --both` (prunes to 50G free on both nodes). Otherwise free disk by hand
(stale `*.mmap` in `kv-mmap/`, old keyed dirs, benchmark junk) via a root container:
`docker run --rm --network none -v ~/.cache/vllm-glm53-flash/kv-nvme:/kv --entrypoint sh $IMAGE -c 'rm -rf /kv/<oldkey>'`
on both nodes, or lower `capacity_bytes`. Keep >40 GiB free on both nodes.

## Re-prove correctness after any change (scripts on spark1)
1. `systemctl --user stop glm-watchdog` (it kills booting containers mid graph-capture). Restart it after.
2. `python3 ~/kvoff_restart.py pre <seed>` (stores a 60k prefix; prints outputs) -> `~/arm_boot.sh 1 nocoop`
   -> `python3 ~/kvoff_restart.py post <seed>`: PASS = restored TTFT ~5s vs ~74s cold, outputs identical,
   never-seen control stays cold (~73s). Use a NEW seed every time - any prompt sent twice is a persistent
   hit forever after (this fakes prefill speedups in unrelated A/Bs too).
3. `python3 ~/kvoff_correct.py <seed>` for the eviction-flood variant (high-margin + early-context tasks,
   decode after restore). Restore counters (`vllm:kv_offload_*`) stay 0 with this spec - judge by wall time,
   `/sys/block/nvme0n1/stat` sectors read, and byte-identical output, not counters.

## Disk guard (auto-prune while serving - 2026-09-20 outage)
The cache has NO eviction and grows while the model serves: both nodes hit **0 bytes free** (201G head /
206G worker, under a day) -> serve died + glm-watchdog went blind (a full disk blocks its own log append).
Since 2026-09-21: `glm-disk-guard.sh` prunes until `GLM_WD_MIN_FREE_GB` (default **50G = 10G above the
40GiB boot gate**) is free, escalating >6h -> >15min -> all; `glm-kv-prune.sh` is the only deletion path
(root container, `--network none`). Run by a **60s systemd --user timer on EACH node** (independent of
the serve and of the watchdog) + belts before every boot (`spark-model glm start`) and every watchdog
restart. Log `~/glm-disk-guard.log`. Manual run: `~/.local/bin/glm-disk-guard.sh --both`.
NEVER prune `~/.cache/vllm-dsv41-flash-exl3/engram-src` (~190G) - DSV4.1 DATA, not a cache.

## Known limits
- No eviction beyond the age prune + the disk guard above; heavy use grows it fast (200G in under a day) -
  the timer handles it, or prune by hand via `glm-kv-prune.sh <+mmin>`.
- Concurrency is unaffected: this fixes SWITCHING between sessions; simultaneous lanes are bound by the
  ~150 tok/s aggregate budget (4 lanes ~18s warm TTFT).
- Thinking-off request kwarg for this template is `chat_template_kwargs: {"enable_thinking": false}`.
