# Verification of the Kimi K3.1 review (2026-11-21)

The owner asked Kimi K3.1, through the OTS router's `kimi3.1-OR` alias, to review the patch series and the session record and say what could be improved, which
rejected levers were recoverable, and where the rest of the speed is. Its report is `docs/audit-2026-11-12/kimi-review-k3.1-2026-11-21.md`, copied verbatim. This file records what of
it was checked here, how, and what was done, so no claim in it is taken on trust. A second reviewer (Opus 4.8) ran the same brief in parallel and its report is separate.

## Its central numbers, recomputed here

The gap table reproduces exactly from the committed rows, with the field the campaign's own scorer reads (`agg_tok_s`, `scripts/queue-scores/score91.py`), from
`docs/audit-2026-11-12/queue-rows/queue91/f91-c/dec-mn{1,2}/P{n}.jsonl`, six rows a cell. **Its production column, however, was not in that field.** The five values it compared against
(83.43 / 91.07 / 119.97 / 111.99 / 136.18) are each round 2's `decode_agg_tok_s` from production's own run (`work/drafter-lever/spark1/bench/pyprod/P<n>.out`, which writes both
fields per round), while the Zig side is a six-row mean of `agg_tok_s`. A cross-check flagged it and the source confirms it. Like for like, production's mean over its three rounds in
the same field, the table is:

| streams | production, `agg_tok_s` mean of 3 rounds | our mean (6 rows) | gap |
|---:|---:|---:|---:|
| 1 | 81.733 | 82.715 | +1.20% |
| 2 | 89.220 | 85.847 | -3.78% |
| 4 | 117.980 | 114.272 | -3.14% |
| 6 | 114.783 | 114.680 | -0.09% |
| 8 | 131.280 | 125.318 | -4.54% |

(The first attempt at this check used `decode_agg_tok_s` on OUR side and disagreed by about 2% at every level; the scorer's field is `agg_tok_s`, so the reviewer was right about our
side and the check was wrong. The reviewer was then wrong about production's side in the same way, and the cross-check caught it. Recorded because a number is only meaningful with its
field, its boots and its reader named together: one stream is 1.2% ahead rather than 0.86% behind, six clients is level rather than 2.4% ahead, and the eight-stream deficit is 4.54%,
not 7.98%, against production rounds that themselves span 129.36 to 135.77.)

## What the cross-check changed in the review's ranking

A bounded second review (mythos5.2) tested Kimi's nine ranked speed items against the record, not the patches, and returned 7 SUPPORTED, 0 STALE at a primary claim, 2 WRONG, in
`work/crosscheck/GAP-CROSSCHECK.md`:

- **Item 1 as ranked is wrong.** Its 11.90 / 12.99 / 13.37% is the stock ladder's gain from upstream #3697 (a stock user's cold prompt), not ours to bank: our recipe already reaches the
  staged tiles through `KDA_PAD=1`, and the open question, our `=1` against upstream's per-rank default, `docs/KNOBS.md` sizes at "0.3 ms of a 61 ms round, 0.5%" with a likely bf16
  numerics consequence. It should not be ranked first on that number.
- **Item 4's 128.3 ms dense-attention prize is a cross-pattern subtraction.** The 174.5 ms in 88 launches is real and worth kernel work; the 46.2 ms is the sparse pipeline on the
  following 2,048 rows, so subtracting them compares dense-with-all-keys against sparse-with-selected-keys on a different row range. It needs sizing offline before it holds a rank.
- The other seven items stand as Kimi ranked them, with item 2's candidate gains and its queue95 clause superseded by section 81.

## Its concrete code findings, checked against the patch text

| finding | status | what was checked |
|---|---|---|
| 0019 and 0020 compute a full "next" QK tile after the final live tile and drop it | **CONFIRMED** | 0019 comment at the tile loop says the last tile's next scores "run on its own buffer and are dropped"; 0020 has the same loop with `ktn` pointing back at the live buffer. Size is one tile of `ntile`, which the reviewer bounds at 1/16 to 1/64 |
| 0024's `tf_glm_hc_partial8_pdl` calls `partial8<false>`, so the PDL weight-preload path is dead | **CONFIRMED, and wider than reported** | 0024:395 and 0024:402 both instantiate `<false>`, and `grep partial8<true>` over all 38 patches returns nothing: the specialisation is never instantiated anywhere in the series, so the template branch is dead code globally |
| 0023 runs an identity tail block for tiles past the last live key | **CONFIRMED as an identity** | the block multiplies `o` by 1.0, runs `mma16816` with zero operands and does `l*1.0+0.0`; its own comment says "o and l are unchanged". Removing it is exact. Its size is not bounded by the patch text alone: it fires only when `live && tiles < CH/KT`, and how often that holds depends on the chunk geometry at run time, so it needs a measured cell, not a guessed bound |
| 0012 converts int64 pools to int32 in a separate launch before gathering | **CONFIRMED** | `tf_glm_pools_i32` (`0012:447`) launched at `0012:706` before `ncclAllGather`, then `tf_glm_dsa_tokens_i32`; the producer could emit int32 directly. Removes one launch and 12 bytes an id of conversion traffic |
| 0029 fetches FP8 tiles as eight 8-byte loads instead of four 16-byte ones | **CONFIRMED, with an alignment condition** | the fetch is `*reinterpret_cast<const uint2*>(codes + u * 8)`, one 8-byte load a slot (`0029:193`), while the store is already a `uint4` (`0029:210`). A `uint4` load at `codes + u * 8` covers slots `u` and `u + 1`, so the pairing is sound only when `u` is even and `codes` is 16-byte aligned; the patch text states the 16-byte alignment for the store's destination, not for `codes`. Check the alignment at the call site before cutting this, and byte-compare after |
| 0030 still renders the whole continued turn for the tool-result probe | **CONFIRMED, and my first reading of it was wrong** | `Once.probe` is `renderText(...)` then `encoded(...)`, which calls `r.pieces(...)`: the piece machinery, not the cut. The cut-once-decided path with `r.cut` and `prefixPieces` exists only in `diffGenerated` (`0030:1695-1708`), which the rewind path uses. So `continuedLen` gets the pieces but not the early exit, which is what the reviewer said. The size stays INFERENCE until a prompt-bench row |

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
