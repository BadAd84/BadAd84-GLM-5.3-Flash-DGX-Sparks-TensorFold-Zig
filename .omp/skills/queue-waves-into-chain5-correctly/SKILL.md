---
name: queue-waves-into-chain5-correctly
description: "Queueing, positioning and ETA for new waves in glm5.3-flash-dev chain 5: the probe positional argument, skip() order versus the resume label, and boot-count arithmetic. Use before adding a wave to chain_wave5.sh or claiming a queued cell will run."
---

# Queue a wave into chain 5 correctly

Applies to `scripts/glm53/v110/perpatch/chain_wave5.sh` in glm5.3-flash-dev (spark1-3 per-patch A/B chain).

## 1. The probe set is positional, not an env export

```
wave() {   # wave <n> <levels> <arms> [probes] [mirror|once]
  bash "$D/perpatch_run.sh" "$2" "$3" "${5:-mirror}" "${4:-none}" > "$D/wave$n.log" 2>&1
}
```

`PERPATCH_PRODBENCH_PARTS=sd` only trims the parts INSIDE prodbench. It does not switch prodbench on. Omit the
fourth argument and the wave header reads `(probes none)` and the boots run model-only: you get pool tokens and boot
times, and no decode or first-token numbers at all.

Correct forms:

```
wave pcr4 "4 4" "prod huntcand" prodbench          # probed comparison
wave 7hc  "4 4 6 6 8 8" "hunt hunt3"               # deliberately model-only
```

Check immediately after a wave starts: `grep -m1 "wave <label>:" wave<label>.log` must show the probes you wanted.

## 2. Position relative to the resume label

`skip()` walks labels in FILE ORDER and consumes every one until START, logging `<label> skipped (resume at <START>)`.
A block placed BEFORE the resume label never runs. Therefore:

- append new waves AFTER the label you will resume at, or at the end of the file;
- to keep an in-flight run's data, resume at the wave AFTER it (the in-flight one lands as an orphan and is harvested);
- after deploying, verify the reachable order from the DEPLOYED file:

```
awk '/^  wave /{print $2}' ~/perpatch/chain_wave5.sh | awk '/<resume-label>/{f=1} f'
```

And after the restart, confirm the expected labels are not being logged as skipped.

## 3. Boot arithmetic (for ETAs and for cost)

- Unprobed wave: 4 boots per level entry. `"4 4"` = 8, `"1 1 2 2 6 6 8 8"` = 32.
- Probed wave: 2 boots per entry. `"4 4"` = 4 (two arms), `once` halves that.
- Measured rate on GB10 model-only boots: 24 boots in 86 to 89 min, about 3.7 min a boot.

Give the owner a DURATION plus the measured rate, and if a clock time is quoted, read the clock in the same turn.

## 4. Deploy sequence

1. edit the repo copy, then `sed 's/\r$//'` it into `work/hunt/deploy/chain_wave5.sh` (WSL bash rejects CRLF);
2. `bash -n`, `test_skip.sh`, `check-bare-wait.sh`, `check-doc-inventory.sh`;
3. commit (GPG signed) and push;
4. `scp` to `~/perpatch/chain_wave5.sh.tmp` on spark1;
5. `kill <pid>` in its own ssh call (never a pattern kill in the same command as a relaunch);
6. `bash ~/work/hunt-deploy/resume5.sh <label>`;
7. wait for `~/perpatch/fwguard/is-off`, remove the markers, `sudo bash /home/adam/fw8888.sh guard <newpid> /home/adam/perpatch/fwguard`, then `touch ~/perpatch/fwguard/on` and check `is-on on`.

## 5. Record what changed

Add the wave to the plan table in `docs/notes/speed-hunt-2026-10-30.md` section 7 in the same commit, and correct any
row whose cells were mis-queued rather than leaving it looking measured.
