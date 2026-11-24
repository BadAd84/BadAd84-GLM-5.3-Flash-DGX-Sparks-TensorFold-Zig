# Provenance: files in this repo that came from another project

Answer to one question, for this repo only: which files here contain another project's code, and what
must this repo's agent do about each under the no-copying rule (`AGENTS.md`, "No copying"; fleet
`RULES.md` section 8). The repository's own agent owns this list; it is not tracked from another repo.

## How each line was found

## Method and the search commands

Tracked files only (`git ls-files`). Two regions scanned:

1. The header region (first 30 lines) of every tracked source, kernel, script and doc file.
2. The added (`+`) side of every tracked `.patch` and `.diff`, including each numbered package's
   new-file headers, because a file that entered through a patch is the case at hand.

Search commands actually run (one per repo, `$R` = the repo dir):

```
git -C "$R" grep -nIE '(^|[^A-Za-z])(From[: ]|Copyright|Apache|MIT License|BSD-|derived from|adapted from|based on|port(ed)? of|port(ed)? from|MiaAI-Lab|Marlin|llama\.cpp|vLLM|FlashInfer|CUTLASS|Triton|cuBLAS|NVIDIA Corporation|taken from|copied from)' -- .
```

then narrowed to two high-signal patterns, applied to the header region of tree files and the `+`
lines of patch/diff files:

```
attribution : (From MiaAI-Lab|Mia's AI Lab|jayleaton|Jay Leaton|Arminova|manuel1618|BertholomusAI|drowzeys|wojo|eleqtrizit|mxfp0|Jason Cook|Turboderp|ExLlama|ExLlamaV3|lukaszraczylo|CUTLASS|FlashInfer|Marlin|llama\.cpp|vLLM)
licence+copy: (Copyright (\(c\) )?20[0-9][0-9] [A-Z]|SPDX-License-Identifier|Apache-?2\.0|Apache License 2\.0)
```

High-signal transcript: `work/provenance/highsignal.json` (123 hits); full marker transcript:
`work/provenance/raw_hits.txt` (3669 raw lines, most noise). Extractor: `work/provenance/extract.py`.

## The false-positive rule, with a worked example

Marker text alone is not a hit. A line is a HIT only when it names a party OUTSIDE these five repos
as the origin of the code the file contains. The test is provenance, not vocabulary.

Example line that is NOT a hit:

```
scripts/glm53/v110/hunt/HuntMatmulExperts/pt/tensorfold.orig/families/glm5_next/cuda/exl3.cu:3
// Format (see exl3.py, after ExLlamaV3, MIT, Copyright (c) 2025 Turboderp): a 16x16 tile is ...
```

Not a hit because the sentence cites ExLlamaV3 as the origin of the EXL3 **tile format** (an interface
the kernel reads and writes), and the file is upstream TensorFold's own `exl3.cu` (the `.orig` path is
a verbatim copy of the pristine tree's file). Citing a format we implement is the OURS arm, not the
copied-source arm. The same rule clears our knobs whose citation is a GitHub issue, and our
`derive*.py`/`score*.py` whose "derived from" names our own rows.

The other false-positive family: "copied from" naming OUR OWN file. Example:

```
patches/engine/0020-onepass-pipe.patch:94
+// Copied from glm_onepass.cu for the measurement pipeline (glm_onepass.pipe.cuh), separate namespace; keep in sync.
```

Not a hit: `glm_onepass.cu` is ours, in the same series.

## Notice state across the five repos (the baseline for DECLARED / UNDECLARED)

- No repo tracks a `THIRD_PARTY_NOTICES`, `NOTICES`, `LICENSE`, `LICENSES/` or `COPYING` file
  (checked: `git ls-files | grep -ciE 'THIRD_PARTY|NOTICES|^LICENSE|^LICENCES/|COPYING'` = 0 in all five).
- The ONLY third-party notice anywhere is inside Qwen patch `0029`, which EDITS upstream TensorFold's
  own `THIRD_PARTY_NOTICES.md` (`diff --git a/THIRD_PARTY_NOTICES.md b/THIRD_PARTY_NOTICES.md`, an edit
  of a 459-line upstream file, not a new file). So the notice exists in the built tree but not in our repo.

Therefore, for classification below:
- **DECLARED** - a notice or a patch RECORD/section names the file and its licence/copyright.
- **UNDECLARED** - the file's own header names another project, but no notice or RECORD entry carries it.
- **OURS** - no external-origin marker in the file; the negative search that found nothing is shown.


