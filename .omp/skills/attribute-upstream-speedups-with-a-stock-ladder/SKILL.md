---
name: attribute-upstream-speedups-with-a-stock-ladder
description: "After syncing a patched serve onto a much newer upstream, measure which upstream changes (merged or in open PRs) sped it up: stock-image ladder, bracketing commits, off-switch arms, written-first scorer."
---

# Attribute upstream's speedups to our serve with a stock ladder

Use when the owner asks "did anyone else's work speed things up" after a sync onto upstream main, or "what do our patches still buy". Read the user skill `attribute-a-rebase-versus-our-patches` too. Text work stays on the laptop; every build, test and GPU window goes to the gate host and the Sparks.

## 1. Decide what could matter before booting anything (git and gh only)
- Commits by PATH, not by title keyword: `git log --no-merges --format='%h%x09%an%x09%cs%x09%s' OLD..NEW -- <the serve's code paths>`. Most "faster" titles are other backends (Metal, Vulkan, other families); here 71 commits touched the GLM CUDA path and only three could speed an EXL3 TP=3 serve.
- Changelog: the bullets present in NEW's CHANGELOG and absent from OLD's that name your model and a number. They are authors' claims to test, never results.
- Which release contains each change: `git merge-base --is-ancestor <commit> <tag>`. Changes that land after the newest tag fall into one rung together. Split them with `git rev-list --first-parent TAG..NEW` (tip first): the commit at position+1 of a change has everything before it and not the change; confirm with is-ancestor in both directions.
- Open PRs: `gh pr view N -R owner/repo --json body,mergeable,headRefOid,baseRefOid`, save the body, read the receipts table's CONFIGURATION (checkpoint, ranks, drafter, settings, base commit) and decide whether it can matter for ours. A gain measured without a setting we already run is already ours (e.g. a padding PR "10% sooner cold" against a base without `TF_GLM_KDA_PAD`; a RoCE PR whose result equals the documented `TF_GLM_ROCE_MULTI`). Select candidates by changed-file overlap plus title, from a saved `pr-files.json`.

## 2. The ladder
- Rungs: each release tag since the old pin, the bracketing first-parent commits, the new pin. Source tar per rung by `git archive` in WSL (deterministic: re-pack and compare sha256), staged by `scp` to `stage/x.part` then `mv`, one image per rung built on spark1 only and copied to the other ranks, one image id on all ranks before any boot.
- Every rung runs the SAME runtime-only settings (the "off" mode: no knob of ours), shape and instrument; interleave the order and repeat the newest rung at the end (drift guard); put the most informative arms first in case the deadline bites.
- Arms that need no image: an upstream OFF switch on the newest stock image (e.g. `TF_GLM_PDL=0`) gives that change's share; an upstream opt-in on stock (e.g. `TF_GLM_REQUEST_STARTS=1`) gives what upstream's own version of our feature does.
- Open-PR arms: a lane builds main-plus-PR trees (merge-tree, smallest conflict resolution, no change to the PR's default), gates them on the gate host, and records the switch lines and the rank-0 log line that proves the switch is active; the queue counts that line per boot and logs it.

## 3. Scorer written BEFORE the rows
Rules fixed in the docstring first: the rungs; a step is CLEAR only when every boot of the rung lies beyond every boot of the rung before; a PR arm is a CANDIDATE only when no cell is more than 1% slower than the stock main group, at least one cell that matters (cold, warm turns, decode at 1, 2, 4 clients) beats the group's BEST boot by more than 1%, and every reply digest equals; missing cells or boots are NOT DECIDED; the stack against the main group is its own section. Fixture-row tests plus mutants of each rule: two mutants survived the first time (a latency-gain branch and a partial-rows branch were untested), so a survivor means a missing test before it means dead code.

## 4. Queue-script hazards (each cost or nearly cost something)
- Register the EXIT trap AFTER the wait for a predecessor queue: a kill while waiting would otherwise run `stop` and kill the predecessor's live serve.
- Wait on the predecessor's PROCESS (`pgrep -f queueNN.sh`), not on its log's DONE line (a dead queue never prints it).
- Do not start a queue whose env file, expected-log regexes or staged tars are not final: the env is sourced at start and bash reads a running script incrementally.
- Overlap `dist-image.sh` with the next build only while no bench runs; per-tag logs keep two copies from colliding.
- A start command that backgrounds a job over ssh can hang until the call's timeout although the job started: check with `pgrep` instead of re-running it.
