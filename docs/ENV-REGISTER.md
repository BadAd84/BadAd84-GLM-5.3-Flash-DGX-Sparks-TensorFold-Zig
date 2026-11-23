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
- `scripts/env/register.env`: the register. Generated against the series' APPLIED tree: TensorFold
  `fa13df5dd` plus the seven packages in their recorded order (engine, pr1411, cache-salt, learn-starts,
  solo-cuts, disk-any-position, restore-held; 41 patches, every one applied with `git apply`, 0
  failures). In scope: 100 table rows for 99 names (see the duplicate below), 29 carried, 70 debt, 0
  silent.

## Findings from the first applied-tree run

1. **A duplicated setting row, which the series must fix.** `TF_GLM_OVN_SOLO_TO_START` is added
   TWICE, identically, once by `patches/solo-cuts/0001-glm-solo-between-starts.patch` (line 609 of the
   patch, the `environment.zig` hunk) and again by `patches/solo-cuts/0002-glm-solo-to-start.patch`
   (line 71), and the same duplication appears in that family's documentation table. The applied tree
   therefore carries 100 rows for 99 names, so any census that counts rows overstates the settings by
   one. Measured on a scratch apply of the whole series, counting the row after each step: 0 rows after
   the four packages before solo-cuts, 1 after `solo-cuts/0001`, 2 after `solo-cuts/0002`, so the later
   patch is the duplicate. The fix is: remove the duplicate doc row and registry row from
   `solo-cuts/0002`, regenerate the package's `SHA256SUMS`, re-run the stack gates (`spark-gates.py`),
   and refresh this register. This register needs no edit after the fix; only its printed row count
   changes, 100 to 99.
2. **Six carried names are not in the table**, so this gate cannot judge them: `TF_GLM_CHUNK_SOLO`,
   `TF_GLM_DENSE_BITS`, `TF_GLM_HEAD_BITS`, `TF_GLM_KDA_PAD`, `TF_GLM_OVERLAP_PIECES` and
   `TENSORFOLD_NO_UPDATE_CHECK`. Each is either registered by a patch that should have added a row, or
   is a raw `getenv` read that `check-env.py` rule 5 covers; decide which per name and record the
   verdict here.
3. **Debt is 70 settings**, the list in `register.env`. Each needs a row in `docs/KNOBS.md` (promote it
   into `dev.env` as a candidate with its cells), a measured `default-ok`, or an `unreachable` reason.
   Nothing was measured to generate this run; the register only records what exists.

### Rebuilding the applied tree without compiling

    git -C <upstream clone> archive fa13df5dd1fdd23ada775510a464c9aa03a39e09 | tar -x -C <dir>
    cd <dir> && git init -q .
    for pkg in engine pr1411 cache-salt learn-starts solo-cuts disk-any-position restore-held; do
      for p in <repo>/patches/$pkg/*.patch; do git apply --check "$p" && git apply "$p"; done
    done

`patches/*/apply.sh` does the same through a temporary index and prints the tree id the package makes,
which is the check to quote when a stack is re-seated.

Then classify what the refresh appended: a measured row in `docs/KNOBS.md` makes it `default-ok` (or
moves the setting into `dev.env` as a candidate, with its cells, per the promotion rule), a path this
serve never runs makes it `unreachable`, and the rest stays `debt` and is the candidate list for the
next queue.

## Honest limits

- The register judges names, not values: it proves every setting was considered, not that a carried
  value still beats the default today. `docs/KNOBS.md` and the queue rows remain that record.
- `--strict-carried` is not used on this repo yet: even in the applied tree six names we set are read
  through a raw `getenv` without a table row, which is `check-env.py`'s rule 5, not this gate's. Turn
  the strict flag on once those six are registered or recorded.
- The committed register is generated against the applied tree of `fa13df5dd` plus the seven packages.
  A re-seat, or any patch that adds or renames a registry row, needs `update-env-register.py` before
  this file can be quoted as current.
