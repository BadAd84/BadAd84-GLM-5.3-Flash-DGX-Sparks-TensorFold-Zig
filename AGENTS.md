# GLM-5.3-Flash on the Zig engine - repo rules, conventions and gotchas

GLM-5.3-Flash (Mia-AiLab EXL3 4bpw) on the TensorFold Zig engine at TP=3 on spark1-3, as a development project: our
levers as patches on upstream TensorFold, their gates and measurements, and the upstream PRs. The serve that runs
today is the Python engine's (`ots/GLM-5.3-Flash-DGX-Sparks-TensorFold-Python-TP3`); the hardware is ots-infra's.

## Branches (owner 2026-11-12)

- **`production`** - the recipe the live serve runs and the target to match or beat: image
  `tensorfold-glm53:v110hunt4-fix`, the Python engine, TP=3 on spark1-3. It is the same commit the Python repo
  carries as its `production` (one sha in both repos), fetched from there and never added to here. Frozen: it changes
  only when production changes. Its history is unrelated to `main`'s: read it in its own worktree
  (`git worktree add work/prod production`), never by switching this checkout, and keep junctions out of it.
  As of 2026-11-12 the Python repo has not pushed that branch, so it does not exist here yet.
- **`main`** - the in-flight work on the modern engine: our levers as numbered `.patch` files in `patches/engine/`
  on a pristine upstream commit recorded in `scripts/config.sh` (`TF_REF`), the harnesses, the measurements, the
  docs. No engine tree is committed. It follows upstream: on each release the series is re-seated and every lever
  re-tested. When `main` matches or beats `production/SPEED-TARGET.md` at 1, 2, 4, 6 and 8 streams, it replaces
  production. The numbers this repo measured on the production serve are in `docs/speed_target.md`.
- **No private engine fork.** The series was ported from `ots/tensorfold-gb10` (branch `ovn-up`, 595e28743944) and
  `ots/ai-engine`; both are being retired (owner 2026-11-12) and are kept whole under `archive/` as git bundles
  with a restore check. The plain fork `BadAd84/TensorFold` is for upstream PR branches only.

## Layout

- `patches/engine/` - EVERY change we own on the engine, numbered, applied in file-name order to a pristine tree at
  `TF_REF` by `scripts/apply.sh`. `RECORD.md` says where each patch's text comes from, `SHA256SUMS` pins the files.
- `scripts/` - the serve and bench files, AUTHORED here and COPIED to spark1 `~/work/glm53-zig/`; the repo copy is
  the source. Serve: `serve.sh` (one rank), `zig-tp3.sh` / `zig-tp3-stop.sh` (the whole TP=3 from spark1),
  `build-image.sh`, `dist-image.sh` (copy the image to spark2 and spark3: every rank needs it). Bench: `streams.py`
  (the instrument), `turns.py` (first token of each turn of a growing chat), `bench-arm.sh` (five levels, a fresh boot
  each), `arms-file.sh` (a list of arms), `abba.sh`, `cells.py` and `rounds.py` (tables), `nsys-rank0.sh` (kernel
  profile). Stack tools: `mkpatch.sh`, `reseat-survey.sh` (how a series sits on a new upstream base, before any
  re-seat work), `catalog-check.py`. Gates: below.
- `docs/` - `speed_target.md` (the target as measured here), `BENCH.md`, the dated overnight records and
  `audit-2026-11-12/` (the lanes' full reports: the fold, what upstream v1.2.7 changed under each patch, the re-seat,
  the round-structure comparison with production, the verify-graph design). Documents of the old-pin series
  (`PATCH-AUDIT`, `PATCH-EVAL`, `PORT-LEFTOVER`, `PORT-LEDGER`, the per-port reports) were removed at the re-seat;
  they are in git history before the commit that removed them.
- `archive/` - the retired engine forks as bundles.
- `work/` - scratch, ignored: trees, tars, lane directories, queue scripts. Nothing in it is a source of truth.

