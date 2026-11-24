---
name: submit-a-tensorfold-upstream-pr
description: "Carry an engine lever or patch onto upstream TensorFold as a PR: rebase, gate host, lean/fmt, body approval. Use before opening or updating any upstream TensorFold PR."
---

# submit-a-tensorfold-upstream-pr

one skill: carry a lever/patch onto TensorFold upstream as a PR

Merged from 19 skill(s): cut-glm-lever-for-upstream-with-lanes, gate-a-tensorfold-pr-before-asking, port-a-glm-lever-to-upstream-tensorfold, port-a-lever-patch-to-upstream-tensorfold, port-an-ai-engine-knob-commit-onto-the-upstream-pin, port-an-engine-lever-onto-upstream-tensorfold, port-an-ots-lever-onto-upstream-tensorfold-main, port-an-ovn-lever-upstream, port-recipe-lever-to-new-upstream, preflight-tensorfold-upstream-pr, prepare-a-tensorfold-upstream-patch, prepare-tensorfold-upstream-pr, prepare-upstream-tensorfold-contribution, run-an-upstream-lever-pilot-with-lanes, submit-a-patch-to-an-upstream-repo-its-rules, submit-a-patch-upstream-to-tensorfold, submit-a-tensorfold-upstream-pr, submit-tensorfold-upstream-pr, tensorfold-upstream-pr-gate.

# Open (and keep) a PR against upstream TensorFold from our fork

When: contributing an engine change from `ots/ai-engine` to `ashhart/TensorFold`, or keeping such a PR healthy as
their `main` moves (they release every few days, so a stale branch is normal).

## 0. The gate that comes first
Nothing is posted - PR title, body, comment - until the exact text has been through the style converter, my
line-by-line review and the owner's approval (RULES.md §14). "Can we upstream this?" authorises the branch, the
rebase and the tests, never the posting. The converter mangles technical text: measured 2026-11-03 it renamed
`decodeBytes` to `exl3_decode_bytes` (a function that does not exist) and produced "Measuered"/"exactely". After any
conversion, diff every identifier and number against the source text before showing it.

## 1. Branch from current upstream main, never from our trunk
Our trunk carries a whole `TF_GLM_OVN_*` knob layer and other flags that upstream has never had
(`git log -S'OvnTail' upstream/main` is empty). Branching off trunk produces a patch that cannot be reviewed.

```
git fetch https://github.com/ashhart/TensorFold.git main     # in the main clone
git worktree add -b pr-<topic> work/aie/up-<topic> FETCH_HEAD
```
Commit objects from our worktrees are in a DIFFERENT clone: fetch them across by path first
(`git fetch ../ovn-up ovn-items`) or the cherry-pick says "bad revision".

## 2. Re-seat, do not assume a port
Upstream restructures freely (in one day it deleted `exl3_ovn.cuh`, moved `grouped_body` into `exl3_grouped.cuh` and
gave `GroupedArgs.standard`/`skip`). Read what the target file looks like in THEIR tree, then re-apply the change
semantically. If a conflict block has our side empty, it is their addition - keep theirs.

## 3. Gates (all must be 0)
```
zig fmt --check zig/
zig build check-native-cuda-host
zig build compile-cuda-tests
zig build test-cuda-host
scripts\engine\fatbins.cmd <worktree>        # nvcc for every sm_121a fatbin
tools/zig/lean_check.py on base and head, then lean_new.py   # must report 0 new
```
A step named after one of OUR knobs (`test-glm-kda-pad-host`) does not exist on an upstream branch - "no such step"
is not a failure.

## 4. Push identity trap
GitHub rejects a push when the commit's author email is a private address:
`push declined due to email privacy restrictions`. Set the repo identity to
`Adam Hillson <598804+BadAd84@users.noreply.github.com>`, then `git commit --amend --no-edit --reset-author -S`
(the amend changes the hash but not the tree) and push with
`GIT_SSH_COMMAND="python C:/Users/Adam/tools/gpgssh/gitssh.py"`.

## 5. Shape the patch for them
Small is accepted. Prefer the unconditional form of a bit-exact change over a flag plus its plumbing: measured
2026-11-03, dropping the flag took the item-plan patch from 6 files/377 lines to **4 files/+313/-30** and removed a
57-line helper module entirely. Keep a plain-twice control in any new GPU check so it cannot pass vacuously.

## 6. Receipts live on THEIR base
Our fork's numbers are not evidence for their change. Queue, on a Spark:
- the byte check they can run (`tf-cuda-test <verb>` on an image built from the PR branch), and
- a pricing A/B on upstream's own base (knob on/off on one image, or two images if there is no flag), ABBA.
Research code A/Bs need two images: our `pp-chain-ab.sh` only varies env, so use the two-image variant
(`pp-img-ab.sh`, arms a/b on different images, per-arm serve flags).

## 7. Posting, then tending
`gh pr create -R ashhart/TensorFold --head BadAd84:<branch> --base main --title ... --body-file <approved>`, then
post the base-specific receipts as a follow-up comment (same approval gate).

