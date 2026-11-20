# Upstreaming our patches to `ashhart/TensorFold`: the plan, the order and the state

Written 2026-11-20 from upstream `main` at `9ba855b3b` (the series is installed on `1ece6e6db`). The owner's directive: start adding our patches upstream, for TP=3 and everything else we carry on top of main. Nothing is posted or pushed yet: every issue, pull request body and comment is the owner's text under his name, and goes through the style pipeline and his approval first. The tiers below are PROPOSALS with their basis; a number quoted here is from a section of `docs/OVERNIGHT-2026-11-12.md` and was measured on the v1.2.9 stack unless it says main.

## How a lever goes up

The order is in `AGENTS.md` ("Contributing upstream") and `.omp/RULES.md`. For this repo, per lever:

1. **A lane** (`ds41-direct`, brief `work/up/BRIEF.md`) cuts ONE lever onto current upstream main in a worktree `work/up/wt-LEVER`, branch `up/LEVER`, in upstream's style: the setting is a rule in `platform/environment.zig` with a `docs/environment.md` line and a reader, the upstream name is `TF_GLM_NAME` (our `OVN` prefix is dropped, our `ovn.zig` helper is not carried), default off, a test with a planted control, a CHANGELOG bullet with a `#NNNN` placeholder, commits as `BadAd84`. It writes `work/up/drafts/LEVER/` (facts, overlap with open PRs, gates, receipts plan, DRAFT issue and PR texts) and nothing leaves the machine.
2. **Gates** run on the gate host only (`python scripts/spark-gates.py iter --pin-repo work/up/TensorFold --pin <cut sha> --dir <patches> check fmt ctest lean pdl contract test`; `zig:STEP` runs one build step for a mutant). A mutant per changed line is killed by a named test.
3. **Receipts** on the three Sparks with upstream's own tools (`tools/bench_openai.py`, `tools/bench_concurrent.py --levels 1,4 --alone --serial`, `tools/bench_cache.py --require-cold`): main against the branch, built the same way from the same sha, our `OVN` knobs off on both arms, one fresh boot a cell, alternating, with the exact environment stated.
4. **The owner** approves the issue text (and the umbrella proposal below), then `atc check ISSUE --json`, `atc claim`, the pull request, `atc overlap --json` last, pulses while working, `atc land` or `release` after. Never a force-push of a branch under review.

## What upstream already has or has open on our hardware

ultradaoto runs the same kind of rig (three GB10 on a switchless triangle, GLM-5.3-Flash EXL3, `--parallel 4 --kv-cache fp8`, DFlash2) and has most of the TP=3 work in flight, so each of our levers is checked against these before a cut:

| open or merged | what it does | relation to ours |
|---|---|---|
| #3776 (merged) | GLM's kernels as dependent launches, `TF_GLM_PDL` default on | in main; queue91's `mz` arm and queue92's `smz` measure it |
| #2044 (merged, ours) | the 16-pair item plan for EXL3 decode windows | our patch 0011 is retired; 0027 and 0031 sit on top of it |
| #3616 | `TF_GLM_DRAFT_SPLIT=1`, the DFlash2 drafter's MLP split at three ranks or more (+4.9% aggregate decode claimed at TP=3) | the same idea as our `TF_GLM_OVN_DRAFT_MLPSPLIT`: ours is not cut; queue92's `pd` arm measures theirs |
| #3659 | `TF_GLM_MOE_DIRECT=1`, a decode window's EXL3 MoE without its row copies | a different cut of the same decode path as the item plan; queue92's `pm` |
| #3697 | an uneven KDA stack padded to 16-byte rows, exact; cold first tokens 10-11% sooner at TP=3 | what our recipe's `TF_GLM_KDA_PAD=1` already gets (ours, #1545) with a 4-bit stack; our patch 0005 is checked against it before any cut |
| #3518 | `TF_ROCE=1` pairs stripes by /24 so a switchless triangle connects | gains what `TF_GLM_ROCE_MULTI` already gives us (their own table) |
| #3689 | `TF_GLM_DSCORES`, a decode window's DSA index scores | level at TP=3 in its own table; its gain is TP=4 at 1M context |
| #3147 | warm turns under `TF_GLM_REQUEST_STARTS=1`, the maintainer's | the upstream form of our request-start work; our `SOLO_TO_START` and `RESTORE_HELD` sit beside it |
| #3617, #3222 | request starts by default; `cache_salt` | the maintainer's own |
| #2279 | `TF_GLM_GRAPHS=1`, verify windows as CUDA graphs (+2.3 / +3.6 / +3.7% at 1 / 2 / 4 streams on two GB10, before PDL) | queue92's `pg` arm |
| #3333 | `TF_GLM_COPY_SHARE=1` | acts only with `TF_GLM_COPIES=1`, which read as a loss on our serve (`docs/KNOBS.md`); not measured with a drafter on main |
| #1411 | the GLM disk tier (wojo), rebased by the maintainers into the landing queue | our `pr1411` package and the three that follow it drop away when it lands |
| #2919, #2415 and the `TF_GLM_KV_SPLIT` stack | placement by `--tp/--rank` flags; the latent split | not ours; they change `cuda_engine.zig` and the kept-state code our levers touch |

