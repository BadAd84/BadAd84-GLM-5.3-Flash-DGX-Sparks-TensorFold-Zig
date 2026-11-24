---
name: benchmark-serve-config-vs-load
description: "Use when comparing serve configurations (parallel lanes, pool, graphs) or explaining per-request vs aggregate numbers; separates configuration from offered load before any verdict."
---

# Benchmark serve configuration separately from offered load

A serve has two independent axes and a level sweep only ever exercises one:

- **configuration**: set at boot (PARALLEL lanes, KV pool reservation, captured graphs).
- **offered load**: how many requests are actually decoding at once.

Every "measure at P1, 2, 4, 6, 8" run holds the configuration equal to the load, so it can never say what a higher configuration costs a request that arrives alone, nor whether a lower one merely queues.

## Procedure

1. **Decouple the two axes in the harness.** Give the probe an env override for the stream count (`PERPATCH_SDC_STREAMS` in glm5.3-flash-dev prodbench) so the level fixes the box and the override fixes the load.
2. **Cross them**: same load on a low and a high configuration (4 streams on a P4 box and on a P8 box; 2 on P2 and on P8), plus demand past the lanes (8 offered to a P4 box) to see queueing rather than degradation.
3. **Take the configuration's own costs from the same boots**: pool tokens, boot time, graph count. Never quote these from a different session.
4. **Read per-request and aggregate apart.** Aggregate tok/s rises with load by construction; only per-request rate and first-token latency say what a user feels.
5. **Two boots a cell**, digests equal across boots, no outside traffic.

## Worked numbers (GLM-5.3-Flash, GB10, 2026-11-03)

| | lone request | 4 in flight | 8 in flight |
|---|---|---|---|
| structured tok/s per request | 156.2 (P1 box), 155.8 (P4), 155.1 (P8) | 91.7 | 64.3 |
| structured tok/s all requests | 156 | 366.9 | 514.4 |

The lone-request row is flat across configurations (0.7%, inside drift), so "a higher setting slows a single request" is not supported; the per-request fall is attributable to load.

## The trap

Explaining a configuration choice from a level sweep conflates the two: the level that shows the best aggregate also happens to be the level at which the most requests share the box. Before claiming a setting is better, name which axis moved and confirm the other was held fixed.
