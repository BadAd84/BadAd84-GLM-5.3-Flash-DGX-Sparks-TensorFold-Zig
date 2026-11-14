# GLM-5.3-Flash on DGX Sparks, TensorFold Zig engine

OTS recipe for serving GLM-5.3-Flash (Mia-AiLab EXL3 4bpw checkpoint) with the TensorFold
Zig engine on the DGX Spark fleet. Gitea is the home of this repo; GitHub carries a public mirror.

## Branches

- `main` is the in-flight work on the modern engine: a pinned upstream TensorFold commit (`TF_REF` in
  `scripts/config.sh`) plus our numbered patches in `patches/engine/`. No engine tree is committed here.
- `production` is the recipe serving on spark1-3 today (the Python engine), carried as the same commit the Python
  repo `ots/GLM-5.3-Flash-DGX-Sparks-TensorFold-Python-TP3` publishes. It is the target `main` has to beat. The
  branch is fetched from that repo, never built here.

## From a clean checkout to a measured serve

    bash scripts/apply.sh work/t                     # the pin plus every patch, in filename order
    tar -C work/t/tree --exclude .git -cf work/t/src.tar .
    bash scripts/build-image.sh <tag> work/t/src.tar # on spark1: image glm53-zig:<tag>, compiled for sm_121a
    bash scripts/dist-image.sh <tag>                 # copy it to spark2 and spark3 (every rank needs it)
    bash scripts/zig-tp3.sh <streams> [ctx]          # TP=3 on spark1-3, waits for /v1/models
    python3 scripts/streams.py 8888 <streams> --kind prose
    bash scripts/zig-tp3-stop.sh

Production and both GLM watchdogs must be stopped for a window: the watchdog restarts production under the boot.

## Where things are

- `patches/engine/` - the series. `RECORD.md` has one row a patch (what it is, where it came from, its receipt),
  `SHA256SUMS` the hashes, and `scripts/check-patch-packages.sh` fails when either is out of step.
- `scripts/` - apply, build, boot, the gates (`gates.sh`, `lean.sh`, `gate-names.sh`) and the measurement tools
  (`streams.py`, `bench-arm.sh`, `abba.sh`, `rounds.py`).
- `docs/` - measurements and audits, dated: `docs/OVERNIGHT-2026-11-12.md` is the running record of what was measured.
- `archive/` - the two retired forks this work came from (`ots/ai-engine`, `ots/tensorfold-gb10`) as git bundles
  with their ref lists and check scripts.
- `AGENTS.md` - the rules of this repo: how a patch is cut, gated, measured and landed, what a version bump of
  upstream requires, and how a change goes upstream. `.omp/RULES.md` carries the hard order for upstream work.

## State (2026-11-12)

Base: upstream v1.2.7 (`93a2e93e`) plus the 33 patches of `patches/engine/`. Decode in tok/s at 1, 2, 4, 6 and 8
streams, one fresh boot a level, 400 tokens a stream. `TF_GLM_KDA_PAD=1` is the setting production runs and it changes
numerics, so the pad rows are the like-for-like ones against production; replies are byte-identical between the rows of
one group.

| serve | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| production (Python engine; its own rendering of the bench prompts) | 81.73 | 89.22 | 117.98 | 114.78 | 131.28 |
| upstream v1.2.7, no pad | 50.16 | 58.57 | 79.23 | 106.37 | 129.66 |
| this series, switches off | 51.55 | 60.88 | 83.11 | 111.63 | 137.43 |
| this series, pad | 64.57 | 73.71 | 93.66 | 126.18 | 153.75 |
| this series, pad + drafter knobs | 69.78 | 78.17 | 98.83 | 133.80 | 160.25 |
| this series, pad + the seven-knob set (`KNOBS=measured`) | 70.17 | 78.71 | 99.40 | 134.31 | 165.26 |
| the same plus the RoCE wire at 4 streams or fewer (mean of two cells; 6 and 8 as the row above) | 71.54 | 79.65 | 101.00 | 134.31 | 165.26 |
| the recipe as `serve.sh` defines it (`KNOBS=measured`: those seven, production's chain rule, the wire at 4 streams or fewer; mean of two cells) | 71.09 | 80.35 | 100.94 | 134.20 | 163.36 |
| **the same recipe on production's prompts** (`scripts/bench-client.sh`: its rendering of the four bench prompts as ids; mean of two cells) | 78.71 | 80.81 | 105.47 | 139.26 | 172.67 |
| **that recipe plus production's routed-expert block order** (`TF_EXL3_DEC_ORDER=1`, now in `DEFS`; mean of two cells) | 78.68 | 80.68 | 107.30 | 141.09 | 173.52 |

The rows above the last two send our server's own rendering of the bench prompts, which is 40 tokens for the first prose prompt where
production renders 33, so the two serves answer different text and the comparison is not like for like (`docs/OVERNIGHT-2026-11-12.md`
section 23). On production's own prompt tokens the recipe as `serve.sh` defines it is -3.7% at one stream and -9.6%, -9.1% at two and
four, and leads at six and eight (+22.9%, +32.2%); cells from different measuring windows differ by up to 3%, so these are about, not
exact. The rest of the gap is in `docs/OVERNIGHT-2026-11-12.md` sections 11 to 24 and `docs/audit-2026-11-12/round-structure.md`.
