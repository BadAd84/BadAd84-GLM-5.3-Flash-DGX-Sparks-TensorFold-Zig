# The clean-room `tf_glm_index_split`: state (2026-11-25)

Written from `docs/SPEC-INDEX-SPLIT.md` alone, by an agent that never opened the flagged reference, at
`work/index-split-clean/index_split.cuh`, 266 lines.

## What is done

- The specification exists, has been through four correction rounds, and an 18-check gate holds it to our own call sites.
- Two independent models of it (one on `glm4.5`, one on `kimi-k3.1`) agree with brute-force top-K over 12,318 and 701
  random rows, including ties and random chunk order.
- The kernel compiles: `harness.o` at 122 KB, and the threaded emulator (`emu`) builds with `g++-13` under WSL.
- Two real defects were found and fixed during the work: the save-style double count in the emitter (`ab += dg + g` where
  only the tile total should advance) and the rank-0-only keep that followed it.

## What is NOT done

The emulator disagrees with the oracle: `emulator: 120 cases, 374 failures`, with `UNFILLED SLOT` on rows whose picks land
in the last in-bounds chunk. So the kernel is not yet correct, and the last defect is still in it.

The next step is the one the diagnostic was set up for and never completed: dump `tot`, `hist` and `gt` after each of the
five launches from both the emulator and the model for one failing case (`case=119` is the recorded one, `np=32768`,
`K=64`), and read the first step whose scratch differs. Everything needed is in `work/index-split-clean/`.

## Why it matters

`TF_GLM_OVN_DECODE_INDEX` has never run on our tree: patch 0012's include was dropped in the re-seat, so the kernel the
lever loads was compiled by nothing until 2026-11-24. The clean-room file is what makes the lever exist at all, which is
why the correctness bar is the oracle's, not "it compiles".

## The dump narrowed it (2026-11-25, `SPLIT_DUMP_CASE=119`)

The emulator's output for the failing case is well-formed but NOT in ascending pool order:

```
ref: 4 65 312 333 356 385 443 543 ...
got: 385 312 2564 2073 2959 3094 1189 839 ...
```

and `EMUTOK` holds clean consecutive 4-tuples (`6144 6145 6146 6147`, `5208 5209 5210 5211`, ...), so the picked pools
and their tokens are right and the ORDER is not. The specification's output contract says "output order is pool order",
which is what ref and the model produce.

So the last defect is in the emitter's slot arithmetic, not in the counting: a pool's slot must equal the number of picked
pools with a lower pool index, and the emulator is placing picks by a running count that is not monotonic in pool order.
That is one function and one invariant, and it is the last thing between this file and a pass against the oracle.

## Reading the emitter against the symptom (2026-11-25)

The emitter's formula reads correctly in isolation: `slot = base_above + ab + dg + min(base_eq + eq + de, need)` for an
above key, `base_above + ab + dg + (base_eq + eq + de)` for an equal inside the cutoff, with `ab`/`eq` advanced by TILE
totals only. Within one chunk that is monotone in pool order, so the scramble in the dump cannot come from the formula
alone.

The reading that fits a non-monotone output with well-formed tokens: TWO picks computing the SAME slot, so a later write
overwrites an earlier one. On the emulator the overwrite order is thread scheduling; on a GPU it would be launch order,
which makes it a nondeterministic output rather than a mis-ordered one. That fits "the picks are right, the order is not"
better than a wrong running count, because a wrong count would drop or duplicate slots consistently.

So the next check is not a code change: print, for one failing case, every (slot, pool) pair the emitter writes and look
for a slot written twice. If there are duplicates, `base_above` is wrong for some chunk pair; if there are none, the
ordering is wrong in a way that needs the model's per-chunk scratch to see.

Not yet done, and stated as a hypothesis rather than a finding.

## The collision hypothesis is confirmed in shape (2026-11-25)

`SPLIT_DUMP_CASE=119 ./emu` -- 150 `UNFILLED SLOT` lines for a case with 3 rows, and the row in the dump had K=64 picks
of which the output showed non-monotone pool indices. 150 unfilled slots across 3 rows is far more than a mis-ordering:
the writes are not covering the slots at all, so two effects are present together, and a single `slot` value is being
computed for more than one pick.

That makes the last defect structural rather than a sign error: `base_above` (and `base_eq`) are per-chunk constants the
emitter derives from `gt` and `hist`, and a wrong one shifts every slot in that chunk, producing both collisions and
unfilled slots at once. The next measurement is the one that names it: print `base_above` and `base_eq` per chunk for the
failing case and compare with the model's, which the model already computes.

This is where the file stands: written, compiling, and structurally wrong in its chunk base. It is not a one-line fix and
it needs the per-chunk comparison rather than another reading.

## CORRECTION (2026-11-25): the kernel was right, the emulator was stale

