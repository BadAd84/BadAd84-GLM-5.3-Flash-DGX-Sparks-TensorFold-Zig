---
name: submit-ots-patch-as-miaai-recipe-pr
description: "Use when upstreaming an OTS patch to a MiaAI-Lab recipe repo (GLM-5.3-Flash or Qwen3.8 Flash Next TensorFold): what the maintainer checks, package, verify, owner approval, post, answer reviews."
---

# Submit an OTS patch as a MiaAI-Lab recipe PR

Repos (`R` below):
- `MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold` - packages in glm5.3-flash-dev `upstream/{recipe,glm}-pr-*/`,
  production patches `scripts/glm53/v110/ots00NN-*.patch`.
- `MiaAI-Lab/Qwen3.8-Flash-Next-Single-DGX-Spark-TensorFold` (Zig engine since 2026-10-08) - packages in
  qwen3.8-flash-next-dev `upstream/zig-pr-*/`, stack trees on spark6 `~/work/zpr*`.
Fork: `BadAd84/<repo>`. Upload script (GLM repo): `work/hunt/UpstreamBatch/upload_batch.py`; review replies:
`work/hunt/UpstreamBatch/` + `upstream/post_review.py` (`--up <repo>/upstream` selects the Qwen packages).

## A. What the maintainer checks (first full review, 2026-10-11, all 17 Qwen PRs) - meet it BEFORE posting
The maintainer triages with Claude Code and leaves one comment per PR. Every PR got the same blocker plus specific
findings. Pre-empt all of these in the package and the body:
1. **GPU exactness with the recipe's own tools**: `tools/exact.py` (drafted, concurrent), `tools/exact.py --pad 3k`,
   `tools/toolcheck.py`, `tools/needle.py` (~200k tokens), and a SAMPLED run in the form of their PR #4
   ("recipe sampling, seed 1234 ... `bench_draft` shas equal the baseline") - note `bench_draft` / `exact_prefill` are
   NOT files anywhere; run the forms (recipe sampling from config.sh, seed 1234, reply shas vs stock; cold greedy
   8k/32k/120k + `"draft": false` + a resume) and say so. Run stock and the whole stack in the same session; quote
   the verdicts in every body. Their node is often busy: if we do not run these, the PRs wait. (GLM batch 2026-10-30:
   `upstream/batch-2026-10-30/gb10_a1.sh` runs all of it, stock main against the batch, under the per-patch harness's
   conventions; `upstream/fill_a1.py <run dir> <upstream dir>` fills the `[[gb10-a1: ...]]` placeholders from the run
   folder - all-or-nothing, and its ttft source is the timed boot's JSON, not the measure log's truncated cases line.)
2. **Merge order**: stacked patches merge strictly in number order; every body says which earlier PRs it needs and
   that each prefix of the stack passes `zig build test` (prove it: build every prefix).
3. **Memory**: the startup estimate and the low-water MemAvailable at the recipe's defaults (Qwen: 8 x 262,144, fp8
   KV, vision on = the defaults) for any change that allocates (scratch, copies, windows, chunk rows). Add the cost
   to `config.sh`'s `mem_need_gib` when it is fixed. Tick the memory box only with these numbers.
4. **Settings are strict**: a malformed or out-of-range env value must stop the start with the setting named (or warn
   and take a documented fallback) - never silently become 0 / 1 / the default. Validate bounds that feed arithmetic
   (e.g. `(ahead+1)*rows` overflow). Two settings that only work together: both or neither, else error. Values must
   be ASCII digits, not just `int()`-parseable.
5. **Fallbacks, not errors**: a fast path whose preconditions do not hold (width not a multiple of the tile, stride
   alignment, buffer sizes, shared memory over the opt-in limit, a checkpoint without the needed head) falls back to
   the stock kernel/path. One predicate decides both the fallback and the hard check. No struct left with null
   pointers on a fallback.
6. **Off means stock**: a feature's `=0` must issue the ORIGINAL launch sequence verbatim (prove with a host test that
   records launches), not a refactored equivalent.
7. **Tests for every invariant the claim rests on**: row invariance across window widths, reset completeness of
   pooled/recycled state (a host gate that classifies every field), NaN/inf/+-0/tie ordering, real-engine (not Toy)
   checks for scheduling fixes, error-path frees (fail every allocation in turn). Each test has a mutant that fails it
   (exit code); a surviving mutant is either a dead check (delete it) or needs a stronger test - show which.
