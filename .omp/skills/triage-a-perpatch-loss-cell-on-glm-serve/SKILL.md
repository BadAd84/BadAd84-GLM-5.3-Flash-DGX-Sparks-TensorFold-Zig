---
name: triage-a-perpatch-loss-cell-on-glm-serve
description: "GLM per-patch A/B shows a starred loss: rule out fill-pattern mix, moved first-use kernel loads, run-level shift before any rewrite."
---

# Triage a starred loss in a GLM per-patch A/B

Use when `perpatch_report.py --ref <arm> <run>` (glm5.3-flash-dev `scripts/glm53/v110/perpatch/`) shows a `*` cell
against a patch (every boot of one side beats every boot of the other) and the fleet rule's 5-step procedure is about
to start. In confirmations c1-c4 (2026-10-30) every loss cell examined (0101, 0104, 0105, 0108, 0109, 0121) was one
of the three artefacts below; none needed a rewrite. Rule them out in this order, from data already on disk, before
dispatching a take-apart lane.

## 1. Fill-pattern mix (burst probes)
- short, forks and fanout send PARALLEL requests at once. An admission race decides whether they fill in one shared
  prompt chunk or apart. Per boot: `d_mp_chunks` / `d_mp_pieces` in the probe's JSON (deltas of /health
  `multi_prefill`).
- The report flags an arm whose pattern mix differs from the reference's and prints within-pattern lines (short:
  `short_mspr_net within the first-fill pattern`; forks: `forks_ttft within the fill pattern`, `forks_mspr_net`).
  When flagged, judge the within-pattern line, never the raw cell.
- Decode booking: a stream's decode seconds start at its first token, so in a split fill the first stream's wait
  through the other's chunk is booked as decode (+130-160 ms a rep at P2, about +2 ms "a round"). Use
  `ms_per_round_net` (the server's `fill_wait_seconds_total` when the image has GroupedFill-2, else `wait_s`).

## 2. A first-use load the patch moves into the probe
- Triton kernel variants load at their first launch, once per process, on every rank. A patch that changes how
  prompts are chunked can move that first launch into a different probe. 0121 made the forks the first to run the
  small-row `sparse.select_tokens` variants (prompt pieces under 64 rows past the dense limit): ~15-25 ms once.
- The tell: the same absolute cost at every level, and it vanishes when the probe is repeated in the same process.
- The harness sends a `forks_warm` burst before the timed forks (report row `forks_warm_ttft`). For another probe,
  repeat the request in the same process (lane ForksLoss's laptop rig over the real MultiDecoder).

## 3. A run-level shift
- Pool every boot of the same image AND env across runs (e.g. wave 1 + c2 + c4) and permutation-test. One run's star
  can be that run's reference boots sitting high: 0109's r2 at P2 read -1.5%* in c4, -0.4% (p 0.55) pooled.
- Read the twin probe doing the same work (r2 beside r2m: the same kept state, about the same new rows). A
  per-request cost shows in both.

## 4. Only then take it apart
The fleet rule's steps 2-5 (`~/.omp/agent/AGENTS.md`, "Local serve speed work"): the mechanism from counters (tokens a
round against ms a round, then the stage that grew), a rewrite, else a gate on stream count and length, logged in
`docs/LEADS.md` "Trades kept", the owner last.

## Hygiene the above relies on
- The benchmark firewall on (`fw8888.sh guard <chain pid> ~/perpatch/fwguard`, armed over `ssh -A`; re-arm after a
  chain restart) and sparkDash off; the report flags foreign requests per probe.
- Each run measures with its own copy of the python helpers (`$RUN/bin`, since 2026-10-30), so replacing
  `~/perpatch/*.py` on spark1 mid-run only changes later runs.
