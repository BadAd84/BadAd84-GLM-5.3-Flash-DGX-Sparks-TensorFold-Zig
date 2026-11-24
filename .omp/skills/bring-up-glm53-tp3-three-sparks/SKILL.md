---
name: bring-up-glm53-tp3-three-sparks
description: "Bring up or repair the MiaAI-Lab GLM-5.3-Flash-EXL3 TP=3 serve across three DGX Sparks (directed RoCE ring, NFS weights, InstantTensor, cooperative MoE requalification) - the traps that cost hours"
---

## When
Booting/repairing `~/glm53-current/start-tp3.sh` on spark1/2/3, re-cabling the ring, or enabling the TP=3 cooperative-MoE kernel.

## Rule zero
Match the recipe README "3x Spark (TP=3)" + "Sharing weights from the head (NFS_SHARE=1)" sections EXACTLY. Every deviation (own subnets, rsync'd weights, LOAD_FORMAT tweaks) cascaded into new failures.

## Fabric (recipe scheme)
- Directed ring: each node Port0 (enp1s0f0np0) -> NEXT node Port1 (enp1s0f1np1). Ours: spark1->spark3->spark2->spark1. Verify with LLDP before addressing.
- Rank order MUST follow the ring: rank1 = next node after head (spark3), rank2 = spark2. Mirrored order leaves one pair unconnectable; reordering NCCL_IB_HCA does not help.
- Loopback identities 10.0.0.1/.2/.3 on a NetworkManager DUMMY con `fab-lo` (ifname fablo0) - `ip addr add ... dev lo` does not survive reboot. Cable /24s: 10.0.22.x (head<->rank1), 10.0.23.x (head<->rank2), 10.0.33.x (rank1<->rank2); head is .1 on both its cables. Per-cable nmcli con: ipv4.never-default yes, 802-3-ethernet.mtu 9000, ipv4.routes "10.0.0.<peer>/32 <peer-cable-ip>". Verify `ping -M do -s 8972` to each loopback.
- .env.tp3: HEAD_IP/WORKER_IP/WORKER2_IP = 10.0.0.1/.2/.3; keep WORKER_SSH/WORKER2_SSH on the LAN (192.168.99.x); SOCKET_IFNAME=enP7s7; NCCL_CROSS_NIC=1; NCCL_IB_SUBNET_AWARE_ROUTING=1.
- HCA: use BOTH ports on every rank (`rocep1s0f0,rocep1s0f1`, CX7_IF likewise). The recipe's single-HCA pins give `ibv_modify_qp ... 110 Connection timed out` (INIT->RTR) on a direct-cabled ring.
- GID: re-addressing moves the RoCE v2 IPv4 GID (was 3, now 4). Find it: `cat /sys/class/infiniband/<dev>/ports/1/gid_attrs/types/N` = "RoCE v2" and gids/N ends `ffff:<ip hex>`. Preflight error "set NCCL_IB_GID_INDEX ... to populated indices" = wrong index.

## Weights / memory
- NFS_SHARE=1 + NFS_SERVER_IP_1=10.0.22.1, NFS_SERVER_IP_2=10.0.23.1, NFS_CLIENTS covering 10.0.22/23/33.0/24. NFS ACL rejection ("rank 1 cannot read ... over NFS") = client subnets don't match the recipe scheme.
- With per-rank local copies InstantTensor fails `buffer_size (1268776960 B) exceeds device memory budget (~704 MB)` at ANY GPU_MEM_UTIL; NFS_SHARE=1 fixes it (load 161 s). LOAD_FORMAT= (empty) also boots but ~4x slower load.
- EXTRA_ARGS with spaces MUST be quoted in .env.tp3 (`EXTRA_ARGS="--kv-cache-memory-bytes 42949672960 ..."`), else "42949672960: command not found".
- Recipe pins: MAX_MODEL_LEN=1000000, GPU_MEM_UTIL=0.80, 40 GiB KV. Expect KV ~3.21M tokens (3.21x at 1M).

## Cooperative MoE (TP=3 ABI2)
A local build's .so hash differs from dispatch_policy.json native_sha256 -> must be re-profiled (do not repin). Serve stopped, run in the serve image with HF cache ro, bundle, `extensions/cooperative_moe/tp3`, `tests/` (GLM53_COOP_TEST_HELPERS) and CLEAN `git show HEAD:overlay/exl3.py` mounted over vLLM's exl3.py:
1. test_contract.py needs the repo layout mounted (ROOT.parents[2]).
2. test_cuda_integration.py + profile_shapes.py for EP rank 0/1/2 x GLM53_COOP_GEOMETRY 0/1/2 with GLM53_COOP_MAINTENANCE_TEST=1 GLM53_COOP_QUALIFICATION=1 (~13 s each).
3. select_policy.py --bundle B <9 logs> (bundle must be user-owned: build leaves root-owned files -> chown).
4. test_policy_gpu.py per rank WITHOUT the qualification flag.
5. prepare_profile.py --stock <clean exl3.py> --bundle B -> exl3-tp3.py; set EXL3_OVERLAY_HOST to it. Verify per-rank log `prepared-layer summary: eligible=42 ineligible=0`.
Gain measured: structured 72->80, code 40->50 tok/s; prose unchanged.

## Benchmark honestly
- Use the recipe's tests/bench_decode.py (sed MODEL to the served name); tok/s = accepted_per_step / decode_ms_per_draft_step. Python SSE counting harnesses undercount ~2x.
- Run 8 runs with --warmup-tokens 400 so adaptive-k EMA settles; short runs look like a regression.
- Clock locking (nvidia-smi -lgc 3003) does nothing: decode is memory-bandwidth-bound; no nvpmodel on DGX OS.

## Ops traps
- Never pipe scripts with inner ssh via `bash -s`; write file, run file. sudo on Sparks needs `ssh -A -tt` (pam_rssh), never `sudo -n` for new setup.
- Workers need py-spy, /usr/local/bin/glm-mem-hygiene.sh and NOPASSWD sudoers (gdb, dmesg, py-spy, hygiene, swapoff/swapon) for watchdog capture.
- Rolling back to TP=2 needs its .env fabric IPs re-pointed at the 10.0.x ring and glm-stack.env switched.
