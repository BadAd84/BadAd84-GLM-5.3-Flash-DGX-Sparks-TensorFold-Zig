# Would TF_CACHE_EVICT=decayed_resume pay at our 7.85 GiB prompt cache?

Lane: `CacheEvictReplayLane`. Upstream pin `46c6ee229d2ea28bde8b273381c0f0443861cdd6` of `ashhart/TensorFold`
(clone at `work/up/TensorFold`). Gate host `<user>@<gate-host>` (x86_64, 16 cpus, zig 0.17.0), CPU only,
`nice 15`, `memory.max` 8 GiB. No Spark was touched, nothing was compiled on the workstation, and no tracked file
in this repo changed.

Every number below is printed by the sweep described in section 1 or computed from its JSON lines by
`report_tables.py` (appendix B); no figure is hand-fitted.

## 1. What was run

The simulator is upstream's own `zig/cache_agent_replay.zig`. It takes no arguments: its traces are fixed at 6
conversations, 48 rounds and an 8,192-token shared prefix, and `zig:STEP` cannot carry arguments through
`scripts/spark-gates.py`. A patch under `work/cache-replay-lane/` (appendix A) therefore does three things, none of
them touching a device backend or the engine's production files:

- `zig/cache_replay_model.zig`: `Model` gains `recurrent`, `per_token`, `eighths` and `align_bytes` fields, all
  defaulted so the replay's own sizes and its equivalence tests are unchanged.
- `zig/cache_agent_trace.zig`: the shared-system trace takes `Params` (conversations, rounds, prefix, base,
  stride, growth, one-offs, one-off sizes). `make` and `makeSeeded` keep the old defaults and therefore the old
  requests and digests.
- `zig/cache_agent_sweep.zig` plus one build step: a table of parameter sets, each run through the real store for
  both policies and printed as JSON lines.

Commands (top-level Windows shell, one run at a time):

```
SPARK_GATES_HOST=<user>@<gate-host> \
SPARK_GATES_SSH_SOCK=<agent socket> \
python scripts/spark-gates.py iter --name cacheev \
  --pin 46c6ee229d2ea28bde8b273381c0f0443861cdd6 --pin-repo work/up/TensorFold \
  --dir work/cache-replay-lane --max-load 90 --mem-max 8 --jobs 4 \
  zig:cache-agent-replay zig:cache-agent-sweep
```

Recorded output of the run the tables come from:

```
PREFLIGHT <gate-host> x86_64, 16 cpus: load 0.34, 28 GiB memory available, 77 GiB disk free
tree id 411264f6cae82d528572031780f8927ac9c3ff4b (1 patches applied)
== zig build cache-agent-replay
Build Summary: 3/3 steps succeeded
zig:cache-agent-replay rc=0 in 3 s
== zig build cache-agent-sweep
Build Summary: 3/3 steps succeeded
zig:cache-agent-sweep rc=0 in 49 s
ITER-DONE rc=0
```

