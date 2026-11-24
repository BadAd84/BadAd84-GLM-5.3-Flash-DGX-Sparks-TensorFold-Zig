---
name: gate-a-build-on-prompt-fidelity-before-benchmarking
description: "Before trusting speed or quality numbers from a patched LLM build, prove it answers the prompt it is given at long prompt lengths against a reference build; then bisect by patch prefix when no environment switch moves it."
---

# Gate a patched inference build on prompt fidelity before believing any number

## When to use

Any time a patched or rebuilt inference stack (TensorFold/Flash Next, vLLM, any engine) is about to be scored, A/B'd against production, or have its quality measured. Especially when a score table looks far below what the same checkpoint produced on an earlier build, or when replies look like they answer a different question.

## The gate (cheap: 20 items, one boot, no scores)

1. **Reference first.** Build or reuse an image of the base build that produced the trusted numbers, and record its replies to 20 long items (1,300-1,500 prompt tokens) with the exact recorded request bodies: `temperature 0`, the recorded `max_tokens` and `stop`, thinking off as recorded. Store per item: reply text, `token_sha256`, character length, completion tokens, finish reason.
2. **Same bodies, candidate build.** Resend the identical bodies. "Identical" means the recorded body hash matches per item (check 500/500 etc.), so `max_tokens`, `stop` and prompt rendering are excluded as causes before anything else is blamed.
3. **Compare.** Count exact reply matches against the reference. A clean build reproduces the reference (measured: 20/20). A broken build matches 0/20 while matching its own wrong answers 20/20, which is what proves it is deterministic rather than flaky.
4. **Length gradient.** Repeat a handful of items at short lengths (40-60 prompt tokens). Clean at short and wrong at long is the signature of a state or layout defect that a short prompt never reaches, not of a weaker model.
5. **Stop.** Until the reference arm reproduces the old answers, do not quote speed, do not score quality, and do not compare the candidate against production. Every number measured on the broken build is void.

## Reading the symptoms

- Reply answers the prompt's own few-shot example with another example's numbers: the prompt is not being attended as sent.
- A two-token reply where the engine log says `prompt=1346 tokens=2 accepted=0/1`: the target's own argmax was garbage, so the defect is upstream of sampling.
- A quality table far below an earlier build on the same checkpoints (28.6% vs 96.4% GSM8K): treat as a build defect until the fidelity gate says otherwise. Genuine model weakness does not cut every benchmark roughly in half at once.
- A median reply length collapsing (128 chars, 34 completion tokens) is truncation or a stop sequence, and it is a different defect from this one; check request fields and `finish_reason` first.

## Bisecting when no switch moves it

The candidate set splits into switchable levers and unconditional code. Test switches first because they are free (one boot each, same image): every prompt-path setting the tree reads, each set to its off value, recording whether the answers return to the reference.

If eight switches covering the whole prompt-side surface all produce the identical wrong answers, stop toggling. The cause is unconditional code in a patch, and the instrument is a PATCH-PREFIX LADDER:

1. Controls: full series must be broken, base alone must be clean, both on the same items and the same reference.
2. Build `base + patches 0001..k` for k chosen by binary search; one image build and one boot a rung, inside the GPU lock, from verified trees.
3. Each rung records the image id, the boot's environment, and the 20-item match count.
4. When the smallest broken prefix is found, read that patch's hunks and name the mechanism, then list which other patches share the code path so the fix covers the class.

## Pitfalls

- Do not use the window's own `SANITY ok` probe as the anchor; measured: it returned `OK.` on one arm and `OK` on another, so it cannot detect this class.
- Do not accept "the bodies are identical" from a summary; check per-item body hashes across arms and against the earlier run.
- Do not compare scores across windows when the control's own repeats disagree by more than about 20% inside one window (measured: production's mid-level cells differed 21% between its own P1 and P9 repeats). A control that is not repeatable cannot anchor a ratio.
- Same-checkpoint comparisons need the same KV dtype, slot count and window; otherwise a checkpoint question and a shape question are being asked at once.