## 8. Keeping it alive (the cadence)
When their main moves and the PR turns `CONFLICTING`:
- check `mergeable`; if conflicting, MERGE main in as a new commit (never force-push unless the maintainer asks -
  measured: on #1545 he asked, on #1623 he had not, so that one got a merge commit);
- resolve, gates again, push (fast-forward), confirm `MERGEABLE`, and hold any "rebase is in" comment for approval;
- our track record: #1534 and #1545 merged within a day of their rebase; #1623 needed two main merges in 36 hours,
  so expect to repeat this weekly.

## 9. Never weaken the check to make the PR smaller
If dropping the knob would have removed the ability to compare paths, keep the comparison by calling the plain
launch directly from the test, as #2044 does; the control arm stays the raw production path.

# Submitting a patch to TensorFold upstream

Their `CONTRIBUTING.md` is stricter than it looks. Work the gates BEFORE opening anything.

## 0. Never trust a local mirror for "what upstream has"

`git ls-remote https://github.com/ashhart/TensorFold main` for the real tip, then
`git cat-file -e <tip>:<path>` for each file the patch touches. A stale mirror branch once produced a
completely wrong claim that upstream lacked the CUDA backend it in fact carries.

```sh
git remote add upstream https://github.com/ashhart/TensorFold   # if absent
timeout 300 git fetch -q upstream main
git rev-list --count <our-base>..upstream/main                   # distance, was 202
git diff --name-only <our-base>..upstream/main | grep -E "cuda|roce|exl3|lanes/"  # what moved under us
```

## 1. Rebase as ONE CHANGE PER PR

Their rule. Cut each PR branch from `upstream/main` and cherry-pick only that change:

```sh
git worktree add --detach <scratch>/up-wt upstream/main
git checkout -B pr-<thing> upstream/main && git cherry-pick -n <commits...> && git commit -F <msg-file>
```

A commit that becomes empty because upstream reworded the same line is SKIPPED, not kept as a no-op.

## 2. Mechanical gates (all must be clean before a reviewer sees it)

- **LF checkout or every gate lies.** A CRLF tree aborts their configure step with
  `error.HybridGeometrySourceChanged` (the guards in `zig/src/families/flashnext/geometry_source.zig`
  match anchors exactly once), which looks like "my change broke the build".
  ```sh
  git config core.autocrlf false
  git ls-files -z | xargs -0 rm -f; git checkout -- .
  # verify: no tracked non-binary file contains \r\n
  ```
- **Lean checker must add zero.** Record the baseline on `upstream/main` first, diff the finding lists:
  ```sh
  python3 tools/zig/lean_check.py > base.txt      # 428 problems / 4,407 files on c6df96cf
  git checkout <branch> && python3 tools/zig/lean_check.py > br.txt
  comm -13 <(sort base.txt) <(sort br.txt)        # what your branch ADDED
  ```
- **Source files <= 600 lines.** Upstream lives near the cap (their `roce.zig` is 597), so a feature has
  to move its own logic into a new module rather than grow the file.
- **Comments are SINGLE lines of <= 120 columns.** The checker flags one finding PER LINE of a
  multi-line block, so a 3-line doc comment costs 3 findings. Also: inserting a function between an
  existing docblock and its function orphans that docblock - re-anchor it.
- **Windows checkout:** run zig gates under WSL with a WSL-local cache (`--cache-dir`/
  `ZIG_GLOBAL_CACHE_DIR`), because Windows-authored `.zig-cache` entries make rename fail with
  `AccessDenied` on `/mnt/c`. WSL git cannot use a worktree whose `.git` file holds a `C:/` path -
  switch branches with Windows git and run only zig under WSL.
- **A test must actually be in the graph before you trust its green.** `zig/glm_contract_host.zig`
  imports only `core` + one contract file, so `test` blocks in `families/glm/*.zig` NEVER run. Prove
  the test executes (mutation must turn it RED) before claiming it defends a fix. A mutation that
  fails to COMPILE proves nothing either - keep every argument used.
- Gates: `zig build check-native-cuda-host` and `zig build test-cuda-host`, and compare the FAILURE
  COUNT against `upstream/main` in the same tree (26 failures were the baseline):
  ```sh
  zig build test-cuda-host    # then diff the failing test NAMES against baseline, not just counts
  ```

## 3. Overlap sweep against every open PR (their `atc overlap` equivalent)

The REST API truncates and rate-limits; the git protocol does not:

```sh
git fetch -q upstream '+refs/pull/*/head:refs/remotes/orig/pr/*'
# for each OPEN pr number n:
git diff --name-only upstream/main...refs/remotes/orig/pr/$n
```

Intersect those with the files your branch touches. Report per branch: CLEAR, or the PR numbers and
shared files. File-level overlap on shared plumbing (`zig/src/native/cuda.zig`) is normal; overlap on
the same FUNCTION is what needs an issue comment first.

## 4. Receipt in THEIR format (not our harness)

```sh
python3 tools/bench_openai.py http://127.0.0.1:8080 MODEL \
  --tokens 256 --reps 3 --temperatures 0 --label <arm> --output decode-<arm>.json
python3 tools/bench_concurrent.py http://127.0.0.1:8080 MODEL \
  --tokens 256 --reps 3 --temperatures 0 --levels 1,2,4,6,8 --alone --serial --output concurrent-<arm>.json
```

- Their protocol is intentionally ONE REQUEST AT A TIME (`benchmark_server.zig`: `--parallel 1
  --prompt-cache-gib 0 --snapshot-dir none --max-snapshots 0`), so `per_stream == aggregate` and TTFT
  rising with the level is correct. Do not "fix" it. Aggregate scaling is a separate measurement with
  the pool sized to the level, one fresh boot per cell.
- `bench_concurrent --alone --serial` gives two exactness contracts free: concurrent == solo, and
  drafted == plain.
- Record: commit/image, GPU + driver, OS, checkpoint revision, request parameters, and a memory
  receipt (on GB10 `nvidia-smi` reports N/A - use the process's `VmHWM`).
- `docs/receipts/<name>/` with README + metrics + SHA256SUMS.

## 5. Rules that need work before a PR, not after

- **Issue first** for a new family, backend, or arithmetic change.
- **An independent FP64 reference for every affected projection class** when the reduction order
  changes, with worst per-column error reported, not just an aggregate.
- **Public identity**: approved Git identity + GitHub noreply address; no private emails, machine
  names, local paths, or internal ticket ids (`OTS-1234`) in source, fixtures or receipts.
- Nothing goes outward-facing without the owner's explicit go-ahead.

## Traps that cost real cycles

- A scripted `replace` with no assertion silently changes nothing and you conclude the wrong thing.
  Always `assert s.count(old) == 1` (a CRLF script also fails this way: `/usr/bin/env: 'bash\r'`
  produces an empty log that reads like a hang - strip CRLF on anything shipped to a Linux box).
- A stale `res/*.json` from a previous run looks like fresh evidence: delete outputs before each run.
- Do not declare a test load-bearing from a mutation that breaks the build, or that the suite never
  compiles.

# Submitting a patch upstream to TensorFold

Their `CONTRIBUTING.md` is the contract; read it in full, plus `docs/kernel-contract.md` and
`docs/atc/SKILL.md`. One change per pull request, from `main`.

## 0. Establish the real base - never trust a local mirror

`git ls-remote https://github.com/ashhart/TensorFold main` gives their tip. A local `mirror/main`
snapshot can be hundreds of commits stale and will make you assert things about upstream that are false
(measured: a stale snapshot at `0efbd447` made me claim upstream had no CUDA backend; the tip
`c6df96cf` had it in full). Fetch it, then cut every branch from that tip:

git fetch upstream main
    git checkout -B pr-<topic> upstream/main
    git cherry-pick <our commits>        # then squash: one commit per PR

## 1. Static gates (all must be at baseline, not merely green)

python3 tools/zig/lean_check.py     # baseline on main = 428 problems / 4,407 files
    wc -l <every file you touched>      # 600-line cap per module, hard
    zig build check-native-cuda-host    # compiles the native CUDA server, no GPU
    zig build test-cuda-host            # compare the FAILURE COUNT to their tip, not to zero

Two rules that quietly fail PRs: comments must be a **single line** of at most 120 columns (a multi-line
doc block costs one finding per line), and a file that is already near 600 lines forces you to move
something out. Upstream `cuda/roce.zig` was at 597, so our change had to split its ABI declarations and
region layout into new modules rather than grow it.

Before believing a test you added, prove the suite actually compiles it: the GLM host test root is
`zig/glm_contract_host.zig` and it imports only `core` plus one contract file, so a test inside
`families/glm/<anything>.zig` never runs. Run a mutation of your own fix and require the suite to fail;
three mutations passed before I noticed the test was dead.

## 2. Receipts in their format

Their clients only: `tools/bench_openai.py`, `tools/bench_concurrent.py` (they import the `bench_*`
helper modules - copy the whole set). Greedy, 256 tokens, 3 reps, `--prompt-cache-gib 0`, fresh KV, and
`--alone --serial` on the concurrent run, which also checks drafted == plain for you. Record commit,
GPU, driver, checkpoint revision, settings, and peak process RSS as the memory figure - `nvidia-smi`
reports N/A on GB10 because memory is shared with the host.

Their `benchmark_server.zig` documents a child that runs **one request at a time** (`--parallel 1`), so
`per_stream == aggregate` and TTFT growing with the level is their protocol, not a defect. A pooled server
is the separate scaling measurement; report both and say which answers which question.

A changed reduction order additionally needs an independent FP64 reference **per projection class**,
worst per-column reported, not an aggregate. To observe an internal projection you may have to add a
dump hook behind an env var - `--dump` on the CLI writes layer activations from before the projection.

## 3. Coordinate with ATC

npm install -g github:ashhart/ATC
    atc doctor --json                 # must report ready
    atc check <issue> --json          # advice: free -> claim; taken -> propose, never race
    atc claim <issue> --json
    atc overlap --json                # before pushing or opening a PR

An issue comes FIRST for a new family, backend or arithmetic change. A bug fix can go straight to a PR.

## 4. Publishing, and the three traps that cost real time

- **Push over SSH, not HTTPS.** An HTTPS push is rejected with "refusing to allow an OAuth App to create
  or update workflow ... without `workflow` scope" because the branch carries `.github/workflows/`.
- **Disable Actions on the fork first**, or every push emails the owner failure notices:
  `gh api -X PUT repos/<owner>/<repo>/actions/permissions -F enabled=false`, then cancel queued runs with
  `gh run cancel <id>`. PR checks still run in the base repository, so nothing is lost.
- **CRLF disables their gates.** Upstream's build patches kernel sources at configure time and aborts with
  `error.HybridGeometrySourceChanged` when an anchor's trailing newline is `\r\n`. `git status` can report
  such a file clean, so verify by reading bytes and re-materialise with
  `git ls-files -z | xargs -0 rm -f && git checkout -- .` (16 remaining CRLF files were all binaries).

Identity and history: commits must carry the approved public identity with a GitHub noreply address; no
private domain emails, machine names or local paths. Never force-push a PR branch - a CI failure is fixed
by adding a commit, exactly like a review finding.

## 5. Before calling it submitted

`gh pr view <n> --repo <base> --json mergeable,statusCheckRollup` - MERGEABLE plus their `fmt` and `zig`
jobs reported. Their `fmt` gate runs `zig fmt --check`, so format the files you touched before pushing;
it is the single cheapest failure to avoid and it cost two force-pushes (which were themselves the
violation) in the first round.

# Prepare a TensorFold upstream PR from the ai-engine fork

## 1. Pin the real upstream tip - never a local mirror

```sh
git ls-remote https://github.com/ashhart/TensorFold main    # live tip
git remote add upstream https://github.com/ashhart/TensorFold
git fetch upstream main
git rev-list --count <our-base>..upstream/main              # how far behind
```

A stale `mirror/*` ref caused a false "upstream has no CUDA backend" conclusion (mirror was
`0efbd447`, tip was `c6df96cf`, 202 commits ahead). A negative claim about upstream needs the live
remote, and check file presence directly: `git cat-file -e upstream/main:<path>`.

## 2. Sweep the open PR queue with git, not the API

```sh
git fetch upstream '+refs/pull/*/head:refs/remotes/orig/pr/*'     # ~1,066 refs, no rate limit
```

For each open PR number N: `git diff --name-only upstream/main...refs/remotes/orig/pr/N`, intersect
with the files your branch touches. The REST API truncates listings and rate-limits (403) part-way
through a 94-PR sweep, which silently yields a half-answer. Report CLEAR vs overlapping per branch.

## 3. One concern, one branch, from current main

```sh
git checkout -B pr-<concern> upstream/main
git cherry-pick <commits>            # resolve, skip commits that become empty
```

A commit that a later one subsumes shows as empty - `git cherry-pick --skip` it rather than keeping a
no-op. Squash fixups before opening.

## 4. Prove the checkout is LF before any gate

A CRLF worktree makes upstream's configure-time source-patching guards abort with
`error.HybridGeometrySourceChanged`, which reads exactly like "your change broke the build".

```sh
python3 - <<'PY'   # count tracked files containing CRLF
import subprocess
from pathlib import Path
files=[f for f in subprocess.run(["git","ls-files"],capture_output=True,text=True).stdout.split("\n") if f]
bad=[f for f in files if b"\r\n" in Path(f).read_bytes()[:200000]]
print(len(bad), "of", len(files))
PY
git ls-files -z | xargs -0 rm -f; git checkout -- .   # re-materialise from the index
```

Leftover CRLF hits should all be binaries. Run zig from WSL/Linux with its own
`--cache-dir`/`ZIG_GLOBAL_CACHE_DIR`, since Windows-authored cache entries block renames on /mnt/c;
and switch branches with WINDOWS git, because a worktree's `.git` file holds a Windows path WSL git
cannot follow.

## 5. Gates and their baselines

- `zig build check-native-cuda-host` - compile gate, must exit 0.
- `zig build test-cuda-host` - compare the FAILURE COUNT to plain `upstream/main` (26 here). Zero is
  not the target; equal-to-baseline is. Diff the failing test NAMES, not just counts.
- `python3 tools/zig/lean_check.py` - must add ZERO over the pinned baseline (428 problems, 4,407
  files). Diff its output against the baseline run to see your own findings only.

## 6. Style limits that bite

- Every source file <= 600 lines. Existing files sit near the cap (`roce.zig` was 597), so new logic
  belongs in a NEW module imported by the old one; re-export what callers need.
- Comments must be SINGLE lines of <= 120 columns. The checker emits one finding per line of a
  multi-line block, so a 3-line doc comment costs 3 findings. Collapse; keep the meaning.
- Never leave a docblock stranded above a function you inserted (orphaned docblock): move the original
  doc back to its owner.
- No internal ticket ids (e.g. `OTS-1297`) and no private emails/machine names/local paths in source;
  published commits need an approved public identity with a GitHub noreply address.

## 7. Prove the change, their way

Performance receipts use THEIR clients, with the helper modules (`bench_auth`, `bench_cache`,
`bench_evidence`, `bench_metrics`, `bench_timing`) beside them:

```sh
python3 tools/bench_openai.py http://127.0.0.1:PORT MODEL --tokens 256 --reps 3 --temperatures 0 --label arm --output decode.json
python3 tools/bench_concurrent.py http://127.0.0.1:PORT MODEL --tokens 256 --reps 3 --temperatures 0 --levels 1,2,4,6,8 --alone --serial --output concurrent.json
```

- Boot the server with enough stream slots for the highest level measured. Booting 1 slot queues the
  4/6/8 levels and yields plausible-looking garbage (~50 tok/s flat instead of 80/89).
- `--prompt-cache-gib 0` and fresh KV per measurement; record commit/image, GPU, OS, checkpoint
  revision and a memory receipt (peak RSS, device used).
- `bench_concurrent --alone --serial` also covers their concurrent == solo and drafted == plain
  contracts.
- A changed reduction order needs an independent FP64 reference per affected projection class.
- A test that lives in a file the test root does not import is DEAD: three mutations of a fix came
  back green because `zig/glm_contract_host.zig` imports only `core` + one contract file. Confirm the
  suite total rises when you add a test, or prove the change with a hardware receipt instead.
- A mutation must COMPILE; keep every local/parameter in use or the "failure" is a build error.

## 8. Before opening

- Issue first for a new family/backend/arithmetic change; ATC coordination (`atc overlap --json`,
  claim a session, read `docs/atc/SKILL.md`).
- `docs/receipts/<name>/` with README, metrics and SHA256SUMS; PR body states the lean baseline count
  and which findings are inherited; post each backend's `SUMMARY` line.
- Kernel changes register with `docs/kernel-contract.md` (five gates, fp64 reference, served envelope,
  launch record).

# Preparing a TensorFold upstream patch

Their bar is higher than a normal repo's and fails quietly. Read `CONTRIBUTING.md` IN FULL (the first
60 lines are the easy part), plus `docs/kernel-contract.md` and `docs/atc/SKILL.md`.

## 1. Rebase onto the real tip first

`git remote add upstream https://github.com/ashhart/TensorFold && git fetch upstream main`.
A local mirror of theirs is often stale and will make you claim things like "upstream lacks X" when it
does not. Check the exact files your patch touches exist at `upstream/main:<path>` before designing.

## 2. Mechanical gates (all fail-able, all cheap)

- `python3 tools/zig/lean_check.py` - must **add zero** over the branch's baseline (428 problems /
  4,407 files on `c6df96cf`). Report the baseline and which findings are inherited.
