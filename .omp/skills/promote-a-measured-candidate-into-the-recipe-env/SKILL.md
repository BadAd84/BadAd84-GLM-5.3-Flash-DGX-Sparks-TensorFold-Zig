---
name: promote-a-measured-candidate-into-the-recipe-env
description: "Promoting a measured candidate setting into the recipe sections of prod.env and dev.env: the mechanical move, the two gates that must be updated, and the pitfalls measured on the GLM Zig serve"
---

# Promoting a measured candidate into a recipe env

Use when a candidate setting that passed its ladder must become part of the production recipe.

1. **The receipt first.** The five-level table with the whole current env against the recipe, two boots an arm, mirrored. The rule must have been written in the queue header before the boots: ship when not slower at any level beyond the boot spread and faster at at least one. A level slower beyond the spread is a trade for the owner.
2. **Move the lines, do not re-type them.** The candidate setting lines become recipe lines in BOTH env files, which stay byte-identical; the candidates section is emptied with a one-line note saying why. Verify with a settings-line hash on each file, not by eye.
3. **Two gates will fail and both are correct to update.**
   - `scripts/tests/test_serve_env.py`: its `ADDED` allowlist must name every promoted setting, because it compares the launcher's environment against the pre-split launcher and a promoted knob reads as drift.
   - The same file's dev-versus-prod assertion must read "dev differs from prod only by its candidates section, which may be empty". Left as "dev.env adds no candidate" it fails the moment the candidates section is empty, and weakening it to nothing would lose the guard against a stray dev-only line.
4. **Run both.** `python scripts/check-env.py` and `python scripts/tests/test_serve_env.py` (7 cases). A green pair plus the hash match is the promotion's receipt.
5. **Record what the env is worth together**, not just per knob: the whole-env five-level table, the cold readings from the ladders, and the stock comparison if one exists. A promotion with only per-knob numbers cannot be read later as a stack.

## Pitfalls measured

- A candidate is not disabled by living in the candidates section: `KNOBS=dev` applies the whole file. Arms measured on "the dev env" already contain every prior winner, so per-bundle deltas are incremental, and saying "the recipe" while meaning `KNOBS=prod` is what makes this confusing in reports.
- Do not rewrite the promotion rule after seeing rows. If a cell is unmeasurable in the configuration (for example 8 clients on `--parallel 4`, a 2:1 oversubscription with an 8 to 20% boot spread), the bundle ships on its cold evidence and the cell is recorded as a property of the configuration, or it waits for the owner.
- Keep the env files' setting lines byte-identical after promotion; a divergence there is the drift the launcher test exists to catch.
