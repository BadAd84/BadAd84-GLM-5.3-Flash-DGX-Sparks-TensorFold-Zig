---
name: diagnose-a-long-context-resume-cliff
description: "Use when TTFT or decode collapses past a stream count on a long-context serve (a forks-style probe), to separate cache-capacity eviction from prefill throughput and to test a pinned prompt-cache budget."
---

# Diagnose a long-context resume cliff

## Symptoms that call for this

- A concurrency matrix shows TTFT and decode fine to 4 streams, then one or two orders of magnitude worse at 6 or 8.
- Each stream resumes a long state (100k to 300k tokens) and the reply is short.
- Both arms of an A/B show the same cliff, so it is the serve, not the change under test.

## Read the probe, not the rate

A forks-style cell sends N concurrent requests that resume the SAME long state, each with a short turn. Pull, per level:

- `ttft_med` and `agg_tps` from the forks block;
- `d_prompt_tokens_total`, which should scale as streams times the long prompt length.

Measured example (GLM-5.3-Flash TP=3, 202,414-token prompt): 1 stream 1.43 s, 2 streams 3.40 s, 4 streams 5.35 s, 6 streams 746 s with 1,214,484 prompt tokens. Resumed states cost seconds; a re-prefill of 1.2M tokens costs minutes. The cliff between 4 and 6 is eviction, not throughput.

## Find the cache budget's semantics before blaming capacity

1. `grep -rn 'prompt-cache-gib' zig/src/server/cli.zig` and read the default. If it is `null`, the budget is derived from RAM left over, for example "whatever 70% of RAM leaves past the loaded server".
2. Consequence: the budget SHRINKS as stream count grows, because every 1M-context stream takes KV pool RAM. A fixed-looking limit is really a moving one, and the eviction point is where long states stop fitting.
3. Compare with the reference stack's explicit budget (for example 56 GiB at 8 streams) plus any disk KV tier; that is why it sustains 8 resume states where ours sustains about 4.

## Prove it with a pinned budget, never by argument

Run the same level, same image, ABBA, with arm b booted adding the flag explicitly:

```
XSERVE='--metrics-open --prompt-cache-gib 96' ./serve4.sh 0 6 1048576
```

Pass the extra serve arguments to EVERY rank (serve4 forwards `XSERVE`, so check the rank lines in the boot log). Success looks like forks TTFT falling from minutes to seconds on arm b while short decode and TTFT stay put. A pool that no longer fits is a refusal at load, not a silent slowdown, so read the boot log rather than the health endpoint.

## Report it as a trade

Pinning the budget takes RAM from the KV pool. State both sides: the resume win at the levels measured, and the pool size at boot (pages or GiB) on both arms. A change that costs pool headroom needs the stream counts where it wins and where it loses, not a single number.

## Traps

- A reporter that flips delta signs with `--ref b` can make a win read as a regression; verify against absolute medians per arm before drawing conclusions.
- A derived pool size (for example `res=6.5` at 8 streams) can refuse at boot and look like "level 8 will not run"; pin the value the other levels used and rerun that level alone.
- Starved cells are still evidence: mark them as starved with the prefill time rather than printing a 1 tok/s "rate".
