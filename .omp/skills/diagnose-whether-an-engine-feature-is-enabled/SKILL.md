---
name: diagnose-whether-an-engine-feature-is-enabled
description: "Before building or porting a feature into the TensorFold Zig engine, prove from source and one instrumented run whether it is already there and enabled; covers gate chains, env-gated logging and reading a distribution instead of a line."
---

# Is the feature already there, and is it on?

Learned the hard way over one session of six wrong absence-claims (roce gather placement, __ldg, expert
rotate, MULTI_WINDOW semantics, the decode multi-slot machinery, and the CUDA multi-stream window). Every
claim of "this does not exist / is dormant / needs porting" was wrong, and each was corrected by reading one
more file. Run this before writing any code.

## 1. Promise nothing from a name

An absence claim is wrong until BOTH have been found:

- **the type that carries the capability** - e.g. `Seg = { st: *State, row0, rows }` (per-segment state) or
  `Piece = { stream, start, end, save }` (a prompt token range);
- **the sibling backend that exercises it** - e.g. the Metal `slots.zig` fills `segs` with several requests
  while the CUDA call sites pass one stream's parts.

Grep the whole tree for the capability, then read the types, then read a sibling family. `MULTI_WINDOW`-style
names sound like batching and may batch prefill; `window` sounds single-stream and may fan out over slots.

## 2. Trace the gate chain to the deciding condition

Features here are gated by facts, not by one flag. Example, shared rounds:

```
cuda_lanes: drafting = e.mtp; sharing = drafting and !alone; hidden_rows = sharing
cuda_native: alone = off("TF_GLM_SHARED")   // off() is true ONLY for the literal "0"
config:      width = clamp(exact_width, 1, max_rows)
             family_streams = width >= 2 and streams_exact and hidden_rows
engine:      if (live.items.len > 1 and cfg.family_streams) roundStreams(chosen) else per-stream
             takeTurns caps chosen at cfg.batch_streams (1 unless family_streams)
```

Read every link, in the family AND in core. Note that an env's "off" helper may test one exact string, that
a model field like `free_streams` may be admission memory rather than a feature switch, and that a knob with
no consumer (a `first_tree` nothing reads) will be rejected upstream.

## 3. Instrument, env-gated, then measure a distribution

Add one log line at the decision point, behind a generic env var, printing the values that separate the
candidate causes:

```zig
if (std.c.getenv("TENSORFOLD_LANES_LOG") != null) std.log.info(
    "lanes: live {d}, family_streams {}, batch_streams {d}, batch_rows {d}", ...);
```

Then read **a distribution**, never a single line: one `live 1` sample looks like a bug and is just an early
round. Histogram the values and read the timestamps to get per-case cost:

```sh
docker logs <rank-0> | grep -oE "lanes: live [0-9]+" | sort | uniq -c
docker logs <rank-0> | grep "glm lanes:" | sed 's/.*glm lanes: //' | sort | uniq -c
```

## 4. Two instruments, two quantities - never substitute one

Measured conflation: the profiler's `verify N rows` is ONE WINDOW's rows; the lanes counter counts WINDOWS.
"2 rows at --parallel 4" therefore proved nothing about batching, and a whole ranking was built on it. When
two instruments disagree, establish what each counts before concluding.

## 5. Container logs die with the run

`stop3.sh` removes the container, taking `docker logs` with it. Capture counters FROM THE RUNNING container:
wait for the streams phase, dump the histogram and the whole `glm prof` span list, then stop it. Grep for all
spans, not just the one you expect: if a 16-row round shows no matching span, the span name is keyed
differently and the gap is in your instrument.

## 6. Cost the prize before believing the ranking

A merged round is not free. Measured on this engine: 1/2/3/4-window rounds cost 45.5 / 79.0 / 106.9 /
129.8 ms, so four streams in one verify is 2.85x one stream - ~1.4x efficient, because a MoE's routed expert
union grows with the batch. That caps utilisation work and points the remaining gap at per-row cost.
