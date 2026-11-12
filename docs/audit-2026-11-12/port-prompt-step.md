All gates are in and the verify tree matches. Final report follows.

# Lane `prompt-step`: six ports, patches cut, gates clean against the baseline

Tree: `work/ports/prompt-step/tree` (pin `9c9bf542` + `patches/engine/0001..0042`). Patch files, in apply order:

| # | patch file | fork sha | files touched | how it landed |
|---|---|---|---|---|
| 01 | `01-chunk-grid-end.patch` | `cfa2cd93c`, plus the log line from `50bf69eb6` | `cuda_engine.zig`, `cuda_prompt_pair.zig` | hand-ported |
| 02 | `02-head-flag.patch` | `a8ccc5c81` plus the fork tip's two later head sites | `cuda_engine.zig`, `cuda_prompts.zig`, `cuda_prompt_pair.zig`, `cuda_prompt_pieces.zig`, `cuda_snapshots.zig`, `glm_prompt_host.zig`, `glm_snapshot_host.zig`, `test_support/glm_snap_fixture.zig` | hand-ported |
| 03 | `03-whole-pass-steps.patch` | `1b4bd2975` | `cuda_engine.zig`, `cuda_follow.zig`, `cuda_lanes.zig`, `tests/cuda/glm_lanes_tests.zig`, `tests/cuda/glm_paged_tests.zig` | hand-ported |
| 04 | `04-batch-mark-inside.patch` | `03138041e`, plus the whole-pass test from `1b4bd2975` | `cuda_lanes.zig`, `glm_prompt_logprobs_host.zig` | hand-ported |
| 05 | `05-follower-disk-bind.patch` | `a3c043cca` | `cuda_follow.zig` | hand-ported (one line, fork's text verbatim) |
| 06 | `06-one-chunk-wiring.patch` | `083da32bb`, `7d01784c3`, two lines of `a6f5615d4` | `cuda_engine_ovn.zig`, `cuda_follow.zig`, `cuda_forward.zig`, `cuda_engine.zig`, `cuda_one_chunk.zig`, `cuda_one_chunk_keep.zig`, `cuda_snapshots.zig`, `build/glm_family_host.zig`, new `glm_one_chunk_host.zig` | hand-ported |

`git apply --check` of a raw fork diff was tried first on 01 and refused (our pre-state has a different doc line and a four-assert test where the fork has five), and every later port edits lines the fork reached through features we do not carry, so all six are hand-ported. Nothing was stubbed.

## Per port

**01, chunk grid end.** `chunkEnd` ends a chunk at `(start / prompt_rows + 1) * prompt_rows` instead of `start + prompt_rows`, and the fork's six-assert test replaces our four-assert one. Our old assert `chunkEnd(5001, 9000, {5001, 7049}) == 7049` cannot hold under the realign (the answer is 6144), so the fork's test is the correct replacement, not an addition. Also takes the fork's `std.log.info("glm: paired prompt step ...")` after `pair.steps += 1`; `Pair.steps` already exists, so no counter was added. Left out of `50bf69eb6`: its `fa.taps`/`fb.taps` lines, already in our `cuda_prompt_pair.prefill`.

Callers checked, none needed an edit. `cuda_follow.chunkOf` keeps `a_end == start + engine.prompt_rows`; I confirmed the fork has the same guard in the same place (`two = pair and a_end == start + engine.prompt_rows and ...`), so it is not a local invention and it is exactly what makes a wide step grid aligned after this change. `cuda_lanes_fill.cut` is `chunkEnd` itself and its four asserts still hold (I walked each). `cuda_one_chunk.cut` already computed `(start / C + 1) * C` for its own end, so it agrees with the new `chunkEnd` rather than fighting it. `cuda_prompt_pair.pairRows` is only reached at grid starts.

Changed from the fork: its two-line doc comment is one doc line plus a trailing comment on the realigning line, because the repo lean gate counts a comment line followed by another comment line as a problem.

**02, the head flag.** `Engine.head = o.mtp and !o.drafter`, gating five absorb sites together: `cuda_engine.prefillChunk` (`prompt_solo.mtpRows`), `cuda_prompts.pass`, `cuda_prompt_pair.mtpRows`, `cuda_prompt_pieces.run`, and `cuda_snapshots.planBytes`'s head term.

Every reading of `e.mtp` in the tree, with the verdict:

| site | stays `mtp` or becomes `head` | why |
|---|---|---|
| `cuda_engine.zig` fingerprint `o.mtp`, `fp.mtp += drafter` | mtp | rank agreement on the loaded head |
| `cuda_engine.zig` `weights.load(..., o.mtp)` | mtp | the drafter reads the head's `.draft` weights, so they stay loaded |
| `cuda_engine.zig` `if (o.mtp) e.bs = initShared` | mtp | shared verify buffers exist whenever the head is loaded |
| `cuda_engine.zig:504` `if (!e.mtp) return error.NoDraftHead` | mtp | the draft path, not the absorb |
| `cuda_engine.zig` prompt absorb (`prompt_solo.mtpRows`) | **head** | absorbs rows nothing reads with a drafter |
| `cuda_prompts.pass` batched absorb | **head** | same |
| `cuda_prompt_pair.mtpRows` | **head** | same, both chunks of a pair |
| `cuda_prompt_pieces.run` | **head** | same, MULTI_FILL pieces |
| `cuda_snapshots.planBytes` | **head** | plans head rows for a state whose `mtp_len` now stays 0 |
| `cuda_snapshots.seal`, `keepAs` | mtp | both read the state's own `mtp_len`, which is 0 when the head absorbs nothing |
| `cuda_disk_ranks.shape` | mtp | the fork writes `e.mtp and !drop_mtp`; DROP_MTP is unported |
| `cuda_lanes.zig` facts, copy confidence, `NoDraftHead` | mtp | drafting capability, not absorbing |
| `cuda_ranks.zig` fingerprint word, `cuda_tile.zig` `w.mtp` | mtp | wire and weights |

Three stand-in engines get the flag because they are `undefined` apart from the fields they set and the code now reads it. Deviation from the fork, stated plainly: `glm_snapshot_host.zig` sits at exactly 600 lines, the lean limit, so its two bare engines use one destructuring statement `e.mtp, e.head = .{ true, true };` rather than the fork's second line, and both are set where the fork sets only one and lets the other read an undefined bool. I checked that the destructuring form compiles and that `zig fmt` leaves it on one line before using it. Left out of `a8ccc5c81`: the `cuda_prof.zig` `mla_chunks`/`mla_merge` sections, which belong to the unported latent profile split.

**03, whole prompt pass steps at its marks.** `prefillFn` loops `Leader.chunkOf`; `marks` leaves `Engine.prefill` and `Leader.prefill`. I took the fork tip's single unified loop rather than keeping patch 0008's `if (reply.rowsOf(s) != 0)` branch, after reading `cuda_reply_prefill.gate` and `rowsOf`: both reduce to the plain gate and cap 0 unless the stream carries a yield check, which only a background pass does. Dropped `slice` from the call (unported FILL_SLICE_MS). Left out: the fork's comment hunk in `zig/src/native/cuda_glm_disk.zig`, a file this tree does not have.

Reachability, which `LeftoverStepState` corrected mid-run and I verified in the brief's terms: `LaneHost.launch` only uses the whole-pass `backend.prefill` when the backend has no `prefill_step`, so this path serves the `TF_GLM_PROMPT_STEPS=0` configuration and REPLY_PREFILL's background pass, not a default serve.

**04, no batch for a prompt with an interior mark.** `canBatch` rewritten to the fork's early returns plus the mark loop; the existing stand-in stream gains `marks`. Both fork tests land in `glm_prompt_logprobs_host.zig`, including the whole-pass `chunkEnd` walk from `1b4bd2975` (the brief's placement). I walked all four of its cases by hand at our `C = 2048` before adding them. Left out: the `copy2d` stub and its `cuMemcpy2DAsync_v2` assignment, which exist for the unported sampler change `0a77dcd7d`.

