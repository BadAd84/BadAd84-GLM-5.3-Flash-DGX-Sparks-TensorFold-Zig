#!/usr/bin/env python3
"""rebuild_tree.py --tf DIR --recipe DIR --out DIR [--emit DIR]

Rebuilds the tensorfold package of the production image tensorfold-glm53:v110hunt4-shard from this branch and
compares it, file by file, with the image: image-files.sha256 beside this file holds the sha256 of every file under
the image's /usr/local/lib/python3.12/dist-packages/tensorfold (__pycache__ excluded). Needs Linux, GNU patch and
Python 3.8 or later; writes only under --out and --emit. Exit 0 only when every file is equal and present on both
sides.

  --tf      a checkout of ashhart/TensorFold at c4646171139ee8a3c38103eaa1699dad226ec12b (tag v0.6.0)
  --recipe  a checkout of MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold at bf5f94523a82
  --emit    also write the thin layers' inputs: sync-files.tgz (layer B, build_thin.sh) and hunt-files.tgz (layer C,
            build_thin_wheels.sh), paths relative to the package

The inputs and their order are ../patches/SERIES; every input is checked against its sha256 before use. The layers
repeat the image's own build (PRODUCTION.md, section Provenance):
  A  the files pip installed from TensorFold v0.6.0 (RECORD beside this file; each checked against its RECORD hash),
     then `patch -p0 --forward` of the recipe and base lines in name order, as the base build's Dockerfile did
  B  the synced tree: the same installed files, the recipe lines, then the sync lines in SERIES order
     (`patch -p0 --forward --batch`); the files of the four v110sync layers laid whole over A, one file removed
  C  the hunt tree: the synced tree plus the hunt lines (`patch -p0 --batch`, *.orig dropped); every file that
     differs from the synced tree laid whole (checked against the deployed kit's expected-hunt.sha)
  D  `patch -p0 --forward` of the fix lines in name order; E  the same for the shard line
"""
import argparse
import base64
import hashlib
import io
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATCHES = HERE.parent / "patches"
# The four v110sync thin layers, oldest first: the members of v110sync3..6-files.tgz as built (the image's history
# lists the same files), and the one path the first of them removed.
SYNC_LAYERS = [
    "cuda/server.py families/glm5_next/cuda/app.py families/glm5_next/cuda/forward.py "
    "families/glm5_next/cuda/indexer_shard.py families/glm5_next/cuda/multi.py families/glm5_next/cuda/verify.py",
    "cuda/literal_tokens.py cuda/server.py families/glm5_next/cuda/app.py",
    "cuda/comm.py cuda/geometry.py cuda/http.py families/glm5_next/cuda/decode.py families/glm5_next/cuda/dflash2.py "
    "families/glm5_next/cuda/dflash2_multi.py families/glm5_next/cuda/engine.py families/glm5_next/cuda/exl3.cu "
    "families/glm5_next/cuda/exl3_mm.py families/glm5_next/cuda/multi.py families/glm5_next/cuda/sliced_fill.py",
    "cuda/literal_tokens.py cuda/spill_blocks.py families/glm5_next/cuda/app.py families/glm5_next/cuda/multi.py",
]
SYNC_REMOVED = ["families/glm5_next/cuda/prompt_cache.py"]


def die(msg):
    print(f"FAIL {msg}")
    sys.exit(1)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_series(recipe):
    """[(layer, Path, sha256)] in SERIES order, every file present and equal to its recorded hash."""
    out = []
    for line in (PATCHES / "SERIES").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        layer, rel, want = line.split()
        path = (recipe / rel) if layer == "recipe" else (PATCHES / rel)
        if not path.is_file():
            die(f"{layer} {rel}: missing")
        if sha(path.read_bytes()) != want:
            die(f"{layer} {rel}: sha256 differs from SERIES")
        out.append((layer, path, want))
    return out


def check_lists(series):
    """SERIES' sync and hunt order must be the order sync/ORDER and hunt/all6y.list give the other tools."""
    def entries(p):
        return [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.strip().startswith("#")]
    sync = [p.name for layer, p, _ in series if layer == "sync"]
    hunt = [p.relative_to(PATCHES / "hunt").as_posix() for layer, p, _ in series if layer == "hunt"]
    if sync != entries(PATCHES / "sync/ORDER"):
        die("SERIES' sync lines are not sync/ORDER")
    if hunt != entries(PATCHES / "hunt/all6y.list"):
        die("SERIES' hunt lines are not hunt/all6y.list")


def patch(tree, path, *flags):
    with open(path, "rb") as fh:  # a new session: no terminal for patch to ask on, as in a docker build
        r = subprocess.run(["patch", "-p0", *flags], cwd=tree, stdin=fh, capture_output=True, text=True,
                           start_new_session=True)
    if r.returncode != 0:
        die(f"{path.name} in {tree.name}: patch exit {r.returncode}\n{r.stdout}{r.stderr}")
    return [l for l in r.stdout.splitlines() if "offset" in l or "fuzz" in l]


def installed(tf, out):
    """The package as pip installed it: every RECORD file under tensorfold/, each equal to its RECORD hash."""
    if out.exists():
        shutil.rmtree(out)
    n = 0
    for line in (HERE / "RECORD").read_text().splitlines():
        rel, digest, _ = line.rsplit(",", 2)
        if not rel.startswith("tensorfold/") or "/__pycache__/" in rel:
            continue
        data = (tf / "src" / rel).read_bytes()
        got = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        if got != digest:
            die(f"{rel}: not the file pip installed (RECORD {digest}, checkout {got})")
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(data)
        n += 1
    return n


