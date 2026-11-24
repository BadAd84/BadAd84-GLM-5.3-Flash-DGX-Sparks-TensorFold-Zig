---
name: attribute-a-cold-prompt-gap-by-kernel-family
description: "Before proposing a kernel fix for a slow cold prompt on the GLM/TensorFold serve: decompose the existing nsys capture by kernel family, name each candidate's ceiling, and pick the family that can actually move the number."
---

# Attribute a cold-prompt gap by kernel family before proposing any kernel fix

Why: a plausible kernel story is cheap and a kernel rewrite is expensive. On the GLM Zig serve, attention looked like the cold-prompt gap until the existing capture was read: attention was 3.3% of the path and the money was in the TP exchange (18.4%) and the EXL3 prompt expert GEMMs (22.4%).

## Procedure

1. **Look for a capture already in the repo first.** `scripts/prefill_passes.py` output lives under `docs/audit-2026-11-12/queue-rows/<queue>/pf-*/`: `passes.txt` (per-pass wall and kernel counts), `kern.txt` (share, total ms, launches, mean us, median us, name), `gaps.txt`, `kdiff.txt`, `launch_cost.txt`. No GPU needed to read them.
2. **Sum by family, not by name.** Group: exchange (`ncclDevKernel_SendRecv`), expert prompt GEMMs (`tf_exl3_prompt_*`), expert decode GEMMs (`tf_exl3_ovn_*`), int4 linears (`glm_mm4_*`), attention (`tf_glm_onepass_pipe*`), KDA, glue. Report share of total and mean us per launch.
3. **Read launches as well as time.** A family at a 300-500 us mean over ten thousand launches is a launch-shape question, not a bandwidth one. Say which it is before proposing work.
4. **State the ceiling of each candidate.** If a family is 3.3% of the path, halving it buys 1.6 points and no effort there can do better; that sentence decides whether the work is worth starting, and it is the sentence that stopped an attention rewrite.
5. **For the family you pick, get the arithmetic of waste before the arithmetic of speed.** The dense-window change came from counting key-rows: 8.39M dense against 4.19M sparse, 75% of the dense rows overwritten by the sparse pass, which pointed at a row-range clip rather than a kernel shape.
6. **A clip that leaves replies identical is provable, so state the proof.** Here: rows past the select's limit have nonzero counts and are written by the sparse pass, and a row's work does not depend on how many rows its launch carries, so the clip is byte-identical by construction and needs a digest check rather than a numerics call.

## Traps

- Do not accept a reviewer's per-kernel figure without the row counts behind it; 174.5 against 46.2 ms was 2.0x rows times 1.9x per-key, and only the first factor was removable.
- A capture of two requests (8k and 32k) reports one table for both; say so, and do not attribute a share to one length.
- Mean versus median separates a launch-shape problem (median far below mean, few slow launches) from a uniformly slow kernel.