**05, follower `.disk` bind.** One line, the fork's exactly. Found with `git log -S` as `a3c043cca`, the same commit patch 0023 ported the rest of. Inert here: nothing assigns `Engine.link`, so rank 0 never sends a disk step.

**06, ONE_CHUNK wiring.** Not parked, and it is whole for the knob's own surface. Wired: the knob in `cuda_engine_ovn.open`/`close`; `plan`/`put`/`arm` in the leader and `read`/`arm` in the follower; the `kdaBlock` hook in `cuda_forward.mixer`; `enter` moved after the gate, which is where `083da32bb` always had it; `defer cap.marks = 0` in `leave`; and `keepAt` taking `heldPages` and recording `.shared`.

Two genuine defects in the knob-on path were in the tree before this and are fixed here, not by me inventing anything: `leave` zeroed `cap.marks` before its keeps, so the first `keepAt` would have returned `error.NotAtMark` for every inner mark (that is exactly what `7d01784c3` says it found on GB10), and `keepAt` planned with the shared store's held pages while leaving `Snap.shared` at 0, so with TF_KV_SHARE on the restore would have failed `error.SnapshotSize`.

One adaptation forced by an unported feature, and it is the thing that made the first gate run fail: `Capture.create` called `cuda_sparse.pooledRow`, which is the PK8 knob's function and does not exist here. The file compiled only because nothing called `create`. It now uses the non-PK8 width that function returns, `i_dim * 2`, which is the expression `cuda_snapshot_layout` and `cuda_state` already write inline for a pooled key's bytes. That is a left-out, not a stub: with PK8 absent there is no other width.

