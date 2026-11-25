# The settings upstream added between our pin and `ea37382cb`

Forty-five settings appear in `zig/src/platform/environment.zig` between `fa13df5dd` (our pin) and `ea37382cb`
(upstream main today). This is the enumeration the owner's step 3 asks for: each one's scope, its default, what its
own description says it does, and a verdict for a GLM-5.3-Flash chat serve.

Most are another family's path - DeepSeek V4.1's calibration suite (twelve rows), FlashNext, Qwen, Gemma 4, Nemotron,
LFM3 - or are outside CUDA (`XPU_CHUNK`, `XPU_CHUNK_SOLO`, scope `.xpu`), and a serve of our model never reaches them.

## Candidates, screened next

| setting | default | what its description says | why it can reach our serve |
|---|---|---|---|
| `TF_GLM_INDEX_SPLIT` | 2048 | a whole prompt position; split from it, 0 never splits | a GLM indexer prompt path, and our prompts are long |
| `TF_GLM_MOE_DIRECT` | see forms | 0 or 1 | a GLM expert path |
| `TF_GLM_WIDE_EXPERT_TILE` | 0 | 0 or 1 | a GLM expert tile width |
| `TF_DFLASH_GRAPH` | 0 | replays DFlash2 holds and live absorbs from CUDA graphs | our drafter is the DFlash2 family |

## Read sites, from the tree at `ea37382cb`

- `TF_GLM_MOE_DIRECT` - `cuda_forward.zig:112`, `read(bool, "TF_GLM_MOE_DIRECT", false)`: **default off**, and its own
  comment says "a decode window's EXL3 MoE without row copies (cuda_moe.direct)". A decode-path lever, which is where
  this serve is bound, so it is the first arm to boot.
- `TF_GLM_INDEX_SPLIT` - consumed in `cuda_engine.zig`, `cuda_follow.zig` and `cuda_forward.zig:182` as "a prompt
  chunk's indexer rows split across the ranks (rank 0's choice)"; default 2048. A prefill path, so its arms are 0 (never
  split) and a larger split point.
- `TF_GLM_WIDE_EXPERT_TILE` - **no consumer**: nothing outside the settings table and its test reads it. A registered
  row with no reader is inert, so it needs no boot.
- `TF_DFLASH_GRAPH` - read only in `families/qwen3_5/cuda_draft_graphs.zig:10`, the Qwen family's drafter, not the GLM
  one; rejected with `TF_CUDA_POOL_AFTER_WARMUP` for the same reason.

## Rejected before screening

- `TF_MTP_TREES` (default 0): sampled MTP tree drafting - a mode that changes output tokens, which upstream takes on
  no advertised path and we do not want either.
- `TF_DFLASH_QL_SPAN` (default 0): drafts a ModelOpt NVFP4 or FP8 head over DFlash2 spans; our head is EXL3.
- `TF_CUDA_POOL_AFTER_WARMUP` (default 0): sizes an idle **Qwen** DFlash2 device pool, so not our path.
- `TF_DSV41_*` (twelve rows), `TF_FLASHNEXT_*` (five), `TF_FN_GX_GATEUP_MB2`, `TF_Q27_*` (three), `TF_Q35_*` (two),
  `TF_QWEN*` (five), `TF_GEMMA4_ARGMAX_GRAPH`, `TF_NEMOTRON_WIDE_ROUNDS`, `TF_LFM3_METAL_WARM_TURNS`,
  `TENSORFOLD_PULL_CONNECT_SECONDS`, `TENSORFOLD_PULL_STALL_SECONDS`: another family, another accelerator, or the
  weight-pull transport rather than the chat path.
- `XPU_CHUNK` / `XPU_CHUNK_SOLO` (defaults 64 and 2048): scope `.xpu`, not CUDA.

## How the four are screened

One boot an arm, the control in the same directory, the same five levels and the same env as `dev.env`, digests
compared: a candidate that changes replies is rejected before its numbers are read, as `TF_GLM_OVN_KVB8` was.

## The screen, three of four arms (2026-11-25, image `glm53-zig:reseat-ports`)

Decode aggregate, tokens a second, a fresh boot a level, `SPLOTS=4 CTX=1048576 KNOBS=dev`:

| arm | 1 | 2 | 4 | 6 | 8 |
|---|---|---|---|---|---|
| `screen-ctl` | 74.9 | 82.4 | 102.2 | 101.3 | 103.9 |
| `screen-moe1` (`TF_GLM_MOE_DIRECT=1`) | 75.4 | 83.7 | 100.9 | 98.7 | 104.2 |
| `screen-idx0` (`TF_GLM_INDEX_SPLIT=0`) | 74.7 | 81.3 | 102.9 | - | - |

`moe1` reads +0.7, +1.6, -1.3, -2.5 and +0.3 percent against the control, and `idx0` reads -0.4, -1.3, +0.7, +1.4 and
+9.9 percent. The `moe1` row is inside the spread this serve shows between boots at the high levels, so nothing is
promoted on it. The `idx0` eight-client cell is the only reading outside noise in either arm, and one boot cannot tell a
real gain from a noisy cell, so an A B B A at level 8 only is queued behind the screen (`~/work/queue-abba-idx8.sh`).
Reading it as +9.9% before that rerun would be the trade the repo's rules forbid: a single cell, one boot.

## All four arms (screen closed 01:05)

| arm | 1 | 2 | 4 | 6 | 8 |
|---|---|---|---|---|---|
| `screen-ctl` | 74.9 | 82.4 | 102.2 | 101.3 | 103.9 |
| `screen-moe1` | +0.7% | +1.6% | -1.3% | -2.5% | +0.3% |
| `screen-idx0` | -0.4% | -1.3% | +0.7% | +1.4% | +9.9% |
| `screen-idx4096` | +1.3% | +2.0% | +0.5% | +3.6% | +4.2% |

`TF_GLM_INDEX_SPLIT=4096` is the only arm positive at every level, and it grows with concurrency, which is the shape a
prefill change has rather than the shape noise has. `TF_GLM_MOE_DIRECT=1` is inside the spread at every level. Two ABBAs
at level 8 are queued in series to confirm the two index cells: `~/work/queue-abba-idx8.sh` then
`~/work/queue-abba-idx4096.sh`, the second waiting on the first's done marker so they never share the box.

The historical note stays true:, which is inside the spread this serve shows
between boots at the high levels, so nothing is promoted on it yet and its four and six cells get an ABBA rerun first.
`idx0` tracks the control at the three levels it has.

Note the control is lower than the dev numbers measured earlier on `ea37` (74.9 against 85.0 at one client). This image
carries the ports and the restored kernel surface, so the screen's comparison is against its own control, never against
that older table.

## The idx0 eight-client cell is CLEARED (ABBA, 2026-11-25)

A B B A at level 8, one boot a cell, image `glm53-zig:reseat-ports`, `INDEX_SPLIT=0` against the control:

| cell | decode tokens a second |
|---|---|
| A1 (control) | 139.0 |
| B1 (`INDEX_SPLIT=0`) | 139.3 |
| B2 (`INDEX_SPLIT=0`) | 138.5 |
| A2 (control) | 139.3 |

The control alone spans 139.0 to 139.3 and the arm sits inside it, so the screen's +9.9% at that level was a noisy
single cell and there is no gain to record. This is the confirmation working: one boot suggested +9.9%, four boots show
nothing. The `idx4096` arm is under the same test now.
