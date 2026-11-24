---
name: boot-glm-53-flash-exl3-on-2x-dgx-sparks
description: "Boot/manage GLM-5.3-Flash-EXL3 on OTS 2x DGX Sparks (port 8889): the 2026-09-19 keeper (FAST=1, coop OFF, SWA=0, restart-persistent NvmeDirect NVMe KV cache, version-keyed root, CG_ESTIMATE=0, vision kept), the coop-vs-retention exclusion, the recurring WEDGE class (worker stuck in cuda.synchronize inside apply_exl3_fused_moe) + watchdog v6 forensics on ALL restart paths (reason-labelled capture dirs, per-node process discovery, gdb native bt via /etc/sudoers.d/glm-diag, docker inspect OOMKilled, previous boot log preserved, --capture-now), offload rules, measured table, upstream watchlist pointer. OWNER: no upstream contributions, no context caps."
---

# Boot / manage GLM-5.3-Flash-EXL3 on 2x DGX Spark (MiaAI-Lab recipe)

GLM-5.3-Flash EXL3/TR3 4bpw on 2x GB10 (TP2 over CX7, sm_121a), served id `glm-53-flash-exl3`, port 8889.
**PRODUCTION KEEPER (2026-09-19, arm S2 + persistent offload): `~/glm53-current` @ upstream `ca85576` + our patches, image `glm53-flash-sm121:local`, `GLM53_EXL3_MOE_FAST=1`, COOP OFF (no EXL3_OVERLAY_HOST; coopslot3 kept for rollback), `GLM53_APC_RETENTION_INTERVAL_SWA=0`, restart-persistent NVMe KV cache (NvmeDirectOffloadingSpec, 40 GiB free-space gate), `CG_ESTIMATE=0`, `LANGUAGE_MODEL_ONLY=0` (owner keeps vision), FlashInfer 0.6.17 (0.7.0rc3 tested, reverted).** Watchdog ACTIVE (v6).
Full mirror guide: `glm5.3-flash-dev/docs/GLM53-FLASH-PRODUCTION-STACK.md`; helper scripts mirrored in `glm5.3-flash-dev/scripts/glm53/`.
Fallback `~/glm53-flash-2spark` intact; `spark-model glm` + rollback `sed -i s/glm53-current/glm53-flash-2spark/g ~/.local/bin/spark-model`.
Auth `ssh adam@spark1.ots-int.net`; worker 192.168.100.11; CX7 f0/f0 both ends, NCCL_IB_GID_INDEX=3.

## >>> OWNER POLICIES <<<
- NEVER send anything upstream to MiaAI-Lab. NEVER cap context as a workaround.

## >>> UPSTREAM WATCHLIST (read FIRST before any new optimisation work) <<<
`glm5.3-flash-dev/docs/GLM53-SPARK-UPSTREAM-WATCHLIST.md` - FlashInfer >=0.6.19 gate (0.7.0rc3 TESTED AND REVERTED: KDA kernels SM100a/SM103a only, no SM121, prefill -12%), vLLM full-rebase trigger (EXL3 fork-only, ~1000 behind, needs 2+ of EXL3-native/FlashInfer-fixed/>30% gain), TP3, drafter replay-clamp cost (2048 tokens/turn), PR#233 tested-neutral, #232/#231 grafted, driver items (dirty_bytes sudoers, ~700k prefill NVRM OOM, #214 idle bug), in-house 3.5bpw requant (gate on RE tasks). Also lists what we already tested and rejected.

## >>> MEASURED TABLE (bench_decode.py 5x400 medians, isolated blocking) <<<
S2 keeper: structured 78.5-80.7 / prose 36.5-36.8 / code 44.6; TTFT ~270-300ms; accept 0.959/6.71.
Config A/B (ca85576 image): M pure main 75.1/33.5; +FAST 79.3/34.6; coop-only(A2) 79.5/37.4; FAST+coop(B1) 78.7/35.8 (do NOT stack). 4 lanes x 30k: S2 39.1% hits, warm TTFT 17.8s vs 153s/0.0%.

