> `PortSamplerGuardsTests` is running a newer turn. The output below is from its PREVIOUS run (published 21m36s ago), not the current one. Live progress: `history://PortSamplerGuardsTests`; its next result auto-delivers to its owner.LANE sampler-guards: seven patch files, all gates run and compared with the baseline, verify-tree diff 0.

Patches are in `work/ports/sampler-guards/`, cumulative in this order, each cut by `scripts/mkpatch.sh` against saved pre-change copies in `NN/a`:

---

## 01-logit-gather-blocks.patch

**Fork sha** `0a77dcd7d` "glm cuda: a logit gather broadcasts one block a rank, so TP=3 prompt_logprobs past ~100 tokens no longer hangs" (its own "Fixes #1559").

**Files** `zig/src/families/glm/cuda_sampler.zig`, `cuda_prompt_logprobs.zig`, `cuda_structured.zig`, `zig/glm_prompt_logprobs_host.zig`.

**Applied clean.** `git apply --check` of the fork diff succeeded for all three source files (one hunk at offset 1), so those are the fork's lines verbatim: the `stage` buffer on `Sampler` and on `prompt_logprobs.Buffers`, the rewritten `gather` (`.local` places each rank's block, `.nccl` broadcasts one block a rank into `stage` then places all spans), the new `place` using `cuMemcpy2DAsync`, the rewritten `Spread.post`, and the three call sites (`draw`, `prompt_logprobs.run`, `structured.drawWhole`).

**Added beyond the fork**, in `zig/glm_prompt_logprobs_host.zig` (patch 0024 owns that file here):
- `copy2d` no-op plus `d.api.cuMemcpy2DAsync_v2 = copy2d` in `Heads.score`. `Heads` builds its driver from `undefined` and sets only the entry points the code under test calls, so without the stub the two tests reaching `score` call a garbage function pointer. The fork added the same stub later in `03138041e`; I kept the fact and dropped its sha from the comment.
- `e.smp.stage`, beside the `e.smp.full` the test already sets. The fork leaves the new field undefined; our `run` reads it on the window path those tests take.

**Left as the fork leaves it:** `Sampler.copy`, the 1D device-to-device helper, now has no caller in either tree. I kept it rather than deleting it so the patch is the fork's lines plus the stub. **This is my one real doubt on this patch** - if you would rather not carry a dead private function, deleting it is a one-line follow-up with no behaviour change.

**Gate:** `zig build test-glm-logprobs-host` 7/7 pass. That step is standalone (`zig/build/glm_contracts.zig`), not part of `test-cuda-host`, so it was run by name.

---

## 02-reply-prefill-spares.patch

**Fork sha** `c9468e336` "reply prefill: the eviction guard, and no background pass beside admitted work" (audit `LeftoverCoreNative` D1, `LeftoverTests` D4/D5).

**Files** `prompt_cache.zig`, `prompt_cache_policy.zig`, `lane_job.zig`, `lane_stream.zig`, `lane_host.zig`, `lane_host_warm_test.zig`, `families/glm/cuda_native.zig`, `native/cuda.zig`, `cuda_startup_phase.zig`, `cuda_warm_serve_test.zig`.

**Hand-ported**, except `lane_host_warm_test.zig` whose three fork hunks applied clean (`git apply --include`). The fork diff failed on `lane_host.zig` hunk 2, `lane_job.zig`, `lane_stream.zig`, `prompt_cache.zig`, `prompt_cache_policy.zig`, `cuda.zig` and `cuda_warm_serve_test.zig`.

**The shape I chose on `warm_alone`.** Our 0025 carried the fork's pre-c9468e336 `warm_alone`; the fork removed it and moved the rule into the core. I took the fork's shape: `warm_alone` is gone from all six files, `warm_spares` replaces it, `quiet()` loses the `warm_alone` term, and `setup` now drops a background prompt-only pass whenever `h.admitted.items.len > 1`, whatever the quiet window. So other families change behaviour exactly as the fork has it (qwen27, qwen4, Nemotron Omni, the Flash Next batch host no longer run a pass inside a live fill); for GLM the outcome is the one `warm_alone` already produced. `git grep warm_alone` is now empty.

