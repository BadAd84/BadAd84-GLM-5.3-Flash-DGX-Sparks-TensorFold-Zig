# REPORT: the 47-patch series re-seated from the tip 46c6ee229 onto upstream main fa13df5dd

Nothing outside `work/reseat2/` was written, nothing committed or pushed, nothing compiled on this machine.

## Placed

- Oracle: the rebuilt old chain reproduces `1fd680b2b681e80d1e40492f881b444602a5bc89` (ORACLE MATCH).
- All 47 patches placed on `fa13df5dd1fdd23ada775510a464c9aa03a39e09` (tree `efd5bccea8b50fc9c98966f4a9f4161d2a6864d7`),
  none absorbed, no number vacated beyond the old 0011. Final tree `19c545b35927ecbf59924852e6d5d07465c2bfe7`, computed three ways: index apply of the
  emitted files, worktree apply on a pristine checkout (`verify.py`), and the gate host's own `SG id` (below).
- 38 placed clean as text; hand-resolved: 0006, 0007, 0012, 0013, 0019, 0020, 0023, 0024, cache-salt 0001;
  amended after a check: 0007 (twice: a test that read undefined fields; then 0007's own doc lines and `Mode.all`
  test, first dropped by me and restored) and pr1411 0001 (kept `lane_host.zig` at 600 lines, which the checkpoint's
  lean step caught). `linecheck.py` shows every other patch's added and removed lines identical to the tip's.
- Packages: `out/patches/{engine,pr1411,cache-salt,learn-starts,solo-cuts,disk-any-position,restore-held}/` with the
  old names and headers, `RECORD.md` (base, tree in and out, the gate) and `SHA256SUMS`; the old packages carry no
  `apply.sh`, so none was made. Not installed anywhere.

## OVERLAPs (upstream's code intact, ours alongside with its default unchanged, one image)

| overlap | upstream (its switch) | ours (switch; recipe) | window on one image |
|---|---|---|---|
| drafter MLP split | `TF_GLM_DRAFT_SPLIT=1`, `5df57c025` (settings parser, default 0) | `TF_GLM_OVN_DRAFT_MLPSPLIT=n` (0006; prod.env sets 4) | ours: the recipe; upstream's alone: `TF_GLM_OVN_DRAFT_MLPSPLIT=0 TF_GLM_DRAFT_SPLIT=1`; never both |
| decode-window index scores | `TF_GLM_DSCORES` (default on), `c1bfb2853`, `16ead2656`, `76e0c0b27`: our mechanism, adopted from MiaAI-Lab 0091, from 8 rows (4 from 2,048 blocks) | `TF_GLM_INDEX_CUDA=all` + `TF_GLM_INDEX_DECODE_FROM` (0007), `TF_GLM_OVN_DECODE_INDEX` (0012): any row count, depth gate; recipe: unset | ours off: both unset (upstream decides); ours on: `TF_GLM_INDEX_CUDA=all` or `TF_GLM_OVN_DECODE_INDEX=n`; upstream's off: `TF_GLM_DSCORES=0` |

No new switch was needed for either. The overlap scan over the 206 upstream commits (`overlap.txt`) found no other
same-job code: upstream's prompt-side sparse files changed only through the decode-index commits, so 0019 and 0020
have no prompt-side overlap.

## OPEN (facts for the decision pass; nothing retired here)

- With `TF_GLM_INDEX_CUDA=all`, decode windows now take upstream's `scores` (`score_tiles` tiles a CTA) where the
  tip's took 1 tile a CTA: same bytes, speed may differ; restoring it would change an upstream function.
- Dependencies of knob-unset patches that active ones need (DECISIONS.md, per patch): 0019 is a build prerequisite of
  active 0020; 0024 (its own knobs unset) chooses the kernel active `ONEPASS_PIPE=1` runs (`x.exact`, 0020 had
  `x.chunk`) and carries the default-path glue refactor; 0021's argument sits on the forward's default `bodyProfile`
  call; 0004 is the `cuda.ovn` registry every OVN knob is read through.

## Gate evidence

Checkpoints so far (gate host paperclip, x86_64; `--jobs 4 --max-load 90 --mem-max 8`):

- patches 1-10, tree `7d0a8d54cbca` (before 0007's amends): `check` 8/8, `fmt` rc 0, `ctest` 10/10, lean base 7,306 files 168 problems, head 7,316 files 168, 0 new.
- patches 1-40, tree `75f37deb50a9` (before the pr1411 amend): `check` 8/8, `fmt` rc 0, `ctest` 10/10, `pdl` 3/3, `contract` 271/271, `test-cuda-host` 446/446 steps, 8,053 of 8,096 tests (43 skipped, 0 failed); lean 1 new: `zig/src/core/lane_host.zig: over 600 lines`, fixed by `amend 39`.
- patches 1-40 corrected, tree `4719d486cd5f`: `fmt` rc 0, lean base 7,306 files 168, head 7,370 files 168, 0 new.

The full gate is IN FLIGHT: run `sg-20261121-100241` (started 2026-11-21T10:02:52Z on paperclip). Exact next commands:

    python scripts/spark-gates.py wait --host adam@paperclip.ots-int.net --run sg-20261121-100241
    python work/reseat2/mktar.py            (only after VERDICT PASS)
    python work/reseat2/records.py work/reseat2/gate.txt

## Source tarball (made after the gate passed)

Not made yet: the tarball is made only after the full gate passes (`python work/reseat2/mktar.py`).
