---
name: diagnose-dgx-spark-cx7-13gbps-fabric
description: "Use when multi-Spark NCCL/RDMA/prefill is slow: detect and fix the DGX Spark ConnectX-7 ~13 Gb/s low-power state (post-hotplug) and GID-index drift."
---

# DGX Spark ConnectX-7 stuck at ~13 Gb/s

## Symptom
- Multi-node prefill or NCCL collectives far slower than expected; profile shows all-gather/all-reduce dominating.
- `ib_write_bw` on a direct cable: ~13 Gb/s per RoCE function (reference: ~100-112 Gb/s per function, ~195 per cable).
- ethtool 200000Mb/s, PCIe 32GT/s x4, and RDMA hw_counters + ethtool -S show NO retransmits/out-of-sequence/discards/pause. Clean but slow.
- dmesg `Detected insufficient power on the PCIe slot (27W)` is cosmetic - not the cause by itself.

## Measure (never assume)
1. Raw link per rail: `ib_write_bw -d <dev> -x <gid> -q 4 -s 1048576 -D 4 --report_gbits [server-ip]` (server first). In OTS: ots-infra `scripts/sparks/triangle_rdma_check.sh` run ON spark1 (a harness script child lacks known_hosts) - all 12 directed rails of the triangle.
2. NCCL: ots-infra `scripts/sparks/nccl_bw.sh` (TensorFold's NCCL wrapper, 32 MB/rank all-gather = the prefill partials).
3. Rule-outs that cost nothing: spark3 `/proc/net/snmp` Ip ForwDatagrams delta during a spark1->spark2 run must be 0 (direct cable, no kernel forwarding); hugepage buffers (root, memlock unlimited) no change => not IOMMU 4K translation.

## Fix
- Reboot every Spark WITH THE FINAL CABLING CONNECTED (hot-plugging after boot re-triggers it). Before rebooting: disable any watchdog/timer that would autostart a stale serve (spark1: glm-watchdog.service, glm-disk-guard.timer).
- Re-run the triangle check: expect 111.85-111.89 Gb/s on every rail.

## After a reboot: GID indexes move
- IPv4 RoCEv2 GID index was 4 before, 3 after. Never hard-code it.
- NCCL: drop NCCL_IB_GID_INDEX; set NCCL_IB_ADDR_FAMILY=AF_INET NCCL_IB_ROCE_VERSION_NUM=2.
- Per-device lookup (bash): first `gids/N` containing `ffff:` whose `gid_attrs/types/N` == `RoCE v2`.
- NCCL_IB_HCA = all four functions (rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1); subnet-aware routing picks the right cable per peer. 32 MB all-gather: 13.3 GB/s on 2 functions, 20.95 GB/s on 4.

## Second PCIe function needs IPv4
The P2 netdevs (enP2p1s0f0np0/enP2p1s0f1np1) are the same cable; give them static per-cable IPv4 (OTS: subnet+100, `setup_p2_rails.sh`) or their RoCE devices have no IPv4 GID (IPv6 disabled => EAFNOSUPPORT at ibv_modify_qp RTR).
