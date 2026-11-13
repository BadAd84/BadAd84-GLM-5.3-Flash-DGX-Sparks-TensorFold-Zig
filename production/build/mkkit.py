#!/usr/bin/env python3
"""mkkit.py <stack tree> <base tree> <out dir>: the hunt image's thin-build inputs, from two trees that each hold
``tensorfold/`` (the stack, e.g. work/hunt/stack/all3, and its base, work/hunt/tree = v110sync6's package).

Writes into <out dir> (created; existing kit files are replaced):
  hunt-files.tgz      every file under tensorfold/ that is new or differs from the base, paths relative to the
                      package (``cuda/roce.cu``), as scripts/glm53/v110/sync/build_thin.sh lays them; members root:root
                      0644 with one mtime (this run's), so a laid CUDA source is never older than a build already
                      in a kernel folder
  expected-hunt.sha   build_thin.sh's output format: the sha256's first 16 hex, a space, the package path; sorted
  removed.txt         base files the stack no longer has (must be empty: the run FAILS otherwise, build_thin.sh's
                      remove arguments are not used for the hunt image)
  kcache-label        the hunt image's kernel-cache label: 12 lowercase hex digits (kcplan.label: content of every
                      compiled source + flags; never the base's c2154670148a), the image's tf.patches, which the
                      recipe's start.sh accepts as the kernel folder only in that form
  kcache-plan.txt     every run-time CUDA build of the stack, its sources (with headers) and its status against the base
  kcache-drop.txt     extension names whose sources/flags differ from the base under the SAME name: their folders are
                      deleted from the seeded copy of the base's kernel folder (prepare_kcache.sh), else the base's
                      build of the old sources could be loaded (torch rebuilds by file times alone)
Excluded everywhere: __pycache__/, .kc/, .tc/, *.pyc, *.orig, *.rej. Fails on: a removed file, a laid file holding
CR bytes its base version does not (a Windows patch artifact), and a tgz that does not extract back to the stack's
bytes (checked at the end of every run)."""
from __future__ import annotations

import hashlib
import io
import os
import sys
import tarfile
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcplan  # noqa: E402

EXCL_DIRS = {"__pycache__", ".kc", ".tc"}
EXCL_SUFFIX = (".pyc", ".orig", ".rej")


def tree_files(pkg: str) -> dict[str, str]:
    """relative posix path -> absolute path, every package file but caches and patch leftovers."""
    out = {}
    for root, dirs, files in os.walk(pkg):
        dirs[:] = [d for d in dirs if d not in EXCL_DIRS]
        for f in files:
            if f.endswith(EXCL_SUFFIX):
                continue
            p = os.path.join(root, f)
            if os.path.islink(p):
                raise SystemExit(f"FAIL symlink in the package: {p}")
            out[os.path.relpath(p, pkg).replace(os.sep, "/")] = p
    return out


def read(p: str) -> bytes:
    with open(p, "rb") as fh:
        return fh.read()


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    stack, base, out = (os.path.abspath(a) for a in sys.argv[1:])
    spkg, bpkg = os.path.join(stack, "tensorfold"), os.path.join(base, "tensorfold")
    for p in (spkg, bpkg):
        if not os.path.isdir(p):
            raise SystemExit(f"FAIL no package at {p}")
    sf, bf = tree_files(spkg), tree_files(bpkg)
    removed = sorted(set(bf) - set(sf))
    laid = sorted(r for r in sf if r not in bf or read(sf[r]) != read(bf[r]))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "removed.txt"), "w", newline="\n") as fh:
        fh.write("".join(r + "\n" for r in removed))
    if removed:
        print("FAIL the stack removes base files (build_thin.sh would need them as remove arguments):")
        for r in removed:
            print("  REMOVED", r)
        return 1
    bad_cr = [r for r in laid if b"\r" in read(sf[r]) and (r not in bf or b"\r" not in read(bf[r]))]
    if bad_cr:
        print("FAIL laid files carry CR bytes their base does not (a CRLF artifact of patching on Windows?):")
        for r in bad_cr:
            print("  CR", r)
        return 1

    mtime = int(time.time())
    tgz = os.path.join(out, "hunt-files.tgz")
    tmp = tgz + ".tmp"
    with tarfile.open(tmp, "w:gz", format=tarfile.GNU_FORMAT) as tar:
        for r in laid:
            data = read(sf[r])
            ti = tarfile.TarInfo(r)
            ti.size, ti.mode, ti.mtime = len(data), 0o644, mtime
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = "root"
            tar.addfile(ti, io.BytesIO(data))
    os.replace(tmp, tgz)
    with open(os.path.join(out, "expected-hunt.sha"), "w", newline="\n") as fh:
        for r in laid:
            fh.write(f"{hashlib.sha256(read(sf[r])).hexdigest()[:16]} {r}\n")

    # the kernel-cache plan
    lab = kcplan.label(spkg)
    if not kcplan.LABEL_RE.match(lab) or lab in kcplan.RESERVED:
        print(f"FAIL kernel-cache label {lab!r}: not 12 hex digits, or a reserved (base) label")
        return 1
    rows = kcplan.plan(spkg, bpkg)
    drop = sorted(x.name for x, st in rows if st == "CHANGED" and not x.content_keyed)
    with open(os.path.join(out, "kcache-label"), "w", newline="\n") as fh:
        fh.write(lab + "\n")
    with open(os.path.join(out, "kcache-drop.txt"), "w", newline="\n") as fh:
        fh.write("".join(n + "\n" for n in drop))
    with open(os.path.join(out, "kcache-plan.txt"), "w", newline="\n") as fh:
        fh.write(f"# kernel-cache plan: {stack} against {base}; hunt label {lab} (base: {kcplan.label(bpkg)})\n")
        fh.write("# status | path | extension | loader | sources (with included headers)\n")
        for x, st in rows:
            fh.write(f"{st} | {'glm' if x.glm else 'other'} | {x.name} | {x.relfile}:{x.func} | "
                     f"{' '.join(x.closure)}\n")

    # round trip: extract the archive and compare every member with the stack's bytes
    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(tgz, "r:gz") as tar:
            names = sorted(m.name for m in tar.getmembers())
            if names != laid or any(not m.isfile() for m in tar.getmembers()):
                print("FAIL archive members differ from the laid set")
                return 1
            tar.extractall(td, filter="data")
        for r in laid:
            if read(os.path.join(td, r)) != read(sf[r]):
                print("FAIL round trip:", r)
                return 1
    for r in laid:
        print(("NEW     " if r not in bf else "CHANGED ") + r)
    print(f"ROUNDTRIP OK {len(laid)} files ({os.path.getsize(tgz):,} bytes), 0 removed; label {lab}; "
          f"drop {' '.join(drop) or '(none)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
