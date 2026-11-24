---
name: prove-a-serves-env-of-record-is-delivered
description: "When an env file claims to be a serve's environment of record (promotion, restore, drift): prove every stated name is deliverable and arrived, not merely written."
---

# Prove a serve's env of record is delivered

An env file is a claim about what the running container gets. Three independent failures hide in it, each with its own proof.

## 1. Deliverability: can the launcher carry the name at all?

The launcher's forward filter decides. In the MiaAI-Lab TensorFold recipe, `start.sh` passes only `^(TENSORFOLD|TF_FLASHNEXT)_[A-Z0-9_]+=`, while the engine's own table (`zig/src/platform/environment.zig`) declares settings with the bare `TF_` prefix too. A stated value for one of those never reaches `docker run`.

- Run the repo's coverage gate with the launcher's own filter (`--passes '^(TENSORFOLD|TF_FLASHNEXT)_'`). `PASSAGE-LOST` lines are the undeliverable names; the gate must exit non-zero on them, never downgrade to advisory.
- Do not silence it by deleting the lines. The repair is the launcher filter (see `upstream/recipe-launcher-tf-env/`), recorded as unmeasured until steps 2 and 3 pass.

## 2. Absence equality: is the stated value the same as not setting it?

Widening the filter DELIVERS values that never arrived. If any differs from the engine's absence default, the serve changes.

- For each name, find the reader (`grep -rn '"NAME"' zig/src`) and read its absence path (`get(...) orelse X`, a clamp, a `flags.*` override).
- Classify EQUAL (textually the default), DERIVED (runtime value; state what explicit does), INERT (no reader in the served family), DIFFERS (changes the serve).
- `DIFFERS` or undecidable: either `unset NAME` or state the absence value explicitly. Produce the change as a diff, not an edit, while another lane owns the file.

## 3. Arrival: did the container actually get them?

- Boot once with the file sourced exactly as the launcher takes it (`set -a; . file; set +a`) and the real start script.
- Compare `docker inspect <container> --format '{{json .Config.Env}}'` to the file: forwarded names equal, `unset` names absent, and nothing present that the file does not explain.
- Guard the identity: every GPU window reuses the production container name, so first prove the image is the pinned production image. Compare only then; a window's env read as production drift is a false alarm (observed: 122 vs 54 names, 69 false problems).
- Behaviour identity: window self-check line, and fixed-prompt replies vs the un-widened boot on the same image.

## Reporting

State the counts, not adjectives: `carried N equal, M differ, K absent`, `levers X of Y at served values`, and for each unreachable name the class and the line that decides it. A red gate on undeliverable names is the honest state; say what turns it green.
