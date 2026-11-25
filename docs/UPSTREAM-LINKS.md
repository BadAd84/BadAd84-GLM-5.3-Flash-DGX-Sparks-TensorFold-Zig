# Patch to upstream link

`main` accumulates every lever as a numbered patch under `patches/engine/`; that is the branch that becomes production.
A lever is ALSO cut as a branch from upstream `main` when we open it there, because upstream cannot take a patch series -
they take one behaviour a pull request. The branch is transport, not a second source of truth: it is cut from upstream's
tree, never merged back into this one, and the two are tied together by this table.

When upstream lands a lever, the PATCH is retired here (deleted from the series, with the upstream commit recorded), so
this repo's main and upstream's main converge on the same behaviour from opposite directions.

Every patch needs a row. `-` in the pull-request column means it has not been opened upstream yet; the state column says
whether it is planned, blocked (with why) or not upstreamable (with why).

| patch | subject | pull request | branch | state | retirement |
|---|---|---|---|---|---|
| `0001` | [PATCH] glm tests: the shared-window check sizes its rows from the eng | - | - | not opened | - |

| `0002` | [PATCH] core and server: the disk grid on the I/O worker, and a quiesc | - | - | not opened | - |
| `0003` | [PATCH] host: the prompt-bench step, so request preparation can be tim | - | - | not opened | - |
| `0004` | [PATCH] core: the TF_GLM_OVN knob registry | - | - | not opened | - |
| `0005` | [PATCH] glm: TF_GLM_KDA_PAD pads the KDA input stack at one width | - | - | not opened | - |
| `0006` | [PATCH] glm: the DFlash2 draft knobs (TF_GLM_OVN_DRAFT_*) | - | - | not opened | - |
| `0007` | [PATCH] glm cuda: the index kernels take decode windows (TF_GLM_INDEX_ | - | - | not opened | - |
| `0008` | [PATCH] core: kept-state walks gated by the last id (TF_GLM_OVN_KEPT_W | - | - | not opened | - |
| `0009` | [PATCH] glm cuda: a pass the rebased index ring cannot hold is refused | - | - | not opened | - |
| `0010` | [PATCH] glm checks: the OVN check commands in their own table beside m | - | - | not opened | - |
| `0012` | [PATCH] glm cuda: TF_GLM_OVN_DECODE_INDEX, _INDEX_SCHED, _POOLS32 | - | - | not opened | - |
| `0014` | [PATCH] glm lanes: the stepped prompt pass in its own file beside cuda | - | - | not opened | - |
| `0019` | [PATCH] glm cuda: TF_GLM_OVN_SPARSE_ONEPASS, production's prompt spars | - | - | not opened | - |
| `0020` | [PATCH] glm: TF_GLM_OVN_ONEPASS_PIPE, the one-pass pipeline with bit-e | - | - | not opened | - |
| `0021` | [PATCH] glm cuda: TF_GLM_OVN_KDA_CHUNKED, production's chunked KDA pro | - | - | not opened | - |
| `0022` | [PATCH] glm cuda: TF_GLM_OVN_MM_WIDE, _SWIGLU_REDUCE, _MM_CLUSTER, _MM | - | - | not opened | - |
| `0023` | [PATCH] glm cuda: TF_GLM_OVN_MLA_FUSEMERGE, _ABSORB_VEC, _KVB8 | - | - | not opened | - |
| `0024` | [PATCH] glm cuda: TF_GLM_OVN_GLUE_FUSE, _GLUE_ROW, _PDL_EARLY | - | - | not opened | - |
| `0025` | [PATCH] glm latent: the head block takes the head count back (test-cud | - | - | not opened | - |
| `0026` | [PATCH] glm cuda: the MTP head's own passes run only without a DFlash2 | - | - | not opened | - |
| `0027` | [PATCH] exl3: TF_EXL3_DEC_ORDER launches each k slice's blocks before  | - | - | not opened | - |
| `0028` | [PATCH] host: byte equality by indexOfDiff, and a string index that st | - | - | not opened | - |
| `0029` | [PATCH] glm cuda: FP8 latent keys fetched a tile ahead, in 8-byte load | - | - | not opened | - |
| `0030` | [PATCH] server: render and tokenize a request once, and TF_GLM_OVN_HOS | - | - | not opened | - |
| `0031` | [PATCH] glm exl3: TF_GLM_OVN_X3_NC, X3_XROW and X3_FUSEDOWN, productio | - | - | not opened | - |
| `0032` | [PATCH] glm cuda: TF_GLM_OVN_KEEP_SEQS, a released stream's sequence s | `#4809` | `keep-seqs` | MERGED as `TF_GLM_KEEP_SEQS`, upstream `ea38fdcf8` | RETIRED: upstream absorbed it; the test's two fixes are `#5122` |
| `0033` | [PATCH] server: TF_GLM_OVN_OFF_EFFORT_LINE, a thinking-off GLM-5.3 pro | - | - | not opened | - |
| `0034` | [PATCH] glm lanes: TF_GLM_OVN_NO_COPY, a DFlash2 drafter's windows wit | - | - | not opened | - |
| `0035` | [PATCH] glm cuda tests: glm-mm-ovn, the matmul launch variants against | - | - | not opened | - |
| `0036` | [PATCH] glm latent: TF_GLM_OVN_LATENT_ROWS, absorb_q and expand_v two  | - | - | not opened | - |
| `0037` | [PATCH] glm cuda: TF_GLM_OVN_SIDE_PRIO, the prompt exchanges' side str | - | - | not opened | - |
| `0038` | [PATCH] glm cuda: TF_GLM_OVN_PIECE_FRONT, _MLA and _FFN, the next bloc | - | - | not opened | - |

## #4809 on 2026-11-24: base merged, CI running

The pull request had gone `CONFLICTING` as main advanced (a conflicting pull request runs no checks at all), so main was
merged into `keep-seqs` twice: `9edf2f89d45b` first, then `0d8cbb26f` once upstream moved again inside the hour. Both
conflicts were the changelog alone, resolved as upstream's file plus our one bullet.

- Merge commits `35600b2b2` and `436ef4b5c`, gated on the gate host at the first: `zig fmt --check` rc 0 and
  `zig build test-glm-rev25-host` rc 0.
- With the conflict gone the checks run again: `fmt`, `zig`, `pytest`, `benchmark-clients` on both runners and the rest
  were queued at 2026-11-24.

## #4809's checks after the merges (2026-11-24)

Nine of the ten ran and passed. One fails: `benchmark-clients (ubuntu-latest)`, job "No GPU", in
`tools/tests/test_bench_prose.py::test_serialized_streams_measure_shared_interval`, asserting `draft_arm["overlapped"]` is
false when it came back true. Evidence that it is not ours: the branch touches only
`zig/src/families/glm/cuda_env_test.zig`, `zig/src/platform/environment.zig` and their test, and the failing test lives in
`tools/`, which the branch does not modify; its windows counterpart passes on the same head.

Not claimed: that it fails on upstream main. Main's runs of that workflow are being cancelled repeatedly, so its history
cannot settle it, and the honest statement is the one above rather than a guess.

## #4809's last ask: a prompt-cache resume onto a kept slot (2026-11-25)

The maintainer accepted both fixes and asked for one receipt with its exact head, checkpoint revision and launch settings.
The check that exists is `glm-keep-seqs-check CKPT ID_PATH`, which compares a kept sequence against a fresh one; it does
NOT exercise a prompt-cache RESUME onto a kept slot, so the ask is a new case rather than a run of the existing one.

What the case has to show: a request whose prompt reuses a state a released slot kept, resumed rather than recomputed,
with the same tokens a fresh run gives, and the settings, head and checkpoint revision named. That is a GPU case on
spark1-3, so it is queued behind the running screen rather than beside it.

Design, from reading the existing check (`zig/tests/cuda/glm_keep_seqs_tests.zig`):

- its `Run.request` already drives bind, begin, prefill and the draft loop, and its `Trace` already records each step's
  token, bf16 logits row and MTP drafts;
- the new case adds the middle three steps around that: run a prompt on slot `s` and record it; release `s` and confirm
  the sequence is kept (`e.keepsSequence(s)`); then run a prompt that RESUME from what `s` kept, and compare its `Trace`
  against a fresh run of the same ids on a clean slot, on tokens, logits rows and drafts;
- the planted control is the same shape the existing check uses: poison the kept arena and confirm the comparison fails,
  so a passing case cannot pass vacuously;
- the receipt names the image tag, the head sha, the checkpoint revision and the launch settings, which is what the
  maintainer asked for.

## The resume case is on the branch (2026-11-25)

`keep-seqs` is at `2ca51d7de`, one file, 78 insertions: `zig/tests/cuda/glm_keep_seqs_tests.zig` gains a resume case that
keeps a prompt state at 2,048, resumes onto that kept slot, compares it against a fresh run on tokens, bf16 logits rows
and MTP drafts, and plants a control that poisons every prompt-cache byte and must make the comparison fail.

Host-side checks on the gate host: `zig fmt --check` clean, `zig build compile-cuda-tests` exit 0 (the runner with the new
case), `test-glm-keep-seqs-host` exit 0. The GPU check itself needs an image, and the receipt for a pull request is taken
from its own head, so `glm53-zig:prkeep2` is building from `2ca51d7de` rather than from the adjacent tree.

The receipt the maintainer asked for needs, beside the run: the head sha (`2ca51d7de`), the checkpoint revision, and the
launch settings (image tag, `TF_GLM_KEEP_SEQS=1`, the rank and world the check runs with).

## The resume case's first run failed on its own callback (2026-11-25)

`glm-keep-seqs-check` on `2ca51d7de` printed the two earlier planted controls and then
`FAIL glm-keep-seqs-check: StateKept` on ranks 1 and 2, at 03:31. The cause is in the case, not in the engine: the mark
callback that keeps the prompt state ran twice for one request, and the second `keepState` collides with the first
because an id is already taken. Fixed by making the callback spend itself (`022992f21`), with a comment saying why.

The rebuilt head `022992f21` is in `glm53-zig:prkeep3` and the check reruns against it. Lesson worth keeping: a new case
in a GPU check produces failures of its own, and they look like engine failures in the log until the callback is read.

## Where the resume receipt stands (2026-11-25, unattended)

`keep-seqs` is at `022992f21` on the fork with the resume case and its `StateKept` fix. `glm53-zig:prkeep3` is the image
built from that head and it ran the check twice:

- first run: the two earlier planted controls printed, then `FAIL glm-keep-seqs-check: StateKept` on ranks 1 and 2, which
  was the case's own save callback firing twice. Fixed and committed.
- second run, against the fixed image: the two controls printed and then the check sat at that point for thirty-five
  minutes with its container alive, which is a hang rather than a slow case. Stopped.

The second run reproduced it on a third attempt (08:17, stopped): rank 0 printed the same two controls and then the
container sat at 199 percent CPU and the GPU at 96 percent, so it SPINS rather than waits. A wait would show near-zero
CPU.

FIRST DIAGNOSIS, WITHDRAWN: I called `gate`'s loop a leader-side spin. Reading it whole and reading `shared` refutes
that. `Engine.shared` (`cuda_engine_gate.zig:23`) is an NCCL all-reduce with `max` over `f64`: every rank sends its word
and every rank receives the maximum. The leader's word is `2*announce` when its `dropped` list is empty, a follower sends
0, so with `announce == 0` both sides see 0 and BOTH RETURN in the same step. There is no state in which one returns and
the other loops.

So the spin's cause is not read yet, and the earlier claim was mine rather than the code's. What is still true: the
process spins at 199 percent CPU at that point, and the case is the only caller that combines `keepState` with a resume,
so the next place to look is the resume path in `prefill` and what it does with a kept id, not `gate`.

Recording the withdrawn diagnosis below as the finding it was, because a wrong cause in the record costs the next pass a
whole run.

The original note, kept for the record: `cuda_snapshots.zig:139` `gate`:

```zig
while (true) {
    const word: u64 = if (!leader) 0 else if (dropped < e.dropped.items.len) 2 * e.dropped.items[dropped] + 1 else 2 * e.announce;
    const shared = try e.shared(@floatFromInt(word));
    ...
    if (got & 1 != 0) { if (leader) dropped += 1 else e.dropState(got / 2); continue; }
    if (leader) { e.dropped.clearRetainingCapacity(); e.announce = 0; } else if (got > 0) try e.keepAs(got / 2);
    return;
}
```

A follower that reads an ODD word drops that state and loops, and the leader advances its own cursor, so the two sides
only converge while the leader still has a dropped id or an announce to send. When the leader's list is empty and
`announce` is 0 it sends the even word 0, the follower takes it and returns, and the LEADER keeps looping on a word that
no longer changes. The check's new case reaches this because it keeps a state on rank 0 alone, so the ranks disagree
about what is pending.

So the resume case is blocked on an engine fix: `gate` must return when the leader has nothing left to send AND the
followers have caught up, rather than treating the absence of work as a reason to keep asking. That is a one-condition
change on the leader's side, but it changes rank agreement in the KEEP_SEQS path, so it needs a run at TP=3 to confirm
and belongs in its own commit rather than folded into the test.

The ssh key also failed for several minutes during that window and recovered on its own, which is the transient agent
state the fleet rules describe rather than the card.

Next pass, in order: bring the key back (owner present), then rerun the check with the driver's output unbuffered to see
the last line before the hang, then fix the case and rerun. The likely place is the case's pool sizing
(`r.x.snapshots(e.stateBytes(resume_at))`) or the resumed request waiting on a state the first request still holds.

## The failure chain, read off the saved rank logs (2026-11-25, run 5)

The driver's own limit bounded the run (`rc 124 1 1`, rank 0 with zero PASS and zero FAIL lines), and its saved logs name
the chain:

```
r0: RESULT control kv8=false, 3000-token prompt: differs from the fresh run at step 0, as planted   (then silence)
r1: FAIL glm-keep-seqs-check: StateKept
r2: FAIL glm-keep-seqs-check: StateKept
```

So it is not a spin in the engine: ranks 1 and 2 EXIT with `StateKept` while rank 0 keeps running, and rank 0's 199
percent CPU is it waiting in the rank fence for partners that are already gone. The earlier "engine spins" reading was
wrong for the second time, and the honest description is a follower exits and the leader waits.

`StateKept` is `snapshots.keepAs` refusing an id already in the map (`cuda_snapshots.zig:44`). The case keeps a state on
rank 0 through `keepState`; the other ranks then reach `keepAs` for the SAME id and are refused. So the case is asking
for something the ranked protocol does not allow: a state kept on one rank only. The fix is in the case (keep through
the ranked path, so all ranks agree) or the check needs a single-rank form for this case, and that is the decision the
next pass takes.

## #4809 is MERGED: TF_GLM_KEEP_SEQS is upstream (2026-11-25 09:22Z)

`gh pr view 4809` returns `state: MERGED`, `mergeCommit: ef4d6429fc873fe34cf37379f69921a791b04ab3`, merged at
`2026-11-25T09:22:24Z`, at head `241d842bc8c9`.

The twelve commits are ours: `ea38fdcf8` "glm cuda: TF_GLM_KEEP_SEQS, a released stream's sequence stays for the next
request on it" by BadAd84, then the check registration, the release-comment wording, the rank/world cast and the rank
setting commits, under one `changelog: #4258 under Unreleased` from the maintainer. So the feature landed, with the
switches fix from `40d4e19b4` among it.

Three consequences:

- The branch `keep-seqs` on the fork is a DIFFERENT lineage from the merged head. Every push tonight was rejected as a
  non-fast-forward for that reason, and none of `436ef4b5c`, `2ca51d7de`, `022992f21`, `22915d1af` is upstream. They are
  our own follow-on work, not a PR.
- The resume case has no PR to attach to. Its home is our series, and it is worth keeping: it found that a keep on every
  rank collides (`StateKept`) and that rank 0 then waits in the fence while its followers have exited.
- `docs/UPSTREAM-LINKS.md`'s row for `0032` changes from "open as #4809" to merged, with `ea38fdcf8` as the commit that
  absorbed it, which is the retirement record the file asks for.

## What upstream has, and what it still needs (2026-11-25)

Upstream main `8d3f8f923` carries the resume case as `9423ecf9c`, which is its FIRST version: `grep` finds no `spent`
field and no rank guard, so it is the version that failed at TP=3 with `StateKept` on ranks 1 and 2 and rank 0 waiting in
the fence. Our two fixes (`022992f21` the spent guard, `22915d1af` the rank-0 keep) are not in it.

That is a follow-up PR in exactly upstream's shape: one behaviour, two lines of logic and a comment, on a test file they
already have. Branch `keep-seqs-resume-fix` is cut from `8d3f8f923` in `work/resume-fix`, eight insertions and one
deletion, and its gate runs on a copy of upstream main (`~/pr/rf` on the gate host) rather than on the reseated tree,
because `test-glm-keep-seqs-host` exists only in the newer tree.

## The follow-up branch, three runs deep (2026-11-25)

`keep-seqs-resume-fix` on the fork: `261d4831f` then `99c6ed56e`, cut from upstream `8d3f8f923`, one file, gate green
(`zig fmt --check` clean, `zig build test-glm-keep-seqs-host` exit 0 on `~/pr/rf`).

The TP=3 runs and what each taught:

| run | image | ranks 1 and 2 | rank 0 |
|---|---|---|---|
| 1 | `prkeep4` (`261d4831f`) | `FAIL StateKept` | waits in the fence |
| 2 | `prkeep4` | `FAIL TestFailed` | waits in the fence |

Run 1's cause: a keep on every rank takes the same id everywhere and the fence's own `keepAs` refuses it. Fixed by keeping
on rank 0 only.

Run 2's cause: keeping on rank 0 only left the followers asserting an id their own callback never set, so they failed
their own check and exited, and rank 0 waited again. Fixed by having the followers read the id from their snapshot map,
which is where the fence put it.

Both fixes are in `99c6ed56e`, and `glm53-zig:prkeep5` PASSED at TP=3 (run 3, 2026-11-25 20:10): rc 0 on all three
ranks, `PASS prompt-cache resume at 2048 onto kept slot 14 equals a fresh 3000-token prompt` on `kv8=false` AND `kv8=true`,
with `RESULT resume control ... poisoned prompt state differs from fresh at step 0, as planted` firing first on both. So
the receipt the maintainer asked for now exists.

The lesson, learned twice: a ranked test cannot assert per-rank state that only one rank is meant to hold.