## Conventions

- **On every TensorFold version bump, re-test the whole patch stack and retire what upstream absorbed (owner
  2026-11-11).** Bring the patches onto the new base first, then decide every patch with evidence: apply it, run the
  gates (exactness, the suite, the A/B), and if the behaviour and the numbers hold without it, the patch is RETIRED:
  removed from the stack and recorded as superseded, naming the upstream commit that absorbed it. A patch that no
  longer applies is NOT automatically redundant; re-seat it, then test. Never carry a patch forward because it was
  there, and never drop one without the test.
- **Everything external arrives as .patch files (owner 2026-11-11).** A contributor's branch, an upstream PR's
  commits or our own delta against a pin is carried as numbered `.patch` files in a package under `patches/`, applied
  to a pristine checkout at a recorded base sha. Each package carries `RECORD.md` (repository, branch, sha, the base
  it applies to, and whether we edited the text), `SHA256SUMS`, and an `apply.sh` whose `--check` writes nothing.
  Never merge, rebase or cherry-pick into the base tree and never edit it in place, so the gates and any A/B run
  against upstream's own source. A measurement taken on a patched tree names the base sha and the patches applied.
- **A patch enters `patches/engine/` with its receipts.** A default-path change needs its GPU cells (digests and the
  five levels); a knob needs the knob-off digests and, before anyone relies on it, the knob-on check. The header
  names the fork or upstream commit, what was left out, and the cells.
- **Every speed result is measured at 1, 2, 4, 6 and 8 streams, a fresh boot a level; a change ships only with no
  regression at any level** (fleet rule, `~/.omp/agent/AGENTS.md`). A cell that reads low is rerun A B B A
  (`scripts/abba.sh`) before it is called a loss: eight-stream rounds on this serve spread about 3% between boots.
