---
name: gate-cu-kernels-after-a-zig-tensorfold-port
description: "After porting TensorFold Flash Next (Zig + .cu) patches by 3-way merge, catch the boot-only defects the host suite cannot see: dropped instantiations, orphaned macros, wrong mangled-name tails, wrong module handles."
---

# Gate .cu kernels and symbol names after a Zig/TensorFold port

`zig build test` green (even 276/276 + seam 33/33) proves nothing about the CUDA half: the host suite never
compiles `.cu` files and never resolves kernel symbols. Three defects measured on one port (fp4port, 2026-11-07),
each found only by building an image and booting it:

1. A 3-way merge silently DROPPED whole blocks of explicit instantiation lines (`TF_QMMF(3, 16, false, false, false)`
   x28 and `TF_QMMF_LD(...)` x14). Boot error: `cuModuleGetFunction: CUDA_ERROR_NOT_FOUND ... kernel symbol not in
   module: _ZN10tf_fn_qmmf11qmmf_kernelILi3ELi16ELi64ELi1ELi4ELi4ELb0ELb0ELb0EE...` - the template args in the
   mangled name tell you exactly which instantiation is missing.
2. Orphaned macro continuation lines (a `    CLUSTER, FUSE>(const __nv_bfloat16*, ...);` with no `#define` opener):
   nvcc `this declaration has no storage class or type specifier` at image build.
3. A hand-copied mangled name string in `cuda_fp8.zig` with the wrong parameter TAIL (`fPKvPfiiiiiii` = const void* + 7
   ints, the fn_qmmf shape, where the fn_qmmf_ld kernel takes `fPvPfiiiiiiii` = void* + 8 ints), and the lookup done
   on the wrong module handle (`k.module.function(sym.ld_...)` instead of `k.ld_module`).

## Diagnose a `CUDA_ERROR_NOT_FOUND` at boot

- Demangle by eye: `ILi3ELi16ELi64ELi1ELi4ELi4ELb0ELb0ELb1EE` = `<3,16,64,1,4,4,false,false,true>`; the tail after
  `EEEv` is the parameter list (`PKv` const void*, `Pv` void*, count the `i`s).
- `git log -S'TF_QMMF(3, 16' -- zig/kernels/cuda/fn_qmmf.cu` and `git show <parent>:<file> | grep -nE '^TF_QMMF'`
  to see which commit dropped lines; restore verbatim from the pre-port tree, and check the ORIGINAL upstream patch
  (`upstream/*/pr.diff`) removed nothing (`grep -nE '^-TF_QMMF\('`).
- Prove what the IMAGE carries, not the tree: the fatbins are EMBEDDED in `tensorfold-native` via `@embedFile`
  (`zig/src/cuda/kernels.zig` `Blob("fatbin_<name>")`), so the loose `/opt/tensorfold/fatbin/*.fatbin` on disk is
  the BASE image's leftover and irrelevant. Check the binary: `cuobjdump -symbols /opt/tensorfold/native/bin/tensorfold-native`
  (0 symbols there means the blob is compressed; then fresh-compile instead).
- Fresh compile of HEAD's file with the build's exact flags (from `zig/build/cuda.zig` `torch_flags` + the kernel's
  flags + one `-gencode`):
  `nvcc -fatbin -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__
  -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -std=c++20 -O3 -gencode=arch=compute_121a,code=sm_121a -o k.fatbin <file>.cu`
  then `cuobjdump -symbols k.fatbin | grep <mangled>`; if the symbol IS there, the Zig name string or module handle is wrong.
- `fn_qmmf_ld.cu` is GENERATED (`tools/zig/flashnext_qmmf_ld.py`, header says do not edit by hand); run its `--check`;
  a port that adds instantiations to the .cu must extend the generator's FOOTER too or they vanish on regeneration.

## Gate (add to the lane's test.sh, judged by exit code)

1. `git diff <recipe tip> HEAD -- '*.cu' '*.cuh' | grep -cE '^-(TF_|#define TF_)'` must be 0 (no instantiation or
   define line vanishes since the base).
2. Every `.cu` changed since the base compiles to a fatbin under the base image (`nvcr.io/nvidia/pytorch:26.07-py3`
   has nvcc 13.3) with the flags above.
3. `grep -cE 'k\.module\.function\(sym\.ld_' cuda_fp8.zig` must be 0 (every `sym.ld_*` resolves in `k.ld_module`).
4. Pin EVERY symbol-name array with an `expectEqualStrings` test (the existing tests pinned `ld_fused2` but not
   `ld_fuse_s`, which is how defect 3 shipped).

A boot in a serve window is still the final gate: `fp4qual.sh <label> int4 golden,exact` with `WAIT_TIMEOUT=3600`.
