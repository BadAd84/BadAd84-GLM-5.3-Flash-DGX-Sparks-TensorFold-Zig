#!/usr/bin/env python3
"""Every include and build registration a patch adds is present in the tree.

A three-way re-seat can drop an include hunk while creating the file it names, and nothing that compiles sees it: the
patch's kernel is loaded BY NAME at run time, so the lever silently loads a symbol its fatbin never built. Two were
found that way in the GLM series (glm_index_split, glm_index_sched) and five more by this check.

Run: python scripts/check-patch-includes.py [PATCH_DIR] [TREE]
Exit 0 when every added include is present (or its target file is absent, which the file audit covers), else 1.
"""
import pathlib, re, sys

patch_dir = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "patches/engine")
tree = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else ".")
pat = re.compile(r'^\+\s*#include\s+"([^"]+)"')

missing = []
for p in sorted(patch_dir.glob("*.patch")):
    cur = None
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\+\+\+ b/(\S+)$", line)
        if m:
            cur = m.group(1); continue
        m = pat.match(line)
        if m and cur and cur.endswith((".cu", ".cuh", ".zig")):
            f = tree / cur
            if f.exists() and ('#include "%s"' % m.group(1)) not in f.read_text(encoding="utf-8", errors="replace"):
                missing.append((p.name, cur, m.group(1)))

# A patch can also register a kernel in the build file that the tree lacks, which leaves the kernel compiled nowhere
# and loaded by name at run time into a symbol its fatbin never built. glm_l2pf and glm_onepass_pipe were both that.
build_bt = (tree / "zig/build/cuda_kernels.zig")
if build_bt.exists():
    bt = build_bt.read_text(encoding="utf-8")
    pat_name = re.compile(r'^\+\s*\.\{ \.name = "([^"]+)"')
    for p in sorted(patch_dir.glob("*.patch")):
        cur = None
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\+\+\+ b/(\S+)$", line)
            if m:
                cur = m.group(1); continue
            m = pat_name.match(line)
            if m and cur and cur.endswith("build/cuda_kernels.zig") and ('.name = "%s"' % m.group(1)) not in bt:
                missing.append((p.name, cur, 'build entry "%s"' % m.group(1)))

if missing:
    for name, f, inc in missing:
        print("PATCH-REACH-FAIL: %s adds %s to %s, which the tree lacks" % (name, inc, f))
    sys.exit(1)
print("patch-reach: OK")
