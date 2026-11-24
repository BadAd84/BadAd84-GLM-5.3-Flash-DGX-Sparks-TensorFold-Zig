---
name: tune-dgx-spark-vllm-serve-ceilings
description: "Find the compute, KV-memory, and speculation ceilings of a vLLM MoE serve on the 2x DGX Spark (DSV4/GLM/Qwen) and pick the batch operating point - concurrency sweep, KV pool from init log, speculation k-sweep, done from the orchestrator CT."
---

# Tune a vLLM DGX-Spark serve: concurrency / KV / speculation ceilings

Use when deciding the operating concurrency + speculation depth for a served MoE
(DSV4-Flash, GLM-5.3-Flash, Qwen) on the 2x Spark, or answering 'do we have
headroom / should we run more agents'.

## Access (do this first)
- Sparks are **user/pass** `adam/<KEY-AUTH: the fleet is KEY-ONLY: connect with the YubiKey SSH agent (see AGENTS.md 'Credential rule'), no password>` - NOT YubiKey (the gpg-agent bridge
  refuses to sign for them). Connect via paramiko password. Proxmox host is
  `root/<KEY-AUTH>` @192.168.99.100.
- Cross-subnet paramiko to the Sparks trips the UniFi IDS (connection reset mid-auth).
  Authorize the orchestrator CT's key on both Sparks once, then drive them
  **from CT 101** (`pct exec 101 -- su - adam -c 'ssh adam@192.168.3.10 ...'`,
  intra-subnet, no IDS). Or ask owner to suppress the IDS sig per-host.
- Persistent-connection helpers avoid re-auth storms: one paramiko client reused
  (`spark.py` pattern) per host.

## Serve restart (TP2 ray) - needed to change any launch flag
- Head: `~/dsv4_serve.sh` on spark1 (docker stop/rm/run -d; starts ray head + vllm
  which waits for 2 GPUs). Worker: `~/dsv4_serve_worker.sh` on spark2 (joins ray).
- Order: run head, `sleep 20`, run worker. ~8 min cold start (weights 131s, CUDA
  graphs + mHC/FlashInfer warmup ~4min). Ready = `docker logs | grep 'Application
  startup complete'` and `/v1/models` responds. Back up the script before editing.

## Ceiling 1 - concurrency / compute (bench_conc.py pattern)
- SIGSTOP the running batch agents (resumable, no lost work), wait
  `vllm:num_requests_running`->0, sweep `omp bench MODEL --profile generation
  --par N --runs 2N --max-tokens 512 --json` for N in [8,16,24,32,48,64].
- Per level: aggregate tok/s = delta(`vllm:generation_tokens_total`)/wall; poll
  max `num_requests_running` + `num_requests_waiting`. SIGCONT agents at end.
- Ceiling = where `max_running` pins at `max_num_seqs` and `waiting` climbs. If it
  never plateaus (still rising at 64, waiting=0) the cap is just the config -
  raise `--max-num-seqs` in the head script and re-sweep. (DSV4: 12 was config;
  64 gave 243 tok/s, no compute plateau for small contexts.)

## Ceiling 2 - KV / memory (READ it, don't slow-sweep)
- Synthetic large-prefill sweeps are impractically slow. Instead read the init log:
  `GPU KV cache size: N tokens` and `Maximum concurrency for <max_model_len>
  tokens per request: X.Yx`. Also `cache_config_info{num_gpu_blocks=...}` x block_size.
- Effective concurrency = KV_tokens / avg_context_tokens. DSV4: 1.42M tokens ->
  ~8 concurrent at 150K ctx, ~14 at 100K, ~64 (seq cap) at <22K.
- Confirm LIVE under real load: `vllm:kv_cache_usage_perc` and
  `num_requests_waiting{reason="capacity"}`. For large-context agents KV is the
  real wall, not compute.

## Ceiling 3 - speculation (measure acceptance on REAL content)
- Snapshot `vllm:spec_decode_num_drafts_total`, `_num_draft_tokens_total`,
  `_num_accepted_tokens_total`; fire representative requests; diff. accepted/drafts
  = accepted-per-cycle (+1 base = tokens/forward). DSV4 DSpark: RE/disasm content
  66% accept, 4.2x, ~55 tok/s single; prose 23%, 2.2x, ~30 tok/s.
- `num_speculative_tokens` MUST be a multiple of `n_predict` (=5 for DSV4 DSpark).
  Non-multiples fail pydantic validation at startup. **k=10 CRASHES at runtime**
  with `CUDA error: illegal memory access` (this build's MTP kernel only does 1
  round) -> speculation hard-capped at 5. Don't burn restarts past k=5.

## Interpreting for the batch
- Single-stream decode is memory-bandwidth bound (must stream all active MoE
  params per token); it's a hardware constant. Concurrency converts idle compute
  into aggregate throughput. Speculation converts idle compute into per-stream
  speed - but only up to the kernel's supported depth.
- If large-context agents are KV-bound AND speculation is kernel-capped, the
  compute headroom is stranded. Levers: smaller per-agent prompts (more fit KV),
  higher `--gpu-memory-utilization` (bigger KV pool, small OOM risk), or a fixed
  multi-round MTP kernel (deep upstream work).

## Gotchas
- Kill batch processes by **PID file** not `pkill -f pattern` - the `bash -c`
  wrapper's own cmdline contains the pattern and pkill self-terminates mid-command
  (pgrep>file in one exec, `kill -9 $(cat file)` in the next).
- `pct exec` runs as root; omp needs `su - adam -c`. sftp lands on the HOST; use
  `pct push/pull` into the CT.
- Orphaned `omp bench` children survive a killed parent and keep holding server
  slots - kill them by explicit PID.
- Warm the serve (a few requests) before benching; first request after cold start
  is ~30% slow.
