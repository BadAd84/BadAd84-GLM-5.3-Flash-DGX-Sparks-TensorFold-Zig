---
name: insert-a-queue-into-the-spark1-chain
description: "Insert, replace, re-time or reorder a queueNN.sh in spark1's pgrep-waiting GPU chain. Not for chain5 or the perpatch harness."
---

# insert-a-queue-into-the-spark1-chain

one skill: insert/splice a queueNN.sh into spark1's waiting chain

Merged from 7 skill(s): insert-a-queue-into-the-glm-zig-spark1-chain, insert-a-queue-into-the-running-zig-glm-chain, insert-a-queue-into-the-spark1-wait-chain, insert-a-queue-into-the-spark1-waiter-chain, insert-a-queue-into-the-spark1-zig-chain, splice-a-queue-into-the-spark1-queue-chain, splice-into-a-pgrep-waiting-queue-chain.

# Insert a queue into the waiter-chained queue chain (GLM Zig repo, spark1)

Each queue is `bash queueNN.sh` in `~/work/glm53-zig/` on spark1, started by a wrapper `start-qNN.sh` that exports `ARMS` and `WAIT_FOR` (or reads `WAIT_FOR` from `queueNN.env`) and `exec setsid nohup bash queueNN.sh > ~/bench/queueNN.log`. The script waits with `while pgrep -f "$WAIT_FOR"; do sleep 60; done` BEFORE any image build or boot. A chain is therefore "each queue waits for the previous queue's process to disappear".

## Rules that each cost a mistake
1. **A waiter whose target is not alive proceeds at once.** Never start a successor's new waiter before the queue it must wait for is running, or two queues take the GPUs together.
2. **No process command line may name the script it waits for** (`pgrep -f` matches it and the waiter waits on itself forever). That is why wrappers export the wait target instead of passing it as an argument. Your own transient `ssh ... pgrep -af "bash queueNN.sh"` command also shows up in `pgrep` output: ignore it.
3. **A running bash has already read its env file and script.** Editing `queueNN.env`, or replacing `queueNN.sh` with `mv` (new inode), changes nothing for the live waiter. To change what a waiting queue does, start a new waiter from the new files, then kill the old one by pid.
4. **New waiter first, old one killed second, by pid** (`kill PID`, never `pkill -f`), so the queue behind it never sees a gap in which its target is absent.

## Procedure (insert Q_new between P and S, where S currently waits for P)
1. Copy the script (a copy of `scripts/queues/queue92.sh` for stock-arm rungs: same `unit`, `ARMS`, `armtag`) and the source tarball to `~/work/glm53-zig/` under `.part` names; compare `sha256sum` with the laptop; then `mv` into place. Make `start-qNEW.sh` with `export ARMS="..." WAIT_FOR=P.sh`.
2. Start it: `ssh -f -n HOST 'cd ~/work/glm53-zig && setsid nohup bash start-qNEW.sh > /dev/null 2>&1 < /dev/null &'`; confirm its log says `waiting for P.sh` and its process exists.
3. Re-point S: write `queueS.env` with `WAIT_FOR=queueNEW.sh` (sed to a `.part`, then `mv`), start a NEW S waiter (`start-qS.sh`), confirm both S processes exist and the new log says `waiting for queueNEW.sh`, then kill the OLD S pid (identify it by the larger `etime`).
4. Verify the whole chain: `ps -eo pid,etime,args | grep -E "bash queue(...)\.sh"` shows exactly one process per queue, and `tail -n 1 ~/bench/queueX.log` of each queue shows `waiting for` the right predecessor.
5. Update the laptop watcher (`work/watch-queues.py`: the QUEUES list and the `pgrep` pattern), start the new watcher first, then cancel the old job.

## Before deploying a changed queue script
Extract the new bash functions with `sed -n '/^name() {/,/^other() {/p'`, eval them under stubbed `docker` and `ssh` functions, and test both branches (arm carries the variable / leaked variable / unreadable environment; effect-proof files hold the line or MISSING and NONE). Then run faithful mutants (each anchor must match exactly once; a kill is a named check failing). `scripts/tests/test_queue92_funcs.sh` and `mutants_queue92_funcs.sh` are the pattern. A first version of the fixture had only one drafter line and one TF_GLM line, so two mutants survived: put decoys in the fixture.

