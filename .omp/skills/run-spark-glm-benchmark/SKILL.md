---
name: run-spark-glm-benchmark
description: "Use when asked to measure GLM on the DGX Spark triangle (base vs patches, python vs zig, a knob A/B) or to explain how those numbers are produced."
---

# Running a GLM benchmark on the dev triangle

Everything runs on spark4 (control box), never from the laptop.

## Pieces

- Serve: `~/glmperf/serve4.sh P CTX` boots TP=3 on spark4-6 under `flock ~/work/gpu.lock`, distributing to spark5/6 over ssh. `XENV='-e KNOB=1'` per arm, `XSERVE='--metrics-open'` for the probe. `NODEFS=1` skips our 23 `TF_GLM_OVN_*` defaults but still applies INDEX_CUDA, the KDA pad, dense 4-bit, 8-bit KV, res and the drafter.
- Probe: `~/perpatch-ai/perpatch_measure_ai.py OUT LEVEL ARM TAG PROMPTS`. One boot gives short/r1/r2/r2m/r3/forks/cold32 plus a reply digest. `COLD_PROMPT` (c32.txt prose, fix40.txt code) and `COLD_TOKENS` pair the kinds at one length (meta.json holds token totals).
- A/B runner: `LEVELS="1 2 4 6 8" ~/glmperf/pp-chain-ab.sh IMAGE TAG WAITLOG WAITPAT "A_XENV" "B_XENV"` runs ABBA, a fresh boot a cell, and writes `~/perpatch-ai/run-<time>-<tag>/` with per-cell JSON, boot log, measure log and `arms.txt`.
- Images: `ovnlib.sh build TAG` builds `~/src-TAG.tar` on spark4 AND copies to spark5/6. A bare `build-image-gram.sh` builds spark4 only and the other ranks then fail to find the image.

## Check before trusting a run

1. `arms.txt` in the run dir is not blank - empty arm strings make both arms the default and the result looks like a null.
2. Digests equal across arms; a digest mismatch voids the speed comparison.
3. `flock` once only: `serve4.sh` locks itself, so wrapping it in another `flock` deadlocks behind its own child.
4. A bare serve keeps no deep states, so a resumed ~200k prompt re-prefills (746 s measured against 1.03 s with defaults). For resume cells put `TF_GLM_OVN_ONE_CHUNK=1 TF_GLM_OVN_KEPT_WALK=1` on BOTH arms and say so in the receipt.
5. Scripts uploaded from Windows carry CRLF and die as `$'\r'`: run `sed -i 's/\r$//'` and `bash -n` after every upload.

## Production-side base vs patches (RigMark)

- Receipts: `~/prof/rigmark/*.json` on spark1; summarise with `~/rigmark/compare.py LEFT RIGHT [--card]`.
- Each receipt carries its arm in `run.appliance.arm`; `stock` is `v110-base` (recipe v1.10 plus ots0073 only), ours is recipe + OTS patches + production env.
- The `a1-B` series is stock-vs-ours in ABBA; B1 against B5 (both stock) is the noise floor. Decode and prefill reproduce within 1-2%, warm replay swings up to 12% and is not gated on.
- spark1 is not in gpgssh's HOSTS: add `gpgssh.HOSTS['spark1'] = ('spark1.ots-int.net', None)` before `run`.

## Reporting

Tables: rows by stack or metric, P1/P2/P4/P6/P8 as columns, ratios beside the absolute numbers, and the measurement date plus image/arm provenance in the caption. A campaign of chains (`policy`, `tier`, `solo`, `kvh`, `itemsfix`) waits on marker files; give each its own `*-CHAIN-DONE` and have dependents wait for the marker, never for a process name.
