---
name: debug-glm-engine-device-fault
description: "Debug a device fault (crash, hang, empty response) in the ai-engine TensorFold GLM serve on the spark4-6 TP=3 triangle without burning 30-minute build cycles."
---

# Debugging a GLM engine device fault on the OTS Sparks

A TP=3 cell costs ~4 minutes of boot and an image build ~20-25 minutes, so a
build-boot-guess loop burns half an hour per hypothesis. Do not use it.

## 1. Validate the harness before trusting a failure

Boot a THIN model: `TF_GLM_LAYERS=1` (~55 s instead of ~190 s). It still runs the
KDA, attention and prompt kernels.

Always run the same harness once with the change OFF and confirm a completion comes
back. A harness that fails both ways proves nothing.

Send ONE tiny non-streaming completion and print the body:

    curl -s -m 120 -X POST http://127.0.0.1:8300/v1/completions \
      -H 'Content-Type: application/json' \
      -d '{"model":"glm","prompt":"The capital of France is","max_tokens":8}'

An empty body means the server died - that is NOT the same as an HTTP error, and it
is NOT the same as a slow reply.

## 2. Read the right log

Rank 0 usually shows nothing. The follower ranks (`~/glmperf/logs/tp3-r1-*.log`,
`tp3-r2-*.log`) carry the first error. A pair of "following rank N stopped
(CudaContextLost)" messages on both ranks means one died first - look for the error
line just above it.

Distinguish the classes:

- `CUDA_ERROR_ILLEGAL_ADDRESS (700)` = bad access; sanitizer will localise it.
- `CUDA_ERROR_LAUNCH_FAILED (719)` = unspecified launch failure, which ALSO covers a
  kernel launched with invalid geometry (grid/block derived from a size that the
  change altered). A memory sanitizer reports nothing for this class - do not keep
  hunting overruns.
- A mutual CudaContextLost with no other error = a hang torn down.

## 3. Instrument one cycle

Wrap the engine in the sanitizer (it is in the image at `/usr/local/bin/ncu` and
`/usr/local/cuda/bin/nsys`; compute-sanitizer is on PATH):

    docker run --entrypoint compute-sanitizer ... "$IMAGE" \
      --tool memcheck --print-limit 4 tensorfold-native serve ...

NCCL's own `cudaErrorNoKernelImageForDevice` from `ncclInitKernelsForDevice` fires on
every boot under the compat driver. It is noise; ignore it. Only "Invalid __global__"
lines matter.

For a launch-geometry suspect, boot with `CUDA_LAUNCH_BLOCKING=1` so the failing
launch is the last one before the error, or use
`compute-sanitizer --kernel-name-base demangled --launch-timeout 0` to name the kernel
at the launch rather than at the sync.

## 4. Measure with the engine's own counters

`/health` has no counters. They are Prometheus gauges on `/metrics`, which only
renders with `--metrics-open`:

    decode_rounds_total, mtp_drafted_total, mtp_accepted_total, generation_tokens_total

`glmrepro/streams.py` needs `--out FILE`; without it, and with output captured, it
fails silently and the counters read as zero.

Read tok/s AND tokens-per-round: tokens/round is the drafter, ms/round is the engine.
Production reference on the same prose prompt set: 3.23 drafted/round, 2.06 accepted
(63.8%), 3.07 tokens/round, 36.4 ms/round.

## 5. Cross-rank agreement rules

- Every rank must pack the same number of linears (the boot line says so; a mismatch
  is a plan bug, not a stride bug).
- Ranks may legitimately carry DIFFERENT row widths (a head split is uneven by
  construction), so "make every rank the same width" is a hypothesis to test, not an
  assumption - an ALIGN=8 split with different widths per rank was measured working.

## 6. Traps

- `TF_GLM_MM=0` cannot isolate the generic matmul path: packed 4-bit weights require
  glm_mm and the engine refuses to load (`PackedNeedsGlmMm`).
- `pkill -f <pattern>` over ssh kills your own session when the pattern matches the
  command line you just sent. `pgrep` first, then `kill <pid>`, or bracket the pattern.
- A drafter folder must be MOUNTED into the container or the engine reports
  "neither a directory nor a repo id".
- Fetch weights from Hugging Face directly on the Spark (~100 MB/s); relaying a tar
  through the laptop pipe runs at ~1 MB/s.
- Dump the production env before tuning parity knobs:
  `docker inspect glm53-flash-tf --format '{{range .Config.Env}}{{println .}}{{end}}' | grep TF_GLM`.
