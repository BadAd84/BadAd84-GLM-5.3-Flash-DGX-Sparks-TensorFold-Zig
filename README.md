# GLM-5.3-Flash on DGX Sparks, TensorFold Zig engine

OTS recipe for serving GLM-5.3-Flash (Mia-AiLab EXL3 4bpw checkpoint) with the TensorFold
Zig engine on the DGX Spark fleet. Gitea is the home of this repo; GitHub carries a public mirror.

**Open work order (owner 2026-11-12): [REPO-FORMAT.md](REPO-FORMAT.md).** The format is a `production` branch (the
serving recipe, the target) and `main` for the in-flight work on the modern engine; that file lists what this repo
still needs. Remove this paragraph with the file.

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
    bash scripts/zig-tp3.sh <streams> [ctx]          # TP=3 on spark1-3, waits for /v1/models
    python3 scripts/streams.py 8888 <streams> --kind prose
    bash scripts/zig-tp3-stop.sh

Production and both GLM watchdogs must be stopped for a window: the watchdog restarts production under the boot.

## Where things are

- `patches/engine/` - the series. `RECORD.md` has one row a patch (what it is, where it came from, its receipt),
  `SHA256SUMS` the hashes, and `scripts/check-patch-packages.sh` fails when either is out of step.
- `scripts/` - apply, build, boot, the gates (`gates.sh`, `lean.sh`, `gate-names.sh`) and the measurement tools
  (`streams.py`, `bench-arm.sh`, `abba.sh`, `rounds.py`).
- `docs/` - measurements and audits, dated. `PORT-LEDGER.md` records what is landed, what is parked and why.
- `archive/` - the two retired forks this work came from (`ots/ai-engine`, `ots/tensorfold-gb10`) as git bundles
  with their ref lists and check scripts.
- `AGENTS.md` - the rules of this repo: how a patch is cut, gated, measured and landed, what a version bump of
  upstream requires, and how a change goes upstream. `.omp/RULES.md` carries the hard order for upstream work.

## State (2026-11-12)

Pin `9c9bf542`. Decode in tok/s at 1, 2, 4, 6 and 8 streams, one fresh boot a level, 400 tokens a stream. The
replies of the three plain Zig rows are byte-identical to each other; `TF_GLM_KDA_PAD=1` is the setting production
runs, and it changes numerics, so the last row is the like-for-like one against production:

| serve | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|
| production (Python engine) | 81.73 | 89.22 | 117.98 | 114.78 | 131.28 |
| the pin, no patches | 51.38 | 58.16 | 72.26 | 95.19 | 115.18 |
| patches through 0042 | 51.51 | 59.56 | 80.99 | 110.01 | 134.09 |
| through 0044 | 52.02 | 60.26 | 82.67 | 113.29 | 137.01 |
| through 0044, `TF_GLM_KDA_PAD=1` | 64.81 | 74.23 | 94.45 | 126.65 | 154.07 |
| upstream v1.2.7, no patches | 50.16 | 58.57 | 79.23 | 106.37 | 129.66 |
| upstream v1.2.7, `TF_GLM_KDA_PAD=1` | 62.19 | 70.57 | 88.91 | 118.29 | 143.25 |

So with production's own setting the Zig engine leads at 6 and 8 streams and trails at 1, 2 and 4. The gap at low
stream counts is the time of one decode round; `docs/speed_target.md` has its breakdown. The series is being
re-seated on upstream v1.2.7 (`93a2e93e`), after which every row is measured again on that base.
