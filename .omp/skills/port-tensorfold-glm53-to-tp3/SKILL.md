---
name: port-tensorfold-glm53-to-tp3
description: "Port the MiaAI-Lab TensorFold GLM-5.3-Flash EXL3 recipe from its hard-capped 2-rank (--tp 2) to 3-rank tensor+expert parallel on the 3 DGX Sparks, keeping world=2 byte-identical."
---

# Port TensorFold GLM-5.3-Flash to TP=3

The recipe (`MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold`, TensorFold v0.5.0 + 53 patches) hard-caps
`--tp` at 2. Goal: 3 ranks on our Spark triangle, **higher single-stream tok/s than TP=2, no TP=2 regression**.
All WIP lives in `work/tp3port/` and spark1 `~/tp3port/` (STATUS.md, DESIGN.md, the tools,
`b/` patched tree, `a/` pristine). Extracted engine sources in `work/tfsrc/`.

## SAFETY FIRST (learned the hard way - froze all 3 Sparks)
- GB10 has **unified CPU+GPU memory**: exhausting it HARD-FREEZES the box (no ping/ssh/HTTP, needs a power cycle).
- NEVER run a memory-heavy job (model split/convert, big numpy) on a Spark that is SERVING (the live serve uses
  ~115/121 GB, leaving ~5 GB). Check `free -g`; keep peak well under free. Generate rank folders ONLY during a
  window with the serve STOPPED, or on a non-serving box.
- The split tool MUST stream one tensor at a time (peak = one tensor), never accumulate the ~54 GB folder in a list.

## Why uneven-thirds TP + expert parallel (not padding)
GLM dense dims are powers of two, don't divide by 3 (heads 64, lin_heads 64, hidden 4096, vocab 154880,
shared_width 2048, kv_lora 512). But the engine **reduces every block over the HIDDEN dim** (hc_post /
residual_add already loop `range(1, WORLD)`), and the attention kernels are **per-head** (`h = program_id(0)`,
KDA general in H) - so heads split **22/21/21 with NO padding**. The 288 EXL3 routed experts can't trellis-split
at 128/3, so they go **expert-parallel** (96 whole per rank). Our vLLM TP=3 overlay confirms the clean route:
its `_narrow_tp` refuses non-divisible dims. Decode fast path needs `NI==1024`; full-width EP gives NI=2048 and
misses it (general `grouped` path still correct) - measure; if it loses, escalate to expert-HALF parallelism
(576 half-shards / 3, keeps NI=1024).

## The port (string-anchored patchers, world=2 stays byte-identical)
1. **presplit_tp3.py** - standalone splitter -> per-rank `model.rankR.safetensors` + `tp3_meta.json`. Attention
   split BY HEAD (per-head width = axis/heads, all multiples of 64), MLP/shared by 64-group, experts EP, rest
   replicated, lm_head replicated (loader vocab-slices). `--check-src` streams the real ckpt and proves every
   split reconstructs byte-exact (PROVEN: rep 1036, row 490, col 92, expert 148608, experts 288/288, 0 problems).
2. **cli.py**: `--tp` (1,2,3), `--rank` (0,1,2), generalized validation.
3. **glm5_next/__init__.py** `cuda_engine`: tp in (2,3), pass `world=tp`.
4. **engine.py** GlmEngine: `world` param; NCCL/RoceComm over world; `load(world=self.world)`; `draft_world`=1 at
   world 3 REPLICATES the DFlash2 drafter (it asserts heads%world==0; 32/8 don't divide by 3).
5. **weights.py** `load(model_dir, rank, world)`: read rank folder `tp3_meta.json` for per-rank HL/LL/vocab slice +
   OWNED expert ids; EP loops over `owned`; head sliced [vocab_lo, vocab_lo+vocab_n); Weights carries
   HL/LL/vocab_lo/vocab_n/owned_experts. **split.py** RankReader(model_dir, rank, world) loads the meta.
6. **forward.py** (`patch_forward.py`): all 5 HL/LL sites -> `w.HL`/`w.LL`; Buffers `ml`=full at world>=3 (EP),
   `sl`=uneven 64-group third, plan over `len(owned)+1`; **moe_block `_ep_remap`**: remap global picks to local
   (`pick-lo`), non-owned + shared slot -> sentinel `cnt` (the routed kernel skips id>=count, exactly as world 2
   skips shared id c.experts), zero their weight. combine_shared handles the real shared; sum over world = full MoE.
   PROVEN offline: `test_ep_algebra.py` (every pick owned by exactly one rank; 3-rank sum == full top-k MoE).

## Build + correctness (needs a 3-GPU window, serve STOPPED)
- Derived image for fast iteration: `FROM tensorfold-glm53:v0.5.0` COPY the 6 files -> `tensorfold-glm53:tp3`;
  stream to spark2/spark3 (`docker save | ssh ... docker load`).
- Generate rank r folder on Spark r from its local ckpt (25a44fdb and 9eaebb7c are byte-identical mirrors) - but
  ONLY with the serve stopped (see SAFETY).
- 3-rank launch: generalize `nodes.sh` from one worker to N (one per ring edge; each rank's NCCL_IB_HCA = its TWO
  ring ports = dual-rail, which TP=2-on-triangle can't; ROCE_MAX_PEERS=16 already ok). Ring: spark1<->spark2
  10.0.23.x, spark1<->spark3 10.0.22.x, spark2<->spark3 10.0.33.x.
- GATE: prove TP=3 greedy (temp 0, `--no-drafts` first) == TP=2 token-for-token, THEN bench single-stream.
  SHIP ONLY IF TP=3 single-stream > TP=2.

## Verify tooling
`python3 -m py_compile` + `python -c "import tensorfold.families.glm5_next.cuda.forward, tensorfold.cli"` in the
container catches integration errors before any build. Patchers are string-anchored and re-runnable from `a/`.