- **Files at or below 600 lines.** Check every file you touch with `wc -l`; if upstream is already at
  597, your feature needs its own module (extract your own new logic, keep behaviour identical).
- **Comments are single lines, at most 120 columns.** The checker raises one finding PER LINE of a
  multi-line block, so a 3-line doc comment costs 3. Collapse to one line per entity. Moving code moves
  or deletes its docblock - an orphaned docblock is both a finding and a lie.
- Checkout must be LF: a CRLF tree aborts their configure step with `error.HybridGeometrySourceChanged`
  (their build patches kernel sources by anchor). `git config core.autocrlf false`, then re-materialise
  from the index if needed. Same for scripts you scp to a Linux box.

## 3. Proof, in their form

- Performance: `tools/bench_openai.py BASE MODEL --tokens 256 --reps 3 --temperatures 0 --label X
  --output decode.json` and `tools/bench_concurrent.py ... --levels 1,2,4,6,8 --alone --serial`.
  Needs `bench_auth.py`, `bench_evidence.py`, `bench_metrics.py`, `bench_timing.py` alongside.
  Boot the server with the pool sized to the levels you measure (`--parallel N`); their own
  `benchmark_server.zig` uses `--parallel 1 --prompt-cache-gib 0 --snapshot-dir none --max-snapshots 0`
  for its internal child, which measures queueing, not scaling - say which question you are answering.
- A changed **reduction order** needs an independent FP64 reference per affected projection class, with
  worst per-column differences reported, not just an average.
- Exactness at one checkpoint: drafted == `"draft": false`, resumed == fresh, concurrent == solo,
  cancellation/reset leaves the next request valid. `--serial` checks the drafted case for you.
- `zig build test-cuda-host` and `test-golden` on Linux; report counts and inherited failures.
- If you change a `.cu`, register it with the kernel contract and post each backend's `SUMMARY` line.

## 4. Procedure

One change per PR from `main`; an **issue first** for a new family, backend or arithmetic change;
`atc overlap --json` and claim a session; sweep the open PR queue for file overlap (fetch
`+refs/pull/*/head:refs/remotes/orig/pr/*` - no API rate limit - and intersect changed files); a
`docs/receipts/<name>/` with README, metrics and SHA256SUMS; a public Git identity with a GitHub
noreply address and no private emails, machine names, internal ticket ids or local paths.

## 5. Traps that cost real time

- A test block in a file the test root does not import **never runs** - mutations come back green. Prove
  the test is in the suite before trusting an A/B.
- A mutation that fails to compile (unused variable) shows the same failure count as the baseline and
  proves nothing; keep every argument used.
- Truncated API listings mislead: check `per_page=100` and the real count before comparing.

# Preparing a TensorFold upstream contribution

Upstream `ashhart/TensorFold`. Their `CONTRIBUTING.md` is strict; every gate below was learned by failing it.

## 0. Establish the real upstream tip first
`git ls-remote https://github.com/ashhart/TensorFold main`, then `git fetch upstream main`. Do NOT reason from `mirror/main` in `ots/tensorfold-gb10` - it is a stale snapshot (0efbd447 vs the real c6df96cf) and reading it produced a completely wrong "upstream has no CUDA backend" claim. Upstream main already carries the GLM CUDA family and the cuda recipes.

## 1. One branch per change, cut from upstream/main
`git checkout -B pr-<change> upstream/main`, cherry-pick only that change's commits, resolve conflicts, then squash to ONE commit. Their rule is one change per PR. Drop anything measured negative (we excluded L2PF and EXL3_PIPE) - a negative arm still costs a reviewer's time.

## 2. CRLF will fake a build break
Their configure step patches kernel sources and aborts with `error.HybridGeometrySourceChanged` (from `zig/src/families/flashnext/geometry_source.zig`) when an anchor's newline does not match. A Windows-materialised worktree had 2,272 of 8,694 files in CRLF and every gate failed, reading exactly like "your change broke the build". Fix: set `core.autocrlf false`, delete tracked files, `git checkout -- .`, then re-scan; the only remaining CRLF files should be binaries (PNG/icns/.bin). Same class bites remote scripts: a `.sh` with CRLF dies as `/usr/bin/env: 'bash\r': No such file or directory` and produces an empty log that looks like a hang.

## 3. Static gates
- `python3 tools/zig/lean_check.py` must add ZERO problems over baseline (main = 428 problems / ~4,407 files). Compare sets, not counts, to attribute findings.
- Every comment must be a SINGLE line of at most 120 columns. A multi-line comment is one finding PER LINE, so a 4-line doc comment costs 4. Write one `///` line per entity.
- Source files at or below 600 lines. `roce.zig` was already at 597 upstream, so ANY addition forces a module split - extract cohesive units (ABI declarations, region layout) into new files rather than compressing.
- Verify `zig build check-native-cuda-host` and `zig build test-cuda-host`, and diff the FAILURE SET against plain upstream, not the count: our branch matched at 26 failures = baseline.
- Run zig/lean from WSL (`~/tools/zig-x86_64-linux-0.17.0/zig`, set `ZIG_GLOBAL_CACHE_DIR`, distinct `--cache-dir` per branch) but run **git from Windows**: a linked worktree's `.git` file holds a Windows path and WSL git reports "not a git repository".

## 4. Never trust a test you have not seen run
Before claiming a test is load-bearing, confirm the test root imports the file. `zig/glm_contract_host.zig` imports only `core` plus one contract file, so `test` blocks inside `src/families/glm/dflash_load.zig` are never compiled - three mutations of a "fix" all came back green. A mutation must also COMPILE (an unused local or parameter turns the A/B into a build error, which proves nothing).

## 5. Receipts in their format
Their clients, not ours: `python3 tools/bench_openai.py <base> <model> --tokens 256 --reps 3 --temperatures 0 --label <arm> --output <file>` and `tools/bench_concurrent.py ... --levels 1,2,4,6,8 --alone --serial`. Copy the whole `tools/bench_*.py` set (they import bench_auth/bench_evidence/bench_metrics/bench_timing).
Boot the server with the pool sized to the levels measured, or the concurrency cells silently queue and `per_stream == aggregate`. Record commit/image, GPU, driver, OS, checkpoint revision, and peak process RSS (`nvidia-smi` reports N/A on GB10 unified memory). Keep your own 1-8 matrix as the separate no-regression view and say plainly that the two are not comparable across harnesses.

## 6. Identity and disclosure
Owner-confirmed identity: `BadAd84 <BadAd84@users.noreply.github.com>`, set via `GIT_AUTHOR_*`/`GIT_COMMITTER_*` at commit time. No private emails, machine names or local paths; no tool co-author trailers; strip internal ticket ids (an `OTS-1297` reference had to come out of a comment).

## 7. Before opening anything
Issue first for a new family, backend or arithmetic change, with the gate you propose written down. `atc overlap --json` plus a session claim per their ATC workflow. Check every open PR for file overlap by fetching all PR heads (`git fetch upstream '+refs/pull/*/head:refs/remotes/orig/pr/*'`) and intersecting changed files - the REST API rate-limits mid-sweep and a truncated listing under-reports badly (94 open PRs looked like 28).

