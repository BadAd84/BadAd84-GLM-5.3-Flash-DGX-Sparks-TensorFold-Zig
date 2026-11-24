---
name: check-if-an-upstream-release-gain-is-already-in-our-pin
description: "Before porting or celebrating an upstream release note, prove whether the named improvement is already in our pinned base (introducing commit vs pin date, default-on status, matching TP/hardware) and what genuinely postdates the pin"
---

# Is an upstream release's improvement already ours?

Use when the owner or a reviewer reports that upstream shipped a gain ("new kernel, N% faster") and the question is whether we lack it. A release number is not evidence about our pin: a changelog line can sit under "Unreleased" for weeks, and a release can be mostly other backends.

## Procedure

1. **Fetch and date the three objects.** `git fetch <url> main:refs/remotes/up/main` and `git fetch --tags`; print `git rev-parse --short=9 up/main`, the tag's commit date, and our pin's date from `scripts/config.sh`. Then `git merge-base --is-ancestor <pin> <tag>`: it tells you which direction the gap runs.
2. **Find the code, not the prose.** Read the release body and the changelog section (`git show <tag>:CHANGELOG.md`), take the PR number, then locate the mechanism by symbol: `git log --format='%h %cI %s' -S "<symbol>" <pin>..up/main -- <paths>` (empty means nothing since the pin touches it) and `git log --format='%h %cI %s' -S "<symbol>" <pin> -- <paths>` (shows the commit that introduced it and when).
3. **Compare the introducing commit's date with the pin's date.** Earlier than the pin means we already have it, whatever the release says.
4. **Check the switch.** Is the feature default-on in the pin (`git grep -n <NAME> <pin> -- <path>`, plus the registry row that states its default)? A default-off upstream feature we never set is a real gap; a default-on one already runs in our recipe.
5. **Check the measurement's shape.** TP width, GPU model and prompt length decide whether the quoted percentage transfers: 13.8% at TP=4 on four GB10s says nothing about TP=3 on three.
6. **List what genuinely postdates the pin for the subsystem we care about**: `git diff --stat <pin>..up/main -- <subsystem paths>`, then read the few commits that are speed-relevant. Separate "new lever" from "parameterisation", "other backend", and "behaviour fix".
7. **Decide and record**: port, or already-had, or needs-weights/owner-call; write it into the repo's overnight/ledger with the commit ids and dates, and put the untouched subsystems (e.g. Metal on a fleet with no Macs) in one line so the next reader does not re-derive them.

## Traps

- Grepping the changelog's *section* is not enough: entries move between Unreleased and a release when a tag is cut, so the tag date is not the code date.
- `git log -S` needs a symbol or literal that exists in the code, not the PR number; the changelog commit that names a PR lands separately from the code commit.
- Re-seating onto a new tag is only worth it for a named reason; a same-day re-seat for a backend we do not run wastes a full gate.
- An upstream gain that is already ours does not close the question of whether OUR switches extend it further (our patch may be a superset), and it does not close the overlap ledger: check whether the mechanism duplicates one of our patches and whether that patch is now a retirement candidate.
