---
name: profile-a-reference-serve-on-our-own-triangle
description: "Stand a foreign or reference LLM serve (e.g. stock 0.6.0 TensorFold) up on our own DGX Spark triangle, driven by a captured environment, to take a kernel-level head-to-head against our build without disturbing the live production box."
---

# Profiling a reference serve on our own triangle

When: the live production serve is faster than ours and you need a repeatable, profile-able reference on identical GPUs and weights, while pausing production would cost someone else's work. Do NOT pause production for a profile; reproduce it.

## 1. Capture the reference's launch, not a guess
On the live box (spark1 for us; reach it as `adam@spark1.ots-int.net` with the agent-gui SSH sock):
```
docker inspect <container> --format '{{range .Config.Env}}{{println .}}{{end}}' > prod.env   # 165 lines, 42 TF_GLM_*
docker inspect <container> --format '{{json .Config.Cmd}}'                                   # argv shape
docker inspect <container> --format '{{.Config.Image}}'                                      # the actual image tag
```
Read the tag: a live box is often a tuned build (`v110hunt3`), not the published stock image. Say which one you are reproducing. For a stock reference, `ghcr.io/miaai-lab/glm-5.3-flash-exl3-2x-dgx-sparks-tensorfold:v0.6.0-789e8f3bdfa2` is public: check with `docker manifest inspect` before pulling.

## 2. Confirm the weights are already local
`ls -d ~/.cache/huggingface/hub/models--*/snapshots/*` on a target box. Mount `~/.cache/huggingface` into the container and pass the SNAPSHOT paths in argv (the container sees `/root/.cache/...`), not repo ids: an offline boot then needs no auth and no download.

## 3. Boot all ranks the way the reference does
Mirror the captured argv exactly, overriding only what the test needs (port, `--context`, `--parallel`):
```
docker run -d --name ref-r0 --gpus all --ipc=host --network host --shm-size 16g \
  --device /dev/infiniband --cap-add IPC_LOCK --ulimit memlock=-1 --ulimit stack=67108864 \
  -v /home/adam/.cache/huggingface:/root/.cache/huggingface --env-file prod.env \
  <image> tensorfold serve <model snapshot> --tp 3 --rank 0 --master <rank0 lan ip> --master-port 29551 \
  --host 0.0.0.0 --port 8300 --drafter <drafter snapshot> --context 262144 --parallel 4
```
Only rank 0 needs `--host`/`--port`. Drive ranks 1/2 over ssh from a box that has keys to the others (spark1 has spark2 and spark3). Wrap the whole GPU session in `flock -o ~/work/gpu.lock` so it cannot overlap another serve.

## 4. Wait for health, then drive the load
`for i in $(seq 1 90); do curl -sf http://127.0.0.1:8300/health && break; sleep 10; done` - a foreign stack can take 2-4 minutes to load. Log the container's own tail on failure; it names the refused flag or the missing path.

## 5. Profile the window the load occupies
Our `serve4nsys.sh` boots under `--entrypoint nsys profile --trace=cuda --cuda-graph-trace=node --delay=240 --duration=90`: with a 240 s delay a load started at boot is MISSED. Set `NSDELAY=10-25 NSDUR=90-120`, start the load right after health, then `docker cp <ctr>:/root/<out>.nsys-rep`. Graph-based stacks need `--cuda-graph-trace=node`; eagerly-launched stacks (ours) record at 4 streams and record NO kernels at 8.

## 6. Compare like with like
Same weights, same `--context`, same `--parallel`, same prompt set, same counters pulled from both sides. State the build you reproduced (stock vs the box's tuned tag) in every conclusion: a stock reference tells you where the tuning lives, not what the live box does.
