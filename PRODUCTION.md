# The production GLM serve's recipe (the target to match or beat)

This branch is what the GLM-5.3-Flash serve on spark1-3 runs today: the upstream pins its image is built from, our
patch stack in apply order, the files that build the image and launch it, and what it measures
(`production/SPEED-TARGET.md`). It is frozen: it changes only when production changes. Its history is unrelated to
`main`'s; read it in its own worktree (`git worktree add work/prod production`). The modern-engine work for GLM is
`ots/GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig`, which carries this same commit; that work is finished when it matches
or beats `production/SPEED-TARGET.md` at 1, 2, 4, 6 and 8 streams.

Everything below was read from spark1-3 on 2026-11-13 with the serve up and untouched.

## What serves

| | |
|---|---|
| image | `tensorfold-glm53:v110hunt4-shard`, built on each node on 2026-11-10 (image ids differ by node: spark1 `2ab6a0efc827`, spark2 `ffb23ae3f0df`, spark3 `6e7d8f7c94c1`); its tensorfold package is the same 457 files on all three |
| its parents | `v110hunt4-fix` (2026-11-08) on `v110hunt4` (2026-11-01) on four thin `v110sync` layers (2026-10-29/30) on the base build `v110sync` (2026-10-29) on `nvcr.io/nvidia/pytorch:26.07-py3` |
| engine | TensorFold v0.6.0 (`ashhart/TensorFold` commit `c4646171139ee8a3c38103eaa1699dad226ec12b`, tag object `c812f8b65b34`), the MiaAI recipe's 123 patches at `bf5f94523a8251029cedae86bf61f8ce37fac218`, then our 149 patch applications (`production/patches/SERIES`) |
| launch recipe | `MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold` at `549fdc562c477d477244d2df0590d6c14bda4889` (release v1.10): the head's `~/mia110`, whose `start-tp3.sh`, `start.sh`, `stop.sh` and `scripts/` equal that commit's, plus an untracked per-box `scripts/local.sh` |
| checkpoint | `Mia-AiLab/GLM-5.3-Flash-EXL3-4bpw-TensorFold` rev `078455ffe6472f9a52fbc1139f58b9db2881b25c`, one copy a node |
| drafter | `incoai/GLM-5.3-Flash-DFlash2` rev `bf582e4eacc1810f76656d1811693ff6c6737d2a` |
| boxes | spark1 = rank 0 and the API (`:8888`, OpenAI-compatible, served name `GLM-5.3-Flash-EXL3`), spark2 = rank 1, spark3 = rank 2; TP=3 |
| streams | `--parallel 4` |
| context | `--context 1048576`, `--max-tokens 32768` |
| other serve flags | `--thinking --vision --spill-gib 120 --snapshot-dir /spill --spill-highwater 0.70 --spill-min-tokens 8192 --spill-min-free-gib 50 --master-port 29551` |
| KV pool | 14,407,680 tokens, the latent cache sharded over the three ranks (`TF_GLM_KV_SHARD=1`) |
| container | `glm53-flash-tf` on every node; mounts the compiled-kernel folder `~/.cache/tensorfold-glm53/6f16fe2b5d59` at `/cache` (the image's `tf.patches` label), `/run/dispram` and kindling's dispram client at `/opt/dispram`, `~/.cache/tensorfold-spill` at `/spill`, `~/.cache/huggingface` |

## What is here

All of it is gathered under `production/`; the table names where each file lives on `main` (or on the head, for the
files no branch held before).

| path | what | source |
|---|---|---|
| `production/patches/SERIES` | the 272 patches the image was built from, in apply order: layer, path, sha256 | written from the files below |
| `production/patches/base/` | the 8 port copies the base build applied after the recipe's patches (`140-` to `147-`) | the head's `~/miasync/patches/`; on main as `sync/*-ported.patch` at `25d9d8b`, `c5889bf`, `5df118e`, `6116779` (140, 142, 143, 145) and current (141, 144, 146, 147) |
| `production/patches/sync/` | `ORDER` and the 19 ports of the synced tree | main `scripts/glm53/v110/sync/`: the versions at `68bc346`, except `glm-fill-fast-ported.patch` at `3f5fa6c` |
| `production/patches/hunt/` | `all6y.list`, its 119 lane patches, `build_stack.sh` | main `scripts/glm53/v110/hunt/` (the list is `stack/all6y.list`) |
| `production/patches/fix/` | `cuda-endpoint.patch`, `expandable-segments.patch` (image `v110hunt4-fix`) | the head's `~/fix-patches/`; main `scripts/glm53/v110/sync/fix/` |
| `production/patches/shard/` | `kernel-warm-shard.patch` (image `v110hunt4-shard`) | main `scripts/glm53/v110/sync/fix/` |
| `production/build/Dockerfile.v110sync` | the base build, reconstructed from the image's history | new |
| `production/build/build_thin.sh` | the four thin `v110sync` layers | main `scripts/glm53/v110/sync/` |
| `production/build/mkkit.py`, `kcplan.py`, `build_thin_wheels.sh`, `prepare_kcache.sh`, `prebuild.py` | the hunt kit, its layer, and its compiled-kernel folder | main `scripts/glm53/v110/hunt/Gb10Kit/` |
| `production/build/build_knobs.sh` | the fix and shard layers | main `scripts/glm53/v110/sync/knobs/` |
| `production/build/wheels.SHA256SUMS` | the one wheel the hunt layer installs (orjson 3.12.0) | the head's kit |
| `production/build/rebuild_tree.py` | rebuilds the image's package from this branch and compares it with the image | new |
| `production/build/image-files.sha256`, `RECORD`, `expected-hunt.sha` | the image's package hashes, pip's record of the TensorFold install, the deployed kit's file hashes | read from the image and the head |
| `production/launch/` | `glm-v110-start.sh`, `glm-v110-stop.sh`, `v110ots.env`, `glm-stack.env`, `spark-model`, `restart_when_idle.sh` | main `scripts/glm53/v110/`, `scripts/glm53/`, `scripts/glm53/v18/` |
| `production/watchdog/` | `glm-watchdog.sh`, `glm-boot-hygiene.sh`, `glm-mem-hygiene.sh`, `glm-disk-guard.sh`, `glm-kv-prune.sh`, `memguard-fallback.sh` | main `scripts/glm53/`; `memguard-fallback.sh` from the head |
| `production/systemd/` | `glm-watchdog-system.service`, `glm-watchdog.service`, `glm-disk-guard.service`, `glm-disk-guard.timer` | the head's `/etc/systemd/system/` for the first; main `scripts/glm53/` and `scripts/glm53/systemd/` |
| `production/SPEED-TARGET.md`, `production/target/pyprod/` | the measured target and its raw cells | new; the head's `~/bench/pyprod/` |

Three files differ from main's current copies at the same names, on purpose: they are what the image holds.

- `sync/glm-indexer-shard-ported.patch` and `sync/glm-expert-rotate-ported.patch` are main's versions of `68bc346`.
  Main's later copies (`7373d76`) carry two fixes that production gets from the hunt patch
  `BatchFixes/BatchFixes-1-shard-rows-rotate-layers.patch`; with main's copies that patch no longer applies (patch
  reports it reversed).
