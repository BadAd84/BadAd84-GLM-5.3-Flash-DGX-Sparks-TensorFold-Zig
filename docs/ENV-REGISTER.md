# The env register: a verdict for every setting the engine's table carries

This repo's `scripts/env/prod.env` and `scripts/env/dev.env` list what we chose to set. They cannot, by
themselves, tell a reader which of the engine's other settings were considered, and on a newer base a
default-on clause can exist in no env file at all. This register and its gate close that gap, the way
`scripts/check-env.py` closes the "is every name we set actually read?" gap.

## The failure it comes from

On the Qwen3.8 Flash Next serve (same engine family tree, `flashnext` scope), upstream added
`shared_stop = 0.6` on 2026-11-10: beside another open stream a greedy chain's draft stops below 0.6
confidence. The setting appears in no env file, and the production engine predates the clause, so
production drafted 3.03 tokens a round while the dev stack drafted 1.92. The difference read as an
engine gap; depth and confidence arms chased it; the cause was a base default nobody had looked at.
Turning the switch off was worth 7 to 11 percent at 2 to 8 streams and closed 54 percent of a prose
throughput gap. Record: Qwen3.8-Flash-Next `work/ProseDraft/RESULT.md`.

## What the register is

The engine's own table, `zig/src/platform/environment.zig`, is the authoritative list. Every row whose
scope this serve reads (`glm`, `cuda`, `common`) must hold one of four verdicts:

| verdict | where | meaning |
|---|---|---|
| carried | `scripts/env/dev.env` | we set it; `check-env.py` already proves the served tree reads it |
| default-ok | `scripts/env/register.env` `# default-ok NAME:` | we keep the engine default, measured level or better, evidence cited |
| debt | `scripts/env/register.env` `# debt NAME:` | unmeasured on this stack: counted, each one a lead |
| unreachable | `scripts/env/register.env` `# unreachable NAME:` | the path cannot run on this serve, with the reason |

SILENT (no verdict) fails. STALE (a verdict for a setting the table no longer has) fails. Debt is
counted and printed on every run; it is a worklist, not permission.

## How it sits beside check-env.py

`scripts/check-env.py --tree` answers "is every name we set read in the tree the series makes?", which
catches a retired patch's leftover line and a name the engine no longer reads. The register answers the
opposite question, "is every setting the engine carries decided?", which catches a default inherited
without anyone looking. A name read through a raw `getenv` with no table row is invisible to the
register by construction and is `check-env.py`'s business; upstream treats an unregistered read as a
finding of its own, and the registry patch (`patches/engine/0004-ovn-knob-registry.patch` and its
successors) is where a name graduates into the table.

## Files and procedure

- `scripts/env/check-env-coverage.py`: the gate. Reads the table field by field, so a row carrying an
  optional field cannot hide from it.
- `scripts/env/update-env-register.py`: run at every re-seat and after every patch that adds a registry
  row. Keeps every verdict and appends `debt` for each new row.
- `scripts/env/register.env`: the register. Generated against TensorFold `v1.2.9` (the pin the gate
  notes name): 33 settings in scope, 0 carried there, 33 debt, 0 silent. The series' patches add rows,
  so the applied tree's count is higher; refresh against it.

Commands, with the tree the series makes (pin plus `patches/engine`, extracted on the gate host):

    python scripts/env/update-env-register.py --table <tree>/zig/src/platform/environment.zig \
      --dev scripts/env/dev.env --register scripts/env/register.env --scopes glm,cuda,common \
      --carried-pattern '^([A-Za-z_][A-Za-z0-9_]*)=([^\s]*)$' --source "<pin> + patches" \
      --evidence docs/ENV-REGISTER.md
    python scripts/env/check-env-coverage.py --table <tree>/zig/src/platform/environment.zig \
      --dev scripts/env/dev.env --register scripts/env/register.env --scopes glm,cuda,common \
      --carried-pattern '^([A-Za-z_][A-Za-z0-9_]*)=([^\s]*)$'

Then classify what the refresh appended: a measured row in `docs/KNOBS.md` makes it `default-ok` (or
moves the setting into `dev.env` as a candidate, with its cells, per the promotion rule), a path this
serve never runs makes it `unreachable`, and the rest stays `debt` and is the candidate list for the
next queue.

## Honest limits

- The register judges names, not values: it proves every setting was considered, not that a carried
  value still beats the default today. `docs/KNOBS.md` and the queue rows remain that record.
- `--strict-carried` is not used on this repo yet: at `v1.2.9` many names we set are read through a raw
  `getenv` without a table row, which is `check-env.py`'s rule 5, not this gate's. Use the strict flag
  once the pin registers every name the serve sets.
- The committed register is generated against the pin, not the applied tree. The first refresh against
  the series' tree is the run that matters and will grow the list.
