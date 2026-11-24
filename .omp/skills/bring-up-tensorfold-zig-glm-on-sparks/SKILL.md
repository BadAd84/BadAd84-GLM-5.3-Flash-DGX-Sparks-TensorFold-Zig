---
name: bring-up-tensorfold-zig-glm-on-sparks
description: "Bring up and debug a pinned TensorFold Zig GLM recipe on the spark1-3 production boxes: detached boots, container-path model/drafter, rank-spark(rank+1), watchdogs stopped, chat-as-instrument bisect, the four port-defect classes, and knob digest halving"
---

# Bring up a TensorFold Zig GLM serve on spark1-3

Measured live 2026-11-11 on GLM-5.3-Flash EXL3 4bpw (rev 078455ffe), TP=3, ctx grid by P.

## Preconditions

- Production (tf-v110) and BOTH GLM watchdogs stopped. The system watchdog restarts production
  after its down limit; that engine holds ~83 GiB of the GB10 and the Zig ranks then fail with
  "the checkpoint's 61.3 GiB of weights do not fit". Check `systemctl is-active glm-watchdog-system`.
- No stale flock holders on `~/work/gpu.lock` (a parked `exec sleep infinity` from an old campaign
  blocks every build silently; the build log stopping after its first line is the tell).
- Image built ON the target box (`scripts/build-image.sh TAG src.tar`, ~17 min CPU); for other boxes
  `docker save | ssh docker load` over the sparks' own links, never the laptop relay (~20 MB/s).

## Launch rules that the failures taught

- `docker run -d` detached. Attached runs die with the launching session (the engine writes to a
  pipe that breaks; every rank stops).
- Model and drafter are CONTAINER paths (`/root/.cache/huggingface/hub/models--*/snapshots/<rev>`);
  the whole HF cache is mounted at /root/.cache/huggingface so blob symlinks resolve. A host-path
  model plus a snapshot-dir bind fails on tokenizer.json.
- rank -> host is `spark(rank+1)`; rank 1 must land on spark2 or NCCL reports "Multiple Ranks are
  using the same GPU/Partition".
- NCCL env: P2P/SHM off, 4 channels, CROSS_NIC, subnet-aware routing, GID 3, all four HCAs, socket
  enP7s7, `--device /dev/infiniband`; the bootstrap COMM_ID is spark1's LAN ip:port.
- `CTX` from the environment is honoured by zig-tp3.sh only via `CTX=${2:-${CTX:-}}`.

## Verifying

- `/v1/models` 200 and 14 min of idle prove nothing. The CHAT is the instrument: ask one prompt and
  read its TEXT. Token salad or a stopped ensemble both show green health first.
- Digest check: `streams.py 8300 1 --kind prose --max-tokens 400 --rounds 1` prints the reply sha;
  stock is 3ec88b6418f7 (prose) / c36689783326.

## Bisecting port defects (boot each arm, read its own reply)

Four classes, each with a tell:
1. Kernel requested but not built: a `.cu` or kernel with no `cuda_kernels.zig` entry -> boot dies at
   `cuModuleGetFunction NOT_FOUND` / `kernel symbol not in module`. Scan every `m.function("tf_...")`
   name against `zig/kernels/cuda/*.cu|cuh` as a substring; a bare name with no suffix means a
   DIFFERENT caller (the glue loop), not the suffixed request.
2. Dropped wire field: a follower step whose header no longer carries start/length (chunk .depth and
   .top_k) -> followers prefill with len=0 -> `PromptTooLong` kills the stack on the first chat.
3. Dropped output write: a ported call replacing `bodyProfile(...)` and dropping the
   `if (out) |o| kda_block.fill(...)` beside it -> every reply is token salad with healthy ranks and
   identical garbage for identical prompts.
4. Load-loop guard: cuda_glue must request only `@FieldType(Kernels, name) == cuda.Function` fields;
   optional fields are set by their own setters with the suffixed kernel names.

## Naming a bits-changing knob

Halve the knob set with one boot per subset (`scripts/knob-digest.sh IMAGE TAG "-e KNOB=1 ..."`) and
compare the sha to stock. Measured: TF_GLM_KDA_PAD alone moves the digests (it puts the KDA stack on
the 4-bit pack list) and buys +23.5% at P1 / +17.2% at P2; the other twelve measured knobs are
bit-exact. The bit-exact set (all but KDA_PAD) is +1 to +3.2% at P2..P8 with stock digests at every
level.
