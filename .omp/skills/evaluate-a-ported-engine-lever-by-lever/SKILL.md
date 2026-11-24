---
name: evaluate-a-ported-engine-lever-by-lever
description: "Evaluate a ported engine's knobs and patches against a production target serve one at a time, with a warm baseline, A/B/A confirmation, and stacked micro-gains; covers the Spark serve gotchas that silently invalidate cells."
---

# Evaluate a ported engine lever by lever

Use when a rebuilt or ported engine serve is behind a production stack and you must prove which knobs and patches actually pay, rather than porting more blindly.

## Protocol

1. Fix the cell shape: same checkpoint, KV format, context, stream counts (C=1 and the everyday peak), one decode pass plus the reply digests, a fresh boot per cell. Record everything the launch sets; the container's own env and `Created` time are the proof, not wall-clock guesses.
2. Defeat the cold-boot confound: the first boot after idle is 1.4-2.0% slow on code and 5.5-6.0% on prose because the tables page from disk. Run a DISCARDED warm-up arm, then the baseline, then the arms, then the baseline again. The closing baseline is the reference.
3. Confirm every candidate A/B/A: arm, baseline, arm. A delta that survives the repeat and is outside noise is real; anything inside +/-0.3% is inert, so say so and move on.
4. Classify the levers before measuring: knob-gated ones flip at runtime with no build; code-only ones need `full series minus that patch`, and if a patch does not compile without its neighbours, that IS the verdict (it cannot be dropped).
5. Use boot-only probes for suspicious code paths: switches that disable a tile, a fused read-out or a tiling threshold (for example `READOUT_ROWS=0`, `FACT_ROWS=0`, `WINDOW_CHECK=0`) cost one boot each and often rule out a whole class in minutes.
6. Stack the survivors: individual 0-2% gains add up (measured: four together, +3.1% on code at both C=1 and C=4, twice, replies 6/6 identical). Measure the stack as one arm, ABBA, then record it in a single serve-env file with the reason for each entry.
7. Price the big architecture levers explicitly (drafting on versus off, for example) so nobody tunes what must be protected.

## Gotchas that invalidate results

- The drafting switch is usually a launcher env that passes a CLI flag (`DRAFTS=0` becomes `--no-drafts`), not the `TF_*` knobs that tune the chain. Two 'drafts off' arms that change nothing mean you found the wrong switch, not that drafting is free.
- A host-memory precheck can refuse a boot the device budget would allow (`MEM_CHECK=0`), and a killed launcher leaves a start lock that makes every later boot fail with 'another ./start.sh is already running' while probes report connection refused.
- An older production image usually cannot be booted by a newer recipe, because its binary predates an argument the recipe now passes. The launcher errors out and the cell silently measures the already-running container, so verify the boot happened.
- Serialise builds and measurement windows: a docker or zig build during an arm perturbs the numbers.
- Restore the production serve from an EXIT trap so a failed run cannot leave the box serving an experiment.

## Recording

One table per batch: arm, each cell, delta versus the warm baseline, reply digests, verdict (keep, drop, modify or inert). Put the surviving set in one serve-env script with a comment per entry quoting its measured delta, and keep the raw cells on the box with the driver scripts in the repo.
