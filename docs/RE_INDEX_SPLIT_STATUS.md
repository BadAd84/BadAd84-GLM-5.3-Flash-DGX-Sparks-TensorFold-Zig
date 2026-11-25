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