- `fix/cuda-endpoint.patch` is the head's copy (paths `tensorfold/...`). Main's copy names `a/tensorfold/...` and
  `b/tensorfold/...`, and the build's `patch -p0` cannot apply it.

## The patch stack, in apply order

`production/patches/SERIES` is the whole series, 272 lines, each with its sha256:

| layer | lines | how the image applied them | image |
|---|---:|---|---|
| A | 123 `recipe` + 8 `base` | `patch -p0 --forward` in name order over TensorFold v0.6.0 as pip installed it | `v110sync` |
| B | 123 `recipe` + 19 `sync` | the synced tree (`patch -p0 --forward --batch`, sync lines in `ORDER`), 18 of its files laid whole and `families/glm5_next/cuda/prompt_cache.py` removed | 4 thin layers |
| C | 119 `hunt` | `patch -p0 --batch` on the synced tree in `all6y.list` order; the 72 files that differ laid whole, plus the orjson wheel | `v110hunt4` |
| D | 2 `fix` | `patch -p0 --forward`, name order | `v110hunt4-fix` |
| E | 1 `shard` | `patch -p0 --forward` | `v110hunt4-shard` |

The `recipe` lines are the recipe's `patches/` at `bf5f945` and are not carried here. The two knobs the env sets,
`TF_GLM_DRAFT_WIDE` and `TF_GLM_POOLED_PACK`, come from the hunt patches (`DrafterBuckets`, `PooledKeys`);
main's `sync/knobs/knobs-synced.patch` built a different image and is not in this one.