**What differs from the fork's lines, and why** (all in the header too):
- `lane_job.zig` keeps our `keepBornFrame(..., job.request.images, job.frame)` inside the fork's guard; the fork's base had `keepBorn`.
- `lane_stream.zig` guards our `lookupUserFrame` line with condition `!r.promptOnly()`; the fork's base had `lookupUser` and `r.embedding == null`. The two `store.spares_only` lines are verbatim.
- `prompt_cache_policy.zig`: the fork edits `victimBut`'s last line; ours routes `victimBut` and the `keep_others` path through `victimIn`, so the clause goes on `victimIn`'s `return best orelse oldest;` and covers both. The fork's new doc comment goes on `victimBut`.
- `lane_host.zig` `quiet()` keeps our `h.load.yields` accounting line.
- The fork changes `Host.serve` to take the family as a comptime argument. Our 0025 reads the family's warm facts in `openWith`, holds them on `Host` and passes them through `cuda_startup_phase.serve`'s callbacks, so the rename lands in those three places and `serve`'s arity is unchanged. **Left out:** the fork's five other host-test files (`trainer_close`, `nemotron_trainer`, `dense_trainer_close`, `cuda_prompt_cancel`, `qwen35_cost_open`), which only exist in its diff because of that arity change.
- `cuda.zig` keeps our `and F.warm_spares` (the declared value decides); the fork tests `@hasDecl` alone.

**Tests taken:** the fork's `warmBesideFill(quiet)` rewrite, its batch-drop test, and its `warm_spares`/`otherLatest` test (two conversations on a store with room for one state).

**Gate:** `zig build test-lane-api-host` 553/553 pass, which is the suite carrying `lane_host_warm_test.zig`.

---

## 03-register-gpu-checks.patch

**Files** `zig/tests/cuda/glm_index_check.zig`, `glm_index_ovn_check.zig`, `glm_reply_prefill_check.zig`, **new** `glm_ovn_checks.zig`, `main.zig`. (Audit `LeftoverTests` G1, G3, D1.)

**Two defects found by compiling, not by reading:**
1. The eight declarations of `glm_index_check.zig` and `Inputs`/`inputs` of `glm_index_ovn_check.zig` are private, so the two ported index checks could never have compiled. `pub` taken from the fork, plus the fork's wording of the `page_bytes` comment.
2. **New finding, patch 0008:** `glm_reply_prefill_check.zig:80` calls `l.chunkOf(ids, at, false, from, cancel, marks, false, cap)`. The fork's `chunkOf` has a `slice: bool` for TF_GLM_OVN_FILL_SLICE_MS between `marks` and `cap`; ours (`cuda_follow.zig:241`) does not. Measured: `compile-cuda-tests` reported "member function expected 7 argument(s), found 8"; dropping the unported argument fixes it. The file had never compiled because nothing imported it.

**Deviation from the fork's shape, on your instruction:** the fork puts all three registrations in `main.zig` (595 -> 604 lines, over the 600-line lean rule). They go in a sibling `zig/tests/cuda/glm_ovn_checks.zig` holding the imports, a `usage` constant and `run(gpu, cmd, rest) !bool`; `main.zig` gains one import, `++ glm_ovn_checks.usage` on the line that closed its usage string, and one dispatch line, ending at **597**. Command names, usage wording and argument order are the fork's; the small `arg` helper is copied from `main.zig` because a sibling cannot import the root.

**Gate:** `zig build compile-cuda-tests` rc=0. These three are GPU checks: nothing runs them under `test-cuda-host`, which does not build the runner at all.

---

## 04-ring-past-refusal-test.patch

**File** `zig/glm_ring_host.zig` (audit G2). The fork's third test for that file, taken unchanged: a 64-row ring, restore at row 65 so the rebase lands on the pool at 64, then `error.PastRing` for a whole ring with `st.base == 64`, acceptance at a ring less one row, and the MTP side refused at a ring and accepted at a ring less a verify window. It is the only unit defence of patch 0042's refusal.

