# AcceptGap, 2026-11-14: why production keeps 3.00 tokens a round at one stream and we keep 2.77

CPU only, existing data only. Our engine was read from `work/accept-gap/w/tree` (a `--shared` clone of
`work/parity/tree` at the pin `93a2e93e` plus `patches/engine/` by `scripts/apply.sh`: 33 applied, `SHA256SUMS` ok;
removed after the run, `bash work/accept-gap/setup-zig.sh` rebuilds it; `Z:` below is `zig/src/families/glm/`, `ZL:`
`zig/src/core/lanes/`, `ZS:` `zig/src/server/`, `K:` `zig/kernels/cuda/`). Production's code is the served package
rebuilt from the `production` branch (`setup-prod.sh`: the Python repo's extracted synced tree `work/srcx/v110sync6`
plus the branch's hunt, fix and shard patches); the cited files are kept in `prod/` and every one equals the image's
`production/build/image-files.sha256` byte for byte (`prod/SHA256-rebuilt.txt` against `prod/SHA256-image.txt`) except
`multi.py`, whose rebuild misses the two `HuntRoundLoop-3r` fill-slice hunks (prompt fill only). `P:` is
`families/glm5_next/cuda/`.

Data, all read-only:
- our cells: spark1 `~/bench` copied to `cells/` (`cells.py`, `p1_texts.py`), including the chain-rule arms run on
  2026-11-14 03:02-04:06 (`cr-ctl`, `cr-prod`, `cr-prod-b`, `cr-ctl-b`, `cr-e2`, scored by `cr_ab.py`; `cr-ctl-log`,
  `cr-prod-log`, the first `dflash2 round` logs of our engine on spark1, scored by `chain_log.py`);
- the fork's chain-rule cells (ai-engine `work/parity/ai/fx/fixed2.jsonl`) and its one chain log
  (`work/parity/ai/rep0diag/rounds.txt`, 2026-10-31, the only `dflash2 round` lines in ai-engine's `work/`);
- production's drafter records (`TF_GLM_DRAFT_DUMP`): the DraftPolicy set (Python repo `work/hunt/DraftPolicy/dumps`,
  `sim_rules.py`); 16 records of the sdbench prose request from the perpatch waves of 2026-11-02 (spark1
  `~/perpatch/dumps-20261102-{103755,164001}`, `sim_prose.py`, `reach_prod.py`); and 120 sampled agent-turn records
  from the waves of 2026-11-01 (`~/perpatch/dumps-20261101-{071059,104407}`, `sim_noise.py`), all copied to
  `proddumps/` and found with `scan_dumps.py`, run on the head from the command line, nothing written there;
- DrafterFG's probe lines (spark1 `~/prof/drafterfg/run.log`, `summary.md`) and the served launcher (`~/mia110` at
  `549fdc5`).

## 0. The gap on one counting basis

| | rounds a request | drafted | accepted | tokens a round | drafts a round | acceptance |
|---|---:|---:|---:|---:|---:|---:|
| ours, seven-knob set (`rs2-ctl`, `env-ctl`, `is-ctl`, ...; reply `323d3f5bcb55`) | 144 | 391-392 | 255 | 2.771 | 2.720 | 0.651 |
| production (`prodwin`, `prodprof`, DrafterFG `incA/B`; reply `8347edfe4ee6`) | 133 | 388 | 266 | 3.000 | 2.917 | 0.686 |

Both on 399 decoded tokens (the first token is the prompt pass's draw in both engines; `rounds + accepted = 399` in both
cells). The quoted 3.01 is 400 / 133 (first token included), so 0.008 of the quoted 0.24 is counting; the gap is
**0.229 tokens a round**: 11 accepted drafts and 11 rounds a request, worth 2.9 ms of our 38.2 ms round.

## 1. The four factors

The rule's share depends on which side it is swapped on, so both are measured. From production's side: production's
rule, drafter and text (3.000, live) -> our rule on production's drafter and text (3.023, replayed on production's own
records of this reply, section 5). From ours: our rule, drafter and text (2.771, live `cr-ctl`) -> production's rule
on our drafter and text (2.810, live `cr-prod`, replies identical, section 7). Our drafter (M-b, section 8) then
separates (a) from (b).

