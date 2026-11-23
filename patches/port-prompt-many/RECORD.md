# RECORD.md - patches/port-prompt-many

## Base: upstream main `fa13df5dd1fdd23ada775510a464c9aa03a39e09`, then the 32 patches of `patches/engine/`

Applies to the engine series alone (tree `59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450`). `patches/port-multi-fill` also
carries this vtable block (MULTI_FILL cannot be admitted without it), so the two packages are alternatives, not a stack.

Source: `archive/ai-engine`, branch `ovn-batchresume`, commit
`71217588c65fb832bb6b570cc7d52526913755e8` (2026-10-29): "glm cuda: short prompts admitted together beside stepped fills
(TF_GLM_PROMPT_MANY)".

The text was edited twice: the switch is a `.glm` flag row `TF_GLM_PROMPT_MANY` read as `TF_GLM_PROMPT_STEPS` is (the
fork read it from `getenv`), and it **defaults off** so that applying the package is additive and the arm turns it on
(the fork's production default was on). A host test pins the vtable pair: `prefill_many` set and `many_rows =
engine.prompt_rows` with the knob on, and both clear with it off.

`apply.sh --check` against the engine series: `before: 59bcb17a86a99e7dff5c5e6d0fabfb4c8cb59450`, `checked 1 patch(es);
tree id: 20be2ed8893783afecbc5a95c6896b6deddfa524`, rc 0, nothing written.

Screened: `check fmt ctest` rc 0 on tree `20be2ed8893783afecbc5a95c6896b6deddfa524` (`iter --name port-prompt-many --pin
fa13df5dd1fdd23ada775510a464c9aa03a39e09 --dir patches/engine,patches/port-prompt-many check fmt ctest --max-load 14`,
`ITER-DONE rc=0` after 351 s; `check-native-cuda-host`, `fmt` and `compile-cuda-tests` each clean, no error lines). Host
tests (`test`) are NOT run and stay open until the integrator runs them. No compile ran on the workstation.

## The measurement that decides it

Batched short-prompt admission at the levels the fork's screen named: `TF_GLM_PROMPT_MANY=1` against unset at 1, 2, 4, 6
and 8 streams of short text prompts, replies equal. The expected cell: **on at 4 and 6 streams, off at one**, which is
what the review's screen recorded (+1.9% at 4 and +1.6% at 6 against -1.3% at one). Under the repo's no-regression rule
it can only ship if the one-stream cell is inside the boot spread when measured on this series.

Patches, in file-name order:

- `0001-glm-prompt-many.patch`
