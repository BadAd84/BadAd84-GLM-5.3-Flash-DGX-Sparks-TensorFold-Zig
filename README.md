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
- `archive/` - the two retired forks this work came from (`ots/ai-engine`, `ots/tensorfold-gb10`, both deleted from Gitea on 2026-11-14) as git bundles
  with their ref lists and check scripts.
- `AGENTS.md` - the rules of this repo: how a patch is cut, gated, measured and landed, what a version bump of
  upstream requires, and how a change goes upstream. `.omp/RULES.md` carries the hard order for upstream work.

## State (2026-11-19, base moved 2026-11-20)

**The base moved on 2026-11-20.** `patches/` now holds the series re-seated on upstream main `1ece6e6db` (1.3.0, 1,221 commits past v1.2.9): 38 engine patches (0011 is retired, upstream has it as our PR #2044) and the six packages `pr1411`, `cache-salt`, `learn-starts`, `solo-cuts`, `disk-any-position` and `restore-held`, tree `5ae4bbe5e418`, full gate PASS against the pristine main (`docs/audit-2026-11-12/reseat-main-1ece6e6.md`, OVERNIGHT section 70). The environment is two files, `scripts/env/prod.env` and `scripts/env/dev.env`. **The third paragraph after this one and everything below it were measured on the v1.2.9 stack**; queue91 (`scripts/queues/queue91.sh`) is the first queue on the new base and its result is the next paragraph, and queue92's (stock upstream, no knob of ours) is the one after.

**The stack on main** (queue91, 2026-11-20, OVERNIGHT section 72, rows in `docs/audit-2026-11-12/queue-rows/queue91`), at `--parallel 4 --context 1048576` against the v1.2.9 stack, every reply equal: the cold first tokens within 0.22% (8k 3,990.0 against 3,986.2 ms), 19 of 20 decode cells faster and all 12 at 1, 2 and 4 clients faster by 1.07% to 3.10%, and one cell over the sync rule's 1.0% limit (greedy code at 8 clients, 1.63% slower, inside the boots' spread; queue95 reruns it). Upstream's PDL is worth 2.48% to 4.02% of decode at 1, 2 and 4 clients. Stock main without the recipe is 29% to 36% lower on decode and 34% to 42% slower on a cold first token. The ten candidates in `dev.env` still gain 8.3 / 8.9 / 8.4% cold and 7.9% on warm turns, but their decode at 1, 2 and 4 clients is lower in all 12 cells (mean 0.86%), so they are a trade on main until queue95 says which of them carries it; request starts give 34.2% faster warm turns with the cold prompt level, but their 6 and 8 client decode cells are not clean (mean -0.41% with four of eight negative, OVERNIGHT section 73), so they stay off until queue100 has run.

**What upstream's merged work gave a stock user** (queue92 and queue96, 2026-11-21, OVERNIGHT sections 73 and 74, rows in `docs/audit-2026-11-12/queue-rows/queue92`, report script `scripts/queue-scores/derive92.py`): eleven boots of stock upstream from v1.2.9 to main `1ece6e6db`, no knob of ours. Cumulative decode at 1, 2 and 4 clients +2.39% (all 20 decode cells +2.02%), the four prompt cells -0.56%, a cold first token flat on every rung (5,190 to 5,280 ms at 8k, 20.4 to 20.7 s at 32k), every step ms a round (tokens a round are identical) and every reply digest equal. The largest step (+1.72% decode) is the one that holds our item plan (PR #2044); net of it the others' merged work is +0.69% decode and -1.40% prompt, below the 2.4% spread between two boots of v1.2.9. Our stack is +25.08% on the prompt cells and +44.57% on decode at 1, 2 and 4 clients over stock main. **After the pin it is different:** stock main at the tip `46c6ee229` (192 commits later; queue96, one boot) has a cold first token 11.90% / 12.99% / 13.37% faster at 8k / 32k / 120k and warm turns 9.89% faster, decode level, all 58 reply digests equal; the only change in those commits to GLM's prompt-window path is ultradaoto's #3697 (the uneven KDA stack padded to 16-byte rows, prompt windows on the staged tiles, bytes unchanged), which is an inference from code scope, not a bisect. Whether the stack gains anything from it is queue97's question.

