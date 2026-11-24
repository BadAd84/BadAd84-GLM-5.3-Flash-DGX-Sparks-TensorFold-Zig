---
name: run-fair-omp-model-benchmarks-no-leak
description: "Run fair, uncontaminated agentic-model benchmarks as omp sessions (interactive OR headless omp -p) against shared task folders, then grade byte-exact on held-out inputs via an independent oracle. Close ALL THREE leak vectors: autolearn answer-skills, mnemopi cross-project recall, AND omp -p's silent session-continuation. Use before/between benchmarking local Spark models (DSV4/Qwen/GLM/KAT/coder) on graded RE/coding tasks."
---

Goal: measure a model's REAL capability/cost on our graded tasks (`re-cost-benchmark/` easy suite, `mtm-selfbootstrap/` hard from-binary task) with NO way for one model to cheat off another's leaked solution, and grade the result objectively.

## The THREE contamination vectors (all must be closed)

### 1. Memory / autolearn (mnemopi + auto-minted skills)
omp auto-mints, after a solve: (a) a **managed skill** containing the algorithm (e.g. `mtm-activator-builder-spec`, `re-cost-benchmark-solver`) that is surfaced to EVERY future agent; (b) **mnemopi working_memory rows** holding the recovered constants/answers. And your REAL project banks (`mtm-unlock-keygen`, `ots-rs232-tcp-driver`, etc.) legitimately hold the answers.
Fix for a benchmark campaign (`~/.omp/agent/config.yml`, restore after):
- `autolearn.enabled: false` (stop auto-minting answer skills/memories at run end)
- `memory.backend: none` for fully-unattended runs (no recall, no retain) — belt-and-suspenders also `mnemopi.polyphonicRecall: false` (kills cross-project recall).
- Purge any pre-existing leak: `manage_skill delete` the answer skills; delete the task's mnemopi bank dir under `~/.omp/agent/memories/mnemopi/banks/<bank>` (SQLite WAL lets you `DELETE FROM working_memory` + clear `memory_embeddings` + FTS even while the DB is open; a lingering process only blocks file-unlink, not row-delete).
- Config is read at PROCESS START, so changes only apply to a FRESH omp process, not a running session.

### 2. omp -p silent SESSION-CONTINUATION (the non-obvious one — cost a full run)
`omp -p "<prompt>" --cwd <folder>` DEFAULTS to continuing/appending the latest session for that cwd's session-dir: the new user message lands right after the previous run's final assistant message with NO reset_boundary, so the new model inherits the PRIOR model's entire transcript (incl. its written solution). A "fresh" benchmark is silently contaminated.
Fix: give every run its own isolated **`--session-dir <fresh empty dir>`** (nothing to continue → clean context). Then VERIFY clean start by reading that dir's jsonl: exactly 1 `role:user` event, small event count, none of the prior model's text (`grep` for a distinctive prior phrase → absent).

### 3. Recall during the run
Even with the above, confirm the run made **0 recall/reflect calls and 0 `skill://` reads** (parse the session jsonl). Watching live also catches it.

## Headless invocation (Windows)
`omp -p "<prompt>" --model <provider>/<model> --cwd <folder> --session-dir <fresh> < /dev/null`
- Detach so it survives job-timeouts: Python `subprocess.Popen(..., stdin=DEVNULL, stdout=logfile, creationflags=DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP)`.
- `-p` text mode BUFFERS output behind a "Working..." spinner — the blank omp window is normal, not a hang; monitor via the session jsonl growth + the served endpoint's `vllm:num_requests_running`.
- Kill a contaminated run with `taskkill /PID <pid> /T /F`; never kill the other omp.exe (your own TUI session / telegram bridge).

## Grading (objective, not self-report)
- Build an INDEPENDENT oracle (e.g. unicorn-emulate the real binary function) and a grader that runs N fresh held-out inputs byte-exact. **Validate the grader on a KNOWN-GOOD prior solution first** (must return solved/250-of-250) so you know it discriminates before the run lands.
- Rank on cost-to-answer: solved? → rounds → gen+prompt tokens → wall. tok/s is a footnote (prompt tokens processed grow ~rounds² in an agentic loop).

## Between models
Archive the produced artifacts (`solution_*.py`/`mtm.py` + `__pycache__`) to `bench_runs/<model>/`, reset the task folder to just its inputs, and use a NEW `--session-dir` per model. Both Sparks can serve different candidates at once (spark1/spark2) — no swap needed if each fits one GB10.

## Watcher pattern
Poll: task folder for the deliverable + the isolated session-dir mtime; when the session goes idle (~4 min unwritten = omp -p exited/yielded) grade and write a VERDICT.json. Give a generous internal deadline; the Windows bash-job cap is 1h so relaunch the watcher if the run grinds longer.