## How the image was built (from `docker history`)

1. 2026-10-29, the base build (`production/build/Dockerfile.v110sync`), its context the recipe checkout at `bf5f945`
   holding `tfsrc/` (TensorFold `c4646171`) and `patches/` (the recipe's 123 plus `base/`, 131 files), tagged
   `v110sync`. The production image's first 67 layers are the 67 layers of `nvcr.io/nvidia/pytorch:26.07-py3` (repo
   digest `sha256:2140e699b3beaf7f96a0081fd9c9406bc3832b435cdb60dfa2d261f7d2f34a1c`).
2. 2026-10-29 18:14 to 2026-10-30 06:44, four `build_thin.sh` layers from `v110sync3-files.tgz` to
   `v110sync6-files.tgz` on the head (label `c2154670148a`); the first one removed `prompt_cache.py`.
3. 2026-11-01, `build_thin_wheels.sh` with the kit's `hunt-files.tgz` (72 files, written by `mkkit.py` from the
   `all6y.list` tree) and the orjson wheel, label `6f16fe2b5d59`: `v110hunt4`.
4. 2026-11-08, `build_knobs.sh` with `fix/`: `v110hunt4-fix` (the CUDA allocator's expandable segments for
   `--parallel` above 1, and a `/cuda` endpoint that reports `torch.cuda.memory_stats()`).
5. 2026-11-10, `build_knobs.sh` with `shard/`: `v110hunt4-shard` (the kernel warm-up takes the rank's own part of a
   sharded latent cache and skips a rank that owns none).

## How it is launched and kept up

- `spark-model glm start|stop|status` (box copy `~/.local/bin/spark-model`) reads `~/.config/glm-stack.env`
  (`production/launch/glm-stack.env`; the box copy differs only in `GLM_WORKERS`, the worker ssh targets) and runs
  `GLM_START` = `~/glm-v110-start.sh` or `GLM_STOP` = `~/glm-v110-stop.sh`.
- `glm-v110-start.sh` sources `~/v110.env`, a symlink to `~/v110ots.env` (`production/launch/v110ots.env`), sets
  `PORT=8888` and runs `~/mia110/start-tp3.sh`: rank 0 here, ranks 1 and 2 over the LAN. `glm-v110-stop.sh` runs the
  recipe's `stop.sh` on every rank.
- Production restarts go through `~/restart_when_idle.sh <label>` (`production/launch/restart_when_idle.sh`), which
  waits for an idle serve.
- `glm-watchdog-system.service` (enabled; `/etc/systemd/system/`) runs `~/.local/bin/glm-watchdog.sh`, which reads
  `/health`, restarts a dead serve, and on low memory asks `restart_when_idle.sh` for a planned restart. Stop it before
  a manual boot and start it after. The user unit `glm-watchdog.service` is masked on the head (its copy is kept as
  `.retired`). `memguard-fallback.sh` runs on the head by hand (`nohup`; no unit starts it) and follows a memory
  restart that found no idle window.
- The disk guard is off: `GLM_DISK_GUARD=0`, and the head's user timer `glm-disk-guard.timer` is disabled. The
  recipe's spill tier keeps its own cap (`SPILL_GIB=120`, at least 50 GiB left free).
- The compiled-kernel folder `~/.cache/tensorfold-glm53/6f16fe2b5d59` was prepared once on every node by
  `prepare_kcache.sh` (seeded from `c2154670148a`'s folder, dropping `tensorfold_glm_kda_chunk` and
  `tensorfold_roce_v1`, then `prebuild.py` in the image), so a boot compiles nothing.

