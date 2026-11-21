# Verification of the Kimi K3.1 review (2026-11-21)

The owner asked Kimi K3.1, through the OTS router's `kimi3.1-OR` alias, to review the patch series and the session record and say what could be improved, which
rejected levers were recoverable, and where the rest of the speed is. Its report is `docs/audit-2026-11-12/kimi-review-k3.1-2026-11-21.md`, copied verbatim. This file records what of
it was checked here, how, and what was done, so no claim in it is taken on trust. A second reviewer (Opus 4.8) ran the same brief in parallel and its report is separate.

## Its central numbers, recomputed here

The gap table reproduces exactly from the committed rows, with the field the campaign's own scorer reads (`agg_tok_s`, `scripts/queue-scores/score91.py`), from
`docs/audit-2026-11-12/queue-rows/queue91/f91-c/dec-mn{1,2}/P{n}.jsonl`, six rows a cell:

| streams | recomputed mean | production target | gap |
|---:|---:|---:|---:|
| 1 | 82.715 | 83.43 | -0.86% |
| 2 | 85.847 | 91.07 | -5.74% |
| 4 | 114.272 | 119.97 | -4.75% |
| 6 | 114.680 | 111.99 | +2.40% |
| 8 | 125.318 | 136.18 | -7.98% |

(The first attempt at this check used `decode_agg_tok_s` and disagreed by about 2% at every level; the scorer's field is `agg_tok_s`, so the reviewer was right and the check was
wrong. Recorded because it is the same class of mistake the campaign keeps making: a number is only meaningful with its field and its reader named.)

## Its concrete code findings, checked against the patch text

| finding | status | what was checked |
|---|---|---|
| 0019 and 0020 compute a full "next" QK tile after the final live tile and drop it | **CONFIRMED** | 0019 comment at the tile loop says the last tile's next scores "run on its own buffer and are dropped"; 0020 has the same loop with `ktn` pointing back at the live buffer. Size is one tile of `ntile`, which the reviewer bounds at 1/16 to 1/64 |
| 0024's `tf_glm_hc_partial8_pdl` calls `partial8<false>`, so the PDL weight-preload path is dead | **CONFIRMED, and wider than reported** | 0024:395 and 0024:402 both instantiate `<false>`, and `grep partial8<true>` over all 38 patches returns nothing: the specialisation is never instantiated anywhere in the series, so the template branch is dead code globally |
| 0023 runs an identity tail block for tiles past the last live key | **CONFIRMED as an identity** | the block multiplies `o` by 1.0, runs `mma16816` with zero operands and does `l*1.0+0.0`; its own comment says "o and l are unchanged". Removing it is exact. Its size is not bounded by the patch text alone: it fires only when `live && tiles < CH/KT`, and how often that holds depends on the chunk geometry at run time, so it needs a measured cell, not a guessed bound |
| 0012 converts int64 pools to int32 in a separate launch before gathering | **CONFIRMED** | `tf_glm_pools_i32` (`0012:447`) launched at `0012:706` before `ncclAllGather`, then `tf_glm_dsa_tokens_i32`; the producer could emit int32 directly. Removes one launch and 12 bytes an id of conversion traffic |
| 0029 fetches FP8 tiles as eight 8-byte loads instead of four 16-byte ones | **NOT YET CHECKED** | the claim is specific and cheap to check, but it is a kernel change with a byte-equality requirement; check it when the change is cut |
| 0030 still renders the whole continued turn for the tool-result probe | **INFERENCE in the review** | it is labelled INFERENCE there and needs a prompt-bench row; not acted on |

## Defects it found in this repo's own documents, and what changed

1. **`docs/speed_target.md` presented an 11 November 39-patch table as the current standing**, calling six and eight streams parity and one to four 32% to 39% behind. The current cells
   are the table above. **Fixed:** the Zig table and its conclusion are replaced, the old numbers are marked superseded, and the "shape of the gap" now says the prompt path is the gap.
2. **The same file said the prompt cache is not part of the gap.** Queue98 (47.40% fewer rebuilt rows, 47.16% lower first-token sum, an agent turn 23.7 s to 2.1 s) and queue100
   (34.51% off a warm turn) both contradict it. **Fixed.**
3. **Its port-queue arithmetic was obsolete** ("the other fourteen are absent" against a 19-row table, and several rows since ported or superseded). **Fixed:** the table is marked a
   snapshot and the live ledger named instead.
4. **Its drafter conclusion (26.2 ms a draft pass, "the widest single gap")** is contradicted by later captures (3.40 ms, drafting level). **Fixed.**
5. **`docs/KNOB-PROVENANCE.md` class B overstated three situations** as "proven faster, not turned on" when each has a measured blocker. **Fixed:** the class is renamed "benefit
   measured, adoption blocked" and says so before its table.

## A defect in the recipe it found that this repo had recorded but not resolved

`TF_GLM_OVN_DRAFT_NOISE=1` is in `scripts/env/prod.env` while its own row in `docs/KNOBS.md` says "its 6 and 8 stream sampled cells are open". The repo's rule is that a knob ships only
with no regression at 1, 2, 4, 6 and 8 streams, so this is a genuine gap between the recipe and its proof, not a documentation style issue. It is cheap to close: the knob acts only on
sampled decode, so the arm is a sampled 6- and 8-client pair on the current recipe. Added to the queue list; if the cells fail, the knob comes out of `prod.env` in the same commit as the
cells that fail it.

## What was actioned, and what waits

Actioned in this commit: the four document corrections above, and the review plus this verification committed as records.

Waiting, in the order the campaign can run them: `DRAFT_NOISE`'s 6 and 8 sampled cells; the confirmed exact improvements (0012 int32 pools, 0023 identity tail, 0019/0020 last tile,
0024's dead `<true>` instantiation) as a follow-up on the re-seated series, each with a byte-equality check; then the reviewer's ranked work, which is the prompt path first (per-rank KDA
padding against our `=1`, the prompt-only candidates, absorb and expand, dense first-2048 attention, rank-0 expert balance) and the routed-expert decode kernel after that.