## Verification sequence that worked
rebase -> comment/size gates -> lean set-diff -> host suite vs baseline -> (if the change moves code) rebuild the image and re-run the real TP test, because passing static gates says nothing about a refactor that touched a working transport.

# Preflight an upstream TensorFold PR

Their CI is the only opinion that counts, and two of its gates reject things a local build accepts.

## 1. Comments are one line, at most 120 columns

The `lean` gate reads every `//`, `///`, `#` and `/*` block in `zig/` and `tools/zig`. A multi-line block produces **one
finding per line**, so a ten-line doc comment is ten findings and fails the job. Put the detail in a repo doc; leave the
code a single short line.

## 2. Verify with their tool, base against head

`zig fmt` cannot check `.cuh` (it parses them as Zig and errors), so lean is checked only this way:

```sh
git worktree add /tmp/base <base-commit>
(cd /tmp/base && python3 tools/zig/lean_check.py . > /tmp/base.txt)
python3 tools/zig/lean_check.py . > /tmp/head.txt
python3 tools/zig/lean_new.py /tmp/base.txt /tmp/head.txt   # must print "0 new"
```

`lean_new.py` is Windows-Python friendly only with `C:/...` paths; pass Windows paths, not `/c/...`.

## 3. Files stay at or below 600 lines

The same gate enforces it. A feature that would push a file over moves a cohesive unit into its own module.

## 4. Fix forward, never rewrite

A gate failure or a review finding is fixed by a NEW signed commit (`Review round N: ...`). Never force-push a PR
branch, not even for a formatting-only fix: the reviewer already read the commit being replaced.

## 5. Before pushing, check the numbers you will quote

Every claim in the PR body needs a measurement behind it: the speed matrix at 1/2/4/6/8 with a fresh boot per cell,
reply digests for bit-exactness, and a note of what is still owed. Reviewers there check defaults: a patch that
changes existing behaviour must ship behind an off-by-default flag.

# Gate a TensorFold PR before asking for sign-off

Their CI is the only opinion that counts, and it is stricter than a single-tree local check. Every step below cost a
round trip on 2026-11-03; run them in order and put the outputs in the hand-off.

## 1. Diff against UPSTREAM main, never the fork

```sh
git fetch https://github.com/ashhart/TensorFold.git main:refs/remotes/up/main
git diff --stat refs/remotes/up/main...HEAD     # three dots = merge-base
```

Our fork's `main` goes stale within hours: it turned a 4-file PR into a 4,000-file, 219 MB diff. Quote the upstream
sha in the review, the receipts and the reply.

## 2. Their lean gate, base versus head

```sh
D=$(mktemp -d); git archive refs/remotes/up/main | tar -x -C $D
(cd $D && python <repo>/tools/zig/lean_check.py > base.txt)
python tools/zig/lean_check.py > head.txt
python tools/zig/lean_new.py base.txt head.txt      # must print "0 new"
```

`lean_check.py` prints a single-tree total, so a change can add findings while the number looks unchanged. Their rules
that this gate enforces: comments and docstrings are SINGLE lines of at most 120 columns, and the check counts every
line of a block - a three-line comment is two new problems. Source comments state facts about the code: no reviewer,
PR, issue or date references.

Note: Windows Python resolves `/tmp/x.txt` to `C:\tmp`, while the bash redirect writes to the WSL `/tmp`. Use one
Windows-visible path for both the redirect and the argument.

## 3. Counts in prose are part of the change

After any test change, grep the branch's own words for every figure it states and recompute:

```sh
gh pr view <n> -R ashhart/TensorFold --json body | grep -oE '[0-9,]+ (comparisons|checks)'
git log --format=%B refs/remotes/up/main..HEAD
```

A check that went 36 -> 44 -> 66 left the body claiming `0 of 3,984` and a commit message `36 to 44`. Fix both in the
same push; a squash is the tidy way when the stale figure lives in a commit message (and the maintainer suggesting it is
the force-push permission - announce it in one line).

## 4. Price the PR, not the fork

For a served-model receipt, the candidate arm is the PR's own head and the control is the base at its own sha, both
built through `~/glmperf/ovnlib.sh build TAG` (which also `docker save | ssh docker load`s to spark5/6 and verifies -
a bare `build-image-gram.sh` leaves the rank boxes imageless). Export `NODEFS=1`: `serve4.sh` otherwise appends our 23
`TF_GLM_OVN_*` knobs to BOTH arms and the table prices the fork's tuning instead of the PR.

## 5. Chains: markers on every exit path

A pricing chain that waits for `ITEMSTEST-CHAIN-DONE` must be able to see it even when the producing chain fails: give
the producer `trap 'echo "<MARKER> $(date -Is) rc=$?"' EXIT`. And never edit a script a chain is executing - bash reads
by byte offset; kill it and relaunch from the edited file.

## 6. ATC

`atc check <pr> --json`, then `atc overlap --json` before a push. `complete: false` (e.g. `pullFilesUnavailable`,
`timeLimit`) means the check did not finish - report that as incomplete and never call it clean.

## 7. Present for sign-off

Post nothing until the owner approves the exact words: the review summary (files, commits, gates with the base/head
pair and command, CI state, what is unresolved), the comment text after the restyle-and-repair pass, and any body or
commit-message edit.

# TensorFold upstream pre-PR gate

Run ALL of these on the PR branch before claiming it is clean. The plain lean checker under-counts.

## The gate (in order, on the PR branch)

1. `zig fmt --check zig/src zig/build build.zig` - rc=0.
2. `python3 tools/zig/lean_check.py` - record the count, but this is NOT the gate; pr_check is.
3. `python3 tools/pr_check.py --base origin/main --pr <NUMBER>` - **the authority**. It counts lean
   findings per-file differently (multi-line comment blocks and over-120-column lines are errors, not
   warnings) and requires a CHANGELOG Unreleased bullet naming the PR. Use a dummy PR number
   (e.g. 9999) for the pre-push run.
4. `zig build test --summary all` in the base image - compare failing-test LISTS, not counts.
5. Fatbins compiled (the host suite does not compile `.cu`; a missing instantiation or a syntax error
   only shows at boot or in the image build).

## Common findings

- Multi-line `//` comment blocks: collapse to single lines <= 120 columns, or move the content to the
  PR body / receipt (upstream: "measurements and history belong in a receipt or recipe, not source").
- Lines past 120 columns: wrap code with line continuation; shorten or split log-format strings.
- Missing CHANGELOG bullet: add under `## Unreleased`, naming the PR.
- `tf.kernels` label: `build-br.sh` images need `tf.kernels=embedded` for the recipe's start.sh -
  `echo "FROM <img>" | docker build -q --label tf.kernels=embedded -t <img> -`.

## The workflow

1. Work on a branch (one lever = one branch), push to the backup remote first.
2. Export the `.patch` for the recipe side if needed; the branch is the source of truth.
3. Run the full gate; fix until clean.
4. Push the PR branch to the GitHub fork; open the PR from it (never attach a .patch).

# Porting one GLM lever to upstream TensorFold

Use when a lever of ours (a `patches/engine/NNNN-*.patch`) has to go to `ashhart/TensorFold` as its own pull
request, with its own gates and a receipt. Measured 2026-11-23 on `TF_GLM_KEEP_SEQS` and `TF_GLM_NO_COPY`.

## Carry the patch

```
git -C work/up/TensorFold worktree add ../../pr/<name> -b <name> refs/remotes/up/main
cd work/pr/<name>
git apply --3way --exclude=<files upstream removed> <repo>/patches/engine/NNNN-*.patch
```

`--exclude` is needed for our registry file (`zig/tests/cuda/glm_ovn_checks.zig`), which upstream does not have; without
it the whole apply aborts and leaves nothing half-done.

**Our patches carry other levers' context lines.** A conflict block whose `ours` side is empty and whose `theirs` side
holds several rows is not "take theirs": it holds rows from patches that must NOT ship here. Keep only the line naming
this lever (assert exactly one, then drop the rest).

## The switch has five places upstream

1. `zig/src/platform/environment.zig`: a `.glm` row (`.kind = .flag`, `.forms = "0 or 1"`), plus the row in
   `docs/environment.md`.
2. `zig/src/families/glm/cuda_ranks.zig`: a `Settings` field and its read block in `readSet` (`if (get("NAME"))`, 1/0
   else `error.BadSetting`). This is the single owner every caller shares.
3. `zig/src/families/glm/cuda_engine.zig`: an `Engine` field, assigned from `o.settings.<name>` immediately AFTER the
   `e.* = .{ ... }` literal in `init`.
4. The policy code that reads it (release, lane facts, and so on).
5. The ranks' `Fingerprint`, which lists fields BY HAND in six places and will not compile without the last one:
   the struct field, `layout` bumped by one with a comment naming the field, `Fingerprint.of`, the `Field` enum, the
   `mismatch()` name tuple, and the `explain()` switch. Add the name to the "every field that differs" test in
   `cuda_ranks_test.zig` too.

**Reading the variable in the server path is the trap.** `cuda_native.openRank` is not on every `Engine.init` path, so a
GPU check or any other caller sees the setting off. Put it in `Settings` and pass it in the options.

## A new GPU check

Upstream has no `*_check.zig` executables: a check is `zig/tests/cuda/<family>_tests.zig` with
`pub fn <name>Check(gpu: check.Gpu, ...)` and it registers in `zig/tests/cuda/main.zig` as an import plus a dispatch line
(`arg(rest, N)`). A host case goes in a `*_test.zig` imported by the family's `test` block and gets its own build step
(`b.step("test-<name>-host", ...)`, filters on the test names).

## The receipt on one Spark

