---
name: restart-a-perpatch-chain-safely
description: "Restart or resume the GLM per-patch A/B chain (chain_wave5.sh on spark1) without silently skipping waves; verify labels and arms by execution, not grep."
---

# Restarting chain 5 safely

The per-patch chain is a linear script: every step is guarded by `skip <label>`, and `resume5.sh <label>` sets START to that label. Two failure modes cost an entire night's schedule once; both are silent.

## 1. The resume label must equal a `skip` label that will be reached

```
# on the laptop, before every restart:
grep -n 'skip [a-z0-9]*' scripts/glm53/v110/perpatch/chain_wave5.sh | cut -c1-90
```
`mb` is not a label: the mb waves are `mb4`, `mb2`, `mb8`, `mb1`, `mb6`. Resuming at a label that does not exist leaves START set through the whole script, so every step logs `skipped (resume at X)` and the chain ends in seconds having run nothing. The tell is a chain log whose tail is `skipped` lines followed by `hunt waves ended`.

Also pick the NEXT not-yet-started step: a step already running continues as an orphan (the new chain's `in_flight` waits for its `perpatch_run.sh`), and if you name the step that is in flight it would run twice.

## 2. Prove an arm by booting it, never by grep

`arm_env` is a nested case: the outer pattern decides which arm names ever reach the inner labels. `a1stock` was added to the inner table and still refused every wave with `UNKNOWN ARM` because the outer pattern was `hunt|hunt?*`. One grep of the file cannot see this.

```
ssh spark1 'cd ~/perpatch && timeout 700 bash perpatch_run.sh "1" "<arm>" once none' \
  | grep -E '== done arm|UNKNOWN|refused|RESTORED'
```
That boot is the receipt (`== done arm=<arm> level=1`, then production restored). Cheap: one boot, no probes.

## 3. Deploy and verify the whole harness, not one file

```
for f in chain_wave5.sh perpatch_run.sh perpatch_report.py perpatch_extra.py hygiene_nodes.sh prodbench_report.py; do
  a=$(git show HEAD:scripts/glm53/v110/perpatch/$f | tr -d '\r' | sha256sum | cut -c1-12)
  b=$(ssh spark1 "sha256sum ~/perpatch/$f" | cut -c1-12)
  c=$(ssh spark1 "sha256sum ~/perpatch/hold-8cc4/$f.staged 2>/dev/null" | cut -c1-12)
  echo "$f $a $b $c"
done
```
Live and staged copies must equal HEAD, or a later `wave()` install resurrects a stale file mid-run. Wave runs install `$D/*.staged` then `$D/hold-<wave>/*.staged`, so a hold folder must carry the SAME version as the live tree once its fixes are deployed.

## 4. Restart sequence (firewall included)

```
scp chain_wave5.sh spark1:perpatch/chain_wave5.sh.tmp        # the file is swapped in by resume5.sh
scp resume5.sh spark1:work/hunt-deploy/resume5.sh
P=$(ssh spark1 'pgrep -f "perpatch/chain_wave[5].sh"'); ssh spark1 "kill $P"
ssh spark1 "bash ~/work/hunt-deploy/resume5.sh <label>"
NP=$(ssh spark1 'pgrep -f "perpatch/chain_wave[5].sh"')
ssh spark1 'rm -f ~/perpatch/fwguard/{on,is-on,is-off}'
ssh -A -tt spark1 "sudo bash /home/adam/fw8888.sh guard $NP /home/adam/perpatch/fwguard"
ssh spark1 'touch ~/perpatch/fwguard/on; tail -2 ~/perpatch/chain5.log'
```
Killing the chain leaves any `perpatch_run.sh` boot running as an orphan on purpose (the new chain waits for it); killing the boot as well is only for a deliberate abort. `serve_down`/`serve_back` set and clear their own EXIT trap, so a kill during a normal wave does not restart production under a running measurement.

## 5. After the restart, read the log

`tail -3 chain5.log` must show the step you intended starting (`wave <label>: ... running`), not a run of `skipped` lines. A watcher keyed on a wave's end line dies with a killed chain: re-key it on the next wave's start, or on `^PERPATCH DONE` in that wave's own log.
