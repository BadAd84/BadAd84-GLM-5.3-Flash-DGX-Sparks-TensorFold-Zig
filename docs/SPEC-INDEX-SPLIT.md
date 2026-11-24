# Specification: `tf_glm_index_split` (TF_GLM_OVN_DECODE_INDEX)

Written from OUR OWN call sites and primitives only (`zig/src/families/glm/cuda_index.zig`, `zig/kernels/cuda/glm_index_pools.cuh`),
with no reference implementation open. It exists so the kernel can be implemented from this text alone, which is what the
no-copying rule requires. It states behaviour and required results, not another file's code or structure.

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
- `hist`: `rows` by `cp` by 256 `int` at `scratch + rows * 1024 * 4`. Written by the kernel in every step before
  it is read; the caller does not zero it.
- `gt`: `rows` by `cp` `int` at `hist + rows * cp * 256 * 4`.

## The five steps

Every step first reads the row's running radix state: the digits fixed so far, and how many more picks are needed. A step
that fixes another byte updates the row's per-chunk histogram for that byte and accumulates it into `tot`.

The digit for a byte can only be decided once that byte's histogram is complete across the row's chunks, and chunks
are separate CTAs with no barrier between them. The steps therefore PIPELINE: step `p` counts byte `p` and decides byte
`p - 1`, using the totals the previous step completed. `need` and the fixed prefix are not carried in memory; each step
recomputes the chain from `tot` alone, which is what the "reads the row's running radix state" above means.

- **step 0**: count byte 24. Nothing is decided (no byte precedes it).
- **steps 1 to 3**: recompute digits for bytes 24 up to `p - 1` from `tot[0..p-1]` (the highest bin whose cumulative
  count reaches the running `need`, then subtract the count above it); add this chunk's counts above digit `p - 1` into
  `gt[row][chunk]`, read from the histogram the previous step left; zero this chunk's histogram; count byte `p` over this
  chunk's scores whose bytes above equal the fixed prefix; add the chunk's counts into `tot[row][p]`.
- **step 4**: recompute the digits for all four bytes from `tot[0..3]`; add this chunk's counts above digit 0 into
  `gt[row][chunk]`; emit the picks. A pool is picked when its key is above the row's fixed prefix, or equal to it and
  among the first `need` equals, `need` being `K` minus the number of keys strictly above the prefix. Output order is
  pool order, and only the first `K` picks of each row are meaningful. Chunk 0 also writes the incomplete visible pool's
  tokens and the row's output count.

The `gt` contribution is why step 4 decides byte 0 rather than step 3: a byte's "count above" contributes only once its
digit is fixed, and byte 0's digit is the last to be known.

A chunk whose start is at or past its row's visible bound leaves immediately without writing anything.

## Visible bound

`NP = min(np, max(npool, K))` where `npool = (pos[0] + row + 1) / 4`: a row never considers pools past its bound, but
never fewer than `K` either. Only the visible part of a chunk is scanned.

## Output

- `TOK` at `tokens`: per row `4 * K + 3` `int`. The first `4 * K` are the picked pools' four tokens each, in pool
  order; the last three are the incomplete visible pool's tokens, or `-1` where a token is not visible.
- `CNT` at `counts`: per row, `4 * K` plus the number of visible tokens of the incomplete pool, or 0 when the row has
  more visible pools than `K`.
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

## What this specification deliberately does not contain

No code, no register or shared-memory plan, no loop structure and no naming from any implementation. Those are the
implementer's to choose, and choosing them is the whole point of writing this page first.
