---
name: profile-tensorfold-decode-rounds
description: "Use when attributing a TensorFold serve's decode-round time: the metrics counters, the three profiler switches and their sampling traps, the DRAFT=0/1 round budget, and how to judge a knob or patch against it."
---

# Measuring and attributing a TensorFold serve's decode round

Use when a TensorFold-family serve (Zig or Python, any of the OTS recipes) must have its decode round attributed:
which stage holds the milliseconds, whether the drafter is the problem, and where a patch or knob moved the numbers.
All of this is measured once per configuration on real hardware, never inferred from docs.

## 0. Prerequisites on the box

- The serve boots and answers a streaming chat. Production and any watchdog that would restart it must be stopped
  first (the GLM watchdog restarts the Python stack under a Zig boot after its down limit and the two fight for
  the GPU).
- A client instrument that records tokens, TTFT and reply sha per stream, plus the /metrics draft counters before
  and after each round (the OTS `scripts/streams.py` does both; its rows carry acceptance, tok/round, ms/round).

## 1. The counters (the metrics contract)

The server emits PREFIXED families: `tensorfold:mtp_drafted_total`, `tensorfold:mtp_accepted_total`,
`tensorfold:decode_rounds_total`, all counters over FINISHED requests. Poll before and after a round and the
delta is that round's own. Normalise the namespace before matching, or a bare-name parse reads nulls silently
(this has already cost one wrong run).

- acceptance = d_accepted / d_drafted (None when no drafts offered, never 0)
- tok/round = d_generated_tokens / d_rounds
- ms/round = span_s * 1000 / d_rounds

With those three, a serve's round period is known without a profiler: tok/s / (a) tok/round = rounds/s.

## 2. The profilers (and their sampling traps)

| switch | what it profiles | report cadence |
|---|---|---|
| `TF_GLM_PROF=1` | prompt chunks (`prompt chunk to N rows`) and verify rounds (`verify N rows`), section events across gate/embed/kda/mla/gather_a/dense/router/routed/shared/gather_b/head/draw/mtp/commit | prompt every 4 calls; verify every 64 calls PER ROW BUCKET |
| `TF_GLM_DFLASH2_PROF=1` | the drafter's phases: ingest, tables, block, select | every 64 calls |
| `TF_GLM_OVN_SHARED_PROF=1` | shared-round decode (`shared N segs to M rows`, `shared commit N segs`) | per profile object |

Traps that produce empty logs and false conclusions:
- A cell under ~1400 tokens prints no verify lines at all (the per-bucket 64-call gate). A 1400-token greedy cell
  is the smallest reliable one, and the draft-width buckets mean short runs split their calls across buckets.
- `docker run --rm` deletes the crash log exactly when it is needed. Run with a KEEP=1-style flag (no --rm) and
  read `docker logs <name>` after the container exits.
- A rank-0-only boot fails on memory (the checkpoint per rank at world=1); the profiled rank must be rank 0 of the
  real world size with the other ranks' containers up.

## 3. The round budget, in the order that explains it

1. `DRAFTER=0` cell: tokens/round = 1, so tok/s gives the plain verify round.
2. `DRAFTER=1` cell: tokens/round, tok/s and ms/round give the pre-draft round.
3. difference = the draft pass; confirm against the drafter's own phase lines (`dflash2 ms a round: ingest ... block ...`).
4. subtract verify + draft from the round period: the remainder is host/HTTP/sampling, never assume it is small.
5. profile the verify sections with `TF_GLM_PROF=1` and the ~1400-token cell to see WHERE the verify goes.

A reference point worth having in view: the MiaAI-Lab production round is 13.66 ms for 2.75 tokens (201 tok/s),
formed of 7.05 ms plain step + ~1.2 ms per extra verify row + ~1.1 ms drafter + ~1 ms sampling. Against that,
any single section above their whole plain step is the headline.

## 4. Judging a knob or patch

- Same cell, fresh boot, only the knob changed; compare per-stream decode, TTFT, tok/round, acceptance, and the
  reply sha. A knob that moves the sha has moved the numerics: state it (KDA_PAD does, because it packs the KDA
  stack at 4 bits) and let the owner decide on the trade.
- Never measure while another job owns the GPU, and never swap the instrument mid-campaign (cells stop being
  comparable).
- Record the receipts in the repo beside the numbers: the command, the image tag, the digests, the sections.
