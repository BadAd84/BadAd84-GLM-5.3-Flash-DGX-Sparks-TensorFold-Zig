#!/usr/bin/env python3
"""prebuild.py [--all]: inside the hunt image (GPU, the image's kernel folder at /cache), build or load every run-time
CUDA extension the GLM serve uses, through the package's OWN loaders, once; one line each:
  READY <name> <built|loaded> <seconds>s <file>     the loader returned a module (built now, or reused from /cache)
  FAILED <name> <reason>                            the loader raised, or returned None (the lazy CUDA ports log why
                                                    and the serve then runs their Triton fallback: other kernels)
  SKIP <name> (<file>: not a GLM loader)           only without --all: another family's extension
Exit 1 if any FAILED, or before any build when a stale torch build lock sits in the extension folder (a killed build
leaves one, and every start then waits on it forever).

The set comes from kcplan.scan over the INSTALLED package (the loaders the image will run), not from a list kept here.
Cache folders: torch's TORCH_EXTENSIONS_DIR (the image sets /cache/torch_extensions; tensorfold.cuda.build.load passes
no build_directory, so each extension builds in $TORCH_EXTENSIONS_DIR/<name>), roce's proxy in
$TORCH_EXTENSIONS_DIR/roce (roce._cache_dir), Triton's in TRITON_CACHE_DIR (/cache/triton; JIT kernels compile at
first launch, not here). Refuses to run when TORCH_EXTENSIONS_DIR is not under /cache (an image without the recipe's
ENV would build into the container and lose everything at exit).

  docker run --rm --gpus all --network none -v $HOME/.cache/tensorfold-glm53/<label>:/cache -v <kit>:/kit:ro \\
    --entrypoint python3 tensorfold-glm53:v110hunt1 /kit/prebuild.py"""
from __future__ import annotations

import glob
import importlib
import importlib.util
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcplan  # noqa: E402


def reason(exc: BaseException) -> str:
    lines = [ln for ln in str(exc).strip().splitlines() if ln.strip()]
    return f"{type(exc).__name__}: {lines[-1][:300] if lines else ''}"


def main() -> int:
    every = "--all" in sys.argv[1:]
    ext_dir = os.environ.get("TORCH_EXTENSIONS_DIR", "")
    print(f"TORCH_EXTENSIONS_DIR={ext_dir or '(unset)'} TRITON_CACHE_DIR={os.environ.get('TRITON_CACHE_DIR', '(unset)')}",
          flush=True)
    if not ext_dir.startswith("/cache/") and "--any-dir" not in sys.argv[1:]:
        print("FAILED precondition: TORCH_EXTENSIONS_DIR is not under /cache (the image's ENV is missing or "
              "overridden); --any-dir to build there anyway", flush=True)
        return 1
    locks = sorted(glob.glob(os.path.join(ext_dir, "*", "lock")))
    if locks:
        for lk in locks:
            print(f"FAILED precondition: stale build lock {lk} (no build may run now: delete it, then rerun)",
                  flush=True)
        return 1
    import torch

    if not torch.cuda.is_available():
        print("FAILED precondition: no CUDA device (docker run --gpus all)", flush=True)
        return 1
    cap = torch.cuda.get_device_capability()
    pkg = os.path.dirname(importlib.util.find_spec("tensorfold").origin)
    print(f"package {pkg}, GPU {torch.cuda.get_device_name()} sm_{cap[0]}{cap[1]}, torch {torch.__version__}",
          flush=True)
    loaders = kcplan.scan(pkg)
    failed = 0
    for x in loaders:
        if not (every or x.glm):
            print(f"SKIP {x.name} ({x.relfile}: not a GLM loader; --all builds it)", flush=True)
            continue
        target = (os.path.join(ext_dir, x.name) if x.content_keyed
                  else os.path.join(ext_dir, x.name, x.name + ".so"))
        before = os.path.getmtime(target) if os.path.exists(target) else None
        t0 = time.time()
        try:
            mod = importlib.import_module(x.module)
            res = getattr(mod, x.func)()
        except BaseException as exc:  # noqa: BLE001 - one line a loader, the others still run
            failed += 1
            print(f"FAILED {x.name} {reason(exc)}", flush=True)
            traceback.print_exc(limit=3)
            continue
        dt = time.time() - t0
        if res is None:
            why = [f"{k}={v}" for k, v in vars(mod).items() if k.endswith("_FAILED") and isinstance(v, str)]
            failed += 1
            print(f"FAILED {x.name} the loader returned None (the serve falls back to Triton): "
                  f"{'; '.join(why) or 'no reason recorded'}", flush=True)
            continue
        path = getattr(res, "__file__", None) or getattr(res, "_name", "?")
        mname = getattr(res, "__name__", "")
        if not x.content_keyed and mname != x.name:
            failed += 1
            print(f"FAILED {x.name} loaded as {mname!r} (a versioned rebuild: two sources under one name in this "
                  f"process?)", flush=True)
            continue
        if not x.content_keyed and not str(path).startswith(ext_dir):
            failed += 1
            print(f"FAILED {x.name} loaded from {path}, outside {ext_dir}", flush=True)
            continue
        after = os.path.getmtime(target) if os.path.exists(target) else None
        state = "loaded" if before is not None and after == before else "built"
        print(f"READY {x.name} {state} {dt:.1f}s {path}", flush=True)
    print(f"prebuild: {failed} FAILED", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
