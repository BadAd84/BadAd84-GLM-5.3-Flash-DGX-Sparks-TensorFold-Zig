# The env register: every row of the engine's table, set, and one verdict each

This repo's `scripts/env/prod.env` and `scripts/env/dev.env` set every row of the engine's own settings table,
`zig/src/platform/environment.zig`, whose scope this serve reads (`glm`, `cuda`, `common`). `scripts/env/register.env`
records one verdict per row. That is the whole model (owner 2026-11-23): **no setting is left unset**, and the only
question left about a row is whether its value was measured or is debt.

The rule replaced the earlier four-verdict register (`carried`, `default-ok`, `debt`, `unreachable`) because
`default-ok` meant "we keep the engine default and no env file holds a line for it", which is exactly how a default
inherits itself into a serve unnoticed. `default-ok` no longer exists; `unreachable` is gone too, because a row is
now always set (a row this serve's family never reads is set to its default like any other, and its verdict says so).

## The failure it comes from

On the Qwen3.8 Flash Next serve (same engine family tree, `flashnext` scope), upstream added `shared_stop = 0.6` on
2026-11-10: beside another open stream a greedy chain's draft stops below 0.6 confidence. The setting appeared in no
env file and the production engine predated the clause, so production drafted 3.03 tokens a round while the dev stack
drafted 1.92. The difference read as an engine gap; depth and confidence arms chased it; the cause was a base default
nobody had looked at. Turning the switch off was worth 7 to 11 percent at 2 to 8 streams and closed 54 percent of a
prose throughput gap. Record: Qwen3.8-Flash-Next `work/ProseDraft/RESULT.md`.

## What the register is

| verdict | meaning |
|---|---|
| `measured NAME=VALUE` | a measurement chose it: its cells are in `docs/KNOBS.md` (and the OVERNIGHT section that file names), or it was verified equal to the engine's own computed answer |
| `inert NAME=VALUE` | examined, and it cannot be a lever on this serve: a log or receipt switch, a limit of a path this serve never runs (vision, PDF, another family), or plumbing. The reason on the line is the record, and it is what stops the row being re-opened as a question |
| `debt NAME=VALUE` | set to the engine's own default and not measured on this stack; each one is a lead |
| `candidate NAME=VALUE` | `dev.env`'s candidates section overrides the value `prod.env` keeps at the engine's default (or names a setting prod does not carry); the value must be `dev.env`'s, and the overridden row must be a completeness-block line |

Both row verdicts sit on a line the env files hold; the value in the verdict must equal the value in both files. A row
with no verdict, a verdict for a row the table no longer has, a verdict whose value differs from the files, a duplicate
verdict, and the retired words `default-ok` / `unreachable` all fail the gate. A candidate is the one way `dev.env`
differs from `prod.env` in the recipe: `serve.sh` applies the recipe and then the candidates, so the later `-e` is what a
`KNOBS=dev` boot runs (D4/D5), and `scripts/check-env.py` grew that rule with this change.

`scripts/env/register.env` also carries `raw NAME=VALUE` lines for every name our env files set that the table has no
row for: they are read through a raw `getenv`, which `scripts/check-env.py` rule 5 covers. A table row is the ideal for
each (D9 below), and the gate fails on a name set with neither a row nor a raw line.

## A blank value is a decision

Some rows have no value to write: the engine's default is "no value" (no dump file, no captured kernel set, no HIP
limit, no operator key file, no max), or the launcher computes the value per boot (`TF_GLM_RANK`, `TF_GLM_WORLD`,
`TENSORFOLD_MEMORY_RESERVE_GIB`). Those lines exist in both env files with **an empty value**, and `serve.sh` does not
pass a blank line, so the engine sees the setting absent exactly as the row documents. The alternative, `-e NAME=`, is
a present empty setting and would also override the rank, world and memory reserve the launcher computes. 16 of the 101
rows are blank for this reason and each says why in its register line.

## The gate

    python scripts/env/check-env-coverage.py --table <tree>/zig/src/platform/environment.zig \
        --prod scripts/env/prod.env --dev scripts/env/dev.env --register scripts/env/register.env \
        --scopes glm,cuda,common

