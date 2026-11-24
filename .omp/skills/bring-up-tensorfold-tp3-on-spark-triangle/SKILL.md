---
name: bring-up-tensorfold-tp3-on-spark-triangle
description: "Bring up, debug, or extend the TensorFold GLM-5.3-Flash TP=3 port on the 3-Spark triangle (the --tp 3 lift of the 2-Spark recipe)"
---

# Bring up TensorFold GLM-5.3-Flash at TP=3 on the DGX-Spark triangle

The MiaAI-Lab TensorFold recipe hard-caps `--tp` at 2. The port to 3 ranks is in
`glm5.3-flash-dev/scripts/glm53/tp3/` + `docs/GLM53-TENSORFOLD-TP3-PORT.md`. It WORKS and is +17.7%
single-stream vs TP=2 (no-drafts). Use this to relaunch, debug, or extend it.

## Preconditions (NON-NEGOTIABLE)
- **Stop the live vLLM serve first** (`~/.local/bin/spark-model glm stop` on spark1 + stop the
  watchdog): TP=3 needs all 3 GB10s. Verify ~117 GB free per Spark before anything heavy.
- **NEVER run the presplit tool (or any big job) on a serving Spark.** The GB10 has unified memory;
  exhausting it HARD-FREEZES the box (no ping/ssh, recovers only via OOM-kill or power cycle). The
  tool streams one tensor at a time, but still do it with the serve down.

## Artifacts (already staged on all 3 Sparks)
- `~/glm53-tp3-ranks/rankR` - per-rank folder (uneven-thirds dense/attn + expert-half experts).
  Regenerate on spark r: `python3 ~/tp3port_presplit.py --src <ckpt> --out ~/glm53-tp3-ranks
  --world 3 --only-rank r` (rank0/1 from 9eaebb7c, rank2 from 25a44fdb - byte-identical mirror).
- `tensorfold-glm53:tp3` docker image on all 3 (v0.5.0 + patched .py COPY).
- `~/tp3src/*.py` - patched engine files, MOUNTED at runtime by the launch script (edit + relaunch,
  no rebuild).

## Launch (order matters)
`bash ~/launch_tp3.sh 0` on spark1 (HEAD, binds NCCL store), THEN `1` on spark2, `2` on spark3.
Head-first avoids an NCCL rendezvous race (error 6). API on spark1:8890. Ring config baked into the
script: identities 10.0.0.1/.2/.3, master 10.0.0.1, NCCL_IB_HCA=rocep1s0f0,rocep1s0f1, GID 4,
bootstrap enP7s7, COMM=nccl.

## Verify
- Health: `curl -s localhost:8890/health`. Decode test: a greedy completion ("17 times 23" -> 391).
- Bisection oracle when debugging: `launch_tp2.sh` runs the SAME patched code at --tp 2 on the full
  checkpoint (mount the whole HF cache so config.json symlinks resolve). If TP2-patched is correct
  but TP3 isn't, the bug is in the world>=3 branches.
- Speed/diff: `compare.py <port> <label> <out.json>` captures greedy outputs + decode tok/s from the
  serve's own /health counters; run on 8890 (TP3) and 8891 (TP2) and diff.

## Key design facts (for debugging)
- Dense/attention split UNEVEN THIRDS (22/21/21 heads), no padding - kernels are per-head, reduction
  is over hidden (equal). hc_post/residual_add already loop range(1,WORLD).
- Experts use EXPERT-HALF parallelism: each expert's two NI=1024 halves (the TP2 trellis split) go to
  2 different ranks (half0->e%3, half1->(e+1)%3). This is REQUIRED because the fast decode kernel
  (exl3.cu) is hardwired NI=1024; full-width EP (NI=2048) misses it and the fallback grouped path is
  wrong at R=1 decode (symptom: first token right, every decode token "!").
- Diagnostic: "prefill correct (first token right) but decode garbage" => decode MoE kernel path.
- All gathers must be world-general: fixed engine `_share`/`_gather_ints`/`_calibrate` (were empty((2
  *...))); decode.py/verify.py KDA reserve must use w.LL not lin_heads//world (uneven heads).

## Restore production when done
Stop TP3 containers on all 3 (`docker rm -f glm53-tp3`), `~/.local/bin/spark-model glm start`,
re-enable `glm-watchdog glm-disk-guard.timer`, verify Hermes (`hermes -p worker chat -q "..."`).
A failed vLLM boot after TP3 experiments usually just needs a clean `./stop.sh tp3` then restart.

## Open work
With-drafts speed (dflash2.py still splits by world; 32/8 heads %3!=0 - thread draft_world there),
dual-rail RoCE (TF_GLM_COMM=roce, ROCE_MAX_PEERS=16 supports 3), package as recipe patch 0054,
long-context/concurrency benchmarks at the 4x720k workload.
