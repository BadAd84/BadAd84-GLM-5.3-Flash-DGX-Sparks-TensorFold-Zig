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