**Gate:** `zig build test-glm-ring-host` 3/3 pass (the file had 2 tests before). **This step is standalone and is NOT part of `test-cuda-host`**, so it will never appear in a gates.sh log and has to be run by name.

---

## 05-shared-window-width.patch

**File** `zig/tests/cuda/glm_lanes_tests.zig` (audit G5). The substitution only: `const W = glm.forward.window_rows;` with the two allocations and the three arrays sized by W instead of the literal 4.

**Left out:** `S = 8` and `sampled`, the `wide` rounds of 33 to 64 rows, every read of `e.settings.shared_rows` (all TF_GLM_OVN_SHARED_ROWS, unported; our shared window is a fixed 32 rows so a 40-row forward would not fit), the `x.prefill(ids, null, null)` arity (fork commit `1b4bd2975`), and the `check.pass` wording.

**Doubt, stated plainly:** this does **not** add coverage of 5 to 8 rows a stream. The per-stream count stays `1 + (round + i) % 4`, so the gap G5 names is only partly closed; what the patch removes is the overflow that would follow if anything raised it. Closing it properly needs SHARED_ROWS ported, and I did not invent a widening that our fixed 32-row window cannot run.

**Gate:** `compile-cuda-tests` rc=0. GPU only otherwise.

---

## 06-rows-worker-and-quiesce-drain.patch

**Files** `zig/src/core/rows_test.zig`, `zig/src/server/health_test.zig`, **new** `zig/src/server/health_quiesce_test.zig`, `zig/src/server/root.zig` (audit G7, G8).

`rows_test.zig`: the fork's hunks applied clean. `gridRoundTrip(sync, tag)`, the `rows.write.drain(r, nowNs() + 3 s)` drain, and the second case on the I/O worker, which is the writer GLM's store actually uses.

`health_test.zig`: the fork's `quiesce` change (the 5 second panic goes). **Deviation on your instruction:** the fork's test and helpers would take the file 558 -> 611, so they go in `health_quiesce_test.zig`, registered beside `health_test.zig` in `root.zig`'s test block; `health_test.zig` ends at **556**, its only other change being `pub` on the five declarations the new file reads (`Idle` with `engine`, `Bytes` with `text`, `WithGpu`, `key`, `quiesce`). Precedent for a test file reading another's fixtures: `lane_review_test.zig` and `lane_rounds_test.zig` already take `FakeLearner` and `LearnBox` from `lane_host_test.zig`.

**Gate:** `zig build test-rows-host` 127/127 pass. The quiesce test ran inside `test-cuda-host`: the server-module step went **1182 tests on the baseline to 1183 on my tree**, pass 1152 -> 1153, fails and skips unchanged.

---

## 07-snapshot-past-rings.patch

**Files** `zig/glm_snapshot_host.zig`, **new** `zig/glm_snapshot_paged_host.zig` (audit G11).

The fork's `past = f.seq.st.ring_rows + 4097`, the arena sized for it, and `past` appended to the case list. With our 4,096-row ring that adds keeps and restores at 8,193 with heads 8,192/8,193/8,200, which is the snapshot side of patch 0042.

**Deviation on your instruction:** the one line would make the file 601, so I took the fork's split. `pagedSeq`, `rowAt`, `same`, `expectSamePrefix` and the four paged tests move across **as our text, not the fork's** (our `State.initPaged` takes one argument fewer), the new file takes its own imports, and the existing test block gains one import line. 444 lines and 165 lines. Left out of the fork's version: its imports of `glm_one_chunk_host.zig` and `glm_lineage_host.zig` (unported knobs), `e.head = true`, and its TF_KV_SHARE adapter rewrite (ours already asserts the no-grid form).

**Gate:** `zig build test-glm-snapshots-host` 21/21 pass; that step is part of `test-cuda-host`.

---

## Gates table

