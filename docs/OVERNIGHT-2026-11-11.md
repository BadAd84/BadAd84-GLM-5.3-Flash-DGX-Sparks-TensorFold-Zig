# Overnight run, 2026-11-10 22:00 - 2026-11-11 morning

Goal for the night (owner): get the latest Zig build working, bisecting patches as needed, then a
full benchmark at stock and the patches added one step at a time.

## Result in one line

**The latest build works end to end**: the full 37-patch stack boots, answers the smoke prompt with
the stock pin's own text, and its P1 reply digest is the pin's (`3ec88b6418f7`). Two port bugs stood in
the way and both are fixed and proven: **0036** (the chunk step lost its start and length, so every
chat request killed the stack with PromptTooLong) and **0037** (the KDA block never wrote its output,
so every reply was token salad). The stock pin and armK6 are benched at 1/2/4/6/8; the full-stack
bench runs in the same harness and its table lands in `docs/BENCH.md`.

## What was found and fixed

1. **The chat death: 0007's chunk step lost its start and length.** Every `/v1/chat/completions`
   stopped the TP=3 ensemble with `rank N stopped (PromptTooLong)` while `/v1/models` answered and
   idle was stable for 14+ minutes. Instrumenting the three raise sites showed rank 1 entering
   prefill with `len=0`: 0007's ported leader stopped setting `.depth` (chunk start) and `.top_k`
   (prompt length) on the chunk send, which the follower reads. **Patch 0036** restores them.
2. **Two earlier "idle deaths" were not the engine**: the GLM watchdog restarted the production
   Python stack at 18:32 under our boots (82.9 GiB of the GPU), and a stale 18-day flock holder
   from the finished hunt campaign blocked the first build. Both cleared; the watchdog must stay
   stopped for any Zig window.
3. **Packaging fixes along the way**: `config.sh` was never shipped to the boxes; the model and
   drafter must be container paths (HF snapshot symlinks); `docker run -d` (detached) so the
   engine outlives the launching session; rank to host is `spark(rank+1)` (rank 1 on the head put
   two ranks on one GPU and NCCL refused); `CTX` from the environment is honoured.
4. **Decode correctness, bisected with the chat as the instrument** (each arm booted and asked the
   same count-to-20 prompt, its own reply read):
   - stock pin: "1 2 3 4 5 6 7 8 9 10 11", coherent
   - 0001-0004, 0001-0006, 0001-0011, 0001-0017: identical coherent reply
   - 0001-0017 + 0019, and 0001-0022, and the full stack: token salad with the knob off and at
     16-bit dense. **0019 (the chunked KDA prompt port) is the corrupting step**: it replaced the
     forward's KDA body call and dropped the `if (out) |o| try kda_block.fill(...)` line beside it,
     so no KDA layer ever wrote its output and every reply read stale rows. **0037 restores the
     fill**; the full stack then answers the pin's own text and its P1 digest is the pin's.

## Benchmark state (docs/BENCH.md)

Stock pin, DRAFTER=0, KNOBS=off, fresh boot per level, streams.py prose 400 tokens 3 rounds:

| P | decode aggregate tok/s | TTFT med (ms) |
|---|---:|---:|
| 1 | 49.69 | 156 |
| 2 | 54.72 | 160 / 422 |
| 4 | 72.34 | 155 / 653 |
| 6 | 90.77 | 950 / 138 |
| 8 | 109.35 | 157 / 850 |

Reply digests are identical across every level (3ec88b6418f7 / c36689783326): concurrency does not
move the bits on the pin. armK6 (0001-0017) is benched in the same harness; its table follows in
BENCH.md.

## Queue (owner asked to line these up)

- **PR #2044** (ashhart/TensorFold, item-plan): everything is accepted except the serve A/B against
  main's own base: equal token hashes and decode at 1/2/4/6/8 with drafts on, table into the PR
  body. Needs a free GB10 pair (the dev triangle is occupied); the same harness as tonight runs it.
- Ash's separate invitation: open `ovn-solo` as a PR on today's main (they reproduced the prompt
  stall and want prompt-token equality plus main-vs-branch gap numbers).
- **0019's decode repair** is the next engineering item before any arm past 0017 can be benched or
  shipped.

## Fleet state as left

Production (tf-v110) STOPPED, both GLM watchdogs stopped, benches stopped between levels, sparks
idle. To restore production: `~/glm-v110-start.sh` on spark1, then
`sudo systemctl start glm-watchdog-system.service`.
