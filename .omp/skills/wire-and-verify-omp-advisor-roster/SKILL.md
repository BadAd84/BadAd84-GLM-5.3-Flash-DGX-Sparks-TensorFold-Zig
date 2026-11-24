---
name: wire-and-verify-omp-advisor-roster
description: "Configure omp's WATCHDOG.yml advisor roster (models, cadences, fallbacks), verify it live, and health-watch the advisors plus the judge role"
---

# Wire and verify an omp advisor roster (WATCHDOG.yml)

Use when configuring omp's advisor subsystem: named advisors, per-advisor models/cadences,
or swapping models (e.g. cloud subs in, local serves in later). omp docs: `omp://advisor-watchdog.md`.

## The layering (don't mix them up)
- `~/.omp/agent/WATCHDOG.yml` = the roster AND the shared `instructions:` block. Created/edited
  via `/advisor configure` in the TUI (User scope) or by hand. GUI's "global advisor instructions"
  field = top-level `instructions:`; per-advisor fields = `advisors[].instructions` (APPENDED after
  shared, never replace). No WATCHDOG.yml = single default advisor on `modelRoles.advisor`.
- `WATCHDOG.md` (same dir) is a SEPARATE discovery file that ALSO concatenates into every advisor
  prompt. If guidance moves into the yml, delete the md or every rule appears twice.
- Advisors snapshot prompts at BUILD time: new sessions automatic; running sessions need
  `/advisor configure` -> save (rebuild). models.yml additions DO resolve in old processes via
  background model discovery - do not claim a restart is needed without checking artifacts.

## Roster shape that works (three-advisor, measured 2026-10-28)
```yaml
instructions: |
  <shared house rules; state how many advisors share them and that role blocks follow>
advisors:
  - name: GLM turn reviewer        # model: zai/glm-5.3-flash, reviewMode: turn, syncBacklog: off
  - name: DeepSeek turn reviewer    # model: deepseek/deepseek-v4-flash, reviewMode: turn
  - name: Opus final reviewer       # model: router/opus-5.5-api, reviewMode: agent-end
```
Per-advisor `instructions:` should state the vantage point (turn = delta-scoped in-flight
correction, no workspace sweeps; agent-end = whole-arc final gate + one-continuation nudge).
Fallback for a reviewer: `retry.fallbackChains:` in config.yml keyed on the exact model selector
(e.g. `router/opus-5.5-api: [router/opus-4.8-api]`); a classifier refusal PINS to the fallback.

## Verification (evidence, never "it configured")
1. YAML parses (python yaml). 2. Headless end-to-end probe per NEW model id:
   `cd <fresh empty dir> && omp -p --model <provider/model> --max-time 80s --mode json "Reply with exactly: OK" </dev/null`
   - stdin MUST be </dev/null (omp -p reads stdin to EOF and hangs otherwise)
   - run from a FRESH dir or omp -p resumes the latest session in cwd
   - check `"model":"<id>"` attributions + the OK reply in the output
3. Advisor build/run proof: `<session-dir>/__advisor.<slug>.jsonl` artifacts (mtime + tail model
   field). `/advisor dump raw` shows the built prompt. Attribute live advisories by advisor name.
4. Health watch: 5-min loop checking artifact mtimes (turn reviewers stall vs PRIMARY activity;
   opus only alerts when a run ENDED - primary quiet 5-30 min - with no final review after it),
   new halt/no_model/quarantine lines in ~/.omp/logs/omp.<date>.*.log, and judge health from
   TRANSCRIPTS (stats.db reads are checkpoint-stale, see below).
5. NEVER overwrite a running script file (bash re-reads from its byte offset -> exit 127 garbage);
  kill the job first. Long watchers: plain `bash script` with timeout: 0 (NOT named-service mode).

## Judge (Jev) metering
omp's judge role calls (purposes: ttsr rule-condition eval, auto-thinking classifier) go to the
Opper CLOUD, never the CT105 ots-jev service - CT105 logs show nothing. Live per-call truth:
grep '"provider":"opper"' in session JSONLs (timestamp/purpose/usage/error_message fields).
stats.db `messages` table works only when caught between checkpoints; `immutable=1` and `mode=ro`
both miss post-checkpoint WAL rows.
