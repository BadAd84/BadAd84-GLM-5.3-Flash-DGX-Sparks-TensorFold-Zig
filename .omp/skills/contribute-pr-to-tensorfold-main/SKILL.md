---
name: contribute-pr-to-tensorfold-main
description: "Open a PR against ashhart/TensorFold (upstream main) from our BadAd84 fork: the pre-flight checks their reviewer actually applies, the gates and commands, the traps that cost round trips, and the benchmark protocol reviewers expect."
---

# Contributing a PR to TensorFold main

Upstream is `ashhart/TensorFold`. Our fork is `BadAd84/TensorFold`; `gh` is authenticated as BadAd84 with
`repo` scope. Read `CONTRIBUTING.md` at their tip in full before starting - this file is the operating
summary, not a replacement.

## Pre-flight: the five questions their reviewer actually asks

Measured over a review of five PRs (2026-10-27). A PR that fails one of these comes back, however sound the code:

1. **Can this test fail?** A test that no test root compiles is worse than no test: it proves nothing and hides
   rot. Break the line deliberately, watch the suite fail, restore. Three branches shipped tests that never ran.
2. **Does this knob have a consumer?** `TF_EXL3_SPLITK` held a split the planner already held still;
   `first_tree` defaulted true while no vtable read it. Both were declined for the same reason. A knob arrives
   with the change that reads it, in that PR.
3. **Does the default change shipped behaviour?** Copy drafts shipped on (`Settings.on = true`) and were called
   out immediately. Anything new defaults off.
4. **Do the ranks agree, or can one wait?** A refusal that returns before a collective hangs its peers - the
   reviewer found exactly that ordering bug in a multi-rank gather. Any early return before a gather is suspect.
5. **Is the receipt measuring the thing it claims?** "MTP only" arm that still carried a proposer compared two
   arms that behaved identically. Name the arms by what they actually run.

## Before writing code

1. **Fetch their tip; do not trust a local mirror.** `git fetch upstream main`, and prove a file exists at their
   tip with `git cat-file -e upstream/main:<path>`. A stale mirror once produced a confident "upstream has no
   CUDA KDA backend" when their tip carried all five files.
2. **One change per PR, cut from `main`.**
3. **Issue first** for a new family, backend or arithmetic change; a bug fix does not need one.
4. **ATC coordination**: `npm install -g github:ashhart/ATC`, then `atc doctor --json`, `atc check <issue>
   --json` (claim only on `advice: "free"`), `atc claim <issue> --json`, and `atc overlap --json` before every
   push. Their tool is authoritative; a hand-rolled file sweep is only a cross-check.

## The gates

| gate | command | note |
|---|---|---|
| formatting | `zig fmt --check <changed files>` | a formatting fix is still a commit, never a branch rewrite |
| **lean check** | `python3 tools/zig/lean_new.py base.txt head.txt` | **base vs head**; `lean_check.py` alone prints a total and can read clean while adding findings (428 vs 456 with 28 new) |
| module size | - | at or below **600 lines**; upstream sits at the limit (597 in `cuda/roce.zig`) |
| comments | - | **single lines, at most 120 columns**; one finding per line of a block |
| host tests | `zig build test-cuda-host` | compare the FAILURE COUNT to plain upstream, not to zero |
| compile | `zig build check-native-cuda-host` | does **not** compile `tf-cuda-test` or the `.cu`: the image build is the real check |
| kernel contract | `zig/src/core/contract/` | a new or changed GPU kernel registers; the PR posts each backend's SUMMARY |

To reproduce the lean gate locally, build both lists:

```sh
git worktree add --detach /tmp/base upstream/main
(cd /tmp/base && python3 tools/zig/lean_check.py > /tmp/base.txt)
python3 tools/zig/lean_check.py > /tmp/head.txt
python3 tools/zig/lean_new.py /tmp/base.txt /tmp/head.txt
```

## Pushing from the fork

- **HTTPS push is blocked** by the token's missing `workflow` scope when the branch carries `.github/workflows/*`.
  Push over SSH: `git remote add fork-ssh git@github.com:BadAd84/TensorFold.git`, then `git push fork-ssh <branch>:<name>`.
- **Disable Actions in the fork**, or every push runs workflows there and emails failures:
  `gh api -X PUT repos/BadAd84/TensorFold/actions/permissions -F enabled=false`. The real checks run in the base repo.
- **Check runs for a fork PR live in the BASE repo** and notify the author, so "failed run" mail comes from a
  repo we do not own:
  `gh api repos/ashhart/TensorFold/commits/<sha>/check-runs --jq '.check_runs[]|select(.conclusion=="failure")|"\(.name) \(.details_url)"'`
  then `gh run view <run-id> --repo ashhart/TensorFold --log-failed`. A queue backlog shows as `queued`, not failing.
- **NEVER force-push an open PR, including to fix CI.** Add a signed commit. Rewriting removes the commit the
  reviewer and the checks were reading.

## Commit shape and identity

- Author and committer `BadAd84 <BadAd84@users.noreply.github.com>`, signed (`commit -S`).
- **A new file needs an explicit `git add`**: `git commit -a` skips untracked files, so a commit can reference a
  module it does not contain while the build still passes from the worktree. Check `git show --stat` afterwards.
- **Commit messages go in a file** (`git commit -F`): backticks in an inline `-m` are command-substituted by the
  shell, so identifiers vanish and the commit fails.
- CRLF breaks their configure guards (`HybridGeometrySourceChanged`) and bash refuses an scp'd script's
  `#!/bin/bash\r`. Note that Python's `Path.write_text` writes CRLF on Windows and leaves the file dirty against
  its LF blob.

## Benchmark protocol

```sh
python3 tools/bench_openai.py <base> <model> --tokens 256 --reps 3 --temperatures 0 --label <arm> --output decode.json
python3 tools/bench_concurrent.py <base> <model> --tokens 256 --reps 3 --temperatures 0 \
  --levels 1,2,4 --alone --serial --output concurrent.json
```

- Start the server as their `benchmark_server.zig` does: "loopback, a free port, one request at a time, no prompt
  reuse, no snapshots" (`--parallel 1 --prompt-cache-gib 0 --snapshot-dir none --max-snapshots 0`). For throughput
  scaling instead, size the pool to the levels and say so - the two answer different questions.
- Peak process RSS for memory; `nvidia-smi` reports N/A on GB10's unified memory.
- `docs/receipts/<name>/` with README, raw client output and `SHA256SUMS`.
- State the stream count beside every number.

## Exactness contracts

drafted == `"draft": false`; resumed == fresh; concurrent == solo (`--alone`); cancellation and reset leave the
next request valid. A **changed reduction order** additionally needs an independent **FP64 reference per affected
projection class**, worst per-column difference reported, prompt and decode separately.

## Traps that have cost round trips

- **A mutation that does not compile proves nothing**: an unused-local error fails the suite for the wrong reason.
  Keep every argument in use and match only summary lines.
- **Search the include graph before claiming absence**: "zero `__ldg` in `exl3_experts.cu`" was true and
  meaningless - the loader lives in `exl3_decode.cuh`.
- **Attribute production levers per lever.** spark1-3 is the MiaAI-Lab recipe (their work and other
  contributors') plus our patches; the flag table in
  `glm5.3-flash-dev/docs/GLM53-FLASH-PRODUCTION-STACK.md` records "recipe:", "otsNNNN" or another contributor's
  credit. Do not call the stack ours or theirs.
- **Before porting a lever, follow the call chain to its end.** A doc line saying "+6-7% by switching transport X"
  is not evidence our code lacks X; ours already did it, and the remaining cost was latency, not transport.
