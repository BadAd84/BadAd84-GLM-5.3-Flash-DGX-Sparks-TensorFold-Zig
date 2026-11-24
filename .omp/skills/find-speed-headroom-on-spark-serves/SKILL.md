---
name: find-speed-headroom-on-spark-serves
description: "Use when speeding up Spark serves (GLM TP=3, Qwen spark4, Clef spark5): attribute growth, roofline, bit-exact patch, live A/B."
---

# Find and ship speed headroom on the Spark serves

Covers GLM-5.3-Flash (TP=3 on spark1-3, port 8888), Qwen3.8 Flash Next (spark4) and Clef (spark5).

- **Tools:** glm5.3-flash-dev `scripts/glm53/v18/`, with copies in spark1's `~`.
- **Ledger:** `docs/GLM53-TENSORFOLD-TP3-PORT.md` section 6 (F-rows).
- **Campaign table:** `docs/GLM53-SPEED-CAMPAIGN-2026-10.md`.

Read the latest F-rows first. They record what already runs at the roofline and what was dropped.

## Ground rules

**Bits are sacred.** Every change must keep replies byte-identical:
- **GLM:**
  - `firstreq.py 8888` gives `011a34adf6`, and `draftcmp.py 8888` gives 7/7 SAME.
  - `ab_long.sh` digests: 35k seed 932 `e5ca6f1dfb`, 226k seed 777 `b7bcd5ecbe`, 590k seed 591 `48b8c37380`.
  - `realdec_ab.sh` digests: code `237e4c3535`, prose `f9295d681a`.
  - The `~/realdec` corpus was copied once. Never refresh it, or the digests change.
- **Qwen:** run `cd ~/work && python3 qf_harness.py golden /tmp/g.json && python3 qf_harness.py diff golden-pr319-final.json /tmp/g.json`. It must report 6/6.
- **Clef:** on spark5, `clef_ref.py compare ~/clef/ref-clef2.json` must report identical; then run `determinism_check.sh`.

**Owner rules:**
- This work runs on Opus 5.5, subagents included (RULES s9 exception).
- Stop Hermes for the duration of measurements and restore it afterwards. On CT106: `export XDG_RUNTIME_DIR=/run/user/0`, then `systemctl --user stop|start hermes-gateway` and `systemctl stop|start hermes-dashboard`.

**Label every tok/s with its workload.**
- `longdec.py`'s filler accepts ~15 tokens a round, the best case for drafting. Real code accepts ~4.3, real prose ~2.5.
- Make claims with `realdec.py`. ms per round is the content-independent metric.

**GPU clocks run unlocked** (owner, 2026-10-07). Any bench that locks them must end with `sudo -n nvidia-smi -rgc` on all three Sparks.

## 1. Attribute before building (GLM)

- **Decode growth with context:** run `nsys_ctx.sh`. It takes one capture of the same fixed prompts at 35k and then 226k, on NCCL with eager wide windows. Then:
  - `ctx_kern.py <sqlite> <run.log>` ranks kernels by their growth per round;
  - adding a kernel name splits that kernel's launches by compiled variant and grid, which tells a Triton kernel's constexpr steps apart.
- **Cold-prefill growth:** `nsys_prefill.sh`, then `prefill_kern.py`. `TF_GLM_PROFILE=1` does NOT cover prefill under `--parallel`, because `multi_prefill.py` never reports.
- **Memory roofline:** `nsys_dram.sh`, then `dram_kern.py <sqlite> <kernel>`.
  - Use GPU metrics set `gb20y-top`; GB10's default set has no memory counters.
  - Calibration: `SysL2 Throughput` 10.5% is a pure read at the achievable ~239 GB/s (a copy reads 15.7%).
  - At or above 10.5%, the kernel is memory-bound and there is no kernel headroom. Measured so far: `dec_kernel` and `qmm_kernel`, about 72% of a GLM decode round. Qwen's `qmm_kernel` measures 94-106% of 240 GB/s.
- **Exposed communication:** `comm_overlap.py <sqlite>`. Kernel time under NCCL is not the same as what overlap could hide (measured at most ~5%).
- **Profiling-copy traps:**
  - The recipe's `config.sh` derives `TF_GLM_WIDE_GRAPHS` from `COPY_CODE` and ignores the environment. Edit that line in the profiling copy, as `nsys_ctx.sh` does.
  - Take one nsys capture per boot, and run the container with `--cap-add SYS_ADMIN`.

