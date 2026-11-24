---
name: merge-a-lane-diff-into-a-moving-main
description: "Merge a lane's diff into a fast-moving main when both sides appended fixtures or rewrote the same file; merge, never rebase or force-push."
---

# merge-a-lane-diff-into-a-moving-main

one skill: merge a lane's diff into a fast-moving main

Merged from 6 skill(s): merge-a-lane-diff-into-a-moving-main, merge-fast-moving-upstream-main-into-pr-branch, merge-moving-upstream-main-into-pr-branch, merge-moving-upstream-main-into-pr-branch-bare, merge-mutant-manifest-by-id, merge-two-lanes-that-append-fixtures.

# Merging a lane's diff into a moving main (project-harness campaign)

Use when a lane's clone must land on main and `git apply --3way` leaves conflicts in files where BOTH sides
appended content (test modules, `MANIFEST.toml`, contract end-sections), or where one side rewrote a region
the other also touched.

## 1. Apply and enumerate

```bash
git -C <clone> diff <lane-base-sha> <lane-head> --binary -- . ':!tests/mutants/run.py' > work/lanes/<lane>.diff
git apply --3way work/lanes/<lane>.diff      # stages clean files, leaves UU on conflicts
git status --short | grep '^U\|^AA'
```

## 2. Resolve by shape, not by hand-splicing

- **Additive block conflict in one file** (both lanes appended fixtures at different anchors): the naive
  "ours then blank then theirs" concatenation cuts through whichever side ended mid-item. Instead:
  1. `git show HEAD:<path> > work/ours`, `git show <lane-ref>:<path> > work/theirs`,
     `git show <base>:<path> > work/base`.
  2. `git merge-file --union -p ours base theirs > work/union`; then check for duplicated definitions
     (`grep -o 'async fn fixture_[a-z0-9_]*' | sort | uniq -d`) and a `cargo fmt --all --check` syntax check.
  3. If union still breaks (interleaved macro boundaries), take OURS whole and append the other side's block
     extracted by its own section marker (`grep -n '^// ---- lane ' theirs`), and splice any single
     modified function by locating `async fn NAME` back to its doc comment and forward to the first `\n}\n`.
