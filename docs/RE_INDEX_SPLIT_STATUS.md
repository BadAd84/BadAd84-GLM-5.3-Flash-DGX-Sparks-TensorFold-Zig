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
