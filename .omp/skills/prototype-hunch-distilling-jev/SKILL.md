---
name: prototype-hunch-distilling-jev
description: "Prototype undrgrnd-labs/hunch (EmbeddingGemma2 CPU reflex layer) on our own traces with OTS Jev as teacher: build eg2cpu, wire the Jev teacher shim, measure distillation honestly"
---

# Prototyping hunch (local CPU reflex layer) distilling OTS Jev

`undrgrnd-labs/hunch` (Apache-2.0) is a "System One" reflex layer: a tiny per-question student over EmbeddingGemma2 embeddings that learns a teacher's answers and takes over on CPU in ~tens of ms. It sits in front of a teacher (Jev/Clef/LLM), escalates the uncertain ones, and keeps auditing. Use this to evaluate it on OUR workload before any adoption.

## When it fits (from hunch's own docs/question-design.md)
- GOOD: unit-level text-property questions - "did this tool call fail?", "is this a prompt injection?", "what kind of output is this?". Answer must be readable in the unit's text (<=1024 tokens, head+tail kept).
- BAD: trace-shaped or reasoning questions - "did the agent yield with work to do (unless blocked on hardware/credential/owner)?". hunch's pre-flight returns BACKEND-ONLY; these stay with the teacher. Our `fold-advisories-into-work` is this class - do NOT prototype hunch on it.
- Rare positives (<~6%) never graduate symmetrically; always-"no" scores ~94% so report AUC + recall + bootstrap CI, never bare accuracy.

## Build (local Windows laptop, x86_64; NOT the Sparks - owner directed)
- Prereqs present: rustc >=1.88, cargo, uv. `git clone --depth 1 https://github.com/undrgrnd-labs/hunch` into a repo's `work/`.
- `uv sync --all-packages` - builds the Rust `eg2cpu` native extension (`_eg2cpu.cp312-win_amd64.pyd`) during sync (~3 min). Verify: `uv run --package eg2cpu python -c "from eg2cpu import Model, decisions"`.
- Model: `cd examples && uv run download.py embeddinggemma-2 --yes` (1.4 GB, Apache-2.0, ungated).
- GOTCHA: `eg2cpu.Model()` fails to find the HF-cache model (relative-path bug). Pass the snapshot dir explicitly: `EG2_MODEL_DIR="C:/Users/Adam/.cache/huggingface/hub/models--google--embeddinggemma-2/snapshots/<rev>"`.

## Decision spec shape
A boolean decision learns its DIRECTION from hand-written `contrasts` (matched `{call, yes, no}` pairs - the semantic anchor) and sets its THRESHOLD from `calibration` (teacher-labeled domain rows). "no contrasts" SpecError = you gave only calibration/hard_negatives. You must write a few contrast pairs per question.
- Predict API: `model.apply([decision.handle], [spans])` -> per-span `{p, status}` where status is answer/escalate/abstain. NOT `handle(texts)`.

## Wiring OTS Jev as the teacher (the "escalate to Jev" path)
- Jev lives on CT105 ots-jev at `192.168.99.105:8888/v1/systemone` - NOT spark1:8888 (that is the GLM serve).
- systemone contract: POST `{state, questions:{name:{type:"noul"|"choice"|"score", instructions:"..."}}}` -> `{answers:{name:{type, noul:0.xx}}}`. Field is `instructions` not `question` (wrong field -> HTTP 422).
- hunch's teacher contract (examples/teacher_openrouter.py): HTTP endpoint taking `{state, questions}` returning `{answers:{name: p_yes}}`. Write a ~60-line shim translating between them (saved as `jev_teacher.py` in the hunch work tree). Point hunch's `TEACHER_URL` at it.

## Measured on our data (2026-10-29, baseline, small-sample)
- tool_call_failed (teacher=harness isError flag, the repo's own method, FREE - do not use Jev here): AUC 0.80 [0.75,0.86], recall 0.40, precision 0.87, ~90 ms/unit laptop CPU. Good cheap triage, misses 60% of failures - not a sole detector.
- blocking-judgment distilled from Jev (250 Jev labels, 110s, ~250 calls negligible): student-vs-Jev AUC 0.83 [0.72,0.94], 93% agreement, 85 ms local vs Jev ~320 ms. Proves local distillation of Jev works per-question.
- Report honestly: lead with AUC+CI, give recall on the positive class, quote the MEASURED laptop latency (not the README's 22 ms Apple-M5-batched figure), flag small-sample CIs.
