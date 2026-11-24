---
name: operate-glm-perpatch-chain-on-spark1
description: "Run, edit mid-run, resume and read the detached per-patch A/B chains on spark1-3 (glm5.3-flash-dev perpatch harness): safe swaps, firewall guard, kits, traps."
---

# Operate the per-patch GB10 A/B chain (glm5.3-flash-dev, spark1-3)

For the detached chains in `scripts/glm53/v110/perpatch/` (`chain_wave5.sh` and siblings) that build images on spark1-3, boot them with `perpatch_run.sh` and record one JSON per boot. Laptop preamble: `export SSH_AUTH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg`, then `ssh -J root@192.168.99.100 adam@192.168.99.11 ...`; scp with `-o ProxyJump=root@192.168.99.100`.

## Changing scripts while a chain runs
1. Bash reads a running script as it goes: never overwrite a running `chain_*.sh` in place. Copy the new file to `<name>.tmp` on spark1, `chmod --reference=<name> <name>.tmp`, then `mv` it into place (the running process keeps its old inode).
2. Harness files (`perpatch_run.sh`, `perpatch_measure.py`, `perpatch_report.py`) are read per boot: install them the same way between boots; `python3 -m py_compile` a `.py` first and remove `~/perpatch/__pycache__`. Before installing a report change, check its output on an old run is byte-identical (`md5sum`).
3. To change the chain's steps: `pgrep -af "perpatch/chain_wave[5].sh"` (the bracket keeps the pattern off the ssh shell), then `kill <pid>` in a SEPARATE ssh call (a command that kills by pattern does nothing else). The in-flight `perpatch_run.sh` child keeps running with `/tmp/perpatch-in-progress`, and the restarted chain's wait loop waits for it.
4. Restart from a launcher run by path (`bash ~/work/hunt-deploy/resume5.sh <label>`, authored in the laptop's gitignored `work/hunt/deploy/`): it refuses while a chain runs, renames `chain_wave5.sh.tmp` into place and starts `setsid nohup bash chain_wave5.sh after5 <label>`. The chain's `skip()` skips every step until the label (a wave name, `c<n>`, `hunt2`, `gpu`); test the rule offline (`work/hunt/deploy/test_skip.sh`) before relying on it.
5. Remote Python inside a chain goes on stdin: `printf '%s\n' "$PY" | on "$n" "python3 -"`. `python3 -c '$PY'` broke on an apostrophe in an INVENTORY text and stopped the chain.

## Benchmark firewall (owner rule: no outside traffic during a benchmark)
- Arm the root guard on the CHAIN's pid: `ssh -A -tt -J root@192.168.99.100 adam@192.168.99.11 'sudo bash /home/adam/fw8888.sh guard <pid> /home/adam/perpatch/fwguard </dev/null'` (prints "guard armed"), then `touch ~/perpatch/fwguard/on`. `~/perpatch/fwguard/is-on` then says "firewalled", and `curl http://192.168.99.11:8888/health` from the laptop returns 000.
- The guard lifts the firewall when that pid ends. After a chain restart: check `is-off`, delete `on`, `is-on`, `is-off`, and arm again on the new pid. Lift early with `touch ~/perpatch/fwguard/off`.
- A report flag `FOREIGN` means a probe saw requests it did not send: rerun that arm.

## Kits and new images
- Build on the laptop (`work/hunt/Gb10Kit/make_kit.sh <list>`), pack `out/kit` and `out/stage`, deploy with a script that unpacks on spark1-3, checks the wheel sha256, records each node's `~/INVENTORY.md`, and touches a READY marker the chain waits for (bounded wait). The deploy script must refuse once the chain has started using that kit (grep `chain5.log`).
- The first boot of a new image, even a one-file variant under the same kernel-cache label, can stall 2-4 s once in its first multi-piece chunk at depth (P8 eight-fork probe) with no kernel build written; later boots never show it. Smoke-boot every new image and never read its first boot as a regression.

## Reading results
- `scp -r` the run folder into `work/perpatch/`, then `perpatch_report.py --ref <arm> <run>`. Since 779ed9e the report exits 1 if the reference arm has no boots at a level; before that, `--ref` after the folder compared nothing and still printed "flags: none". Confirm the `- <arm>:` lines exist before quoting any result.
- Decode ms a round from `/health` depends on the short probe's first-fill pattern: two separate prompt chunks book the first stream's wait through the other chunk as decode (~130-160 ms a rep at P2, ~+2 ms a round, no round slower). Use `short_mspr_net` (and `fill_wait_seconds_total` on images with GroupedFill-2), or force one shared chunk in both arms with `TF_GLM_MULTI_PREFILL_WAIT_MS=100`. The report flags arms whose pattern mix differs.
- The pool at P2-P6 sits on the 31 GiB cap; at P8 it is budget-bound and moves ~6.4k tokens per 0.04 GiB of MemAvailable at boot.
- Record results in `docs/notes/per-patch-sync-2026-10-29.md` / `docs/notes/speed-hunt-2026-10-30.md` with the run folder name, run the repo gates, and commit with `git commit -S -F <file>`.
