---
name: qualify-a-persistent-prompt-cache-tier
description: "Use when proving a disk-backed prompt/KV state tier on a TensorFold Spark serve: equal-depth exactness, level at every stream count, disk budget, crash resume, and the shape trade."
---

# Qualify a persistent prompt-cache tier

For a tier that writes kept prompt/KV states to disk so a restart, eviction or crash resumes instead of re-prefilling. Every claim below needs its own cell; none follows from another.

## Order of work
1. Read the lookup before measuring: what is in the state identity (token test, decode-span list, chunk height, page height)? A state is refused when ANY keyed member differs, and a refusal looks exactly like a missing state in the logs.
2. Re-run the ORIGINAL working request as a control before blaming the code. A changed last turn (role, trailing message) that sits inside the keyed prefix refuses the boundary state and turns every resume cell into a silent prefill. Grep the boot log for the tier's read line (`imprint: read N tokens`) on every arm; a with-tier number without it is a prefill.
3. Equal-depth exactness: build three resume depths deliberately (the boundary, one turn behind so a span is recomputed, and a state truncated by the store) and compare each reply byte for byte against a no-tier run of the SAME prompt. A divergent pair at different depths proves nothing; say so rather than reporting it as a defect.
4. Level at every stream count the shape admits, tier on against off, two boots an arm, alternating, noise rule. Name the levels admission refuses rather than omitting them.
5. Crash resume: SIGKILL mid-decode, reboot, confirm the boundary state resumes and report its depth and TTFT against the cold twin.
6. Disk: bytes a seed, an append and a rewrite write; bytes a turn after any dedup; the budget and what eviction does (a skipped save must name its reason and re-prefill cleanly, never error).
7. Rewrite turns: a state is keyed to its old prefix, so an edit re-prefills and branches a fresh state. Measure it and say so; do not fold rewrites into append averages.

## Traps measured on this repo
- A silent no-op beats a refusal as a defect: at 8 x 262,144 the memory plan granted the prompt cache 0 bytes, so `--prompt-cache-disk` did nothing and said nothing. Make the plan refuse by name when it leaves the cache no bytes, with a witness test in the cache-budget filter.
- Zig prints no test name on a pass, so a witness check that greps for the name can never pass. Run the built test binary and read its own line; prove the check fails on a reverted patch and on a planted false assertion.
- Two state files a turn usually means the keep is deduplicated only against RAM and happens before the disk recall; re-point the rewind to the recalled state after the recall, and pin it with a test that fails on the old code.
- State sizes at fp8 on one GB10: 32k 0.635 GiB, 100k 1.87 to 1.96 GiB, 131k 2.41 GiB, 261k 4.70 to 5.14 GiB. Size the shape from these before promising a resume.

## Shape trade, stated not decided
Slots x window x granted cache decides which states fit: 8 x 262,144 with the page pool grants about 3.1 GiB (a 100k state fits, a 261k one does not); 4 x 262,144 grants about 5.1 GiB (one full-window state); 8 x 131,072 grants about 3.7 GiB (several agent-size states). Present the measured cells and let the owner choose.

## Report
One table per axis with the tier on and off, exactness pairs named by hash, bytes a turn, the levels admission refused, and the restore evidence (health, image id, a named OK marker).
