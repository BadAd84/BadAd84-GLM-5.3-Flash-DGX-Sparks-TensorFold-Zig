---
name: orchestrate-overnight-speed-hunt-lanes
description: "Owner wants agents to hunt every speed gain in a Spark serve overnight: lane briefs, patch stacking, final-tree test registry, GB10 kit, measurement chain order."
---

# Orchestrate an overnight multi-agent speed hunt on a Spark serve

For requests like "orchestrate multiple agents to pick this code base apart looking for speed gains overnight" on a
TensorFold serve. First run: glm5.3-flash-dev, 2026-10-29/30, ~40 lanes, ~90 candidate patches. Record:
`docs/notes/speed-hunt-2026-10-30.md` and `docs/notes/speed-hunt-2026-10-30/` (every lane's REPORT, patches, tests,
mutants, `VERIFY.md`); GB10 kit `scripts/glm53/v110/hunt-kit/`; chain `scripts/glm53/v110/perpatch/chain_wave5.sh`.
Scratch lives in the gitignored `work/hunt/`.

## 1. Lanes
- Phase 1: one lane per area of the serve path (host request, host reply, admission/pool, round loop, drafter,
  decode attention, matmuls/experts, prompt chunks, comms, spill tier, knobs/boot, upstream backlog).
- Phase 2: verify each report yourself: the patch applies to the tree, its test passes with it and FAILS without it,
  its mutants die, the claimed numbers re-measure.
- Phase 3: gap lanes from a MEASURED coverage table (a script over every lane's per-module coverage table; the first
  hunt sat at 71% of 46,565 serve-path lines with 30 files at 0%), port lanes (upstream PRs, sibling-family branches),
  adversarial review lanes, and one lane per regression a GB10 wave shows.
- Every brief: write only to `work/hunt/<Lane>/`; never touch a Spark; WSL one process, scratch on ext4 under `~/`,
  under 3 GB, never `--shutdown`; laptop GPU only through `work/hunt/gpulock.py`, extensions built before taking the
  lock; profile before proposing a mechanism; probe with the system's own code (real tokenizer:
  `work/hunt/hostfix/model/`); each patch = a test that fails without it + mutants + interleaved old/new timings; the
  knob-off path is the old code byte for byte; findings reported INLINE.
- Before a follow-up lane, grep earlier lanes' patches for the same lead. Twice two lanes built one lead
  (HuntPrefill-4/5 vs PrefillLeftovers-1/2; HuntMatmulExperts-1/2 vs HuntUpstream-4/3). Keep one implementation.
- Give lanes production's source to diff against: `docker create` the production image, `docker cp
  <c>:/usr/local/lib/python3.12/dist-packages/tensorfold`, tar without `*.so` / `__pycache__` (on an idle node, under
  `nice -n 19 ionice -c3`), unpack into `work/srcx/<tag>/`.

## 2. Stacking
- `work/hunt/stack/<name>.list` + `bash work/hunt/build_stack.sh <out> <list>` (under WSL: a fresh copy of
  `work/hunt/tree`, `patch -p0 --batch`, exit 1 on any failed hunk). Late patches go at the END; a conflicting patch
  is rebased by its own lane as `-Nb`.
- After every list change, audit every lane `*.patch` against the list (`comm -23` of the two sorted sets) and
  classify each absent one in the notes: superseded, rebased, or not stacked with the reason. One candidate
  (HuntDrafter-3) was never added at all.
- Recurring stacking defect (three times, four patches): an attribute set only in `__init__` and read on a knob-off
  path crashes tests that build the object without `__init__`. Demand class-level defaults equal to "off" in briefs.
- Run every lane's tests and the repo gates on the FINAL stacked tree, not each lane on its own base (lane Registry:
  `work/hunt/Registry/registry.json`, `python work/hunt/Registry/run_registry.py <tree> [--only id,id]`). That run
  found the `__init__` crash, a knob the prepared-weights gate wanted classified, and the missed candidate; running a
  gate at other trial counts found it failing correct code below ~1,000 trials (fixed floors). Fold such fixes into an
  `Integration-N` patch at the end of the list.

## 3. GB10 kit and chain
- Kit: `cd work/hunt/Gb10Kit && bash make_kit.sh ../stack/<list>` (WSL) gives `out/kit` (the image layer's files,
  their sha list, and its OWN kernel-cache label seeded from the base label: CUDA sources changed under unchanged
  extension names would otherwise load stale compiled kernels) and `out/stage` (GPU exactness tests with reference
  trees). Rerun after every list change.
- Deploy: tarballs into `work/hunt/deploy/`, scp to spark1, unpack the kit on spark1-3 and the stage on spark1,
  update each box's `~/INVENTORY.md` in the same action with an idempotent script.
- Chain on spark1, detached: wait for the run in flight (`pgrep -f "perpatch/perpatch_run[.]sh"` and
  `/tmp/perpatch-in-progress`); build the image on every node and compare laid files to the kit's sha list; build the
  kernel folders with the serve down; smoke-boot at P8 and P1; then the waves; then the GPU tests
  (`PERSIST=$HOME/gb10kit-builds` shares each tree's builds; estimated 2.5-3.5 h for ~40 tests).
- ORDER BY THE OWNER'S QUESTION: the headline wave (`prod`, the base image and the stack, at 1/2/4/6/8) runs right
  after the smoke boots, before long GPU steps and old confirmations. The owner asked "any wins from overnight?" the
  next morning while ~6 h of GPU tests and confirmations sat queued ahead of the stack's first number. Every wave's
  reply digests already flag a reply difference.
- A serve-down window longer than 20 min needs a `/health` stand-in on 127.0.0.1:8888 returning `{}`, or the GLM
  watchdogs (DOWN_LIMIT 40 x 30 s) start production under the tests; an EXIT trap restores production.
- Start or replace a detached chain with a launcher SCRIPT run by path. An inline `ssh '... pgrep -f "x[.]sh" ||
  setsid bash x.sh'` matches its own ssh shell (the launch branch names x.sh) and starts nothing.
- `perpatch_run.sh` refuses, before any boot, a hunt arm whose `TF_*` setting the image never reads.

## 4. Reading results
- `perpatch_report.py <run dir> --ref <arm>`: + is better with the change, `*` both boots on the same side. Put
  production (`prod`) in the first wave: the synced image's own regressions show up there (masked-turn host time and
  the P8 pool, first hunt).
- Per boot, TTFT minus `d_prefill_seconds_total` (both in `<boot>.measure.log`) is host time before the first token;
  that split pinned the masked-turn regression to the host in one pass.
- One request per boot carries per-boot noise (P1 forks: +-20 ms, bimodal, within one image). Two boots a side cannot
  resolve 10 ms: use six or more, or repeated mirrors.
- In a two-arm mirror A B B A the B arm always sits in the middle; before blaming B for a small steady gap, rerun with
  the arms swapped.
- A pool difference with no code change: diff the boot logs' workspace and startup-estimate lines and the recipe's
  `config.sh` defaults. Upstream's `TENSORFOLD_VISION_WORKSPACE_MIB=1440` (production 768) cost ~104k pool tokens at
  P8, where the pool is budget-bound rather than capped.
- Every candidate stays a candidate until GB10 shows no regression at any level; a loss goes through the fleet rule's
  5-step procedure, and a trade goes to the owner.
