# The decode `AllGather`: dependency-bound, so there is no patch

2026-11-23, pin `fa13df5dd`, series `ret17` (engine `a12524ae144f47d41a977728b64b608359e62cc4`). The measurement
this answers: a four-client decode capture of the shipped recipe reads `ncclDevKernel_AllGather_RING_LL` at
7,640 launches, 675.6 ms, on stream 18, the main stream, against 115.9 ms of `SendRecv` on the side stream
(`docs/OVERNIGHT-2026-11-12.md:2801` and the decode half of the same work).

## 1. Which call sites, and what they gather

One family, not three: **the rank_fold of each site's fp32 partials**, `cuda_boundary.resolve`
(`zig/src/families/glm/cuda_boundary.zig:16-37`), which gathers `rows x hidden` fp32 from every rank in rank
order into `b.gathered` and runs on `f.stream`, the main stream.

It is called twice a layer from the unpieced decode loop, `cuda_forward.zig:435` (after the mixer) and
`cuda_forward.zig:451` (after the ffn), and twice in the MTP block's propose path, `cuda_forward.zig:525` and
`:533`. 45 layers x 2 = 90 a window, so 7,640 / 90 = 84.9 windows in the 19,244 ms capture, which is the
four-client round count at that aggregate; the MTP pair adds two a round only when its propose path runs, and the
90-a-window figure is already in the record from an earlier four-client capture
(`docs/OVERNIGHT-2026-11-12.md:1631`: "90 `ncclDevKernel_AllGather_RING_LL` launches of 64 us a window").

Not one of these launches is a weight gather:

- the experts' weights never cross ranks: each rank holds a column shard of every expert (`cuda_exl3.zig`'s
  `by_cols` cut), so the expert phases exchange rows, not weights;
- the KDA stack and the MLA absorb do not gather at all: their inputs are the layer's rows, exchanged as rows;
- the side stream's 115.9 ms of `SendRecv` is the drafter and taps path (`dflash_block.zig:78-83` via
  `tp.group`/NCCL), and `cuda_engine_pick.zig:32,59` gathers only the propose path's u8 pairs.

## 2. Dependency: every one is consumed by the very next kernels

- After `:435`: the ffn site's glue, `hc_glue.fused` at `:437-441` or `post` and `pre` at `:443-445`, which is
  the kernel that adds the gathered partials rank 0 first (`cuda_boundary.zig:1`).
- After `:451`: the same layer's hc_post at `:453` (`f.post`, which reads `b.gathered` at `cuda_forward.zig:219`)
  and then the next layer's hc_pre and mixer.
- The MTP pair at `:525` and `:533` is the same shape, its consumer the residual add and the drafter's step.

Between each producer (the site's last matmul, which writes this rank's partial) and each consumer there is no
independent main-stream work to run: the only kernels in between are the profiler marks. A side stream would
therefore move the *name* of the wait, not the wait.

The arithmetic agrees that the wait is the transfer, not the schedule: 24 rows x 4,096 hidden x 4 B is 393 KB a
rank, so 1.2 MB across three ranks, and 675.6 ms / 7,640 = 88 us a launch, which is 13.6 GB/s, the wire's measured
rate. There is no queueing slack to recover at this size.

## 3. What prefill's overlap provides, and why decode cannot use it

`Pieces` (`cuda_forward_pieces.zig:76-100`) gives a second stream at high priority, the `filled/gathered/glues/
shared` event handshakes (`:225-270`), and a room-per-piece buffer discipline (`cuda_forward.zig:320`). It is
prompt-only: `ranges()` is called only under `b.prefill` (`cuda_forward.zig:411`), so a decode window always takes
`whole()`. And the reason it works in prefill is structural: a piece's exchange overlaps the main stream's *next
piece*, which exists because a prompt chunk is cut into row ranges. A decode window has one row range; there is no
next piece to overlap with, and the fold's consumer is the next kernel.

## 4. What the arithmetic does leave, as a measurement rather than a patch

The folds are on NCCL's ring rather than the RoCE wire only because 393 KB a rank is above the wire's mailbox
ceiling (`TF_TP_MAILBOX_MAX_KB`, default 256 KiB a rank, boot-checked equal on every rank, at most 1,024;
`docs/OVERNIGHT-2026-11-12.md:1631`), and the wire measured 18 us a 2-row window where NCCL reads 64 to 88 us.
Raising the ceiling to 1,024 at four clients is a boot knob already in the engine, moves the same bytes in the same
rank order, and changes no digest. It is a queue (four-client decode cells, agg_tok_s, digests, plus the prefill
capture unchanged because the knob does not touch the prompt path), not a patch, and this note does not propose it
without the owner's word.

No patch, by the rule: all 7,640 launches are on a true dependency path, and a side-stream issue would hide the
stall without removing it.