One clean run prints a line of the form `coverage: 85 rows in scope, set 85, measured 55, inert 25, debt 5, raw 6,
candidates 0, unset 0, unrecorded 0`; the register's own counts are authoritative for that line, and the gate reruns it
from the tree it is given. The gate's own
test, `python scripts/tests/test_check_env_coverage.py`, holds one defect class a case on a fixture table and fixture env files (sixteen
tests: clean, UNSET, VALUE, the retired word, REFUSED, BLANK, the three candidate rules, UNREAD, STALE, and inert counted
and inert without a citation). Proven to fail on copies of
the real files too: a row deleted from `prod.env` (`UNSET`), a register value changed
(`VALUE`), a verdict renamed `default-ok` (retired word + `UNRECORDED`), a line for a row the table lacks (`STALE`), and
a `raw` line removed (`UNREAD`), a candidate line whose value differs from `dev.env` (`VALUE candidate`), a candidate
overriding a measured recipe line (`CANDIDATE`) and a candidates line with no `candidate` record (`UNRECORDED candidate`).

The rule that ties it to a rebase (D7): a base that adds a table row is a hard stop. The gate fails until a value is
chosen, written into both env files and given a verdict; there is no generator that appends debt for you, because a
chosen value is the decision the gate exists to force. `scripts/env/update-env-register.py` was deleted with the old
model: it only knew how to append the absent.

## The applied tree this register is against

