# REPO-FORMAT.md - bring this repo to the two-branch format (owner 2026-11-12)

Written from the Qwen repo's session after comparing the three serve repos. It is a work order for the agent that
works in THIS repo: do the steps, then delete this file in the commit that finishes the last one. Every "today" below
was measured on 2026-11-12 at `main` = `db314e5`.

## The format

The reference is `ots/Qwen3.8-Flash-Next-DGX-Sparks-TensorFold-Zig` (`production` at `7f6ad55`, `main` at `32c2f98`;
its `AGENTS.md` section "Branches" and the `PRODUCTION.md` on its `production` branch).

- **`production`** - the recipe the live serve runs, which is the target to match or beat. It holds what rebuilds
  and relaunches the serving image, the image build files, the launcher with its whole environment, and the measured
  target. `PRODUCTION.md` at the root says what serves, where, from which image, and how the branch was proved equal
  to that image. Frozen: it changes only when production changes. Its history is unrelated to `main`'s; read it in
  its own worktree (`git worktree add work/prod production`), never by switching the main checkout.
- **`main`** - the in-flight work on the modern TensorFold engine: our levers as numbered `.patch` files on a
  pristine upstream release at a recorded sha, the harnesses, the measurements, the docs. No engine tree is
  committed. It follows upstream: on each release the series is re-seated and every lever re-tested. When `main`
  matches or beats `production/SPEED-TARGET.md` at 1, 2, 4, 6 and 8 streams, it replaces production.
- **No private engine fork.** Levers live as patch files in the serve repo. The plain fork `BadAd84/TensorFold` is
  for upstream PR branches only.

## This repo today, against that

`main` is already the right shape: `patches/engine/` is one series (42 patches) on a pristine pin named in
`scripts/config.sh`, with `RECORD.md`, `SHA256SUMS` and `scripts/apply.sh`, no engine tree, and the package gate is
clean with nothing grandfathered (1 package dir checked, 0 grandfathered, `--strict` clean). What is missing:

| point | today | gap |
|---|---|---|
| `production` branch | none; `main` is the only branch | to create |
| the target's recipe | `docs/speed_target.md` holds the target's numbers; the recipe that produces them (image `tensorfold-glm53:v110hunt4-fix`, Python engine, TP=3 on spark1-3) is in another repo, `ots/GLM-5.3-Flash-DGX-Sparks-TensorFold-Python-TP3` | the target cannot be read from this repo |
| base | pin `9c9bf542` is `v1.2.4-242`, not a release; upstream's v1.2.7 tag (`93a2e93ec`, 2026-11-11) is 600 commits past it | `main` is not on the modern release |
| private engine fork | `ots/ai-engine` on Gitea (82 branches, 135 tags, about 110 MB): `RECORD.md` names it as the source of 0001-0031 and 0042, `PORT-LEDGER.md` and `docs/PORT-LEFTOVER.md` track what is still only there, and the images are named `ai-engine:fixN` | the format has no such repo |
| `AGENTS.md` | none; the rules are in `README.md` | every repo has one, with a "Branches" section |
| `candidates/` | named in `README.md` and `scripts/patch-packages.list`; 0 tracked files | drop the mention or track what belongs there |

## Steps

1. **Carry `production` as the same commit the Python repo carries.** That repo's `REPO-FORMAT.md` step 1 builds the
   branch (the serving recipe, `PRODUCTION.md`, `production/SPEED-TARGET.md` including this repo's
   `docs/speed_target.md` table). When it is pushed:
   `git fetch ssh://git@gitea.ots-int.net:2222/ots/GLM-5.3-Flash-DGX-Sparks-TensorFold-Python-TP3.git production:production`
   then `git push origin production`. Check: `git ls-remote` shows one sha for `refs/heads/production` in both
   repos. Add nothing on top of it here, so the sha stays the same. `docs/speed_target.md` stays on `main`.
2. **Move the pin to the release and re-seat the series** (the version-bump rule already in `README.md`): all 42 onto
   v1.2.7, each one applied, gated and measured, and each one upstream absorbed retired with the commit that absorbed
   it. A patch that no longer applies is re-seated before it is judged.
3. **Close out `ots/ai-engine`.** When `PORT-LEDGER.md` shows every item landed here, retired with its evidence, or
   re-seated as a patch, nothing should be readable only in the fork. Then salvage it the way the Qwen repo did its
   fork (`archive/tensorfold-levers124/` there): a git bundle of every ref beyond upstream, `REFS.txt`, a script that
   restores the bundle into a clone and compares every ref, and a walk of every object (blobs included; that fork's
   clone turned out to be a partial clone, which is why the walk exists). Images stop being named after the fork.
   Other users to move first: the DeepSeek repo calls its probe in 11 files (its own note has a step for that) and
   the Qwen repo names it in 5.
4. **Find the owner of `ots/tensorfold-gb10`.** It has 15 branches with GLM names (`miaai-glm`, `fill-short-resume`,
   `lead/kvh-bw`, `lead/latent-mma-exact`, `lead/latent-tile`, `lead/win-catchup`, `lead/win-fair`, last pushed
   2026-11-07) and no serve repo names it. If it is GLM's, it gets the treatment of step 3.
5. **Write `AGENTS.md`**: the "Branches" section, the conventions and gates now in `README.md`, the gotchas. `README.md`
   keeps what a reader of the recipe needs. Then delete this file.

## Needs the owner's word

- Deleting `ots/ai-engine` (and `ots/tensorfold-gb10` if it is GLM's) from Gitea after the salvage is verified.
  Salvaging and verifying need no word; the delete does.

## Do not

- Switch this checkout to `production`: use a worktree, and keep junctions out of it.
- Force-push `main`, or commit an engine tree on it.
- Delete a branch or a repo before its content is proved to exist elsewhere.
