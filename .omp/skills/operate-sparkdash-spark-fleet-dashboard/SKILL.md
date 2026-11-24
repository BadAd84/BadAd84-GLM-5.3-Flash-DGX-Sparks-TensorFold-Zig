---
name: operate-sparkdash-spark-fleet-dashboard
description: "Build, wire, or debug sparkDash (MiaAI-Lab fleet dashboard) on a Proxmox CT for the DGX Sparks; not other dashboards."
---

sparkDash (github `MiaAI-Lab/sparkDash`) is a Node web dashboard showing GPU/CPU/VRAM/process + LLM
metrics for the DGX Sparks. It runs on **CT111** at `sparkdash.ots-int.net` (`192.168.99.111:5555`, UniFi
reservation + DNS in place) wired to spark1-6. Metrics come over SSH (GPU/CPU via `nvidia-smi`) + HTTP `:8888` (the LLM probe).

## Build + wire on a fresh CT
1. Ubuntu 24.04 CT, YubiKey key + Europe/London TZ (fleet rules). ~2c/2GB/12GB is plenty.
2. Node 22 (NodeSource; the repo file is `/etc/apt/sources.list.d/nodesource.sources`). `git clone
   https://github.com/MiaAI-Lab/sparkDash /opt/sparkDash`; `npm install && npm run build`.
3. `/opt/sparkDash/.env`: `PORT=5555`, `BIND_HOST=0.0.0.0`, `SPARKDASH_TOKEN=<secret>`,
   `SPARKDASH_ALLOW_OPEN_REMOTE=0` (require the token), `LLM_PORT=8888`,
   `SSH_IDENTITY_FILE=/root/.ssh/id_ed25519`.
4. **Generate the SSH key BEFORE first-starting the service** (see gotcha). Append its pubkey to
   `adam`'s `~/.ssh/authorized_keys` on each Spark (`/home` persists across kindling spark-os reboots).
5. systemd `sparkdash.service`: `ExecStart=/usr/bin/node server/index.js`,
   `WorkingDirectory=/opt/sparkDash`, `EnvironmentFile=/opt/sparkDash/.env`.
6. Register each Spark: `POST /api/sparks` (Bearer token) with
   `{id,name,lanIp,ssh:{host,user,auth:"key",port:22},llmPorts:[8888],role,workerNode}`.
   `role` = head/worker/standalone; workers auto-disable `llmMonitoring` (correct). Config lands in
   `/opt/sparkDash/config/sparks.json`.

## Debug gotchas (each cost real time)
- **Per-Spark metrics are nested under `metrics`, NOT top-level.** `GET /api/sparks/:id/metrics`
  returns `{id,online,uptime,hardware,...,metrics:{gpu,cpu,memory,llm,...}}`. Probing `d["gpu"]`
  returns empty - use `d["metrics"]["gpu"]`. GPU = `{temperature,usage,power:{draw,limit,systemDraw},
  vram:{used,total,percentage,available},processes}`; CPU = `{usage,temperature}`; LLM = an ARRAY
  `[{available,backend,modelId,models,slotsActive,slotsTotal,generationTps,prefillTps}]`. `hardware`
  (GB10/128GB) is top-level and separate from the live `metrics`.
- **Collectors need the SSH identity at STARTUP.** If the key is generated AFTER `sparkdash` starts,
  the log shows `preflight warning: No SSH identity is configured` and GPU/LLM stay empty - RESTART the
  service once the key + `.env` are in place.
- **The LLM probe needs the serve HTTP-reachable on `:8888`.** The Spark serves (GLM/Qwen tensorfold)
  flap under heavy load - `/health` can hang (connect-then-no-response, `curl` returns `000`) for
  minutes then recover via the watchdog, and a parked serve shows no model loaded (VRAM drops to a few
  %). So LLM `available:false` is usually the SERVE's transient state, not a sparkDash bug. GPU/CPU
  metrics (over SSH) stay stable regardless. Confirm by curling `:8888/health` from several hosts: a
  per-serve flap (one serve `000`, others `200`) that flips between polls is the tell.
- **`online:true` + empty `metrics` is a startup transient** - the monitor marks every spark
  `unreachable (no liveness) - pausing` at boot then `reachable again - resuming` within ~1s. SSH to
  the Sparks is fast + reliable (~300 ms); the flap is startup-only.

## Access + security
`http://<ct-ip>:5555`, bearer token (in `/root/sparkdash.token`). The SSH key is full `adam`-level
(collectors need command access); "read-only" is operational - the token gates access and you simply
don't use the power / start-stop controls. CT is DHCP by default; add a UniFi reservation for a stable URL.
