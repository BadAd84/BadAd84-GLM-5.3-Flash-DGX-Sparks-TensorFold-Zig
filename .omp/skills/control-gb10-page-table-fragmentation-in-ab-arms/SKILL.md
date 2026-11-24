---
name: control-gb10-page-table-fragmentation-in-ab-arms
description: "Before trusting or comparing Spark GB10 A/B arms: measure SecPageTables and free 64 MiB blocks per boot, and cold power-cycle before windows whose arms span sessions; use when a pair shows 1-2 percent drift between blocks, when memory-fit refusals appear near the floor, or when an arm sequence compares early and late boots."
---

# Control GB10 page-table fragmentation in A/B arms

## Why this exists

On the GB10 (Spark, 64 KiB kernel) any process that maps GPU memory in small chunks leaves kernel page-table
pages that the kernel never returns and cannot move. `/proc/meminfo`'s `SecPageTables` goes from about 4.8 MiB
after a reboot to 28 to 33 MiB after a single serve start, and stays there after the process exits. Those pages
strand inside the large contiguous blocks the GPU prefers, so the node cannot form 512 MiB blocks even though the
memory reads as free.

Measured effect: every decode shape runs 1.0 to 1.5 percent slower on the second start after a reboot than on the
first, with identical greedy output. Our own engines map at 2 MiB granularity (`zig/src/cuda/arena.zig`, the
`granularity = 2 << 20` backend), so this applies to us by construction, not only to PyTorch's expandable segments.

## The check, before any window

1. On each node: `grep -E "^(SecPageTables|PageTables|MemAvailable):" /proc/meminfo` and `cut -d. -f1 /proc/uptime`.
2. Keep a sampler (`~/frag-sample.sh`, one line a minute: date, uptime, SecPageTables, PageTables, MemAvailable,
   free order-10 blocks from `/proc/buddyinfo`) so every boot has the node state it ran on. Read each key BY NAME,
   never by position: a positional `grep` mislabels MemAvailable as SecPageTables.
3. Quote the numbers beside the arm's result. Two arms measured on nodes with different SecPageTables are not
   comparable at the 1 percent level, which is the level most of our levers live at.

## When to power-cycle

A reboot restores the blocks; nothing else does (dropping caches and compaction both fail). Cold power-cycle (not a
warm reboot) the nodes before a window whose arms will be compared across sessions or whose baseline was measured on
a fresher node, and re-read the samplers afterwards to prove the reset landed.

## How to read a result

- If the drift is 1 to 2 percent and the node's SecPageTables is in the tens of MiB, treat the number as
  fragmentation-tainted until the same arm runs on a freshly booted node.
- Memory-fit refusals near the floor (`the pool does not fit; the largest that does: ...`) are also candidate
  fragmentation effects, not only pool arithmetic; check SecPageTables before changing any pool setting.
- Never explain a large regression (tens of percent) this way: the published effect is about one percent.