def files(tree):
    out = {}
    for p in sorted((tree / "tensorfold").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            out[p.relative_to(tree).as_posix()] = sha(p.read_bytes())
    return out


def drop_orig(tree):
    for p in tree.rglob("*.orig"):
        p.unlink()
    rej = list(tree.rglob("*.rej"))
    if rej:
        die(f"rejects in {tree.name}: {[str(p) for p in rej]}")


def tgz(path, tree, rels):
    now = int(time.time())
    with tarfile.open(path, "w:gz", format=tarfile.GNU_FORMAT) as tar:
        for rel in sorted(rels):
            data = (tree / "tensorfold" / rel).read_bytes()
            info = tarfile.TarInfo(rel)
            info.size, info.mode, info.mtime, info.uid, info.gid = len(data), 0o644, now, 0, 0
            tar.addfile(info, io.BytesIO(data))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tf", required=True, type=Path)
    ap.add_argument("--recipe", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--emit", type=Path)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    series = read_series(a.recipe)
    check_lists(series)
    by = {k: [p for layer, p, _ in series if layer == k] for k in ("recipe", "base", "sync", "hunt", "fix", "shard")}
    print("inputs: " + ", ".join(f"{k} {len(v)}" for k, v in by.items()) + f" ({len(series)} patches, sha256 checked)")

    img = a.out / "image"
    n = installed(a.tf, img)
    print(f"A: {n} files of TensorFold v0.6.0, each equal to the image's RECORD hash")
    inexact = []  # patch keeps a .orig of a file whose hunks applied with an offset or fuzz: the image holds those too
    for p in sorted(by["recipe"] + by["base"], key=lambda p: p.name):
        if patch(img, p, "--forward"):
            inexact.append(p.name)
    print(f"A: {len(by['recipe'])} recipe + {len(by['base'])} base patches applied in name order; with offset or fuzz: "
          + (", ".join(inexact) or "none"))

    syn = a.out / "synced"
    installed(a.tf, syn)
    for p in by["recipe"] + by["sync"]:
        patch(syn, p, "--forward", "--batch")
    drop_orig(syn)
    laid_b = sorted({f for layer in SYNC_LAYERS for f in layer.split()})
    for f in laid_b:
        shutil.copy2(syn / "tensorfold" / f, img / "tensorfold" / f)
    for f in SYNC_REMOVED:
        (img / "tensorfold" / f).unlink(missing_ok=True)
    print(f"B: synced tree ({len(by['sync'])} sync patches); {len(laid_b)} files laid, {len(SYNC_REMOVED)} removed")

    hun = a.out / "hunt"
    if hun.exists():
        shutil.rmtree(hun)
    shutil.copytree(syn, hun)
    for p in by["hunt"]:
        patch(hun, p, "--batch")
    drop_orig(hun)
    fs, fh = files(syn), files(hun)
    gone = [f for f in fs if f not in fh]
    if gone:
        die(f"the hunt tree removes {gone}: the kit carried no removals")
    laid_c = sorted(f for f in fh if fs.get(f) != fh[f])
    for f in laid_c:
        (img / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(hun / f, img / f)
    kit = {}
    for line in (HERE / "expected-hunt.sha").read_text().splitlines():
        if line.strip():
            h16, rel = line.split(" ", 1)
            kit[rel.strip()] = h16
    mine = {f[len("tensorfold/"):]: fh[f][:16] for f in laid_c}
    if mine != kit:
        die(f"layer C differs from the kit's expected-hunt.sha: {sorted(set(mine.items()) ^ set(kit.items()))}")
    print(f"C: hunt tree ({len(by['hunt'])} patches); {len(laid_c)} files laid, equal to the kit's expected-hunt.sha")

    inexact = [p.name for p in by["fix"] + by["shard"] if patch(img, p, "--forward")]
    print(f"D, E: {len(by['fix'])} fix + {len(by['shard'])} shard patches applied; with offset or fuzz: "
          + (", ".join(inexact) or "none"))

    got = files(img)
    want = {}
    for line in (HERE / "image-files.sha256").read_text().splitlines():
        h, rel = line.split("  ", 1)
        want[rel] = h
    differ = sorted(f for f in want if f in got and got[f] != want[f])
    missing = sorted(f for f in want if f not in got)
    extra = sorted(f for f in got if f not in want)
    same = len(want) - len(differ) - len(missing)
    print(f"compare: image {len(want)} files, rebuilt {len(got)}; equal {same}, differ {len(differ)}, "
          f"missing {len(missing)}, extra {len(extra)}")
    for tag, lst in (("DIFFER", differ), ("MISSING", missing), ("EXTRA", extra)):
        for f in lst:
            print(f"{tag} {f}")
    if a.emit:
        a.emit.mkdir(parents=True, exist_ok=True)
        tgz(a.emit / "sync-files.tgz", syn, laid_b)
        tgz(a.emit / "hunt-files.tgz", hun, [f[len("tensorfold/"):] for f in laid_c])
        (a.emit / "sync-removed.txt").write_text("\n".join(SYNC_REMOVED) + "\n")
        print(f"emitted {a.emit}/sync-files.tgz, hunt-files.tgz, sync-removed.txt")
    if differ or missing or extra:
        sys.exit(1)
    print("PASS the branch rebuilds the image's package byte for byte")


if __name__ == "__main__":
    main()
