---
name: bring-up-and-bench-a-tensorfold-zig-engine
description: "Bring a ported TensorFold-family Zig/CUDA serve to a serving, bit-exact, benched state on DGX Sparks: pre-boot kernel audit, chat-as-instrument bisection, patch-subset arms, and the comparable bench with digest and knob-halving checks."
---

# Bring up and bench a TensorFold-family Zig engine

For a recipe stack of numbered patches on a pinned engine commit (e.g. the GLM-5.3-Flash Zig recipe), running TP=3 on spark1-3.

## Pre-boot audit (catches the port-gap class in one pass)

1. Every kernel the family requests (`m.function("tf_...")` / quoted `tf_*` in `zig/src/families/<fam>/*.zig`) must appear as a substring of `zig/kernels/cuda/*.cu|cuh`; the absent set is the missing-kernel list. A requested-but-absent name is silent until the boot dies at `cuModuleGetFunction NOT_FOUND`.
2. Every `.cu`/`kernels.zig` embed needs a `zig/build/cuda_kernels.zig` catalog entry, and the entry belongs to the patch that ships the `.cu`. Subset arms need the catalog trimmed to their actual files.
3. A struct-driven load loop (`inline for (@typeInfo(Kernels)...)`) needs its `@FieldType(Kernels, name) == cuda.Function` guard, or `?cuda.Function` fields are requested under the bare field name.
4. The error message prints the literal string passed to `m.function`: a bare name where the code paths pass suffixed names proves a different caller (and `strings` on the built binary shows nothing for names built with `++`).

## Boot checklist that cost real hours

- Model and drafter are CONTAINER paths (`/root/.cache/huggingface/.../snapshots/<rev>`); host paths with a snapshot-dir bind fail on tokenizer.json (dangling blob symlinks).
- `docker run -d` only: an attached run ties the engine's stdout to the launching shell and the ranks stop when the session ends.
- Rank to host is `spark(rank+1)`; rank 1 on the head puts two ranks on one GPU and NCCL refuses with "Multiple Ranks are using the same GPU".
- Production serves and BOTH watchdogs must be stopped for a window: the watchdog restarts production after its down limit and that engine takes ~83 GiB, starving the Zig ranks into memory fit errors.
- A stale `flock` holder from a finished campaign blocks the image build: the log stops after its first line, the tell.

## Correctness is the chat

Health and idle prove nothing: a stack can serve `/v1/models` for 14 minutes and produce token salad (a dropped fill call) or kill the ensemble on the first prompt (a wire field dropped on the send). Boot, send one deterministic prompt (`temperature 0`), read the TEXT, and compare against the stock pin's reply.

## Bisection with patch-subset arms

Clone the pin tree, apply a prefix/subset of patches (plus build-fix patches), pack `tar -C tree --exclude .git -cf src.tar .`, build an image per arm on a Spark, boot and chat it. Each arm is ~15 min build + ~2 min boot. A wire/protocol change (chunk steps) needs its follower-side fix in every arm or the chat dies the same way.

## The comparable bench

- ONE instrument for every engine (`streams.py <port> <N> --kind prose --max-tokens 400 --rounds 3`), a fresh boot per stream level, JSONL receipts.
- Reply digests across arms are the bit check; equal digests = same tokens.
- For a knob set, halve it: boot with a subset via env, one cell, compare digest against the stock digest; repeat on the offending half until ONE knob is named. A knob that changes the bits is a numerics decision for the owner, not a bug.
- Compare engines with the SAME settings (drafter on/off, knobs on/off): a default-off recipe against a fully tuned production stack measures the tuning, not the code.
