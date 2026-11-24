---
name: add-hunt-image-to-glm-perpatch-chain
description: "Add a new speed-hunt image (stack list, kit, chain 5 block, arms) to the GLM-5.3-Flash per-patch chain on spark1-3."
---

# Add a speed-hunt image to the GLM per-patch chain (glm5.3-flash-dev, spark1-3)

Use this when verified candidate patches (lane outputs in `work/hunt/<Lane>/`) should become the next hunt image, `tensorfold-glm53:v110huntN`, measured by chain 5 (`scripts/glm53/v110/perpatch/chain_wave5.sh`) on spark1-3. It was done twice on 2026-10-31/11-01: hunt3 from all6w and hunt4 from all6x.

- Repo: `C:/Users/Adam/Gitea/glm5.3-flash-dev`.
- Shell: WSL, as `wsl.exe -e bash -lc 'cd /mnt/c/Users/Adam/Gitea/glm5.3-flash-dev || exit 1; ...'`.

## 1. Build the list and prove it (laptop)
1. **Write the list.** `work/hunt/stack/<new>.list` is the previous list's lines, then `# == end of stack/<prev>`, then one patch path per line, relative to `work/hunt`.
2. **Never edit a lane's patch.** If a later patch fails or fuzzes on the earlier ones, an integration lane writes `work/hunt/<Lane>/<name>.rebased.patch` and the list names that file instead.
3. **Trial build.** From `work/hunt`, run `bash build_stack.sh <Lane>/trial stack/<new>.list`. Every patch must print `0 failed, 0 fuzz`.
4. **Patches that touch the same file.** An integration lane runs both lanes' tests and mutants on the combined tree, at every value of each knob. Lane Hunt3 did this for PooledKeys-3 with SwitchSave-1.
5. **Patches that save or restore cache state.** An adversarial review lane goes first. SwitchReview found a LOW in SwitchSave-1, fixed as -1b.
6. **Registry run.** Lane Registry registers the new lanes' CPU tests, runs the full CPU set on the new list, and reports the summary line plus any verdict that changed.
7. **TRAP: tests are pinned by file name.** Registry pins and the name lists in `stage_tests.py` match patch file names. A renamed or rebased patch makes its tests skip or disappear without an error. After any rename, have both lanes re-pin and say which tests actually ran.

## 2. Build the kit (laptop, lane Gb10Kit)
1. **Stage the GPU tests** in `work/hunt/Gb10Kit/stage_tests.py`, in a round-N block:
   - leave-out refs: the list without the patch under test;
   - `post`: a compare step after the run;
   - `unless`: excludes a test that a newer patch supersedes.
   Windows-only rigs (fabric.dll, cmd) cannot be staged; record that.
2. **Build and package.** In `work/hunt/Gb10Kit`, run `make_kit.sh ../stack/<new>.list`. Package two files:
   - `work/hunt/deploy/huntN-kit.tgz`, top folder `kit/`;
   - `huntN-stage.tgz`, top folder `stage/`.
   The older tgz files' sha256 must not change.
3. **Check the label.** It must be 12 hex characters, because start.sh picks the kernel folder by that test. Patches that change only Python keep the previous label, so no new kernel folder is needed.
4. **Write the deploy script.** Copy `deploy_kit(N-1).sh` to `work/hunt/deploy/deploy_kitN.sh` and change:
   - hunt(N-1) to huntN, and hunt(N-2) to hunt(N-1), in folder names and markers;
   - the guard, which greps `~/perpatch/chain5.log` for `huntN: `;
   - the INVENTORY entries, inserted before the previous image's;
   - the last line, `touch ~/work/huntN-kit/READY`;
   - the header's own file name, which a plain substitution leaves stale.
   Then run `bash -n` on it.

## 3. Harness arms and report
1. **Arms in `scripts/glm53/v110/perpatch/perpatch_run.sh`** (the hunt block of `arm_env`):
   - the image arm: `huntN) echo "export IMAGE=tensorfold-glm53:v110huntN" ;;`
   - one arm per knob: `echo "export TF_GLM_X=..."`.
   The pre-flight refuses an arm whose TF_* setting the image's Python never names as a double-quoted literal (`"TF_GLM_X"`), so check that the patch reads its setting that way.
2. **Classification in `perpatch_report.py`:**
   - knob arms go in ENV_ADDS (setting turned on; + means the arm is better) or ENV_OFFS (setting turned off);
   - the image arm goes in ADDS, plus `OVER["huntN"] = "hunt"`.
   `python scripts/glm53/v110/tests/host/test_report_arms.py` must pass.
