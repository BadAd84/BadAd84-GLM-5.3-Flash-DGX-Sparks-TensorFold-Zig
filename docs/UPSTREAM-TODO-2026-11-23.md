# Upstream TODO, compiled 2026-11-23 (read-only; nothing started)

Upstream is `ashhart/TensorFold` at `refs/remotes/up/main` = `281d81b8b` (changelog for #4457). Our pin is
`fa13df5dd`, and **826 commits have landed since it, 50 of them in `zig/src/families/glm`,
`zig/kernels/cuda` or `zig/src/cuda`**.

## 1. BLOCKING: the maintainer answered our issue and we missed it

`#4247` ("GLM-5.3-Flash on CUDA at TP=3: default-off, bit-exact levers we would like to send 1 at a time. Which first,
and is this the gate?") was answered by Synthena on 2026-11-22 09:50. Nobody acted on it. What it says, in full effect:

- **Order confirmed: `TF_GLM_KEEP_SEQS` first, `TF_GLM_NO_COPY` second.**
- **The KEEP_SEQS pull request must show three things:** the startup memory line unchanged; what a kept sequence holds while
  idle; and a test that a **reused sequence equals a fresh one when the new prompt is shorter than the last**, with a planted
  control. Context he gave for that: on main, `Engine.release` (`cuda_engine.zig:327`) frees every unpaged slot except slot 0,
  so slots 1 to 3 build a fresh sequence per request.
- **NO_COPY is measured on its own** (the +11% we banked had two matmul levers beside it), and **checked against `#3333`**
  (`TF_GLM_COPY_SHARE`, OPEN upstream), which changes copies in the same shared rounds.
- **The gate is ours plus one thing:** with the setting on, **greedy token hashes and seeded sampled tokens must equal
  main's**, not only drafted equal to plain, resumed equal to fresh, concurrent equal to solo. **Alternate A-B-B-A with a
  fresh server for each arm**, as `docs/optimizing.md` asks.
- **Issue policy: `#4247` is enough.** Link it from each pull request; open another only for a lever that needs its own
  decision.
- **If a lever keeps tokens and costs nothing when unused, say in its PR whether it could be the default instead of a
  setting** (he names skipping the MTP head's prompt passes under DFlash2 as a possible example).

Neither `TF_GLM_KEEP_SEQS` nor `TF_GLM_NO_COPY` exists in main's table, so both are novel and the issue is the right
home for them.

## 2. Retirement candidates: upstream now does what our patches do

Per the repo rule, an upstream equivalent is a retirement CANDIDATE, never an incumbent: each needs its test before the
patch leaves the series.

| upstream commit | what it says | our patch it may absorb |
|---|---|---|
| `ff64ef9d9` | `GLM CUDA: skip sparse-overwritten dense rows`, touching `cuda_dsa_block.zig` and adding a `cuda_latent_test` case | **our dense-window clip** (`7d1286a`, patch `0025`'s `denseRows`) |
| `37db5c593` | `GLM CUDA: skip unread prefill projections`, `cuda_dsa_block.zig` + `cuda_forward.zig` + `cuda_engine.zig` | possibly `0019`/`0020`'s speculative next tile |
| `20cb27d32` | `glm/cuda: follow main's dependent-launch prologue for combine_tail (#3776)` | adjacent to `0024`'s dependent-launch work |

## 3. New upstream levers worth measuring on our serve

| commit / PR | lever | why it matters here |
|---|---|---|
| `0b06e1ede` (#3659, MERGED) | `TF_GLM_MOE_DIRECT=1` runs a decode window's EXL3 MoE **without its row copies and put_slots** | the decode MoE is 46% of a four-client window (`nc1`), and the expert-skew item is about exactly those rows |
| `#3776` (MERGED) | decode kernels as dependent launches, +3.7% | our `0024` PDL work sits in the same place; check for double-work or a merge |
| `61d4a487a` | opt into local indexer rows through 32K | our indexer path (`0007`, `0012`) |
| `5b0b7d33f`, `1bc6c1556`, `1e5014c8d`, `fa6fa4fef`, `71fdfb22f` | paired expert joins, own-partial in place, split shared/combine | our `0038` piece-front area |
| tag `v1.3.3` | release | analysed earlier: its GLM CUDA decode headline is already in our pin; only the 3-bit prompt kernels genuinely postdate it and they need a re-quantised checkpoint |

## 4. Re-seat scope, measured rather than assumed

Our 32 engine patches touch **148 files**. Upstream commits since the pin per file, worst first:

| file | commits |
|---|---|
| `docs/environment.md` | 34 |
| `zig/src/platform/environment.zig` | 28 |
| `zig/src/platform/environment_test.zig` | 19 |
| `zig/src/server/root.zig` | 18 |
| `zig/build/cuda.zig` | 15 |
| `zig/tests/cuda/main.zig`, `zig/src/server/server.zig` | 12 each |
| `zig/src/core/lanes/lanes.zig` | 10 |
| `zig/src/families/glm/cuda_state.zig`, `cuda_forward.zig` | 6 each |

So the churn is concentrated in the registry, build and server plumbing our patches add rows and steps to (mechanical but
wide), with only four to six commits in the GLM kernel files themselves. `scripts/reseat-survey.sh` gives the per-patch
verdict before any re-seat work, and the earlier measurement on `v1.3.3` was 9 of 32 applying clean.

## 5. Nothing else in our workstream

Our other open pull requests upstream are not this workstream: `#4449`, `#4075`, `#3523`, `#3218` are Flash Next, `#3592` is
DSV4.1, `#4183` is the int4 GPTQ kernel. `#3333` (COPY_SHARE) is open and matters only because the maintainer wants
NO_COPY measured against it.

## 6. State of the two the maintainer asked for

**`TF_GLM_KEEP_SEQS` is open as https://github.com/ashhart/TensorFold/pull/4809** at `46a681fdc`, against
`0b39f4d64`, with the Unreleased line naming it (`pr_check --pr 4809`: 0 errors, 0 warnings). CI has created no run for
its head while fresh runs appear for other pull requests at the same minute, which is GitHub's first-time-contributor
gate: a maintainer approves the workflows on the pull request before they start. Nothing on our side can start them.

**`TF_GLM_KEEP_SEQS`** (branch `keep-seqs`, head `ed007da20`, 8 commits, 10 files, +367/-4). The lever is a row of
`platform/environment.zig`, a field of `ranks.Settings` read once and passed in the engine's options, a field of
`Engine` that `release` consults, a `Fingerprint` field with the layout at 24 (and its enum, mismatch walk, explain
and divergence test), a host test of four cases, and the GPU check registered in `zig/tests/cuda/main.zig`. Gates:
`tools/pr_check.py` 0 errors and its one warning is the changelog line, which needs the number; lean 165 problems on
both sides with 7,697 and 7,699 files, 0 new; `compile-cuda-tests` rc 0; `test-glm-keep-seqs-host` 4 of 4; the eight
GLM host steps pass; `zig build test test-golden` fails the same 27 test binaries as the pristine base on a host whose
GPU cannot run these kernels; `zig fmt --check` and `git diff --check` clean. Receipt on one GB10 with
`TF_GLM_LAYERS=2` (the snapshot is 163.6 GiB): `PASS kept sequences, as left and with every byte poisoned, equal
fresh ones: 24 greedy steps' tokens, bf16 logits rows and MTP drafts after prompts of { 600, 3000 } tokens, fp8 and
bf16 caches`, with four planted controls firing, and with the switch unset the same command stops at
`needs TF_GLM_KEEP_SEQS=1`. The logs are in spark1 `~/bench/receipts/`.

**`TF_GLM_NO_COPY`: measured twice, null both times, rejected by the owner and dropped (2026-11-23).** It was carried
to the same base with the same plumbing (settings row, engine field from the options, fingerprint at 24, tests off the
registry fake, lean at 0 new) as branch `no-copy`, and the branch is deleted from the fork. Upstream `main` against it
at the five levels, tuning stripped: 52.7/60.5/81.5/109.1/133.5 against 52.3/60.1/80.8/109.1/134.2 tok/s, acceptance
identical, token digests equal. A prompt built to repeat its own head, the same image both ways: acceptance 0.664
against 0.664, 54.0 against 54.4 ms a round, 102 rounds each. `windows.zig` takes its `Copy` from the stream's own
context or Recall's record and neither workload gives the server one, so the switch had nothing to act on; upstream's
rule wants a measured benefit, so nothing was posted.

## 7. The retirement candidates, mapped to our patches

All three postdate our pin `fa13df5dd`, so each is a test, not a fact:

| upstream commit | what it does | our patches on the same files |
|---|---|---|
| `20cb27d32` | `glm_glue_rows.cuh`: follow main's dependent-launch prologue for `combine_tail` | `0024-glue-fuse` - the same file |
| `ff64ef9d9` | `cuda_dsa_block.zig`: skip sparse-overwritten dense rows (+ a latent test, a build step) | `0019-sparse-onepass`, `0020-onepass-pipe`, `0023-mla-knobs`, `0025-head-block-rule`, `0038-glm-piece-front` |
| `37db5c593` | `cuda_dsa_block.zig`, `cuda.zig`, `cuda_engine.zig`, `glm_prompt_host.zig`: skip unread prefill projections | as above |

The test is the standing one: re-seat onto the base that carries the upstream commit, remove our patch, run the gates
and the five levels, and retire only if the behaviour and the numbers hold without it. `20cb27d32` is the cheapest test
because it touches one file and one patch; the sparse pair is a family of five patches and needs a prefix build.

## 8. The series against current upstream (`ea37382cb`): 8 clean, 24 partial, none absorbed

`scripts/reseat-survey.sh ea37382cb work/reseat2 patches/engine` over all 32 patches, text only:

| verdict | patches | meaning |
|---|---|---|
| clean | 8 (`0001`, `0004`, `0009`, `0014`, `0021`, `0028`, `0029`, `0035`) | apply whole on the new base unchanged |
| partial | 24 | some hunks apply, the rest reject; each needs a re-seat |
| absorbed | 0 | **not one patch's lines are already in upstream** |
| refused | 0 | none is obsolete in the sense of "files gone" |

So the answer to "why 32 local patches" is not that upstream declined them: only one has ever been offered
(`#4809`), and none is absorbed, so every one is still ours to submit. The eight clean ones can go up as they are;
each partial one is a re-seat, and per the owner's rule of 2026-11-24 the default is to submit rather than keep local,
reworking a lever into an acceptable shape while the trade is small.

## 9. The re-seat itself: a three-way merge, 22 API conflicts, not 114 text hunks

Applying the series with `git apply --3way` (the patch blobs are reachable from the parity clone) collapses the survey's
114 rejected hunks to **27 conflict blocks in 18 files**; ten patches merge clean and the rest leave markers. Five blocks
were "ours empty, theirs adds" and are resolved by taking theirs (`docs/environment.md`, `platform/environment.zig`,
`tests/cuda/glm_ovn_checks.zig`). The remaining 22 are real merges in fifteen files, concentrated in
`cuda_latent.zig` (4), `prompt_cache.zig` (3), `cuda_glue.zig` (2), `cuda_forward.zig` (2):

| file | blocks |
|---|---|
| `zig/src/families/glm/cuda_latent.zig` | 4 |
| `zig/src/core/prompt_cache.zig` | 3 |
| `zig/src/families/glm/cuda_glue.zig`, `cuda_forward.zig` | 2 each |
| `prompt_cache_fork.zig`, `prompt_cache_index.zig`, `prompt_cache_keep.zig`, `cuda.zig`, `cuda_dsa_block.zig`, `cuda_env_test.zig`, `cuda_prompt_pair.zig`, `cuda_prompts.zig`, `cuda_state.zig`, `cuda/kernels.zig`, `test_support/glm_snap_fixture.zig` | 1 each |

They are API merges, not text drift: upstream changed `absorbQ` to take E4M3 `sk` scales and `rowBlocks`/`chunks` to take
a pointer tuple, while our patches add the roped (YaRN) branch and the fuse/skip path into the same functions. Each needs
the two APIs reconciled and the call sites updated, and each is also the moment to decide **port or retire**: where
upstream's new body already does what our hunk did (`20cb27d32` against `0024` is the clearest), the patch is retired
instead of merged.

## 10. The re-seat lands: compiles, passes the GLM host suite, fmt clean

On `ea37382cb` with all 32 patches applied and the 27 conflicts resolved (branch `reseat-ea37382cb` in the parity clone):

- `zig build check-native-cuda-host`: rc 0.
- `zig build test-glm-rev25-host`: rc 0, 31 tests (30 pass, then the env-test row fix made it 31).
- `zig fmt --check build.zig zig`: rc 0.

What the cycles taught, each of which cost a rebuild:

- **`Mla` and `compactKv` are upstream's own definitions.** A resolution that takes "theirs" (our patch's side of a
  three-way apply) can delete a type or function upstream added earlier; check the base file before replacing a block.
- **Never merge the settings table hunk by hunk.** Row insertions from different patches land in the same region and are
  silently dropped: 25 of the 36 rows our patches add had vanished. Rebuild it by union, the base's rows plus every row
  our patches add that the file lacks, and verify the count afterwards.
- **Our new fields belong where the code reads them**: `roped` and `onepass_pipe` live on `Modules` (because `set()`
  reads `f.m`), and `roped` is a value whose address the `Set` takes, since `Mla.load` returns a value.
- **Three call sites follow the new APIs**: `longestShared` takes the salt, `width` is `sparse.width`, `onepass_pipe` is
  already a `Function`.
- **The env test's lists are part of the re-seat**: a row our patches add must be named in one of its lists or the count
  assertion fails (`TF_GLM_INDEX_DECODE_FROM` was the one).

## 11. The re-seat compiles and runs; two tests still fail, both understood

Status after the argument and guard fixes: 1,274 of 1,277 pass. The four that were fixed were call-site
consequences of the merged `absorbQ` signature (eleven arguments, `rd` before `lw`, `sk` carrying the scales
pointer) and of `sparseAttentionFormat` needing `headBlockFor(rows, lw)` for the 576-wide roped row rather than
upstream's `headBlock(rows)`; the drafter window came back with patch 0038's hunk.

The fuse failure's cause was the sparse attention path: our version takes the caller's head block, upstream's computes
its own, and the merge kept upstream's, so a call that asks for 32-head tiles silently got 16. Restoring the parameter
(production callers pass `headBlockFor(rows, lw)`, byte-identical to what upstream computes for a 512-wide row) brought
the suite to 1,286 of 1,288.

The one that remained:
- **`TF_GLM_OVN_MLA_FUSEMERGE: 32-head launches`** expects `chunks_32_fp8_skip, merge, chunks_32_fp8_skip, merge`
  and gets `54, 49, 53, 49`: the second chunk of one attention call launches the non-fp8 `chunks_32_skip` instead of
  the fp8 form, so the scales pointer does not reach that launch. The merge left `sparseAttentionFormat` with two
  `fuses(...)` early returns (`cuda_latent.zig:135` and `:201`, each passing a different pair of `tokens`/`counts`
  zeros) where one side had one; reconciling those two paths is the work, and the fused launch reads `scales` at its
  own call site (`:179`).
- **`GLM disk ranks: a blank state takes bytes past its words and front only once sealed`** now runs through the prompt
  steps (the wide step stops at the next start instead of refusing, and our own prompt-cuts test follows that) and dies
  at `cuda_snapshots.zig:99` in `seal`: `n > s.lease.ids.items.len * pages.page`. That guard is upstream's, identical at
  its tip, so the divergence is the size the seal recomputes from `s.shared` exceeding the lease `keepAs` took from
  `plan.len` on the same kept state - an input difference between the two calls, not a guard to relax. Relaxing it was
  tried and moved the failure to the `n >` clause on the next boot, which is why the guard is restored byte-identical.
  The lead: the test seals with `at - 1` as the MTP length (`cuda_disk_ranks_test.zig:183`), so `Plan.size` at the seal
  adds 2,047 MTP rows to a lease that `blankAs` took with none - and `blank`/`blankAs` are upstream's own, so the lease
  sizing or a `Plan.size` input is what one of our patches changes. That is where the next pass starts.
  Found: `planBytes` (ours, from patch 0026) took the head's rows as none while the head flag is off, so `blankAs` leased
  10 pages for a state at 2048 where the seal, which includes the MTP rows regardless of the flag, needs 11 (measured:
  `n=22614272 lease=20971520 pos=2048 mtp_len=2047 shared=0 cap=6144 mtp=true pages=2097152`). A blank lease is the most
  a state at that position can need, so it now includes the head rows as upstream's does.

## 11b. The older notes

**The pristine base is green**: `zig build test-cuda-host` on `ea37382cb` alone returns 0 with no failing test, so every
failure below is OURS - introduced by the patches or by the merge - and none of them is inherited from upstream.

`zig build test-cuda-host` on the re-seated tree: 482/484 steps, **1270 of 1277 tests pass, 6 fail**, 1 skipped. The
build is clean; the failures are behaviour.

**Four are our own MLA tests** asserting exact launch records (`absorb_q_192`, the 16-head roped tiles, the fuse_rows
split, the E4M3 forms): the merged `absorbQ`/`rowBlocks`/`chunks` signatures moved where the arguments come from, so the
recorded grids and argument tuples no longer match. Each has to be re-derived from the merged implementation, not edited
to fit it.

**Two are upstream's own tests that our patches break**, which is the serious class:

| test | what happens |
|---|---|
| `cuda_disk_ranks_test`: a blank state takes bytes past its words and front only once sealed | our guard in `cuda_prompt_cuts.zig:56` returns `error.BadChunk` ("a solo pass would step over a request start") on a pass upstream's test performs |
| `dflash`: the drafter's window bounds its context from below | `windowFrom(90, WIN + 100)` returns 100 where upstream expects 90, so one of our window levers changed the resumed-stream rule |

So "current" is not yet true in the full sense: the tree builds and runs, and six tests stand between it and the base's
own green. The two upstream ones are regressions our patches introduce on the new code and are fixed first.

## 12. The full-checkpoint receipt the maintainer asked for

`gpu-check-tp3-keep-seqs.sh prkeep-full glm-keep-seqs-check` with `TF_GLM_KEEP_SEQS=1`, on the complete checkpoint at
TP=3 (spark1-3, 2026-11-24): **rc 0 0 0 (ranks 0, 1, 2) in 266 s**, rank 0 reporting 1 PASS and 0 FAIL.

```
RESULT control kv8=false, 600-token prompt: differs from the fresh run at step 0, as planted
RESULT control kv8=false, 3000-token prompt: differs from the fresh run at step 0, as planted
RESULT control kv8=true, 600-token prompt: differs from the fresh run at step 0, as planted
RESULT control kv8=true, 3000-token prompt: differs from the fresh run at step 0, as planted
PASS kept sequences, as left and with every byte poisoned, equal fresh ones: 24 greedy steps' tokens,
bf16 logits rows and MTP drafts after prompts of { 600, 3000 } tokens, fp8 and bf16 caches
```

So the comparison holds on the whole model rather than the two-layer probe: every layer kind and the MTP head are in it,
across all three ranks. What remains of his ask is the prompt-cache resume that lands on a kept slot, and the driver had
to be fixed twice to get here (the binary lives at `/usr/local/bin` in the check image, and `XENV` is its fourth
positional argument, not an environment variable).

## 13. The host suite is green (and what that does not cover)

A full clean rebuild of the host suite on the gate host returns 0: `zig build test-cuda-host` with the cache removed
ran 364 s and every test passed, against the same invocation on the pristine base at `ea37382cb` which also returns 0.
The seven failures the merge produced are closed, each by a real cause rather than an expectation moved:
the eleven-argument `absorbQ`, the sparse path's caller-supplied head block, `headBlockFor` for the roped row, the
drafter window from patch 0038, the wide prompt step stopping at the next request start, and the blank lease including
the head rows.

**Scope warning, added after the image build:** `test-cuda-host` compiles none of the CUDA kernel surface, so this green
result does not cover it. Sections 14 to 16 record what that hid: 27 missing new files, and 70 added declarations absent
across twelve patches. The re-seat is green on the host suite and NOT complete.

## 14. The apply had silently lost 27 of the series' 47 new files

`test-cuda-host` cannot see this: the `.cu` and `.cuh` kernels, the onepass pipe, the glue and two tests compile only in
the image build (and in `compile-cuda-tests`), so a tree that passes the host suite can still be missing them. It was the
image build that said so, one file at a time:

```
zig/tests/cuda/glm_index_ovn_check.zig:1:1: error: unable to load "glm_index_ovn_check.zig": FileNotFound
```

Auditing every `new file mode` in `patches/engine/` against the tree found 27 absent, including
`zig/kernels/cuda/glm_index_sched.cuh`, `glm_index_split.cuh`, `glm_onepass_pipe.cu`, `glm_l2fp.cu` and
`cuda_onepass_order_test.zig`. All 27 were reconstructed from the series in patch order (`git apply --include=<file>` for
each patch that carries it, 28 applies, 0 failures) and the tree now holds 47 of 47.

The lesson for the next re-seat: after the three-way merge, audit `new file mode` against the tree before anything else,
then run `compile-cuda-tests`, which is the gate that actually compiles them.

## 15. Patch 0012 is only partly in the tree

With the 47 files restored, `compile-cuda-tests` (the gate the host suite does not run) exposes that the index-split
feature itself is missing from `zig/src/families/glm/cuda_index.zig`: the `split_rows` and `split_fn` fields, the `sr`
the load computes, and the `decodeSelect` and `splits` methods are all absent, while the check file and the kernels that
use them are present. Its hunks were rejected in the three-way merge and the rejection was not noticed because nothing
in `test-cuda-host` compiles that file's new surface.

The port is not a mechanical re-apply: the patch no longer applies to `cuda_index.zig` (context drift at line 60), and
upstream renamed `Mode.all` to `Mode.both`, so the hunks need re-reading against the current struct before they go in.
That is the next piece of work on this series, and `compile-cuda-tests` is the gate that says when it is done.

## 16. The re-seat needs a per-patch symbol audit, not a file audit

Fixing 0012's surface (the split fields, `selectSplit`, the exported types in `glm_index_check.zig`, the two
`selectTokens` geometries) moved `compile-cuda-tests` on to the next one: `cuda_onepass` has no member `PipeKernels`, so
patch 0020 is partly missing too. The pattern is the same in both: hunks that ADDED declarations were rejected in the
three-way merge, while the files that use them arrived whole, and nothing in `test-cuda-host` compiles that surface.

So the audit is per patch and per declaration: for every patch, take the declarations it adds (`pub fn`, `pub const`,
struct fields) and check each exists in the tree, then run `compile-cuda-tests`. Recovering files by name (the 47-file
check) is necessary but not sufficient.

State at this point: 47 of 47 files present, 0012's index surface ported, three `sparseAttentionFormat` callers given the
head block; `compile-cuda-tests` still fails, now inside patch 0020's onepass pipe.

## 17. The declaration audit's two flaws, both measured

The audit that produced the 70-row list searched for `pub fn`/`pub const` only, so a declaration that exists WITHOUT
`pub` counted as missing: the tokenizer's eight were all present that way, and porting them duplicated members the gate
rejected in one round. Widening the pattern to any visibility then over-counted in the other direction (170 rows, because
it also matches declarations the patches merely mention in context lines).

What is reliable is the gate, not the audit: `compile-cuda-tests` plus the image build name a genuinely missing
declaration and its use site, and the pre-merge tree supplies the definition. The port proceeds file by file with the
gate behind each, and the audit is at most a coarse map.

## 18. A new kernel needs its build registration, not just its source

With the onepass pipe ported, the image build failed on `zig/src/cuda/kernels.zig:8: failed opening
"fatbin_glm_onepass_pipe": FileNotFound`. Patch 0020 also adds the fatbin's entry to
`zig/build/cuda_kernels.zig` (`.{ .name = "glm_onepass_pipe", .flags = &.{"-O3"} }`), and that hunk was rejected with the
rest. A declaration that embeds a blob is therefore two pieces: the const, and the build step that produces the blob, and
only the image build checks the second.

## 19. The four packages that would not stack, surveyed on the re-seated base

`git apply --check` of every patch in each package against the tree at `ea37382cb`:

| package | applies |
|---|---|
| port-multi-fill | 0 of 1 |
| restore-held | 0 of 1 |
| solo-cuts | 0 of 1 |
| pr1411 | 0 of 2 |

So the port is a hand rebase of each package's hunks, not an application, and `scripts/dev-packages.list` already says why:
every package edits `environment.zig`, `cuda.zig` and `cuda_follow.zig`, and each was cut against the state the ones
before it left. The order in that file is priority, not applicability.

The rung order to port in, lightest first, is the list's own: pr1411, cache-salt, learn-starts, solo-cuts,
disk-any-position, restore-held, port-multi-fill.
