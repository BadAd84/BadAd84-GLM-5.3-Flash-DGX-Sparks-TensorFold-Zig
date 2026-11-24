# Specification: `tf_glm_index_split` (TF_GLM_OVN_DECODE_INDEX)

Written from OUR OWN call sites and primitives only (`zig/src/families/glm/cuda_index.zig`, `zig/kernels/cuda/glm_index_pools.cuh`),
with no reference implementation open. It exists so the kernel can be implemented from this text alone, which is what the
no-copying rule requires. It states behaviour and required results, not another file's code or structure.

## Launch contract (the caller's ABI, from `cuda_index.zig`)

The kernel is called as `tf_glm_index_split(S, np, pos, K, chs, cp, step, scratch, hist, gt, TOK, CNT, pt, page_rows)`:
`S` is a `const float*`; `np`, `page_rows` are 64-bit; `pos`, `K`, `chs`, `cp`, `step` and the five pointers are 32-bit.
`hist` and `gt` are passed as their own pointers, at the offsets the Layout section gives, and `scratch` is the base of
the same region. The grid is `(rows, cp)`; the block is 128 threads. The five launches run on ONE stream, which is what
makes a previous launch's writes ordered with respect to a later launch's reads. `np >= K` is guaranteed by the caller
(`Kernels.takes`), so exactly `K` pools are always picked and a digit always exists.

## Purpose

A decode window with few rows and many pools picks its top-K pools by a chunked radix select, one CTA per (row, chunk),
instead of the one-pass selection the older path uses. "Chunked" is a speed decision: the scores of a row are visited in
chunks so no single CTA walks the whole row.

Called only where the caller decides the shape qualifies (`Kernels.splits`): `rows` below the split threshold, `rows`
below the decode ceiling, and `np` at or above the split floor.

## Inputs

- `S`: the scores, row-major, `rows` by `np` `float`. Score order is by the unsigned order of the bits, with `-0` and
  `+0` treated as equal: `order_key(float)` in `glm_index_pools.cuh` defines that mapping and must be the same one the
  rest of the index path uses.
- `np`: pools per row.
- `pos[0]`: the row's position, used to derive the visible pools.
- `K`: pools to pick per row.
- `chs`: scores a chunk CTA takes (`splitChunk(np)`: 2048 up to 16384 pools, else 4096).
- `cp`: chunks a row takes, a power of two (`splitChunks(np)`, at least 1).
- `step`: which of the five steps this launch performs, 0 to 4.
- `scratch`: the caller zeroes the `tot` region before step 0 (`rows * 1024` dwords at the front, which is
  exactly `rows * 4 * 256`). It does NOT zero `hist`: the kernel writes each chunk's histogram before reading
  it, so `hist` needs no initial value.
- `pt`, `page_rows`: the token indirection described under Output.

## Layout inside scratch (the caller's carving)

- `tot`: `rows` by 4 by 256 `int` at `scratch`.
- `hist`: `rows` by `cp` by 256 `int` at `scratch + rows * 1024 * 4` (byte offset). Steps 0 to 3 each overwrite
  their chunk's histogram before that generation is read. Step 4 does NOT write it: it reads the byte-0 histograms step 3
  left, whose writes the launch boundary orders. The caller does not zero it.
- `gt`: `rows` by `cp` `int` at `hist + rows * cp * 256 * 4`.

## The five steps

Every step first reads the row's running radix state: the digits fixed so far, and how many more picks are needed. A step
that fixes another byte updates the row's per-chunk histogram for that byte and accumulates it into `tot`.

The digit for a byte can only be decided once that byte's histogram is complete across the row's chunks, and chunks
are separate CTAs with no barrier between them. The steps therefore PIPELINE: step `p` counts byte `p` and decides byte
`p - 1`, using the totals the previous step completed. `need` and the fixed prefix are not carried in memory; each step
recomputes the chain from `tot` alone, which is what the "reads the row's running radix state" above means.

- **step 0**: count byte 24 over the whole visible range, overwriting this chunk's `hist` entry, and add the counts
  into `tot[row][0]`. Nothing is decided (no byte precedes it). `gt[row][chunk]` is left alone here.
- **step 1**: recompute the digit for byte 24 from `tot[row][0]`; STORE this chunk's counts above that digit into
  `gt[row][chunk]`, overwriting whatever the caller left there; zero this chunk's histogram; count byte 16 over this
  chunk's scores whose byte 24 equals the fixed digit; add the chunk's counts into `tot[row][1]`.
- **steps 2 and 3**: as step 1 with byte `p`, ADD (not store) this chunk's counts above digit `p - 1` into
  `gt[row][chunk]`, because step 1 stored the first contribution and the previous step's own contribution is already in.