Knob off is byte for byte today's path, and the specific reasons are in the patch header: `plan` returns null, `put` memsets three header words a chunk step already leaves zero, `arm`/`read` are no-ops on a zero word, the mixer hook needs `Forward.one` which only `enter` sets, and making `heldPages` public changes no code.

The fork's host test comes with it as `zig/glm_one_chunk_host.zig`, registered in `zig/build/glm_family_host.zig` rather than through the fork's test block in `glm_snapshot_host.zig`, again because that file is at the 600-line limit. It runs inside `test-cuda-host`. Three of its five cases encode the fork's 4,096-row chunk and would assert the wrong thing here, so their numbers are re-derived for our 2,048-row chunk (warm turn 200,031 to 201,397 with the grid point at 200,704; slots case over 1,500 rows with marks at 300, 700, 1,101 and 1,497; wire case round-tripping the warm turn over 1,366 rows). The two cases written in terms of `prompt_rows` are the fork's unchanged. Left out: the fork's GPU check `zig/tests/cuda/glm_onechunk_tests.zig` and its `main.zig` registration.

## Gates

Run as `bash scripts/gates.sh work/ports/prompt-step/tree prompt-step`, plus the two extra steps Main added. Logs in `/home/adam/gates/prompt-step-*.log`.

| step | baseline `fix6` | lane `prompt-step` |
|---|---|---|
| `check-native-cuda-host` | rc=0 | rc=0, 7/7 steps |
| `test-cuda-host` | rc=1, 26 failing names | rc=1, 26 failing names, 1884/1915 tests passed |
| failing NAME sets | 26 | 26; `comm -13` base head prints nothing, so zero names are mine |
| `zig fmt --check zig/` | rc=0 | rc=0 |
| `zig build compile-cuda-tests` | not in the baseline run | rc=0 |
| lean, base `work/f5/tree` against head | 5991 files, 127 problems | 5992 files, 127 problems, `lean_new` reports 0 new, rc=0 |

The 26 shared names are the baseline's file-permission, symlink and FIFO tests (`auth.test`, `auth_scope_*`, `benchmark_*`, `drama_voice_tool`, `request_log`, `slide_key`) that cannot pass on `/mnt/c`. The two file counts differ by one because of the new host test file, which is the tell Main asked for that each side ran its own tree.

The first gate run failed on the `pooledRow` error above, which is the knob-wiring compile trap the audit predicted; the table is the clean re-run after that fix.

## Verify tree

