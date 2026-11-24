---
name: fill-upstream-pr-texts-from-gb10-a1
description: Fill a MiaAI recipe batch PR.md gb10-a1 placeholders from a finished gb10_a1.sh run folder
---

# Fill upstream PR texts from a gb10 a1 run

Use when a `gb10_a1.sh` (section A.1) run has finished and the batch's PR.md files still hold `[[gb10-a1: ...]]` placeholders. Repo: glm5.3-flash-dev.

## Procedure
1. Copy the run folder's small artifacts to the laptop: `exact-*.json forms-*.json compare-*.log a1.log summary.txt B*-*.measure.log B*-*.rigmark.log B*-*.json` (scp via the Proxmox jump).
2. `python upstream/fill_a1.py --dry-run <run dir> <upstream dir>` then without `--dry-run`. It computes every fill first and writes nothing unless all evidence exists; exit 1 names the missing artifact. Placeholders are matched whole; the real set is in the PR.md files themselves.
3. `python upstream/compile_batch.py --batch <tag>` must then exit 0 (no `[[...]]` left).
4. Offline test: `scripts/glm53/v110/tests/host/test_fill_a1.py` (fixtures built from the real placeholder set at run time) and `mutants_fill_a1.py` via mutlib.

## Format facts (measured 2026-11-02)
- Only the `stock` and `batch` boots run the timing step; `batchon` and `source` have exactness/memory only, so absent measure logs for them are not an error.
- The measure log's `  prodbench ttft: cases=` line is truncated at 260 chars by the run's tee; the full cases live in the boot's `B*-.json` under `prodbench.ttft.cases`.
- rigmark logs: `<group>: N runs` then `  <i>: <tps> tok/s, TTFT <s>s, ...` lines; medians per group.
- a1.log carries `toolcheck.py: exit`, `needle.py (~200k): exit`, one `rank 0 startup estimate <GiB> within <GiB>` line per boot in boot order, and the memory summaries' low-water MemAvailable lines.
- A clean compare log holds no FAIL/differ/not-equal line; `n_of_m` counts token_sha equality across the two exact/forms records and refuses any mismatch.

## After filling
Commit the filled PR.md files plus the regenerated `BATCH-*-TEXTS.md`; present every title and body to the owner; post nothing until the owner says send (upload via a scratch-clone script that branches `ots-<pkg>` off upstream main, applies each pr.diff alone, one signed commit).
