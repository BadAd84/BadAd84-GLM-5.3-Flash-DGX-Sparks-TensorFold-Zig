---
name: restart-glm-chain-5-safely-midrun
description: "Use when restarting or resuming chain_wave5.sh on spark1 (per-patch A/B chain): pick an existing label, check the installed harness has the arms, re-arm the firewall guard, verify the first step"
---

# Restart chain 5 on spark1 safely, mid-run

The chain (`~/perpatch/chain_wave5.sh`, driven by `~/work/hunt-deploy/resume5.sh`) is a linear script with labelled
steps. A restart kills the chain bash and starts a fresh one at a label; the per-patch run in flight carries on as an
orphan and the new chain's `in_flight()` waits for it (`perpatch_run.sh`, `chain_confirm.sh`, the marker
`/tmp/perpatch-in-progress`, `gb10_a1.sh`, `gb10_gpu_tests.sh`).

## Before you kill

1. **Pick a label that EXISTS.** List them: `grep -nE '^ *wave [a-z0-9]+|skip [a-z0-9]+' ~/perpatch/chain_wave5.sh`. A label that matches no `skip()` is not "no resume": every step is skipped and the chain walks to its end
   (measured 2026-11-02, resumed at `mb` when the wave is `mb4`: mb, pcr, gpu4b, hunt5 and waves 7-18 all skipped and
   the chain exited).
2. **Pick the next step not yet started.** Resuming at a wave that is in flight runs it twice.
3. **Check the harness has the arms that step needs.** Files in `~/perpatch/hold-<wave>/` install only when that wave
   runs. Editing them after the wave has passed changes nothing installed: `grep -c <arm> ~/perpatch/perpatch_run.sh`.
   If it is missing, install the staged copy yourself (`cp x.staged x` with the old mode) before the wave that uses it;
   otherwise the wave boots nothing and logs "0 boots" for every arm (measured: the `a1stock` arm, wave mb).

## The restart

```bash
cd work/hunt/deploy && sed 's/\r$//' scripts/glm53/v110/perpatch/chain_wave5.sh > chain_wave5.sh
scp -o ProxyJump=root@192.168.99.100 chain_wave5.sh adam@192.168.99.11:perpatch/chain_wave5.sh.tmp
ssh ... 'bash -n ~/perpatch/chain_wave5.sh.tmp && tail -1 ~/perpatch/chain5.log'
ssh ... "kill $(ssh ... 'pgrep -f "perpatch/chain_wave[5].sh"')"
ssh ... "bash ~/work/hunt-deploy/resume5.sh <label>"
```

Then re-arm the firewall guard for the new PID (the old guard lifts it when its chain dies):
`rm -f ~/perpatch/fwguard/{on,is-on,is-off}`; `sudo bash ~/fw8888.sh guard <newpid> ~/perpatch/fwguard`; `touch ~/perpatch/fwguard/on`.

## After it

- Read `chain5.log` and confirm the FIRST line after the restart is the step you chose, not a "skipped" line.
- Waiter keys: a killed chain never writes "wave X ended", so key waiters on `^PERPATCH DONE` in `~/perpatch/wave<X>.log`.
- For an overnight watch, `work/hunt/deploy/watch_overnight.sh` polls and exits (waking the session) on a new
  " ended:" line, a dead chain, or 45 minutes without a log line.
