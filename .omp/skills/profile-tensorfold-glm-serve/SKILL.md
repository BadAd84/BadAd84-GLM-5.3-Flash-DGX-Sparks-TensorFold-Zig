---
name: profile-tensorfold-glm-serve
description: "Profile TensorFold GLM serve on Sparks (stage profile, py-spy dumps, nsys) - privileges, wedges, unbuffered prints"
---

# Profile the TensorFold GLM serve (spark1-3)

Use for a speed campaign on the GLM-5.3-Flash TensorFold serve (or another TensorFold family). Cheapest instrument first; every arm on FIXED prompts with identical replies.

## 1. Engine stage profile (no rebuild)
- `TF_GLM_MULTI_PROFILE=20`: rank 0 prints `multi profile (batched), 20 rounds: ... ms a round: wall = plan + message + propose + verify + sample + accept + commit + taps + emit; verify GPU N`. `sample` includes waiting for the verify readback; `verify GPU` is the forward.
- `TF_GLM_PROFILE=1`: per-block prefill timing after a prefill (chunked fills may only report small ones).
- TRAP: the reports are plain unflushed `print`s, so nothing reaches `docker logs` without `PYTHONUNBUFFERED=1` in the container. The recipe's start.sh forwards only `TENSORFOLD_*`/`TF_GLM_*`/`TF_ROCE_*`, so set it in an image wrapper (`/usr/local/bin/tensorfold` -> exports + exec `tensorfold.real`).

## 2. Host stacks
- py-spy 0.4.2 `record` HANGS on this serve. Use a dump loop in a sidecar:
  `docker run --rm --pid=container:glm53-flash-tf --cap-add SYS_PTRACE -v /usr/local/bin/py-spy:/usr/local/bin/py-spy:ro --entrypoint bash <image> -c 'end=$((SECONDS+25)); while [ $SECONDS -lt $end ]; do echo "=== sample"; py-spy dump --pid 1 --nonblocking; done' > dumps.txt`
  then aggregate the innermost frames of the `_loop` thread (~24 dumps/s).
- tf-v18 result: 89-97% of rank 0's host time is the verify readback (`multi.py:329` sample_streams `.cpu()`), so host Python is not the bottleneck.

## 3. nsys timeline
- Image wrapper: rank 0 only under `nsys launch --session-new=glm --trace=cuda,nvtx --cuda-graph-trace=node --wait=primary`; other ranks unchanged. Capture: `docker exec glm53-flash-tf nsys start --session=glm -o /cache/nsys/<name> --force-overwrite=true --sample=none --cpuctxsw=none`, sleep, `nsys stop --session=glm`.
- TRAPS (each cost a boot):
  - `nsys launch` REJECTS `--sample`/`--cpuctxsw` ("not supported by the launch command"): rank 0 exits with code 1 at boot. Those switches go to `nsys start`.
  - Without `--cap-add SYS_ADMIN` on the container, CUPTI returns `CUPTI_ERROR_INSUFFICIENT_PRIVILEGES`: the capture holds NVTX only ("no GPU activity"). Add it to `RUN_ARGS` in a COPY of the recipe tree, never in production.
  - Graph-node tracing WEDGED rounds: with `osrt` + RoCE gathers on the first try, and with NCCL + SYS_ADMIN after the first capture (round stuck > 90 s). Always run a guard (poll `/health` `iteration_s`; stop the serve past 90 s), use `COMM=nccl`, and copy `/cache/nsys/*.nsys-rep` (host `~/.cache/tensorfold-glm53/<kc>/nsys`) out BEFORE teardown.
  - Tracing slows the round ~3.5x (127 vs 36 ms), so read kernel SHARES as indicative, not absolute.
- Analysis: `nsys export --type=sqlite`, then busy/idle gaps from `CUPTI_ACTIVITY_KIND_KERNEL`/`MEMCPY` and host API totals from `CUPTI_ACTIVITY_KIND_RUNTIME`.
- tf-v18, 1 stream: GPU busy 96.4%; dec_kernel (EXL3 experts) 39%, qmm 24%, NCCL AllGather 18% (NCCL arm; production uses faster RoCE), l2pf 12%. Decode is GPU-bound: candidate wins must cut GPU work (expert weight reads, gathers).

## 4. Hygiene
- Profiling boots use a scratch tier (`TF_GLM_KV_TIER=/cache/kvtier-prof`): production's tier evicts by json mtime.
- Stop the watchdog before manual boots and restore production after (`glm-v18-start.sh`), then restart the watchdog.
- In bash drivers, `wait` with no args also waits on a background guard loop forever: wait on client PIDs only.
- Compare arms on fixed prompts: sdbench, or a fixed-seed long prompt sent twice (cold fill, then decode-only). ms/round follows tokens/round, so never compare random-prompt depth runs.
- Scratch tools (laptop `work/v18/prof/`, copies in spark1 `~`): prof_nsys.sh, nsys_gaps.py, pyspy_agg.py, longdec.py, ctxcurve.sh.