TensorFold `fa13df5dd1fdd23ada775510a464c9aa03a39e09` plus, in their recorded order, `patches/engine` (32),
`patches/pr1411` (2), `patches/cache-salt` (2), `patches/learn-starts` (1), `patches/solo-cuts` (1),
`patches/disk-any-position` (1), `patches/restore-held` (1) and `patches/port-multi-fill` (1): **41 patches,
101 in-scope table rows for 101 names**, stack tree `fe60f611502a`.
The register was read field by field from `zig/src/platform/environment.zig` in the tree that stack makes, and each
default from the row's own reader in that tree (the `default` its `environment.read`/`value` call passes, its
`ovn.int`/`ovn.on` default, or for a path/null row the absent case itself), never from memory of an older base. To
rebuild the tree without compiling:

    git -C <upstream clone> archive fa13df5dd1fdd23ada775510a464c9aa03a39e09 | tar -x -C <dir>
    cd <dir> && git init -q .
    for pkg in engine pr1411 cache-salt learn-starts solo-cuts disk-any-position restore-held port-multi-fill; do
      for p in <repo>/patches/$pkg/*.patch; do git apply --check "$p" && git apply "$p"; done
    done

Examples of the derivations that are not a bare number in the row's `forms`: `TF_CACHE_EVICT`'s reader falls back to
`main`; `TENSORFOLD_RESTORE_PREFETCH`/`_GIB`/`_MS` to 2 reads, 16 GiB and 30 s (`core/rows_prefetch.zig`'s `Limits`);
`TENSORFOLD_PRESSURE_CACHE_PERCENT` to 50; `TF_QMMF_HALF_BELOW` to 96; `TF_HY4_MEM_FLOOR_GIB` to 10;
`TF_MTP_DRAFTS` to `cuda_mtp.zig`'s `default_depth` 3; `TF_DRAFT_NODES` to `draft_tree.zig`'s `default_nodes` 15;
`TENSORFOLD_MAX_PDF_PAGES` to 16 (still capped by `--vision-max-images`); `TF_GLM_PROMPT_MANY` and
`TF_GLM_OVN_MULTI_FILL` to 0 (the multi-fill package's `environment.value(..., false)` and `ovn.on`); `TF_ROCE_GID_INDEX` to 3, the index the
engine's own table search picks on all four HCAs of spark1 (probed: each HCA's `gid_attrs/types/3` is `RoCE v2` and its
GID is the IPv4-mapped form), so the value is the search's own answer rather than a second opinion.

## Findings that produced this model

1. **The duplicate row (D8), fixed 2026-11-23.** `TF_GLM_OVN_SOLO_TO_START` was added twice: once by
   `patches/solo-cuts/0001` (line 609 of the patch) and again by `0002` (line 71), with the same duplicated in that
   family's documentation table, so the applied tree carried 100 rows for 99 names. `0002` turned out to be nothing but
   that duplication (after the 2026-11-21 re-seat its only hunks were those two rows), so it was withdrawn; the package
   is now `0001` alone. `patches/restore-held/0001`, written on top of the duplicate, had that second row as a context
   line in two hunks; the context lines and their header counts were repaired and its `SHA256SUMS` regenerated. The
   `port-multi-fill` package, landed on the stack the same day, needed one context line of its own (`cuda_native.zig`'s
   `release(own);`, added by `restore-held`) and nothing else. Both packages' `SHA256SUMS` verify
   (`scripts/check-patch-packages.sh` CLEAN); the 41-patch stack (engine series + seven packages) applies cleanly and is
   gated on the gate host. The first run, `sg-20261123-112522`, failed on nine lean findings the port-multi-fill package
   carried (multi-line comments and `cuda_lanes.zig` at 605 lines); they were fixed with the behaviour unchanged
   (`patches/port-multi-fill/RECORD.md`), and the re-run is `sg-20261123-120611`, whose verdict is the run log's
   `VERDICT` line.
2. **Six names with no table row (D9).** `TF_GLM_CHUNK_SOLO`, `TF_GLM_DENSE_BITS`, `TF_GLM_HEAD_BITS`,
   `TF_GLM_KDA_PAD`, `TF_GLM_OVERLAP_PIECES` and `TENSORFOLD_NO_UPDATE_CHECK` are read through a raw `getenv`
   (`zig/src/families/glm/cuda_ranks.zig`, `cuda_kda_block.zig`, `zig/src/server/benchmark_server.zig`). They are `raw`
   lines in the register with their reader named; a table row is the ideal for each, and one arriving is a rebase that
   moves the line to a verdict.
3. **Debt is 69 rows**, the worklist in `register.env`. A debt row is set, boots as its default and is counted; it
   becomes `measured` only when a cell exists, which for a speed knob means the five-level rule in `docs/KNOBS.md`.

## Honest limits

- The register judges every row's VALUE and presence, not that a carried value still beats its default today: the
  cells in `docs/KNOBS.md` are that record, and a row whose cells are superseded goes back to `debt` in the same commit
  that says so.
- `measured` includes a value verified against the engine's own computation (`TF_ROCE_GID_INDEX`); it does not claim a
  speed measurement where none was run.
- The register is against the applied tree named above. Any patch that adds or renames a registry row, or a re-seat,
  needs a new read of the table: the gate fails until it happens, which is the point.

One carried candidate's cells need their carrier named: `TF_GLM_PROMPT_MANY=1` was measured on the mf1 image, which carries
`patches/port-multi-fill` - the package's own ladder. Its switch came from the standalone `patches/port-prompt-many`, which cannot
stack with that package, so the +1.55 / +5.45 / +2.96% are the carrier's numbers and not the old package's. A later stack that
carries the switch another way needs its own cells.

### The env of record, in numbers

`prod.env` and `dev.env` carry the same 118 settings, and the register gives every table row one of 55 `measured`,
25 `inert` and 5 `debt` verdicts (plus the raw and launcher names). The `measured` lines name their cells,
the `inert` lines name the reason they can never be a lever here, and the `debt` lines are the whole of what a boot
could still move: `TENSORFOLD_PROMPT_CACHE_KEEP_OTHERS`, `TF_PROMPT_INTERMEDIATE`, `TF_GLM_DSCORES`, `TF_GLM_OVN_KVB8`, `TF_GLM_OVN_DISK_SLICE_MIB`.

What none of that claims:

- **`inert` is an argument, not a measurement.** Each one says why the row cannot move a chat cell on this serve; a new
  model family or a new serving path can turn an inert row into a real one, and then it is re-examined.
- **The values were measured one at a time**, against the others as they stood. No arm has run the whole set as a block,
  so an interaction between two measured winners is untested until the dev union is measured as a combination.
- **The launcher is part of the env.** `LEARN` (the NVMe tier) is promoted to a default in `serve.sh` and the driver that
  forwards it, and its long-context cells are the open item; the short-prompt cells are flat against the tier-off control.
- **A setting our env sets that the binary does not carry is silently ignored.** `scripts/check-env-in-image.py` reports
  them per image; eight were found against `m130a`, two of them real (a package that image does not carry) and the rest
  to confirm one by one.

See `docs/DOC-AUDIT-2026-11-23.md` for the documentation pass that removed the statements contradicting this model.