Where each file goes on a node: `~/` for `glm-v110-start.sh`, `glm-v110-stop.sh`, `v110ots.env` and
`restart_when_idle.sh`; `~/.config/` for `glm-stack.env`; `~/.local/bin/` for `spark-model`, `glm-watchdog.sh`,
`glm-boot-hygiene.sh`, `glm-disk-guard.sh` and `glm-kv-prune.sh`; `/usr/local/bin/` for `glm-mem-hygiene.sh`;
`/etc/systemd/system/` for `glm-watchdog-system.service`; `~/.config/systemd/user/` for the disk-guard units.
The head's copies of all of these equal this branch's by sha256, except `glm-stack.env` as above.

## The environment as it runs

The container's environment on spark1 (`docker inspect glm53-flash-tf`); spark2 and spark3 carry the same 60
`TF_*`, `TENSORFOLD_*` and `NCCL_*` values.

Set by `production/launch/v110ots.env` (a recipe name in brackets where the env file sets that instead):

| variable | value |
|---|---|
| `TF_GLM_CACHE_GIB` (`KV_POOL_GIB`) | `31` |
| `TF_GLM_DISPLAY_KV_MIB` / `TF_GLM_DISPLAY_KV_BACKEND` (`DISPLAY_KV_MIB` / `DISPLAY_KV_BACKEND`) | `2032` / `dispram` |
| `TF_GLM_COMM` (`COMM`) | `roce` |
| `TF_GLM_EXL3_DEC_ORDER` | `1` |
| `TF_GLM_LOOP_GUARD` | `1` |
| `TF_GLM_CACHE_ENTRIES` | `96` |
| `TF_GLM_FILL_FAST_MS` | `400` |
| `TF_GLM_PREFILL_ROWS` / `TF_GLM_FILL_ROWS` | `4096` / `4096` |
| `TF_GLM_INDEXER_SHARD` | `prefill` |
| `TF_GLM_EXPERT_ROTATE` | `10,16,16` |
| `TF_GLM_KEEP_PER_CHAT` | `2` |
| `TF_GLM_STREAM_SMOOTH` (`STREAM_SMOOTH`) | `0` |
| `TF_GLM_DRAFT_WIDE` / `TF_GLM_POOLED_PACK` | `2176:prompt` / `2` |
| `TF_GLM_KEPT_BYTES_GIB` | `8` |
| `TF_GLM_KV_SHARD` | `1` |
| `--parallel` (`PARALLEL`), `--spill-gib` (`SPILL_GIB`), the image (`IMAGE`), `PREPARE` | `4`, `120`, `tensorfold-glm53:v110hunt4-shard`, `0` |

Set by the launch recipe at `549fdc5` (`start.sh`, `scripts/config.sh`): `TF_GLM_MTP=auto`, `TF_GLM_EFFORT_TAIL=0`,
`TF_GLM_DFLASH_POLICY=fnc7:0.3`, `TF_GLM_CACHE_SHARE_PCT=0`, `TF_GLM_CLEAR_THINKING=0`, `TF_GLM_COPY_MAX=15`,
`TF_GLM_COPY_REPLY_MATCH=16`, `TF_GLM_COPY_DRAFTS=1`, `TF_GLM_WIDE_GRAPHS=16`, `TF_GLM_KDA_CHUNKED=1`,
`TF_GLM_MULTI_LONE=0`, `TF_GLM_MULTI_PREFILL=1`, `TF_GLM_MULTI_WINDOW=32`, `TF_GLM_KV=fp8`, `TF_GLM_L2PF=1`,
`TF_GLM_EXL3_LOADS=nc`, `TF_GLM_HC_SPLIT=1`, `TF_GLM_MAX_QUEUED=` (empty), `TF_GLM_DENSE=q4`, `TF_GLM_FILL_DRAFTS=1`,
`TF_GLM_STREAM_SMOOTH_MS=400`, `TF_GLM_PREFILL_OVERLAP=2`, `TF_GLM_FILL_BUDGET_MS=200`, `TF_GLM_SHARED_PREFIX=1`,
`TF_SPILL_FLUSH_S=60`, `TF_ROCE_HCA=roceP2p1s0f0,roceP2p1s0f1,rocep1s0f0,rocep1s0f1`, `TF_ROCE_MAX_KB=512`,
`TF_ROCE_WAIT_S=300`, `TENSORFOLD_MEMORY_RESERVE_GIB=14.5`, `TENSORFOLD_NO_UPDATE_CHECK=1`,
`TENSORFOLD_NUCLEUS_UNION=1`, `NCCL_SOCKET_IFNAME=enP7s7`, `NCCL_IB_HCA=` (the same four devices as `TF_ROCE_HCA`),
`NCCL_IB_GID_INDEX=3`, `NCCL_IB_SUBNET_AWARE_ROUTING=1`, `NCCL_CROSS_NIC=1`, `NCCL_MIN_NCHANNELS=4`,
`NCCL_MAX_NCHANNELS=4`, `NCCL_P2P_DISABLE=1`, `NCCL_SHM_DISABLE=1`, `HF_HUB_OFFLINE=1`, `PYTHONPATH=/opt/dispram`.
From the NGC base image: `NCCL_NET_PLUGIN=spcx`, `NCCL_VERSION=2.30.7`. The rank arguments (`--master`, the worker
targets) are addresses and are left out (see the end of this file).

