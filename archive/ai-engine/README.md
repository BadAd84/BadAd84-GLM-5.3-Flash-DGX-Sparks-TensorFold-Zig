# The old engine fork `ots/ai-engine`, kept whole

`ai-engine.bundle` is a git bundle of everything that fork, its working clone on this laptop and that
clone's worktrees held that upstream `ashhart/TensorFold` does not: 458 refs, 1,410 commits, 25,289
objects, 27,701,344 bytes, sha256 `177a5bbc561945b8851db90e5a160171b3856388368ccbf1ebaf9f15fd3738c2`.
Taken 2026-11-12 so the fork can be retired without losing anything.

- `REFS.txt` - every ref in the bundle and its sha.
- `LEFT-OUT.txt` - every ref of the fork or its clones that was not bundled, with the upstream ref that
  holds that object.
- `SOURCES.txt` - every ref that existed in a source when this was taken, where it lived, and the name it
  has here. This is what makes the accounting checkable after the repository is gone.

The repository's HEAD was `refs/heads/master`. Sources read: the Gitea repository
`ssh://git@gitea.ots-int.net:2222/ots/ai-engine.git`, the laptop clone `C:/Users/Adam/Gitea/ai-engine`,
and that clone's three worktrees under `work/aie/`. The six Sparks hold no clone of this fork: every git
repository under the home directory and `/srv` of each, to depth 6, was read for its remotes on 2026-11-12
(36, 12, 2, 17, 2 and 131 repositories).

## What is in it

| refs | what |
|---|---|
| `refs/heads/master` = `394cc9887` | the fork's trunk, 742 commits, and a history with **no common ancestor with upstream at all**: `docs`, `engine`, `evidence`, `patches`, `scripts`, `tools`. This is the research and recipe repository that drove the GLM, DeepSeek and Qwen work, not an engine source tree |
| 74 `refs/heads/ots-*` | one branch per OTS ticket. By name: 25 CUDA arm and kernel branches (`ots-1197-armC-*`, the `ots-1260-*` seed, order, pedantic, bf16 and cublas probes, `ots-1290` and `ots-1336-kernel-candidates`), 17 GLM (`ots-396-glm-profile`, the `ots-6xx-glm-ab*` series, `ots-1050-l39-diag`, `ots-1142-g3-layout`), 5 Qwen (`ots-q9`, `ots-q36`, `ots-q37`), 4 DeepSeek V4.1 (`ots-868` and `ots-875-dsv41-*`, `ots-570-d2-5-fullforward`), 3 MiaAI recipe (`ots-418` and `ots-419-miaai-*`), and 20 harness, serve and gate branches named after the box they ran on or the thing they fixed (`ots-171-0118-spark4`, `ots-223-ownenv-spark5`, `ots-384-warm-split-spark6`, `ots-424-warm-gate-spark4`, `ots-860-pool-from-parallel`, `ots-1205-qual-driver`, `ots-728-code2-stack`). `ots-g3-b-transport` (263 commits) is the N-rank GLM control-link hub, never merged |
| 5 `refs/heads/ovn-*` | the overnight GLM speed-hunt levers, about 250 commits each: `ovn-cachesalt` (per-salt kept states), `ovn-catchup` (`TF_GLM_OVN_WIN_CATCHUP`), `ovn-fair` (`WIN_FAIR`), `ovn-prefixwait` (`TF_GLM_OVN_EXCHANGE_KB`), `ovn-solo` (`TF_GLM_OVN_CHUNK_SOLO`) |
| `refs/heads/pr-exl3-items-unconditional` = `610ce288b` | the branch behind upstream pull request 2044, two commits past upstream main. Upstream also holds this object as `refs/pull/2044/head`, but a plain clone of upstream does not fetch pull refs, so it is bundled here |
| `refs/heads/workspace-notes-2026-10-24` | untracked deliverables, verdicts and reports from the shared workspace, committed before that box was cleared |
| 101 `refs/tags/archive/*` and 34 `refs/tags/wip/*` | lightweight per-ticket snapshots, named after the branch or ticket they froze |
| 13 `refs/pull/N/head` | Gitea's own pull request heads. **No branch points at any of the 13 any more**, so inside this repository these refs were the only copy of those heads |
| 3 `refs/laptop/heads/*` | the laptop clone's local branches: `master` (same sha as the Gitea branch), `pr-exl3-items` (`7b349f4e6`, a merge of main into the PR branch that was never pushed anywhere) and `pr-exl3-items-unconditional` |
| 94 `refs/laptop/tags/archive/*`, 34 `refs/laptop/tags/wip/*` | the laptop's copy of the tags; the Gitea repository has 7 archive tags the laptop never fetched, and no tag differs in sha |
| 83 `refs/laptop/remotes/origin/*` | the laptop's view of the Gitea branches, including `origin/HEAD`. Same shas as `refs/heads/*` |
| 12 `refs/laptop/remotes/fork-ssh/*` | branches of the GitHub fork `BadAd84/TensorFold`: `ovn-up`, `fill-short-resume`, the five `lead/*` levers, `carveout-dispram`, `pr-dflash-prompt-taps`, `pr-exl3-items-unconditional`, `window-48-rows` and `window-48-rows-receipt` |
| 2 `refs/laptop/worktree/*` | the detached or checked out HEAD of the worktrees `work/aie/up-items` and `work/aie/up-items-uncond` |