8. **Fragile reproductions** (hand-written kernels repeating Triton's SASS) get a boot-time self-check against the
   loaded kernel set with a fallback on mismatch.
9. **Tool/artifact versioning**: generated artifacts (overlays) keyed by checkpoint revision AND tool hash, with a
   checksum verified at prepare/start.
10. **RigMark + TTFT**: the owner wants RigMark (alexellis/rigmark, extra body as on its published card) and
    client-measured TTFT stock-vs-ours tables in every body (Qwen: Python release, Zig release, + earlier batches,
    + this batch). Report cells that moved the wrong way and settle them with a re-run.

## B. Choose what to send - inventory EVERY patch production runs first
- One line per production patch: in this batch / already upstream (which PR) / held (why) / not upstreamable (measured
  reason). Keep it in `upstream/BATCH-<yyyy>-<mm>*.md`. A fix the recipe needs to run on our platform goes in the same
  batch as any feature that only works there. A PR text that says "we also run X" means X belongs in the batch.
- Provenance before framing: whose idea / whose code (git log, the upstream PR's created_at, session logs); improve a
  merged design rather than compete with it; credit in CREDITS.
- Engine vs recipe: the recipe ships the Flash Next CUDA backend as its own patches on a pinned TensorFold commit;
  upstream TensorFold (`ashhart/TensorFold`) has no `cuda_*.zig` Flash Next backend. Core changes (`core/lanes/*`,
  `core/prompt_cache.zig`, `core/lane_host.zig`, `server/*`) could ALSO go to TensorFold main, but it is ~700+ commits
  past the recipe's pin: porting, not reposting.
- A patch is in a batch only once its per-patch GB10 confirmations are in at all five levels (owner: one batch, posted
  together); a starred loss cell keeps it held, named with the confirmation run that settles it.
- Bundling (owner, 2026-11-02): where two PRs target the same thing, bundle them - measured pairs: one mechanism with
  a hard dependency (prompt ids + literal prompts through them), one request-path stage measured as a single arm
  (prestage ids + prepare host). Keep apart: a parallelism change beside a bit-identical kernel regroup (the regroup's
  review value is "only the grouping changes"), and engine patches beside recipe shell scripts.

## C. Package (once per patch)
- `pr.diff` against upstream main: `patches/00NN-<name>.patch` (applies in order on the pin; upstream wording, no OTS
  names), its check tool/CLI, README rows (patch table + settings), CHANGELOG `## Unreleased`, CREDITS
  `by [BadAd84](https://github.com/BadAd84)`. Clone with `-c core.autocrlf=false`.
- Strip from the measured code: experiment switches, mutant switches, OTS names; rename env knobs to descriptive
  `TF_FLASHNEXT_*`. Say in Testing what was cut ("the patch is the measured code with ... taken out").
- Build the clean stack image from the packaged patches and A/B it against the merged build it came from (golden 6/6,
  decode matrix, copy/prefill): the shipped artifact is what is timed.
- `PR.md`: internal header, `---`, `**Title:**`, `**Body:**`. `mutants.sh` judged by exit code; if it needs the GPU
  lock, strip any nested `flock` when called from inside a held lock (deadlock).
- Placeholders `[[...]]` until measured; `#[00NN's PR]` for cross-references. upload_batch.py fills ONLY numbered
  `#[00NN's PR]` / `#<00NN PR>` forms: a named one (`#[the 4096-row setting's PR]`) must be filled by hand after
  posting - grep every live body for `#[` afterwards.
- Check tools set `sys.dont_write_bytecode = True` and nothing runs inside a package's `files/` tree: a probe run
  beside a tool once put a 57 kB `.pyc` into 0136's pr.diff. `upstream/compile_batch.py` now refuses any binary patch,
  `__pycache__` path or `.pyc` in a pr.diff.

## D. Re-verify on the day
- `gh api repos/$R/commits/main`, open PRs and their `patches/` files, the last patch numbers.
- Fresh `--depth 1` clone; `tr -d '\r'`; `git apply --check` of every pr.diff in order. Trailing-whitespace warnings
  inside nested `patches/*.patch` are expected: never `--whitespace=fix`.
- `bash -n`, `py_compile`, shellcheck base vs patched (no new findings; portable 0.10.0 in `C:\Users\Adam\tools\shellcheck`).
- The repo's `bash scripts/check-python.sh` (pyflakes, undefined names): py_compile does not catch an undefined name.
- **Run EVERY package's check tool on the FULLY STACKED tree too** (main + every batch patch in order), not only on its
  own patch: a later patch changes shapes an earlier tool checks. 2026-10-30: 0134's agreement section evaluated the
  whole agreed list in engine.py and crashed on 0135's / 0137's additions (103 / 104 on the whole batch), unseen
  because each tool had run only on its own patch.
- Leak scan: `grep -niE "ots-int|192\.168|spark[0-9]|hillson|\bOTS\b|ots-infra|glm5\.3-flash-dev|qwen3\.8-flash-next-dev|/home/adam|C:/Users" pr.diff` empty.
- Every text that names the batch names ALL of it; overlapping README/CHANGELOG/CREDITS hunks: "whichever merges second, I rebase".

## E. Body: `.github/PULL_REQUEST_TEMPLATE.md` exactly
Description and Motivation / Related Issues / `---` / Testing / `---` / Checklist (7 boxes; tick only with evidence).
State: whether bits change and how checked; the setup (boxes, TP, engine version); what was NOT tested; dependencies.
Numbers only from the ledger/campaign doc, attributed to the build they were measured on. Plain English, no em dashes.

## F. Owner approval gate
`python upstream/compile_batch.py [--batch TAG]` (fails on `[[...]]`, a missing file or a build artefact in a pr.diff).
Show every title and body in chat (shared blocks once). Post NOTHING until the owner says send.

## G. Post
GLM repo: `python3 work/hunt/UpstreamBatch/upload_batch.py --dry-run <upstream dir> <ORDER file>` first, then the same
without `--dry-run`. Per package it branches `ots-<dir>` off upstream main in a scratch clone of the fork, applies the
`pr.diff` (each applies ALONE on main), one signed commit, pushes, `gh pr create --base main --head BadAd84:ots-<dir>`,
then fills every `#[0133's PR]`-form cross-reference from the created numbers (the ORDER file is number order, so
0132+k maps to package k; named forms print a WARNING for a hand fill). Verify: open, one commit, no `#[` left. Record
PR numbers in `upstream/BATCH-*.md` (and the watchlist).
Measured gotchas (2026-11-02): WSL's git does NOT read the Windows `~/.gitconfig-github` includeIf, so the script sets
the clone's identity itself (noreply `598804+BadAd84@users.noreply.github.com`); WSL's `/usr/bin/gh` is a separate
auth from Windows gh.exe (check `gh auth status` where you run it); a `[boot]`-style bracket in a title is styling,
not a placeholder (the placeholder check is `[[` / `#[`).
GitHub shows the commits as Unverified (`bad_email`) since 2026-10-25, and the owner accepted that on 2026-11-02:
the noreply identity is not a UID of the signing key until the offline primary key adds it, and the gmail address is
against TensorFold's PR rules. Do not change the identity.

## H. Answering a review
- Fetch every comment (`gh api repos/$R/issues/<n>/comments`, `.../pulls/<n>/comments`, `.../pulls/<n>/reviews`) and
  tabulate findings per PR. Every finding gets a FIX with a test + killed mutant, or (only for questions) a measured
  answer. Nothing argued, nothing waived.
- Keep the stack consistent (a fix to patch N moves later context); build and `zig build test` every prefix; rebuild
  the clean stack; run section A.1's tools on it and byte-compare against the posted image.
- Draft replies in `upstream/REVIEW-ROUND-<n>.md` (one `## #N title` section per PR, one paragraph per finding);
  GPU numbers as placeholders until the final image's run fills them. One complete reply + one review commit per PR
  (owner's choice), not an evidence comment first.
- Owner approves; then `post_review.py --dry-run --round="Review round N"` and the real run: a NEW signed commit on
  top of each PR branch, never a force-push (RULES section 8).
- Lane budget: a fix round over 15+ PRs exceeds one agent's request budget; plan a handover file (stack paths, what is
  done / not done, compile-risk notes) and continue with a fresh agent.

## I. After the first merge
Rebase the rest onto the new main (the one allowed force-push, announced "rebase onto <sha> only, no content change"),
renumber if the maintainer did, re-run section D. If the maintainer rewrites our patch into his series, port onto his
version and drop ours.