## Provenance, checked 2026-11-13

The method is `main`'s `scripts/glm53/v110/RECIPE-PROVENANCE.md`: every upstream input is named by its commit, never by
a branch or a version string. On top of that the content is compared file by file, as the Qwen repo's `production`
branch did against its image's build tar.

- The image's package: every file under `/usr/local/lib/python3.12/dist-packages/tensorfold` inside the image (a
  throwaway container from the image, no GPU, no network), `.pyc` aside: 457 files, the same 457 sha256 on spark1,
  spark2 and spark3 (`production/build/image-files.sha256`).
- TensorFold: the 392 files pip installed equal the hashes in the image's own `tensorfold-0.6.0.dist-info/RECORD`
  when taken from commit `c4646171` (0 mismatches). That commit is the `v0.6.0` tag's.
- The recipe: the 123 patches at `bf5f945` equal the base build's copies on the head, 0 differences.
- The hunt list: `production/patches/hunt/all6y.list` equals the deployed kit's `stack.list` byte for byte (119
  entries).
- The rebuild: `production/build/rebuild_tree.py`, run on this branch's committed bytes with TensorFold at `c4646171`
  and the recipe at `bf5f945`, rebuilds the package through layers A to E: **457 files, 457 equal, 0 differ, 0
  missing, 0 extra**. Its layer C is the deployed kit's 72 files (`expected-hunt.sha`), and `mkkit.py` run over its
  synced and hunt trees writes the kit's label `6f16fe2b5d59`, its drop list and its `expected-hunt.sha` byte for byte.
- The orjson wheel in `wheels.SHA256SUMS` is PyPI's file of that name (`bf44e374aadd...`, the hash PyPI publishes).
- The head's copies of the launch, watchdog and systemd files, and of the build scripts it ran (`build_thin.sh`,
  `build_thin_wheels.sh`, `build_knobs.sh`, `prepare_kcache.sh`, `prebuild.py`, `kcplan.py`), equal this branch's by
  sha256, `glm-stack.env` aside (`GLM_WORKERS`). `~/mia110` is clean against `549fdc5`.

## What cannot be rebuilt from this branch

- The base build's pip installs are not pinned: the image recorded av 19.0.2, xgrammar 0.2.8 and TensorFold's
  dependencies as PyPI served them on 2026-10-29. The image is their only record; the proof covers the tensorfold
  package, not the rest of site-packages.
- The NGC base image is named by tag and digest; if NVIDIA withdraws it, the image on the nodes is the only copy.
- The base build's Dockerfile was not kept: `Dockerfile.v110sync` is rebuilt from the image's history.
- The thin layers' archives on the head (`v110sync3` to `v110sync6-files.tgz`, `hunt-files.tgz`) are not carried:
  `rebuild_tree.py --emit` writes the same files again (new times, so a new archive).
- The compiled-kernel folder and the spill tier are runtime state on the nodes.

## Left out, and why

