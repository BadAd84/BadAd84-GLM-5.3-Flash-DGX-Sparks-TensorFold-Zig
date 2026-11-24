---
name: bisect-a-ported-engine-stack-by-answer-correctness
description: "Bisect a ported engine stack (pinned upstream + our patches) for boot, chat and correctness failures by booting arms and reading each arm's own reply; covers the raiser-rank log rule, guard instrumentation, docker/ssh/restore traps and benchmark confounds."
---

# Bisect a ported engine stack by answer correctness

When a ported/pinned engine stack fails to boot, fails on a chat request, or answers garbage, use this
discipline. Each rule below cost real time when it was not followed (measured on the GLM Zig stack).

## The instrument

- A chat request is the instrument, not health. A stack can answer `/v1/models` with 200 and idle
  stably for 15 minutes while every completion is token salad; only reading the reply text proves
  correctness. Send one fixed prompt (count 1..20) at temperature 0 and read the content.
- Bisect by ARMS: pin (stock), then pin + the first N patches, then pin + patches (0,0,0,7)-era fixes +
  the next block, and so on. One arm per build (tag each image), boot it, chat it, record the reply
  digest. The first arm whose reply turns to garbage names the range; halve again.
- Compare DIGESTS across arms: the same prompt must return the same sha on a bit-exact arm. A digest
  change is a numerics change and needs the owner's call, not a silent accept.

## Where the raise actually is

- `rank N stopped (ErrorName)` names the PEER rank, not the raising one. Read THAT peer's own container
  log on ITS box (`docker logs <name> ` on the worker host); the real raise sits there. Measuring the
  guards in rank 0 proved it innocent (`len=29 window=8 capacity=262208`), while rank 1's log showed
  `prefillStart len=0`.
- A guard whose operands you have not printed is a suspect, not a cause: instrument the guard to log
  its real values before changing anything around it.
- Ported wire protocols break by MISSING FIELDS: a leader that stopped setting a header field
  (`depth`, `top_k`) while the follower still reads it gives a silently empty prompt (`len=0`) and an
  instant PromptTooLong on every request. Diff the header field SET on both sides - parse AND send.
- Kernel-symbol failures (`cuModuleGetFunction NOT_FOUND`, `kernel symbol not in module: X`) are the
  catalog/embed class: the runtime requests `"tf_glm_" ++ field_name` per struct field, so an optional
  field (`?cuda.Function` set elsewhere) must be skipped by a `@FieldType(...) == cuda.Function` guard,
  and every `.cu` or `.cuh` kernel the contract requests must exist in a compiled source AND in the
  fatbin catalog that builds the images.

## Container and session traps

- `docker run --rm` destroys the crash log. Always `KEEP=1` (no `--rm`) and `docker run -d` detached:
  an attached run ties the engine's stdout to the launching shell and the ranks stop when it ends.
- `docker inspect` on a missing container prints an empty NEWLINE to stdout before failing, so
  `s=$(docker inspect ... || echo absent)` yields `"\nabsent"` and string compares fail silently. Use
  the inspect EXIT STATUS to tell absent from stopped.
- A harness that kills/greps by pattern self-matches: `pkill -f start-tp3.sh` from an ssh whose command
  line contains that string kills the session. Use bracketed patterns (`start-tp[3]`).
- A detached restore chain (nohup/setsid) has NO ssh agent, so any `sudo systemctl` inside it wedges.
  Arm the restore with the production start only; do the sudo interactively with `ssh -A -tt`.
- Production's watchdog restarts the production stack under your test serve once its down limit
  passes; that python then holds ~83 GiB and the ported ranks die on memory. Stop
  `glm-watchdog-system.service` AND the user unit for any window.
- `read -r -a XE <<< "$XENV"` takes only the FIRST LINE: a multi-line knob list silently drops every
  entry after line 1. Validate the env the container actually got (`docker inspect ... .Config.Env`).

## Benchmark confounds - match before you compare

- Match drafts on/off and the knob set across arms. Production runs the drafter; arms benched
  DRAFTER=0 while production ran with it produce a fake 40% gap.
- One fresh boot per stream count at 1/2/4/6/8; digests must match at every level before any delta is a
  result. A slow level whose TTFT has a multi-second outlier is usually the serve's own `--parallel`
  queue, not a regression - record it as such.
- A knob that changes the reply digest is a numerics change: find it by halving the knob set with one
  boot per subset (`knob-digest.sh` style), then take it to the owner as a trade.
