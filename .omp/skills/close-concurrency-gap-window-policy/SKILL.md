---
name: close-concurrency-gap-window-policy
description: "Use when a TensorFold/ai-engine GLM serve lags production at 4-8 concurrent streams: attribute rows-per-round vs round time, find the allocator's cost table, and A/B a policy-mode window with two images."
---

# Close a concurrency gap in the shared verify window (GLM, ai-engine / TensorFold)

When: our serve is fine at 1 stream but falls away at 4-8 (measured 2026-11-02: 87% of production at 1 stream, 58% at 8), and the usual knobs (SHARED_ROWS=auto/64, EXL3_LOADS nc, MULTI_FILL) are already level or shipped.

## 1. Split the gap into the two factors before touching code
- Useful tokens per stream per round (production 7.2-7.5, ours 5.75) and round period (production ~130 ms, ours 165-180 ms at P8).
- Take both from the probe's counters and the profiler (`tf_glm_*` metrics, `TF_GLM_OVN_SHARED_PROF`), never from wall time alone. The wrong answer here wastes a night: the host language is irrelevant (decode is GPU-bound; we were ahead on host work while behind on rows).

## 2. Rows per round: the allocator's cost table is the usual cause
- `zig/src/families/glm/cuda_lanes.zig` passes a CONSTANT cost table (`costTable(max_rows, 76.0, 4.1)`) into the lanes config; `zig/src/core/lanes/allocate.zig` then prices every extra draft row, so a draft needs roughly E/C x 4.1 ms (about 59% acceptance at P8) to be admitted.
- An EMPTY cost table is production's `policy` mode: `rate()` returns expected/(1+overhead), every added row raises it, and the allocator fills likeliest-first to `max_rows`. So the change is to pass `&.{}` for shared rounds behind a knob (`TF_GLM_OVN_WIN_FREE`), not to rewrite the allocator.
- Compose with `TF_GLM_OVN_DEPTH_FULL` (removes the grant+2 ratchet) - the ratchet was the other half of the trim.
- Check upstream first: `67e761edf` (lanes: an external drafter's chain chances price verify rows) works the same area; compare before landing a local knob.

## 3. Round time: gathers wait, they do not stream
- `gather_b` at 23-26 ms of a ~170 ms P8 round is mostly WAITING on the peer rank that holds the wide expert share (production's total gather cost is 1.35-2.4 ms).
- Profile ALL ranks, not rank 0 (the usual missing measurement). If only rank 0 is profiled, you cannot tell skew from bytes.
- Verified non-gap: production's `TF_ROCE_MAX_KB` is 512 KiB rising to 1024 past 4 streams; ours defaults to 4096 KiB, i.e. already larger. Do not "fix" the cap.

## 4. A/B rules that this work keeps getting wrong
- `pp-chain-ab.sh` takes ONE image: it varies env only. A code change needs `pp-img-ab.sh` (two images, same ABBA cells, same probe) or the arms are identical.
- One fresh boot per cell, ABBA, and require every digest equal; the new defaults only if no level regresses (boot time excepted).
- Flip defaults only after the queue drains, from a chain that waits on the queue's DONE marker (`defx3-chain.sh` pattern), then prove it with a separate chain that greps the container env and re-measures one cell.

## 5. Reference numbers to compare against (2026-11-02, GLM-5.3-Flash EXL3 TP=3)
- ITEMS + X3 defaults: short 129.0 / 164.6 / 212.6 / 222.9 / 251.4 tok/s at 1/2/4/6/8 vs production 147.7 / 207.2 / 301.2 / 373.0 / 435.2.
- One-stream prose 67.4 vs 81.3; cold 32k 14.34 vs 12.20 s; ~200k conversation 88.5 vs 77.0 s.
