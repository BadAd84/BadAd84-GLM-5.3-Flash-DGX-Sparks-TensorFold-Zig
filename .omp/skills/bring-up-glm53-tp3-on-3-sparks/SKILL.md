---
name: bring-up-glm53-tp3-on-3-sparks
description: "Bring up or repair the GLM-5.3-Flash EXL3 TP=3 serve across three DGX Sparks (directed RoCE ring, NFS weights, coop MoE) by matching the MiaAI-Lab recipe"
---

# GLM-5.3-Flash TP=3 on 3 DGX Sparks

Rule zero: READ the recipe README `### 3x Spark (TP=3)` and `### Sharing weights from the head (NFS_SHARE=1)` sections in ~/glm53-current/README.md and match them. Improvising addressing cost hours.

## Topology (live 2026-09-28)
- Ranks: spark1 .101 = rank0 (head/API), spark3 .103 = rank1, spark2 .102 = rank2. Rank order MUST follow the physical ring direction (each node Port0 -> next node Port1; ring spark1->spark3->spark2->spark1). NCCL pairs NIC index to NIC index; reordering NCCL_IB_HCA does not help.
- Fabric via nmcli (persistent, MTU 9000, never-default): cable subnets 10.0.22.x (spark1 f0 .1 <-> spark3 f1 .2), 10.0.23.x (spark1 f1 .1 <-> spark2 f0 .2), 10.0.33.x (spark3 f0 .1 <-> spark2 f1 .2); loopback identity on NM dummy `fab-lo`/fablo0 (10.0.0.1/.2/.3) with /32 routes to each peer's loopback via its cable. (An `ip addr` alias on lo is NOT persistent.)
- Verify: ping all loopbacks from every node + `ping -M do -s 8972`.

## .env.tp3 essentials
- HEAD_IP/WORKER_IP/WORKER2_IP = 10.0.0.1/.2/.3; WORKER_SSH/WORKER2_SSH = LAN adam@192.168.99.103/.102 (separate override).
- CX7_IB/CX7_IF = BOTH ports on every rank (rocep1s0f0,rocep1s0f1). The recipe's single-HCA pins fail on a direct-cabled ring (ibv_modify_qp 110 INIT->RTR between non-adjacent subnets).
- NCCL_IB_GID_INDEX: read /sys/class/infiniband/<dev>/ports/1/gid_attrs/types/N; RoCE v2 IPv4 was index 4 after re-addressing (launcher preflight errors if unpopulated).
- SOCKET_IFNAME=enP7s7, NCCL_CROSS_NIC=1, NCCL_IB_SUBNET_AWARE_ROUTING=1.
- NFS_SHARE=1, NFS_SERVER_IP_1=10.0.22.1, NFS_SERVER_IP_2=10.0.23.1, NFS_CLIENTS=10.0.0.2,10.0.0.3,10.0.22.0/24,10.0.23.0/24,10.0.33.0/24, LOAD_FORMAT=instanttensor. Without NFS the workers fail InstantTensor `buffer_size exceeds device memory budget` (lowering GPU_MEM_UTIL makes it worse).
- MAX_MODEL_LEN=1000000, GPU_MEM_UTIL=0.80, EXTRA_ARGS="--kv-cache-memory-bytes 42949672960 --cudagraph-capture-sizes 1 2 ... 64" - QUOTE it or bash runs the number as a command.
- Decode knobs from examples/tp3-throughput.env: GLM53_DENSE_FP8=dense,kda,shared,mla, EXL3_FUSED_MOE=1, EXL3_TEMP_ROWS_FUSED=64, GLM53_ADAPTIVE_K_SET=2,4,7.
- Expect KV pool ~3.21M tokens (recipe says 3.23x) as a sanity check.

## Boot mechanics
- Write launch scripts to a file and `setsid bash -c './start-tp3.sh >> ~/tp3_boot.log 2>&1' </dev/null &` (inner ssh eats stdin). Stop watchdog first (`systemctl --user stop glm-watchdog`).
- Boot ~8-10 min; per-rank logs ~/glm53-current/logs/{head,worker1,worker2}.log.

## Cooperative MoE (TP=3 ABI2)
- A locally built coop-build-tp3/cooperative_moe.so has a different hash than dispatch_policy.json -> must re-profile. Use CLEAN `git show HEAD:overlay/exl3.py` (prepare_profile pins STOCK_SHA 849e2588...), mounted over vLLM's exl3.py in the maintenance container.
- chown the bundle to adam first (container build leaves it root-owned).
- Sequence: test_contract (mount repo at /repo), test_cuda_integration x9 (ranks 0-2 x geometry 0-2, GLM53_COOP_QUALIFICATION=1), profile_shapes x9, select_policy --bundle + 9 logs, test_policy_gpu x3 (no qualification env), prepare_profile -> exl3-tp3.py; set EXL3_OVERLAY_HOST to it. ~5 min total. Verify each rank logs `prepared-layer summary: eligible=42`.
- Gain ~7-9% per decode step (structured 72->80, code 40->50 tok/s).

## Speed facts
- GB10 decode is memory-bandwidth-bound; `nvidia-smi -lgc 3003` gave 0 gain (SoC holds ~2.5 GHz); no nvpmodel on DGX OS.
- Benchmark with tests/bench_decode.py (sed MODEL to glm-53-flash-exl3); tok/s = accepted_per_step / decode_ms_per_draft_step. Python streaming harnesses undercount.
- NFS carries ~55 GiB per worker at boot only, zero during serving.

## Ops
- Stack file ~/.config/glm-stack.env (repo glm5.3-flash-dev scripts/glm53/glm-stack.env) drives spark-model, glm-watchdog.sh v8, glm-boot-hygiene.sh. Workers need py-spy, glm-mem-hygiene.sh and NOPASSWD sudoers (gdb, dmesg, py-spy, hygiene, swapoff/on).
- After stack changes: refresh glm5.3-flash-dev docs/spark-live-state.json (run refresh-spark-state.sh from CT106 if the laptop's agent can't reach spark1 by name) and check-doc-inventory.sh --ssh must be CLEAN.
