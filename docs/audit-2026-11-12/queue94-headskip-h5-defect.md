# queue94: the head-skip verdict cannot be read (H5 vs the arms queue94 runs)

Recorded 2026-11-21 from queue94's own partial rows, while its solo-to-start arms were still running. It is a defect in the RULE against the ARMS, found before any verdict was
published, and it is not a change to the rule: H5 stands exactly as written and the run's head-skip verdict therefore reads NOT DECIDED.

## The observation

`score94.py --dir work/pp94/f94-c` on the rows the five head-skip boots have written:

    HEAD SKIP: NOT DECIDED: H5: hk-A1 (prompt_cache_states is 0); hk-A2 (prompt_cache_states is 0);
                         hk-B1a (prompt_cache_states is 0); hk-B1b (prompt_cache_states is 0); hk-B0 (prompt_cache_states is 0)

and the file it reads, `hk-A1/metrics-after.txt`, says so itself:

    tensorfold:prompt_cache_states 0
    tensorfold:prompt_cache_bytes 6771703808

So the engine holds 6.77 GB of prompt-cache bytes while reporting 0 retained states. Queue99's kept logs show the gauge can be non-zero (`12 states, 7478 MiB` in `ca1`), so the gauge
is not broken in general.

## Why it is a rule-versus-arms mismatch

H5 is written as "bytes per kept state (`prompt_cache_bytes / prompt_cache_states`, states > 0 required) is strictly smaller in both B1 boots than in B0 and in both A boots;
B0 equals A within 0.1%". Its premise is that the served configuration keeps prompt states, because `TF_GLM_HEAD_SKIP` shrinks what a kept state holds: the MTP head absorbs no prompt
rows, so the state it stores is smaller. queue94's arms all run `KNOBS=off`, which applies only `prod.env`'s runtime section; nothing in that section creates kept states, and the
boots end the cell with 0 of them. The lever under test cannot be measured in an arm set that never populates the thing it is supposed to shrink.

H5 is a fails-if-violated clause and a NOT DECIDED is not a violation, so the run does not fail and does not hold: it is silent about the lever. That is the correct behaviour for a
rule that cannot be evaluated, and the wrong answer to carry forward as if it were a result.

## What the corrected run needs

An arm pair that keeps prompt states while the cells run: `KNOBS=prod` (or the runtime section plus whatever the recipe sets to keep states), request starts on, so each turn's state
is the one the next turn resumes from, and the same five labels A1 A2 B1a B1b B0. H5 then applies as written, and H4's cold clause still reads `cache-<N>.json`. The rule for that run
is unchanged; only its arms differ, and it must be written down before those arms boot.

## What this does not affect

H1 (checks clean, one digest a cell), H2 (the switch's own log line: 1 line in `hk-B1a` and `hk-B1b`, 0 in `hk-A1`, `hk-A2` and `hk-B0`, so the switch did take effect), H3 and H4
all read normally on these rows. The solo-to-start half of queue94 is unaffected: its clauses read `concurrent.json`, `ours-rows.jsonl` and the check logs, none of which touch the
states gauge.

## queue107: the same clause fails with the states kept, and the premise is what is wrong

queue107 re-ran the head-skip arms with `KNOBS=prod` plus `TF_GLM_CHUNK_SOLO=4096` and
`TF_GLM_REQUEST_STARTS=1` on every arm, so a turn keeps the prompt state H5 wants to divide by. The verdict is the same
`NOT DECIDED`, and the cause is now visible in the numbers: `prompt_cache_states` reads 0 on all five labels
(`hk-A1`, `hk-A2`, `hk-B1a`, `hk-B1b`, `hk-B0`), while the same boots report `tensorfold:prompt_cache_bytes` lines and
3 states lines in `metrics-after.txt`.

So H5's premise is wrong rather than its threshold. The probe is one cold single-turn request per size, and a
single-turn request is not what keeps a state: queue100's 34.51% warm-turn gain came from a conversation, where
`TF_GLM_REQUEST_STARTS=1` keeps the state at each request start. A one-turn probe in a serve configured to keep states
creates none, so the divisor is zero by construction and no amount of rerunning decides it.

The measurement H5 needs is a conversation: several turns that grow a prompt, with the head-skip count and the kept
states read on the same request, and the switch's cost divided by the states actually created. That is a new rule for a
new instrument, written before its rows, not an edit to this one.
