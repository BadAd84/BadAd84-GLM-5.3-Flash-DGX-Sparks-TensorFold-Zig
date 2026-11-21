# The series re-seated on upstream main's tip `46c6ee229` (2026-11-21), scratch only

The 47-patch series, pinned at upstream main `1ece6e6db`, put onto the tip `46c6ee229d2ea28bde8b273381c0f0443861cdd6` (tree `56ccf3b8bf3a621c094e6cfb1981af904dd517e7`, 192 commits later, the merge of #3697) so a GPU window can measure the stack on the tip. **It is not installed**: `patches/` and `scripts/config.sh` still say `1ece6e6db`, because every GPU result so far is on that base and a repo that moved under its evidence would be a repo whose numbers no longer describe it. The output is archived in `archive/reseat-tip-46c6ee2-patches.tar` (the seven package directories with their `RECORD.md` and `SHA256SUMS`; 1,710,080 bytes, sha256 `761eebd1d1403c5a441a0f41936eaa1398aebb2fb678f707b45499da9966ab17`; the gate host's name is replaced by `<gate-host>` in its `RECORD.md` files).

Companion records: the text survey that preceded it, `reseat-tip-46c6ee2-survey.md`, and the gate log, `gate-reseat-tip-46c6ee2.log` (the gate host's own `run.log`, scrubbed of host names and paths).

## What was built

- Result tree `1fd680b2b681e80d1e40492f881b444602a5bc89` (chain head commit `db5f6be4f7a4bc3241f9e569011c0fe3057f2e3b` in a scratch repository): the tip plus all 47 patches in the repo's order (engine 38 with 0011 vacant, then pr1411, cache-salt, learn-starts, solo-cuts, disk-any-position, restore-held).
- Method: the old chain was rebuilt from the current files on the pin and its final tree equals the tree the series was gated at on the pin (`5ae4bbe5e4186133616753872b735b42ea18184d`), and every package boundary tree equals the id its `RECORD.md` names. The new chain is one `git merge-tree --write-tree` per patch against the chain so far, conflicts settled by hand. A patch that applied clean keeps its header and every added and removed line (checked for all 47: same file set and same per-file added and removed line multiset as its source); only offsets and context moved. No file of the 237 it touches has CRLF.
- The tree id was computed three ways (an index apply, a worktree apply, the gate host's own build: `SG id stack 1fd680b2b681e80d1e40492f881b444602a5bc89 applied=47`), and they agree.

## What changed

44 patches apply clean. Three were partial and are repaired (the survey's names, with the file of each rejected hunk now known from a reproduction that kept the `.rej` files):

| patch | rejected | file | repair |
|---|---|---|---|
| `0005-kda-pad-one-width` | 2 of 8 | `cuda_kda_block.zig` (the dump declarations beside `pad_to`), `cuda_tile.zig` (the dump read, a doc line above it reworded by #3697) | one conflict: upstream's new `tile_pad` and our `dump_driver` and `dump_path` both kept, `tile_pad` first; the second hunk lands unchanged under the reworded line |
| `0019-sparse-onepass` | 1 of 16 | `zig/src/cuda/kernels.zig` | its `glm_onepass` fatbin row kept after upstream's new `inkling2_attn` and `inkling2_pattn` rows |
| `0020-onepass-pipe` | 1 of 20 | `zig/src/cuda/kernels.zig` | its `glm_onepass_pipe` row placed after `glm_onepass`; no line changed |

Nothing is absorbed or refused.

## Patch 0005 against #3697 (the lane's reading, read from the commit and its whole diff)

On the pin the patch added no layout code: `TF_GLM_KDA_PAD`, `padWidth` and the one common `rowWidth` were already upstream's (our PR #1545), and the patch's own header says so (it dates from the v1.2.7 re-seat). What it adds is the `TF_GLM_KDA_DUMP` diagnostic: the registry row, its docs row, two `cuda_env_test.zig` tests, `dump_driver`, `dump_path` and `dumpOnce` in `cuda_kda_block.zig`, and the dump read at the top of `padKdaInputs`.

#3697 pads every rank's KDA input at load to its own width rounded up to eight columns, so prompt windows take the staged tiles; `tiledInput` is an even stack or `tile_pad` with a width divisible by eight; `TF_GLM_KDA_PAD=1` keeps main's common width and the `glm_mm` tiles; `project` is untouched. They compose: with our switch on, `pad_to = padWidth(common)` and `tile_pad = true`, exactly the pin's layout, so the bytes are unchanged and only the dump hook is added (it returns at once unless the variable is set); with the switch off none of upstream's default path is touched. One inference: with the switch off the dumped stack is now the padded one (`rows x alignedWidth`), because upstream pads at load, where on the pin the dump was `rows x width`. Whether 0005 still earns a place is a measurement and not a text call, so it is kept.

The consequence for what the recipe buys: the recipe's pad also changes numerics (the patch header: at `TF_GLM_DENSE_BITS=4` the padded stack is quantized where it was not before, so replies differ), while #3697 keeps the stack bf16 and row-major and tiles it for prompt windows only (decode windows keep `tf_glm_bmm_decode`). So #3697 should help a stock user's cold first token and leave decode where it was; that is an inference from the two descriptions until queue96's `ut1` measures it.

## The gate

`python scripts/spark-gates.py gates --pin 46c6ee229d2ea28bde8b273381c0f0443861cdd6 --pin-repo work/up/TensorFold --tree base --tree stack=<the seven patch directories in order> --expect stack=1fd680b2b681e80d1e40492f881b444602a5bc89`, run `sg-20261121-000728`, 00:07 to 00:53 UTC, verdict **PASS**: every step rc 0 on both trees, `gate-names` none listed and none new (the host's `cuda_disk_test` flake did not appear on either), lean 7,202 files and 168 problems on the base against 7,272 and 168 on the stack, 0 new. Base `test-cuda-host`: 440 of 440 steps, 7,811 of 7,854 tests (43 skipped); stack: 444 of 444 steps, 8,027 of 8,070 tests. `scripts/check-patch-packages.sh` over the output reports CLEAN (7 package directories, none grandfathered), and the local lean run reports 0 new.

One mutant per repaired patch (the stack with exactly one line changed, as an extra patch at the end of the engine directory, control being the stack's own `test` step, 444 of 444 steps):

| patch | line changed | result |
|---|---|---|
| 0005 | `environment.zig`: the `TF_GLM_KDA_DUMP` row's `.kind = .path` to `.flag` | killed: two `cuda_env_test` cases (the strict-env reader list and the levers' blank-as-unset and control-character test) |
| 0019 | `cuda_onepass.zig`: `min_heads = 17` to `16` | killed: `cuda_onepass.test.onepass: prompt rows on an FP8 cache at TP=3's head counts only` |
| 0020 | `cuda_onepass.zig`: `pipe_smem = smem + 24 * 4` to `smem + 24 * 4 + 8` | killed: `cuda_onepass.test.onepass pipe: the knob gates the pipeline and its smem matches SmemPipe` |

## The source tar

`work/src-m140a.tar` (198,307,840 bytes, sha256 `30bd481137e7d0bbe83e2b7241fcc7720d170718565b366547ccc988fff69822`, 13,598 entries, no `.git`), made after the gate passed by `tar --force-local -C <the stack tree> -cf work/src-m140a.tar .`, the shape `scripts/build-image.sh` documents. Three files in it were compared byte for byte with the tree's blobs.

## Left for the measurement

- Whether the stack on the tip is level with the stack on the pin on every cell and every reply (the sync rule again), and what it buys over stock main at the tip (queue96's `ut1`).
- One observation, not touched: `0020` carries a glued comment line that `0021` removes; the pin's gated tree has it too and the re-seated chain reproduces it exactly.
- The patches are archived but not installed; installing means copying the seven directories into `patches/`, moving `TF_REF`, regenerating the records and running the gate on the repo's own copy.