The 4bpw EXL3 snapshot is 163.6 GiB, more than one GB10 holds, so a single-rank check runs with `TF_GLM_LAYERS=2`; the
MTP head loads separately from the layer list, so draft comparisons still work. Build the runner inside the pytorch
image (zig 0.17.0 downloaded and sha-checked, `zig build -Dnvcc=/usr/local/cuda/bin/nvcc -Dsm=121 -Doptimize=fast
compile-cuda-tests`), about twenty minutes a build: verify the archive carries the fix before spending it.

## Gates, in the order that catches mistakes

1. `zig build compile-cuda-tests` on the gate host: the fastest way to catch a missing enum case.
2. The host step for the new test, and the eight `test-glm-*-host` steps.
3. `python tools/pr_check.py --base <up/main>`: 0 errors, and its one warning is the changelog line, which needs the
   PR number and goes in as a later commit.
4. lean base against head with each side's own `tools/zig/lean_check.py`, two different file counts, 0 new.
5. `zig build test test-golden`, read against the same run's pristine base: on a host whose GPU cannot run these
   kernels the failing step set is identical to the base's, which is the evidence that nothing was added.

## Traps that cost real time

- `pkill -f <pattern>` matches your own ssh command line and kills the session; kill by PID from `pgrep`, and never put
the literal pattern in the same command.
- `git archive HEAD` ships only committed content: a fix left in the working tree is silently absent, and the remote
  build fails on the old text. Check `git status` first and `tar -xOf` the archive afterwards.
- A host test that fakes our `cuda.ovn` registry does not compile upstream: drive the settings field instead.

# Port a lever patch to upstream TensorFold

Use when a lever in `patches/engine/` (or a port-* package) has to go upstream as its own pull request. One behaviour a branch, cut from upstream `main`, never from our fork's main.

## Before any edit

1. `git fetch https://github.com/ashhart/TensorFold.git main` and read `CONTRIBUTING.md`, `docs/atc/SKILL.md`, `docs/pr/SKILL.md` at that tip. Quote the base sha in every receipt and in the review.
2. Find or open the issue; run `atc check ISSUE --json` and read `complete` first. `complete:false` with `pullRequestsLimit` is ATC's own window over a repo with hundreds of PRs, not our quota (`gh api rate_limit` proves it); the owner may override it, and `duplicateAttempts` is the field that matters.
3. Worktree: `git -C <upstream clone> worktree add ../../pr/<name> -b <name> refs/remotes/up/main`.

## Carrying the patch

4. `git apply --3way --exclude=<files upstream deleted> <patch>`. Expect conflicts where our series added context rows that belong to OTHER levers: resolve each conflict to the ONE line this lever owns and drop the rest, or the PR carries several behaviours and gets refused.
5. Our registry reads do not exist upstream (`cuda.ovn.on("X")`, `cuda.ovn.fake`). Re-express the setting the upstream way: a row in `zig/src/platform/environment.zig`, a field on `ranks.Settings` with its `readSet` block, passed through `Options.settings` into `Engine.init` (or the struct that owns the behaviour), read from `o.settings.<field>`.
6. Every setting must then join the SIBLINGS, all hand-written lists: `Fingerprint` struct field with `layout` bumped and its comment naming the new field, `.field = @intFromBool(s.field)` in `Fingerprint.of`, `Fingerprint.Field` enum member, the name tuple in `mismatch()`, the `explain()` switch case, and the divergence test's inline field list. A missing `explain` case is a compile error; a missing `mismatch` entry silently stops the ranks agreeing.
7. Checks are not executables upstream: a `pub fn <name>Check(gpu, checkpoint, id_path, rank, world)` in `zig/tests/cuda/<name>_tests.zig`, registered in `zig/tests/cuda/main.zig` (import + `if (std.mem.eql(u8, cmd, "<name>"))`), mirroring `glm-solo-check`. Cast rank and world with `@intCast` as the siblings do.

## Gates, in the order they cost least

8. Compile first on the shared gate host (`python scripts/spark-gates.py`, or a plain `zig build compile-cuda-tests` on a tree shipped by tar): never spend an image build on code that has not compiled. `compile-cuda-tests` compiles the GPU runner; `zig build test-glm-<x>-host` runs the new host test by name filter.
9. Lean base against head with each side's own `lean_check.py`, two file counts that differ, then `lean_new.py`. A file at 600 lines is the wall: move the field to the engine rather than adding a line.
10. `python tools/pr_check.py --base <upstream sha>`; `zig build test test-golden`, and read a failure set against the PRISTINE BASE's own run (a host whose GPU cannot run the kernels fails the same 27 test binaries). Copy up to the run's own platform.

## Receipts

11. GPU run of the check: build an image from the branch tree with `build-image.sh`-shaped Dockerfile plus `compile-cuda-tests`, then run it with `TF_GLM_LAYERS=2` when the checkpoint exceeds one box (GLM-5.3-Flash 4bpw is 163.6 GiB; one GB10 holds less), and `TF_GLM_KEEP_SEQS`-style switch on. Capture the control RESULT lines and the PASS line; run once with the switch unset to show the check refuses.
12. An A/B compares the branch against upstream main with the SAME launcher and only the switch differing; `KNOBS=off` keeps our env out of both arms. Equal token digests per level are the exactness evidence; a flat speed result is only meaningful once you have proved the switch reached the engine (grep the switch in the image's binary, and remember `XENV` is the launcher's `-e` path).
13. A lever whose mechanism needs a workload the bench does not produce (a copy window needs a context that repeats a continuation) reads inert: build the workload or do not claim a verdict.

## Publishing

14. Push the branch to the owner's fork early (it is his repo, not someone else's; the text gate does not apply to the branch). Open the pull request only after the owner approves the exact title and body, through the style pipeline and repaired.
15. Zig changes need a `CHANGELOG.md` bullet under `## Unreleased` naming the PR number, which cannot exist before the PR: open, then add it as its own commit, never a force-push.
16. `git log --format='%an %ae | %cn %ce' up/main..HEAD` must show only the owner's public identity; grep the outgoing diff for hosts, paths and addresses; no AI attribution line.

# Porting one lever onto upstream TensorFold

Use when a lever exists in our repo as `patches/engine/NNNN-*.patch`, cut against our series (so it depends on our `zig/src/cuda/ovn.zig` registry and our `zig/tests/cuda/glm_ovn_checks.zig` dispatcher), and it must go upstream alone.

## 1. Branch from upstream, never the fork

```
git -C work/up/TensorFold worktree add ../../pr/<name> -b <name> refs/remotes/up/main
```

Fetch upstream first and quote its sha in every receipt. Diff and review against `up/main`, never the fork's `main`.

## 2. Apply with the removed file excluded

```
git apply --3way --exclude=zig/tests/cuda/glm_ovn_checks.zig <abs C:/ path to patch>
```

`glm_ovn_checks.zig` does not exist upstream. Without `--exclude` the whole apply aborts and rolls back, so the tree looks untouched. Paths handed to Windows-native git must be `C:/...`, not `/c/...`.

## 3. Resolve every conflict to ONE lever

The conflicts come in one shape: `ours` empty, `theirs` a block of rows. That block carries rows belonging to OTHER levers of our series, present because our patch's context includes them. Take only the line naming the lever under port; drop the rest, or the PR carries a second behaviour and fails "one behaviour a pull request".

## 4. Re-express the read through the platform

Our code reads `cuda.ovn.on("NAME")`; upstream has no such file. Replace it with the platform's own path:

- a row in `zig/src/platform/environment.zig`: `.{ .name = "TF_GLM_NAME", .scope = .glm, .kind = .flag, .forms = "0 or 1" },` (`.flag` is upstream's dominant kind for 0/1);
- a doc row in `docs/environment.md` in the table's own voice;
- a field on the engine or lanes struct with its comment;
- one read where the other switches are read: `try @import("sys").environment.value(bool, "TF_GLM_NAME", ranks.environment("TF_GLM_NAME"), false)`.

Place the read on EVERY rank when the code path it governs runs on every rank (a release path does); a rank-0-only read diverges the ranks. Name the setting as the maintainer wrote it in the issue, not as our repo spells it.

## 5. Place the check in the runner's dispatch

Upstream has no check-file registry. GPU checks are commands in `zig/tests/cuda/main.zig`, each a `pub fn nameCheck(gpu: Gpu, ckpt, id_path, rank: c_int, world: c_int) !void` in a `*_tests.zig` file, registered as:

```zig
if (std.mem.eql(u8, cmd, "glm-name-check")) return glm_name_tests.nameCheck(gpu, try arg(rest, 0), try arg(rest, 1), try std.fmt.parseInt(c_int, try arg(rest, 2), 10), try std.fmt.parseInt(c_int, try arg(rest, 3), 10));
```

Cast rank and world with `@intCast` at the `Engine.init` call, as `glm_solo_tests.zig` does: `Engine.init` takes usize and the runner hands c_int.

Host tests are imported from the module's `test` block (`_ = @import("name_test.zig");`) and driven by a filtered step `b.step("test-glm-name-host", ...).filters = &.{"<test name prefix>"}`.

## 6. Keep files at 600 lines

A field added to `cuda_lanes.zig` at exactly 600 lines is a lean finding (`over 600 lines (1 new)`). Put the field on the engine instead and read it as `self.x.e.<field>` from the lane backend, which keeps that file's length.

## 7. Gates, in this order

- `python tools/pr_check.py --base <merge-base>`: catches lean, source length and the missing CHANGELOG line.
- lean base against head with EACH side's own `tools/zig/lean_check.py` (extract both trees, run each tree's copy, feed both outputs to `lean_new.py`); the two file counts must differ or the scan hit one tree twice.
- `zig build compile-cuda-tests` on the gate host: the only step that compiles the CUDA runner and the checks in it.
- the family host steps (`test-glm-*-host`) and the step owning the new host test.
- `zig build test test-golden`: on a host whose GPU cannot run these kernels exactly 27 test binaries fail on the pristine base too, so compare base against head by failing step set, never by pass/fail.
- `zig fmt --check build.zig zig`, `git diff --check`, and a grep of the outgoing diff for `spark`, `ots-int`, `192.168`, `/home/`, `C:/Users`.

