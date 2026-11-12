# The old engine fork `ots/tensorfold-gb10`, kept whole

`tensorfold-gb10.bundle` is a git bundle of everything that fork and the five working clones of it on this
laptop held that upstream `ashhart/TensorFold` does not: 341 refs, 871 commits, 12,317 objects,
11,346,795 bytes, sha256 `017e3ee2b6bbf2bd21b1f2226a7ef9a4dec888c9612bbe884e316ed3642dd424`. Taken
2026-11-12 so the fork can be retired without losing anything.

- `REFS.txt` - every ref in the bundle and its sha.
- `LEFT-OUT.txt` - every ref of the fork or its clones that was not bundled, with the upstream ref that
  holds that object.
- `SOURCES.txt` - every ref that existed in a source when this was taken, where it lived, and the name it
  has here.

The repository's HEAD was `refs/heads/main`. Sources read: the Gitea repository
`ssh://git@gitea.ots-int.net:2222/ots/tensorfold-gb10.git` (15 branches, no tags), and five clones of it
that live inside the gitignored `work/` of the laptop's `ai-engine` clone: the bare mirror
`work/aie/tf.git`, the working clone `work/aie/glmnight-tree` with its worktrees `work/aie/merge-wt`,
`work/applytest` and `work/hdr`, and `work/tfbase`, `work/verify`, `work/verify2`. The six Sparks hold no clone
of this fork: every git repository under the home directory and `/srv` of each, to depth 6, was read for its
remotes on 2026-11-12 (36, 12, 2, 17, 2 and 131 repositories).

## The reason the scratch clones matter

The Gitea repository has 15 branches left. The scratch clones between them name 55 branches of this fork,
so **41 branch names are gone from Gitea and survive only in those clones**. Twelve of the 41 carry
commits that no surviving `tensorfold-gb10` branch and no upstream branch or tag has:

| branch | own commits | tip |
|---|---|---|
| `kda-pad` | 10 | `a46ca982c` glm cuda: glm-kda-pad-split's header is one line |
| `ovn-img20` | 6 | `cc38f4fbb` image branch ovn20: merge ovn-batchresume |
| `pr1623-review3` | 5 | `e93425038` merge upstream main into pr-dflash-prompt-taps |
| `pr1623-review2` | 4 | `b2c6cdab3` a TP>1 GPU check for DFlash2 prompt taps |
| `ovn-numx` | 2 | `6fa7d3a85` merge ovn-latmma-exact into ovn-numx |
| `tapchk-main` | 2 | `db8c522d6` image only: taps.hidden as 4096 on main |
| `glm-pair-drafter` | 1 | `f7795d99a` a paired step beside the drafter drops its views' taps |
| `glm-tapfix-2k` | 1 | `0d5bfb3a5` prompt chunks of 2,048 rows again |
| `glm-up1028-stack` | 1 | `e6b0aea97` the disk-image fake has the head flag |
| `ovn-latile` | 1 | `b2d1754ab` `TF_GLM_OVN_LATENT_TILE` register-tiled absorb and expand |
| `ovn-latmma-exact` | 1 | `450a7a3af` `TF_GLM_OVN_LATENT_MMA_EXACT` |
| `pr-dflash-prompt-taps` | 1 | `9d29dc256` DFlash2 reads complete prompt taps at TP>1 |

Salvaging the Gitea repository alone would have lost those twelve.

## What is in it

