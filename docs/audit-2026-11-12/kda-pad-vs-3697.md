# KDA padding: upstream #3697 against `TF_GLM_KDA_PAD=1`

2026-11-22. Pin `fa13df5dd1fdd23ada775510a464c9aa03a39e09` (2026-11-21, "changelog: #4076 under Unreleased").
Stack: `patches/engine/0001..0038`, engine tree `889b2a773d815f66eb472f20d1f8f4a4b151d930` before the dense-window
clip and `59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450` after it (the pad is untouched by that clip).

**Verdict in one line: #3697 is already in the pin, `TF_GLM_KDA_PAD=1` is the pin's own switch that #3697 kept for a
different mechanism (one common width plus glm_mm's packed tiles), and our stack now contributes only a diagnostic hook
to it. The item is a numerics comparison, not a port.**

## 1. What #3697 does, and where it lives

Merged 2026-11-20 as `ae8f0a10f`. No switch, no new kernel, no fingerprint change. It sets the fused KDA input stack's
row width at load (`kb.pad_to`), so that

- unset (the default now): each rank's stack is padded to **its own width rounded up to eight columns** - TP=3's
  8,726 -> 8,728 on rank 0 and 8,341 -> 8,344 on ranks 1 and 2 (`alignedWidth`, `cuda_kda_block.zig:62`); at worlds 1,
  2, 4 and 8 the width is the stack's own and nothing moves;
- the padded stack stays row-major bf16, and prompt windows from 128 rows now take the **staged** `tf_glm_bmm_tile`
  (the stack) and `tf_glm_bmm_tile1` (the f_b and g_b views), where before they went to the unstaged `tf_glm_bmm_rows`;
  decode keeps `tf_glm_bmm_decode`;
- the staged tiles give the unstaged kernel's bytes: the same mma chain per K slice, slices added in order.

Byte identity is argued in the PR and proven by `glm-ref`'s `paddedStack` (both TP=3 shapes, 144 row counts each, every
byte of the first n columns equal and every pad column zero) plus 13 greedy hashes and `bench_concurrent`'s 36 across
main and the branch. Cold first tokens: 7.2K 5.07 s -> 4.53 s, 28.8K 19.32 s -> 17.18 s, about 10-11%.

In the pin: `pad_to`, `alignedWidth`, `rowWidth`, the `paddedStack` check and `cuda_kda_tp3_test.zig` are all present
(`git grep` on `fa13df5dd`), and the pin's date is after the merge. **Nothing to port.**

## 2. What `TF_GLM_KDA_PAD=1` does now

The knob is the pin's, kept by #3697 exactly as main had it (`cuda_engine.zig:154-155`):

    kb.tile_pad = o.settings.kda_pad;
    kb.pad_to = if (kb.tile_pad) kb.padWidth(c.kda_heads, world) else kb.alignedWidth(share.kda.len());

so with the knob on the pad width is `padWidth` = the **widest** rank's row rounded up to eight - 8,728 on all three
ranks - and `Layer.tiledInput()` (`cuda_kda_block.zig:44`) becomes true, which sends the stack to **glm_mm's tiled
kernels** and packs it under `TF_GLM_DENSE_BITS`. `padOneKdaInput` (`cuda_tile.zig:78-101`) allocates `[m][dims]` bf16,
copies the n true columns of every row, `cuMemsetD8Async` zeroes the rest, and swaps the buffer in at load; the MTP
head's KDA layer is padded the same way.

Consequences at TP=3:

- rank 0: 8,726 -> 8,728, the same two columns as #3697's own pad;
- ranks 1 and 2: 8,341 -> **8,728**, 387 more columns than #3697's per-rank pad, i.e. 3.17 MB a layer a rank extra
  (387 x 4,096 x 2 B), about 111 MB over the 35 KDA stacks including the MTP head. This is the 4.6% wider stack the PR's
  first version measured (ranks 1-2's kda 16.4 -> 16.9 ms, every rank's wall 60.9 -> 61.2 ms), which is why the merged
  default pads each rank to its own width;
- under `TF_GLM_DENSE_BITS=4` - which **both** `scripts/env/dev.env:15` and `scripts/env/prod.env:17` set, with
  `TF_GLM_KDA_PAD=1` at `dev.env:29` and `prod.env:30` - the stack is **quantized**, where #3697's default keeps it
  bf16. The PR counts `188 linears packed` without the pad switch and `290` with it, the difference being the KDA
  stacks. That is a numerics change, not a scheduling one. The knob's route is glm_mm by construction, and the boot
  refuses it otherwise: `cuda_ranks.zig:193`, "TF_GLM_KDA_PAD=1 requires TF_GLM_MM=1 (glm_mm is what reads the padded
  rows)". Neither env file sets `TF_GLM_MM`, so glm_mm is on by default on both arms. Our patch's own receipt says
  the same in its own words: the pad columns are exactly zero (0 of 68 dumped non-zero), but at 4 dense bits the stack
  is quantized where it was not before, so replies differ, and the gate that cleared it was the retrieval fixture, not
  bit-identity.

