---
name: diagnose-missing-kernel-symbol-in-ported-engine
description: "Boot dies at kernel load with 'kernel symbol not in module X' after a port/merge: scan requested names vs sources, find the wrong caller, restore the type guard."
---

# Diagnose a missing kernel symbol in a ported engine

Symptom: the image builds and passes host/contract gates, but the serve dies seconds into startup:

    error: cuModuleGetFunction: CUDA_ERROR_NOT_FOUND (500) named symbol not found
    error: kernel symbol not in module: <name>

## 1. Read the name literally

The message prints the exact string passed to `module.function(X)`. If the name has no suffix
while the real kernels are suffixed (`tf_glm_router16` vs `tf_glm_router16_s3`/`_s4`), the
requester is NOT the suffixed call site you can see; find the one passing the bare name.

## 2. Scan every requested kernel name against the sources

    python3 - <<'EOF'
    import re, glob
    src = ''.join(open(f, encoding='utf-8', errors='ignore').read()
                  for f in glob.glob('zig/kernels/cuda/*.cu') + glob.glob('zig/kernels/cuda/*.cuh'))
    req = set()
    for f in glob.glob('zig/src/families/<family>/*.zig'):
        s = open(f, encoding='utf-8').read()
        req |= {m.group(1) for m in re.finditer(r'"((?:tf_\w+|glm_\w+))"', s) if m.group(1).startswith('tf_')}
    print(sorted(n for n in req if n not in src))
    EOF

Absent names are either (a) genuine gaps to port from the source era, or (b) names built at
runtime by `"prefix" ++ field_name`.

## 3. Check the built binary as corroboration

    docker run --rm --entrypoint bash IMAGE -c 'strings /opt/tensorfold/bin/tensorfold | grep -o KEYWORD[a-z0-9_]* | sort -u'

No literal at all despite it existing in source = runtime concatenation, which points at a
reflective loop, not a direct call.

## 4. The reflective loop bug (the one measured case)

    inline for (@typeInfo(Kernels).@"struct".field_names, 0..) |name, i|
        @field(k, name) = if (i < from or ovn) try m.function("tf_glm_" ++ name) else ...;

Any field whose kernel name is not exactly `tf_glm_<field>` (e.g. an OPTIONAL field set later from
a suffixed kernel, `router16: ?cuda.Function`) gets a bogus request. The source era guards it:

    if (@FieldType(Kernels, name) == cuda.Function) @field(k, name) = ...;

Restore that guard as a numbered patch and re-verify: the knob-set boot (`KNOBS=measured`) must
pass kernel load before any benchmark of it counts.

## 5. Port the genuinely missing kernels verbatim

For a real gap, lift the block from the source-era .cuh/.cu (check every helper it calls already
exists in the ported header: cp16s, commit, wait, ldm4s, ldm2s, mma16816), insert it at the
matching namespace position, and record the finding in the ledger with the scan command, because
every newly enabled knob is a chance to hit the same class.
