---
name: diagnose-glm53-spark-wedge-and-serve-health
description: "Diagnose why a session using the OTS 2x DGX Spark GLM-5.3-Flash serve died, and prove the serve's real health: read the glm-watchdog log for wedge/restart events, read the auto-captured py-spy forensics (worker stack, not head), classify the hang, and verify with a live generation rather than /health."
---

# Diagnose a GLM-5.3-Flash (2x DGX Spark) wedge / serve death

Use when someone reports their session on the local GLM serve "crashed", hung, or errored - or when you need
to prove the serve is genuinely healthy. Serve: spark1 `:8888` (TP=3 since 2026-09-28), `ssh adam@spark1.ots-int.net`.

## 0. Silent death (the watchdog log stops mid-line) => the DISK filled

A full volume kills the serve AND makes glm-watchdog blind - its `log()` append fails, so
`~/glm-watchdog.log` ends mid-line and nothing is captured. Measured 2026-09-20: **both** nodes at 0
bytes free (201G head / 206G worker of NVMe KV cache, under a day of serving; the offload tier has no
eviction). Check FIRST, on BOTH nodes:

```
ssh adam@spark1.ots-int.net 'df -h / | tail -1; du -sh ~/.cache/vllm-glm53-flash/kv-nvme'
ssh adam@spark1.ots-int.net 'ssh adam@192.168.100.11 "df -h / | tail -1"'
```

Fix: `~/.local/bin/glm-disk-guard.sh --both` (prunes the KV cache to >= `GLM_WD_MIN_FREE_GB`, default
50G, on both nodes), and `docker rmi` superseded images (89G of images was the secondary hog). Since
2026-09-21 a 60s systemd --user timer on EACH node runs the guard, so a recurrence means the timer was
stopped/absent - check `systemctl --user list-timers glm-disk-guard.timer`.

## 1. Look at the watchdog FIRST (not the container)

The serve is supervised by `glm-watchdog` (user unit, v7). It wedges-detects and auto-restarts, so a
"crash" is usually the watchdog killing a hung engine - which is exactly what kills in-flight requests.

```
journalctl --user -u glm-watchdog --since "-30 min" --no-pager | tail -20
ssh adam@spark1.ots-int.net 'tail -40 ~/glm-watchdog.log'
```

Signatures in `~/glm-watchdog.log`:

- `WEDGE: running=N waiting=N frozen 10 samples (P=<prompt> G=<gen>) -> capture+recovery` - engine hung;
  the watchdog captured forensics, `docker kill`ed both ranks, swap-cycled, ran hygiene, restarted.
  Total downtime ~6 min (`boot-hygiene: serve healthy after N passes`).
- `metrics unreachable for 40 samples -> starting glm` - serve down/not answering metrics at all.

The tell that a restart happened: `docker ps` shows both containers **Up N minutes** where N is shorter
than the session that died (`glm53-exl3-head` + `glm53-exl3-worker`, the latter on 192.168.100.11).

Wedge counts here are historically recurring (6 since 2026-09-16; also tracked in
`glm5.3-flash-dev/docs/GLM53-SPARK-UPSTREAM-WATCHLIST.md`) - a wedge is a known class, never blame the user/config
without evidence.

## 2. Read the forensics - the WORKER stack is the answer

The watchdog saves `~/wedge-capture-<ts>/` on the head: `head-pyspy.txt`, `worker-pyspy.txt`,
`head-sys.log`, `head-docker.log`, `worker-docker.log`.

- **Head's EngineCore legitimately looks stuck** in `_wait_for_response` / `shm_broadcast get_response` /
  `step_with_batch_queue` - it is waiting for the worker. Ignore it as a cause.
- **Read Worker_TP0's MainThread** in `head-pyspy.txt`. Measured root cause of our wedges:

```
Thread NNNN (active): "MainThread"
    synchronize (torch/cuda/streams.py:108)
    apply_exl3_fused_moe (vllm/model_executor/layers/quantization/exl3.py:1544)
    apply_exl3_experts -> ... -> execute_model
```

  = a silent GPU hang in the fused EXL3 MoE (FAST) decode/prefill path - the CUDA kernel never completes,
  so `cuda.synchronize()` blocks forever.
- Check `head-sys.log` for `Xid` / `nvrm` / `oom` (grep). Absent = a silent hang, not a driver fault or
  host OOM.
- Check `worker-docker.log` tail for the last thing it was doing (e.g. `exl3 fat-expert P0: layers=...`).
- Known capture gaps: `worker-pyspy.txt` often 0 bytes, and py-spy `--native` fails
  (`UNW_EBADREG: bad register number`). Fix the capture before drawing conclusions about the worker's
  native frame - do not assume "no stack" means "no worker involvement".

## 3. Prove the serve's real health (health endpoints LIE)

`curl :8888/health` → 200 and `GET /v1/models` both succeed **even on a wedged engine**. Only a real
completion proves it:

```
curl -s -m 120 http://localhost:8888/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"glm-53-flash-exl3","messages":[{"role":"user","content":"Reply with exactly: GLM-HEALTHY-OK"}],
       "max_tokens":64,"temperature":0,
       "chat_template_kwargs":{"enable_thinking":false}}'
```

- Thinking-off kwarg for this template is `chat_template_kwargs {"enable_thinking": false}`;
  `{"thinking":{"type":"disabled"}}` is silently ignored (reasoning-only output, no content).
- Healthy = the exact reply comes back in well under a second with sane usage counts.
- Also worth checking: both containers Up, `systemctl --user is-active glm-watchdog` = active,
  and the watchdog's `boot-hygiene` line showing the last boot completed.

## 4. Report and options

State: (a) serve currently up/hung + evidence, (b) the watchdog event that killed the session with its
21:02-style timestamp, (c) the root-cause stack from the capture, (d) whether it is the known recurring class.

Mitigation options to offer (owner decides):
1. Accept - watchdog recovers in ~6 min; cost is an occasional killed session.
2. A/B `GLM53_EXL3_MOE_FAST=0` (drops the fused FAST MoE tier, ~4-5 tok/s structured) via `~/arm_boot.sh`
   to see whether wedge frequency falls.
3. Improve the capture (worker py-spy + a working native unwinder) before chasing it upstream.

Campaign rules: STOP the watchdog before any manual boot (`systemctl --user stop glm-watchdog`), never
`pkill -f` with a literal pattern (it self-matches your ssh shell), and A/B with `~/bench_arm.sh`
never-seen prompts only.
