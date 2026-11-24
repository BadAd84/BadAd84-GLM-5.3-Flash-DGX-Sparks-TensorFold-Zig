---
name: queue-a-perpatch-wave-correctly
description: "Queue a new wave/cell into glm5.3-flash-dev's perpatch chain (spark1-3): the probe argument trap, boot counts for an ETA, and the safe mid-wave restart."
---

# Queueing a wave into the perpatch chain (glm5.3-flash-dev)

Use when adding a measurement cell to `scripts/glm53/v110/perpatch/chain_wave5.sh` on spark1.

## 1. The shape of a wave call

```
wave <label> <levels-and-boots> <arms> [probes] [mirror|once]
```

- `<levels-and-boots>` is a list of level entries, space separated: each entry repeats the PARALLEL level once per
  entry, e.g. `"4"` = P4 once, `"4 4"` = P4 twice, `"1 1 2 2 6 6 8 8"` = eight entries.
- `<arms>` come from the arm table in `perpatch_run.sh` (`prod`, `hunt`, `huntcand`, `huntwide`, `huntpk2`, ...).
- **PROBES ARE THE FOURTH ARGUMENT.** `wave x "4 4" "prod huntcand" prodbench`. Leave it off and the wave
  header reads `probes none` and the boot measures nothing but boot time and pool tokens.

## 2. The trap that cost five cells

`PERPATCH_PRODBENCH_PARTS=sd` does NOT enable prodbench. It only narrows the parts (sd alone, no realdec/longdec/
ffft) once prodbench is already selected by the fourth argument. Queueing five cells with only the export produced
five model-only waves whose metrics were absent from the report; the pool tokens still landed, which is what made it
look like a measurement. Always echo/check the wave's own header line in the chain log after a restart:
`wave <label>: <arms> at <levels> (probes <set>, <mode>)`.

## 3. Boot counts, because they set the finish time

| wave kind | boots per level entry | measured cost a boot |
|---|---|---|
| model only (`probes none`) | 4 (2 arms x 2 passes) | 3.6-3.7 min (`7hc` 24 in 89 min, `7ydl` 24 in 86) |
| probed (`prodbench`/`realdec`) | 2 | 15-25 min |

So `"1 1 2 2 6 6 8 8"` model-only is 32 boots (~2 h), not 8. Compute an ETA only from a boot count times a rate
measured on a completed wave, and state the clock reading you took in the same turn.

## 4. Per-cell env, when a cell needs one

- `PERPATCH_SDC_STREAMS=N` decouples the stream count from the level: run 4 streams on an 8-lane box as
  `export PERPATCH_SDC_STREAMS=4; wave ... "8 8" ... prodbench`.
- `PERPATCH_CAND_ENV=<file>` re-points the `huntcand` arm's env file, which is how an env-versus-image question gets
  split. There is no equivalent prod-side override; use the three-arm shape instead (`prod hunt huntcand`), where
  `hunt` is the same image as `huntcand` on `base.env`, so agreement between `hunt` and `huntcand` proves the env is
  not carrying the difference.

## 5. Deploy at a clean boundary

1. `sed 's/\r$//' <repo chain>` into `work/hunt/deploy/chain_wave5.sh`, run `bash -n`, `test_skip.sh`, and the repo
   gates.
2. Commit (signed) and push, then `scp` the stripped copy to `~/perpatch/chain_wave5.sh.tmp`.
3. Find the chain PID with `pgrep -f "perpatch/chain_wave[5].sh"`, kill it **alone** (never in the same command as
   anything else, the pattern self-matches the ssh session).
4. Restart resuming at the wave AFTER any run in flight (`bash ~/work/hunt-deploy/resume5.sh 8mc` while `8hc`
   runs): `skip()` then skips the in-flight label with a note, waits for the orphan to finish, and the orphan's data
   is still harvested. Resuming AT the in-flight wave re-runs it from scratch.
5. Wait for `~/perpatch/fwguard/is-off`, clear `on`/`is-on`/`is-off`, arm the guard on the NEW pid
   (`sudo bash /home/adam/fw8888.sh guard <pid> /home/adam/perpatch/fwguard`), then `touch ~/perpatch/fwguard/on`
   and confirm `is-on on`.

## 6. Verify before walking away

`grep -c <new label> ~/perpatch/chain_wave5.sh` on the box, the wave header in the log once it starts, and the
`lvc`-style report read: if `prodbench_report.py` prints no metric rows for a run, the probes never ran.