`scripts/arm-tree.sh 42 work/ports/prompt-step-verify`, then `git apply` of `01` to `06` in order (each printed "applied"), then `diff -rq --exclude=.git` against the lane tree: one line, `Only in work/ports/prompt-step/tree: .zig-cache`, which is build output rather than a source path. Zero differing source paths. The verify tree is deleted.

## What the host gates did not check

The host gates compile no `.cu` or `.cuh` and do not build the GPU test binary's run. I touched no kernel file. Three edits sit in files the host build does not execute:

- `zig/tests/cuda/glm_lanes_tests.zig` and `zig/tests/cuda/glm_paged_tests.zig`, one dropped `null` argument each (port 03). These ARE now compiled, by `zig build compile-cuda-tests`, which returned rc=0; I re-read both edits after making them.
- `zig/src/families/glm/cuda_one_chunk.kdaBlock` and `Capture.create` are compiled for the first time by this patch set, since nothing called them before, but no host test can execute a kernel, so only their types are proven.

## Doubts, stated plainly

1. **Port 06 has never run.** Everything above says the knob can now be switched on and that knob-off is unchanged; neither half has been on a GPU. If the parent wants one port parked, this is the one, and the reason would be that a knob nobody has booted is worth less than the risk of the `enter` move and the mixer hook. I did not park it because the knob-off argument is mechanical and checkable line by line, and because leaving `leave`'s mark reset and `keepAt`'s `.shared` unfixed keeps two known defects in the tree.
2. **Port 02's `planBytes` term is the one piece whose absence would be safe.** If it is dropped, admission over-estimates a kept state's bytes with a drafter loaded, which is conservative and cannot fail. I took it because the brief names it and because the fork has it, but it is the natural thing to split out if the parent wants patch 02 smaller.
3. **Port 03 is knob-gated,** as `LeftoverStepState` established after its first message. It is a correctness repair for `TF_GLM_PROMPT_STEPS=0` and for the REPLY_PREFILL background pass. The unified loop changes the background pass's gate selection in one corner (a stream with `yield_check` set while the knob's settings are absent would now take `stops` instead of `cancelled`); that is the fork's own tip behaviour and I believe it unreachable, but I did not prove `yield_check` cannot be set with the knob off.
4. **Port 01's realign changes how many steps a resumed prompt takes** even where pairing is off, because a chunk after an off-grid start is now short. Row bits do not depend on chunk bounds, so replies should not move, but that is the fork's claim and a digest check is what settles it.
5. **The three re-derived test cases in `glm_one_chunk_host.zig` are my arithmetic, not the fork's.** They pass in `test-cuda-host`, so they are self-consistent with the planner, but they assert what I computed the planner should do at 2,048 rows. If `prefill_rows` ever becomes 4,096 the fork's original numbers are the ones to restore.

## What each patch needs from a GPU run

- **01**: `glm: paired prompt step` lines in the serve log for a prompt resumed from an off-grid kept state, where today there are none, and the same reply digest with `TF_GLM_PROMPT_PAIR` on and off.
- **02**: with `--drafter` loaded, the `mtp` profile section of a prompt chunk at zero and the cold prefill about 4 per cent shorter; unchanged reply digest; a turn resumed from a state kept under the new plan restoring without `error.SnapshotSize`. Without a drafter, nothing should move at all.
- **03**: a prompt resumed off the 2,048 grid keeping a state at every interior mark under `TF_GLM_PROMPT_STEPS=0`; `glm-resume-check` unchanged; with REPLY_PREFILL on, the background pass still stopping at its gates and still capping its chunks.
- **04**: nothing for a default serve, both tests are host tests. With `TF_GLM_OVN_KDA_CHUNKED=1`, a short fresh prompt with an interior mark must leave the batch path and keep its state.
- **05**: nothing while `Engine.link` is unassigned. When the tier is wired, a follower's bound slot must survive a disk step.
- **06**: first with the knob off, prompt and kept-state digests identical to the pre-patch image. Then with the knob on and a prompt carrying two marks inside one chunk: the capture size line once at load, both states kept rather than `error.NotAtMark`, each restoring to the same tokens as a resume from the knob-off state at the same row, and with TF_KV_SHARE also on, no `error.SnapshotSize`.