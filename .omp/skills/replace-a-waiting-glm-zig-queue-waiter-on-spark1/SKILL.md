---
name: replace-a-waiting-glm-zig-queue-waiter-on-spark1
description: "Use to replace, re-point or insert a waiting queue (queueNN.sh, start-qNN.sh, queueNN.env in ~/work/glm53-zig on spark1) in the GLM Zig repo's chain without a gap; not for the perpatch or chain5 harnesses."
---

# Replacing a waiting queue in the GLM Zig chain on spark1

Each queue is a bash process that waits for the previous queue's process to disappear, then runs. A waiter has already read its script and env file, so changing either changes nothing for it; a new waiter must be started to pick up a change.

## Rules that cost time before

- Start queues through a wrapper (`start-qNN.sh`: `cd ~/work/glm53-zig`, export ARMS and WAIT_FOR or let `queueNN.env` carry WAIT_FOR, then `exec setsid nohup bash queueNN.sh > ~/bench/queueNN.log 2>&1 < /dev/null`). No command line may name the script it waits for: the wait is `pgrep -f "$WAIT_FOR"` and a launcher naming it waits on itself forever.
- The wait target must be ALIVE when a waiter starts. A waiter whose target is absent sees nothing and runs at once, on a box where another queue holds the GPUs. To insert queue X between A and B: start X waiting for A first, then replace B's waiter with WAIT_FOR=X.
- Count processes with `ps -eo pid,etime,args | grep -E "bash queueNN\.sh" | grep -v grep`. A `pgrep -af` run through ssh also matches the ssh command's own text.
- Never `pkill -f`. Kill the old waiter by pid (the one with the larger etime), after the new one is up.

## Procedure

1. Compare the deployed script's sha256 with the repo copy before replacing it (never clobber a hot-fix), then `scp` the new file to `queueNN.sh.part` and compare the hash on the box.
2. If the wait target changes: `sed 's/^WAIT_FOR=.*/WAIT_FOR=X.sh/' queueNN.env > queueNN.env.part && mv queueNN.env.part queueNN.env`.
3. `mv queueNN.sh.part queueNN.sh` (the running waiter keeps its old inode).
4. Start the new waiter: `ssh -f -n HOST 'cd ~/work/glm53-zig && setsid nohup bash start-qNN.sh > /dev/null 2>&1 < /dev/null &'`. The wrapper truncates `~/bench/queueNN.log`, which only holds the old "waiting" line at this point.
5. Check two processes exist and the log says `start; ... waiting for <target>`.
6. `kill <old pid>`, then list the whole chain with `ps` and read every queue log's last line: each queue's wait target must still be a live process.
7. Update the background watcher (`work/watch-queues.py`: its QUEUES list and its live-process pattern) and start the new watcher before cancelling the old one.

## Afterwards

The repo copy of the script is the record: deployed copies of queue92 (queue96, queue97, queue101, queue92b) are copies of `scripts/queues/queue92.sh`. Say in the commit which version was deployed if the repo file changed after a copy was started.
