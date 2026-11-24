---
name: benchmark-served-model-re-fairly
description: "Fairly benchmark a served LLM's reverse-engineering capability (DGX-Spark or any OpenAI-compatible endpoint) with an agentic, byte-exact, identical-harness protocol - covering the with-oracle vs self-bootstrap distinction and the harness-fairness traps that repeatedly produce false capability fails. Use when comparing candidate RE/agent models (Qwen/GLM/DSV4/etc.)."
---

# Benchmark a served model's RE capability FAIRLY (agentic, byte-exact, identical harness)

The make-or-break test of a candidate RE/agent model is AGENTIC and graded byte-exact against an OWNED
oracle on FRESH inputs - never a one-shot probe, never self-report. This session (2026-09-05) proved the
bigger risk is an UNFAIR HARNESS producing a false "fail": five times "the model can't do X" was really a
broken/mismatched harness. Run every model on the IDENTICAL fair harness before concluding anything.

## Harnesses (on Adam's Windows box; point at the served endpoint over LAN)
- `work/agent_re.py <base_url> <model> <recover|leitz|leitzbug|apply> [thinkoff]`
  Agentic loop (python tool -> execute/observe/reassess, 40-turn cap), graded on held-out pairs by
  `hybrid_bench.py`'s owned graders. Tasks = learn/recover-from-pairs.
- `work/agent_mtm.py <base_url> <model> <probe|nobench> [thinkoff]`
  Agentic DERIVE-FROM-BINARY of the MTM builder @0x4026a0 in MTM_Activator.exe. `probe` mode gives a
  ground-truth `real_build()` to validate against (matches how we normally work); `nobench` gives NO
  oracle - the model must build its OWN Unicorn harness (SELF-BOOTSTRAP). Grades the final pure-Python
  `build()` byte-exact vs the real Unicorn oracle on 250 fresh inputs.
- Grader/oracle: `hybrid_bench.py` (vast_bench), `MitutoyoServiceHasp/src/mtm/activator/re/oracle.py`.
- Run each via the `hub` process manager (op:start, ready-log `AGENTIC ...`, wait for=exit) - reliable on
  Windows; do NOT use `subprocess.DETACHED_PROCESS`/msys `python3` (PATH + detach traps waste iterations).

## The fairness checklist (do ALL before scoring a fail)
1. **thinkoff is MANDATORY for reasoning models.** GLM-5.3-Flash with thinking ON returns `content:null`
   (everything in `reasoning`), bogs in giant single generations, and BREAKS tool-calling (hermes shows
   "API call failed / Connection error"). Pass `chat_template_kwargs={"enable_thinking":false}`. Qwen runs
   clean by default. Symptom of thinking-on bog: session msgcount frozen for many minutes, tokens still
   generating.
2. **Identical turn cap for all models.** A 15-turn cap truncated GLM mid-analysis -> false "None/no keygen"
   which became 8/8 at cap=40. Use a generous cap (>=40); never conclude fail if it hit the cap while
   progressing.
3. **Give the same VALIDATION PATH to every model.** A model failing because it couldn't build its own
   emulation harness (INV/UC_ERR mapping loop) is NOT the same as failing the RE - provide a working probe
   (the crackme-VM / oracle-harness we always have in real work) and re-test. Distinguish two verdicts:
   (a) byte-exact RE WITH an oracle provided, and (b) SELF-BOOTSTRAP (build its own oracle, no probe).
4. **Grade independently, never trust self-report.** A model self-claimed 90/90 but scored 0/250 (verified
   against its OWN wrong-convention harness - circular). Grade `build()`/`keygen()` against the owned oracle
   on fresh random inputs.
5. **Anti-cheat the deliverable.** The reimplementation must be pure stdlib (hashlib/struct) - grep it for
   `unicorn|capstone|subprocess|<binary>|probe` in the CODE (docstring mentions are fine). A build() that
   imports unicorn / emulates is a cheat, not a port.
6. **Fix the environment, then re-test.** Wrong cwd, missing 32-bit libs/qemu, missing hashlib in the
   grader exec namespace, a stray old base_url in a `--profile` config or `.env` - all produced false
   fails. Fix and re-run on the fair harness.
7. **Isolate contention.** Run agents one-at-a-time (or few) - many parallel agent-subprocesses cause tool
   `[timeout]`s that look like model failure. Give a single-model capability run a dedicated endpoint.

## Result shape to report (per model)
- Speed: single-stream tok/s (memory-bound on GB10 -> tracks ACTIVE-param bytes/token, not total).
- Byte-exact RE WITH oracle: oracle-suite (recover/leitz/leitzbug/apply) + MTM-probe, each N/N.
- SELF-BOOTSTRAP (no oracle): pass/fail + whether it built its own Unicorn harness (emu_start in the log).
- Operational: does it run clean in the real harness (hermes/omp), or need thinkoff / bog.

## What we found (2026-09-05, reference)
With an oracle provided, DSV4-Flash, Qwen3.8-Flash-Next, and GLM-5.3-Flash ALL hit 250/250 byte-exact.
Self-bootstrap: DSV4 and GLM PASS (build their own oracle); Qwen FAILS (needs one provided). Speed:
Qwen ~60 > GLM ~44 > DSV4 ~41 tok/s single-stream. GLM needs thinkoff + has a DFlash2 NC-license blocker.
Full detail: `ots-infra/docs/GLM-QWEN-MEASURED-2026-09-05.md`.
