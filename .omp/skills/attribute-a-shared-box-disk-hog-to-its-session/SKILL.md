---
name: attribute-a-shared-box-disk-hog-to-its-session
description: "A shared box's disk is filling and your own lanes are not the cause: attribute the producer to its session from process lineage and files, relieve it safely with owner approval, and hand over a paste-able fix; not for your own lane's disk."
---

# Attribute a shared box's disk hog to its session, then relieve it safely

Use when free space on a box that several sessions share (the orca build host `orca.ots-int.net`, formerly paperclip, the Sparks) is falling and your own lanes are not the cause. The owner will ask which agent is responsible: answer from evidence, never from whose project the files look like.

1. Prove the grower and its rate. Take `df --output=avail -BM /` twice, 10 s apart, and `du -xsm` of each large candidate directory (`~/work/*`, tool trees under home) twice, 30 s apart. The directory whose size moves is the producer. State the rate in GB per minute and the time to full; one reading of a size proves size, not growth.
2. Find the driver on the box: `ps -eo pid,ppid,etimes,args --forest | grep -B6 <grower dir name>`. Read the driver script it runs: its header comment names the tool that wrote it and the slot it works in, and its `flock` line names the lock file that marks the slot busy.
3. Match it to a laptop process. The box's driver runs under an `sshd-session` opened from the laptop, so a laptop `ssh.exe` is a child of the runner. On the Windows laptop run a `.ps1` FILE (never inline) that lists `Get-CimInstance Win32_Process` entries whose `CommandLine` matches the script name and prints each one's parent's command line: the parent is the runner (for example `python work/run_<campaign>.py ...`), and its relative paths mean its working directory is the repo holding them.
4. Name the repo from files: `git cat-file -e <pinned sha>` over `~/Gitea/*` for repos that contain the commit, and `find <repo> -maxdepth 4 -iname '<script>*'` for the tool and the runner. A literal search of `~/.omp/agent/sessions` for the slot names finds nothing when the runner builds the names itself (`mut{m}`), and the sessions directory's file mtimes only narrow the candidates by recency. Say "inferred" where the working directory could not be read.
5. Relief is the owner's call because the data is another session's: put the numbers, what is regenerable, what is not, and the exact command into one `ask` form that includes "leave it". Never delete another session's trees, logs or running slots. The approved and safe form deletes only regenerable build caches (`cache/`, `global/`, `home/`) of IDLE slots under each slot's own lock, the one the driver takes, so no run starts meanwhile:
   `for IT in ~/spark-gates/iter-*; do ( exec 9> "$IT/lock"; flock -n 9 || exit 0; pgrep -f "spark-gates/$(basename "$IT")/" >/dev/null && exit 0; rm -rf "$IT"/cache "$IT"/global "$IT"/home ); done`
   Print each slot's size before and after, then `df -h /`.
6. Give the owner a message to paste into the producing session: the mechanism in its own file names, the measured numbers, what was removed and under whose approval, and concrete fixes in its tool (remove regenerable caches when a run ends, reuse one slot per worker so a content-addressed cache is shared, refuse to start below a free-space floor). Say plainly that cleaning once does not stop the producer.
7. Protect your own work meanwhile: project-harness's `tools/remote.py` refuses to start below `--min-free-gb`, and a guard script that kills only your own `ph-build-*` containers below a floor protects the box's services (raise its floor while another session is the grower). Drop finished lanes with `--drop`.

Measured 2026-11-20: `~/spark-gates/iter-*` slots of the GLM Zig repo (`scripts/spark-gates.py`, `work/run_mut42.py`) kept about 4 GB of cache each; three workers wrote 1 to 1.5 GB a minute; cleaning 28 idle slots took free space from 18.6 GB to 112 GB.