**The prompt-cache victim policy, served** (queue98, 2026-11-21, OVERNIGHT section 75, rows in `docs/audit-2026-11-12/queue-rows/queue98`, report script `scripts/queue-scores/derive98.py`): upstream's `TF_CACHE_EVICT=decayed_resume` against the default on the stack on the pin, one fresh boot per arm at `--parallel 4 --context 1048576`, upstream's `tools/bench_cache_agents.py` (six conversations, 24 rounds, a 32,768-token prefix, 432 requests). Rebuilt prompt rows fell from 14,396,073 to 7,572,137 (47.40% fewer, inside the host-only replay's predicted 44% to 50%), the sum of first-token times fell 47.16%, and all 432 replies are equal. The agent turns rebuilt 92.10% fewer rows and none of 138 missed its previous turn with the policy on (103 of 138 without it); the one-off prompts, which share no prefix, are unchanged. That is the oversubscribed regime, where the live conversations do not fit the 7.9 GiB cache; the replay predicted no effect when they do. Decode and the cells without eviction pressure are queue99's question, with the adoption rule fixed before its rows (OVERNIGHT section 75), so the setting is in no environment file yet.

**The final recipe on the v1.2.9 stack** (queue77, 2026-11-20, `docs/OVERNIGHT-2026-11-12.md` section 71, rows in `docs/audit-2026-11-12/queue-rows/queue77`), at `--parallel 4 --context 1048576`, the committed recipe against the same plus the candidates in `scripts/env/dev.env`, every reply equal: the cold first token 9.3 / 9.9 / 9.6% faster at 8k / 32k / 120k, a 112,695-row conversation's first turn 9.6% and its warm turns 8.6% faster, 24 prompts one at a time 1.2% faster (22 of 24), decode at 1, 2 and 4 clients level (-0.5% to +0.7%), fresh 6 and 8 stream boots level (-0.5% to +0.3%); with `TF_GLM_REQUEST_STARTS=1` the warm turns are 39.2% faster and the cold prompt pays nothing for it (2.8% faster at 8k, level at 120k). Against production's recorded times the cold first token is 1.244 / 1.219 / 1.206 times its own, a first turn 1.199 times, a warm turn 1.194 times (with request starts). The disk tier resumed every reply equal to a cold server's at TP=3. Nothing is promoted to `prod.env` from those cells: queue91 re-measured the candidates on main (the paragraph above) and queue95 splits them.

Base of the measurements below: upstream v1.2.9 (`6b9de695`) plus the 36 patches of `patches/engine/`, then `patches/pr1411/` (GLM disk tier, upstream PR #1411: its head and the batched restore) and `patches/cache-salt/` (upstream PR #3222). The tables below were measured on image `glm53-zig:v129v` (35 patches, tree `5137a5ef75ab`). Three things on top of that image pass their gates on a gate host and wait for their GPU checks (`scripts/queues/queue73.sh`): `patches/learn-starts/` (the disk image carries a request-start chunk digest, so `TF_GLM_REQUEST_STARTS=1` runs with `--learn-conversations`), `patches/solo-cuts/` (a solo prompt step runs between request starts, where a request with starts took none) and patch 0036 of the series (`TF_GLM_OVN_LATENT_ROWS`, two or four rows a step in the latent kernels, off by default); all three together are tree `fc3526cde368`. Gates: check, fmt, `test-cuda-host` (the only failure is the pristine v1.2.9's own `cli_config_test` case), lean 0 new. The recipe is `KNOBS=measured` in `scripts/serve.sh`: 23 switches, each measured against the recipe with the replies equal (`docs/KNOBS.md`).

**Against production on the Sparks (the Python engine)**, at its deployed shape (`--parallel 4 --context 1048576`, so 6 and 8 clients queue), the same prompt ids, 2026-11-19 (`docs/OVERNIGHT-2026-11-12.md` section 50; the Zig rows are the recipe's six prompt and decode switches without `DRAFT_NOISE`, two boots; production before and after the window). Ratio above 1 is Zig faster.

| decode, aggregate tok/s | production | Zig | Zig over production |
|---|---:|---:|---:|
| greedy prose, 1 / 2 / 4 streams | 80.19 / 88.40 / 116.56 | 81.72 / 84.86 / 112.43 | 1.019 / 0.960 / 0.965 |
| greedy code, 1 / 2 / 4 streams | 115.40 / 145.19 / 183.90 | 114.14 / 136.65 / 166.61 | 0.989 / 0.941 / 0.906 |
| sampled prose, 1 / 2 / 4 streams | 82.47 / 85.43 / 116.25 | 76.62 / 79.96 / 104.31 | 0.929 / 0.936 / 0.897 |
| sampled code, 1 / 2 / 4 streams | 108.35 / 139.30 / 173.53 | 115.61 / 140.48 / 158.62 | 1.067 / 1.008 / 0.914 |
| the 24 prompts one at a time | 113.1 s of decode | 115.0 and 115.8 s | 0.980 |

| prompt work | production | Zig | Zig over production |
|---|---:|---:|---:|
| cold first token, 8k / 32k / 120k | 2.9 / 11.1 / 41.9 s | 4.0 / 15.0 / 55.9 s | 1.38x / 1.36x / 1.33x |
| a growing conversation, ~113k, turns 2 to 8 (without request starts, with) | 668 ms | 1,308, 844 ms | 1.96x, 1.26x |
| the same at ~284k, turns 2 to 6 | 744 ms | 1,420, 910 ms | 1.91x, 1.22x |
| 596k conversation after a SIGKILL of every rank (disk tier), prefill | 12.80 s | 12.81 s | 1.00x |
| the same after a clean restart, beside 3 decoding streams | 12.90 s | 15.79 s | 1.22x |

At one stream decode is level with production (0.93 to 1.07 of its tok/s over the four decode rows); at two and four streams it is 0% to 10% behind (0.897 to 1.008), and a conversation survives a restart at parity. What is left is prompt speed: a cold prompt costs 1.33x to 1.38x, a warm turn 1.26x with request starts (which are off in the recipe until the disk tier's check of them and a 7% cold-prime cost are settled), and the sampled and two-to-four stream decode cells above. The profile of a 4,096-row prompt pass (section 50) puts the time in the exchanges between ranks (we leave the main stream waiting about 11.7% of a pass for them), in two attention helper kernels that step through rows one at a time, and in the dense matmul. The 6 and 8 stream cells at this shape queue requests and vary by 4% to 8% between identical boots, so they decide nothing; the fresh `--parallel 6` and `--parallel 8` pairs are in sections 48 and 49. Tables measured on the v1.2.7 stack are in sections 11 to 41.