- **Both sides changed the same function**: prefer the newer design and delete the superseded helper (e.g.
  the sealed git runner replaced the import's own env/config lists) rather than keeping both.
- **Field/default lists** (`Seams`): keep both sides' entries in declaration order and in `Default`.
- **Generated files**: `prompt_pack/pack.toml` sha is recomputed after resolution (`python3 work/packsha_fs.py`),
  a mutant patch whose anchor moved is regenerated from the merged file with `difflib.unified_diff` and the
  header `diff --git a/<p> b/<p>` plus the `---`/`+++` lines (a patch missing those is "corrupt patch").

## 3. Verify on the merged tree, then commit

```bash
python3 work/loaders.py                      # manifest integrity, duplicate names
cargo fmt --all --check
# one remote run: compile, gate, and a handful of the lane's own pairs
python3 tools/remote.py --lane <new-lane> --timeout 5400 -- bash -c \
  'cargo check --workspace --all-targets 2>&1 | grep -E "^(error|warning)" -A 8 | head -40; echo CHECK_DONE; bash tools/gate.sh; python3 tests/mutants/run.py --kinds stub,stub-linux --only <pairs> | tail -12'
```

Then stage only what you resolved (`git add -- <paths>`), commit with `git commit -S -F work/msg.txt`, and
immediately `git show --stat --format='%h' HEAD` to confirm the commit carries only what the message says
(a staged merge is swept in by a bare `git commit -F`).

## Pitfalls measured in this campaign

- `git apply --3way` needs the base blobs; if the lane lives only in another clone, `git fetch <clone> HEAD:refs/lanes/<x>` first.
- Never run two `tools/remote.py` invocations on one lane name: the second removes the first's container.
- Fixture files touched by two lanes: 355 fixtures in one file after a union merge is normal; duplicated
  `fixture_` names are the tell that the union went wrong.
- A lane's own "gate green" can be void if it ran `remote.py` from the wrong checkout; trust only runs from the clone.

# Merge a fast-moving upstream main into an open PR branch

Use when a PR branch must take upstream main by a MERGE commit (never a force-push), main lands batches faster than a
full gate run, and the recurring conflict is one shared file (TensorFold: `CHANGELOG.md`, top of `## Unreleased`).
GitHub runs no `pull_request` workflow while a PR conflicts, so the merge has to land inside a gap between batches.

## 1. Build the merge with plumbing, in a bare repo (no checkout, no compile)

```
git init --bare work/signmerge.git && cd work/signmerge.git
git fetch https://github.com/<fork-owner>/<repo>.git <pr-branch>:refs/heads/prhead
git fetch https://github.com/<upstream>/<repo>.git main:refs/heads/up
git merge-tree --write-tree --name-only prhead up     # line 1 = tree, then conflicted paths
```

- Assert the conflicted set is exactly the expected file. Anything else: stop and resolve by reading the code.
- Resolve by construction: take main's blob of the file and insert our bullet (first under `## Unreleased`), then
  `git hash-object -w --stdin`, and with a temporary `GIT_INDEX_FILE`: `git read-tree <tree>`,
  `git update-index --cacheinfo 100644,<blob>,CHANGELOG.md`, `git write-tree`. Delete the temp index.
- Check: no `^<<<<<<< ` in the tree (`git grep`), `git diff --name-only up <tree>` equals the PR's own file list, and the
  both-sides file list (`comm -12` of `git diff --name-only <merge-base> prhead` and `... up`) matches what the commit
  message states. Re-derive every count in the message; put the new main sha in it.

## 2. Sign at the TOP LEVEL (native git), not in a script file

`bash script.sh` runs inside WSL: wrong git, wrong gpg, `gpg: signing failed: No secret key`. Run inline:

```
export GNUPGHOME=C:/Users/Adam/AppData/Roaming/gnupg GIT_AUTHOR_NAME=... GIT_AUTHOR_EMAIL=<noreply> GIT_COMMITTER_NAME=... GIT_COMMITTER_EMAIL=<noreply>
S=$(git commit-tree -S <tree> -p <prhead-sha> -p <main-sha> -F C:/.../msg.txt)
git log -1 --format='%G? %GK %T %P' $S      # G, same key as the PR head, same tree and parents
```

## 3. Gate so it can keep pace

- Gate ONE merge fully on the build box (identity checks, fmt, lean base vs head with each tree's own tool, pr_check,
  the pinned-fixture and environment tests first; the long host suites after).
- When main moves before the gate ends, rebuild (step 1) and apply the carry-over criterion instead of restarting:
  `git diff --name-only <old-main> <new-main>` shares NO file with the PR's files except the changelog, AND the new
  merge tree differs from the gated tree by exactly that list, the non-changelog files being main's own blobs. If it
  holds, the gated results carry over: push now, then run the full gate on the pushed head and report it.
- Have the gate agent compute the expected tree independently on the box; equal tree ids are the cross-check.

## 4. Push as a fast-forward, over SSH

```
git ls-remote <upstream> refs/heads/main            # must still equal the merge's second parent
git ls-remote <fork> refs/heads/<pr-branch>         # must still equal the first parent
export SSH_AUTH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg
git push git@github.com:<fork-owner>/<repo>.git $S:refs/heads/<pr-branch>
```

HTTPS is refused when the merge carries main's workflow-file changes: `refusing to allow an OAuth App to create or
update workflow ... without workflow scope`. That is not a content rejection; use SSH.

## 5. After the push

- `gh pr view N --json mergeable,mergeStateStatus`; fork-PR workflow runs sit in `action_required` until a maintainer
  approves them.
- Do NOT keep re-merging unasked: each push notifies reviewers and stays conflict-free only until main's next batch.
  Rebuild (about a minute with the script) when the maintainer is ready to run CI or asks.
- A stacked PR on that branch re-seats with one command onto the pushed head; keep its re-seat as a script.
- `verified: false, reason: bad_email` on GitHub means the signing key has no UID for the committer address; it is an
  account/key matter for the owner, not a defect of the push.

# Merging two lanes that both append fixtures to one test file

Symptom: after `git apply --3way <lane>.diff`, a `server_tests.rs` / `team_review_tests.rs` conflict resolves into a file whose brace depth is one higher than either side, and `cargo fmt` or `cargo check` reports an unclosed delimiter at some line far from the seam. The cause is that both lanes appended at nearly the same anchor, so the conflict boundaries fall INSIDE a macro or a fixture, and concatenating ours+theirs cuts both.

Do not hand-splice. Rebuild the file from two whole versions:

1. Extract the three versions: `git show HEAD:<path> > /tmp/ours.rs`, `git show <lane-head>:<path> > /tmp/theirs.rs`, `git show <merge-base>:<path> > /tmp/base.rs`. Compare brace depth per file (count `{` minus `}`, skipping `//` lines): ours and theirs should agree; the broken merge will differ by exactly one.
2. Take OURS as the base of the rebuilt file (it is the tree you already gated).
3. Find the lane's ADDED region in theirs: either a section marker comment the lane wrote (`grep -n '^// ---- ' /tmp/theirs.rs`) or a `git diff base theirs -- path` whose single hunk's `+` lines are the additions.
4. Append those added lines to ours at end of file (a Rust test file allows a new top-level `fn` there), or insert before the marker block they belong to.
5. For any non-fixture change the lane also made in that file (a fixture it modified), transplant the whole function: locate `async fn <name>` in both files, walk back to the doc-comment start and forward to the first line that is exactly `}`, and swap the block.
6. Prove it: `cargo fmt --all --check` (a syntax error shows as an unclosed delimiter), then grep that each expected `async fn fixture_...` name appears exactly once, then run the gate.

Alternative when the lane's diff has a single hunk: `git checkout HEAD -- <path>` then `git diff <base> <lane> -- <path> > lane.diff` and `git apply --reject lane.diff`, then read the `.rej` and append its `+` lines. Both routes end with the fmt check and the one-copy-per-fixture grep.

Never resolve this class with a naive both-sides concatenation: it type-checks the markers away but leaves two half functions, and the resulting error points at the wrong line.

# Merge a fast-moving upstream main into a PR branch without a checkout

Use when a PR branch (ours or one we may push to) conflicts with upstream `main` again and again in one file that every upstream commit touches (TensorFold: `CHANGELOG.md`, top of `## Unreleased`), the maintainer wants the branch current, and force-pushing is forbidden. The result is ONE merge commit pushed as a fast-forward.

## Why the obvious way fails

- A full gate run takes longer than the gap between upstream batches, so a merge gated end to end is stale before it can be pushed, and a conflicting PR gets no CI.
- TensorFold cannot be checked out on Windows (illegal file names), and nothing may be compiled on the laptop.

## Procedure (Git for Windows at the top level, bare repo, no working tree)

1. Bare scratch repo under the repo's `work/`: `git init --bare work/signmerge.git`; fetch the PR head (`prhead`) and upstream main (`up`) into it.
2. Confirm the conflict set: `git merge-tree --write-tree --name-only prhead up` exits 1 and lists ONLY the changelog. Its first output line is a tree with conflict markers in that one file.
3. Resolve by rule, not by hand: take upstream's `CHANGELOG.md` at `up`, insert our one bullet (read it from the previous merge or the PR head) directly under `## Unreleased`, then replace the blob: `GIT_INDEX_FILE=idx.tmp git read-tree <tree>`, `git hash-object -w --stdin`, `git update-index --cacheinfo 100644,<blob>,CHANGELOG.md`, `git write-tree`. Keep this as a small script taking the upstream ref, because it will be re-run.
4. Prove the tree: `git diff --name-only up <tree>` equals the PR's own file list; no `<<<<<<<` markers (`git grep`); the changelog diff against `up` is exactly our bullet.
5. Re-derive the merge message's numbers (conflict count, files changed on both sides: `comm -12` of `git diff --name-only $(git merge-base prhead up) prhead` and the same against `up`). Message in a file.
6. Sign with plumbing, INLINE at the top level (a `bash x.sh` file runs inside WSL with the wrong git and gpg): set `GNUPGHOME`, author and committer identity env vars, then `git commit-tree -S <tree> -p <prhead> -p <up> -F <msgfile>`; check `%G?` is `G` and the tree and parents match.
7. Just before pushing, `git ls-remote` both remotes: upstream main must still equal the second parent and the PR branch tip the first parent. Push the sha to the branch ref with a plain push (fast-forward). If HTTPS is refused with a `workflow` scope error (upstream changed a workflow file), push over SSH.

## When gates cannot keep up

- Gate ONE merge fully (identity checks, fmt, lean base against head with each tree's own tool, the repo's PR check, the steps that pin the PR's files).
- For a later rebuild, push immediately if `git diff --name-only <gated-merge-main> <new-main>` shares no file with the PR except the changelog AND the new tree differs from the gated tree by exactly those files, each being upstream's own blob. Then the gated results carry over; run the full set on the pushed head afterwards and report it.
- If the new upstream commits DO touch a PR file or a file its fixtures pin, run the merge-specific steps before pushing.

## After the push

- Fork PR workflow runs may sit in `action_required` until the maintainer approves them; that is not a failure.
- The branch conflicts again at the next upstream batch. Do not push merge after merge unasked: each push notifies reviewers. Rebuild (about a minute with the script) when the maintainer is ready to run CI or asks.
- A stacked PR on this branch must be re-seated on the pushed head by script; keep its re-seat one command.

# Merge a fast-moving upstream main into an open PR branch, without a checkout

Use when a PR on `ashhart/TensorFold` (or any repo whose main lands batches hourly and touches `CHANGELOG.md` every time) must take main by a MERGE COMMIT (never a force-push), on a Windows workstation where the tree cannot be checked out.

## Facts that shape the procedure (measured 2026-11-16, PR #2762)
- Main moved four times in 2.5 hours; each move conflicted only in `CHANGELOG.md` (both sides insert at the top of `## Unreleased`). A merge that waits for a 30+ minute gate run is stale before it is pushed.
- GitHub runs no `pull_request` workflow while the PR conflicts, and fork-PR workflows sit in `action_required` until a maintainer approves them.
- HTTPS push is rejected with `refusing to allow an OAuth App to create or update workflow ... without workflow scope` whenever main changed a workflow file since the PR base. Push over SSH.
- `bash script.sh` at the harness top level runs inside WSL: Linux git and gpg, `No secret key`. Sign with native Git for Windows commands typed at the top level.

## Steps
1. Bare repo under the repo's `work/`: `git init --bare work/signmerge.git`; fetch the PR head and upstream main into refs (`git fetch <url> <branch>:refs/heads/prhead`, `git fetch https://github.com/ashhart/TensorFold.git main:refs/heads/up`).
2. `git merge-tree --write-tree --name-only prhead up`: first output line is the tree; the remaining lines list conflicted paths. Assert the set is exactly `CHANGELOG.md`; anything else needs real resolution.
3. Resolve the changelog by construction: take main's `CHANGELOG.md`, insert our one bullet right after `## Unreleased` (assert the heading occurs once), `git hash-object -w --stdin`, then with a temporary `GIT_INDEX_FILE`: `git read-tree <tree>`, `git update-index --cacheinfo 100644,<blob>,CHANGELOG.md`, `git write-tree`. Delete the temp index.
4. Verify before signing: `git diff --name-only up <tree>` equals the PR's own file list; `git grep -c '^<<<<<<< ' <tree>` finds nothing; re-derive every count the merge message states (files changed on both sides: `comm -12` of the two `git diff --name-only <merge-base> <side>` lists).
5. Sign natively (top-level shell, not a script run by `bash`): `GNUPGHOME=C:/Users/Adam/AppData/Roaming/gnupg`, the public identity in `GIT_AUTHOR_*` and `GIT_COMMITTER_*`, then `git commit-tree -S <tree> -p <prhead> -p <main> -F <msgfile>`. Check `git log -1 --format='%G? %T %P'` shows `G`, the tree and both parents.
6. Immediately before the push, `git ls-remote` both main and the PR branch; refuse if main is not the merge's second parent or the PR tip is not its first parent.
7. Push as a fast-forward over SSH with `SSH_AUTH_SOCK` set: `git push git@github.com:<owner>/TensorFold.git <sha>:refs/heads/<branch>`. No force.

## Keeping pace with main
- Gate the first merge fully on a build box (never the laptop). After that, a rebuilt merge may be pushed at once when BOTH hold: `git diff --name-only <old main> <new main>` shares only `CHANGELOG.md` with the PR's files (and touches no file the PR's fixtures pin), and the new tree differs from the gated tree by exactly those files with the non-changelog ones being main's own blobs. Then run the full gate set on the pushed head and report it.
- Have the gate lane compute the expected merge tree independently on the box; equal tree ids are the proof the two builds agree.
- Do not push merge after merge unasked: each push notifies reviewers and stays conflict-free for about an hour. Rebuild when the maintainer is ready to run CI or asks.

## Traps
- Redirecting output to `/tmp/...` at the top level fails on Windows and makes the command exit 1, which reads like a merge conflict. Write under `work/`.
- Zig's build summary leaves out tests of cached steps, so the same step reports different totals on two runs. Quote the summary line of the run you cite.
- GitHub may show the commit unverified with reason `bad_email` when no UID on the signing key matches the committer address; that is a key/account matter for the owner, not a reason to re-push.

# Merge a mutant manifest by id

A mutation-gate manifest (`tools/mutants.json`, a JSON array of `{id, file, find, replace, tests, why}`) is kept one entry per line so branches that append entries only conflict at the tail. When a branch re-serialises the file (one line, different indent), `git merge` reports the whole file as one conflict. Merge by id instead.

## Procedure
1. Start the merge as usual (`git merge --no-ff --no-commit <theirs>`); leave the manifest conflicted.
2. Run an id-level merge with three inputs: ours = `git show HEAD:tools/mutants.json`, base = the branch's own base commit (the commit its worktree was created from, not the merge-base of an unrelated branch), theirs = the branch tip.
3. Rules:
   - first prove ours round-trips: `layout(json.loads(ours)) == ours`, else stop;
   - refuse duplicate ids on any side;
   - removed = ids in base but not theirs: drop from ours (flag if ours changed it);
   - changed = ids in both base and theirs with different content: take theirs where ours still equals base, flag where both changed;
   - added = ids in theirs but not base: append in theirs' order (flag an id added on both sides);
   - write ours' layout: `"[\n" + ",\n".join(" " + json.dumps(e, ensure_ascii=False) for e in entries) + "\n]\n"`, newline="\n".
4. Print counts (ours, base, theirs, removed ids, changed ids, added, merged) and exit 1 on any clash.
5. Run `tools/mutants.py --check`; re-anchor any entry whose anchor no longer matches because the merged code moved (keep its perturbation and its tests).
6. `git add tools/mutants.json` with the other resolved files and commit the merge with a message that states the counts.

## Prevent it
Every lane brief says: append new entries at the END of the array, one per line; never rewrite or re-serialise the manifest.