## 2. Reproduce the hot kernel alone

**Copy every size from the PRODUCTION call site** (grep the callers of the buffer's constructor).
- The trap that hid a 20x cost: `verify.py` sizes `SelectScratch` by the whole pool, 512 chunk programs a row.
- A bench sized by one stream's window (128 chunks) measured 0.26 ms, where live took 5.6 ms.

**Compare against a verbatim copy of the pre-patch kernel**, placed in the bench, so it runs in any image.
- Compare whole outputs bit for bit (`torch.equal` on int32 views).
- Pre-fill the buffers, so a slot the kernel never writes shows up.
- Faster arms that change bits are not deployable (seen: 8 warps on a dot, one dot over stacked heads).

**Run it in** `tensorfold-glm53:v18-ots` with `--gpus all -v ~/.cache/tf-triton-bench:/root/.triton`. Running beside an idle serve is fine at ~2-3 GiB.

## 3. Patch, prove, build

1. Write `00NN-glm-*.patch` beside `build_v18.sh`. Patches apply in name order with -p1.
2. Write a GPU test, `test_*.py`: the old kernel plus an oracle.
3. Write `mutants_00NN.sh`:
   - each anchor must match exactly once;
   - a kill needs a non-zero exit AND a FAIL line;
   - it prints `exit N`.
4. Copy the patches into `~/v18-build`, then run `bash ~/v18-build/build_v18.sh tensorfold-glm53:v18-ots-00NN`. All three nodes must report the same files digest.

## 4. Live A/B

**Decode change:**
1. On all three nodes, tag the current `v18-ots` as `v18-ots-pre00NN`, then tag the new image as `v18-ots`.
2. Restart and measure: `setsid nohup ~/restart_when_idle.sh <label> 1200 bash ~/ab_long.sh <label> > /dev/null 2>&1 < /dev/null & disown`.
3. Four agents at once: `multidec.sh 8888 520000 1000 591 592 593 594`.
4. Real text, old image against current: `realdec_ab.sh <old tag> 700000 663000`.

**Prefill change:** `cold_ab.sh <label> <new image> <seed1> <seed2>`.
- It snapshots the NVMe tier's entry names and runs arm A.
- It then stops every rank and deletes the points and blocks arm A created, by name.
- Arm B must report `cached 0`.
- Use fresh seeds on every run.

**Warm agent turns:** `warmturn.py` appends new text to a cached prompt.

**Afterwards:** drop the staging tag and keep `pre00NN` as the rollback image.

## 5. Record

1. Update the production doc (patch list, `tf.ots-patches` shas, rollback images), the ledger F-row and the campaign table.
2. Run the gates:
   - `scripts/check-doc-inventory.sh`: every `scripts/glm53/*` file must be named in the production doc.
   - `scripts/check-python.sh`: module-level closures over loop variables fail it; use `functools.partial`.
3. Refresh `docs/spark-live-state.json`.
4. Update every touched Spark's `~/INVENTORY.md`.
5. Commit signed with `git commit -S -F <file>`.

**Upstream:** put the PR package in `upstream/recipe-pr-*/`:
- `pr.diff`, made from a recipe worktree at `33b50fd`;
- `PR.md`;
- `mutants.sh`, using `patch -p0`.

Validate the package on `tensorfold-glm53:v0.6.0-31557ed1` before handing it to the owner.

## Delegated lanes (Qwen, Clef)

- A lane's final JSON can show truncated at `agent://<id>`. Extract the yield from the session JSONL: the last assistant toolCall `yield`, whose `arguments.data` is a dict with `report` or a string.
- Verify before committing. Re-run golden yourself on the deployed serve and review the diff. A diff that rewrites a whole file is often only CRLF; check with `diff --strip-trailing-cr`.

## Shell traps

- The harness bash is MSYS. Syntax-check with `"C:/Program Files/Git/bin/bash.exe" -n`. A bare `bash` is WSL and cannot see `/c` paths.
- Never add another redirect after `> log 2>&1` on a nohup line: it replaces the log.
- `pkill -f` with a literal pattern kills its own ssh shell; use a `[x]` pattern.
- Killing a runner orphans its docker container. Kill containers by `--filter ancestor=<image>`.