- Internal material. This repository pushes to a GitHub mirror, and its `int-docs/` folder is ignored because it holds
  what must not reach that mirror: host names, addresses, and incident records with timestamps and memory readings.
  So this branch carries no host address: not the `--master` arguments of the ranks, not the worker ssh targets of the
  head's `~/.config/glm-stack.env`, not the recipe's per-box `scripts/local.sh` (it sets `WORKER`, `WORKER2`,
  `WORKER_WEIGHTS`, `WORKER_WEIGHTS2`), and no incident record. The numbers `production/SPEED-TARGET.md` takes from
  internal notes are measurement results only.
- Upstream code, which the pins name: the TensorFold source, the recipe's 123 patches and its launch scripts.
- The orjson wheel itself (PyPI, by sha256).
- `build_v110.sh`: it builds the retired `v110-ots<N>` images from the recipe-v1.10 base image, which is not in this
  image's history.
- The hunt record's tests, registry, reports and lanes not in `all6y.list`; the stacks production replaced (`v18`,
  `v15`, `tp2`, `tp3`); the benchmark harnesses; the PR packages. They are on `main`.

Facts found while proving this branch that `main`'s documents state otherwise. `REPO-FORMAT.md` names
`v110hunt4-fix` as production and places the recipe pin `bf5f945` at the head's `~/mia110`: the serve runs
`v110hunt4-shard` (since 2026-11-10; `v110hunt4-fix` is its parent), `~/mia110` is the launch tree at `549fdc5`, and
`bf5f945` is the image's base build (`~/miasync`). `RECIPE-PROVENANCE.md` gives `a1897d591f70` as TensorFold v0.6.0:
that is the recipe-v1.10 image's patches label, and the tag's commit is `c4646171`. The comment at the top of
`v110ots.env` (carried here byte for byte, as the head runs it) lists `sync/knobs/knobs-synced.patch` among the image's
inputs: the image's history and the rebuild above show it is not one.

## Rebuild and relaunch

1. Checkouts: `ashhart/TensorFold` at `c4646171`, the recipe at `bf5f945` (the image) and at `549fdc5` (the launch).
   Check out with `git -c core.autocrlf=false` so the patch bytes match `SERIES`.
2. Prove (Linux, GNU patch):
   `python3 production/build/rebuild_tree.py --tf <tensorfold> --recipe <recipe at bf5f945> --out <dir> --emit <dir>/emit`
3. Build on every node, each step's tag the next step's base:
   `docker build -f production/build/Dockerfile.v110sync --build-arg EXTRAS="av xgrammar" --build-arg PATCHES_HASH=v110sync -t tensorfold-glm53:v110sync <context>`;
   `build_thin.sh tensorfold-glm53:v110sync6 tensorfold-glm53:v110sync <emit>/sync-files.tgz c2154670148a families/glm5_next/cuda/prompt_cache.py`
   (one thin layer in place of the four, the same files);
   `build_thin_wheels.sh tensorfold-glm53:v110hunt4 tensorfold-glm53:v110sync6 <emit>/hunt-files.tgz 6f16fe2b5d59 <wheels dir>`
   (the dir holds the orjson wheel and `wheels.SHA256SUMS` named `SHA256SUMS`);
   `build_knobs.sh tensorfold-glm53:v110hunt4 tensorfold-glm53:v110hunt4-fix <dir holding patches/fix/*.patch>`;
   `build_knobs.sh tensorfold-glm53:v110hunt4-fix tensorfold-glm53:v110hunt4-shard <dir holding patches/shard/*.patch>`.
   Then the package inside the image must equal `image-files.sha256`:
   `docker run --rm --network none --entrypoint sh <image> -c 'cd /usr/local/lib/python3.12/dist-packages && find tensorfold -type f ! -name "*.pyc" | LC_ALL=C sort | xargs sha256sum'`.
4. The compiled-kernel folder: `mkkit.py <out>/hunt <out>/synced <kit dir>`, copy `kcplan.py` and `prebuild.py` beside
   it, then `prepare_kcache.sh <kit dir> tensorfold-glm53:v110hunt4-shard` on every node with the serve down.
5. Lay the launch, watchdog and systemd files where the list above puts them, `ln -sf ~/v110ots.env ~/v110.env`,
   clone the recipe at `549fdc5` to `~/mia110` with a `scripts/local.sh` naming the workers, then
   `spark-model glm start` and `sudo systemctl start glm-watchdog-system`.