## >>> THE COOP x RETENTION EXCLUSION (why coop is OFF) <<<
SWA=0 (drafter retention) + cooperative MoE overlay = decode collapse (struct 79->32, prose 37->25, accept 3.9/step). Pure main + SWA=0 healthy (74.3/34.3); FAST + SWA=0 healthy (78.5/36.8). Coop's not-bit-exact decode path poisons the DFlash SWA replay on cache hits. COOP AND DRAFTER-RETENTION ARE MUTUALLY EXCLUSIVE. If coop is re-enabled, SWA retention MUST return to empty, and vice versa.

## >>> THE WEDGE CLASS (recurring; the watchdog exists for this) <<<
Signature: `num_requests_running` >= 1 with BOTH token counters frozen (log: `WEDGE: running=N waiting=M frozen 10 samples`) -> in-flight requests (user sessions) die when the watchdog restarts. 6 wedges 2026-09-16..09-20 + one metrics-unreachable restart. Not workload-caused; an open driver/knob item.
Root-cause evidence (py-spy, 09-20 capture): worker MainThread blocked in `torch.cuda.synchronize()` inside `apply_exl3_fused_moe` (exl3.py:1544) mid-forward = SILENT GPU-side hang in the fused EXL3 MoE path (`GLM53_EXL3_MOE_FAST=1` tier); head EngineCore correctly waits on the worker; NO Xid / NO NVRM OOM in dmesg.
Open A/B (not yet run): does `GLM53_EXL3_MOE_FAST=0` reduce the wedge rate? Costs ~4-5 tok/s structured. Owner elected to wait for the next crash rather than A/B now.
Recovery automatic: capture -> docker kill both ranks -> swap cycle -> mem hygiene -> SKIP_BUILD=1 start (~6 min).

## >>> FORENSICS ON EVERY RESTART PATH - watchdog v7 <<<
`~/.local/bin/glm-watchdog.sh` (v7; v4 at .bak-v4). Capture dirs are reason-labelled:
`wedge-capture-<ts>` (frozen counters), `crash-capture-<ts>` (serve down/unreachable), `manual-capture-<ts>`
(`--capture-now`, read-only, no kill - use it to validate the path or grab state on demand).
**All three paths capture BEFORE the restart**, so the recreate never destroys evidence. Last 5 kept;
prune: `ls -dt ~/*capture-* | tail -n +6 | xargs rm -rf`.
Per capture: per-node py-spy all-thread (nonblocking) + gdb native all-thread bt per discovered
`VLLM::*` process, `nvidia-smi -q` (Xid/ECC/throttle), `docker inspect` of both containers
(Status/OOMKilled/ExitCode/Error/RestartCount - the OOM-vs-abort-vs-API-hang discriminator), dmesg both
nodes, docker logs both nodes, the previous boot's `glm53_start.log.prev`, live `/metrics`, last
requests, and `MANIFEST.txt` (reason + per-file line counts).
Implementation rules that matter:
- **Process names are DISCOVERED per node.** The worker runs `VLLM::Worker_TP1` - v4 hardcoded TP0 and
  produced 0-byte worker captures. Never hardcode TP indices.
- **gdb native bt** (py-spy `--native` fails `UNW_EBADREG` on this aarch64 kernel) needs
  `adam ALL=(root) NOPASSWD: /usr/bin/gdb` in `/etc/sudoers.d/glm-diag` on BOTH Sparks. Writing a
  sudoers drop-in without a password: `docker run --rm -v /etc/sudoers.d:/hs --entrypoint sh <image> -c 'printf ... > /hs/glm-diag && chmod 440 /hs/glm-diag'` (`sudo tee` needs a password).
- pgrep self-match filtered (nameless matches skipped).
- Residual gap (accepted): a full node reboot/kernel panic cannot be captured by the watchdog - but the
  PERSISTENT journal (~418 MB) keeps Xid/OOM across reboots: `journalctl -k -b -1 | grep -iE "Xid|nvrm|oom"`.