## Effect proofs for env-only arms
Read the container environment back on all three ranks (`docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}'`, ssh for ranks 1 and 2) and stop the queue on any mismatch, controls included (a leaked variable makes an A/B an A/A). Keep the engine's own log evidence next to the rows (rank 0's `dflash2: drafter from ... GiB on the device`, any `TF_GLM_DSCORES` warning) because the boot lines scroll out of `keeplog`'s 800-line tail.

Use when a queue in the spark1 `~/work/glm53-zig` chain (queueNN.sh waiters, GPU window already held) must be inserted, changed or re-pointed while other queues run or wait.

How the chain works (measured):
- Each queue is `bash queueNN.sh` started by a wrapper `start-qNN.sh` (`cd ~/work/glm53-zig; export ARMS=... WAIT_FOR=queueMM.sh; exec setsid nohup bash queueNN.sh > ~/bench/queueNN.log 2>&1 < /dev/null`) or reads WAIT_FOR from `queueNN.env`. No process command line may name a queue script: the wait is `while pgrep -f "$WAIT_FOR"; do sleep 60; done`, so a launcher or an ssh command containing the name matches itself and waits forever (or wrongly proceeds).
- A waiter whose target is NOT running proceeds immediately, so the target must be alive before the waiter that depends on it starts.
- bash reads a script incrementally from its open inode: replacing the file with `mv` leaves running and waiting processes on the OLD text. A changed script only takes effect through a new process.

Procedure:
1. Compare the deployed copy with the repo copy (`sha256sum` on the box) before replacing anything, so a hot fix is never clobbered. Copy the new script to `queueNN.sh.part`, check its sha256 against the local one, then `mv` it into place.
2. Inserting Q between A (running or waiting) and B (waits A): start Q first with WAIT_FOR=A (wrapper), confirm it is alive and logged "waiting for A". Then point B at Q: rewrite `queueB.env` (temp file, `mv`), start a NEW B waiter through its wrapper, confirm both B processes exist (`ps -eo pid,etime,args | grep -E "bash queue"`), and only then `kill <old B pid>` (by pid, never `pkill -f` over ssh). Whoever waits on B keeps finding a `bash queueB.sh` the whole time.
3. Replacing a waiting queue in place: same order, new waiter first, old killed by pid after the new one logged its start line.
4. Verify after every step: the process list with etimes, and the last log line of every queue in the chain.
5. Update the watcher (`work/watch-queues.py`: its QUEUES list and its live-process pgrep pattern), start the new watcher before stopping the old one.
6. When a script changes, run `bash -n`, and run its function tests and mutants where they exist (`scripts/tests/test_queue92_funcs.sh`, `mutants_queue92_funcs.sh`, `scripts/tests/check_smoke_probe.py`).

Traps: an ssh one-liner containing `pgrep -af "bash queueNN.sh"` matches its own `bash -c`; a row-copy script with a keep list silently drops a new output file kind (add it before fetching); a first-boot smoke must not reuse a unit probe's seed and size.

## Model
Each queue is a detached bash on spark1 (`~/work/glm53-zig/`): `bash queueNN.sh`, started by a wrapper `start-qNN.sh` (`cd ~/work/glm53-zig || exit 1; exec setsid nohup bash queueNN.sh > ~/bench/queueNN.log 2>&1 < /dev/null`). The script sources `queueNN.env` (IMG, WORKERS, HOURS, WAIT_FOR) and loops `while pgrep -f "$WAIT_FOR" > /dev/null; do sleep 60; done` before doing anything, so the chain is a linked list by WAIT_FOR. The wait target lives in the env file or the wrapper's export, never in a command line: a launcher whose command line names the script it waits for matches itself and waits forever. A waiter's own process (`bash queueP.sh`) matches `pgrep -f queueP.sh` from its first second to its end, so a successor sees no gap.

