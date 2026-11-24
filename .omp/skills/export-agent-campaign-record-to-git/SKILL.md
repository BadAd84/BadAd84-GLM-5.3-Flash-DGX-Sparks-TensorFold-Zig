---
name: export-agent-campaign-record-to-git
description: "Campaign patches/tests/reports only in ignored work/: export to a committed, rebuild-proven record without captured traffic."
---

# Export an agent campaign's work/ folder into a committed record

When: a multi-lane campaign (speed hunt, RE campaign) left its patches, tests, mutant runners, benches and lane
REPORTs only in the repo's ignored `work/<campaign>/`. One disk failure loses all of it.

## Procedure
1. **Target**: a repo folder mirroring `work/<campaign>/`'s relative paths (glm5.3-flash-dev: `scripts/glm53/v110/hunt/`),
   so every stack-list entry and registry path stays valid.
2. **Copy mechanically, never by eye**:
   - every stack list, every patch any list names, plus every top-level lane `*.patch` (dropped ones are the measured
     negatives the notes cite);
   - for EVERY registry entry (CPU and GPU): its script plus its closure, computed by import scan + path-literal scan +
     lane-wide filename match; report unresolved names;
   - lane REPORT.md and logs they cite (under 1 MB), tooling (build, kit, deploy scripts), registry sources and results;
   - never: trees, builds, extension caches, mutant scratch, archives, dumps, files over 2 MB. A lane may try to copy
     whole engine trees "for tests": refuse, they are rebuilt at run time.
3. **What git must not hold** goes to `restore_inputs.py` + `inputs/manifest.json` (sha256 per file), restored with
   `--from <old work root>` before a run, every laid path in the record's `.gitignore`:
   - base and lane reference trees (rebuilt from the base plus small overlay blobs);
   - large inputs;
   - ALL captured traffic and copied private docs (recorded agent/omp request bodies, prompt corpora built from other
     repos' docs). Measured 2026-11-01: a captured agent turn held the live LiteLLM router key, a copied doc a bearer
     token.
4. **Relocation**: if the root moved deeper, rewrite path climbs (`parents[N]`, `"../.."`) and absolute
   `work/<campaign>` paths mechanically at copy time; record the edit count in the README. LF for `.sh/.py/.list/.md`;
   never touch patch bytes (report any CRLF patch).
5. **Prove from the COPY** (point every tool at the new folder, not work/):
   - rebuild the newest image's tree from the copied list; compare every laid file's sha256 with the deployed kit's
     expected list: N of N equal;
   - run the registry's CPU set from the copy: verdicts equal the original's entry for entry. The first run usually
     fails on missing inputs (36 of 112 in the hunt: tokenizer, safetensors headers, vendored packages, reference
     trees, path climbs): add each, rerun until equal;
   - delete every laid input afterwards.
6. **Gates before the commit**:
   - credential scan over `git ls-files -co --exclude-standard`, printing kinds and lines, never values
     (glm5.3-flash-dev `scripts/check-secrets.sh`);
   - pyflakes: classify every undefined-name finding by reading the code. pyflakes falsely flags a name a nested
     function or lambda reads when the enclosing function later `del`s it; allow-list the exact finding line with a
     reason (stale entries must fail the gate). Never edit copied lane files to quiet a gate.
7. **Merge older partial copies**: list files only they hold (`comm -23` of the two file lists), copy them in (current
   work/ versions), `git rm` the old copy, repoint every doc reference; leave no second copy.
8. **README in the record**: image-to-list map (matched against each deployed kit's `stack.list`), the rebuild and
   registry commands, what git does not hold and how it is restored, scripts that read outside the folder.
