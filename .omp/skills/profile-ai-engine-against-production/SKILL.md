---
name: profile-ai-engine-against-production
description: "Compare ai-engine's Zig GLM serve against the production Python stack (spark1-3) at metric and kernel level without pausing production."
---

# Compare our serve against production's, without pausing production

Production (spark1-3) is an ACTIVE speed-up workstream. Never stop it to profile. Two levels of comparison are enough.

## 1. Metric level (the number that matters)
Use production's own instrument on both stacks: `scripts/glm53/v110/perpatch/perpatch_measure.py` on theirs (their run
`run-20261030-052650` is the reference, two boots a level), our copy `scripts/parity/perpatch_measure_ai.py` on ours
(it differs only in reading `/metrics`). Read both with `work/parity/prod/perpatch_report.py --ref <arm>`.
Always pair a speed number with the counters: tokens per stream-round (our drafting policy) against ms per round (our
round). A gap that looks like one number is two: 5.75 against 7.2 tokens a round, 165-180 against ~130 ms.

## 2. Kernel level (attribution) without touching them
- Ours: `~/glmperf/serve4nsys.sh RANK P CTX` wraps the serve in `--entrypoint nsys ... profile --trace=cuda`. Its
defaults are `NSDELAY=240 NSDUR=90` - the window starts FOUR MINUTES after boot, so a load fired at health lands
outside it. Set `NSDELAY=10 NSDUR=120` and start the load about 12 s after `/health` answers.
- nsys records our eager launches at P<=4 (4 x 22-24 rows is the shape production published). At P=8 it records no
kernels at all - do not profile there.
- Their reference table: `glm5.3-flash-dev/docs/notes/decode-nsys-DecNsysFable.md` (4 x 22 / 3 x 24 rows, prose,
v18-era). Diff our per-kernel ms against it; state the era difference when reporting.
- Copy the report out with `docker cp <container>:/root/.cache/tf-up/npr0.nsys-rep` before stopping the serve.

## 3. If production really must be measured live
Capture argv and env per rank first, so a restore is verbatim:
`docker inspect glm53-flash-tf --format '{{json .Config.Cmd}}'` and `... '{{range .Config.Env}}{{println .}}{{end}}'`
on spark1, spark2, spark3 into `~/prodprof/`. Then a stop/profile/restore window of ~20 min, with the restore checked
by `/health` on :8888. Ask the owner first: it costs their workstream, and case 2 usually answers the question.

## Access notes (measured 2026-11-02)
- The laptop cannot resolve bare `spark1`; use `spark1.ots-int.net`.
- `gpgssh.py`'s HOSTS map has only spark4-6 + proxmox. For spark1-3 use the restored agent:
`export SSH_AUTH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg`, then plain `ssh`.
spark1 can ssh spark2 and spark3 (so one script on spark1 can drive all three ranks).
- Production runs `tensorfold-glm53:v110hunt3` (their hunt build, not stock v0.6.0) - label any percentage with
the image tag it was measured against.