| factor | tokens a round (of 0.229) | acceptance (of 0.035) | evidence |
|---|---:|---:|---|
| (c) draft-chain policy | **-0.023 to +0.039** | +0.019 to +0.023 | production's side: draft_sim on production's records of `8347edfe4ee6` (exact here: production's rule replays to the live 133 rounds and 388 drafted, `check` 1.0): production's rule 133 rounds, 388 drafted, acceptance 0.688; ours 132, 403, 0.665 (`sim_prose.py`). Our side, live on our engine (`cr-ctl` against `cr-prod`, 2026-11-14, every reply equal): ours 144 rounds, 391 drafted, 0.652; production's rule 142, 383, 0.671 (`cr_ab.py`). Text-dependent: +0.048 and +0.119 on production's two other texts of this prompt, +0.084 on the fork's text, about +0.04 on 24 agent turns |
| (a) text and prompt | **+0.190 to +0.252 together with (b)** (3.000 against 2.810 under production's rule, 3.023 against 2.771 under ours); the split is M-b | +0.014 to +0.015 with (b) | the prompts differ by 7 tokens on every prompt (section 2); production's own rate moves 3.000 / 3.117 / 3.142 over three texts of this prompt at one drafter and rule, and 3.000 against 2.77 on a 33.5k-token prose context; ours moves +0.07 to +0.11 when a target-numerics change rewrites the reply (section 3) |
| (b) drafter arithmetic and taps | inside the 0.190-0.252 | inside the 0.014-0.015 | our knobs move it about 0 on our text (ONEPASS 0.000, DOWN4 -0.019, MLPSPLIT 0.000). But at matched rules, at every cut from 0.7 to 0.2, our engine sits 0.21-0.44 below production's drafter on all three of its texts, which span 0.05-0.19 among themselves; our logged chains are right as often as production's at depths 1-2 and less often than on any of production's three texts from depth 3 on (whole-chain correct 2.21-2.30 a round against 2.42-2.62), while the cut loses no more of ours; and on identical reply text the fork's Zig drafter ends its chain early 9 times against 2, mostly at margins of 1.5-17 logits in production's lattice (section 4) |
| (d) what counts as accepted | 0 (0.008 of the quoted figure) | 0 | the same greedy-equality keep and the same counters (section 6); the replay matches production's live rounds and drafted exactly, and counts one more accepted draft (267 against 266), the end-of-reply draft production's `take` cuts |

What changed from this report's first version: (c) was put at +0.04 to +0.09 from other texts (the fork's prose
reply and production's agent turns). Measured on the two texts of the gap, the rule is worth -0.023 to +0.039 tokens a
round; it buys tok/s at every stream count (+1.7% to +3.4% live) by drafting fewer rows at higher precision, and with
NOISE 0.7 on sampled traffic about +4.9% by replay (section 7). At least 0.19 of the 0.229 sits in (a) + (b).

## 2. (a) The two serves answer different prompts

streams.py sends `chat_template_kwargs: {"enable_thinking": false}` (`scripts/streams.py:125-127`). The checkpoint's
`chat_template.jinja` (spark1 snapshot `078455ffe647`, copy here) has no thinking switch and always renders
`<|system|>Reasoning Effort: Max` unless the effort is low or high.

- Production: `GlmTokenizer.apply_chat_template` sends thinking-off text through `thinking_off`, which drops the
  effort line and closes the think block (`tensorfold/families/glm5_next/prompts.py:11-12,113-120,132-143`): 33 tokens.
- Ours: the template is rendered with `reasoning_effort = if (thinking) effort else null`, so `Max`, and only the
  dangling `<think>` is closed (`ZS:prompt.zig:48-57,79-95`; `ZS:chat.zig:149-155`): 40 tokens. rank 0's log says
  `prompt cache: 40 tokens` (`work/drafter-lever/spark1/bench/rs2-ctl/r0-P1.log`), the fork's cells record
  `prompt_tokens [40]`.
- `prompt_tokens.py` tokenizes both with the checkpoint tokenizer: 33 against 40, the 7 tokens of the effort line.
- The same 7 tokens on every other prompt: the fork's chain log against production's DraftPolicy records of the same
  six requests reads 34/27, 33/26, 40060/40053, 44/37 twice and 202414/202407.

So no cell compares like text: the replies differ by prompt as well as by numerics. Our rendering follows the
checkpoint's template and production's drops the line, so this is not a defect of ours. Aligning the rendering would
change our reply digests: an owner decision, not a speed lever.

## 3. (a) Text alone, measured at a fixed drafter and rule

Production (`sim_prose.py` on its records; DrafterFG):

| production's text of the sdbench prose prompt | prompt | production's rule | our rule |
|---|---:|---:|---:|
| `8347edfe4ee6` (served; 10 records, all one lattice) | 33 | 133 rounds, 3.000 | 132, 3.023 |
| `7e1d5851c9eb` (the wave's other arm, 3 records) | 36 | 128, 3.117 | 130, 3.069 |
| `1325539f6f53` (the same arm, 3 records) | 36 | 127, 3.142 | 132, 3.023 |

DrafterFG (`summary.md`, `run.log` STAT lines; image `v110-ots106-dfg`, the incumbent drafter): sd-prose 3.000 at
acceptance 0.686 (133 rounds, 388 drafted, 266 accepted: the live figures above), rd-prose (realdec's prose prompt at
120,000 characters, 33,512 tokens, 600 out; `dfg_stats.py:5-6,68-73`) 2.77 at 0.621. Every production lane's sd-prose
reply on spark1 is `8347edfe4e` (DrafterFG's seven arms, MtpAB's eight), so the table's three texts are every
production text of this prompt with counters or records; the 2026-10-02/03 sdbench saves under `~/out/` hold two
more (`84aa7d627418`, `53a3fa4fdad8`) with neither.

Ours (`p1_texts.py`, first P1 row of each cell, 399 / rounds):
- one target-numerics change of the same prompt, same drafter and rule (the KDA pad, off to on): `v127` 2.678 ->
  `v127-pad` 2.790 (+0.112), `rs1-nopad-d4s` 2.696 -> `rs1-d4s` 2.771 (+0.075), `fix5` 2.678 -> `f5-pad` 2.752
  (+0.074; the first version of this report quoted 2.696 for `fix5`, which is `rs1-nopad-d4s`'s figure);
- the context prefix at one configuration: `v127` 2.678 (short), `v127-mid` 2.810 (about 3.6k tokens), `v127-long`
  2.891 (about 10.9k);
- left out: `f5-long` (3.000; its reply was written by the paired-step ring overrun, OVERNIGHT section 4),
  `k-kda_pad` (2.242; the pad broken through patch 0039, OVERNIGHT section 2), the `nd` cells (drafter off).

Text moves tokens a round by 0.05 to 0.19 in production at one drafter and rule (by rule and cut, section 4), and by
0.07 to 0.21 in ours. That is the size of (a). It is not enough on its own to place our 0.25 inside production's
spread: section 4.

## 4. (b) Drafter arithmetic and taps

At matched rules. Our rule at four product cuts on our text (`rs2-ctl`, `rs1-conf05/03/02`) against the same rule
replayed on production's records of its three texts (tokens a round / drafts a round / acceptance):

| cut | ours on `323d3f5bcb55` | production's drafter on `8347edfe4ee6` | on `7e1d5851c9eb` | on `1325539f6f53` |
|---:|---|---|---|---|
| 0.7 | 2.771 / 2.72 / 0.652 | 3.023 / 3.05 / 0.665 | 3.069 / 3.13 / 0.661 | 3.023 / 2.95 / 0.686 |
| 0.5 | 3.000 / 3.96 / 0.505 | 3.353 / 3.99 / 0.592 | 3.325 / 4.11 / 0.566 | 3.440 / 4.32 / 0.565 |
| 0.3 | 3.167 / 4.90 / 0.442 | 3.470 / 5.12 / 0.484 | 3.381 / 5.31 / 0.448 | 3.500 / 5.32 / 0.470 |
| 0.2 | 3.192 / 5.54 / 0.396 | 3.531 / 5.92 / 0.429 | 3.410 / 6.01 / 0.401 | 3.595 / 5.97 / 0.434 |

Production's three texts stay within 0.05-0.19 of each other at every cut. Ours sits 0.21-0.44 below all three. At
the 0.5 cut the draft counts are nearly equal (3.96 against 3.99-4.32 a round) and acceptance is 0.505 against
0.565-0.592. One text of ours against three of production's can't exclude a systematic text effect, such as the effort
line making replies harder to draft, which M-a measures. But a rule-independent deficit of this size, outside
production's own text spread, points at what our drafter sees or computes.

Where in the chain. The two logging cells (`cr-ctl-log`, `cr-prod-log`: our engine at one stream with
`TF_GLM_DFLASH2_LOG=600`, 2026-11-14, replies equal to each other) scored by `chain_log.py`, against production's
records scored the same way at the anchors each rule visits (`reach_prod.py`). Per request a round: kept drafts,
whole-chain correct drafts (L), reach at depths 1-7, and the correct drafts lost to a cut before the first miss:

| rule | drafter, text | kept | L | reach 1 / 2 / 3 / 4 / 5 / 6 / 7 | lost to the cut |
|---|---|---:|---:|---|---:|
| ours, `fc7:0.7@edge=1.0` | ours, `323d3f5bcb55` (140 rounds) | 1.807 | 2.207 | 0.771 / 0.536 / 0.350 / 0.257 / 0.143 / 0.086 / 0.064 | 0.400 |
| | production's, `8347edfe4ee6` | 2.008 | 2.565 | 0.809 / 0.611 / 0.420 / 0.305 / 0.198 / 0.122 / 0.099 | 0.557 |
| | production's, `7e1d5851c9eb` | 2.069 | 2.423 | 0.769 / 0.523 / 0.400 / 0.292 / 0.208 / 0.131 / 0.100 | 0.354 |
| | production's, `1325539f6f53` | 2.023 | 2.618 | 0.771 / 0.595 / 0.450 / 0.344 / 0.206 / 0.145 / 0.107 | 0.595 |
| production's, `nc7:0.3:2.0@edge=0.6` | ours, `323d3f5bcb55` (138 rounds) | 1.833 | 2.304 | 0.790 / 0.572 / 0.355 / 0.254 / 0.152 / 0.116 / 0.065 | 0.471 |
| | production's, `8347edfe4ee6` | 2.000 | 2.545 | 0.773 / 0.614 / 0.432 / 0.288 / 0.197 / 0.129 / 0.114 | 0.545 |
| | production's, `7e1d5851c9eb` | 2.117 | 2.453 | 0.781 / 0.531 / 0.391 / 0.297 / 0.219 / 0.141 / 0.094 | 0.336 |
| | production's, `1325539f6f53` | 2.143 | 2.595 | 0.794 / 0.619 / 0.452 / 0.317 / 0.198 / 0.127 / 0.087 | 0.452 |

The cut is not where it is lost: production's rule throws away as many correct drafts as ours or more. The drafter's
chain is. At depths 1 and 2 ours sits inside production's range over its three texts; from depth 3 on it is below
all three under both rules (depth 3: 0.350 / 0.355 against 0.391-0.452; depth 5: 0.143 / 0.152 against 0.197-0.219;
depth 7: 0.064 / 0.065 against 0.087-0.114), and the whole-chain count is 0.15-0.22 under production's lowest
text. Production's three texts carry two renderings (33 and 36 tokens) and two numerics arms and still stay
together; one text of ours cannot exclude a systematically harder text, which M-b's paired mode (one text, every
position, both drafters) does.

Same text, paired. The fork's chain log (`rep0diag/rounds.txt`) covers six requests that production's DraftPolicy
records also cover (dumps 0004-0009). The replies agree for 16, 16, 11, 76, 188 and 9 tokens. At the 45 anchors whose 7
drafts all fall in shared text (37 of them in the counting replies), the fork's whole-chain correct count is 5.58
against production's 6.04 at the fork's pick edge (6.07 at 0.6). The fork is shorter at 9 anchors and longer at 2.

At 7 of the 9, production's lattice puts the fork's pick 1.5-5.75 logits under the right token:
- `</arg_value>` for a newline four times (2.25-5.75);
- `...\n` for `4` twice (1.5, 2.75);
- ` [` for ` lst` (2.1).

One is a near tie (` was` against `.`, 0.75). At the last, counting from 14, the Zig chain reads `14 \n 14 \n 15 \n
16` against `14 \n 15 \n 16 \n 17`: depths 3, 5 and 7 each predict the token two places earlier. Production's drafter
puts `15` 17 logits above its runner-up there, and `14` is outside its top 16. Production's two misses are at 2.8 and
4.25 logits.

The failures don't cluster after a full-block keep (4 of 24 after `kept 8`, 5 of 21 otherwise). Rounding, merge order
and kernel order flip near-ties, under a logit; these are confident disagreements, the sign of a different input
(prompt or taps). The sample is small, mostly counting, and from the 2026-10-31 fork rather than our series.

Same code, read this round to test the shifted predictions above for a structural cause; none is one:
- block attention is bidirectional in both: the checkpoint's `config.json` says `"is_causal": false` (both
  snapshots on spark1, `bf582e4e` and `dc77ff1c`), production reads it (`P:dflash2.py:455`, `:248-249`;
  `P:dflash2_multi.py:77-78,300`), and ours lets every block row see all 8 block keys (`K:glm_dflash.cu:122-238`);
- the block is [anchor, mask x 7] at positions p..p+7, the mask rows the target's embedding of id 154856
  (`P:dflash2.py:680-699`; `Z:dflash.zig:332-340`, `Z:dflash_block.zig:138`; the incoai drafter ships no
  `mask_embedding.pt`, production's boot line `mask rows the target embedding`);
- each query row attends to its own last 2,048 positions (`P:dflash2.py:247,454`; `K:glm_dflash.cu:186-189`);
- the taps are the 4-stream mean of the residual after layers 5, 14, 24, 33 and 42 (`P:forward.py:151,1628-1631`;
  `Z:cuda_taps.zig:1-29`, `Z:cuda_forward.zig:430-433`), entering the context through fc and the hidden norm at
  their own positions (`P:dflash2.py:646-677`; `Z:dflash_block.zig:84-99`, `Z:dflash.zig:284-326`);
- the two-tap convolutions use the same base and dynamic layouts, the block's first row without a predecessor
  (`P:dflash2.py:139-165`; `K:glm_dflash.cu:97-109`);
- the context never restarts: every one-stream cell on spark1 logs `256 rounds, 0 contexts restarted`
  (`Z:dflash.zig:314-322,357`);
- every linear at 4 bits by the same quantizer (`Z:cuda_quant.zig:1,45-56` "same bits" as `qmm.quantize4`;
  `P:dflash2.py:293-297,476-508`), the 4-bit draft head from the target head's rows (`Z:cuda_mtp_load.zig:32`;
  `P:weights.py:496-501`), bf16 logits into the top 16 (`Z:dflash_block.zig:182-206`; `P:dflash2_multi.py:326-334`),
  DOWN4 and the MLP split with the rank-ordered fp32 sum (`Z:dflash_block.zig:113-133`; `P:dflash2.py:602-610`).

Different, unmeasured: production splits attention by KV groups 3/3/2 with fp32 o_proj partials (`P:dflash2.py:
437-441,623`), ours runs whole attention on every rank; Triton kernels against ours (attention in 16 key chunks plus a
merge, `Z:dflash_block.zig:159-169`, against 64-key tiles, `P:dflash2.py:215-258`); the convolution's weight
(base + dynamic) rounded to bf16 before the product in production (`P:dflash2.py:159-161`) and kept in fp32 in ours
(`K:glm_dflash.cu:104-105`); the selector projection rounded to bf16 in production (`F.linear(...).float()`,
`P:dflash2.py:709`, `P:dflash2_multi.py:337`) and fp32 in ours (`Z:dflash_block.zig:208`); candidates merged by
(value, id) in production (`P:dflash2.py:337-340`) and first-seen in ours (`Z:dflash_select.zig:25-41`); the target's
taps from different target numerics; and the prompt the drafter's context holds (section 2). Each of the arithmetic
differences moves a value by about one bf16 rounding; the confident disagreements above fit the last two better.

## 5. (c) The chain rule, both engines

Production serves `fnc7:0.3`: `~/mia110/scripts/config.sh:171-172` (`DRAFT_POLICY` defaults to it; neither
`v110ots.env` nor `local.sh` sets it), read by `P:engine.py:14-18`, encoded `[16, 7, 300000, 2000000]`
(`P:engine.py:421-439`; every record's meta carries exactly this), decoded to `DepthPolicy(7, fixed, confidence 0.3,
beta 2.0)` (`P:engine.py:442-458`, `P:decode.py:1152-1173`), under `--parallel` per stream (`MultiSettings.depth` =
`policy`, `P:multi_tune.py:38-66`; boot log `depth policy`; `P:multi.py:542-551,3577-3592`). The chain
(`P:dflash2.py:758-809`): score = logits + 0.6 x edge (`EDGE_DEFAULT`, `:25-61`, unset in production), confidence
softmax(score / 2.0) at the pick (`:64-80`), stop when the product falls under 0.3 past the first draft (`:792-799`),
up to 7 drafts, every one verified (no pricing; the boot's `drafter costs` table is read only by `fcost` policies,
`P:engine.py:459-470`).

Ours: score = value + 1.0 x edge (`Z:dflash_ovn.zig:46`, `Z:dflash_select.zig:60`), chance softmax(score / 1)
(`Z:dflash_load.zig:173-174,202`, `Z:dflash_select.zig:70-73`), zeroed past the first where the product falls under
0.7 (`Z:dflash.zig:42-45`, `Z:cuda_lanes.zig:530-539`), up to 7 (`Z:cuda_lanes.zig:16,532`), then the lane core
sizes the window by chained chances (`Z:cuda_lanes.zig:542-557`, `ZL:windows.zig:243-310`).

On the gap's own text (`sim_prose.py`; production's records of `8347edfe4ee6` are one lattice across ten requests and
two waves; `draft_sim.check`: `target_ok` 1.0, `prod_chain_ok` 1.0):

| rule on production's lattice | rounds | drafted | accepted | tokens a round | acceptance | tok/s, our cost table |
|---|---:|---:|---:|---:|---:|---:|
| production's, `nc7:0.3:2.0@edge=0.6` (live: 133 / 388 / 266) | 133 | 388 | 267 | 3.000 | 0.688 | 76.69 |
| ours, `fc7:0.7@edge=1.0` | 132 | 403 | 268 | 3.023 | 0.665 | 76.06 |
| our cut at production's edge, `fc7:0.7@edge=0.6` | 132 | 388 | 268 | 3.023 | 0.691 | - |
| production's cut at our edge, `nc7:0.3:2.0@edge=1.0` | 131 | 402 | 269 | 3.046 | 0.669 | - |
| production lane's refit, `nc7:0.3:2.0@edge=0.2` | 138 | 365 | 262 | 2.891 | 0.718 | 76.36 |
| every draft verified, `f7` | 111 | 770 | 289 | 3.595 | 0.375 | - |
| hindsight bound, `oracle7` | 105 | 294 | 294 | 3.800 | 1.000 | - |

Production's rule over ours, tok/s on our cost table: +0.83% here, +2.09% and +2.82% on production's two other
texts. The refit at edge 0.2: +0.39%, +2.44%, -0.56%. Production's drafter reaches 0.827 / 0.649 / 0.481 / 0.343 /
0.231 / 0.160 / 0.110 at depths 1-7 on this text at edge 1.0 (whole-chain correct 2.802 a position), 0.822 / 0.657 /
0.479 / 0.341 / 0.243 / 0.170 / 0.118 at 0.6 (2.830), and nearly the same on its other two texts (0.837 and 0.840 at
depth 1).

Step prices against our static table: with a drafter loaded `facts()` drops load-time prices (`Z:cuda_lanes.zig:100`;
boot line `DFlash2 keeps its seed window and step prices`); `window_costs` 52 + 6.8 ms a row is overwritten by
`shared_costs` 76 + 4.1 ms a row at every width (`Z:cuda_copy_policy.zig:5-13`, `ZL:config.zig:129-147`; both 32 wide),
and a lone round prices on that table (`lone_costs.enabled` needs `lone_cost_tile`, unset: `ZL:lone_costs.zig:15-18`,
`ZL:windows.zig:275-285`) with an overhead learned as max(0, round - table) = 0 (`ZL:depth.zig:370-379,404-416`;
8 ms before the first round) and no row term at one stream (`ZL:row_cost.zig:139-155`). A draft of reach c is then
added while c > E x 4.1 / (76 + 4.1 (r - 1)): at most 0.054 for the first and 0.285 at the eighth row even with every
earlier draft certain, so every draft either cut keeps (chained 0.7, or 0.3 on beta-2 chances) passes: the table does
not bind at one stream (or at two: 0.10-0.24 typical). The cut sweep agrees: lowering the cut raised drafts
monotonically to 5.54 a round (`rs1-conf05/03/02`). The table is stale (it prices a row at 5% of a round, the box at
12%: 4.6 ms of 38.2), a latent defect for any rule that lets low-reach drafts through, not a factor in this gap.
`TF_GLM_DFLASH2_WIN` is 2,048 like production's window; `--mtp-confidence` does not apply with a DFlash2 drafter
(`Z:cuda_lanes.zig:115`). `TF_GLM_OVN_DRAFT_FIXED` (verify every draft the cut keeps) was left out of the series
(`patches/engine/0017-plain-margin.patch:10-12`) and is not needed here: at one to three streams it would change
nothing.

The rule elsewhere (`sim_rules.py`, production's 24 agent turns, tokens a round): ours 3.425; edge 0.6 alone 3.461;
beta 2 and cut 0.3 alone 3.470; both (production) 3.470 (+1.3% [-0.2, +2.9]); tok/s on our cost table 83.01 / 83.96 /
83.84 / 84.82 (+2.2% for production's). The fork's pieces over its 11 prompts (`p1multi-fixparts.jsonl`): cut 0.3 on
raw chances 4.92 drafts a round at acceptance 0.584 (-5.2% tok/s), beta 2 at the 0.7 cut 2.49 drafts at 0.849
(-2.7%), together 3.43 drafts at 0.761 (+1.9% tokens a round, +0.74% tok/s, prose +2.3%); its live same-text A/B on
prose `2553ee660f86`: 162 -> 157 rounds, 2.648 -> 2.732 (`fixed2.jsonl`).

## 6. (d) What counts as accepted

Production: keep = 1 + drafts while the row's sample equals the draft and is not an end token
(`P:multi.py:3632-3638`); `Stream.counted` adds rows - 1 to drafted and one round, `Stream.take` adds the kept drafts
the reply takes (`tensorfold/cuda/streams.py:48-68`). Ours: the path of rows whose parent's pick equals the draft
(`ZL:accept.zig:40-57`), drafted += rows - 1, accepted += path - 1, one round (`ZL:engine.zig:343-348,418`). Ours counts
before the end-of-reply cut (`:424-427`), production after it: in `rs2-ctl` that is zero (144 + 255 = 399); in `fix5`
it is one draft (149 + 251 = 400), as in draft_sim's replay of production (267 against the live 266). Same greedy
rule, same counters, rounds unaffected.

## 7. The lever

No (c) or (d) lever closes the tokens-a-round gap: on the two texts of the gap the rule is worth -0.023 to +0.039.
At least 0.19 is (a) + (b), and M-b (section 8) splits it. If M-b gives (b) its expected share, the next lever is in
what our drafter sees: the prompt in its context (M-a) and the target's taps, then the arithmetic differences of
section 4.

The lever for tok/s is production's chain rule, and it needs no code. The rule is in the series as knobs
(`TF_GLM_OVN_DRAFT_EDGE`, `_BETA`, `_CUTS`, `_NOISE`: `Z:dflash_ovn.zig:41-65`,
`zig/src/platform/environment.zig:83-86`), and the ABBA of `arms-chainrule.txt` (spark1, 2026-11-14 03:02-03:46,
`glm53-zig:rs2`, cells copied to `cells/cr-*`, scored by `cr_ab.py`) measured it at every stream count. Decode
tok/s, the mean of three request rounds a cell; every reply equal to `cr-ctl`'s at every level:

| streams | ours (ctl / ctl-b) | production's rule (prod / prod-b) | ABBA | rounds | drafted | acceptance | tokens a round |
|---:|---|---|---:|---|---|---|---|
| 1 | 69.95 / 69.84 | 72.43 / 70.78 | +2.45% | 144 -> 142 | 391 -> 383 | 0.652 -> 0.671 | 2.771 -> 2.810 |
| 2 | 77.44 / 77.52 | 80.95 / 79.31 | +3.42% | 354 -> 346 | 697 -> 673 | 0.637 -> 0.672 | 2.254 -> 2.306 |
| 4 | 100.20 / 98.10 | 102.46 / 100.21 | +2.20% | 705 -> 695 | 1395 -> 1318 | 0.639 -> 0.684 | 2.264 -> 2.296 |
| 6 | 135.85 / 131.92 | 137.95 / 134.41 | +1.72% | 1067 -> 1094 | 2046 -> 1788 | 0.649 -> 0.728 | 2.244 -> 2.188 |
| 8 | 165.58 / 161.79 | 168.74 / 164.13 | +1.68% | 1426 -> 1518 | 2690 -> 2194 | 0.657 -> 0.764 | 2.238 -> 2.103 |

At 6 and 8 streams the rule keeps fewer tokens a round but drafts so much less that each round is cheaper, so it
still wins; the fork's 4-8 stream loss (`ai-engine docs/SPEEDUPS.md:136,146,169`) does not reproduce on the series.
The B half drifts from its A half by +0.1% to -2.9%. At one stream the drift is uneven (prod-b 2.27% below prod,
ctl-b 0.17% below ctl), so the one-stream gain lies between +1.35% (the B pair) and +3.55% (the A pair).

The working copy of `scripts/serve.sh` (modified 2026-11-14 04:09, uncommitted, not by this lane) already adds the
first three of the knobs below to `DEFS`, with a comment pointing at OVERNIGHT section 22; `NOISE` is the one it
lacks.

The change is the serve's default knob list, `DEFS` in `scripts/serve.sh:67-69` (the seven-knob arm): add
`TF_GLM_OVN_DRAFT_EDGE=0.6 TF_GLM_OVN_DRAFT_BETA=2 TF_GLM_OVN_DRAFT_CUTS=1:0.3 TF_GLM_OVN_DRAFT_NOISE=0.7`, and update
the comment at `:70-71` with these measurements. `knob-arms.sh` reads the same list, so its one-at-a-time arms pick
the four up. Expected on greedy streams: decode tok/s +1.7% to +3.4% by stream count (the ABBA above; NOISE never
acts on a greedy stream), with replies unchanged (selection runs on rank 0 and the verify keeps the target's own
sample). The stream-count gate designed in this report's first version (`TF_GLM_OVN_DRAFT_RULE_MAX`) is not needed and
is withdrawn.

NOISE on sampled streams, which the greedy bench cannot see. Our selector reads the target's keyed Gumbel draw only
on a sampled stream and only with NOISE above 0 (`0007-draft-knobs.patch`: `keyed = if (k.noise > 0) q.sampling`,
the pick `score / T + NOISE g`, the chance `softmax((score / T + g) / beta)`; the draw is the target's own,
`ovn.gumbel` against sample.cu's `raceUniform`). Production left 120 sampled agent-turn records (temperature 1.0,
top-p 0.95, top-k 20, seed 7; `~/perpatch/dumps-20261101-{071059,104407}`, copied to `proddumps/`; production's chain
and the target's keyed resampling reproduce in all 120, the keyed draws to 8.9e-16). Replayed by `sim_noise.py` on
our cost table, 19,649 positions, paired 95% intervals over the turns:

| rule on sampled turns | tokens a round | drafts a round | acceptance | tok/s, our table | against the row above |
|---|---:|---:|---:|---:|---|
| today (`fc7:0.7@edge=1.0`, no draw) | 3.010 | 3.023 | 0.665 | 76.01 | - |
| the measured change, NOISE 0 (beta-2 chances without the draw) | 3.059 | 2.989 | 0.689 | 77.55 | +2.03% [+1.55, +2.51] |
| with NOISE 0.7 (production's served rule) | 3.140 | 2.972 | 0.720 | 79.76 | +2.85% [+2.15, +3.55] |
| with NOISE 1.0 | 3.140 | 2.993 | 0.715 | 79.57 | -0.24% [-0.57, +0.12] |

With NOISE 0.7 the whole change is +4.94% [+4.20, +5.66] tok/s over today on sampled turns, by replay on production's
drafter; 1.0 buys nothing more. "NOISE 0" is a rule draft_sim lacks: `sim_noise.BetaProduct`, which
`test_sim_noise.py` proves equal to draft_sim's own rule on greedy records at every position and different on sampled
ones. The live check is the sampled ABBA of section 8. The
production lane's refit, EDGE 0.2, does not beat 0.6 on production's prose records (mean +0.76% against +1.91%). Live
on our engine (`cr-e2`, one cell run after the ABBA, every reply equal), over the control mean at 1, 2, 4, 6 and 8
streams, it measured +2.92%, +3.29%, +1.83%, +1.05% and +1.08%; over production's rule, +0.46%, -0.13%, -0.37%,
-0.65% and -0.60% (one stream: 144 rounds, 353 drafted, acceptance 0.722). That is a tie at one and two streams and a
small loss from four on, inside the run's 2% drift, so 0.6, production's own setting, stays the choice.

## 8. Measurements

- M-b, the same-text split, with no production run and no engine change; the decisive one. Production's reply text
  exists: sdbench saved it on spark1 (`~/prof/drafterfg/sd-incA/prose.txt` and three more runs, all sha256
  `8347edfe4ee6`, md5 `6e1052ab9a` as DrafterFG records; copied to `prodreply/`). It tokenizes to 400 ids,
  production's completion count, decodes back to the same bytes, and equals the tokens of production's ten records
  (`forced.json`, with the 33-token prompt). `forced-arm.sh` boots one stream with `--prompt-cache-gib 0` (a resumed
  request would restart the drafter's context) and `TF_GLM_DFLASH2_LOG`, and `teacher_forced.py` sends production's
  prompt plus the reply's first p tokens for every p as ids. Each request's first round drafts from production's text
  and prompt, so the prompt difference is gone: `forced_score.py` reads per position our target's token (does it follow
  production's?), our drafter's 7 picks (L, how many equal production's next tokens) and the kept rows of the next round
  (K, what our rule kept), and replays the rounds over the 400 tokens. With `--prod` it pairs every position with
  production's own chain on the same text from its record, prints the reach of both drafters by depth, and replays the
  arm's rule on production's lattice. Arms:
  - `tf-ctl`: `XENV="<cr-ctl's list> -e TF_GLM_DFLASH2_LOG=100000" KNOBS=off bash forced-arm.sh glm53-zig:rs2 tf-ctl`,
    scored with `python forced_score.py forced.json records.jsonl rounds.log cache.log --prod
    proddumps/dumps-20261102-103755/dump-20261102-102524-1-0017.npz --edge 1.0`. Our rule's rounds with our drafter
    against 132 with production's give (b) = 3.023 - ctl@prod and (a) = ctl@prod - 2.771; the paired reach against
    production's 0.827 / 0.649 / 0.481 / 0.343 / 0.231 / 0.160 / 0.110 says at which depths.
  - `tf-prod`: cr-prod's list, scored with `--edge 0.6 --rule nc7:0.3:2.0@edge=0.6` (against 133 rounds, reach 0.822 /
    0.657 / 0.479 / 0.341 / 0.243 / 0.170 / 0.118).
  `test_forced_score.py` proves the scorer on runs synthesized from production's dumps: its rounds equal draft_sim's
  own replay for both rules (88/86 and 70/68) and for f7, only the last position flagged; a position where our target
  leaves the text is flagged with the rounds that meet it; paired with its own lattice a run reads 0 shorter, 0
  longer and equal rounds, and with third drafts corrupted at every seventh request, shorter at 45 and 22 and never
  longer. Caveat: a forced position's context taps come from the prompt pass, a live round's from verify windows, as
  in production's records.
- Every tool of this lane is proven the same way: `mutants_forced.py` runs the six tests unmutated in a scratch copy
  (`test_forced_score.py`, `test_chain_log.py`, `test_sim_noise.py`, `test_streams_sampled.py`,
  `test_bench_client.sh`, `test_arms_noise.sh`; the shell tests in WSL bash), then sixteen mutants, each anchored
  once, all killed by exit code: K from the wrong line, L one position early, one round too many, exactness ignoring
  G, the paired walk ignoring the edge, shorter and longer swapped, production's chain scored one position early, a
  cut-off log head raising again, `BetaProduct` keeping the draw or ignoring beta, the sampling fields never set or
  the seed left out, the client's options dropped or the default client changed, A2 running B's settings, and NOISE
  at 1.0.
- M-a, the prompt: `bench-client.sh` (bench-arm.sh's boot loop, its default client) runs `streams_ids.py`,
  streams.py's own accounting with the prompt sent as ids to `/v1/completions`
  (`zig/src/server/completion_prompt_test.zig`: ids served as given), from
  `prose33.json`: the four prose prompts in production's thinking-off rendering (`make_ids.py`: 33/23/22/36 tokens
  against our 40/30/29/43, the fork's cells record exactly our four counts). `test_streams_ids.py` runs it against a
  local stand-in server (prompt as the file's ids, digest, tokens, counter deltas and ratios); two mutants (reading
  `delta.content`, sending the prompt as text) are killed. In the window, beside zig-tp3.sh on the head:
  `XENV="<cr-ctl's list>" KNOBS=off bash bench-client.sh glm53-zig:rs2 ids-ctl`. Its tokens a round against 2.771 is the
  prompt's share of (a); a reply digest equal to `8347edfe4ee6` makes the comparison same-text.
- The lever: `arms-chainrule.txt` on `glm53-zig:rs2`. The ABBA (ctl, prod, prod-b, ctl-b at 1/2/4/6/8) ran on
  2026-11-14 from 03:02 to 03:46 and is scored in section 7 (`python cr_ab.py`): production's rule wins at every
  level with every reply equal, so the gate is not needed. `cr-e2` (boots 03:46 to 03:58) is scored beside the ABBA
  by the same `cr_ab.py` (section 7). The two `TF_GLM_DFLASH2_LOG=600` cells booted at 04:01 and 04:03; production's
  serve was back up at 04:06, so no M-a or M-b cell ran in that window.
- NOISE, live: `arms-noise.sh` runs the sampled ABBA through `bench-client.sh` with `streams_sampled.py`
  (streams.py's measurement with every chat request at temperature 1.0, top-p 0.95, top-k 20 and seed 7, which our
  server takes per request, `ZS:benchmark_stream.zig:56-67`; the keyed sampler then gives one reply a prompt in every
  arm): A = cr-prod's list, B = A plus `-e TF_GLM_OVN_DRAFT_NOISE=0.7`, in the order A, B, B2, A2 at 1 2 4 6 8
  streams, then cr-ctl's list as an extra cell. On the head: `scp arms-noise.sh bench-client.sh streams_sampled.py`
  to `~/work/glm53-zig/`, `bash ~/work/glm53-zig/arms-noise.sh glm53-zig:rs2`; scored by `python cr_ab.py --arms
  sm-lever,sm-noise,sm-noise-b,sm-lever-b --extra sm-ctl`. Expected from the replay (section 7): B over A about +2.9%,
  the whole change over today about +4.9%, on sampled agent turns.
- From the two log cells: `python chain_log.py <cr-ctl-log r0-P1.log> <cr-prod-log r0-P1.log>` rebuilds each request's
  reply from the `dflash2 round` lines (anchor at `pos`, the next round's `kept` = 1 + the drafts kept,
  `Z:cuda_engine.zig:480-484`, `Z:dflash.zig:337-340,356`), scores every round's whole 7-draft chain against it (L)
  beside what the round kept (K), checks the two arms' replies agree, and prints the reach by depth: picks (edge) and
  stops (beta, cut) apart on one text. `test_chain_log.py` proves it on logs synthesized from production's dumps by
  `draft_sim`: replies rebuilt token for token, every round's L and K equal to the replayer's, a warm-up request split
  off; two mutants (the reply taking N drafts, K off by one) are killed by its assertions. A log whose head
  bench-arm.sh's 800-line tail cut off is read from the first request start on, the skipped rounds counted on stderr
  (tested on a log missing its first three rounds; the mutant that raises instead is killed).
  Its per-request lines set beside `python reach_prod.py`, which scores production's drafter on its three texts the
  same way at the anchors each rule visits, compare the two drafters at one rule on their own texts (text and drafter
  together; M-b removes the text). Run on the two logging cells (complete from round 0: 440 and 435 round lines, the
  three measured requests identical, the replies of the two arms equal over 398 tokens): section 4's table.