The first two attempts failed to compile (`cache_replay_model.zig:10: error: expected type expression, found
'align'`, then the same field name in the sweep's literals): `align` is a Zig keyword, so the field is
`align_bytes`. Nothing else changed between those attempts and the recorded run.

The logs were then read off the host with `scp <user>@<gate-host>...:~/spark-gates/iter-cacheev/zig-cache-agent-*.log`,
and `python report_tables.py` turned them into the tables in sections 4 and 6. The replay's own output
(`zig-cache-agent-replay.log`, 24 JSON lines) is kept as the fidelity check in section 4.

## 2. A. What the simulator models

**Capacity is bytes, and a state's size is an affine function of its token count.** `Model.bytes`
(`zig/cache_replay_model.zig:6-11`) is `alignForward(raw + raw/8, 32 MiB)` with
`raw = recurrent_bytes + kv_bytes_per_token * at`, where `recurrent_bytes = 153,944,064` (an 18.8% share of an
8,192-row state) and `kv_bytes_per_token = 65,536`. One state is 768 MiB at 8,192 rows, 3,168 MiB at 42,512 rows
and 8,608 MiB at 120,000 rows. The budget is the store's `budget` in bytes; the 1/8 margin and the 32 MiB
rounding are the replay's own modelling choices, not the real family's.

**The trace is fixed synthetic agent traffic.** `zig/cache_agent_trace.zig` (`rounds = 48` at :5, budgets
`{4, 8, 16} GiB` at :6) builds, per round and per conversation, one `agent` request whose prompt is a shared
system prefix (`shared = 8,192` tokens) followed by a history of `16,384 + (session % 3) * 1,024 + turn * 512`
tokens plus 16 trailing tokens, and then two `one_off` prompts of 1,024, 4,096, 8,192 or 12,000 unique tokens.
`agent_cohorts` replaces every conversation at the halfway round. These are the same shapes the served client
`tools/bench_cache_agents.py` drives (`--conversations 6 --rounds 48 --prefix-tokens 8192 --tokens 16` are its
defaults), and the served client's own growth is one sixteenth of the prefix a turn (512 tokens here).

**The store is the production store.** `Replay.init` (`zig/cache_replay_run.zig:13-17`) builds
`pc.Store.init(a, family.snapshots(), .{ .chunk = 1 }, budget)` from `zig/src/core/prompt_cache.zig` and sets
`eviction = .main`; `request` (:22) does the real lookup, `marks`, admission and `keep`, and then the replay's
own accounting checks (byte accounting, borrower leaks, state equality). The family only copies a small `State`
per keep, so the trace is priced in bytes and no device is involved.

**`main` is the native order; `decayed_resume` is a frozen selector over it.** `policy.victim`
(`zig/cache_replay_policy.zig:5`) returns `s.victimMain(...)` for `main`. For `decayed_resume`
(`zig/cache_replay_decay.zig:29`) it starts from the native `victimBut` choice, returns it immediately when that
entry is redundant, and otherwise picks the entry with the largest
`age = (clock -| used) -| 8 * min(seen.hits, 2)`, preferring entries that are not the active rewind, and never
touching a borrowed entry, the skipped one or one a reservation guard protects. The replay's `request`
(`zig/cache_replay_run.zig:27-31`) carries the resumed entry's hit count (capped at 2) onto the states kept at or
after the resume point, which is what gives a resumed conversation its up-to-16-tick credit. The shipped policy
(`zig/src/core/prompt_cache_decay.zig`, `resumed` and `kept`) does the same on the real entry and its successors.

**It prints one JSON line per (trace, policy, budget)**: `requests`, `hits`, `prompt_rows`, `rebuilt_rows`,
`evictions`, `peak_bytes` (`zig/cache_agent_replay.zig:20`). `rebuilt_rows` is the sum of
`prompt length - resume point` over the trace, i.e. the rows that would be prefilled.

## 3. B. Our cache mapped onto it

Our deployed shape (queue91's facts row `work/pp91/f91-c/mn1-facts.out`, image `glm53-zig:m130a`):
`prompt_cache_budget_bytes = 8,426,464,256` (7.8478 GiB) and `prompt_cache_minimum_state_bytes = 176,160,768`
(168.0 MiB exactly). The facts rows never report a kept state (`prompt_cache_states = 0` in all 236 rows under
`work/` that carry the metric), so the per-state byte sizes come from the same boot's probe rows instead, whose
`cache` block gives `held_mib` and `states` after each request (`work/pp91/f91-c/mn1-probe.out`):

| prompt tokens | states after | held after | bytes added by this request |
| --- | --- | --- | --- |
| 8,005 | 1 | 202 MiB | 202 MiB |
| 32,014 | 2 | 554 MiB | 352 MiB |
| 120,388 | 3 | 1,442 MiB | 888 MiB |
| 7,999 (repeat) | 4 | 1,644 MiB | 202 MiB |
| 32,001 (kept 2) | 6 | 2,336 MiB | 692 MiB for two states |
| 120,526 (kept 2) | 8 | 4,100 MiB | 1,764 MiB for two states |

Two fits follow, both with 2 MiB pages (`zig/src/core/state_walk.zig:6`), which is the family's admission
rounding (`cuda_snapshot_pages.zig:8-10`, `cuda_snapshot_layout.zig` `Plan.size`):

- **measured**: `fixed = 162,843,852 B (155.3 MiB)`, `per_row = 6,378 B`. It reproduces 204 / 352 / 888 MiB for
  7,999 / 32,014 / 120,388 rows against the measured 202 / 352 / 888 (one page high at 8k) and the reported
  minimum exactly (168.0 MiB at the first legal mark, 2,048 rows: `snap_grid = prompt_rows = prefill_rows = 2048`,
  `zig/src/families/glm/cuda_native.zig:28-30,406`). The same 202 / 352 / 888 numbers appear on the image's other
  boots (mn1, mn2, md1, md2, mz1, mo3), so this is the deployed stack's size, not one boot's.
- **layout**: the source's own page math. `pageCacheBytes` is `page_rows * kv_lora * 2 + page_rows / pool *
  i_dim * 2 = 512 * (1,024 + 64)` (`zig/src/families/glm/cuda_state.zig:66-84`, "13,056 a row on
  GLM-5.3-Flash"), but a served snapshot prices fp8 latent rows at `512 + 4` and the pooled keys at 64, i.e. 580
  a row a cache (`cuda_snapshot_layout.zig` `rows`), and the boot line says the serve runs fp8 caches ("4 streams
  at once, 7.00 GiB each at a 1048576-token window (fp8 caches)"). For 12 caches that is **6,960 B a row**; with
  `fixed = 163,997,286 B (156.4 MiB)` it reproduces 210 / 370 / 956 against the stock-main image's measured 208 /
  372 / 956 (two pages off at 32k) and its 170 MiB minimum. The bf16 number, 13,056 B a row, is 2.05 times the
  measured slope and does not apply to a deployed snapshot.

The two per-row estimates are 6,378 and 6,947 B, **8.9% apart**, which is one cache's 580-B row share (11 against
12 caches). The stock-main image `glm53-zig:m130base` (unit `mps`, and the same three state sizes again on u129,
u130, ud and ui in `work/pp92-partial/f92-c/`) fits 6,947 to 6,994 B a row depending on whether the reported
170 MiB minimum is held as a constraint, within 0.2 to 0.7% of the layout number. So the layout math is validated
on the unpatched stack, and the deployed patched stack keeps **one fewer cache's rows per state** (an inference:
the two images differ by our patch stack). A third model, the midpoint (6,662 B a row,
`fixed = 163,420,569`), is carried through the sweep to show the sensitivity.

**Capacity in the simulator's unit is a range, not a point.** Converting at a reference length means: how many
states of that length our budget holds under the measured model, times the replay's bytes for one such state.
Consecutive rungs of that conversion differ by up to 2x, so the answer depends entirely on the state length the
question is asked about:

#### Our capacity for a state of a given length, and the same capacity in the replay's unit
| rows | our state, measured model | our state, layout model | our states held | replay state | converted capacity |
| --- | --- | --- | --- | --- | --- |
| 2048 | 168.0 MiB | 170.0 MiB | 47 | 320.0 MiB | 14.69 GiB |
| 8192 | 206.0 MiB | 212.0 MiB | 39 | 768.0 MiB | 29.25 GiB |
| 16384 | 256.0 MiB | 266.0 MiB | 31 | 1344.0 MiB | 40.69 GiB |
| 32768 | 356.0 MiB | 374.0 MiB | 22 | 2496.0 MiB | 53.62 GiB |
| 42512 | 414.0 MiB | 440.0 MiB | 19 | 3168.0 MiB | 58.78 GiB |
| 120000 | 886.0 MiB | 952.0 MiB | 9 | 8608.0 MiB | 75.66 GiB |


The extremes are the 8,192-row state (39 of ours, 29.25 GiB in the replay's unit) and the 120,000-row state (9 of
ours, 75.66 GiB). At the lengths the default trace actually uses, our budget is worth 40.69 GiB (16,384-row state)
to 58.78 GiB (42,512-row state); for the 32,768-prefix trace's last state (169,984 rows) it is 71.05 GiB. That
spread is why the same budget can look tight or slack depending only on context length.

**The policy only has work to do when the live conversation working set approaches the budget.** At the measured
model, six conversations at the default 8k prefix hold 6 x 414 MiB = 2.43 GiB (30.9% of the budget); twelve hold
4.85 GiB (61.8%); six at a 32k prefix hold 6 x 1,190 MiB = 6.97 GiB (88.8%); three hold 1.21 GiB (15.5%). The
sweep's results track that ratio almost exactly (section 4).

## 4. C. The runs

### Reproduction of upstream's quoted figure

Upstream's message for `decayed_resume` (commit `6eeb7c3aa`) quotes "at 16 GiB agent loops rebuild 28-34% fewer
prompt rows and agent cohorts 24-30% fewer ... no cell worse on seeds 7, 11 and 23". Our sweep at the replay's own
model and 16 GiB reproduces it:

**Seed by seed, the replay's own model, 16 GiB.**
| trace | seed | rebuilt rows main | rebuilt rows decayed_resume | fewer |
| --- | --- | --- | --- | --- |
| agent_cohorts | 7 | 7782880 | 5486560 | 29.5% |
| agent_cohorts | 11 | 7858816 | 5943936 | 24.4% |
| agent_cohorts | 23 | 7838528 | 5693760 | 27.4% |
| agent_loops | 7 | 9600992 | 6357472 | 33.8% |
| agent_loops | 11 | 9646720 | 6320768 | 34.5% |
| agent_loops | 23 | 9651520 | 6902592 | 28.5% |


That is 28.5 to 34.5% for `agent_loops` and 24.4 to 29.5% for `agent_cohorts`; one seed's 34.5% is half a point
above the rounded window, the rest are inside it. At 4 GiB the sweep gives 4.0% (`agent_loops`) and 8.0%
(`agent_cohorts`), inside upstream's quoted 4 to 18%; at 8 GiB both traces give 0.0% (not quoted upstream). No
cell in the whole sweep rebuilt more rows under `decayed_resume` than under `main` (214 cells, 0 worse).

### Fidelity of the parameterised trace

The sweep's `replay-4gib`, `replay-8gib` and `replay-16gib` cells rebuild exactly what the unmodified
`zig build cache-agent-replay` prints for the same trace, policy and budget, digests included:
**12 of 12 cells compared, 0 mismatches** (`report_tables.py` checks `rebuilt_rows`, `prompt_rows`, `hits`,
`evictions`, `requests` and `digest`). The parametrised generator therefore produces the same requests and the
same digests at its defaults.

### The replay's own model at capacities converted from our budget

Seed 7, both traces. `reference rows` names the state length the conversion used; every rung is a capacity at
which our budget holds the same number of *such* states in our cache as the replay's model holds in its own bytes.

**Seed 7, both traces.**
| set | trace | reference rows | converted capacity | rows main | rows decayed | fewer |
| --- | --- | --- | --- | --- | --- | --- |
| conversations-12 | agent_cohorts | 120000 | 75.66 GiB | 7686656 | 7686656 | 0.0% |
| conversations-12 | agent_cohorts | 16384 | 40.69 GiB | 8807936 | 7686656 | 12.7% |
| conversations-12 | agent_cohorts | 32768 | 53.62 GiB | 7686656 | 7686656 | 0.0% |
| conversations-12 | agent_cohorts | 42512 | 58.78 GiB | 7686656 | 7686656 | 0.0% |
| conversations-12 | agent_cohorts | 8192 | 29.25 GiB | 15882752 | 15882752 | 0.0% |
| conversations-12 | agent_loops | 120000 | 75.66 GiB | 7574016 | 7574016 | 0.0% |
| conversations-12 | agent_loops | 16384 | 40.69 GiB | 16054784 | 11552768 | 28.0% |
| conversations-12 | agent_loops | 32768 | 53.62 GiB | 7680512 | 7574016 | 1.4% |
| conversations-12 | agent_loops | 42512 | 58.78 GiB | 7574016 | 7574016 | 0.0% |
| conversations-12 | agent_loops | 8192 | 29.25 GiB | 19413504 | 19413504 | 0.0% |
| conversations-3 | agent_cohorts | 120000 | 75.66 GiB | 1910976 | 1910976 | 0.0% |
| conversations-3 | agent_cohorts | 16384 | 40.69 GiB | 1910976 | 1910976 | 0.0% |
| conversations-3 | agent_cohorts | 32768 | 53.62 GiB | 1910976 | 1910976 | 0.0% |
| conversations-3 | agent_cohorts | 42512 | 58.78 GiB | 1910976 | 1910976 | 0.0% |
| conversations-3 | agent_cohorts | 8192 | 29.25 GiB | 1910976 | 1910976 | 0.0% |
| conversations-3 | agent_loops | 120000 | 75.66 GiB | 1876672 | 1876672 | 0.0% |
| conversations-3 | agent_loops | 16384 | 40.69 GiB | 1876672 | 1876672 | 0.0% |
| conversations-3 | agent_loops | 32768 | 53.62 GiB | 1876672 | 1876672 | 0.0% |
| conversations-3 | agent_loops | 42512 | 58.78 GiB | 1876672 | 1876672 | 0.0% |
| conversations-3 | agent_loops | 8192 | 29.25 GiB | 1876672 | 1876672 | 0.0% |
| default | agent_cohorts | 120000 | 75.66 GiB | 3846112 | 3846112 | 0.0% |
| default | agent_cohorts | 16384 | 40.69 GiB | 3846112 | 3846112 | 0.0% |
| default | agent_cohorts | 32768 | 53.62 GiB | 3846112 | 3846112 | 0.0% |
| default | agent_cohorts | 42512 | 58.78 GiB | 3846112 | 3846112 | 0.0% |
| default | agent_cohorts | 8192 | 29.25 GiB | 3846112 | 3846112 | 0.0% |
| default | agent_loops | 120000 | 75.66 GiB | 3785696 | 3785696 | 0.0% |
| default | agent_loops | 16384 | 40.69 GiB | 3785696 | 3785696 | 0.0% |
| default | agent_loops | 32768 | 53.62 GiB | 3785696 | 3785696 | 0.0% |
| default | agent_loops | 42512 | 58.78 GiB | 3785696 | 3785696 | 0.0% |
| default | agent_loops | 8192 | 29.25 GiB | 3785696 | 3785696 | 0.0% |
| prefix-32768 | agent_cohorts | 120000 | 75.66 GiB | 16459136 | 15375744 | 6.6% |
| prefix-32768 | agent_cohorts | 16384 | 40.69 GiB | 31735168 | 31735168 | 0.0% |
| prefix-32768 | agent_cohorts | 32768 | 53.62 GiB | 31288704 | 23485824 | 24.9% |
| prefix-32768 | agent_cohorts | 42512 | 58.78 GiB | 29326720 | 16700800 | 43.1% |
| prefix-32768 | agent_cohorts | 8192 | 29.25 GiB | 31735168 | 31735168 | 0.0% |
| prefix-32768 | agent_loops | 120000 | 75.66 GiB | 30502272 | 18492800 | 39.4% |
| prefix-32768 | agent_loops | 16384 | 40.69 GiB | 38780288 | 38780288 | 0.0% |
| prefix-32768 | agent_loops | 32768 | 53.62 GiB | 38516096 | 27452800 | 28.7% |
| prefix-32768 | agent_loops | 42512 | 58.78 GiB | 37686656 | 23575936 | 37.4% |
| prefix-32768 | agent_loops | 8192 | 29.25 GiB | 38780288 | 38780288 | 0.0% |
| prefix-32768-rounds-24 | agent_cohorts | 120000 | 75.66 GiB | 7832064 | 7832064 | 0.0% |
| prefix-32768-rounds-24 | agent_cohorts | 16384 | 40.69 GiB | 14049792 | 14049792 | 0.0% |
| prefix-32768-rounds-24 | agent_cohorts | 32768 | 53.62 GiB | 13453824 | 9499136 | 29.4% |
| prefix-32768-rounds-24 | agent_cohorts | 42512 | 58.78 GiB | 11440640 | 7942656 | 30.6% |
| prefix-32768-rounds-24 | agent_cohorts | 8192 | 29.25 GiB | 14049792 | 14049792 | 0.0% |
| prefix-32768-rounds-24 | agent_loops | 120000 | 75.66 GiB | 8509952 | 7590400 | 10.8% |
| prefix-32768-rounds-24 | agent_loops | 16384 | 40.69 GiB | 15786496 | 15786496 | 0.0% |
| prefix-32768-rounds-24 | agent_loops | 32768 | 53.62 GiB | 15522304 | 9951744 | 35.9% |
| prefix-32768-rounds-24 | agent_loops | 42512 | 58.78 GiB | 14692864 | 8272384 | 43.7% |
| prefix-32768-rounds-24 | agent_loops | 8192 | 29.25 GiB | 15786496 | 15786496 | 0.0% |
| rounds-24 | agent_cohorts | 120000 | 75.66 GiB | 1963200 | 1963200 | 0.0% |
| rounds-24 | agent_cohorts | 16384 | 40.69 GiB | 1963200 | 1963200 | 0.0% |
| rounds-24 | agent_cohorts | 32768 | 53.62 GiB | 1963200 | 1963200 | 0.0% |
| rounds-24 | agent_cohorts | 42512 | 58.78 GiB | 1963200 | 1963200 | 0.0% |
| rounds-24 | agent_cohorts | 8192 | 29.25 GiB | 1963200 | 1963200 | 0.0% |
| rounds-24 | agent_loops | 120000 | 75.66 GiB | 1902784 | 1902784 | 0.0% |
| rounds-24 | agent_loops | 16384 | 40.69 GiB | 1902784 | 1902784 | 0.0% |
| rounds-24 | agent_loops | 32768 | 53.62 GiB | 1902784 | 1902784 | 0.0% |
| rounds-24 | agent_loops | 42512 | 58.78 GiB | 1902784 | 1902784 | 0.0% |
| rounds-24 | agent_loops | 8192 | 29.25 GiB | 1902784 | 1902784 | 0.0% |


Read as a band, our budget is worth 29 to 76 GiB in the replay's unit, and across that band the default 6-conversation
trace and the 3-conversation trace gain nothing at all (0.0% in every cell), while a 32,768-token prefix gains
24.9 to 43.1% (`agent_cohorts`) and 28.7 to 39.4% (`agent_loops`). The 12-conversation trace at 40.69 GiB gains
28.0% (`agent_loops`) and 12.7% (`agent_cohorts`), and 0.0% at the other rungs.

### Our own budget, 8,426,464,256 bytes, at our measured state sizes

This is the direct prediction: the replay's model replaced by our three fitted byte models, the budget left at
the deployed 7.85 GiB, all three seeds, both traces.

**All three seeds, the measured, midpoint and layout byte models.**
| set | trace | seed | cell model | rows main | rows decayed | fewer | main rebuilt / prompt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| conversations-12 | agent_cohorts | 7 | ours-layout | 15865344 | 15223296 | 4.0% | 77.1% |
| conversations-12 | agent_cohorts | 7 | ours-measured | 15293440 | 7752192 | 49.3% | 74.3% |
| conversations-12 | agent_cohorts | 7 | ours-measured-2gib | 15882752 | 15882752 | 0.0% | 77.2% |
| conversations-12 | agent_cohorts | 7 | ours-measured-4gib | 15882752 | 15882752 | 0.0% | 77.2% |
| conversations-12 | agent_cohorts | 7 | ours-measured-6gib | 15882752 | 15882752 | 0.0% | 77.2% |
| conversations-12 | agent_cohorts | 7 | ours-mid | 15697920 | 10118144 | 35.5% | 76.3% |
| conversations-12 | agent_cohorts | 11 | ours-layout | 16159648 | 16159648 | 0.0% | 77.5% |
| conversations-12 | agent_cohorts | 11 | ours-measured | 15825824 | 9042336 | 42.9% | 75.9% |
| conversations-12 | agent_cohorts | 11 | ours-mid | 16130464 | 15162784 | 6.0% | 77.3% |
| conversations-12 | agent_cohorts | 23 | ours-layout | 15932160 | 15611136 | 2.0% | 77.2% |
| conversations-12 | agent_cohorts | 23 | ours-measured | 15370496 | 8049920 | 47.6% | 74.4% |
| conversations-12 | agent_cohorts | 23 | ours-mid | 15750400 | 10495232 | 33.4% | 76.3% |
| conversations-12 | agent_loops | 7 | ours-layout | 19396096 | 17488384 | 9.8% | 80.4% |
| conversations-12 | agent_loops | 7 | ours-measured | 19272704 | 7915008 | 58.9% | 79.9% |
| conversations-12 | agent_loops | 7 | ours-measured-2gib | 19413504 | 19413504 | 0.0% | 80.5% |
| conversations-12 | agent_loops | 7 | ours-measured-4gib | 19413504 | 19413504 | 0.0% | 80.5% |
| conversations-12 | agent_loops | 7 | ours-measured-6gib | 19413504 | 19413504 | 0.0% | 80.5% |
| conversations-12 | agent_loops | 7 | ours-mid | 19350016 | 13661696 | 29.4% | 80.2% |
| conversations-12 | agent_loops | 11 | ours-layout | 19690400 | 19690400 | 0.0% | 80.7% |
| conversations-12 | agent_loops | 11 | ours-measured | 19451296 | 10737056 | 44.8% | 79.7% |
| conversations-12 | agent_loops | 11 | ours-mid | 19661216 | 16758176 | 14.8% | 80.6% |
| conversations-12 | agent_loops | 23 | ours-layout | 19474688 | 19474688 | 0.0% | 80.5% |
| conversations-12 | agent_loops | 23 | ours-measured | 19196672 | 8807680 | 54.1% | 79.4% |
| conversations-12 | agent_loops | 23 | ours-mid | 19417344 | 14321920 | 26.2% | 80.3% |
| conversations-3 | agent_cohorts | 7 | ours-layout | 1910976 | 1910976 | 0.0% | 37.3% |
| conversations-3 | agent_cohorts | 7 | ours-measured | 1910976 | 1910976 | 0.0% | 37.3% |
| conversations-3 | agent_cohorts | 7 | ours-measured-2gib | 3860672 | 3304128 | 14.4% | 75.4% |
| conversations-3 | agent_cohorts | 7 | ours-measured-4gib | 1910976 | 1910976 | 0.0% | 37.3% |
| conversations-3 | agent_cohorts | 7 | ours-measured-6gib | 1910976 | 1910976 | 0.0% | 37.3% |
| conversations-3 | agent_cohorts | 7 | ours-mid | 1910976 | 1910976 | 0.0% | 37.3% |
| conversations-3 | agent_cohorts | 11 | ours-layout | 1897824 | 1897824 | 0.0% | 37.1% |
| conversations-3 | agent_cohorts | 11 | ours-measured | 1897824 | 1897824 | 0.0% | 37.1% |
| conversations-3 | agent_cohorts | 11 | ours-mid | 1897824 | 1897824 | 0.0% | 37.1% |
| conversations-3 | agent_cohorts | 23 | ours-layout | 1934816 | 1934816 | 0.0% | 37.6% |
| conversations-3 | agent_cohorts | 23 | ours-measured | 1934816 | 1934816 | 0.0% | 37.6% |
| conversations-3 | agent_cohorts | 23 | ours-mid | 1934816 | 1934816 | 0.0% | 37.6% |
| conversations-3 | agent_loops | 7 | ours-layout | 1876672 | 1876672 | 0.0% | 31.2% |
| conversations-3 | agent_loops | 7 | ours-measured | 1876672 | 1876672 | 0.0% | 31.2% |
| conversations-3 | agent_loops | 7 | ours-measured-2gib | 4737216 | 2890432 | 39.0% | 78.8% |
| conversations-3 | agent_loops | 7 | ours-measured-4gib | 1876672 | 1876672 | 0.0% | 31.2% |
| conversations-3 | agent_loops | 7 | ours-measured-6gib | 1876672 | 1876672 | 0.0% | 31.2% |
| conversations-3 | agent_loops | 7 | ours-mid | 1876672 | 1876672 | 0.0% | 31.2% |
| conversations-3 | agent_loops | 11 | ours-layout | 1863520 | 1863520 | 0.0% | 31.1% |
| conversations-3 | agent_loops | 11 | ours-measured | 1863520 | 1863520 | 0.0% | 31.1% |
| conversations-3 | agent_loops | 11 | ours-mid | 1863520 | 1863520 | 0.0% | 31.1% |
| conversations-3 | agent_loops | 23 | ours-layout | 1900512 | 1900512 | 0.0% | 31.5% |
| conversations-3 | agent_loops | 23 | ours-measured | 1900512 | 1900512 | 0.0% | 31.5% |
| conversations-3 | agent_loops | 23 | ours-mid | 1900512 | 1900512 | 0.0% | 31.5% |
| default | agent_cohorts | 7 | ours-layout | 3846112 | 3846112 | 0.0% | 37.4% |
| default | agent_cohorts | 7 | ours-measured | 3846112 | 3846112 | 0.0% | 37.4% |
| default | agent_cohorts | 7 | ours-measured-2gib | 7944160 | 7944160 | 0.0% | 77.2% |
| default | agent_cohorts | 7 | ours-measured-4gib | 7501792 | 4430304 | 40.9% | 72.9% |
| default | agent_cohorts | 7 | ours-measured-6gib | 3846112 | 3846112 | 0.0% | 37.4% |
| default | agent_cohorts | 7 | ours-mid | 3846112 | 3846112 | 0.0% | 37.4% |
| default | agent_cohorts | 11 | ours-layout | 3858560 | 3858560 | 0.0% | 37.5% |
| default | agent_cohorts | 11 | ours-measured | 3858560 | 3858560 | 0.0% | 37.5% |
| default | agent_cohorts | 11 | ours-mid | 3858560 | 3858560 | 0.0% | 37.5% |
| default | agent_cohorts | 23 | ours-layout | 3874624 | 3874624 | 0.0% | 37.6% |
| default | agent_cohorts | 23 | ours-measured | 3874624 | 3874624 | 0.0% | 37.6% |
| default | agent_cohorts | 23 | ours-mid | 3874624 | 3874624 | 0.0% | 37.6% |
| default | agent_loops | 7 | ours-layout | 3785696 | 3785696 | 0.0% | 31.4% |
| default | agent_loops | 7 | ours-measured | 3785696 | 3785696 | 0.0% | 31.4% |
| default | agent_loops | 7 | ours-measured-2gib | 9705440 | 9705440 | 0.0% | 80.5% |
| default | agent_loops | 7 | ours-measured-4gib | 9348576 | 3785696 | 59.5% | 77.5% |
| default | agent_loops | 7 | ours-measured-6gib | 3785696 | 3785696 | 0.0% | 31.4% |
| default | agent_loops | 7 | ours-mid | 3785696 | 3785696 | 0.0% | 31.4% |
| default | agent_loops | 11 | ours-layout | 3798144 | 3798144 | 0.0% | 31.5% |
| default | agent_loops | 11 | ours-measured | 3798144 | 3798144 | 0.0% | 31.5% |
| default | agent_loops | 11 | ours-mid | 3798144 | 3798144 | 0.0% | 31.5% |
| default | agent_loops | 23 | ours-layout | 3814208 | 3814208 | 0.0% | 31.6% |
| default | agent_loops | 23 | ours-measured | 3814208 | 3814208 | 0.0% | 31.6% |
| default | agent_loops | 23 | ours-mid | 3814208 | 3814208 | 0.0% | 31.6% |
| prefix-32768 | agent_cohorts | 7 | ours-layout | 30203264 | 15531392 | 48.6% | 73.5% |
| prefix-32768 | agent_cohorts | 7 | ours-measured | 27309440 | 15453568 | 43.4% | 66.4% |
| prefix-32768 | agent_cohorts | 7 | ours-measured-2gib | 31800704 | 31735168 | 0.2% | 77.4% |
| prefix-32768 | agent_cohorts | 7 | ours-measured-4gib | 31735168 | 31735168 | 0.0% | 77.2% |
| prefix-32768 | agent_cohorts | 7 | ours-measured-6gib | 31735168 | 31735168 | 0.0% | 77.2% |
| prefix-32768 | agent_cohorts | 7 | ours-mid | 28614016 | 15494528 | 45.8% | 69.6% |
| prefix-32768 | agent_cohorts | 11 | ours-layout | 30539776 | 16957440 | 44.5% | 74.2% |
| prefix-32768 | agent_cohorts | 11 | ours-measured | 27570176 | 15503360 | 43.8% | 67.0% |
| prefix-32768 | agent_cohorts | 11 | ours-mid | 29200384 | 15536128 | 46.8% | 70.9% |
| prefix-32768 | agent_cohorts | 23 | ours-layout | 30331648 | 16384768 | 46.0% | 73.6% |
| prefix-32768 | agent_cohorts | 23 | ours-measured | 27755264 | 15567616 | 43.9% | 67.3% |
| prefix-32768 | agent_cohorts | 23 | ours-mid | 28607232 | 15602432 | 45.5% | 69.4% |
| prefix-32768 | agent_loops | 7 | ours-layout | 38149504 | 20815232 | 45.4% | 79.2% |
| prefix-32768 | agent_loops | 7 | ours-measured | 36662656 | 18732416 | 48.9% | 76.1% |
| prefix-32768 | agent_loops | 7 | ours-measured-2gib | 40549760 | 38780288 | 4.4% | 84.2% |
| prefix-32768 | agent_loops | 7 | ours-measured-4gib | 38780288 | 38780288 | 0.0% | 80.5% |
| prefix-32768 | agent_loops | 7 | ours-measured-6gib | 38780288 | 38780288 | 0.0% | 80.5% |
| prefix-32768 | agent_loops | 7 | ours-mid | 37399936 | 20387200 | 45.5% | 77.6% |
| prefix-32768 | agent_loops | 11 | ours-layout | 38203392 | 21561344 | 43.6% | 79.2% |
| prefix-32768 | agent_loops | 11 | ours-measured | 36653056 | 18606080 | 49.2% | 76.0% |
| prefix-32768 | agent_loops | 11 | ours-mid | 37548032 | 18944000 | 49.5% | 77.8% |
| prefix-32768 | agent_loops | 23 | ours-layout | 38109952 | 21334784 | 44.0% | 78.9% |
| prefix-32768 | agent_loops | 23 | ours-measured | 36911872 | 17826560 | 51.7% | 76.4% |
| prefix-32768 | agent_loops | 23 | ours-mid | 37579520 | 19245824 | 48.8% | 77.8% |
| prefix-32768-rounds-24 | agent_cohorts | 7 | ours-layout | 12237312 | 8020480 | 34.5% | 65.4% |
| prefix-32768-rounds-24 | agent_cohorts | 7 | ours-measured | 9642496 | 7942656 | 17.6% | 51.6% |
| prefix-32768-rounds-24 | agent_cohorts | 7 | ours-measured-2gib | 14049792 | 14049792 | 0.0% | 75.1% |
| prefix-32768-rounds-24 | agent_cohorts | 7 | ours-measured-4gib | 14049792 | 14049792 | 0.0% | 75.1% |
| prefix-32768-rounds-24 | agent_cohorts | 7 | ours-measured-6gib | 14049792 | 14049792 | 0.0% | 75.1% |
| prefix-32768-rounds-24 | agent_cohorts | 7 | ours-mid | 11028992 | 7979520 | 27.6% | 59.0% |
| prefix-32768-rounds-24 | agent_cohorts | 11 | ours-layout | 12575872 | 8037504 | 36.1% | 67.4% |
| prefix-32768-rounds-24 | agent_cohorts | 11 | ours-measured | 9958528 | 7849088 | 21.2% | 53.4% |
| prefix-32768-rounds-24 | agent_cohorts | 11 | ours-mid | 11517056 | 7922816 | 31.2% | 61.8% |
| prefix-32768-rounds-24 | agent_cohorts | 23 | ours-layout | 12682880 | 8867456 | 30.1% | 67.5% |
| prefix-32768-rounds-24 | agent_cohorts | 23 | ours-measured | 10671744 | 7997056 | 25.1% | 56.8% |
| prefix-32768-rounds-24 | agent_cohorts | 23 | ours-mid | 11722368 | 7997056 | 31.8% | 62.4% |
| prefix-32768-rounds-24 | agent_loops | 7 | ours-layout | 15155712 | 7590400 | 49.9% | 74.0% |
| prefix-32768-rounds-24 | agent_loops | 7 | ours-measured | 13668864 | 7590400 | 44.5% | 66.8% |
| prefix-32768-rounds-24 | agent_loops | 7 | ours-measured-2gib | 15852032 | 15786496 | 0.4% | 77.4% |
| prefix-32768-rounds-24 | agent_loops | 7 | ours-measured-4gib | 15786496 | 15786496 | 0.0% | 77.1% |
| prefix-32768-rounds-24 | agent_loops | 7 | ours-measured-6gib | 15786496 | 15786496 | 0.0% | 77.1% |
| prefix-32768-rounds-24 | agent_loops | 7 | ours-mid | 14406144 | 7590400 | 47.3% | 70.4% |
| prefix-32768-rounds-24 | agent_loops | 11 | ours-layout | 15107200 | 7642240 | 49.4% | 74.0% |
| prefix-32768-rounds-24 | agent_loops | 11 | ours-measured | 13556864 | 7537792 | 44.4% | 66.4% |
| prefix-32768-rounds-24 | agent_loops | 11 | ours-mid | 14451840 | 7570560 | 47.6% | 70.8% |
| prefix-32768-rounds-24 | agent_loops | 23 | ours-layout | 15097472 | 7952000 | 47.3% | 73.4% |
| prefix-32768-rounds-24 | agent_loops | 23 | ours-measured | 13899392 | 7685760 | 44.7% | 67.6% |
| prefix-32768-rounds-24 | agent_loops | 23 | ours-mid | 14567040 | 7685760 | 47.2% | 70.8% |
| rounds-24 | agent_cohorts | 7 | ours-layout | 1963200 | 1963200 | 0.0% | 41.9% |
| rounds-24 | agent_cohorts | 7 | ours-measured | 1963200 | 1963200 | 0.0% | 41.9% |
| rounds-24 | agent_cohorts | 7 | ours-measured-2gib | 3517632 | 3517632 | 0.0% | 75.1% |
| rounds-24 | agent_cohorts | 7 | ours-measured-4gib | 3014848 | 2028736 | 32.7% | 64.4% |
| rounds-24 | agent_cohorts | 7 | ours-measured-6gib | 1963200 | 1963200 | 0.0% | 41.9% |
| rounds-24 | agent_cohorts | 7 | ours-mid | 1963200 | 1963200 | 0.0% | 41.9% |
| rounds-24 | agent_cohorts | 11 | ours-layout | 1950048 | 1950048 | 0.0% | 41.8% |
| rounds-24 | agent_cohorts | 11 | ours-measured | 1950048 | 1950048 | 0.0% | 41.8% |
| rounds-24 | agent_cohorts | 11 | ours-mid | 1950048 | 1950048 | 0.0% | 41.8% |
| rounds-24 | agent_cohorts | 23 | ours-layout | 1987040 | 1987040 | 0.0% | 42.2% |
| rounds-24 | agent_cohorts | 23 | ours-measured | 1987040 | 1987040 | 0.0% | 42.2% |
| rounds-24 | agent_cohorts | 23 | ours-mid | 1987040 | 1987040 | 0.0% | 42.2% |
| rounds-24 | agent_loops | 7 | ours-layout | 1902784 | 1902784 | 0.0% | 37.1% |
| rounds-24 | agent_loops | 7 | ours-measured | 1902784 | 1902784 | 0.0% | 37.1% |
| rounds-24 | agent_loops | 7 | ours-measured-2gib | 3951808 | 3951808 | 0.0% | 77.1% |
| rounds-24 | agent_loops | 7 | ours-measured-4gib | 3594944 | 1902784 | 47.1% | 70.2% |
| rounds-24 | agent_loops | 7 | ours-measured-6gib | 1902784 | 1902784 | 0.0% | 37.1% |
| rounds-24 | agent_loops | 7 | ours-mid | 1902784 | 1902784 | 0.0% | 37.1% |
| rounds-24 | agent_loops | 11 | ours-layout | 1889632 | 1889632 | 0.0% | 37.0% |
| rounds-24 | agent_loops | 11 | ours-measured | 1889632 | 1889632 | 0.0% | 37.0% |
| rounds-24 | agent_loops | 11 | ours-mid | 1889632 | 1889632 | 0.0% | 37.0% |
| rounds-24 | agent_loops | 23 | ours-layout | 1926624 | 1926624 | 0.0% | 37.4% |
| rounds-24 | agent_loops | 23 | ours-measured | 1926624 | 1926624 | 0.0% | 37.4% |
| rounds-24 | agent_loops | 23 | ours-mid | 1926624 | 1926624 | 0.0% | 37.4% |


The pattern is a threshold, not a slope:

- **3 conversations (working set 15.5% of budget) and 6 conversations at 8k (30.9%): 0.0% on every seed, every
  trace and every byte model.** The cache never has to make the choice the policy changes: `main` already keeps
  every conversation state and evicts one-off prompts, and the rebuilt rows are the one-off prompts themselves
  (31.4% of `agent_loops`' prompt rows) plus each turn's growth.
- **6 conversations at a 32,768-token prefix (88.8%): 43.4 to 51.7% with the measured model, 45.5 to 49.5% with
  the midpoint, 43.6 to 48.6% with the layout model.** All three byte models agree to within 8 points, so this
  prediction is the robust one.
- **12 conversations at 8k (61.8%): 42.9 to 58.9% with the measured model, 6.0 to 35.5% with the midpoint, 0.0 to
  9.8% with the layout model.** Here the three models disagree over the whole range, because the budget sits at
  the edge: with states 9% larger, the twelve states plus a round of one-offs no longer leave the credit room to
  act. Treat 12 short conversations as undetermined by this replay (see section 7).

The small-budget cells (measured model) show the same threshold from the other side: for the default 6-conversation
trace, 2 GiB gives 0.0%, 4 GiB gives 59.5% (`agent_loops`) and 40.9% (`agent_cohorts`), and 6 GiB gives 0.0%
again. The policy pays in a band around the point where the conversation set just oversubscribes the cache; below
it the cache thrashes whatever the policy does, above it nothing needs evicting.

### Half-length traces

A 24-round trace reaches the same regime with about half the rows, which matters for the cost of a served A/B:

- `rounds-24` (6 conversations, 8k prefix): 0.0% on every seed and every model, as for the 48-round set.
- `prefix-32768-rounds-24`, `agent_loops`: measured 44.4 to 44.7%, midpoint 47.2 to 47.6%, layout 47.3 to 49.9%.
  All three models still agree, at half the rows, so this is the cheapest trace that carries the robust signal.
- `prefix-32768-rounds-24`, `agent_cohorts`: measured 17.6 to 25.1% against the layout model's 30.1 to 36.1%,
  the same model-direction disagreement as the 12-conversation case, so it is not a good first target.

## 5. D. What a served A/B would cost

Cold prefill on this serve is about 2.0K rows a second at 8k and 2.2K at 32k and 120k: queue91's cold cells took
3,964 ms for 8,005 tokens, 14,795 ms for 32,014 and 55,351 ms for 120,388 (`work/pp91/f91-c/mn1-probe.out`), i.e.
2,019, 2,164 and 2,175 rows a second. A boot takes 131 s (`work/pp91/f91-boots/c91-mn1.log`, "[zig-tp3] up in
131 s"). The cost below uses 2,000 rows a second and adds 16 decode tokens per request at ~60 tokens a second
(864 requests = 230 s, 1,728 = 461 s), plus one boot per arm; HTTP, tokenize and admission are under 3 ms a
request and are not counted.

#### Requests, rebuilt rows and seconds per trace, at 2,000 rows a second
| set | trace | requests | prompt rows | rows rebuilt main | seconds main | rows rebuilt decayed | seconds decayed | seconds saved |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| conversations-12 | agent_cohorts | 1728 | 20584960 | 15293440 | 7647 | 7752192 | 3876 | 3771 |
| conversations-12 | agent_loops | 1728 | 24123904 | 19272704 | 9636 | 7915008 | 3958 | 5679 |
| conversations-3 | agent_cohorts | 432 | 5123264 | 1910976 | 955 | 1910976 | 955 | 0 |
| conversations-3 | agent_loops | 432 | 6008000 | 1876672 | 938 | 1876672 | 938 | 0 |
| default | agent_cohorts | 864 | 10287072 | 3846112 | 1923 | 3846112 | 1923 | 0 |
| default | agent_loops | 864 | 12056544 | 3785696 | 1893 | 3785696 | 1893 | 0 |
| prefix-32768 | agent_cohorts | 864 | 41106816 | 27309440 | 13655 | 15453568 | 7727 | 5928 |
| prefix-32768 | agent_loops | 864 | 48184704 | 36662656 | 18331 | 18732416 | 9366 | 8965 |
| prefix-32768-rounds-24 | agent_cohorts | 432 | 18702848 | 9642496 | 4821 | 7942656 | 3971 | 850 |
| prefix-32768-rounds-24 | agent_loops | 432 | 20472320 | 13668864 | 6834 | 7590400 | 3795 | 3039 |
| rounds-24 | agent_cohorts | 432 | 4680896 | 1963200 | 982 | 1963200 | 982 | 0 |
| rounds-24 | agent_loops | 432 | 5123264 | 1902784 | 951 | 1902784 | 951 | 0 |


Per experiment, with a fresh boot per arm (the client requires a fresh model process per trace and policy, and
`compare` requires matching settings, fixtures and ordered request identities):

| experiment | parameters (all `agent_loops`, `--tokens 16 --seed 11`) | main arm | decayed arm | boots | total | predicted saving |
| --- | --- | --- | --- | --- | --- | --- |
| E1, mechanism at a reduced budget | 6 conversations, 48 rounds, prefix 8,192, `--prompt-cache-gib 4` on both arms | 4,674 s | 1,893 s | 2 | about 2.0 h | 59.5% (measured model only; the band is sharp: 0.0% at 2 GiB, 0.0% at 6 GiB) |
| E2, deployed budget, short contexts | 6 conversations, 48 rounds, prefix 8,192 | 1,893 s | 1,893 s | 2 | about 1.3 h | 0.0%: not worth running |
| E3, deployed budget, long contexts, half length | 6 conversations, 24 rounds, prefix 32,768 | 6,834 s | 3,795 s | 2 | about 3.2 h | 44.4 to 49.9%, all three models agree |
| E4, deployed budget, long contexts, full length | 6 conversations, 48 rounds, prefix 32,768 | 18,331 s | 9,366 s | 2 | about 8.0 h | 43.4 to 51.7%, all three models agree |
| E5, many short conversations | 12 conversations, 48 rounds, prefix 8,192 | 9,636 s | 3,958 s | 2 | about 4.2 h | 42.9 to 58.9% (measured), 0 to 9.8% (layout): undetermined |

Adding `agent_cohorts` doubles the client time for a similar direction (17.6 to 36.1% at 24 rounds, 43.4 to 48.6%
at 48 rounds in the 32k-prefix sets), so `agent_loops` alone is the cheaper arm. E3 is the cheapest trace that
still reaches the deployed regime with a model-independent prediction.

## 6. Recommendation

**Predicted saving at our 7.85 GiB budget, in a range.** If the owner's live conversations are short and few (up
to six conversations at an 8k prefix, a working set under about a third of the cache), `decayed_resume` saves
**nothing measurable**: 0.0% of rebuilt rows on every seed and every byte model, because the cache is never forced
to choose between a conversation and a one-off. If they are long (six conversations at a 30k-plus prefix, a
working set near the budget), it saves **43 to 52% of rebuilt prompt rows at our measured state sizes**, and all
three byte models agree. In between, the saving appears abruptly and is sensitive to the exact state size: twelve
short conversations predict anywhere from 0% to 59% depending on which of the three byte models is right.

**Is a served A/B worth it?** Yes, but only in the informative regimes. The default 6-conversation 8k trace is
not worth a window at all (0.0%, 32 minutes an arm). Recommended order:

1. **E3, about 3.2 h, the deployed answer.** `agent_loops`, 6 conversations, 24 rounds, prefix 32,768, the
   deployed budget, `TF_CACHE_EVICT` unset against `decayed_resume`, a fresh boot per arm, `--tokens 16 --seed 11`,
   then `tools/bench_cache_agents.py compare A.json B.json`. All three byte models predict 44 to 50% fewer rebuilt
   rows (6,834 s of prefill against 3,795 s at 2,000 rows a second), so the run confirms a large, model-independent
   prediction rather than choosing between models.
2. **E1, about 2 h, the mechanism.** `agent_loops`, 6 conversations, 48 rounds, prefix 8,192,
   `--prompt-cache-gib 4` on both arms. Predicted 59.5% with the measured model, but the prediction is a sharp
   function of the budget, so treat it as a mechanism check that also calibrates the replay's carry model against
   the shipped selector (the replay stamps the credit on the kept successors; the shipped policy carries it on the
   entry and its successors). Do this first if the 32k run has to wait for a GPU night.
3. **E5 only if the owner's real session count is known to be near twelve.** Its prediction is undetermined here
   (0% to 59% across the byte models), so a served run would be measuring, not confirming.
4. **Skip E2/E4.** The default shape is 0.0% by construction, and the 48-round 32k run costs 2.5 times E3 for the
   same answer with more statistics.

Both arms need the same checkpoint, template, context (1,048,576), stream count (4) and cache budget; only
`TF_CACHE_EVICT` (and in E1 the budget itself, identically on both arms) changes. The cache must start empty on
both arms, so the boot for each arm must be fresh, and the comparison needs token-equal replies
(`compare` exits 0 only then).

**Which parameters to use.** Upstream's client defaults, unchanged: `--trace agent_loops --conversations 6
--rounds 48 --prefix-tokens 8192 --tokens 16 --seed 11`, and for E3 `--prefix-tokens 32768`. The replay's own
mapping of `--prefix-tokens 32768` is what the `prefix-32768` set in the sweep uses: base 65,536, session stride
4,096, growth 2,048 a turn, one-offs 4,096 to 48,000 tokens.

## 7. What I could not confirm from the repo, and how I resolved it

- **Per-state bytes are not in the facts rows.** Every facts row under `work/` that carries
  `prompt_cache_states` reports 0, so the accounting counters cannot price a state there. Resolved with the same
  boots' probe rows, whose `cache` block reports `held_mib` and `states` after each request; the three
  single-state deltas and the reported 168 MiB minimum give the affine fit.
- **The deployed stack's row price is 11 caches' worth, not the layout's 12.** The measured slope (6,378 B a row)
  is one 580-B cache share below the fp8 page math (6,960 B a row), while the stock-main image's slope (6,947 B a
  row) matches the page math. Both images run the same model and the same fp8 caches, so the difference is in the
  patch stack, not in the model. [INFERENCE] One cache's rows (the MTP layer's) are not part of a kept state on
  the patched stack. The layout model is carried as the pessimistic bound either way.
- **The 12-conversation result is a knife edge, and I did not isolate the mechanism.** The credit is at most 16
  store ticks (eight a resume, two resumes: `cache_replay_decay.zig:25-27`); whether that bridges the gap between
  a conversation state used a round ago and a one-off kept since depends on how many requests a round costs, which
  the store's clock counts. [INFERENCE] With states 9% larger the credit no longer spans a round's insertions, and
  the two policies make the same choices (the layout model's 12-conversation cells rebuild exactly equal rows).
  This is consistent with the numbers but not proved; the served A/B is the arbiter, which is why I recommend
  against relying on E5's prediction.
- **The replay's mark rules are not our engine's.** The replay runs the real store with `.chunk = 1` only, so a
  request keeps its history mark plus the shared marks. Our engine also keeps interior cuts on long messages
  (queue91's probe shows `kept_states 2` on 32k and 120k prompts) and applies its own `min_gap` and fork rules.
  More kept states per request means more pressure and, if anything, more to save; the prediction is therefore a
  model of the policy's direction and size, not a byte-exact forecast of the served run.
- **The 16 GiB reproduction is not bit-exact to upstream's prose.** One of their three seeds sits at 34.5% against
  a quoted 28 to 34%; their quoted range is a rounding of the same measurement, and the sweep's own 4/8/16 GiB
  cells equal the unmodified replay's output exactly (12 of 12), so the trace and the policy are faithful. The
  discrepancy is in their rounded prose, not in the runs.
- **Two images, two minima.** The facts rows show both 176,160,768 (168 MiB, m130a) and 178,257,920 (170 MiB,
  the stock-main boot) as the minimum state, which is what the two fits were anchored to at 2,048 rows. That
  cross-check is what ties the probe-row deltas to the reported minimum.
- **The replay counts a hit at the exact prefix length; this engine resumes at a chunk boundary (added by the reviewer, not the lane).**
  queue91's chain rows for a growing chat of 112,695 to 121,557 tokens show every resumed turn reusing a multiple of 2,048 rows
  (112,640, 114,688, 116,736 and 118,784), the gap to the previous prompt being 55 to 1,839 rows with a mean of 944 and nothing evicted.
  Both arms of a served run lose that tail on every resumed turn, about a thousand rows against the tens of thousands a lost state
  costs, so the direction and size of the prediction are not affected. It does change how a served run must count a resumed turn:
  the rule P2 of score98.py allows one chunk plus the template's few rows before a turn counts as not resumed.
- **Inputs the reviewer re-read from the boot and probe records (the lane's figures, checked).** The stack on the pin's boot record reads
  `prompt_cache_budget_bytes` 8,426,464,256 and `prompt_cache_minimum_state_bytes` 176,160,768; its three cold probes grow the held cache
  from 202 to 554 to 1,442 MiB, which are single states of 202, 352 and 888 MiB at 8,005, 32,014 and 120,388 tokens. The `/metrics`
  gauge `prompt_cache_bytes` is "storage held by retained prompt states and spare buffers" (the engine's own help text) and reads
  8,426,356,736 at boot with no state held, so it is not occupancy; `prompt_cache_states` is the count.

## 8. Files and reproduction (the patch is archived beside this record as `cache-agent-sweep-46c6ee2.patch`)

Scratch for this lane was `work/cache-replay-lane/` (patch, logs, `summarise.py`, `report_tables.py`); as
instructed, only this report is kept. The run that produced every table above is the `iter --name cacheev` command
in section 1, with the patch reproduced in appendix A. The logs it read were
`~/spark-gates/iter-cacheev/zig-cache-agent-replay.log` (24 JSON lines) and
`~/spark-gates/iter-cacheev/zig-cache-agent-sweep.log` (one JSON line per cell and policy, with `set`, `trace`,
`seed`, `cell`, `policy`, `budget_bytes`, `ref_rows`, `requests`, `hits`, `prompt_rows`, `rebuilt_rows`,
`evictions`, `peak_bytes` and the three fitted state sizes).
