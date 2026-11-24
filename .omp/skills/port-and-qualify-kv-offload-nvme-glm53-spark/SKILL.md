---
name: port-and-qualify-kv-offload-nvme-glm53-spark
description: "Port/enable/qualify the persistent NVMe KV-offload tier (NvmeDirectOffloadingSpec) on the GLM-5.3-Flash Spark serve - TP=3 (live 2026-09-30, start-tp3.sh via port_kvoffload_tp3.py) or TP=2 - with ground-truth restore checks, the all-node disk guard, and the traps that fake a result."
---

# Port + qualify the persistent NVMe KV tier on GLM-5.3-Flash (TP=3 live, TP=2 fallback)

Why: a cold 656k-token agent history prefills in ~835 s; restored from NVMe after a restart/GPU eviction it is back in 13-17 s.

## TP=3 (live since 2026-09-30, serve spark1:8888)
- Launcher port: glm5.3-flash-dev `scripts/glm53/port_kvoffload_tp3.py [start-tp3.sh]` - anchor-asserted, refuses to run twice, writes `start-tp3.sh.pre-kvoffload`. It mirrors start.sh's `[ots-kvcache-key]` block for all 3 ranks: keyed cache root (key includes `tp3`), boot age-prune on every node, overlays `patch_kv_offload_groups.py` / `patch_none_hash_seed.py` / `patch_cache_reset.py` in BOTH inner scripts after kpool-tail, `overlay/kvoffload/nvme_direct.py` (lookup-reverify applied) mounted over vLLM's, env forwards (NONE_HASH_SEED, EXPOSE_CACHE_RESET, OFFLOAD_*). Seed/reset/prune values come from `.env` (start-tp3 sources it).
- Enable: append to `.env.tp3` EXTRA_ARGS (keep it one double-quoted line, escaped JSON, no spaces):
  `--kv-transfer-config {"kv_connector":"OffloadingConnector","kv_role":"kv_both","kv_connector_extra_config":{"spec_name":"NvmeDirectOffloadingSpec","spec_module_path":"vllm.v1.kv_offload.nvme_direct","root_dir":"@@KVCACHE_ROOT@@","n_io_threads":8,"capacity_bytes":42949672960}} --enable-cumem-allocator`
- Dry-run first in a throwaway container of the LIVE image: expect `[kv-offload-scratch]` edits 3/14/3/4/3 and 4 group tests passing.
- Boot check on every rank log: `[ots-kvcache-key] ... key=`, `Created NvmeDirectManager (lookup dir .../r0)`, `NONE_HASH pinned`, groups 1 and 6 excluded as scratch.
- Disk guard: set `GLM_DISK_GUARD=1` in `~/.config/glm-stack.env`, enable `glm-disk-guard.timer` on the HEAD only. The guard reads `GLM_WORKERS`; while serving it prunes all nodes or none, and `--local-only` always defers. `glm-kv-prune.sh` must be byte-identical on every node. Offline test: `test-disk-guard.sh <guard>` (two workers, 19 checks).
- Disk use: ~20 GB per 656k history per node.

## Qualification (at real scale; ~1 h)
1. `~/kvport/kvq_tp3.py pre` - never-seen salted 656k history (unique agent salt), cold.
2. Full restart (`spark-model glm stop` then `start`; there is NO `restart` verb), drop page cache, `kvq_tp3.py post`: TTFT << cold, NVMe read MB > 0, never-seen control stays cold, decode after restore.
3. Correctness = GROUND TRUTH, not cold-vs-restored text: `kvq_truth.py <label>` appends "quote the first 12 words / last line of the workspace" to the exact prior conversation. Cold vs restored free-form greedy replies diverge after ~20 tokens even with a correct prefix (low-margin text), so `identical=false` there is NOT a failure.
4. `docker cp ~/test_nvme_direct_stale.py <head>:/tmp/`; exec: PASS live, FAIL with `-e GLM53_KV_LOOKUP_REVERIFY=0` (proves the reverify is load-bearing).
5. `curl -X POST localhost:8888/reset_prefix_cache?reset_external=true` -> `{"success":true}`, then re-run step 3.
Measured 2026-09-30: restore TTFT 17.3/13.2 s vs 835 s cold, 5.3 GB read, 46.4 tok/s decode after restore.

## Traps
- Long-held ssh watchers from the laptop get `Connection reset by peer` after ~4-5 min: use short `sleep N; ssh check` steps, run jobs detached on the box (`setsid ... & disown`).
- Pushing a script and launching it with `&` in the same ssh races stdin (0-byte file): push, then launch in a separate ssh. Strip CR on the REMOTE side (`tr -d "\r" > file`); the harness shell backend flips between WSL and msys and a local tr is not reliable.
- `pgrep/pkill -f` with a literal pattern self-matches the ssh shell: bracket a character (`longct[x]`).
- Any prompt sent before is a cache hit forever (persistent tier): A/Bs need never-seen salts.
- Delete old-key cache dirs via a root container (`docker run --rm -v ~/.cache/vllm-glm53-flash/kv-nvme:/kv --entrypoint rm <image> -rf /kv/<oldkey>`); files are root-owned.
- Never set PYTHONHASHSEED; keep `expandable_segments:True` + `--enable-cumem-allocator` (GB10 allocator wedge).
- `kv_offload_*` byte counters stay 0 with NvmeDirect: prove restores with `/proc/diskstats` nvme0n1 read sectors + TTFT + never-seen control.
