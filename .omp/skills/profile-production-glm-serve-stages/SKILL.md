---
name: profile-production-glm-serve-stages
description: "Profile the live python GLM production serve (spark1 glm53-flash-tf) per-stage or compare it to ai-engine on an identical prompt, when the owner frees the production sparks; covers the env-file forwarding, restore, and what each stack's profiler does and does not emit."
---

# Profile the production GLM serve against ai-engine on an identical prompt

Use only when the owner has said the production sparks (spark1-3, `glm53-flash-tf`, image `tensorfold-glm53:v110hunt4`) are free. Restore production afterward.

## The decisive comparison is the identical prompt on both stacks, token-matched

1. Drive the SAME prompt file (e.g. `/home/adam/perpatch/prompts/c32.txt` on spark1, `~/perpatch-ai/prompts/c32.txt` on spark4) cold (`max_tokens: 1`, `temperature: 0`, no cache or a fresh `cache_salt`) on both serves and read `usage.prompt_tokens` from each response. Only compare when the token counts match. Never compare by character count (GLM ~0.196 tok/char).
2. Do it at 2-3 lengths (truncate the file by chars, then READ the returned token count). A delta that grows linearly with tokens is per-token; a constant delta is fixed per-request.
3. Cross-check against RigMark's `effective_prefill_tokens_per_second` at the same `prompt_tokens` (`~/prof/rigmark/*.json`, field `prefill.<N>.cold`). Production reconciles; ours reads pessimistic in RigMark (extra cold warmup).

## Adding TF_GLM_PROF to production (python stack)

- The launcher `~/glm-v110-start.sh` sources `~/v110.env` -> `~/v110ots.env` and forwards every exported `TF_GLM_*` as `-e`. Verify with `cd ~/mia110 && . ~/v110.env; DRY_RUN=1 ./start-tp3.sh | grep -o 'TF_GLM_PROF=1'` BEFORE touching anything.
- `cp ~/v110ots.env ~/v110ots.env.bak-prof; echo 'export TF_GLM_PROF=1' >> ~/v110ots.env; docker rm -f glm53-flash-tf samplers pwcap; setsid bash ~/glm-v110-start.sh > ~/prof-restart.log 2>&1 < /dev/null &` (detach; the launcher holds the SSH channel and paramiko times out otherwise). Boot ~2-4 min; poll `curl -sf :8888/health`.
- The python stack's `TF_GLM_PROF` does NOT emit per-stage prompt-chunk lines in the Zig `glm prof prompt chunk` format. Its decode-round profiler is `TF_GLM_MULTI_PROFILE=20` ("multi profile (batched)" lines, parsed by `scripts/glm53/v110/lanes/DecNsysMimo/stageprof.py` / `Prose100/parse_prof.py`). Its prompt-stage numbers come from nsys (`DecNsys*` lanes) and ncu CSVs (`lanes/ExpertsFable/logs/ncu-gu4096-ref-source.csv`). Do not expect a capturable prompt-stage breakdown from the env flag alone.
- RESTORE: `cp ~/v110ots.env.bak-prof ~/v110ots.env; rm ~/v110ots.env.bak-prof; docker rm -f glm53-flash-tf samplers pwcap; setsid bash ~/glm-v110-start.sh ...`; then verify `docker inspect glm53-flash-tf --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -c PROF` is 0 and `/health` is up.

## Our side (ai-engine) per-stage is one boot away

`serve4.sh` with `XENV="-e TF_GLM_INDEX_CUDA=1 -e TF_GLM_PROF=1" XSERVE="--metrics-open --prompt-cache-gib 0"`, send the prompt, then `docker logs glmperf3-r0 | grep 'glm prof prompt chunk'`. Read `wall` vs `gpu`: gpu > wall means the gathers overlap compute (GPU-bound, no host idle). Pattern: `scripts/parity/c32prof-chain.sh`, `coldprof-chain.sh`.

## Check the ledger FIRST

Before any of the above, grep `docs/SPEEDUPS.md` ("Trades kept") and `docs/PARITY.md` for an owner decision that already explains the gap. On 2026-11-06 the whole cold-prefill deficit was SPEEDUPS.md line 137: production's prompt numerics (KDA_CHUNKED + SPARSE_ONEPASS + LATENT_MMA) are faster but change bits, and the owner chose keep OFF on 2026-10-31. Production's log on the freed sparks names its knobs (`grep -iE 'KDA_CHUNKED|chunk' <(docker logs glm53-flash-tf)`), which is the fastest pointer to that ledger entry.