## 8. Shipping

Archive with `git archive HEAD` only after `git status --short` is clean for the files being shipped, and verify the archive itself (`tar -xOf src.tar <path> | sed -n '<line>p'`) shows the fix: an uncommitted fix is silently absent and costs a full remote rebuild. Add the CHANGELOG bullet naming the PR number only after the PR exists, as a new commit, never a force-push.

# Port one lever onto upstream TensorFold main

Our levers are cut against our own series, so they carry two things upstream does
not have: the `cuda.ovn` switch registry and our check-file registry. Both must be
replaced, not carried, or the PR ships dead code.

## 1. Branch from upstream main, never the fork

git -C <clone> worktree add ../../pr/<lever> -b <lever> refs/remotes/up/main
    git apply --3way --exclude=zig/tests/cuda/glm_ovn_checks.zig <patch>   # C:/ paths on Windows shells

`glm_ovn_checks.zig` no longer exists upstream; excluding it stops the apply
aborting on that one path.

## 2. Resolve each conflict to ONE lever's lines

Conflicts are usually `ours` empty, `theirs` a block of rows. That block holds
rows from several of our patches, because the patch was cut after them. Keep only
the line naming the lever, drop the rest, and remove the markers:

awk '/^<<<<<<</{c=1} c&&/<LEVER>/{print} /^>>>>>>>/{c=0}' <file>

## 3. Replace the registry read with the platform read

`cuda.ovn.on("X")` does not exist upstream. The upstream shape is a table row in
`zig/src/platform/environment.zig` (`.kind = .flag`, `.forms = "0 or 1"`) plus

try @import("sys").environment.value(bool, "TF_GLM_X", ranks.environment("TF_GLM_X"), false)

Read it where the engine exists (`own.e = try engine.Engine.init(...)`), so it runs
on EVERY rank, and hold it on a field with a default of `false`, because `release`
and the lane backend also run on followers. Place the install call there, not in
the rank-0-only lane construction.

## 4. Respect the 600-line rule without reflowing upstream code

Adding a field to a file already at 600 lines is a NEW lean problem. Move the
field onto the Engine instead of the family struct, and read it from the struct
as `self.x.e.<field>`. Do not delete upstream comments to buy a line.

## 5. Register the check where upstream registers checks

Upstream has no `*_check.zig` registry; its GPU checks are

pub fn <name>Check(gpu: check.Gpu, checkpoint: []const u8, id_path: []const u8, rank: c_int, world: c_int) !void

in `zig/tests/cuda/<family>_tests.zig`, dispatched from `zig/tests/cuda/main.zig`
(one `const ... = @import(...)` next to `glm_solo_tests`, one
`if (std.mem.eql(u8, cmd, "..."))` beside `glm-solo-check`). `Engine.init` takes
`usize` for rank and world, so cast with `@intCast` as the sibling checks do. An
unregistered file never compiles.

## 6. Gates, in this order, all on a remote host

- `zig build compile-cuda-tests` (the only thing that compiles `zig/tests/cuda`).
- The family host steps by name (`test-<family>-<thing>-host`), which is what
  actually runs a new host test; a filtered step prints nothing when cached, so
  confirm with `--summary all` that it says `success`, not that it skipped.
- lean base against head, EACH SIDE'S OWN `tools/zig/lean_check.py`, then
  `lean_new.py BASE.txt HEAD.txt`; the two file counts must differ.
- `python tools/pr_check.py --base <upstream main sha>`; the one expected warning
  is the changelog line, which needs the PR number, so add it as a later commit.
- `zig build test test-golden` on the base AND the head; compare the failing STEP
  SETS (`awk '/failed command/{print root} /^[a-z][a-z0-9-]*$/{root=$0}'`), never
  the counts alone. A host whose GPU cannot run the kernels fails the same 27 on
  a pristine base.

## 7. Traps that each cost a rebuild

- `git archive HEAD` ships COMMITTED content only: a fix left uncommitted is
  silently absent from the archive and the remote build fails on the old text.
  Check `git status --short` is clean for shipped files, and verify the archive
  with `tar -xOf src.tar <path> | sed -n '<line>p'`.
- A docker image of the server does not carry `tf-cuda-test`; the check needs a
  variant image that runs `compile-cuda-tests` and copies the produced binary.
- `pkill -f <queue>.sh` over ssh kills the ssh session itself, because the command
  line contains the pattern. Match a narrower pattern or use pids.

# Port one lever from our patch series to an upstream TensorFold PR

Use when an issue asks for a lever we already carry in `patches/engine/` (the repo
`GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig`) to go upstream as its own pull request. One
lever a branch, cut from upstream `main`, never a bundle.

## Shape the maintainer expects

- Name it as the issue names it (`TF_GLM_KEEP_SEQS`, not `TF_GLM_OVN_KEEP_SEQS`), so
  our `OVN_` prefix and its registry do not leak into upstream.
- A row in `zig/src/platform/environment.zig` (`kind = .flag`, `forms = "0 or 1"`) and a
  matching row in `docs/environment.md`.
- New things default off; state in the PR whether the lever could be the default and why.

## The plumbing trap that costs a rewrite

A switch read where the server builds its engine (`cuda_native.zig`, beside
`TF_GLM_PROMPT_STEPS` / `TF_GLM_SHARED`) never reaches any other caller of
`Engine.init` - the GPU checks build engines directly and see the setting off.
Correct homes, all of which must agree:

1. `ranks.Settings` (`zig/src/families/glm/cuda_ranks.zig`): a field plus a read block
   copied from the `TF_GLM_PROMPT_PAIR` idiom (accept exactly `"0"`/`"1"`, else set
   `problem.*` and return `error.BadSetting`).
2. `Engine.init`: `e.<field> = o.settings.<field>;` right after the `e.* = .{ ... }`
   literal, and the `Engine` struct carries the field with a comment naming the switch.
3. `Fingerprint`, or ranks with different values will not be caught: a `u32` field, bump
   `layout` (23 to 24 and say which field in the comment), an entry in `Fingerprint.of`,
   the `Field` enum member, the name in `mismatch()`'s tuple, a case in `explain()`
   (its switch must be exhaustive or the runner does not compile), and the name in
   `cuda_ranks_test.zig`'s divergence list.
4. The tests drive the field, not our `cuda.ovn.fake` registry, which upstream lacks.

## Files that cap out

`zig/src/families/glm/cuda_lanes.zig` sits at 600 lines, the lean gate's limit, so a new
field belongs on the `Engine` (read as `self.x.e.<field>`), never on the lanes struct.

## The GPU check

Upstream has no `zig/tests/cuda/glm_ovn_checks.zig`. A check is a
`pub fn <name>Check(gpu: check.Gpu, checkpoint: []const u8, id_path: []const u8, rank: c_int, world: c_int) !void`
in a `glm_<family>_tests.zig`, registered in `zig/tests/cuda/main.zig` (an `@import` and a
dispatch line with `try arg(rest, N)` and `std.fmt.parseInt(c_int, ...)`), casting rank and
world with `@intCast` for `Engine.init`.

A planted control is mandatory: a case that must differ from the fresh run and fails as
planted when it does not, so the comparison is shown able to fail.

## Running it on one GB10

The 4bpw GLM-5.3-Flash snapshot digests at 163.6 GiB, more than one Spark holds, so the
check runs with `TF_GLM_LAYERS=2` (the MTP head loads separately from the layer list, so
the drafts comparison survives). Build a check image from the branch tree with the repo's
`build-image.sh` Dockerfile shape plus `compile-cuda-tests`, copying the binary out of
`.zig-cache`; the recipe image alone contains no test binary.

## Gates before the PR, and how to read them

- `python tools/pr_check.py --base <upstream main sha>`: 0 errors; its one warning is the
  CHANGELOG line, which needs the PR number and goes in as a commit after opening.
- lean, base against head, each side's own `lean_check.py`, and the two file counts must
  differ (about 7,697 base and 7,699 head): 0 new.
- `zig build test-glm-<name>-host`, `zig build compile-cuda-tests`, the neighbouring GLM
  host steps, `zig fmt --check build.zig zig`, `git diff --check`.
- `zig build test` on an x86_64 host whose GPU cannot run these kernels fails a fixed set
  of test binaries (27 on 2026-11-23); run the pristine base too and compare the step set,
  never the raw count alone.

## Pitfalls measured

- `git archive HEAD` ships only committed content: verify the archived file carries the
  fix (`tar -xOf src.tar <path>`) or the remote build fails on the old text.
- Never pkill by pattern from a command that names the target; it kills your own shell.
- Requesting the PR text: restyle through `work/restyle.py`, then repair - the model
  collapses headings and mangles backticks and identifiers, and a reversed "does not
  remember anything" almost shipped as a fact.

# Porting one ai-engine knob commit onto the upstream pin

Use when a measured OTS knob (TF_GLM_OVN_*) lives in the ai-engine trunk and must become
`patches/engine/NNNN-*.patch` in a recipe repo whose engine pin is pristine upstream.

## 0. Judge the commit by its own file list, not its neighbours

`git show --stat <sha>` and check every touched file exists at the pin. Era-bound means a
file is ABSENT, not that the commit sits near an era commit. ONE_CHUNK looked era-bound
and was not: its two new modules imported only pin modules, so the port was a field plus
two hooks. A missing file is the only hard signal.

If files are absent, park the commit in the repo's PORT-LEDGER.md with that evidence and
move on; do not "port the era" to unlock one knob.

## 1. Build the graft tree

