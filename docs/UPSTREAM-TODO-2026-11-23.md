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
