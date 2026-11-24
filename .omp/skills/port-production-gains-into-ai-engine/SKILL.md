---
name: port-production-gains-into-ai-engine
description: "ai-engine catch-up: map every production GLM lever, measure the gap with production's own probe, port by measured gain."
---

# Port production's gains into ai-engine (catch-up mode)

Use when production (glm5.3-flash-dev, Python TensorFold on spark1-3) has moved or the owner asks how far behind ai-engine is.

## 1. Keep the ledger complete (mechanical)
- `python scripts/parity_check.py` (ai-engine root). It reads production's committed records: `scripts/glm53/v110/v110ots.env`, flag tables in `docs/GLM53-FLASH-PRODUCTION-STACK.md`, every `ots*.patch`, `scripts/glm53/v110/sync/*.patch`, and the newest `docs/notes/speed-hunt-*/stack/all*.list`.
- Any UNMAPPED lever: add its row to `docs/PARITY.md` (status present / partial / absent / n.a. with file:line evidence, production's measured gain and source). For big batches, fan out read-only mapping lanes (one per source: flags+patches, upstream sync diff v110-ots124 vs v110sync6 under `glm5.3-flash-dev/work/srcx/`, hunt host candidates, hunt GPU candidates) with a fixed table contract; copy their files to `docs/research/parity-<date>/` and regenerate the index with `scripts/parity/build_index.py`.

## 2. Measure the gap with production's own instrument
- Production probe: `perpatch_measure.py`; ours `scripts/parity/perpatch_measure_ai.py` (identical except health() also reads `/metrics`; serve needs `--metrics-open`). Prompts: copy spark1 `~/perpatch/prompts` to spark4 `~/perpatch-ai/prompts` and compare sha256.
- Production reference numbers: spark1 `~/perpatch/run-*/L*-prod.json` (wave-3 `prod` arm).
- Chain: `scripts/parity/pp-chain.sh IMAGE [WAITFOR] [EXTRA]` (P=1/2/4/6/8, 1M, ABBA; EXTRA = the ports as arm `port` against `win`).
- Warm-turn split: `scripts/parity/warmprof-chain.sh` (TF_GLM_PROF=1 prompt trace; `glm prompt chunk` lines show how many steps a turn runs).

## 3. Port in order of production's MEASURED gain
- One worktree per port off `ovn-int` (`git worktree add ../ovn-<name> -b ovn-<name> ovn-int` in glmnight-tree), default-off `TF_GLM_OVN_*` knob, knob read FIRST before any Engine/drafter field (host fakes leave fields undefined: segfaults in test-cuda-host otherwise).
- Every port ships a `tf-cuda-test` byte check comparing knob on vs off that can fail; run it on the GPU before any speed cell (the first one-chunk check caught a refused-keep bug that made every turn cold while replies stayed identical).
- Gates locally, commit signed, `ovnmerge.sh <lane>`, image via `ovnlib.sh build`, cells ABBA with digests.

## Measured lessons
- A warm turn's cost is prompt STEPS, not host work: each step re-reads expert weights (~0.2 s). Count steps first.
- Bit-identical kernel ports can still be decode-level; check the stage split (e.g. mla_chunks vs mla) before expecting a gain.
- Pause other chains with `kill -STOP` on the chain pid (not the flock child) to put a verification first; never kill a chain mid-cell without killtree.sh.
