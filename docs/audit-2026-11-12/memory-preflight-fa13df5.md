# Upstream main's memory preflight refuses our boot on a GB10 (2026-11-21)

Queue101 booted stock upstream main (`fa13df5dd`) four times and every attempt died on rank 0 inside 20 seconds:

    tensorfold: the checkpoint's 61.3 GiB of weights do not fit the 55.6 GiB the CUDA memory budget grants
    (68.6 GiB free less a 13.0 GiB reserve); free device memory or adjust TENSORFOLD_MEMORY_RESERVE_GIB / TENSORFOLD_CUDA_MEMORY_LIMIT_GB

The four attempts read 55.6 / 55.3 / 55.2 / 55.1 GiB of budget, with 68.6 / 68.3 / 68.2 / 68.1 GiB "free". Logs: `~/bench/f92-boots/c92-ut2{a,s,d,b}.log` on spark1 (not committed: they carry
host paths). This file records what is known, what is not, and what will settle it.

## The change that refuses it

`c896bfc0c` (committed 2026-11-21 06:19 UTC, after our tip re-seat base `46c6ee229`, so every window on the new base carries it), "cuda: a unified Linux budget is at most CUDA's free memory,
after the checkpoint leaves the page cache". On an integrated device it:

- makes the pool the smaller of the host figure (`/proc/meminfo` MemAvailable plus the free pages parked on the per-CPU lists) and CUDA's own free memory, less the reserve
  (`zig/src/native/cuda_memory.zig` `boundFree`, `zig/src/native/cuda_family_memory.zig` `poolFor`);
- before the weights check, advises `POSIX_FADV_DONTNEED` on the checkpoint shards the loader opens (`zig/src/native/cuda_page_drop.zig`, called from `zig/src/native/cuda.zig` at the
  integrated-device open), so a checkpoint that was just read does not count against itself.

Its own message says "a GB10 device check is owed". The reserve in the message, 13.0 GiB, is ours: `scripts/serve.sh` passes `RES`, which is 13.0 at four streams.

## The facts measured here

- The checkpoint is 83 shards, all symlinks into the Hugging Face blob store on local ext4, all 83 named by `model.safetensors.index.json`, none nested (163.6 GiB in total). The drop
  therefore reaches every shard; a shard the drop cannot name is not the explanation.
- spark1's MemTotal is 123.7 GiB.
- queue100, whose first boot came 284 seconds after production actually went down (production stopped at 09:51:14 for queue101; queue100's own `prod-stop` at 09:53:17 found it already
  stopped, and its boot followed at 09:55:58), admitted `memory.active` 82,648,134,704 bytes (77.0 GiB) on the same box and ran its whole set of cells
  (`work/pp100/f100-c/ca1-facts.out`). Its memory snapshot at that moment (`ca1-mem-idle.txt`): `available` 34.3 GiB of 123.7 GiB, `buff/cache` 34.7 GiB, with the three containers at
  3.63 / 3.32 / 3.33 GiB RSS. So the pin-era admission (MemAvailable only) granted 77 GiB of device memory on a box whose host `available` read 34.3 GiB, which is the situation upstream's
  change exists to stop, and the boot succeeded.
- queue101 stopped production at 09:51:14 and booted at 09:51:35, 21 seconds later.
- Free pages parked on the per-CPU lists, read later with a serve up on all three boxes: 0.13 / 0.14 / 0.11 GiB. That reading says nothing about the state at the boot, but it rules out a
  permanent large pool of parked pages on these boxes.

## What is not known

What held about 55 GiB of the 123.7 GiB when queue101's boots ran. Three candidates, none excluded:

1. **Production's unified memory not yet returned.** The 21-second gap is the only clear difference from queue100's successful boot 140 seconds later. On a GB10, device memory is host memory and
   a large allocation's release is not instantaneous at process exit; a 20-second spacing is plausible and a 161-second one is comfortable.
2. **Page cache of files the drop does not name.** The `ut2` image had just been built on spark1 and `docker load`ed on spark2 and spark3; those layers are not checkpoint shards and the drop
   never touches them. Page cache counts against CUDA's free until reclaimed.
3. **A slow drain in the driver or the display carveout** (`dispramd` lends the 2 GiB carveout on kindling spark-os).

The pin-era boots never met any of this because their admission read MemAvailable, which counts page cache as available.

## What will settle it

A queue that, before each boot attempt, writes an idle snapshot of all three boxes, then boots and records the engine's own "N GiB free less a M GiB reserve" line from rank 0, and climbs rungs in
this order: snapshot only; wait 60 s, then 120 s, then 240 s (each its own attempt and snapshot, so the drain curve is in the files); drop the page cache; drop it and compact. The rung that passes
is kept for the rest of the queue, and the queue then re-runs queue101's four arms. Guessing between the three candidates is what this is designed to prevent.

## Who is affected

Every measurement on the re-seated series, and every retirement window that follows it, boots a tree with `c896bfc0c`. The pin-era image `m130a` is unaffected: it reads MemAvailable, which is
why queue95 through queue102 can run on it while this is open. Production (the Python stack) is not affected; it stays down for the campaign.
