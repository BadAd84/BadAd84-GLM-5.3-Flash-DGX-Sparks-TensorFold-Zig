---
name: propagate-a-rule-to-all-engine-repos
description: "Add or update one fleet rule across every OTS TensorFold engine repo's AGENTS.md and ~/.omp/agent/RULES.md, with signed per-repo commits and pushes, and place any per-repo worklist the rule generates inside each owning repo; use when the owner says to put a rule in all our engine repos."
---

# Propagating a rule to every engine repo

Use when the owner asks for a rule in "all our engine repos" or a cross-repo convention change, and when
a fleet-wide sweep produces a per-repo worklist the owner wants each repo's agent to own.

## Repos
Under `C:/Users/Adam/Gitea`: `Qwen3.8-Flash-Next-DGX-Sparks-TensorFold-Zig`,
`GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig`, `GLM-5.3-Flash-DGX-Sparks-TensorFold-Python-TP3`,
`DeepSeek-V4.1-Flash-DGX-Sparks-TensorFold-Zig-TP2`, `Inkling-2-Mini-DGX-Sparks-TensorFold-Zig`.
Re-list with `ls -d *TensorFold*`; new family repos appear.

## The rule itself
1. The fleet text goes in `~/.omp/agent/RULES.md` in the section that owns the subject, edited IN PLACE (never
a new dated block).
2. Per repo, `read` the lines around `## Conventions` (each repo has exactly one), then `edit` the same
anchor `## Conventions` to prepend the rule section. Keep the paragraph identical across repos except
repo-specific fallbacks (e.g. a repo with no patch series records a file's origin in its build receipt).
3. Commit each repo separately: signed, owner identity, explicit path. Use ABSOLUTE paths for `git -C` when
the shell's cwd is another repo (relative `git -C <sibling>` fails with "cannot change to" and costs a
round trip). Message via `-F` a file, never `-m`.
4. Push each: `git -C <abs> push origin HEAD`; report the fast-forward line per repo.
5. Check dirty worktrees first (`git -C <abs> status --porcelain`); stage only `AGENTS.md` and leave other
sessions' files alone.

## The per-repo worklist the rule generates
A rule whose subject is "what already exists" needs an inventory, and the owner wants that inventory INSIDE
the owning repo so that repo's agent actions it:
1. Run the sweep centrally (one lane), then split its report into one page per repo: shared method and
   search commands, the false-positive rule with a worked example, the baseline, then that repo's findings,
the engines-or-libraries list, and the options per file. Do not hand a repo a page of another repo's work.
2. Write it as `docs/PROVENANCE.md` (or the subject's name) in each repo, commit signed and push, then add
   ONE sentence to that repo's rule text pointing at the page, so rule and list are found together.
3. Keep the decision with the owner. Per file the options are: keep with notice (licence line, upstream
   copyright line and a `THIRD_PARTY_NOTICES` entry together), rewrite from our own specification with the
   reference closed, or remove with the lever it serves.

## Verification
`git show --stat --format='%h %G?' HEAD` per repo: the expected file count, `G` signature, push line printed.
Quote them.

## Traps
- The edit must be a real rule with a mechanical form (where the origin is recorded, what lands with an
exception), not a sentiment; a rule without a detection step needs a follow-up inventory lane.
- A rewrite target duplicated across patch packages needs every form handled: one file's header can differ
  between the r5 re-cut and older packages, so a cleanup that touches one package silently leaves the rest.
- Cross-repo overlapping files: give each repo's page one owner. Never let two agents edit the same page.
