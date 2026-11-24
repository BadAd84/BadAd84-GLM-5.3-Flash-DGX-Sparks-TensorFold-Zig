---
name: queue-unattended-gpu-ab-chains
description: "Queue and supervise long unattended GPU A/B chains on a multi-box model serve: wait markers, image distribution, disk guards, safe kills and edits, result extraction. Use when several cells must run overnight on shared GPUs."
---

# Queue unattended GPU A/B chains

For a serve spread over several boxes (coordinator + ranks), where each A/B cell needs a fresh boot.

## Order the work with wait markers, not sleeps
- Every chain writes a marker when it finishes (`echo "TAG-CHAIN-DONE $(date -Is)"`) and each queued chain
  waits for the previous marker in a loop: `for _ in $(seq 1 5760); do grep -q PREV-CHAIN-DONE logs/prev-chain.out && break; sleep 60; done`.
- Reordering is then editing one marker name, and a restart can never silently skip an arm.
- Serialise GPU use inside the cell with `flock -o ~/work/gpu.lock`; never wrap a builder that takes that lock itself.

## Build AND distribute the image
- A cell that boots ranks on other boxes needs the image THERE. Use the repo's helper that builds, saves/loads to
  every rank box and verifies (on the Spark triangle: `source ~/glmperf/ovnlib.sh; build TAG`, which reads
  `~/src-<tag>.tar`). A bare `build-image-gram.sh TAG tar` builds on the coordinator only; the ranks then fail
  minutes later with `unable to find image`, which looks like a model fault.
- Two-image A/Bs take the container image as an argument (e.g. `pp-img-ab.sh TAG WAITLOG WAITPAT IMG_A IMG_B A_XENV B_XENV`);
  one-image A/Bs take the image plus two env strings (tag, waitlog, waitpat, A_XENV, B_XENV). Check the argument count
  before launching: a misplaced env string silently runs the control arm with the candidate's settings.

## Guard the box
- Before each build: if free space `< 60G` and no build is running, prune the builder cache; otherwise prune only our own
  superseded tags (`docker rmi`), never `-f` during a build.
- Expect ~25 GB per image tag and check `df -h` before queueing a night of builds.

## Editing and killing safely
- Never edit a bash script that is mid-run: bash resumes reading by byte offset. Kill it and relaunch from the clean file.
- Kill with an anchored pattern (`pkill -f '^bash ./name.sh$'`). The bracket trick (`name-chai[n]`) still matches your
  own shell when the same command line also names the script path elsewhere - you will kill the connection.
- Prefer `sed -i` on a file then relaunch, over editing a live process.

## Extract results
- Pull the run directory back and run the repo's report tool against it (`perpatch_report.py --ref b RUN`), reading the
  per-level `a:` lines. Keep the run dirs: they are the receipts.
- Record every mixed result as a trade with BOTH directions (what it gained, what it lost, which stream count), and the
  gated or rewritten form as the next arm - a trade is not a dead lead.
