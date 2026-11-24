---
name: characterize-tune-spark-vllm-concurrency
description: "Find the real concurrency/throughput operating point of a vLLM model served on the DGX Sparks (DSV4-Flash TP2 etc.): sweep concurrency to separate the max_num_seqs config cap, the compute ceiling, and the KV/memory ceiling - then set max_num_seqs for the actual (large-context) workload."
---

# Characterize + tune a Spark vLLM serve's concurrency

Use when deciding how many concurrent agents/requests a Spark-served model can
take, or why single-stream is 'slow'. Separates three different ceilings.

## The mental model (proven on DSV4-Flash 2xSpark 2026-09-04)
- **Single-stream decode is memory-bandwidth bound**, not compute bound. Each
  token streams all active weights (~13B MoE params) from LPDDR5X once; batch=1
  leaves the tensor cores idle. ~30 tok/s floor (up to ~83 with high speculative
  acceptance). Not improvable except speculation / pruning / lower quant.
- **Aggregate throughput scales with concurrency** because batching amortizes
  that one weight read across N tokens (matrix×matrix vs matrix×vector). Rises
  until FLOPs saturate (compute ceiling) or KV runs out (memory ceiling).
- **Three ceilings, don't confuse them:**
  1. `--max-num-seqs` = a CONFIG cap. If aggregate plateaus exactly at par=cap
     with `num_requests_waiting` climbing beyond it and `max_running` pinned at
     the cap, that's the config, not the hardware. Raise it.
  2. Compute ceiling = where aggregate tok/s plateaus with small prompts and
     waiting stays 0 (KV not binding). For DSV4 2xSpark this is >64.
  3. KV/memory ceiling = pool_tokens / context_len. Read it from serve init:
     `Maximum concurrency for 1,048,576 tokens per request: X.Yx` → pool =
     X.Y × max_model_len. This BINDS the real large-context agent workload long
     before the compute ceiling.

## Method
1. Access the Sparks (user/pass adam/<KEY-AUTH: the fleet is KEY-ONLY: connect with the YubiKey SSH agent (see AGENTS.md 'Credential rule'), no password>) or, better, from the orchestrator
   CT whose key is authorized (avoids the UniFi IDS on rapid cross-subnet SSH).
   Persistent paramiko helper (spark.py) - reuse one connection, don't reconnect.
2. Pause any running batch cleanly with SIGSTOP on the omp agents (resumable, no
   lost work); wait for `vllm:num_requests_running`->0 before benchmarking.
3. Compute-ceiling sweep (small prompts): `omp bench <model> --profile generation
   --par P --runs 2*P --max-tokens 512 --json` for P in 8,16,24,32,48,64.
   Measure AGGREGATE server-side via delta of `vllm:generation_tokens_total`
   over wall time; poll max `num_requests_running`/`num_requests_waiting`.
4. KV-ceiling sweep (phase B): `--profile prefill --prefill-bytes <ctx>` (≈4
   bytes/token) at realistic agent context sizes, sweep par, watch
   `vllm:gpu_cache_usage_perc`->~1.0 and `num_requests_waiting`>0. That par is
   the memory ceiling at that context size = the real operating cap.
5. SIGCONT the agents.

## Tuning the cap (DSV4 example)
`dsv4_serve.sh` (spark1 head) carries all vllm args incl `--max-num-seqs`,
`--max-num-batched-tokens 8192`, `--gpu-memory-utilization 0.78`. Worker
(`dsv4_serve_worker.sh`, spark2) only joins ray. To change the cap: back up,
`sed -i 's/--max-num-seqs 12/--max-num-seqs N/'`, restart HEAD first (docker
stop/rm/run -d -> ray head + vllm waits for 2 GPUs) THEN worker (joins ray,
provides GPU2). ~8 min cold start (155GB weights + CUDA graphs + warmup); wait
for `Application startup complete` and `/v1/models`.

## Gotchas
- pgrep/pkill -f self-matches the wrapper `bash -c` cmdline containing your
  pattern → kills itself mid-command. Capture PIDs to a file in one step, kill
  from the file in a separate step (its cmdline has no pattern).
- SIGSTOP mid-decode leaves a sequence 'running' on the server (backpressure)
  until it finishes; expect a small residual after drain.
- Raising max_num_seqs does NOT enlarge the KV pool (that's gpu-mem-util); at
  large contexts you hit KV waiting well below the new cap. Set the operating
  max_num_seqs from the phase-B KV curve, not the compute ceiling.