- **Reply digests must equal the base's** unless the owner accepts a numerics change. `TF_GLM_KDA_PAD=1` is such a
  change (the KDA stack in 4 bits, as production's `TF_GLM_DENSE=q4` has it); it is the like-for-like configuration
  for comparing with production, and its digests are compared with the base's own pad digests.
- **Production is down only inside a window the owner opened.** A window stops production
  (`~/glm-v110-stop.sh`) and both GLM watchdogs (they restart production under a boot). Restore:
  `setsid nohup ~/glm-v110-start.sh`, then `sudo systemctl start glm-watchdog-system.service`.
- **Builds run on spark1, never beside a bench** (a build shares the box's memory bandwidth), and images go to
  spark2 and spark3 by `docker save | ssh ... docker load`. Images are `glm53-zig:<tag>`; those named
  `ai-engine:<tag>` are from before 2026-11-12.
- **Quantities come from a tool, with the reading.** Elapsed time and "now" are read from the box (`date`), never
  estimated: a session can sit for hours between two tool calls.
- **GPG-signed commits.** Stage explicit paths; the message goes in a file (`git commit -S -F`).
- **Current-state docs.** A retired thing is marked RETIRED in one line; a "current" claim carries a date.

## Contributing upstream (`ashhart/TensorFold`)

The same text is in the three serve repos (GLM Zig, Qwen3.8 Flash Next, DeepSeek-V4.1). It was written 2026-11-12
from upstream `main` at `000b534a2`: `CONTRIBUTING.md`, `AGENTS.md`, the README's "Contributing with agents",
`docs/atc/SKILL.md`, `docs/pr/SKILL.md`, `docs/recipes/SKILL.md`, `.github/pull_request_template.md` and
`tools/pr_check.py`. Those files are the rules and they move: fetch upstream and read them at its tip before each
contribution (`git fetch https://github.com/ashhart/TensorFold.git main`), and when they change, change this
section in all three repos. The order of work is also in `.omp/RULES.md`, which omp carries on every request and
gives to subagents; they do not get this file, so hand them this section when upstream work is delegated.

**The order of work. Nothing is edited for upstream before step 3 returns a claim.**

1. **An issue first, always.** Upstream requires one before a new model family, backend or arithmetic change, "so
   we can agree on its gate" (a gate we proposed is not an agreed one). We open or find one for every change,
   because the ATC claim, the public session and the pull request's `Issue:` line all hang off an issue number.
   Blank issues are off: use the template that fits (`bug`, `feature`, `performance`, `proposal`). Look at the
   [agent radar](https://tensorfold.dev/atc) and `atc board --json` before choosing or opening one.
2. **Check it:** `atc check ISSUE --json`. Read `complete` first: `false`, or advice `incomplete`, means stop and
   resolve the missing coverage. Then by advice: `free` goes to step 3; `yours` means continue (`atc status --json`,
   `atc renew ISSUE`); `proposeInstead` means someone holds it, so offer to `pair`, `split` or `review` and wait for
   `accepted`; `takenOutside` or `notOpen` means do not start. A `duplicateAttempts` entry means others already have
   open pull requests for it: never add a competing one.
3. **Claim it:** `atc claim ISSUE --json`, and start only when it returns `claimed`. A successful new claim starts
   an anonymous public session on the radar and returns its `session` number: keep that number, do not start a
   second session, and check that `publication` is `public` (`unavailable` means the public update failed). For
   work already ours, `atc start ISSUE --json`. A draft pull request of ours that says `Fixes #ISSUE` also counts as
   the claim. The limit is 25 claims a user.
4. **While working:** `atc pulse ISSUE SESSION working --json` before each five-minute check-in expires
   (`reviewing` or `blocked` when that is the truth), and only while an agent is really working: never pulse for an
   idle one. `atc who FILE --json` after editing a file others may touch.
5. **When work stops:** `atc land ISSUE SESSION --json`; `atc release ISSUE --json` when we give the issue up.
6. **Before the pull request, and again after every push:** rebase on current `main` first, then
   `atc overlap --json` last. Every `"conflicts"` entry is resolved (coordinate, narrow or rebase) and the result,
   its time and its base go in the description. A conflict whose only shared file is `CHANGELOG.md` is the ordinary
   case; say so.

**What a pull request is.**

- One behaviour, cut from upstream `main` (its only branch), on a branch of the plain fork `BadAd84/TensorFold`. If
  the one-sentence description needs "and", split it; stack dependents as drafts and say what each sits on.
- From these repos a lever goes up as its patch re-seated on upstream's tip, alone. Review and diff it against
  upstream `main`, never the fork's `main`, and quote that sha.
- Anything new defaults off, and a switch arrives with the code that reads it and a measured benefit. A new setting
  is read through `platform/environment.zig` (a rule in its table, then `read(T, name, default)`); a new `getenv`
  is a lean finding.
- Upstream takes no lossy weight or cache format and no mode that changes output tokens, even opt-in. Drafts are
  never turned off on an advertised path.
- Code is written for TensorFold, not copied from another engine; anything from elsewhere names its source and
  licence in the pull request.
- The template is filled on the pushed head, every line: a line that does not apply says "n/a" and why, and only
  the sections the template says to delete are deleted. `Fixes #N` only when it completes the issue, else
  `Refs #N`. An optimisation added, finished or dropped updates that family's cell in
  `docs/optimization-ledger.md`. Zig changes carry a bullet under `## Unreleased` in `CHANGELOG.md` naming the pull
  request (`tools/pr_check.py --pr NUMBER` looks for it).

**Checks on the head, as upstream's CI runs them.**

- `python3 tools/pr_check.py --base origin/main --pr NUMBER`: new lean and source-length findings are errors.
- Lean, base against head with the same checker, both counts reported and 0 new: the commands are in
  `docs/pr/SKILL.md` step 5 (a worktree at the merge base, the head's `lean_check.py` copied into it, then
  `lean_new.py`). One checker run twice from one tree always reads 0 new: the two file counts must differ. Source
  files stay at or below 600 lines; comments and docstrings are single lines of at most 120 columns and carry no
  measurements, history, reviewer or pull request references.
- `zig build test test-golden` (`test-cuda-host` is a subset, not a substitute), `zig fmt --check build.zig zig`,
  `git diff --check`. Each new test is shown failing before the change and passing after, and is reached by the
  step that was run.
- A new or changed GPU kernel registers with the kernel contract (`docs/kernel-contract.md`) with a planted control
  that fails as planted, and the pull request posts each backend's `SUMMARY` line and exit status.
- Read the head's CI: fix what we introduced, label the rest inherited, flaky or infrastructure. Check runs for a
  fork pull request live in the base repo.

**Receipts, for a change that can reach inference.**

- Main against our branch on the same machine, checkpoint and settings, posted before asking for a run on
  upstream's machines; token hashes equal on the default path. A loss is fixed or shown to be noise first.
- Exactness contracts at the same checkpoint and settings: drafted equals `"draft": false`, a resumed prompt equals
  a fresh one, concurrent equals solo, cancellation and reset leave the next request valid
  (`tools/bench_concurrent.py ... --levels 1,4 --alone --serial`).
- Decode before and after with `tools/bench_openai.py`; prompt speed cold with `tools/bench_cache.py --require-cold`
  and `--prompt-cache-gib 0`, at 2k, 8k, 32k and 64k where admitted. Alternate the arms when the difference is a
  few percent. No slower than main at one stream and at the widest admitted; with `--drafter` no slower than
  without it.
- Name the commit, Zig and toolchain, GPU, OS, RAM class, checkpoint revision and request parameters; attach the raw
  results. Platforms are named by chip or target, run and not run: unrun is not passed.
- A changed reduction order needs an independent FP64 reference for each affected projection class, worst
  per-column difference reported, prompt and decode separately.

**Identity, privacy and the branch.**

- Author and committer are the owner's public identity (`BadAd84`, the GitHub noreply address), commits signed.
  Check every outgoing commit: `git log --format='%an %ae | %cn %ce' origin/main..HEAD`. No AI co-author or
  "Generated with" line: a pull request whose commits carry one lands as new commits and shows as closed.
- No private email, machine name, internal host, local path, key or confidential data in the diff, the commits or
  a receipt. Read the whole outgoing tree and history before pushing.
- Never force-push a branch under review, not to follow `main` and not to fix CI: add a commit. Maintainers rebase
  at landing.

**What needs the owner (fleet rule, `~/.omp/agent/RULES.md` section 14).** Upstream's own text says creating an
issue, sending a pull request and uploading results need the human's authorisation. Here: issue text, pull request
titles and bodies, and every comment go through the style pipeline and are posted only after the owner has approved
the exact text. A request from the owner to work on an issue covers the ATC claim, pulses, landing and release for
it (ATC posts only the typed command). `--github-name` is used only if the owner says so; sessions are anonymous
otherwise.

**Mechanics on this workstation (each cost a round trip).**

- ATC needs Node 22.16 or later, git 2.38 or later and an authenticated `gh` (`BadAd84`): it runs on the laptop, not
  on a Spark. Install or upgrade to the version upstream's README names (0.9.4 on 2026-11-12):
  `npm install -g github:ashhart/ATC`; `atc doctor --json` on a new setup. Always pass `--json`.
- It needs a FULL clone of upstream: a blobless one reports `workingTreeUnavailable` and every conflict as
  `unknown`. WSL bash cannot start `npx.cmd`: run ATC from a `.cmd` file through `cmd.exe /c`.
- Push to the fork over SSH (the HTTPS token lacks the `workflow` scope), and keep Actions disabled in the fork.
- The skills hold the step-by-step: `contribute-pr-to-tensorfold-main`, `run-atc-overlap-for-tensorfold-prs`,
  `tensorfold-upstream-pr-gate`, `gate-public-pr-text-on-owner-approval`.

## Gates

Run on the applied tree, from WSL on the workstation:

- `scripts/gates.sh TREE NAME` - `zig build check-native-cuda-host`, `test-cuda-host` (the gate that matters for a
  GLM patch: the other two compile none of the family's host tests), `compile-cuda-tests` (the GPU test binary; a
  check nothing imports from `main.zig` is otherwise never compiled), the standalone host steps (`test-glm-ring-host`,
  `test-glm-logprobs-host`, `test-glm-onepass-order-host`, `test-rows-host`) and `zig fmt --check zig/`. It runs on
  a copy of the tree under `~/gt/` on the WSL filesystem.
- `scripts/gate-names.sh BASE HEAD` - failing test NAMES of two runs compared, never counts.
- `scripts/lean.sh BASE_TREE HEAD_TREE` - the lean gate as upstream's CI runs it: base against head, 0 new problems,
  each side scanned by its own copy of `tools/zig/lean_check.py`. A comment line followed by a comment line is a
  problem, and so is a file past 600 lines.
- `scripts/check-patch-packages.sh` - every package dir with `.patch` files has `RECORD.md` and `SHA256SUMS` and the
  hashes match.
- The image build on spark1 is the only gate for `.cu` and `.cuh`: nothing local compiles a kernel.

## Gotchas (each cost real time)

- **Do not gate a tree on `/mnt/c`.** There 26 upstream tests that need POSIX file modes, symlinks or FIFOs fail on
  the pin itself, and under load the test binary that spawns child processes hangs (three runs sat until killed).
  `scripts/gates.sh` copies the tree to the WSL filesystem for that reason.
- **A change that widens an invariant has dependents its own diff does not touch.** An earlier port let a prompt step
  start at any row and left the pairing check and `State.ready` in upstream's form; a paired step then wrote past the
  index rings and replies on long prompts were wrong with no error. Read every caller and every guard of what a patch
  widens, and keep a host test beside each.
- **A repair belongs inside the lever it repairs.** The series is one lever a patch with its repairs folded in, so every
  prefix compiles and is correct alone; an arm tree cut from the middle of it takes whole patches only.
- **A check that prints "none missing" has to be shown failing first.** The first catalog check here matched nothing.
- **Tests taken from the fork can encode the fork's 4,096-row prompt chunk** (ours is 2,048): a prompt of 2,088
  tokens is "one chunk" there and refused for its length here.
- **`SHA256SUMS` and the patches must be LF** (`.gitattributes` pins them): a checkout under `core.autocrlf` otherwise
  makes the package gate report every patch as unlisted.
- **A queued script is replaced atomically** (`scp` to `stage/`, then `mv`): a waiting bash holds the old file.
- **Every image must be on all three boxes before a bench uses it.** `scripts/build-image.sh` builds on spark1 only;
  `scripts/dist-image.sh TAG` copies it to spark2 and spark3. Without that rank 0 waits for ranks that cannot start and
  every boot of the bench fails after five minutes.
- **Do not run Zig tests or builds in place on `/mnt/c`.** A hung test there left two real files of 100 GB and 70 GB
  in a cache directory and filled the disk; the WSL disk file (`ext4.vhdx`) only grows, and a full C: puts it
  read-only. `scripts/gates.sh` copies to the WSL filesystem.
- **Production and the Zig serve cannot share the GPUs.** Stop production (`docker rm -f glm53-flash-tf samplers
  pwcap`) before a Zig boot and restore it with `setsid nohup bash ~/glm-v110-start.sh`; both GLM watchdogs stay
  stopped for the whole window.
- **`TF_GLM_L2PF`, prefill and fill rows are not environment switches on this engine** the way they are in
  production's file: setting production's values killed every boot of that arm.
- **The lanes' full reports are in `docs/audit-2026-11-12/`**; a status table quotes them, it does not replace them.