## The patches by tier

### Tier A: a measured benefit and exact bytes, in the order the lanes take them

| patch | our knob | upstream shape | basis | hottest code file (open PRs on it) |
|---|---|---|---|---|
| engine/0032 | `TF_GLM_OVN_KEEP_SEQS` | `TF_GLM_KEEP_SEQS`, default off, exact | four-stream decode 109.73, 106.98, 101.95 tok/s at 262,144, 524,288, 1,048,576 context (the cost scales with the window): the pilot, branch `up/keep-seqs` | cuda_engine.zig (14 open PRs) |
| engine/0034 | `TF_GLM_OVN_NO_COPY` | `TF_GLM_NO_COPY`, default off, exact | code prompts +11.15 / +4.13 / +4.21% at 1 / 2 / 4 clients with MM_DECTILE and SWIGLU_REDUCE (OVERNIGHT sections 49, 50): the pilot, branch `up/no-copy`; the lane first checks what main's own copy pricing does with a DFlash2 drafter | lanes.zig (17 open PRs) |
| engine/0026 | the MTP head's own passes only without a DFlash2 drafter (no switch) | a default-path change, exact | 4.0 to 4.7% of a cold prefill (61 to 86 ms of each 1.5 to 1.8 s chunk) in the fork's measurement, plus the head's rows in every kept state; to be re-measured on main | cuda_engine.zig (14 open PRs) |
| solo-cuts/0001+0002 | `TF_GLM_OVN_SOLO_TO_START` | `TF_GLM_SOLO_TO_START`, default off, exact | cold 8k / 32k first token 4.14% / 1.23% faster, a 3,000-row turn 10.75% faster (OVERNIGHT section 68); needs upstream's `TF_GLM_CHUNK_SOLO` and `TF_GLM_REQUEST_STARTS`, both on main | cuda_state.zig (8 open PRs) |
| engine/0019+0020 | `TF_GLM_OVN_SPARSE_ONEPASS`, `_ONEPASS_PIPE` | one switch each, default off, bit-exact | cold first token -5.30 / -6.74 / -6.95% at 8k / 32k / 120k (queue71, one boot; section 49's two boots -4.73 / -5.84 / -6.51%), decode level at 1 to 8 streams, every cold reply equal across eight boots | kernels.zig (52 open PRs) |
| engine/0027+0031 | `TF_EXL3_DEC_ORDER`, `TF_GLM_OVN_X3_NC`, `_X3_XROW`, `_X3_FUSEDOWN` | after main's item plan, one lever each if each shows a cell | production's decode kernels on the item plan; on v1.2.9 the item plan itself was +3.8 / +3.9 / +5.3% at 1 / 4 / 8 streams (section 41), and it is upstream now (our #2044) | exl3_experts.cu (3 open PRs) |
| engine/0006 (part) | `TF_GLM_OVN_DRAFT_EDGE`, `_BETA`, `_CUTS` | the DFlash2 chain rule, default off | part of the measured recipe arm (section 17); the chain rule needs its own cells on main, and lanes core has changed since (the draft-depth hold, #3468) | cuda_engine.zig (14 open PRs) |
| engine/0006 (part) | `TF_GLM_OVN_DRAFT_NOISE` | `TF_GLM_DRAFT_NOISE`, default off, same replies | sampled streams: fewer rounds with equal replies, prose +0.74 / +1.76 / +2.96%, code +0.74 / +0.57 / +0.44% at 1 / 2 / 4 clients (section 50); greedy streams never read it | cuda_engine.zig (14 open PRs) |
| engine/0022 (part) | `TF_GLM_OVN_MM_DECTILE`, `_SWIGLU_REDUCE` | one lever each when each is measured alone | measured only together with NO_COPY (the +11% code row above); each alone is not measured | cuda_glue.zig (3 open PRs) |
| engine/0023 (part) | `TF_GLM_OVN_MLA_FUSEMERGE` | default off, exact | inside the section 17 arm; alone on main not measured | cuda_forward.zig (12 open PRs) |
| engine/0036, 0037, 0038 | `_LATENT_ROWS`, `_SIDE_PRIO`, `_PIECE_FRONT`, `_PIECE_MLA`, `_PIECE_FFN` | the piece schedule, default off, bit-exact | cold first token -3.6 / -3.8 / -3.5% for the three piece switches, the first turn of a 113k conversation -3.5%, warm turns -1.2% (queue83, section 57); the whole candidate set -9.3 / -9.9 / -9.6% (section 71) | cuda_latent.zig (5 open PRs) |
| restore-held/0001 | `TF_GLM_OVN_RESTORE_HELD` | after #1411 lands | warm turns 0.95% faster at ~113k and 2.54% at ~284k, cold and decode level (section 69) | cuda_state.zig (8 open PRs) |
| engine/0030 | `TF_GLM_OVN_HOST_ONCE`, render and tokenize once | default off | a warm turn at ~250k with request starts: -0.95% idle, -0.35% beside three decoding streams (section 49); 14 code files | root.zig (73 open PRs) |
| engine/0008 | `TF_GLM_OVN_KEPT_WALK` | default off, identical decisions | 540 to 3.0 ms for a warm turn at 600k with 32 kept states on a laptop (host work only); 13 code files and `prompt_cache.zig`, which 16 open PRs touch: last | prompt_cache.zig (16 open PRs) |
| engine/0029 | FP8 latent keys fetched a tile ahead | default path or a switch, to decide on the cells | a kernel change with no cell of its own in the tables: to be measured before it is cut | pending_133.zig (11 open PRs) |

### Tier B: fixes and tests with no switch

| patch | what | note |
|---|---|---|
| engine/0001 | the shared-window check sizes its rows from the engine, not a literal 4 | a test fix |
| engine/0002 | host tests the pin skips: the disk grid with the I/O worker's writer, a quiesce drain | tests only |
| engine/0009 | a pass the rebased index ring cannot hold is refused (`error.PastRing`), not written past it | a guard; no reachable default-path step changes; host test `glm_ring_host.zig` |
| engine/0025 | the DSA head block takes the head count back | a fix with `test-cuda-host` coverage |
| engine/0028 | byte equality by `indexOfDiff`, a string index that stops counting at it | host code; check main's own copy first |
| pr1411/0002 | a disk read sends each block's rows to the other ranks in one step | on #1411's code: after it lands |

### Tier C: measured neutral or a loss: not sent

| patch | knob | cells |
|---|---|---|
| engine/0007, 0012, 0013 | `INDEX_CUDA`, `DECODE_INDEX`, `INDEX_SCHED`, `POOLS32`, `INDEX_REGROUP` | within +-1% at every level (sections 17, 31); `INDEX_CUDA=all` +2.0 / +1.6 / +0.7% at 1 / 2 / 4 clients did not pass its rule |
| engine/0015, 0016, 0017 | `PLAIN_MARGIN`, `EXCHANGE_KB`, `ROUTER_WARM` | inert or neutral (sections 17, 50) |
| engine/0022 (part), 0024 | `MM_WIDE`, `GLUE_FUSE`, `GLUE_ROW`, `PDL_EARLY`; `ABSORB_VEC` | neutral (sections 17, 20, 31); `MM_WIDE` is in the candidate set but measured level on its own |
| engine/0018 | `WIN_FREE` | a loss: -20.9 to -31.2% at 1 to 8 clients (section 44) |
| engine/0022 (part) | `MM_CLUSTER` | a screen below both controls at one and two clients |
| engine/0039 | `PIECE_KDA` | did not pass its rule (queue90) |
| engine/0003 | the prompt-bench step | a tool of ours |

### Tier D: not sendable as written

| patch | knob | why |
|---|---|---|
| engine/0021 | `TF_GLM_OVN_KDA_CHUNKED` | changes bits (production's chunked KDA kernel); upstream takes no mode that changes tokens |
| engine/0023 (part) | `TF_GLM_OVN_KVB8` | changes bits |
| engine/0033 | `TF_GLM_OVN_OFF_EFFORT_LINE` | changes the rendered prompt, so the tokens |
| engine/0004, 0010, 0014, 0035 | our knob registry, our check table, a file split, a check of ours | internal scaffolding: each lever's PR carries what it needs in upstream's own places |

### Tier E: carried until upstream lands the same thing

| package | what | state |
|---|---|---|
| pr1411/0001 | wojo's disk tier (#1411), plus our three changes on the v1.2.9 series | the maintainers rebased #1411 onto main themselves and put it in the landing queue; the package drops away when it lands |
| learn-starts, disk-any-position, restore-held | our additions on the disk tier | each follows #1411 |
| cache-salt/0001, 0002 | `cache_salt` and `--cache-salt-per-key` | the maintainer's own #3222 is open; ours drops away when it lands |

## Overlap, measured

`work/up/open-prs.json` and `work/up/pr-files.json` hold the 382 open pull requests of 2026-11-20 and the files each changes (`work/up/overlap-table.py` derives the column above). The files that decide are `cuda_engine.zig` (14 open PRs), `kernels.zig` (52, one table of kernel names), `lanes.zig` (17), `prompt_cache.zig` (16), `cuda_forward.zig` (12) and `cuda_state.zig` (8); the settings registry and the test lists are append-only, so a conflict there is the ordinary one. Only 11 of our 47 patches apply alone to a pristine main (`work/reseat/independence.json`), so each lever is re-cut, never applied.

## Receipts and the umbrella issue

- The receipts need main-based numbers, so they wait for queue91 (our stack against stock main) and queue92 (what other people's work gave the serve). A receipt window for the pilots follows them: images built from the pilots' branches and from one control, `main` at the cut sha, on the three Sparks, with upstream's tools.
- Upstream has 382 open pull requests and asks for agreement on a gate before a new arithmetic or family change, so the first public step is ONE proposal issue naming the levers, their tiers and what each measures, asking the maintainer which to take first, rather than a batch of pull requests. Its text is a draft until the owner approves the exact words; the per-lever issues follow it.

## State

| lever | branch | state on 2026-11-20 |
|---|---|---|
| `KEEP_SEQS` | `up/keep-seqs`, head `151839e5c`, tree `37d550a25f2a`, cut from `9ba855b3b` | one commit, `git diff --check` clean, `pr_check` 0 errors, lean 168 against 168 with 0 new; gate host: all seven steps pass (check, fmt, ctest, lean, pdl, contract, and `test` at 438/438 steps, 7755/7798 tests, 43 skipped); six of six mutants killed by named host tests (two first forms did not compile and were rewritten); drafts in `work/up/drafts/keep-seqs/`; GPU receipts are queue93 |
| `NO_COPY` | `up/no-copy`, head `f9bf65048`, tree `45ee2c34fe7e`, cut from `9ba855b3b` | main has no switch for it, so it is not a duplicate; one commit, lean 168 against 168 with 0 new; gate host: all six steps pass on the final tree (`test` 438/438 steps); nine of nine mutants killed by named host tests, the wiring of the setting to the lanes included (a first version left that line untested; it moved into a function a host test reaches); drafts in `work/up/drafts/no-copy/`; GPU receipts are queue93 |
| open-PR test trees (#2279, #3616, #3659) | `test/pr-N`, `work/pr-trees/` | a lane is building and gating them; they run after the receipts |
| umbrella proposal issue | `work/up/drafts/umbrella-issue-final.md` | a draft for the `proposal` template, through the voice pipeline and reviewed (`umbrella-review-notes.md`), waiting for the owner's approval of the exact words, not posted |
