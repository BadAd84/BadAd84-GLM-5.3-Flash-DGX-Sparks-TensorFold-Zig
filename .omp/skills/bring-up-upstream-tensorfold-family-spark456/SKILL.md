---
name: bring-up-upstream-tensorfold-family-spark456
description: "Bring up and benchmark a model on the upstream TensorFold families (glm_cuda, flashnext, deepseek_v41) on the OTS spark4-6 dev triangle: env, NCCL/RoCE fabric config, the config-parity trap, kit generation, gates."
---

# Bring up a model family on upstream TensorFold glm_cuda/flashnext/deepseek_v41 on the OTS spark4-6 dev triangle

Use when validating or benchmarking a model on the upstream TensorFold families (post-faccd11c) on spark4/5/6, or when an A/B arm measures implausibly slow.

## Environment rules
- ssh ONLY from the Windows harness shell (`SSH_AUTH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg`); ssh from inside `wsl.exe` has no agent and hangs (measured repeatedly). WSL for tree/build work via `wsl.exe -e bash /mnt/c/.../<script>.sh`, scripts written LF.
- Every GPU job/boot under `flock -o ~/work/gpu.lock` on EACH box used. spark1-3 production = read-only. Paperclip agents share the boxes: never kill foreign containers; report wedged ones to the owner instead.
- Measurements per ai-engine AGENTS.md: off-port loopback serve, requests_total before/after each probe, 1/2/4/6/8 streams x3 interleaved cycles, exactness first (drafted==serial, concurrent==solo, resumed==fresh), never trust /health.

## The config-parity trap (2x measurement error, measured)
Upstream families boot with SAFE DEFAULTS (bf16 KV, bf16 dense). Our reference arms run q4 dense + fp8 KV. An arm benched on defaults measures ~half speed. Before ANY speed comparison: set `TF_GLM_DENSE_BITS=4`, `--kv-cache fp8`, and the copy-draft knobs; pass `--parallel`/`--context` explicitly. Re-run the exactness gates at the perf config (they must still pass).

## GLM-5.3-Flash on glm_cuda (spark4=0, 5=1, 6=2)
- Env: `TF_GLM_RANK=i TF_GLM_WORLD=N`, `NCCL_COMM_ID`, `TF_EXPERIMENTAL` NOT needed for glm.
- NCCL on GB10: HCAs are `rocep1s0fX/roceP2p1s0fX` (NOT mlx5_N). Exposing all four mispairs rails -> `ibv_modify_qp ETIMEDOUT`; pass per-cable pairs, OR production's shape: all four + `NCCL_CROSS_NIC=1 NCCL_IB_SUBNET_AWARE_ROUTING=1`. Bootstrap `NCCL_SOCKET_IFNAME=fablo0` (fabric loopback) on the dev ring; production spark1-3 uses `enP7s7`.
- Production TP=3 speed rides the OTS RoCE one-shot all-gather (TF_ROCE_*), not NCCL; upstream in-tree RoCE is world-2-only (world-3 port: sync/glm-perf 06046530). A TP=3 arm on plain NCCL will measure 13-20% under - check the boot log says the RoCE gather is active before trusting an arm.
- `TF_GLM_HEAD_BITS=8` is a free ~+4% (greedy sha unchanged). The old family's captured Triton kit CANNOT be wired into glm_cuda (it refuses kits, runtime-generates kernels); kernel-lineage gaps need real kernel work.
- Free wins ruled out by measurement: CUDA graphs (99.6% GPU-bound), KDA width knob (level).

## DeepSeek V4.1 on deepseek_v41
- Requires `TF_EXPERIMENTAL=deepseek` (gate #827) in the CONTAINER env (`--env-file`, not just the host shell - measured boot failure).
- Checkpoint gate: EXL3 1.x only, all-trellis. MiaAI EAQ v1.1 pack has 27 dense BF16 groups without suh/svh -> upstream refuses (MissingTensor, projection.zig requires trellises). EAQ v1 is all-trellis and boots. Kit: block emitters call captured-Triton ops; generate host-side (vendor/TensorFold @ c4646171 + jayleaton recipe 3 patches + triton_fill.py, Triton 3.7.1, ptxas 13.3, no GPU). `aot-needs` emits nothing for ~4 min/cell - do not timeout-kill it.

## Unattended chains
Long matrices run as a watcher + pipeline scripts on the box (logs + res/*.jsonl, one row per completed cell). Rank-death errors inside a cell self-heal via rank-1 verify/relaunch; judge liveness from log growth and cell-completion lines, not the row count alone. Keep the lane's report file updated after EVERY step - laptop crashes kill lanes, the report is the bank.