| step | baseline `fix6` | lane `sampler-guards` |
|---|---|---|
| `check-native-cuda-host` | rc 0 | **rc 0** (7/7 steps) |
| `test-cuda-host` | rc 1, 26 failing names | **rc 1, the same 26 names** |
| `zig fmt --check zig/` | rc 0 | **rc 0** |
| `compile-cuda-tests` | not in gates.sh | **rc 0** |
| lean base vs head | 127 problems | **127 problems, 0 new** |

`scripts/gate-names.sh fix6 sampler-guards`: `only sampler-guards fails: none` / `only fix6 fails: none`, rc 0. The 26 are the baseline's file-permission, symlink and FIFO tests (`auth`, `auth_scope_http_test`, `auth_scope_test`, `benchmark_*`, `drama_voice_tool`, `request_log`, `slide_key`) that cannot pass on `/mnt/c`.

Honest note on the totals: my gates run reports 1322/1352 tests against the baseline's 5553/5606 because I had already run several of those steps by name in the same `--cache-dir`, so zig served them cached and did not re-count them. The name set is the contract and it matches; the per-step counts above (553, 127, 21, 3, 7, and the server step's 1182 -> 1183) are from runs that actually executed.

Lean: base `work/f5/tree` 5991 files / 127 problems, head 5994 files / 127 problems, `lean_new.py` 0 new, rc 0. Line counts after the restructuring: `main.zig` 597, `health_test.zig` 556, `glm_snapshot_host.zig` 444; new files `glm_ovn_checks.zig` 37, `health_quiesce_test.zig` 64, `glm_snapshot_paged_host.zig` 165. One intermediate lean run caught a two-line `//!` doc in the new paged file as a "multi-line comment" problem; it is one line now.

**Verify tree:** `work/ports/sampler-guards-verify` rebuilt from the pin + 0001..0042, all seven patches applied in order with `git apply`, `diff -rq --exclude=.git` against the cut tree: **0 differing paths**. (Re-run after the last two comment edits and the re-cut.)

---

## Doubts, in order of how much they matter

1. **Patch 05 is a partial gate close.** The audit calls G5 "the shared-window check never covers 5 to 8 rows a stream"; the substitution does not change which rows are exercised. If you want the gap actually closed, it needs TF_GLM_OVN_SHARED_ROWS ported first. I would not park the patch, but do not count it as coverage.
2. **Patch 02 changes four other families' admission behaviour**, which is the fork's intent but is the only part of this lane that touches a non-GLM production path. It is defended by the fork's own three tests, all passing on the host; nothing here has seen a serve.
3. **Patch 01's `Sampler.copy` is now dead** in both trees. Kept for fidelity; say the word and it goes.
4. **`glm_reply_prefill_check.zig` has still never run.** Patch 03 only makes it compile. Its first real result will be a GPU run, and that is also the first live evidence for patch 02's guard.
5. `test-glm-ring-host` and `test-glm-logprobs-host` are **standalone steps**: neither is reachable from `test-cuda-host`, so a future gates.sh run will not notice if patch 01 or 04 regresses. Wiring them into the gate is a change I did not make because it edits the build files.

## What each patch needs from a GPU run

- **01** - a TP=3 `prompt_logprobs` request over 128 tokens answering at all (the hang), and its logprob words equal to TP=1 for the same prompt. A structured or sampled decode digest on three ranks checks that `place` and the broadcast layout agree bit for bit.
- **02** - with `TF_GLM_OVN_REPLY_PREFILL=1`, two conversations and a cache budget holding about two states: B's reply pass must leave A's kept state (evicted counter flat, A's `at` unchanged) and A's next turn must still report a prefix hit; separately, a reply pass sent while another prompt fills must end cancelled with no chunk run.
- **03** - `glm-index-ovn-check`, `glm-index-regroup-check` and `glm-reply-prefill-check` each passing on a Spark.
- **04, 06, 07** - nothing; host tests over fake drivers and sockets.
- **05** - `glm-shared-check` passing unchanged on three ranks (it compares the same rows, so any difference means the substitution itself is wrong).