| refs | what |
|---|---|
| 14 `refs/heads/*` | the live branches. `ovn-up` = `595e28743` (266 commits beyond upstream) is **the engine series our GLM patch stack was ported from**. `main` = `55d5636d0` is the gb10 trunk (179 commits), `port-dsv41` (111), `port-glm` (52) and `port-qwen` (13) are the three family ports onto it, `miaai-glm` (7) is the MiaAI recipe's zig-engine patch, `ots-g3-c-kit` (180) is the OTS-1144 Triton cubin capture, `sync/qwen-rebase` is the rebased warm-turns work, `fill-short-resume` and the five `lead/*` branches (`kvh-bw`, `latent-mma-exact`, `latent-tile`, `win-catchup`, `win-fair`) are the lever branches, each a merge of `ovn-up` |
| 50 `refs/scratch/tf-mirror/heads/*` and 41 `refs/scratch/tf-mirror/remotes/gitea/*` | the bare mirror `work/aie/tf.git`. This is where most of the deleted branches survive: the `glm-*` family (dflash-win, disk-staging, exl3-rows2k, exl3-sk, fp8-pages, fp8-pipe, index-decode, l2pf, padfix, pair-drafter, resume-any, rows4k, stack-many, tapfix, tapfix-2k, up1028, up1028-stack), the `ovn-*` family (base, batchresume, copyagree, flakes, img20, int, items, kdapieces, latile, latmma-exact, numx, onepass2, prxflake, routerwarm), `kda-pad`, `pr1623-review2` and `-review3`, `pr-dflash-prompt-taps`, `sync-glm-perf`, `sync-glm-residuals`, `tapchk-main`, `gb10` |
| 35 `refs/scratch/glmnight-tree/remotes/gitea-eng/*` | the same branches as that clone saw them through a remote whose configuration has since been removed |
| 61 `refs/scratch/glmnight-tree/remotes/orig/*` and 17 `refs/scratch/glmnight-tree/up/*` | upstream pull request heads this clone had fetched that upstream's own `refs/pull/N/head` no longer points at, 77 of the 78 because the pull request was pushed again afterwards and one (`pr/1571`) because the head moved on past it. The 1,007 that still match upstream exactly were left out |
| 50 `refs/scratch/glmnight-tree/remotes/mirror/*`, 10 `remotes/fork/*`, 8 `remotes/fork-ssh/*`, 7 `heads/*` | the same working clone's view of the bare mirror, of the GitHub fork `BadAd84/TensorFold`, and its own local branches (`ovn-up`, `fill-short-resume`, the five `lead/*`) |
| `refs/scratch/glmnight-tree/stash` = `80bf7a125` | the only stash anywhere in this salvage: "WIP on (no branch): 71bb14872 S24: fronts + pair", 2026-11-09, GLM CUDA forward, KDA, MLP and MoE files, three parents as git stores a stash |
| `refs/scratch/glmnight-tree/atc/presence/local` | an ATC presence marker commit the clone carried |
| 35 `refs/scratch/tfbase/remotes/origin/*` + `heads/main`, 2 + 1 each for `verify` and `verify2` | the three small clones under `work/`. `tfbase` and `verify` are blobless partial clones, which is why `deep_check.py` exists |
| `refs/scratch/tf-mirror/remotes/upstream/ds41-four-ranks` | an upstream branch that upstream has since deleted |
| `refs/scratch/worktree/work-aie-merge-wt` | the checked out HEAD of that worktree, `595e28743` |

## The era tree the GLM Zig docs cite

`docs/PATCH-AUDIT.md`, `docs/speed_target.md` and the two `docs/audit-2026-11-11/patches-*.md` of the GLM
Zig repository call their third comparison tree "era", at the path `ai-engine/work/aie/fair-base`. That
directory is a plain extraction with no `.git` of its own, and no ref anywhere is named `fair-base`. It is
commit `a55671a7c2c4` ("glm lanes: TF_GLM_OVN_WIN_FREE, shared rounds fill with no cost model", 2026-11-03):
all 4,558 files under `zig/src`, `zig/tests`, `zig/build` and `tools` hash to that commit's blobs, with none
missing on either side. That commit is an ancestor of `refs/heads/ovn-up` and is in this bundle and in
ai-engine's. The base those docs name, `9b2991d122c7`
("CHANGELOG: the half-operand projections on Metal", 2026-11-07), is an upstream commit that a plain clone
of upstream has and that this bundle lists as one of its 41 prerequisites, and it is an ancestor of
`refs/heads/ovn-up` = `595e28743`. Checked by restoring this bundle into a plain clone of upstream and
reading back the one file `patches/engine/0035-top1-sums.patch` cites from that tree:
`zig/kernels/cuda/glm_glue_rows.cuh`, blob `906fa606f890c98502d9ed584abc739b69023d93`, 15,391 bytes,
first line `// GLM's element-wise glue by hand: each output value alone, in the Triton kernel's order of
fp32 ops.`

## What was left out, and why

1,139 refs, all listed in `LEFT-OUT.txt` with the upstream ref that holds each object. By group:

- 1,005 `refs/scratch/glmnight-tree/remotes/orig/pr/*` and 2 `up/pr*` - this clone's mirror of upstream's
  pull heads, each byte-identical to a `refs/pull/N/head` that upstream still holds.