- **step 4**: recompute the digits for all four bytes from `tot[0..3]`; emit the picks. It does NOT write `gt` or
  `hist`. A picked pool's output slot is the number of picked pools with a lower pool index. For a pool in chunk `c`
  that is: the sum over predecessor chunks `c' < c` of `gt[row][c']` plus the bins of `hist[row][c']` above digit 0,
  to cover the predecessors' above-prefix keys; plus `min(need, the sum over the same predecessors of
  hist[row][c'][digit 0])`, for the equals those chunks contributed; plus the same two counts over the pools before it
  within its own chunk. Equals count only until `need` of them have been taken, in pool order across the whole row. A pool is picked when its key is above the row's fixed prefix, or equal to it and
  among the first `need` equals, `need` being `K` minus the number of keys strictly above the prefix. Output order is
  pool order, and only the first `K` picks of each row are meaningful. Chunk 0 also writes the incomplete visible pool's
  tokens and the row's output count.

`gt` is written by steps 1 to 3 only, and step 4 must not write it. The caller zeroes `tot` and nothing else, so
`gt` holds unrelated data when step 1 runs: step 1 therefore STORES its first contribution rather than adding to it, and
steps 2 and 3 add. The reason is ordering: a chunk's emission has
to read its PREDECESSOR chunks' counts to know which output slot its picks take, and a step-4 write by a predecessor is
not ordered against that read, so a chunk would observe the predecessor's value with or without its step-4 increment
depending on scheduling. Only the step-3 state of `gt` is stable, and the emission uses `gt[chunk]` plus the byte-0
histogram that step 3 left in `hist`, which is the one byte whose "count above" is not in `gt` yet. Step 4 writes
neither `gt` nor `hist`: both of its reads are of previous launches' writes, which is what makes them ordered. Writing it too would double count.

The `gt` contribution is why step 4 decides byte 0 rather than step 3: a byte's "count above" contributes only once its
digit is fixed, and byte 0's digit is the last to be known.

A chunk whose start is at or past its row's visible bound leaves immediately without writing anything.

## Visible bound

`NP = min(np, max(npool, K))` where `npool = (pos[0] + row + 1) / 4`: a row never considers pools past its bound, but
never fewer than `K` either. Only the visible part of a chunk is scanned.

## Output

- `TOK` at `tokens`: per row `4 * K + 3` `int`. The first `4 * K` are the picked pools' four tokens each, in pool
  order; the last three are the incomplete visible pool's tokens, or `-1` where a token is not visible.
- `CNT` at `counts`: per row, `4 * K` plus the number of visible tokens of the incomplete pool when the row has MORE
  COMPLETE POOLS than `K`, and 0 otherwise. Complete pools are `npool = (pos[0] + row + 1) / 4` of them, which is the
  same quantity the visible bound uses. This is the call site's own rule (`counts[r] = npool > K ? 4 * K + tail : 0` in
  `glm_ops.cu`), and it is the opposite sense from an early draft of this page: every row that reaches the split has
  thousands of pools against a `K` in the tens, so the "0" branch is the unreachable one and the "4 * K + tail" branch is
  what a real row takes.
- Token values come from the pool index through `pt` and `page_rows`: in order when `pt` is null, otherwise
  `pt[t / PAGE] * page_rows + t % PAGE` for `PAGE = 512`.

## Requirements a reimplementation must meet

1. Same picks, same order, for the same `S`, `np`, `pos`, `K`: the output is part of the reply, so a different set or a
   different order is a behaviour change, not a detail.
2. Integer arithmetic only in the counting and the select; scores are compared through `order_key`, never as floats
   directly, so that `-0.0` and `+0.0` cannot order differently from the rest of the path.
3. Deterministic: no atomics order dependence in the result. A count may accumulate in any order (integer sums), but the
   emission order is pool order and the `need`-th equal is the first in pool order.
4. Correct for `nonzero` chunk counts, for a row whose visible bound falls inside a chunk, and for `np` larger than
   `chs * cp` rounded up.
5. Steps are separate launches writing into the same scratch; a reimplementation may change the internal decomposition
   only if the caller's five-step protocol and the scratch layout stay as above, which is what `selectSplit` drives.

## Decisions this page makes explicitly, so an implementer does not choose silently

1. "Cumulative count" means the sum of bins at or ABOVE the candidate bin, scanned from 255 downwards.
2. The chain starts with `need = K`.
3. `tot[0..p-1]` in the step descriptions includes index `p - 1`.
4. "byte p" means bits `24 - 8p` down to `16 - 8p`.
5. Within a step, the listed operations are whole-CTA phases with a barrier between the phases that read and write the
   same shared array.
6. Chunk `c` covers pools from `c * chs` up to `min((c + 1) * chs, NP)`, clipped at `NP`, and a chunk whose start is at
   or past `NP` returns without writing anything. Chunk 0's tail-token and count writes are unconditional, not subject
   to that return.
7. A row's position is `pos[0] + row`; only row 0's is `pos[0]`.
8. Entries of `hist` and `gt` for chunks past a row's bound hold whatever they held before and must not be read; a
   chunk reads only predecessors that are inside the bound.
9. `TOK` slots not written by any pick are undefined when the row's count is 0, which this caller never reaches.
10. The three tail entries are `-1` where the token is not visible, including when the incomplete pool has no visible
    token at all.

## Further decisions from an independent model (2026-11-24)

An independent reviewer modelled this page and compared it against brute-force top-K over 12,318 rows with ties and
random chunk order, and found no divergence and no remaining unordered read. It had to choose six things the page did not
say, and they are decided here so the next reader does not choose:

11. The digit rule: scan bins from 255 downwards and take the first whose count AT OR ABOVE reaches `need`; then
    subtract the count strictly above that bin from `need`. If no bin reaches it, the digit is 0 and `need` is reduced by
    the row's total for that generation, which the caller's geometry never reaches.
12. `order_key` is defined in `glm_index_pools.cuh` and is not restated here; it canonicalises both zeros and orders by
    the unsigned bits. A reimplementation must use that mapping, not one of its own.
13. The slot rule combines the predecessor and local counts before the `min`: an above-prefix pool also counts the
    equals picked before it, and splitting the two `min` operations is wrong when their combined equals cross `need`.
14. The incomplete pool is pool `npool`, and its visible tokens are its first `(pos[0] + row + 1) % 4` lanes.
15. "Phases" means there is a barrier between zeroing a histogram and the next accumulation into it, and between a count
    phase and the reads that follow it in the same launch.
16. The offsets in the Layout section are BYTE offsets; a pointer "is 32-bit" means it points to 32-bit elements, not
    that its address is 32 bits.

## What this specification deliberately does not contain

No code, no register or shared-memory plan, no loop structure and no naming from any implementation. Those are the
implementer's to choose, and choosing them is the whole point of writing this page first.
