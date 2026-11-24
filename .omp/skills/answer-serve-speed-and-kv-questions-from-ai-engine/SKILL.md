---
name: answer-serve-speed-and-kv-questions-from-ai-engine
description: "Use when asked for the speed, context window, KV size or stream scaling of any of our local serves (GLM, DSV4.1, Qwen, 1017 checkpoints) - answer from the ai-engine measurement tables, never by re-benchmarking or searching GitHub."
---

# Answer serve speed / context / KV questions from ai-engine

Every measured number for our local serves is already committed. Read it; do not re-benchmark, and do not
search GitHub or the web for recipe names.

## Where the numbers are
- `ai-engine/docs/repro/<lane>/table.md` - one table per measured serve/lane, always with a provenance header
  (arm, image, pair of boxes, context, streams, cycles, how decode is measured).
- The matching `<lane>-evidence/*.log` (or `evidence/res/*.jsonl`) holds the raw cells; a `table.md` that says
  its logs were lost cannot be regenerated - quote it as-is and say so.
- `docs/repro/<model>-speed.md` - the published baseline for that model (e.g. `dsv41-speed.md`, `dsv41-0202-ab-p*.md`
  for per-arm A/Bs at a given stream count).
- `docs/port/<model>-nvme-tier-plan.md` - the per-token KV arithmetic (bytes/token, per-prompt file sizes).
- `docs/MIAAI-PRS.md` - which recipes we have upstream PRs on; its `== recipe ==` lines are section headers, not links.
- The boot's own pool line (`streams at once, X GiB each at a N-token window ... model Y GiB`) is the serve's own
  statement of memory; quote it when asked "what KV size".

## How to answer
1. Identify the model/checkpoint and the box pair - they differ per lane (published EXL3 ran spark1+spark3; the
   converted 1017 ran spark4+spark5) and confusing them produces a wrong answer.
2. Give the table's aggregate and per-stream columns at each P, plus TTFT cold and next-turn; state drafts on/off,
   accept rate, and whether the row is the shipping default (P=6 often needs `TF_DS_STREAMS`).
3. State the context window and KV as measured/derived (bytes per token x window, per rank at TP=2), and say which
   figure is the boot's own line versus arithmetic from the plan.
4. Carry the caveats the table carries: chat-template refusals, uncommitted columns, no quality claim.

## Traps
- Draft acceptance can invert the story: on the converted 1017 (accept 0.13-0.23) drafts OFF is much faster; on the
  published EXL3 (0.64-0.93) drafts ON scales. Never quote one checkpoint's numbers for another.
- "Published recipe" (upstream Mia-AI-Lab, EXL3 2.9bpw) and "our 1017 conversion" are different models with
  roughly 2x different per-stream rates.
