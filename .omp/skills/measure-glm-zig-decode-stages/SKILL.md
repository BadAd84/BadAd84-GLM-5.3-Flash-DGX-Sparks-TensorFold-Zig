---
name: measure-glm-zig-decode-stages
description: "Method to measure the ai-engine Zig GLM engine's decode stages, draft acceptance and A/B arms on spark4-6 without being misled by instrument bugs."
---

# Measuring the Zig GLM engine's decode (spark4-6)

Use when a GLM speed claim or A/B must be produced on the dev triangle (spark4-6, TP=3) against production (spark1-3).

## Instruments and their traps

- **Per-stage times**: boot with `TF_GLM_PROF=1` (via the serve launcher's XENV hook); the engine prints `glm prof verify N rows (64 calls): wall ... kda ... routed ...` per width. The rows accumulate over ALL layers of one forward (42 MoE layers), so never divide one layer's bytes by them - that mistake understates bandwidth by 42x.
- **Counters** (rounds, drafted, accepted, tokens): `/metrics` with `--metrics-open` (Prometheus, prefix `tensorfold:`), NOT `/health` (no counters) and NOT `/stats` (needs `--dashboard`). Parse by taking the key after the last colon.
- **Throughput**: `~/glmrepro/streams.py <port> <P> --rounds 3 --max-tokens 400 --each 1 --tag <tag> --out <file>` - `--out` is mandatory; without it the run errors and sends nothing, and an A/B then reports all zeros.
- **Exactness**: `~/glm-run/gate.py <port> --tag <tag> --out <file>` runs smoke, drafted==serial, concurrent==solo, resumed==fresh. Run it on every arm.

## Boot and A/B harness on the boxes

- Launchers: `serve3.sh RANK P` (TP=3), `serve4.sh` (same plus an `XSERVE` hook for extra serve flags and a `~/dflash2` mount), `serve2p.sh` (world 2, spark4+5, with XENV/XSERVE hooks). Env extras go through `XENV='-e NAME=VAL ...'` (docker `-e`) and serve flags through `XSERVE='--metrics-open --drafter /dflash2'`.
- Every cell must take `flock -o ~/work/gpu.lock` and end with `stop3.sh`, which removes the rank containers on all three boxes - so NEVER run two chains at once (they destroy each other's serves).
- Interleave arms, one fresh boot per setting, and record the boot line: `RoCE all-gather: N rank(s), M link(s) over K HCA(s)` means the RoCE wire came up; a `warning: ... PeerRefused ... NCCL carries every gather` means it did not and the arm is really NCCL.
- Any chained script that waits on a marker in another script's log must have that marker relayed (copy the log) or it will sit idle for its whole timeout.

## Discipline

- Measure before proposing a mechanism: profile first, name the hot stage, then change one thing.
- A roofline check kills kernel work fast: expert bytes per forward / routed ms should be ~211-254 GiB/s on GB10; if it is, there is nothing to re-tile.
- No change ships on P=1 alone: run 1/2/4/6/8, and if the change alters a partition (like an aligned head split), compare reply digests between arms before calling it free.