3. **TRAP: mutant M1** in `tests/host/mutants_report_arms.py` anchors on the tail of ENV_ADDS' text, so appending an arm breaks the anchor. Re-anchor it, then under WSL run `python3 scripts/glm53/v110/tests/host/mutants_report_arms.py` until it prints ALL KILLED.
4. **Probes that need P>=2** (for example bgprio) skip P1 by themselves, so a wave may still list `"4 1 2 6 8"`.

## 4. Add the chain block
Copy the previous image's block in `chain_wave5.sh`. Put the copy after that block and before `wave 4bp1`. The block holds:
- **Variables and guard:** `HKN=~/work/huntN-kit`, `HSN=~/work/huntN-stage`, `IMGN`. It builds only when `[ "$HUNT(N-1)" = 1 ] && ! skip huntN && [ -f "$HKN/READY" ]`.
- **Image build, per node:** `build_thin_wheels.sh $IMGN tensorfold-glm53:v110sync6 hunt-files.tgz $LABELN wheels`, then compare the laid files' sha list, then the INVENTORY python heredoc, which inserts the entry before the previous image's.
- **Kernel folder,** only when the label differs: `serve_down`, then `prepare_kcache.sh` on the three nodes in parallel, then `wait "${pids[@]}"` by PID (the check-bare-wait gate), then `serve_back`.
- **Switch over:** set IMG, HS, GK and LABEL to the new image, so the GPU step tests its stage. Resume detection is the READY marker plus `docker image inspect`.
- **Smoke and waves:**
  - smoke boots `perpatch_run.sh "8 1" "huntN" once none`;
  - the comparison wave while `HUNT_IMAGE` is still the previous image: `wave Nh "4 1 2 6 8" "hunt huntN" <probe>`;
  - then `export HUNT_IMAGE=$IMGN` and the knob waves.

Checks before committing:
1. `bash -n` on the chain.
2. A CRLF-stripped copy through `bash work/hunt/deploy/test_skip.sh <copy>`: must print PASS.
3. The gates `check-python.sh`, `check-doc-inventory.sh`, `check-bare-wait.sh` and `check-digest-greps.sh`.

Update `docs/notes/speed-hunt-2026-10-30.md`: the section 2 table for the new image, and the section 7 plan rows and footnote. Commit with `git commit -S -F <message file>`.

## 5. Deploy and restart (spark1; needs the owner's YubiKey agent)
Set `export SSH_AUTH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg` and connect with `ssh -J root@192.168.99.100 adam@192.168.99.11`; scp needs `-o ProxyJump=root@192.168.99.100`.

1. **Deploy the kit.** Copy both tgz to `~/work/hunt-deploy/`, check their sha256 there, then run `bash deploy_kitN.sh`. It installs the kit on spark1-3 and the stage on spark1, updates INVENTORY and writes READY.
   - Check `~/work/huntN-kit/kcache-label` on all three nodes.
   - READY must exist before the chain reaches the block. Otherwise the block is skipped and the later waves run on the previous image.
   - A rebuilt kit can be redeployed the same way until the chain has logged `huntN: `.
2. **Deploy changed harness files.** Strip CRLF, copy them to `~/perpatch/upd/`, run `py_compile` or `bash -n`, then `cp` each to `.tmp` and `mv` it into place. Never cp over a running script. The chain goes to `~/perpatch/chain_wave5.sh.tmp`.
3. **Restart the chain.**
   1. Edit line 11 of `work/hunt/deploy/resume5.sh` (the restart note) and copy it to `~/work/hunt-deploy/`.
   2. Find the chain's PID with `pgrep -f "perpatch/chain_wave[5].sh"`, then `kill <pid>`, in separate ssh calls.
   3. Run `bash ~/work/hunt-deploy/resume5.sh <next step>`, where the step is the one AFTER the step now running. That run finishes as an orphan and the new chain waits for it.
   Never restart during an inline step: kit build or kernel folder, gpu, a1, xhook, or a draft-record dump.
4. **Re-arm the firewall.**
   1. Wait for `~/perpatch/fwguard/is-off`.
   2. `rm -f ~/perpatch/fwguard/{on,is-on,is-off}`.
   3. `timeout 90 ssh -A -tt -J root@192.168.99.100 adam@192.168.99.11 "sudo bash /home/adam/fw8888.sh guard <new pid> /home/adam/perpatch/fwguard </dev/null"`, which must print "guard armed".
   4. `touch ~/perpatch/fwguard/on`.
   5. curl from the laptop to `192.168.99.11:8888`: it must return 000.
