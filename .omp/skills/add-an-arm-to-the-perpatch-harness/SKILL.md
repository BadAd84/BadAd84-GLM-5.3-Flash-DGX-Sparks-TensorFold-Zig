---
name: add-an-arm-to-the-perpatch-harness
description: "Add or verify an arm in the perpatch A/B harness on spark1-3, restart chain 5 at a valid label without corrupting waves, and run registry mutant entries without hangs."
---

# Add an arm to the perpatch A/B harness (spark1-3)

1. Edit `scripts/glm53/v110/perpatch/perpatch_run.sh`:
   - add the arm's `arm_env` branch (image or `export TF_*=value`),
   - **extend the OUTER case pattern** (`hunt|hunt?*|myarm)`) if the arm does not start with `hunt`; the inner case only runs for names that matched outside,
   - declare it in `perpatch_report.py` (ENV_ADDS / ENV_OFFS, and OVER, or `test_report_arms.py` fails on it).
2. Prove it with one real boot on spark1, never with a grep: `bash perpatch_run.sh "1" "myarm" once none` and require `== done arm=myarm` plus `RESTORED`. A grep cannot see a case-structure mistake (measured: `UNKNOWN ARM a1stock`, waves logging `0 boots`).
3. Deploy: copy to `~/perpatch/perpatch_run.sh` with a `.bak` backup, copy the `perpatch_report.py` too, and refresh `~/perpatch/hold-<wave>/` staged copies (`*.staged`) or the change never reaches a later wave.
4. Run the gates on the way in: `scripts/glm53/v110/tests/host/run_reaching.sh --mutants <changed files>` plus check-secrets / check-python / check-doc-inventory / check-bare-wait; commit with an explicit path list, never `git add -A`.

## Restarting chain 5 safely
- Pick a resume label that EXISTS in `chain_wave5.sh`; a wrong one skips every later step and logs `hunt waves ended`. Grep the label first.
- `resume5.sh <label>` refuses while a chain runs: kill the chain PID, then resume; the killed chain's in-flight run continues as an orphan and `in_flight()` makes the new chain wait for it.
- After starting, re-arm the firewall: `fw8888.sh guard <newpid> ~/perpatch/fwguard`, then `touch ~/perpatch/fwguard/on`; a run in flight at kill time restores production by its own trap.

## Running registry mutant entries
- One entry per invocation, `< /dev/null`, an outer `timeout` sized from the entry's own test; `run_registry.py` has no per-entry timeout.
- Point entries at the repo copy of a runner, not a lane copy: a drifted anchor in a second copy reports `anchor matched 0 times` and proves nothing.
