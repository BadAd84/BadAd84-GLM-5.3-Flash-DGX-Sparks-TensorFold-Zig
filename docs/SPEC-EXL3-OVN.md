# Specification: the X3 prefetch-ahead grouped body (`TF_GLM_OVN_X3_NC`)

Written from OUR OWN declarations and call sites, with the flagged implementation (`exl3_ovn.cuh`, patch 0031) treated as
closed for the purpose of writing a replacement. It states what the kernel must compute and what its callers require, not
how the flagged file does it.

## What it is

`exl3_experts.cu` compiles `tf_exl3::grouped_body<NS, 8, 4, LOAD>` for the EXL3 routed experts: an 8-bit activation times a
4-bit trellis weight, tiles of 16 rows. `TF_GLM_OVN_X3_NC` selects a variant that keeps the same arithmetic and changes
only how the trellis words are fetched: `PD` steps of 16-byte loads issued ahead of the multiply, staged in registers, so
the loads are covered by the math.

Two settings reach it: `TF_GLM_OVN_X3_NC` (1 or 2: the number of steps kept ahead) and `TF_GLM_OVN_X3_FUSEDOWN` (whether
the down projection's epilogue writes the scaled output inline). `exl3_experts.zig` reads both and passes them down; the
`nc` field there is `u2` and its comment says "1 or 2, 16-byte trellis loads kept that many k steps ahead".

## Interface a replacement must meet

- `tf_exl3::OvnArgs`: the grouped arguments (`GroupedArgs`: the experts, their trit/trellis pointers, the activation, the
  plan and its counts) plus `OvnTail` (from `exl3_grouped.cuh`: `tb0` gate trellis, `tb1` up trellis, `ew` words an
  expert, `svh` fp16 output scales, `y` fp32 slot rows).
- `nc_body<PD>(o, u, nblock, zz)`: the same arguments and the same `blockIdx`-derived indices as `grouped_body`, for one
  routed item `u`, one output block `nblock` and the plan's `zz`; `PD` in 1 or 2.
- The body runs one CTA per (item, blocked) pair with the launch shape `grouped_body` is launched with, which
  `exl3_experts.cu` fixes: threads `NT = 8` warps of `W = 4` lanes, `NV = NT / 4` vectors and `TW = 32` words a tile.

## Required behaviour

1. **Same arithmetic, same rounding.** The activation is 8-bit, the weight is 4-bit trellis, and the mma is the one
   `grouped_body<CB_MCG, 8, 4>` performs. `PD` changes only when a load is issued relative to the multiply: every output
   element must equal the `PD = 0` path's, bit for bit, and a replacement must demonstrate that equality rather than
   assert it.
2. **One load feeds two words.** A 4-bit lane's two trellis words come from one 16-byte load: the word at the lane's own
   position and the word 31 lanes along, which the lane obtains by a warp shuffle of the loaded word. A replacement may
   choose a different fetch, but each lane must end with the same two words.
3. **No L1 allocation on the trellis path.** The load is the read-only non-coherent form, so the trellis does not evict
   the activation and the output from L1. A replacement that uses a normal load is a behaviour change for the cache and
   must measure its cost.
4. **Bounds.** `u >= a.ucount[0]` returns; a standard item equal to `a.skip` returns; the tile index comes from `zz`
   split by `a.maxm`, `a.sk` and the plan's counts, and a tile past the item's rows must not write outside `y`.
5. **The fused down epilogue, when enabled**, writes the scaled rows to `y` with the fp16 scales in `svh`; when disabled
   the rows are left to the caller as the plain path does.

## What this page deliberately does not contain

No code, no register plan, no loop structure, no naming from the flagged file. Those are the implementer's, and choosing
them is the point of writing this first.

## State of the lever

The header is included by `exl3_experts.cu` but `nc_body` is NOT instantiated there: only `grouped_body` is. So
`TF_GLM_OVN_X3_NC` currently selects a variant nothing calls, and a replacement is worth writing only together with the
call site that would use it, which is the same shape as `glm_index_split` before its include was restored.