- 57 `refs/scratch/glmnight-tree/tags/*` and 46 `refs/scratch/tf-mirror/tags/*` - upstream's release tags.
- 5 `refs/scratch/tf-mirror/heads/*` - `main` and `zig-flashnext` (both upstream's `v1.0.8` tag object),
  `zig-preview` (`v1.0.2`), `python-0.6` and `upstream-main`, both reachable from upstream's `main`.
- `refs/heads/upstream-main` = `cde4fe7d9` - the fork's copy of upstream main, reachable from upstream's
  `main`. This is the only one of the fork's 15 branches that is not bundled.
- 17 others, each a clone's view of an upstream branch or of one of the refs above.

The exclusion set is upstream's branches and tags as they stood on 2026-11-12: 81 branches and 61 tags,
compared against a plain `git clone --bare` of upstream and found identical. Upstream's pull heads were
not used as an exclusion for our own work, only to recognise the clones that had mirrored them.

## Where this overlaps the `ai-engine` archive

Seven tips are in both archives: `ovn-up` (`595e28743`), `fill-short-resume` (`19350d61e`) and the five
`lead/*` levers, which this repository holds as branches and the other holds as
`refs/laptop/remotes/fork-ssh/*`. That is 3,582 objects, 1,458,548 bytes, stored twice. Each archive is
self-contained on purpose: a dependency between the two bundles would save 1.4 MB out of 39 MB and would
stop either from restoring on its own, which is the property that matters once both repositories are gone.

## Restore

The bundle is thin against upstream: it needs 41 prerequisite refs, all commits in upstream's branches and
tags. Restore into a **full** clone of upstream TensorFold. A `--filter=blob:none` partial clone will not
do: it cannot resolve the bundle's deltas and git stops with `pack has 2442 unresolved deltas`.

    git clone https://github.com/ashhart/TensorFold.git tf
    cd tf
    git fetch /path/to/tensorfold-gb10.bundle 'refs/*:refs/gb10/*'     # everything, structure kept

Single pieces:

    git fetch /path/to/tensorfold-gb10.bundle refs/heads/ovn-up:refs/heads/gb10-ovn-up
    git fetch /path/to/tensorfold-gb10.bundle 'refs/scratch/tf-mirror/heads/*:refs/heads/gb10-old/*'
    git bundle verify /path/to/tensorfold-gb10.bundle                  # lists refs and prerequisites

## Checks, run 2026-11-12

    python verify_bundle.py tensorfold-gb10.bundle <a full TensorFold clone> REFS.txt
    341 refs, 0 mismatches, connectivity ok

    python deep_check.py tensorfold-gb10.bundle <a full TensorFold clone>
    341 refs, 96,205 objects walked, 0 missing

    python accounted_for.py SOURCES.txt REFS.txt LEFT-OUT.txt --live ssh://git@gitea.ots-int.net:2222/ots/tensorfold-gb10.git
    1,482 source refs: 343 bundled under the same name, 2 bundled under another name, 1,137 left out
    because upstream holds them, 0 unaccounted for; the live repository had 16 refs and 0 differences
    from the snapshot

The two bundled under another name are `refs/remotes/orig/pr/1206` of the glmnight-tree clone, archived as
`refs/scratch/tf-mirror/remotes/upstream/ds41-four-ranks`, and its `refs/remotes/orig/pr/735`, archived as
`refs/scratch/glmnight-tree/remotes/fork/prompt-cache-branch-point`: the same commit under two names.

`verify_bundle.py` proves the bundle gives back every ref it lists. `deep_check.py` walks every object of
the restored refs, blobs included, because two of the clones this archive drew from (`work/tfbase` and
`work/verify`) are blobless partial clones and a hole inherited from one of them would be invisible to a
ref comparison. `accounted_for.py` is the other direction: every ref that existed in a source is either
bundled under the same sha or left out with the upstream ref that holds it. All three were shown to fail
on a damaged input before being trusted: a bundle with one ref dropped (exit 1, `340 refs, 1 mismatches`),
a bundle built with `--filter=blob:none` (exit 1, `the bundle did not restore: missing blob object`), and
a `REFS.txt` with one uniquely named ref removed (exit 1, `1 unaccounted for`).