git worktree add --detach <pN> <pin>
    for p in <all landed patches in order>; do git apply $R/patches/engine/$p.patch; done
    git add zig/src zig/kernels zig/build zig/tests && git commit -m S<n>

`git apply --3way` REQUIRES a clean index: an uncommitted stack makes it fail with
"does not match index" and roll back everything.

## 2. Apply the source commit

(cd merge-wt && git diff <sha>^ <sha> -- ':!absent-test-files' ':!absent-modules') > /tmp/x.patch
    git -c rerere.enabled=false apply --3way /tmp/x.patch

Exclude absent files up front; a single absent path makes the whole apply fall back to
direct application and lose every three-way merge. `rerere.enabled=false` prevents a stale
resolution from an earlier attempt being replayed.

## 3. Conflict rules (measured)

- **Additive** (theirs adds a field, import, test ref): union both sides.
- **Pin-evolved file** (theirs is an older era at the same site): keep the pin's shape and
graft only the knob's hunks. Signals: `propose`/`tap_rows` vs source-era `Req`; `piecesOf`
vs `drafterIdle`; `mtp_confidence` vs `together`/`multi`; L2PF `prefetch` vs `o_site`.
- **Later-era fields/modules** (`m.tiled = false`, `shared_depth_full`, `split_min`,
`cuda_kda_chunk`'s missing deps): drop them and keep whatever the pin's engine still
assigns.
- After a marker delete, re-read the region: splicing by regex can merge two fields onto
one line or duplicate a tail. Split them and recompile.

## 4. Compile-error loop, the traps hit every time

- `Arena.ptr` is `ptr()` at the pin; `Plan.init` takes a `shared` page count.
- `cp_wait` is a TEMPLATE at the pin: `cp_wait<0>()`.
- `headBlock(rows)` takes one argument.
- A local `fn mm` shadows `const mm = @import(...)`: rename the import.
- `@import` of a struct's nested members is `Mod.Struct.member`, not `Mod.member`.
- A file-local keyword clash (`resume`) needs a rename, not a cast.
- Marker deletion can DROP AN INCLUDE (`glm_index_regroup.cuh`): verify the kernel symbol
  is compiled, not merely looked up.

## 5. Gates, in the repo's own form

- `zig build check-native-cuda-host`
- `zig fmt --check zig/` over the WHOLE tree
- lean: `(cd pN && python tools/zig/lean_check.py > head.txt)` then
  `python merge-wt/tools/zig/lean_new.py base.txt head.txt`. **Never run lean_check from
  the merge tree**: it resolves ROOT from `parents[2]` and scans the wrong tree, reporting
  0 new for a tree full of findings. Two identical file counts are the tell.
- fatbins when any `.cu` changed. To debug a failure, write the exact failed argv from the
  build log into a `.cmd` that calls vcvars64 first; a bare nvcc call fails on `cl.exe`.
- 600-line rule: fold a const into its function, or move a cohesive unit to a module that
  already uses it (`ranges` -> `cuda_forward_pair.zig`), and re-export what the caller
  needs.
- Comment rule: one line, <=120 cols. Third-party attribution stays in the line.

## 6. Write the patch and prove it

Header: From/Subject, source sha, mechanism, pin adaptations, gate results.
Body: `git diff --cached --binary` (cached, so it is the patch, not the working tree).

Proof, always: a FRESH worktree at the pin, apply every patch in order, then run the four
gates. A patch cut from a working tree whose index differs from the committed stack will
fail to re-apply; rebuild it from the clean graft tree if that happens.

## 7. Land

Commit with `-S -F <msg file>` (never `-m`), dual-push (Gitea origin + GitHub mirror),
then add the PORT-LEDGER.md row: patch, knob, source sha, gates.

# Porting a recipe patch onto a newer upstream (TensorFold-style)

When a recipe's patch series (patches/00NN-*.patch) needs porting onto a newer upstream main, use this exact workflow. Context: the PARITY-CAMPAIGN-1.2.4 run (docs/PARITY-CAMPAIGN-1.2.4.md in qwen3.8-flash-next-dev) ported 17 recipe levers onto TensorFold 1.2.4.

## 1. Verify BEFORE porting (saves whole ports)

- Read the recipe patch in full; map every hunk onto the new upstream's tree.
- Grep for the MECHANISM (function bodies, contract tests, the knob's effect), not the signature - upstream may have the same feature with different names/signatures (measured: 1.2.4's `gdn_rows_late` has a different signature than the recipe's, and #1763 carried a SUPERSET of recipe 0012's folding).
- Three verdicts: fully covered (stop, record evidence piece-by-piece), partially covered (port only the missing pieces as one change), genuinely missing (port as one change).
- A stale campaign note ("upstream lacks X") can be wrong - verify against the actual tree, not a doc line.

## 2. One lever = one branch = one PR

- Fresh clone of upstream main; branch `port-<NNNN>-<name>`; note the base sha.
- Adapt the structure (new knobs go through the upstream's environment-rules pattern, NOT raw getenv; a knobs file with std.c.getenv breaks the lean gate).
- Comments: single-line <= 120 cols, no measurements/history in source (upstream's rule).
- Tests: place them where they ENTER THE TEST GRAPH (a test in a file whose only importer references it inside a function body never runs - prove discrimination with a mutant in a scratch copy).

## 3. Gates (in order)

- `zig fmt --check`
- `tools/pr_check.py --base origin/main --pr 9999` until 0 errors/0 warnings (the authoritative gate - plain lean_check counts differently and WILL under-report)
- Host suite base AND head failing lists diffed (zero new; note GPU-contention false failures when another lane holds the GPU)
- CHANGELOG Unreleased bullet with the #9999 placeholder (real number at open time, follow-up commit, never force-push)
- Kernel-contract records for changed GPU kernels (launch-record + FP64 reference; if the FP64 work can't complete, state exactly what is missing)

## 4. The toggleable series (the owner-facing artifact)

- Cherry-pick every lever's code commits onto ONE base (the release sha) in value order; resolve conflicts as the UNION of both sides for enums/rule-lists (never drop a member silently); skip-and-record if a lever won't apply.
- `git format-patch <base>..<stack>` -> renumber after the recipe's own series (0018+); one .patch per lever.
- Verify: all patches apply in order on a PRISTINE base producing a byte-identical tree; the README lists each patch's lever, gain, source branch, and conflict resolutions.
- Check the local dir against the README before committing (drift = the doc-inventory defect class).

## 5. Receipts (per upstream CONTRIBUTING)

- bench_openai.py + bench_concurrent.py --alone --serial, 256 tokens, greedy; cold prefill at 2k/8k/32k/64k exact token arrays; golden byte-equality per boot; boot lines with device-scratch; VmHWM + GPU temp per window.
- A neutral lever ships its verdict plainly ("neutral at 1-6 streams, mechanism verified") - never manufacture a percent; carrying it behind the knob is the owner's call.
- The A/B must run on the ARTIFACT that ships, both arms from the same tip, interleaved ABBA.

## 6. Fleet/GPU discipline (spark-class shared boxes)

- GPU lock: `flock -o ~/work/gpu.lock` FIFO; a lane NEVER stops the production serve speculatively (no marker heuristics - the convention isn't universal); the serve stops only inside a lock-held window and restores via the recipe's recreate path (docker run -d --name, NOT docker start).
- The restore script must match the image's recipe generation (a newer recipe's arg-check can reject the older binary's flags).
- build-br-style images need the bare engine binary on PATH (the recipe's start.sh invokes it unqualified) - fix it in the BUILDER (ENV PATH), not per-lane overlays (which rebuilds wipe).
- The tf.kernels label gate is generation-split (present vs embedded per recipe era) - keep a 5s relabel script handy.
- Ghost lock: a runner that `exec 9>lock` then forks children leaves the lock alive in any surviving child after the runner dies - scope it `( flock 9; ... ) 9>lock` or `exec 9>&-` before long children; exorcism is mv-aside + touch + kill stranded waiters.
- Checkpoint sidecars (`.tensorfold/*.sha256`) skip the one-time ~30min verify on reboots - pre-hash when a window is long.
- ATC coordination before any PR: `atc overlap --json` on a FULL clone (a blobless clone sets workingTreeUnavailable and nulls changedFiles); the laptop needs the .cmd wrapper (WSL cannot invoke npx.cmd directly).

# Cut one lever for upstream (GLM Zig repo), lane by lane

Repo: GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig. Ledger: `docs/UPSTREAMING.md` (tiers, landscape, state). Shared lane brief: `work/up/BRIEF.md` (read its last section before every lane). Clone for all lanes: `work/up/TensorFold` (origin = ashhart upstream, remote `fork`). Nothing is posted, pushed or opened by a lane; the owner approves every public word.

## Per lever
1. Pick from the ledger's Tier A. Check main FIRST (the lane's step 1): grep the code, `git log -S`, the open PRs on the same files (`work/up/pr-files.json`, `gh pr diff N -R ashhart/TensorFold`). If main has it, the finding is the deliverable.
2. Launch a `ds41-direct` lane with: the patch path, the evidence (OVERNIGHT sections), the files to read, the overlap PRs to read, branch `up/LEVER`, worktree `work/up/wt-LEVER`, gate slot `LEVER`, mutant slot `LEVERm`, and the acceptance list (branch, facts, overlap, gates, receipts-plan, DRAFT issue and PR). Upstream rules to restate: default off, setting through `platform/environment.zig` + `docs/environment.md` + a host-reachable reader function, name `TF_GLM_NAME` (drop our `OVN`), no token change, one behaviour, `BadAd84` identity, no AI line, comments one line.
3. Gate host (orca box, shared, often load 25-45 and 10-15 GiB free): `python scripts/spark-gates.py iter --name X --max-load 90 --mem-max 8 --jobs 4 --pin-repo work/up/TensorFold --pin <cut sha> --dir <patch dir> check fmt ctest lean pdl contract test`. rc 4 = preflight refused (retry), rc 2 = slot busy. A `test` step takes 20-50 min.
4. Mutants: one patch per changed line, run as ONE step: `iter ... --dir <branch> --dir <mutant> zig:test-glm-<step>` (list steps with `zig build -l`). A killer test that lives only in `test-cuda-host` gets a HARNESS patch adding a throwaway step (applied to control and mutants, never the branch). Zig 0.17 refuses unused params: keep `_ = x;` or the mutant does not build and proves nothing. Count only a named failing test or ABRT. Run the control first. Run a mutant harness ONCE to completion (a timeout kill leaves a mutant applied: check `git diff`).
5. Wiring of a setting must be host-reachable: read+assign in one small function taking an injected `get`, tested with "1", "0", unset, typo; a surviving wiring mutant is a finding (fallback: a rank-0 startup log line).
6. Receipts: images from `git archive` of the branch and of the control (same sha), tars staged on spark1, built by `build-image.sh`, run with upstream's own tools (`tools/bench_concurrent.py --alone --serial`, `bench_openai.py`, `bench_cache.py --require-cold`, model id `GLM-5.3-Flash-EXL3`, ids from `scripts/gen_ids.py`). Write the scorer (`scripts/queue-scores/scoreNN.py`) with its rules and tests and mutants BEFORE any row exists; run control boots in palindromic order (A1 B1 ... B1 A2). First boot gets a smoke run of each tool. Queue pattern: `queueNN.sh` waits on `pgrep -f <previous>.sh`, registers its EXIT trap only after the wait, and is started detached with `ssh -f -n ... 'cd ~/work/glm53-zig && setsid nohup bash queueNN.sh > ~/bench/queueNN.log 2>&1 < /dev/null &'`. Never `pkill -f` through ssh (kills your own shell); kill by pid. Replacing a script under a running bash changes nothing: kill the waiting instance and restart.
7. Public text: AI draft, restyle section by section (`work/restyle.py`, model adam-style), repair what it broke (flipped meaning, identifiers lowercased, dropped clauses, merged cells), present the exact final text inline with a list of changes, wait for approval. Numbers measured on the old stack are labelled as such until main-based receipts exist.

## Checks before any unattended queue
Dry-run every check against its real CLI: lanes checks need glm-synth's `kinds` fixture (single GPU, synthetic ckpt, base vs stack); glm-pair-check needs the runtime env only (CHUNK_SOLO replaces pairing); a queue that stops on a failing check needs proof the check is valid for that env.

# Pilot a lever into an upstream PR branch (GLM Zig repo)

Rules that bind all of it: nothing compiles on the laptop or WSL; nothing is pushed, posted or claimed before the owner approves the exact words (RULES section 14); commits are `BadAd84 <BadAd84@users.noreply.github.com>`, no AI line, one behaviour a PR, default off, upstream name `TF_GLM_NAME` (drop `OVN`), setting read through `platform/environment.zig`.

## 1. Plan from the ledger
`docs/UPSTREAMING.md` holds the tiers. Overlap per patch comes from `work/up/pr-files.json` (changed files of every open PR; exclude the append-only files: environment.zig, root.zig, cuda.zig test lists, build step lists, main.zig). Read the nearest PRs before a cut; for a PR we test, build a tree (`git merge-tree --write-tree` onto the pin, resolve by the smallest edit).

## 2. One lane per lever (`ds41-direct`, brief `work/up/BRIEF.md`)
Worktree `work/up/wt-LEVER`, branch `up/LEVER` cut from `origin/main` of the clone `work/up/TensorFold`; deliverables in `work/up/drafts/LEVER/` (facts, overlap, gates, receipts-plan, DRAFT issue and pr). Review the diff yourself when it lands.

## 3. Gates, gate host only
`python scripts/spark-gates.py iter --name N --max-load 40 --pin-repo work/up/TensorFold --pin <cut sha> --dir <format-patch dir> check fmt ctest lean pdl contract test` (top-level Windows shell, SPARK_GATES_HOST and SPARK_GATES_SSH_SOCK set). The host (16 cpus, 30 GiB) is shared: preflight refuses above load 40 or when available memory is under --mem-max (default 14 GiB). One compile at a time per lane; the base's own failure is `cli_config_test` serve --config.

## 4. Mutants (a named test must kill each)
- Control first (unmutated tree, same step). Use `iter ... zig:STEP` (one `zig build STEP`, e.g. `zig:test-glm-keep-seqs-host`), own slot name, `--max-load 90 --mem-max 7`; retry on iter rc 2 (slot busy) and rc 4 (preflight).
- A test that lives only inside `test-cuda-host` (settings-registry tests): add a HARNESS patch dir that adds one build step with a filter, applied to the control and the mutants, never to the branch.
- A mutant that does not compile proves nothing (Zig 0.17: unused function parameter; keep `_ = x;`). Test names with an apostrophe break `error: '([^']+)' failed` parsers.
- Survivor: first ask if the mutated code is dead. The common live one is the line wiring the setting to its consumer: move read + assign into a small function taking an injected `get` that a host test calls; only if impossible add a rank-0 log line and say so.
- A mutant harness killed mid-run (timeout) leaves the file mutated: run it ONCE with a timeout above the total, then `git diff` the target.

## 5. Receipts (queue93 pattern)
Images from `git archive` tars (WSL) of main and each branch at the SAME base; control boots bracket the arms in a palindromic order (A1 B1a C1a C0 B0 C1b B1b A2) and are shared by levers; upstream's tools (`tools/bench_concurrent.py --alone --serial`, `bench_openai.py`, `bench_cache.py --require-cold`, ids from `scripts/gen_ids.py`) with a smoke step after the first boot; device checks on glm-synth first, a failing branch is dropped; scorer rules (`scripts/queue-scores/score93.py`) are written before any row, with tests and mutants.

## 6. Public text
AI draft, then `work/restyle.py` section by section (2,048-token context; leave numeric tables out), then line-by-line repair (the model flips meanings, drops clauses, lowercases identifiers, merges list items, once called the checkpoint "the same as" the drafter), then present the final text inline with the list of changes. Verify every cited PR number and state with `gh pr view` first. Only after approval: `atc check ISSUE --json`, claim on `free`, post.

## 7. Queue plumbing on spark1
Chain queues with `WAIT_FOR` (a `pgrep -f NAME.sh` loop, trap registered AFTER the wait) and `ARMS`; run a second start from a copy with another name (queue92b.sh) or the first queue's wait sees it and both deadlock; replacing a script under a running bash changes nothing, kill the waiting instance by pid (never `pkill -f` through ssh: it kills your own shell) and restart; check each tool's real CLI shape in a smoke run.

# Submitting a patch to an upstream repo, by their rules

Use when a fork holds work that should land upstream. Measured on ashhart/TensorFold, 2026-10-27.

## 1. Read their rules first, in full, and again before opening

Not the first screen. The tail of CONTRIBUTING.md is where the hard limits live. Build a checklist and
treat each line as a gate:

- module line cap (TensorFold: 600 lines per source file)
- comment style (TensorFold: single-line comments, <=120 columns - a 3-line doc comment is 3 findings)
- a lint/lean checker that must add ZERO findings over the branch's pinned baseline (run it on their main
  first to record the baseline, then on every branch)
- receipts in THEIR tools' format, not yours
- "open an issue before X" where X is family, backend or arithmetic change
- coordination tool (TensorFold uses ATC) and a claim per issue
- identity: approved public name plus a GitHub noreply address; no private domain in history
- branch hygiene: one change per PR; only ever add commits

## 2. Get the tree right before believing any result

- Rebase onto their CURRENT tip, not a local mirror snapshot. Verify with
  `git ls-remote <url> refs/heads/main` and compare; a stale mirror caused a fully wrong conclusion.
- Re-materialise the worktree from the index if it may carry CRLF: their build guards patch sources at
  configure time and a CRLF anchor makes the build abort with a guard error that looks like your bug.
  Check `core.autocrlf` and count `\r\n` in tracked files before running their gates.

## 3. Gates to run on every branch, in this order

1. compile-only step (fast)
2. their test suite, and compare the FAILURE COUNT to their tip run - equal means no regression, and
   equal is the only honest statement when their own tree has failures
3. their lint/lean checker, compare to baseline
4. their formatter (`zig fmt --check`, `gofmt -l`, ...). Skipping this is what gets a PR red.
5. a real hardware or end-to-end run for anything that touches a data path

## 4. Publish

- fork: `gh repo fork OWNER/REPO --clone=false`
- push over SSH (`git@github.com:USER/REPO.git`). The gh OAuth token usually lacks `workflow` scope and
  any branch carrying `.github/workflows/*` is rejected with a confusing "OAuth App" error.
- disable Actions on the FORK before pushing, or every push emails the owner a failure
  (`gh api -X PUT repos/USER/REPO/actions/permissions -F enabled=false` then cancel queued runs). PR
  checks still run in the base repo, where they count.
- coordination: install (`npm install -g github:ashhart/ATC`), `atc doctor --json`, `atc check <issue> --json`,
  claim only on advice `free`, `atc overlap --json` before pushing.
- open the issue for arithmetic/structural work BEFORE the PR, with measurements a maintainer can re-run.
- PR body: what, why, the measurement table, what the reviewer should know (including a test of yours
  that was wrong), and link the issue so their tooling associates it.

## 5. Never force-push an open PR

Not for a review response, not for a formatting failure. A force-push deletes the commit the checks and
any reader were looking at. Add a commit. The one-commit shape is your convenience, not their rule.

## 6. Traps that produced false evidence

- A mutation A/B whose mutation does not compile proves nothing (unused local, unused parameter).
- A test only counts if the suite compiles the file it lives in. Check the test root's imports; a family
  module outside the root means your test never runs and every mutation passes.
- Compare per-arm numbers from the same client and protocol. Their bench child runs one request at a
  time by design; a pooled server answers a different question. Label both, never mix them.
