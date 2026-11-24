---
name: tf124-lever-campaign-spark6
description: "Driving TensorFold v1.2.4 lever campaigns on spark6: GPU-window protocol, lane coordination, image relabeling, boot-count parsing, and PR packaging"
---

# TensorFold v1.2.4 lever campaign on spark6

Procedures proven 2026-11-07/08 porting Qwen3.8 Flash Next levers onto upstream TensorFold main (v1.2.4, `267c5af6`, later `ab4b2f05`).

## Layout on spark6 (ssh `-o BatchMode=yes adam@spark6.ots-int.net`, lowercase adam, one ssh at a time, `export SSH_AUTH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg`; never sudo, never spark1-5)

- Upstream clone: `~/work/lanes/up-pr/tf`. Lever worktrees: `~/work/lanes/port124{,b,c}/tf` (branches `port-copy-windows` 71f1afaee+receipt 0d951b3bd on ab4b2f05, `port-hc-q12` 24f70f52b on 267c5af6, `port-64rows` 427063f62 on 267c5af6). Backups: Gitea `ssh://git@gitea.ots-int.net:2222/ots/tensorfold-levers124.git` (same branch names).
- Recipe (v1.1.4 series, for boots): `~/work/lanes/rpr/recipe`, boots via its `start.sh` with `PREPARE=0 CHECKPOINT=nvfp4 VISION=0 KV_DTYPE=bf16 PARALLEL=C CONTEXT=131072 HOST=127.0.0.1`. `tensorfold-qwen38:w64`-style images need the relabel (below). The recipe's engine REFUSES `CHECKPOINT=int4` (`UnsupportedCheckpoint`) and its Flash Next family REFUSES `--kv-cache fp8` on 1.2.4.
- Cells: `~/work/lanes/par114/arm.sh` (arms up124/cw124/hq124/w64/tune*; `RUNS_DIR` env picks the run dir), summariser `sum.py`, boot-split `sum_hq.py`; zgold reference `~/work/lanes/par114/zgold-up124.json`; probes `~/work/lanes/tfmain/tfm_decode.py`, `~/work/bench/ttft.py`, `~/work/merge/v/zcopy.py` + `w2copy.py` (copy/rewrite/edit workloads), `~/work/qf_harness.py golden` + `zgold_cmp.py`.
- Build: `cd ~/work/merge && ./build-br.sh TAG git://192.168.99.16/<dir>/tf <full 40-char sha>` (git daemon on :9418 serves `~/work/lanes`, started with setsid nohup), then the relabel below.

## GPU window protocol (the proven sequence)

1. From YOUR session: `ssh -o BatchMode=yes root@192.168.99.100 'systemctl list-timers "sparkdash*" --all'` (refuse to start over a foreign pending timer; name yours `sparkdash-safety-<lane>`), then `pct exec 111 -- systemctl stop sparkdash`.
2. On spark6: `(cd ~/qwen-zig && ./stop.sh)`, kill stale holders `for p in $(pgrep -f "qwen6-gpu-lock-holder" | grep -vw $$); do kill $p; done`, then `flock -o ~/work/gpu.lock` for the whole window.
3. Cells: `bash ~/work/lanes/par114/arm.sh ARM C` (fresh boot per cell, ABBA order, two boots at 1/2 streams when the expected delta is small). The arm logs golden (6/6 vs `zgold-up124.json` required), SOURCES (must be 127.0.0.1 only), GPU temps.
4. Exit path: restore the serve (`setsid nohup ~/qwen6-start.sh > ~/qwen6-boot.log 2>&1 < /dev/null &`, prove `/health`) and start sparkDash - but only when the lock is free (`flock -n` test); a foreign window owns the box otherwise. Never inline a multi-minute pipeline behind one ssh timeout: write a script on the box, run it `setsid nohup`, watch with bounded commands.

## Measured traps (each cost hours)

- **`tf.kernels=embedded` relabel**: build-br images inherit `tf.kernels=present` from the base and the recipe's `start.sh` refuses them ("is not an image of this recipe", boot seconds 0). Fix: `echo "FROM <img>" | docker build -q --label tf.kernels=embedded -t <img> -`. Check the label BEFORE any boot.
- **Lock-holder grace**: the holder's old `sleep 600` kept the GPU lock 10 min after every stop (three windows stalled on it). New holder (qwen6-start.sh): waits up to 10 min for the container, then follows it. After any reboot run `~/qwen6-start.sh` once (the container restarts on its own; the holder does not).
- **Boot-count parsing**: repeated boots APPEND rows to the same dec.jsonl (same reply shas, rates ±0.4%); medians must split boots by (kind, pass) groups and state the group count - a naive median mixes boots and inflates aggregates ~2x. tfm_decode rotates prompts per pass and adds a nonce, so reply shas are NOT compared across passes within an arm (only between arms on the same probe).
- **arm.sh mid-boot writes corrupt boots** (two voided, rc=143): no shared arm.sh writes while any lane holds the lock or has a boot in flight; new arms go in lane-owned copies; announce windows on `agent://all`.
- **pkill self-match**: `pkill -f "x"` inside an ssh command line kills the session itself if "x" appears elsewhere in the line (e.g. a `tail x.log`) - exit 255, no output. Use `pgrep | grep -vw $$ | xargs kill`.
- **CRLF**: Windows-written .sh files must be `sed -i 's/\r$//'` + `bash -n` before deploy; a CRLF arm.sh dies at `case "$ARM" in\r`.
- **Windows python `write_text` writes CRLF by default**: pass `newline="\n"` or sed on the box.

## Verdicts recorded (docs/FP4-PORT-AND-RETEST.md sections 6-6.4)

- Lever 1 (copy re-sync + shared-round ramp, opt-in settings): +30% rewrite, +42-52% concurrent edits, +58% edit-beside-prose on 1.2.4, byte-identical everywhere, plain decode flat ±2% - PR text ready (`upstream/tensorfold-pr-copy-resync/PR_final.md` + `PR_64row.md` template), HELD pending the 64-row verdict and owner approval.
- Lever 2 (12-bit hc read-out): byte-identical but FLAT at every level on 1.2.4 - the old +2.6-3.7% does not reproduce; no PR (6.3).
- Settings retune: keep `TF_FLASHNEXT_CONFIDENCE=-0.4` and `PRODUCT_STREAMS=5` (-0.15 costs 9% prose at 1 stream; PS=6 loses 4.3% prose at 6) (6.4).
- Stock upstream 1.2.4 on GB10: NVFP4 only, bf16 KV, cannot serve 8 streams (32.86 vs 31.41 GiB at 131k), slowest of the three arms.
- Overnight guard: `~/boxguard.sh` on spark6 (every 10 min, restores the serve if down with no window running, log `~/boxguard.log`).
