---
name: port-an-archived-fork-lever-into-the-series
description: "Use when porting a lever out of the archived engine forks into the current numbered patch series: cutting the package, the three failure classes that survive a clean apply, the screen step order, and the image-and-arm that actually decides the lever."
---

# Porting an archived fork lever into the numbered patch series

## Before cutting anything

1. Find the carrying commit(s) in the archived bundle (`archive/ai-engine`, `archive/tensorfold-gb10`), not just the branch tip. Restore into `work/port/<lever>/`, never into the repo tree.
2. Establish the base: the pin from `scripts/config.sh` plus every patch in `patches/engine/` in file-name order (`scripts/apply.sh <work-dir>`), and record the tree id.
3. Cut the package as `patches/port-<lever>/0001-<name>.patch` with `RECORD.md` (source repo, branch, sha, base, whether the text was edited) and `SHA256SUMS`, so `scripts/check-patch-packages.sh` passes.

## What always breaks, in the order it breaks

**Zig launch grids.** Hoisting a launch's arguments into a `const` loses the field-type context and fails with `expected type 'abi.Dim3', found <anon struct>`. Keep `.{ .grid = .{...}, .block = .{...} }` inline in the launch call, the way the sibling launchers in the same file write it.

**Fork-era engine fields in checks and tests.** A GPU check carried from the fork references fields the current engine does not have, and qualified calls lose their receiver: `Lanes.marksOf(s, &keeps[i])` must be `self.marksOf(s, &keeps[i])` for a three-argument method whose first argument is `self`. Read what the current engine exposes before adapting; deleting the field's use is often right when the data moved to another struct.

**A new row in only one of two tables.** A new `TF_GLM_*` `.glm` row must be registered in `zig/src/platform/environment.zig` AND in the strict-env test's own `switches` list in `zig/src/families/glm/cuda_env_test.zig`, which counts every `.glm` row not prefixed `TF_GLM_OVN_`. The compile passes and only the host test catches it. If the lever has a second knob, check whether its `TF_GLM_OVN_` prefix excludes it from that count.

**Two packages that share a build file.** Packages that both attach a host-test step to `zig/build/glm_family_host.zig` cannot be stacked as cut: the second fails on context after the first applies. Each screens green alone. Build one image per package rather than merging by hand unless the merge is the point.

**Alternatives that look additive.** Two packages that both introduce the same vtable (a stepped-many path, for instance) are alternatives, not a stack. Say which one the series would get and keep the other as the fallback package.

## Screening, in cost order

    python scripts/spark-gates.py iter --name <unique> --pin <TF_REF> \
      --dir patches/engine,patches/port-<lever> check fmt ctest --max-load 14

`check fmt ctest` compiles the GLM module and the GPU test binary in roughly 100-330 s; `test` adds about 420 s of host tests and is required whenever the package adds an env row. Quote every step's rc from the log; an absent `error:` line under a failing step is how a red build gets reported as clean.

## Then the measurement, which is the point

The package compiles and its tests pass; that says nothing about the lever. Build an image (`build-image.sh <bare-tag> <src.tar>`, bare tag because the script prefixes the repository), `dist-image.sh <tag>` to all three ranks, verify one image id across three, drop the page cache before every boot, and run the arm with a rule written to a file before the first boot. Two boots a side minimum, unique output labels per boot so a mirrored order does not collide with itself, and digests compared before times.

A lever that loses is a result: record the cells, keep the package out of `patches/engine/`, and let the next port take the boots.