## >>> DISK GUARD - the KV cache fills the volume WHILE serving (2026-09-20 outage) <<<
The offload tier has NO eviction and writes for as long as the model serves: both nodes hit **0 bytes
free** (201G head / 206G worker, under a day). Consequences: the serve died AND **glm-watchdog went
blind - a full disk blocks its own log append** (its log stops mid-line; nothing captured for 12h).
An age-based boot prune cannot bound this; `GLM53_KVCACHE_PRUNE_DAYS` is 3 but the guard is what holds.
- `glm-disk-guard.sh` (one implementation; deletion only in `glm-kv-prune.sh`): prune until
  `GLM_WD_MIN_FREE_GB` (default **50G = 10G above the serve's own 40GiB boot gate**) is free, escalating
  >6h -> >15min -> all; `--both` also guards the worker. `--network none` because docker's own netns
  setup fails on a nearly-full volume. Cost when healthy: one df = 4ms. Log `~/glm-disk-guard.log`.
- `glm-disk-guard.timer` (systemd --user, 60s) on **EACH** node guarding its own disk - must not depend
  on the serve or on the watchdog. Enabled on both; linger=yes.
- Belts: `spark-model glm start` runs `glm-disk-guard.sh --both` first; watchdog v7 does the same before
  every restart (recover/DOWN paths); captures record `df -h` + cache size.
- NEVER prune `~/.cache/vllm-dsv41-flash-exl3/engram-src` (~190G) - that is DSV4.1 DATA, not a cache.
- Secondary hog: docker images (89G/18). Removed 2026-09-21: fi070, ots-fairv5(+baseline), ots-nightly-0916,
  exl3-e3-20260907 (~45G). A full node needs BOTH the cache pruned and images cleaned.
- Diagnosis tell: serve down + `~/glm-watchdog.log` ending mid-line => `df -h /` on BOTH nodes.

## >>> RESTART-PERSISTENT NVMe KV CACHE (NvmeDirectOffloadingSpec, live) <<<
Graft of upstream PR#232's spec onto our #58 base: overlay/kvoffload/nvme_direct.py bind-mounted at vllm/v1/kv_offload/nvme_direct.py on BOTH ranks (NVMEDIRECT_SPEC_HOST), spec via kv_connector_extra_config {spec_name NvmeDirectOffloadingSpec, spec_module_path vllm.v1.kv_offload.nvme_direct, root_dir @@KVCACHE_ROOT@@, n_io_threads 8, capacity_bytes 40 GiB free-space gate}, --enable-cumem-allocator (expandable_segments:True STAYS; False wedges GB10; NEVER set PYTHONHASHSEED - use overlay/patch_none_hash_seed.py pinning NONE_HASH from GLM53_NONE_HASH_SEED=ots-glm53-2026).
QUALIFIED: 60k prefix 5.3s after FULL restart vs 73.2s cold, byte-identical, 572 MiB physical reads; 288k session restored 8.3s.
RULES: (1) capacity_bytes is a FREE-SPACE boot gate (>40G free both nodes or boot refuses); (2) NO eviction/TTL - prune kv-nvme/r*/ by mtime inside a root container (start.sh _ots_kvcache_prune, GLM53_KVCACHE_PRUNE_DAYS=3; the 60s DISK GUARD above is what actually bounds it); (3) the tier index is in-process - a restart keeps the FILES (version-keyed) but a model/overlay change starts a new keyed root; (4) this spec bypasses vllm:kv_offload counters - measure wall time + physical reads.

## >>> VERSION-KEYED CACHE ROOT ([ots-kvcache-key] in start.sh) <<<
.env EXTRA_ARGS holds the literal @@KVCACHE_ROOT@@; _ots_kvcache_apply_key (TOP of launch_cluster, AFTER IMAGE/EXL3_OVERLAY_HOST/DFLASH_REVISION defaults exist) substitutes kv-nvme/<sha256(git HEAD|image Id|overlay sha|MODEL_REVISION|DFLASH_REVISION|KV dtype)[:12]>. Stack change => empty cache (never stale KV). Current key c0518cdbe795. COPY wheels into a /tmp/wheels/ DIR target in Dockerfiles.

## >>> DFLASH_SCHEDULE (wired, kept OFF) <<<
Per-batch-size spec-k taper. DFLASH_SCHEDULE='[[1,1,7],[2,2,4],[3,4,2]]' at 4 lanes: best warm TTFT (12.8s) but worst per-lane decode (7.8 tok/s) - throughput-at-c8 profile. Keep empty for interactive.

## >>> COPY-STARVATION PREFILL PATCH + PREFILL TEST <<<
`python3 ~/patch_starv_current.py` (anchor-asserted). Validate: `python3 ~/prefill_test.py` (~290k tokens; PASS = PREFILL_OK). Measured 288k in 296s (974 tok/s). NVRM OOM at ~700k/14GiB is a driver limit - keep MAX_MODEL_LEN=500000/12GiB.

## >>> DECODE MEASUREMENT RULES <<<
- ~/bench_arm.sh <arm> [runs] wraps tests/bench_decode.py (~/bench_decode_8889.py). NEVER inline-python JSON in ssh heredocs.
- Thinking-off kwarg: chat_template_kwargs {"enable_thinking": false} ({"thinking":...} is IGNORED).
- First structured run after boot can cold-JIT to ~9 tok/s - read min/max first.
- Persistent KV cache: A/B prompts must be NEVER-SEEN (reuse fakes a prefill speedup, even across restarts).
- Watch for external sessions (vllm:num_requests_running) - contention fakes regressions.
- Acceptance signature: structured accept ~0.96 / per_step ~6.7 = clean; ~0.8x = numerics perturbed.

## >>> CAMPAIGN RULES <<<
- DOCS ARE GATED: after any stack change, run `scripts/refresh-spark-state.sh` then
  `scripts/check-doc-inventory.sh` in glm5.3-flash-dev (must print CLEAN - it compares the docs against
  `docs/spark-live-state.json`, the scripts, and the README index). Never report the stack without them.
- STOP glm-watchdog before ANY manual boot; restart after (it killed a container mid graph-capture).
- `pkill -f`/`pgrep -f` with a literal pattern self-matches your ssh shell - use `[V]LLM::` style.
- ALWAYS factorial A/B: coop x retention; FAST x coop do not stack.
- Arms: ~/arm_boot.sh <0|1 FAST> <coop|nocoop>; ~/kvoff_toggle.sh on|off; ~/kvoff_{qual,correct,restart}.py; ~/agent_lanes.py.

## >>> COOP LAB-REPIN (v3, only if coop re-enabled) <<<
prepare_profile.py pins STOCK_SHA/BINARY_SHA/ADAPTER_SHA in extensions/cooperative_moe/prepare_profile.py. After ANY exl3.py change: new patched sha + rebuild .so + regenerate profile + GPU gate 48 checks both nodes. ~/coop_build.sh, ~/coop_enable3.sh (SLOT=coopslot3). Upstream #209/#226: the blessed .so is unreproducible.

## >>> HYGIENE / SSH <<<
HOST py-spy (container has no ptrace); `sudo dmesg|tail` for NVRM OOM. /usr/local/bin/glm-mem-hygiene.sh before every boot. Stop BOTH nodes when swapping. UniFi IDS rate-limits rapid SSH - drive long boots via tmux/scripts (~/arm_boot.sh).

## >>> ROLLBACK / REJECTED / SUPERSEDED <<<
- Full GLM rollback: sed spark-model to glm53-flash-2spark (fallback image ots-nightly-0916b).
- #58 NVMe mmap-CPU-tier: superseded by NvmeDirect spec.
- DFLASH_SCHEDULE taper: rejected for interactive; knob stays wired.
- GLM53_MIXED_PREFILL_CHUNK=fair: rejected under 4 lanes (25s vs 18s warm TTFT); keep 0.
- #233 KDA BF16 large-M: knob 0, no prefill gain (979 vs 966).
- FlashInfer 0.7.0rc3: no decode gain, prefill -12%, reverted to 0.6.17.
- Fast tails (#227): the 09-20 wedge (worker stuck in the FAST fused-MoE sync) puts this back under scrutiny.
- ~/backup-prepull-20260918/: delete when confident. DSV4.1 (~/dsv41-flash-2spark) is MUTUALLY EXCLUSIVE.
