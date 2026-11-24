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