All 135 tags in this repository are lightweight, so a tag carries no message of its own.

## What was left out, and why

62 refs, all listed in `LEFT-OUT.txt` with the upstream ref that holds each object:

- 58 `refs/laptop/tags/v*` - upstream's own release tags, `v0.2.0` through `v1.2.6`, each byte-identical to
  `refs/tags/<same name>` in upstream TensorFold.
- `refs/laptop/remotes/fork-ssh/HEAD` and `refs/laptop/remotes/fork-ssh/main`, both `499b20baf`, a commit
  reachable from upstream's `main`.
- `refs/laptop/remotes/up/main` and `refs/laptop/worktree/work-aie-up-main`, both `673a34b3b`, likewise
  reachable from upstream's `main`.

The exclusion set is upstream's branches and tags as they stood on 2026-11-12: 81 branches and 61 tags,
compared against a plain `git clone --bare` of upstream and found identical. Upstream's pull heads were
**not** used as an exclusion: a plain clone does not fetch them, so anything of ours that matches only a
pull head is bundled anyway and noted in `REFS.txt`.

## Where this overlaps the `tensorfold-gb10` archive

Seven tips are in both archives: `ovn-up` (`595e28743`), `fill-short-resume` (`19350d61e`) and the five
`lead/*` levers, which this repository held only as `refs/laptop/remotes/fork-ssh/*` and the other
repository holds as branches. That is 3,582 objects, 1,458,548 bytes, stored twice. Each archive is
self-contained on purpose: making one bundle depend on the other would save 1.4 MB out of 39 MB and would
stop either archive from restoring on its own, which is the property that matters when both repositories
are gone.

## Restore

The bundle is thin against upstream: it needs 22 prerequisite refs, all commits in upstream's branches and
tags. Restore into a **full** clone of upstream TensorFold. A `--filter=blob:none` partial clone will not
do: it cannot resolve the bundle's deltas and git stops with `pack has 1067 unresolved deltas`.

    git clone https://github.com/ashhart/TensorFold.git tf
    cd tf
    git fetch /path/to/ai-engine.bundle 'refs/*:refs/aie/*'        # everything, structure kept

Single pieces:

    git fetch /path/to/ai-engine.bundle refs/heads/master:refs/heads/ai-engine-master
    git fetch /path/to/ai-engine.bundle 'refs/tags/archive/*:refs/tags/aie-archive/*'
    git bundle verify /path/to/ai-engine.bundle                    # lists refs and prerequisites

## Checks, run 2026-11-12

    python verify_bundle.py ai-engine.bundle <a full TensorFold clone> REFS.txt
    458 refs, 0 mismatches, connectivity ok

    python deep_check.py ai-engine.bundle <a full TensorFold clone>
    458 refs, 114,911 objects walked, 0 missing

    python accounted_for.py SOURCES.txt REFS.txt LEFT-OUT.txt --live ssh://git@gitea.ots-int.net:2222/ots/ai-engine.git
    521 source refs: 459 bundled under the same name, 62 left out because upstream holds them,
    0 unaccounted for; the live repository had 231 refs and 0 differences from the snapshot

`verify_bundle.py` proves the bundle gives back every ref it lists. `deep_check.py` walks every object of
the restored refs, blobs included: none of this archive's own sources was a partial clone, but a hole in a
bundle is invisible to the ref comparison, and the sibling `tensorfold-gb10` archive did draw on two
blobless clones, so the same walk is run here. `accounted_for.py` is the other direction: every ref
that existed in a source is either bundled under the same sha or left out with the upstream ref that holds
it. All three were shown to fail on a damaged input before being trusted: a bundle with one ref dropped
(exit 1, `457 refs, 1 mismatches`), a bundle built with `--filter=blob:none` (exit 1, `the bundle did not
restore: missing blob object`), and a `REFS.txt` with one uniquely named ref removed (exit 1,
`1 unaccounted for`).