## 3. What our patch stack still contributes

`patches/engine/0005-kda-pad-one-width.patch` now adds only `TF_GLM_KDA_DUMP` and `dumpOnce` (one dump of a projected
fused stack for the float64 pad check); its own re-seat note records that the pad layout it was written for is
upstream's default since #3697. `0006` and `0010` mention the knob only in the check table's doc rows
(`glm-kda-pad-split`). No patch of ours changes a pad width, a pad site or a kernel route.

| | #3697 unset (pin default) | `TF_GLM_KDA_PAD=1` (pin, production's env) |
| --- | --- | --- |
| pad width, TP=3 | each rank's own: 8,728 / 8,344 / 8,344 | one common width: 8,728 on all three |
| pad columns a row | 2 on rank 0, 3 on ranks 1-2 | 2 on rank 0, 387 on ranks 1-2 |
| where the pad is written | at load, into a new bf16 buffer, zeros after the true columns | the same buffer and the same memset; same site |
| kernel route | staged `tf_glm_bmm_tile` / `tile1` (prompt >= 128 rows), `bmm_decode` (decode) | glm_mm's tiled kernels, packed under `TF_GLM_DENSE_BITS` |
| values a kernel computes | unchanged (byte-proven: `paddedStack`, 13 + 36 hashes) | unchanged at bf16; **changed at `TF_GLM_DENSE_BITS=4`**, the stack is 4-bit now |
| what it buys | 10-11% cold first token for free | the same staged-tile gain plus 4-bit KDA weights (8,728 x 4,096 bf16 = 71.5 MB a layer a rank at bf16, ~18 MB packed) at the cost of the wider rows on ranks 1-2 and of the quantization |

So the knob is not redundant: it trades ~111 MB of extra weights on two ranks for a 4x smaller KDA stack under the
dense bits. It is also not free: it changes replies.

## 4. The measurement that decides, written before any row

Arms, on the same pin, stack, image and boot settings, `KNOBS=dev` explicitly on both:

- **A** - `TF_GLM_KDA_PAD` unset: per-rank pad, bf16 stack, staged bmm tiles. `dev.env` with line 29 removed.
- **B** - `TF_GLM_KDA_PAD=1`: today's dev.env (and production's).

Cells: cold first token at 8k, 32k and 120k (one nonce-line prompt a length, `max_tokens` 1, thinking off), two starts
each, alternating A B B A per length; decode level at 1 and 4 clients on the same two boots (the knob widens ranks 1-2,
so a decode regression is possible even where the prompt wins).

The rule, fixed now:

1. Every reply on both arms is hashed and recorded per cell. The **digest comparison happens before the time
   comparison**.
2. **Digests differ** - which the source says they will, because B packs the stack at 4 bits and A does not - is a
   **stop and report**, never a verdict. The report carries: the per-cell times, the digest delta, and the retrieval
   fixture's result on both arms as the only evidence that could justify changing the incumbency. Choosing between the
   two is the owner's call.
3. **Digests equal** (only possible if the arms are run without the dense bits, or if a later change makes the packed
   path bit-exact) - then a time verdict applies, with the 2% chunk-to-chunk band of `prefill_passes.py` as the
   significance floor, and A adopted only if it is not slower.
4. Any cell where the two starts disagree by more than 2% is re-taken before the arm's number is quoted.

The admissible outcomes, so the result is decided rather than discussed:

- A slower than B at any length by more than the band, digests different -> keep production as it is, close the item.
- A equal or faster and digests different -> owner's numerics call with the fixture; no automatic change.
- A equal or faster and digests equal -> adopt A (drop the knob from the env files) in a separate patch.

Not in the design, on purpose: a third arm with the common width kept at bf16 (the pre-#3697 `TF_GLM_KDA_PAD=1`) would
isolate width from quantization but needs a patch - `tile_pad` currently couples them - and would be an upstream-shaped
PR of its own, not a row on tonight's queue.

## 5. Queue and scorer: withheld

Per the instruction's own branch, no queue script and no scorer are written now: #3697 is in the pin and our knob does
something different, so the deliverable is this note. When a window opens, the queue is two cells (`A` and `B`) over
the three cold lengths and the two decode levels, `KNOBS=dev` with line 29 edited per arm, and the scorer is the
existing `scripts/cells.py` beside a digest column: a three-line script whose STOP row prints the digest delta and the
word `STOP-OWNER` instead of a winner. Nothing about it needs measuring to be written, and nothing about it is worth
writing until the owner says which way a digest difference should go.