## Insert queue X between P and S
1. From the laptop's top-level Windows shell (not WSL): export SSH_AUTH_SOCK to the agent-gui socket; every ssh/scp with `-o BatchMode=yes -o ConnectTimeout=20` and `< /dev/null`. An 'agent refused operation' is a PIN state: never restart the agent.
2. Stage queueX.sh, queueX.env (WAIT_FOR=queueP.sh) and start-qX.sh with scp; compare sha256 on both sides; `bash -n queueX.sh` on the box. Stage and hash-check any tools tarball the queue extracts.
3. Before a window run `python scripts/check-spark-sync.py adam@<spark1>` (every runtime script the repo authors must equal the box's copy) and run any upstream client's own tests on the box's python (3.12 there) from the staged tarball, then delete that scratch.
4. Start X's waiter: `ssh -f -n ... 'cd ~/work/glm53-zig && setsid nohup bash start-qX.sh > ~/bench/qX-start.log 2>&1 < /dev/null &' < /dev/null`; confirm `head -n 1 ~/bench/queueX.log` says it waits for P.
5. Repoint S: copy queueS.env to a `.before-qX` file, set WAIT_FOR=queueX.sh, read the old waiter's pid with `pgrep -f "bash queueS\.sh"`, start a NEW S waiter through its wrapper, confirm its log says it waits for X, and only then kill the old pid (check /proc/PID/cmdline first). Start-new-then-kill-old: killing first leaves a gap in which a later queue's wait could see nothing and start.
6. Never `pkill -f "bash queueNN.sh"` over ssh (the pattern also matches the remote shell running it). Kill by pid.
7. Update the QUEUES list of the session's watcher (work/watch-queues.py) in chain order; stop the running watcher job (proc://bg_N/kill) and start the new one as an async background job with timeout 0.
8. Verify the whole chain: `pgrep -af "bash queue9[0-9]b?\.sh"` shows one process per queue, and each queue's log first line names its predecessor.

## Replace a script a waiter already runs
bash reads a script by offset while it runs. Copy the new file under a temporary name, `bash -n` it, `mv` it over (a new inode), start a new waiter, kill the old one by pid. The old process keeps running the OLD file, so a replaced script without a restarted waiter changes nothing.

## Writing a queue by copying another
- Rows layout: queue95 has OUT=$HOME/bench and writes $OUT/f95-c/...; a skeleton with OUT=$BENCH/fNN-c doubles the directory when cell code is pasted in. Expand every $OUT/ and $BENCH/ path with a stub HOME and list the distinct directories before deploying.
- Never name a queue variable MODEL (serve.sh reads it as the container model path): use SERVED. Export LEARN=0 XSERVE="" (zig-tp3.sh forwards both to every rank).
- An arm that differs by an XENV variable: read every rank container's environment back after each boot (docker inspect on spark1 and both workers) and stop on a mismatch; require TF_GLM_RANK in the listing. Test the guard block against a mocked cenv.
- Skip a dependent arm when the first arm's client did not exit 0. Gate an optional queue on a previous queue's output (a spend rule: integer arithmetic on its compare report) so it exits in seconds when not needed and the trap still prints its DONE marker.
- Scorer rules are written, tested and mutated (each mutant killed by a named assertion, control first) before any row exists; a rule that depends on engine behaviour is checked against real engine rows.

# Insert a queue into the spark1 waiter chain (GLM Zig repo)

Each queue is a detached bash on spark1 that polls `pgrep -f <predecessor script>` and starts when it is gone. Used five times in one campaign; every rule below came from a real near miss or a verified check.

## Files on spark1 (`~/work/glm53-zig/`)
- `queueNN.sh`, `queueNN.env` (IMG, WORKERS, HOURS, WAIT_FOR), `start-qNN.sh` = `cd ~/work/glm53-zig; exec setsid nohup bash queueNN.sh > ~/bench/queueNN.log 2>&1 < /dev/null`.
- The wait target lives in the env file or the wrapper. A launcher whose command line names the script it waits for waits on itself forever.

## Deploy order (never leave a gap)
1. scp the script under a temporary name, compare sha256 local against box, `bash -n` on the box, then `mv` into place. A running bash keeps its old file: to change a running waiter, copy, mv, restart that waiter.
2. Start the new waiter detached: `ssh -f -n HOST 'cd DIR && setsid nohup bash start-qNN.sh > LOG 2>&1 < /dev/null &'`. Confirm its first log line says `waiting for <predecessor>`.
3. Re-point the successor: `sed -i` its env `WAIT_FOR`, start ITS new waiter first, confirm the new log line, and only then `kill <old pid>` (read `/proc/PID/cmdline` first). Never `pkill -f queue...` through ssh (the ssh command line matches), and never kill before the new one is up: the gap lets the next queue start.
4. Verify: `head -n 1 ~/bench/queueNN.log` for every waiter (each names its target) and `pgrep -af 'bash queue(9[0-9]b?|100)\.sh'`; the count must equal the number of waiters.
5. Update the laptop watcher: its QUEUES list and its pgrep pattern (a three-digit name needs an alternation). Its "none alive" test is `live <= 0` (the live query does not match itself; check that count equals the process list). Pass finished queues as SEEN args (`queue92:1`); queues that are copies of queue92.sh log `QUEUE92-DONE`.
6. A window that can exit before any boot (a gate, a refused check) must not stop or remove containers: guard the exit handler with a BOOTED flag.

## Verify a new queue before it is deployed
Each of these caught a real defect that `bash -n` and the unit tests did not:
- Derive it from a verified sibling, normalise only the names, diff, and classify every changed line in a table.
- Run the real guard block (per-rank environment read-back) and the real gate lines in a throwaway harness against mocks, including the leaked, missing, wrong-value and unreadable cases.
- Expand every output-path expression with a stub HOME and list the distinct directories: this found a doubled `f99-c/f99-c` that nothing else shows.
- Run the scorer on real rows relabelled into the new layout, and on the real client's own output through a fake server: this found a vacuity gate that would have read every real resumed turn as a miss.
- Independent mutant batch of your own (control first; a kill is a named assertion failure, never an ERROR), and hash the scorer before and after.
- When a lane reports, hash its files against its stated hashes; a lane may edit again after its report (re-check before committing).

Context: the Zig GLM campaign's GPU work is a chain of bash queues in `~/work/glm53-zig/` on spark1. Each `queueNN.sh` sources `queueNN.env` (IMG, WORKERS, HOURS, WAIT_FOR; sourced, not exported), waits with `while pgrep -f "$WAIT_FOR"`, runs fresh-boot units, logs to `~/bench/queueNN.log`, writes rows to `~/bench/fNN-c`, and prints `QUEUENN-DONE` from its EXIT trap. The chain order is just the linked list of WAIT_FOR targets. Every ssh/scp runs from the top-level Windows shell with `export SSH_AUTH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg`, `-o BatchMode=yes`, `< /dev/null`. Never restart the agent ("agent refused operation" is a PIN state).

## Before touching spark1
1. `wsl.exe -d Ubuntu -- bash -n /mnt/c/<repo>/scripts/queues/queueNN.sh` exits 0 and `grep -c $'\r'` on the file is 0.
2. Read the live graph: `pgrep -af "bash queue9[0-9]b?\.sh"`, `head -n 1 ~/bench/queueXX.log` for each queue (its first line names the wait target), and every `start-qXX.sh` (they export ARMS / WAIT_FOR).
3. `python scripts/check-spark-sync.py adam@<spark1>` must print OK (runtime scripts equal to the repo).
4. If the queue uses an upstream client from a staged tar, run its own tests on the box from an extracted copy under `stage/` as a script (`python3 tests/test_x.py`; `-m unittest tests.test_x` cannot import the sibling fixture), then remove the copy.

## Stage and start
- scp to a NEW name (`queueNN.sh`, `queueNN.env`, `start-qNN.sh`); compare `sha256sum` local and on the box; `bash -n` on the box.
- Wrapper: `cd ~/work/glm53-zig || exit 1; exec setsid nohup bash queueNN.sh > ~/bench/queueNN.log 2>&1 < /dev/null`. Neither the wrapper nor the ssh command line may contain the script name the queue waits for, or the waiter matches itself forever.
- Start: `ssh -f -n host 'cd ~/work/glm53-zig && setsid nohup bash start-qNN.sh > ~/bench/queueNN-start.log 2>&1 < /dev/null &'`, then confirm its first log line says `waiting for <target>`.

## Insert X between P and its successor S
A running S waiter has WAIT_FOR baked in. Edit `queueS.env` (WAIT_FOR=queueX.sh; keep a `.before` copy), start a NEW S waiter through its wrapper, confirm its log says it waits for X, THEN kill the old S waiter by pid after reading `/proc/<pid>/cmdline`. Start new before killing old: a gap lets the successor's wait see no process and start early. Never `pkill -f` through ssh (it matches the ssh shell).

## Replace a script that is already waiting or running
bash reads a script incrementally, so never overwrite it in place. scp to `queueNN.sh.new`, `bash -n`, `mv` over the old name (atomic; the old process keeps its inode), start a new waiter, kill the old by pid, and check `ls -l /proc/<newpid>/fd | grep -c "queueNN.sh (deleted)"` is 0.

## Watcher
Add the queue to `QUEUES` in `work/watch-queues.py` in chain order (it greps `^QUEUE.*-DONE` in each `~/bench/<q>.log`; the live count pattern is `bash queue9[0-9]b?\.sh`). Stop the old watcher job (write empty content to `proc://bg_N/kill`) and start the new one as an async background job with `timeout: 0`.

## Verify
One live process per queue, and each waiter's first log line names its predecessor. Queue 92 was read this way: `for q in ...; do head -n 1 ~/bench/queue$q.log; done`.

## Traps that cost time
- A queue variable named `MODEL` collides with serve.sh's container model path if it is ever exported: use a fixed `SERVED=GLM-5.3-Flash-EXL3` for the client's model name.
- `export LEARN=0 XSERVE=""`: zig-tp3.sh forwards both to every rank, so the arms' flags are then fully set by the script.
- After each boot read every rank container's environment back (`docker inspect NAME --format '{{range .Config.Env}}{{println .}}{{end}}'`, over ssh for ranks 1 and 2) and stop if the arm's variable is not exactly as designed. Test the guard lines against a mocked `cenv` for clean, leaked, missing, wrong-word and unreadable cases.
- Skip the second arm when the first arm's client did not exit 0; a comparison needs both.
- Keep scored rows in `$HOME/bench/fNN-c` and put boot logs and the check-env log in `$HOME/bench/fNN-boots` and `fNN-check-env.log`, outside the scored directory.
- A scorer's assumptions about the producer are checked against real rows from an earlier run and against the real client run on a fake server, not only against the lane's fixtures.

## Model (this repo's queues, `~/work/glm53-zig/` on spark1)

Each `queueNN.sh` sources `queueNN.env` once at start (WORKERS, HOURS, WAIT_FOR, image names), loops `while pgrep -f "$WAIT_FOR"; do sleep 60; done`, THEN sets `trap finish EXIT` and a DEADLINE of HOURS from the end of the wait. So: a changed WAIT_FOR or HOURS only takes effect in a NEW process, and killing a waiter before it passes the wait loop runs no cleanup (the trap is not set yet).

## Traps, each measured on 2026-11-21

1. **A launcher that names the script it waits for waits on itself.** `ssh -f -n 'cd .. && WAIT_FOR=queue93.sh setsid nohup bash queue92b.sh ... &'` leaves a `bash -c` launcher alive as long as its child, and its command line contains `queue93.sh`, so the queue's own `pgrep -f queue93.sh` matches it forever. Start every queue through a wrapper file `work/start-qNN.sh` (`cd ~/work/glm53-zig; export ARMS=... WAIT_FOR=...; exec setsid nohup bash queueNN.sh > ~/bench/queueNN.log 2>&1 < /dev/null`), launched as `ssh -f -n host 'cd ~/work/glm53-zig && setsid nohup bash start-qNN.sh > /dev/null 2>&1 < /dev/null &'`. The surviving process is `bash queueNN.sh`; nothing else names a queue script. A copy of a script that another queue must not mistake for the original needs a name that does not contain the original's as a substring (`queue92b.sh`, `queue96.sh`, `queue97.sh` for copies of `queue92.sh`).
2. **Start the new waiter BEFORE killing the old one.** Killing first leaves a window with no process of that name; the next queue's `pgrep -f` sees nothing and starts at once (a ~20 s gap happened; it was only luck that nobody polled in it). Two waiters on the same predecessor are harmless for a few seconds; then `kill <old pid>` (by pid; `pkill -f "bash queueNN.sh"` through ssh kills your own shell).
3. **Never overwrite a running script in place** (bash reads scripts incrementally): `scp` to `queueNN.sh.new`, `sed -i 's/\r$//'`, `bash -n`, `mv -f` onto the name (atomic; a running instance keeps its inode), then replace the waiter as in 2.
4. **Insert X between P and Q in the right order:** start X (WAIT_FOR=P) first; only then set Q's env `WAIT_FOR=X`, start Q's new waiter, kill Q's old one. If Q is pointed at X before X exists, Q starts immediately beside P.
5. **Size HOURS from the work:** image builds ~8 min each, boots ~25-30 min each at this cell set, device checks ~15-20 min; the units check `room` only at their start, so a short deadline silently drops the tail units. Raise it in the env file and replace the waiter (2).
6. **Verify the chain after every change:** `pgrep -af '^bash queue9'` shows one instance per queue; each log's last line says `waiting for <predecessor>`; the predecessors' logs have no `is done` line; the running queue is the only one past its wait.

## Waking the session

Queues are not tracked jobs. Run a read-only watcher as a tracked background bash job (`timeout: 0`): every 300 s over ssh read, per queue log, the count of `^QUEUE.*-DONE` markers and the number of live `bash queue9x.sh` processes (the ssh shell's own command line matches the pattern once, so `<= 1` means none); exit on a new DONE marker, on none alive, or after 12 failed ssh tries, printing each log's tail. Its exit starts the next turn; restart it with the updated queue list whenever the chain changes. SSH needs the agent socket (`SSH_AUTH_SOCK` for the YubiKey agent), `BatchMode=yes`, `< /dev/null`; an `agent refused operation` is a PIN state that clears.

## Inputs

Stage tars before the queue needs them: `git archive COMMIT` is deterministic (the same commit gives the same sha256), `scp` to `~/work/glm53-zig/stage/`, compare sha256 on the box; each queue re-extracts its own tools tar at its start, so queues that use different upstream tool versions do not collide. Keep a copy of the wrapper and watcher under the repo's `work/` (untracked).

## When
A chain of queue scripts on one box (spark1 `~/work/glm53-zig/queueNN.sh`), each doing `while pgrep -f "$WAIT_FOR"; do sleep 60; done`, then `trap finish EXIT` and its work, and you must start a new link, change what a link waits for, or replace a link's script while the chain is live.

## Traps (each measured)
1. **A launcher that names the script it waits for waits on itself.** `ssh -f -n 'ARMS=.. WAIT_FOR=queue93.sh setsid nohup bash queue92b.sh ... &'` leaves a `bash -c` subshell alive for the queue's whole life whose command line contains `queue93.sh`; the queue's own `pgrep -f queue93.sh` matches it and never ends. Fix: a wrapper file `start-qNN.sh` (`cd DIR; export ARMS=.. WAIT_FOR=..; exec setsid nohup bash queueNN.sh > ~/bench/queueNN.log 2>&1 < /dev/null`), or a `queueNN.env` the script sources; start it with `ssh -f -n host 'cd DIR && setsid nohup bash start-qNN.sh > /dev/null 2>&1 < /dev/null &'`. The running process is then plain `bash queueNN.sh`.
2. **Name a copy differently.** A copy that runs a different arm list needs its own name (`queue96.sh`), and no waited-for name may be a substring of another script's name (`queue92.sh` is not inside `queue92b.sh`, which is why that pair works).
3. **Never overwrite a script a bash is running or waiting in.** `scp` truncates in place and bash reads a script incrementally. Upload as `queueNN.sh.new`, `bash -n` it, `mv -f` it over (atomic; the old process keeps its old inode), then replace the waiter as in 4.
4. **Replace a waiter by starting the new one FIRST, then killing the old one by pid.** Kill-then-start leaves a window with no `bash queueNN.sh`; a successor polling every 60 s can see nothing and start (a 20 s gap happened; luckily both successors had not polled). Two waiters for a moment is harmless. After any splice read each successor's log: it must still end `waiting for ...`.
5. A waiting instance has not registered `trap finish` yet (the trap comes after the wait loop), so `kill PID` of a waiter runs nothing. Kill by pid, never `pkill -f "bash queueNN.sh"` through ssh (it matches and kills your own ssh shell).
6. **Insert Y between X and Z:** start Y (waiting for X) first; then set Z's wait target (its env file or wrapper) to Y and replace Z's waiter as in 4. Do the insertion while X is still hours from finishing.

## Check
`ssh box 'for p in $(pgrep -f "queue9[0-9]b?\.sh|start-q9"); do c=$(tr "\0" " " < /proc/$p/cmdline | cut -c1-40); case "$c" in *pgrep*|*"date -u"*|bash\ -c*) ;; *) echo "$p $c";; esac; done'` lists one `bash queueNN.sh` per link; every link's log tail says `waiting for <its predecessor>`.

## Waking the agent
Queue scripts are not harness jobs, so nothing wakes you when one ends. Run a background bash job (`timeout: 0`) that polls over ssh every 300 s for `^QUEUE.*-DONE` markers in `~/bench/queue*.log` and for "no live queue process", and exits when either happens; its exit is the wake-up. The query's own shell matches the `pgrep -f` pattern once, so treat a live count of 1 as none.
