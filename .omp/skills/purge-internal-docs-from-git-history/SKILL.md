---
name: purge-internal-docs-from-git-history
description: "Move internal-only docs out of a tracked repo, purge them and banned strings from git history, and contain both remotes"
---

# Purge internal docs/hostnames from a git repo's history and both remotes

When the owner rules that internal material (ops docs, notes, hostnames, LAN IPs) must not be in a repo that mirrors
publicly, a working-tree edit is not enough: history holds it. Procedure, measured on glm5.3-flash-dev (2026-11-08):

1. **Working tree first**: create the internal folder (e.g. `int-docs/`), add it to `.gitignore`, move every internal
   file there, scrub banned strings from remaining tracked files (docs use bare names; functional config uses
   placeholders with real values only in per-box untracked copies - keep any gates that count fields happy, e.g. a
   two-placeholder GLM_WORKERS satisfies a worker-count check).
2. **`git mv` stages into gitignored folders** - gitignore never guards explicit adds. After any mv into the internal
   folder, `git rm -r --cached <internal>/` in the SAME action, and check `git ls-files <internal>/` is empty before
   pushing.
3. **Backup before rewriting**: `git bundle create <path>.bundle --all` (14.7 MB for 499 commits; keeps every purged
   object recoverable).
4. **Stash or commit the working tree clean** (filter-repo refuses otherwise), then:
   `git filter-repo --force --invert-paths --path-regex '^docs/(?!README\.md$).*' --path int-docs --path WATCHDOG.yml
   --replace-text <file>` with lines like `ots-int.net==>internal-lan` and `192.168.99.==>192.168.0.`.
   Rewritten commits LOSE their GPG signatures - unavoidable, state it.
5. **Verify from the tool, not the eye**: for every purged pattern run
   `git grep -l "<pat>" $(git rev-list --all) | wc -l` - 0 required. Leftover hits may be in STASH commits (stashes
   carry full tree snapshots): drop the stashes (bundle holds them) and re-check. Current-tree mentions of the
   internal folder's NAME (pointers like "int-docs/GLM53-...") are fine; content is not.
6. **filter-repo removes the remote** - re-add origin (fetch + every push URL, including mirror push URLs) before
   pushing. Force-push is legitimate here: owner-ordered, no open PRs; announce it in one line.
7. **Post-push residue**: old shas stay fetchable until each server GCs. GitHub: dangling commits are served by exact
   sha to anyone until then - make the repo private immediately (`gh api -X PATCH repos/<o>/<r> -f private=true`, anon
   then 404s) and offer delete+recreate for instant purge (needs interactive `gh auth refresh -s delete_repo`, owner
   only). Gitea: LAN-only, so residue is inside the trust boundary; do NOT docker-exec/ssh the Gitea container for gc.
8. **A verification fetch pollutes**: `git fetch origin <old-sha>` re-downloads the purged objects as dangling locally
   - `rm -f .git/FETCH_HEAD; git reflog expire --expire-unreachable=now --all; git gc --prune=now` to re-clean.
