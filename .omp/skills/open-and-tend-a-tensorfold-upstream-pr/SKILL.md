---
name: open-and-tend-a-tensorfold-upstream-pr
description: "Opening and maintaining a PR against ashhart/TensorFold upstream from our ai-engine fork: gates, traps, identity, no force-push."
---

# Opening and tending a TensorFold upstream PR

Our fork `BadAd84/TensorFold` (SSH push works; the OAuth token lacks `workflow` scope, so HTTPS pushes of
branches containing `.github/workflows/` are rejected). Upstream `ashhart/TensorFold`, `main` only, one
change per PR.

## Before opening

1. Read `CONTRIBUTING.md` in full plus `docs/kernel-contract.md` and `docs/atc/SKILL.md`. Arithmetic or
   backend changes need an ISSUE first; bug fixes do not.
2. Cut the branch from the CURRENT upstream tip, not from our fork's base. Verify with
   `git merge-base` and `rev-list --count <base>..upstream/main`; ours was 202 commits stale once.
3. One commit, authored `BadAd84 <BadAd84@users.noreply.github.com>`, signed. Squash before pushing.
4. `atc doctor --json`, `atc check <issue> --json`, `atc claim <issue>` (installed via
   `npm install -g github:ashhart/ATC`), and `atc overlap --json` before any push.

## The gates that actually reject

- **Lean check: use `tools/zig/lean_new.py` with a base list and a head list, never `lean_check.py`'s single
  total.** A file can add 28 findings while the total still reads the baseline (measured). Fix = comments are
  SINGLE lines of at most 120 columns; one finding per line of a multi-line block.
- **600-line module cap.** Upstream sits at the limit (`cuda/roce.zig` was 597), so a feature has to move a
  cohesive unit into a new module (`roce_abi.zig`, `roce_region.zig`).
- **`fmt` is its own check.** `zig fmt --check` locally; a formatting fix is still a commit.
- **`zig/glm_contract_host.zig` is the only GLM host test root and it imports `core` only**, so `test` blocks
  in family files such as `dflash_load.zig` are never compiled or run. An A/B on such a test comes back green
  no matter what the mutant does. Prove a test runs before trusting it.
- **Their CI runs in the BASE repo for a fork PR** and mails the author. Keep Actions disabled in our fork
  (`gh api -X PUT repos/BadAd84/TensorFold/actions/permissions -F enabled=false`) so it adds no noise.

## Never

- Never force-push an open PR, CI failures included. Fixes are additional signed commits.
- Never leave a new file out: `git commit -a` skips untracked files, so the commit can reference a module it
  does not contain while the worktree build still passes. Check `git show --stat` after committing.
- Never put an internal ticket id or private domain in the source or the PR body.

## Receipts

Their "Performance receipts" section wants `tools/bench_openai.py` and `tools/bench_concurrent.py` with the
same checkpoint, greedy prompts and `failed 0 / unmeasured 0`, plus a memory figure (peak RSS; `nvidia-smi`
reports N/A on GB10 unified memory) and `docs/receipts/<name>/` with SHA256SUMS. Their own
`benchmark_server.zig` runs the child server `--parallel 1 --prompt-cache-gib 0`; a pooled server is also
legitimate but say which, and state the stream count beside every number.
