---
name: attribute-tensorfold-round-time
description: "Attribute a TensorFold (Zig or Python) serve's per-round decode time to its sections and the drafter, using the built-in profilers, the /metrics draft counters and the drafts-on/off decomposition."
---

# Attribute a TensorFold serve's round time

Goal: split a decode round's ms into its sections and the drafter, so optimisation targets are measured, not guessed. Everything here uses switches already in the engine; no code change.

## 1. The round economics from the harness first (5 minutes)

- Run `streams.py <port> <P> --kind prose --max-tokens 1400 --rounds 1` twice, once with the drafter on and once off (`DRAFTER=0`).
- From each row: round period = `tok_per_round / decode_agg_tok_s` (or per-stream decode tok/s). The draft pass = period(drafts on) - period(drafts off) scaled to 1 token when comparing: period_off is already one token a round.
- Acceptance = `accepted/drafted` from the counters; sanity band for a healthy DFlash2 is 0.55-0.65 with 2.4-2.8 tok/round (= 2.15-2.7 in Mia's records).

Gotchas, both measured:
- `/metrics` families are PREFIXED `tensorfold:`; a parser matching bare names passes a fake serve and reads None on the real one. rsplit(':') before matching.
- The counters are over FINISHED requests, so wrap each round with a before/after poll; the warm-up round consumes the first pair.

## 2. Section split with the built-in profilers

- `TF_GLM_PROF=1` -> `glm prof prompt chunk to N rows` (prefill sections).
- Verify (decode) sections print as `glm prof verify N rows (64 calls)`: gate/embed/kda/mla/gather_a/dense/router/routed/shared/gather_b/head/draw/mtp/commit.
- `TF_GLM_OVN_SHARED_PROF=1` -> `shared N segs to M rows` rounds; only exists when shared multi-stream rounds actually run (a single stream takes the solo verify path and prints nothing).
- `TF_GLM_DFLASH2_PROF=1` -> `dflash2 ms a round: ingest tables block select`.

**The threshold trap**: every profiler reports only every `every` calls (verify = 64 calls PER ROW BUCKET, i.e. per draft width; dflash = 64 draft calls). A 96- or 260-token cell shows NOTHING even though the engine serves. Use a 1400-token greedy single stream (~520 rounds) so each bucket crosses 64. Symptom of the trap: the prompt-chunk line appears (its stride is 4) and no verify/dflash lines do.

## 3. Reading the numbers into targets

The two headline sections are usually kda (linear attention, flat per round) and routed (MoE experts, scales with rows). Measured reference (GLM-5.3-Flash EXL3 4bpw, TP=3 GB10, 1 stream, full recipe): without KDA_PAD kda 14.9 ms / routed 13.1 ms / wall 38.6 ms at 2 rows; with KDA_PAD=1 kda 5.2 / routed 13.4 / wall 29.5 (+16.7% decode). KDA_PAD is the only digest-moving knob of the measured set (it packs the KDA input stack at 4 bits) - expect the digest to change and say so.

External target for the same class of hardware (MiaAI-Lab's own served log): 7.05 ms plain step + ~1.2 ms per extra verify row + ~1.1 ms drafter + ~1 ms sampling = 13.66 ms a round at 2.75 tok/round. Their note: 1 ms off the plain step is +8% decode, 0.1 ms off per-row is +2% - attack fixed per-step cost first.

## 4. Overlap is not free on one GPU

A round is GPU-bound (wall ~= gpu in the verify profile), so "pipeline the draft behind the next verify" cannot hide GPU work; the Python engine's one-round-late draft queue overlaps the CPU-side rollback/sampling, not extra GPU work. Shrinking the draft pass itself is the lever.

## 5. Gate every change

Digests must equal the pre-change cell for prompts where drafts were bit-exact before (greedy, drafts on: e.g. 3ec88b6418f7) - a knob that moves them (KDA_PAD) is a numerics decision for the owner, recorded with its measured size.
