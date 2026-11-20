# How the series sits on upstream main's tip `46c6ee229` (survey, 2026-11-20)

`scripts/reseat-survey.sh 46c6ee229 work/reseat-tip patches/engine patches/pr1411 patches/cache-salt patches/learn-starts patches/solo-cuts patches/disk-any-position patches/restore-held`: the tip is `46c6ee229d2ea28bde8b273381c0f0443861cdd6` (192 commits past the series' current pin `1ece6e6db`, the merge of #3697). A verdict is about text only (`clean` applies whole, `partial` applies with rejected hunks); nothing was compiled and no patch was changed.

**44 of 47 patches apply clean, 3 are partial, none is absorbed or refused.**

| patch | verdict | hunks | rejected | files |
|---|---|---:|---:|---:|
| `0005-kda-pad-one-width.patch` | partial | 8 | 2 | 5 |
| `0019-sparse-onepass.patch` | partial | 16 | 1 | 10 |
| `0020-onepass-pipe.patch` | partial | 20 | 1 | 13 |

Why each is partial, from the upstream commits since the pin that touch the patch's files (`git log 1ece6e6db..46c6ee229 -- FILE`):

- `0005-kda-pad-one-width`: `ae8f0a10f` (#3697, the uneven KDA stack padded to 16-byte rows so prompt windows take the staged tiles) edits `cuda_kda_block.zig` and `cuda_tile.zig`, which the patch also edits, and `platform/environment.zig` took three commits. This is the one that needs a decision, not only a context fix: upstream now pads the stack at load by default and leaves `TF_GLM_KDA_PAD=1` meaning main's common width; whether the patch's one-width layout still adds anything over #3697 is a measurement (queue96's `ut1` against queue91's `mps` is the first one).
- `0019-sparse-onepass` and `0020-onepass-pipe`: one rejected hunk each. The files they touch that upstream changed since the pin are the kernel registrations (`zig/build/cuda_kernels.zig` and `zig/src/cuda/kernels.zig`, extended by `f2d7e3bff` and `82386e8fd`, other families' kernels) and `platform/environment.zig`; which of them holds the rejected hunk was not inspected (the survey removes its `.rej` files), so reading them as context-only conflicts is an inference.

The 44 clean patches are only clean as text; each still needs the gate and, where a default path changed, its cells, as at the last re-seat (OVERNIGHT section 70). Not done: no re-seat, because the GPU window is occupied until the queues in `docs/OVERNIGHT-2026-11-12.md` section 72 finish and queue96 says what #3697 gives a stock user.
