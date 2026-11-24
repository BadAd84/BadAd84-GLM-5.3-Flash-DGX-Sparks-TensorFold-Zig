---
name: ab-a-serve-change-on-the-spark-triangle
description: "A/B a change to a local LLM serve on the DGX Spark triangle with matched instruments (counters, per-stage profile, reply digests), including the harness and its measured traps."
---

# When to use
A/B a change to a local LLM serving engine on the DGX Spark triangle (spark4/5/6, TP=3): a kernel knob, a drafter, a transport, or a sharding change. Also for measuring one stage of decode against a reference stack.

# Non-negotiables
- Every GPU job takes `flock -o ~/work/gpu.lock` on each box it uses.
- Exactness before speed: smoke, drafted==serial, concurrent==solo, resumed==fresh, per boot.
- Never run two chains at once: `stop3.sh` removes containers unconditionally, so two chains kill each other's serve mid-measurement.

# Procedure
1. Build the image on spark4 (`build-image-gram.sh TAG src.tar`), then ship it: `docker save IMG | ssh adam@spark5 docker load` (and spark6).
2. One cell = a fresh boot: `serve3.sh RANK P` for TP=3, or `serve4.sh` when extra serve flags are needed (`XSERVE='--metrics-open ...'`); wait for /v1/models.
3. Send ONE smoke request before the gates. A request-time crash (a stride bug, a missing mount) then shows the server's own message instead of an empty result.
4. Gates, then `streams.py ... --out res/x.jsonl` (the `--out` is mandatory), then read the engine's counters.
5. `stop3.sh TAG` to release the boxes; check `docker ps` is empty afterwards.

# Instruments
- Counters: `/metrics` (needs `--metrics-open`), names prefixed `tensorfold:`: decode_rounds_total, mtp_drafted_total, mtp_accepted_total, generation_tokens_total. `/health` has no counters.
- Per stage: `TF_GLM_PROF=1` prints `glm prof verify N rows` with embed/kda/mla/gather_a/dense/router/routed/shared/gather_b/head in ms per call.
- Reply identity: `streams.py` rows carry a per-prompt `sha`; equal digests across arms mean the change did not alter numerics.

# Traps, all measured
- `pkill -f <pattern>` kills your own remote shell when the pattern text appears in the command you are running. Use `pgrep` first, then `kill <pid>`.
- A drafter or any host folder must be MOUNTED into the container (`-v $HOME/dflash2:/dflash2`), or the engine reports "neither a directory nor a Hugging Face repo id".
- GNU `tar -L` means tape-length, not dereference. Use `tar -ch` to follow symlinks (HF snapshots are symlink farms).
- Download weights on the box itself; HF runs at ~100 MB/s against a laptop relay's ~1 MB/s.
- Editing a bash script that is already running does nothing: functions are parsed when defined. Kill, edit, relaunch.
- A profile stage that includes projections and a chain together will mislead you; attribute by kernel before concluding which half is slow.

# Acceptance
No regression at 1/2/4/6/8 streams (a gain at some and a loss at others is a trade only the owner can accept). Replies identical unless the owner accepts a numerics trade in writing. Every kept change carries its gates and its A/B in the report.
