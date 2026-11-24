---
name: bisect-a-recipe-patch-stack-by-arm-boot
description: "Find which patch in a recipe patch stack breaks boot, chat or decode numerics by building arms and reading each arm's own reply; also covers the confounds (watchdog, session teardown, --rm) that make arms look dead."
---

# Bisecting a recipe patch stack by booting arms

For a repo that = a pinned upstream + a numbered patch series (TensorFold Zig recipe, GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig), when the full stack misbehaves and the question is WHICH patch does it.

## Build an arm

- `git clone --shared -q <applied-tree> work/armX/tree` (instant, reuses objects), `git checkout --detach <pin>`, then `git apply` the chosen patch subset in order.
- Subsets must be SELF-CONSISTENT to compile: the fatbin catalog (`zig/build/cuda_kernels.zig`) must match the kernels the subset's .cu files actually ship (a catalog entry whose .cu is absent fails the build with `FileNotFound`); test repairs (shadowed captures, arity) may be needed from later patches; a `.cuh` the subset lacks (e.g. one only 0023 grafts) breaks whichever patch introduced the later-era template.
- Pack with `tar -C tree --exclude .git --exclude .zig-cache -cf arm-src.tar .` (write the tar to a WINDOWS-visible path when sshing from Git Bash; `/tmp` there is msys-only and scp cannot see it).
- Build on the target box with the repo's own `build-image.sh TAG src.tar`, then distribute `docker save | ssh worker docker load`.

## The instrument is the model's own reply, never health

- A chat that answers `1 2 3 4 5 6 7 8 9 10 11` to a count-to-20 prompt = coherent; a mirror-of-the-same-garbage across arms = deterministic corruption. `/v1/models` 200 says nothing about decode.
- For each arm: boot TP=3, one non-streaming completion, read the TEXT, then `docker inspect` the container.
- Compare digests (`streams.py` sha) across arms at the same stream count to prove bit-exactness or catch silent numeric change (one knob can move all bits: `TF_GLM_KDA_PAD` did; every other knob was bit-exact).

## Confounds that make an arm look dead (each measured)

- **Production's watchdog**: the GLM watchdog restarts the production Python serve after its 20-min down limit. That engine takes ~83 GiB and the TP=3 arm then fails `the checkpoint's weights do not fit`. Stop production AND both watchdogs (`systemctl stop glm-watchdog-system.service` with `ssh -A -tt` + `sudo ... </dev/null`; `sudo -n` fails, a plain `sudo` with the agent works).
- **Attached `docker run`**: an attached run ties the engine's stdout to the launching shell; when that session ends the pipe breaks and every rank stops. Launch `-d`, read `docker logs`.
- **`--rm` hides the crash log**: for diagnosis boot a KEEP variant (no `--rm`) so `docker logs <name>` survives the exit; the exit code tells 137 (kill) from 1 (handled error).
- **Stale `flock` holders**: a build script's `flock -o ~/.work/gpu.lock` waits forever if a previous campaign's `flock ... exec sleep infinity` still holds it (an 18-day-old holder cost 20 min of silence; `flock -n` test + kill the PID by number, never a pattern that matches your own ssh command line).

## Locating the raise when logs are silent

- Instrument the raise sites with `std.log.err` prints of their operands (len, capacity, rows), build once, and read which site fires with what values. A raise whose printed values pass the guard came from another site.
- `module.zig`'s 'kernel symbol not in module: X' prints the EXACT string passed to `m.function` - a BARE name where the code only builds suffixed names (`"tf_glm_" ++ field`) means a different caller: check for a `@FieldType(...) == cuda.Function` guard that the port dropped.
- A kernel requested by a knob must exist in a compiled .cu: grep every quoted `tf_*` in the family against `zig/kernels/cuda/*` (substring audit) before enabling a knob set.