## This repo's findings

### 2.1 UNDECLARED - two engine patches whose header names an outside project, no RECORD entry

| | |
|---|---|
| Path | `patches/engine/0012-index-sched-decode-pools32.patch` (the added file's header line) |
| Header line | `patches/engine/0012-index-sched-decode-pools32.patch:165`: `+// A decode window's top-K pools over chunk CTAs (TF_GLM_OVN_DECODE_INDEX); port of prod-src select_split (Apache-2.0).` |
| Licence | Apache-2.0 (declared); `prod-src` is not a repo name - the actual upstream of `select_split` is unstated |
| How it entered | numbered engine patch 0012 in the live series (`patches/engine/`) |
| Our changes marked? | Not stated in the line; the header does not say what changed |
| Notice | None; `patches/engine/RECORD.md` does not name `select_split`, `prod-src` or this patch's origin |

| | |
|---|---|
| Path | `patches/engine/0031-glm-exl3-x3-decode.patch` |
| Header line | `patches/engine/0031-glm-exl3-x3-decode.patch:226`: `+// TF_GLM_OVN_X3_NC: grouped_body's sums with exl3.cu dec_kernel LD 1's 16-byte loads (Apache-2.0; jayleaton 0580).` |
| Licence | Apache-2.0; credited to `jayleaton` patch `0580` |
| How it entered | numbered engine patch 0031 in the live series |
| Our changes marked? | Not stated |
| Notice | None; `patches/engine/RECORD.md` does not name jayleaton or 0580 |

Both: **UNDECLARED** (in-file header only, no notice or RECORD entry). A doc records a related but
different adoption: `docs/audit-2026-11-12/reseat-main-fa13df5/REPORT.md:24` marks decode-window index
scores as "our mechanism, adopted from MiaAI-Lab 0091".

Owner decision lines: keep with notice (add the source repo, licence and copyright line to the patch
header and a `THIRD_PARTY_NOTICES` entry), OR rewrite from TensorFold's own spec, OR remove with the
lever. Do not decide.

### 2.2 OURS

Everything else in the tree is ours; the marker search's other hits all name our own files
(`scripts/streams.py:4` "Copied from the OTS repro lanes"; `derive92.py`/`score98.py` "derived from"
our own rows; `queue85.sh` "copied from queue79.env"). No external project is named as a code origin
outside the two patches above and the two docs (2.1).

---

## Correction, re-derived independently (2026-11-24)

The table above lists two engine patches. Re-running the method's own second pattern over the live series finds four,
and the two extra are the same kind of hit, not dictionary noise:

| | |
|---|---|
| Path | `patches/engine/0021-kda-chunked.patch:5` |
| Header line | "production's chunked (WY) KDA chain (from glm5_next/cuda/kda_chunk.cu, Apache-2.0, ..." |
| Licence | Apache-2.0 named; `glm5_next` is an engine tree, not identified further |
| Notice | None |

| | |
|---|---|
| Path | `patches/engine/0022-mm-knobs.patch:135` |
| Added line | `+// BANDS: qmm_prefill.cu's tile_of order (prod-src cuda/kernels/qmm_prefill.cu); CLUSTER: ...` |
| Licence | not stated on the line; `prod-src` is the same unnamed origin `0012` cites |
| Notice | None |

So the set of engine patches whose own text names an outside origin is `0012`, `0021`, `0022` and `0031`, and any
decision taken for the first two has to cover these as well. The same three options apply to each, unchanged.

## Files here that came from another engine or library

- **Qwen** `fn_int4.cu` and its host companions: MiaAI-Lab's dual-Spark recipe (an engine recipe). [DECLARED]
- **GLM Zig** engine patches 0012 (`select_split`) and 0031 (jayleaton 0580): another engine's kernel
- **GLM Python** `kept_reasoning.py` (jayleaton 0620 on 6 files; also MiaAI-Lab recipe 0036's file kept
- **DeepSeek** `ots-patches/recipe/` (MiaAI-Lab's 48 recipe patches, i.e. a whole engine's patch set)

## The decision, per file (the owner decides; this page lists the options)

- **Keep with notice**: the licence, the upstream copyright line and a `THIRD_PARTY_NOTICES` entry
  land together, which is the exception the rule allows.
- **Rewrite from TensorFold's own specification**, with the reference source closed while we write it.
- **Remove**, with the lever it serves retired in the same change.
