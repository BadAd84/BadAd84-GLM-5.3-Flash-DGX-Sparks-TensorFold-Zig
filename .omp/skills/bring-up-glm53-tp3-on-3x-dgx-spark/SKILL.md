---
name: bring-up-glm53-tp3-on-3x-dgx-spark
description: "Bring up / repair the MiaAI-Lab GLM-5.3-Flash-EXL3 TP=3 serve on 3 DGX Sparks (directed RoCE ring, NFS weights, cooperative MoE) - the traps that cost a day"
---

# GLM-5.3-Flash TP=3 on 3x DGX Spark - bring-up

Recipe: `~/glm53-current/start-tp3.sh` + `.env.tp3` on spark1; README section "3x Spark (TP=3)" holds this kit's pins. MATCH THE RECIPE - every improvisation (own addressing, rsync'd weights) cost hours.

## Fabric (recipe scheme; do this first)
- Directed ring: each node Port0 (`enp1s0f0np0`) -> next node Port1 (`enp1s0f1np1`). Confirm cabling with LLDP. Rank order MUST follow ring direction (here spark1 -> spark3 -> spark2: WORKER_IP=spark3, WORKER2_IP=spark2).
- Loopback identities `10.0.0.1/.2/.3` on an NM dummy (`nmcli con add type dummy con-name fab-lo ifname fablo0 ...`), NOT `ip addr ... dev lo` (not persistent).
- Cable /24s: head<->w1 `10.0.22.x`, head<->w2 `10.0.23.x`, w1<->w2 `10.0.33.x`; /32 routes to each peer loopback via the direct cable; MTU 9000, never-default; all via `nmcli con mod` (manual `ip addr` gets dropped by NM).
- Verify: ping all loopbacks from every node + `ping -M do -s 8972`.

## .env.tp3 pins that matter
- HEAD_IP/WORKER_IP/WORKER2_IP = 10.0.0.x; WORKER_SSH/WORKER2_SSH stay on the LAN (separate override).
- `NCCL_IB_GID_INDEX`: re-read after ANY re-address (`/sys/class/infiniband/<dev>/ports/1/gid_attrs/types/N` = RoCE v2 with `::ffff:<ip>`). It moved 3 -> 4. Preflight error "set NCCL_IB_GID_INDEX ... populated indices" = wrong index.
- CX7 pins: DUAL-HCA (`rocep1s0f0,rocep1s0f1` on every rank). The recipe's single-HCA pins fail on a direct-cabled ring: `ibv_modify_qp ... 110 Connection timed out` INIT->RTR between GIDs on different cables.
- `SOCKET_IFNAME=<mgmt LAN>`, `NCCL_CROSS_NIC=1`, `NCCL_IB_SUBNET_AWARE_ROUTING=1`.
- `NFS_SHARE=1` with `NFS_SERVER_IP_1/2` = head's IP on each worker's cable, `NFS_CLIENTS` covering the cable /24s. REQUIRED: with local rsync'd copies InstantTensor fails `buffer_size ... exceeds device memory budget` on workers (budget tracks GPU_MEM_UTIL; no util value fits). `LOAD_FORMAT=` (empty) boots but ~2x slower load.
- `EXTRA_ARGS="--kv-cache-memory-bytes 42949672960 ..."` MUST be quoted (unquoted = "command not found", silently wrong args).
- MAX_MODEL_LEN=1000000, GPU_MEM_UTIL=0.80. Expect KV ~3.21M tokens (recipe 3.23x) = sanity check you match.

## Cooperative MoE (TP3 ABI2) - built binary never matches the shipped policy hash
Serve stopped; mount clean `git show HEAD:overlay/exl3.py` over vLLM's exl3.py; run in the image with `GLM53_COOP_MAINTENANCE_TEST=1 GLM53_COOP_QUALIFICATION=1 GLM53_COOP_EP_RANK={0,1,2} GLM53_COOP_GEOMETRY={0,1,2}`: `test_cuda_integration.py` x9, `profile_shapes.py` x9 (~14 s each), then `select_policy.py --bundle` (chown bundle to adam first - container build leaves it root-owned), `test_policy_gpu.py` x3 without qualification, `prepare_profile.py --stock <clean exl3> --bundle`. Set `EXL3_OVERLAY_HOST=<bundle>/exl3-tp3.py`; launcher stages to workers. Verify each rank logs `prepared-layer summary: eligible=42`.

## Benchmark correctly
Use `tests/bench_decode.py` (sed MODEL to the served name) and READ its `tok_s_median`. Never compute accepted_per_step/step_ms - a spec step emits accepted+1 tokens. Measured: 92.1/62.5/41.8 struct/code/prose (coop on) vs recipe 87.8/54.9/39.6. Clock locking does nothing (memory-bound).

## Ops
- Launch/stop from files (`setsid bash -c './start-tp3.sh >> ~/tp3_boot.log 2>&1' </dev/null &`), never `bash -s` pipes (inner ssh eats stdin). Boot ~6-9 min.
- Watchdog v8 / spark-model / boot-hygiene read `~/.config/glm-stack.env` (repo glm5.3-flash-dev `scripts/glm53/`). Stop the watchdog before manual boots.
- NFS carries only boot-time weight reads (~55 GiB/worker, zero while serving).