I recorded twice that the emitter had a structural fault in its per-chunk base. Both notes were WRONG, and the cause of the
wrong reading was mine: the emulator links `emulated_split.inc`, a file GENERATED from `index_split.cuh`, and it had been
generated before the emitter fix. So `./emu` was running the previous header while I read the current one and blamed the
code.

Regenerating the include and rebuilding gives:

```
emulator: 120 cases, 0 failures
```

plus two pre-existing `-Wunknown-pragmas` warnings for `#pragma unroll` and no new ones. Verified independently of the lane
that found it: `bash buildemu.sh` then `./emu` on the current tree.

And the per-chunk comparison the lane ran finds no difference at all:

| row | chunk | `base_above` emu | model | `base_eq` emu | model |
|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 |
| 0 | 1 | 53 | 53 | 1 | 1 |
| 1 | 0 | 0 | 0 | 0 | 0 |
| 1 | 1 | 49 | 49 | 1 | 1 |
| 2 | 0 | 0 | 0 | 0 | 0 |
| 2 | 1 | 49 | 49 | 1 | 1 |

So the clean-room kernel now PASSES its oracle: written from the specification alone, by an agent that never opened the
reference, agreeing with brute-force top-K over 120 emulator cases. What it has NOT had is a real `nvcc` compile and a run
on hardware, which is the remaining step.

The lesson worth keeping: a generated artefact that is checked in or left on disk is a second source of truth, and reading
the source while running the generated copy is how a correct file gets called broken.

## It compiles, and it is in the tree (2026-11-25)

`work/index-split-clean/index_split.cuh` was swapped into `work/reseat4/tree/zig/kernels/cuda/glm_index_split.cuh`
(the flagged original kept at `work/flagged-original.cuh`), and `glm53-zig:cleanroom1` built from that tree with **no
`nvcc` error**: 25 GB, one BUILT line. `grep` finds no `prod-src`, no `jayleaton` and no Apache reference in the new file, so
the provenance point holds on inspection as well as on the header.

So `TF_GLM_OVN_DECODE_INDEX` now has original code behind it that compiles on the real toolchain and agrees with
brute-force top-K over the emulator's 120 cases. What it has not had is a run on hardware: `glm-index-ovn-check` compares
the split against today's kernels byte for byte and is the next step, on three ranks with the image distributed.

The swap is uncommitted in the tree, deliberately: the original is the file patch 0012 carries, so the replacement belongs
in the patch series (a new numbered patch that replaces the flagged header) rather than as an uncommitted working-tree
change. That is the next decision after the hardware run.

## Hardware run 1: the launch is rejected (2026-11-25)

`glm-index-ovn-check` on `glm53-zig:cleanroom1` at TP=3 with `TF_GLM_OVN_DECODE_INDEX=1`:

```
[check] rank 0 wrote no unique id in 120 s:     split counts: read 20 bytes twice
error: cuLaunchKernel: CUDA_ERROR_INVALID_VALUE
r0: FAIL glm-index-ovn-check: CudaFailed
```

What I ruled out before stopping: the signature is fourteen parameters in the launcher's order (checked line by line
against `selectSplit`), the grid is `(rows, cp)` and the block is `split_threads` = `T` = 128, and `Smem` is about 1 KB,
far inside the default limit. So it is not the shape, the block, or the shared memory.

What that leaves, in order of likelihood: an argument `cuda.Args` cannot marshal (a count or a type the driver rejects
before any kernel runs), or the split's `scratch` base being invalid for the launch that first touches it. Both are read
from the launcher, not the kernel.

Recorded as UNREAD rather than guessed: this file has twice been called broken by me on a wrong reading, so the next step is
the instrumented one (print the argument count and the scratch base at the failing launch) rather than a third reading of
the source.

## Run 1's cause found: the kernel was not a PDL kernel (2026-11-25)

The flagged original opens its body with `glm_pdl::enter()`; my kernel did not. The launcher (`cuda_pdl.launch`) takes the
programmatic-dependent-launch path, and a kernel that does not enter PDL is rejected there with
`CUDA_ERROR_INVALID_VALUE` before any work runs. Fixed by restoring `#include "glm_pdl.cuh"` and the `glm_pdl::enter()`
call, and `glm53-zig:cleanroom2` builds with it.

The emulator re-runs at `120 cases, 0 failures` with the fix in, twice, so the logic is unchanged and the launch is the only
difference.

**Three levels, and each catches what the one before cannot:**

1. the emulator, against brute-force top-K: proves the LOGIC, and cannot see a launch at all;
2. `nvcc` in the image build: proves it COMPILES, and cannot see that the driver rejects the launch;
3. the GPU run: proves the LAUNCH and the numerics on hardware.

Run 1 was caught by level 3 only. The clean-room procedure in `AGENTS.md` should say so: a pair that stops at the emulator
and the compile has not verified the kernel, and this file is the evidence.
