"""kcplan.py: the CUDA extensions a tensorfold package builds at run time, read from its own source.

Shared by mkkit.py (laptop: the kernel-cache plan of a stack against its base) and prebuild.py (inside the image:
which loaders to call). One scanner, so the plan and the prebuild cannot disagree on the set.

A loader is a ``load(name="...", sources=...)`` call of tensorfold.cuda.build.load (the package's only JIT path; every
extension goes through it) inside a function of a package module; its sources are the quoted .cu/.cpp/.c file names
between that function's ``def`` and the end of the call (exl3/experts.py builds its list on the line before the call),
resolved against the module's directory. The closure adds every local ``#include "..."`` reached from them, so a
changed header marks every extension compiling it. roce.py's ``proxy_library`` (roce_proxy.c, compiled with the host
C compiler into $TORCH_EXTENSIONS_DIR/roce/roce_proxy-<sha16 of the source>.so) is listed beside them: content-keyed,
it never needs a drop. streaming/build.py (the MLX host-sync module, Apple only) is not a CUDA path and not listed.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field

COMPILED = (".cu", ".cuh", ".cpp", ".cc", ".c", ".h", ".hpp")
SKIP_DIRS = {"__pycache__", ".kc", ".tc"}
_LOAD = re.compile(r"\bload\(\s*name\s*=\s*(f?)\"([^\"]+)\"")
_DEF = re.compile(r"^[ \t]*def[ \t]+(\w+)[ \t]*\(", re.M)
_SRC = re.compile(r"\"([\w./-]+\.(?:cu|cpp|cc|c))\"")
_INC = re.compile(r"^[ \t]*#[ \t]*include[ \t]*\"([^\"]+)\"", re.M)
# the GLM serve's loaders (families/glm5_next imports these shared modules; checked by grep 2026-10-30): every loader
# under families/glm5_next/ is GLM's too. The rest (gdn, exl3/, nvfp4/, nemotron, qwen) belong to other families.
GLM_SHARED = {"cuda/experts.py", "cuda/kernels/qmm.py", "cuda/kernels/prefill_attention.py", "cuda/roce.py"}


@dataclass
class Loader:
    relfile: str                 # the module, relative to the package (posix)
    func: str                    # the function holding the load call (prebuild calls it)
    name: str                    # the extension name (torch's build folder under TORCH_EXTENSIONS_DIR)
    sources: list[str]           # compiled sources, relative to the package
    call: str                    # the call's text (flags included): part of the build's identity
    content_keyed: bool = False  # roce_proxy: its file name carries the source hash
    closure: list[str] = field(default_factory=list)

    @property
    def glm(self) -> bool:
        return self.relfile.startswith("families/glm5_next/") or self.relfile in GLM_SHARED

    @property
    def module(self) -> str:
        return "tensorfold." + self.relfile[:-3].replace("/", ".")


def _files(pkg: str, suffixes: tuple[str, ...]) -> list[str]:
    out = []
    for root, dirs, files in os.walk(pkg):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            if f.endswith(suffixes):
                out.append(os.path.relpath(os.path.join(root, f), pkg).replace(os.sep, "/"))
    return out


def _call_end(text: str, start: int) -> int:
    """Index just past the parenthesis closing the call whose '(' is the first one at or after ``start``."""
    i = text.index("(", start)
    depth = 0
    while i < len(text):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced load( call")


def includes(pkg: str, rel: str, seen: set[str] | None = None) -> set[str]:
    """``rel`` and every local header it includes, transitively (paths relative to the package)."""
    seen = set() if seen is None else seen
    if rel in seen:
        return seen
    seen.add(rel)
    path = os.path.join(pkg, rel)
    with open(path, "rb") as fh:
        text = fh.read().decode("utf-8", "replace")
    for inc in _INC.findall(text):
        cand = os.path.normpath(os.path.join(os.path.dirname(rel), inc)).replace(os.sep, "/")
        if os.path.isfile(os.path.join(pkg, cand)):
            includes(pkg, cand, seen)
        # else a system / torch header (<...> is not matched at all; a quoted one not found here is not ours)
    return seen


def scan(pkg: str) -> list[Loader]:
    """Every run-time CUDA build of the package at ``pkg`` (the directory named tensorfold). Raises on a load call
    whose name or sources it cannot read, so a new loader shape fails loudly instead of being missed."""
    found: list[Loader] = []
    for rel in _files(pkg, (".py",)):
        with open(os.path.join(pkg, rel), encoding="utf-8") as fh:
            text = fh.read()
        if rel == "cuda/build.py":
            continue                      # the loader itself (cpp_extension.load(name=name, ...))
        for m in _LOAD.finditer(text):
            if m.group(1):
                raise ValueError(f"{rel}: an f-string extension name {m.group(2)!r}: the scanner cannot key it")
            defs = [d for d in _DEF.finditer(text) if d.start() < m.start()]
            if not defs:
                raise ValueError(f"{rel}: load(name={m.group(2)!r}) outside a function")
            d = defs[-1]
            end = _call_end(text, m.start())
            span = text[d.start():end]
            srcs = _SRC.findall(span)
            if not srcs:
                raise ValueError(f"{rel}:{d.group(1)}: load(name={m.group(2)!r}) with no readable source names")
            here = os.path.dirname(rel)
            resolved = []
            for s in srcs:
                p = os.path.normpath(os.path.join(here, s)).replace(os.sep, "/")
                if not os.path.isfile(os.path.join(pkg, p)):
                    raise ValueError(f"{rel}:{d.group(1)}: source {s!r} of {m.group(2)!r} not found ({p})")
                if p not in resolved:
                    resolved.append(p)
            found.append(Loader(rel, d.group(1), m.group(2), resolved, text[m.start():end]))
    roce = os.path.join(pkg, "cuda", "roce.py")
    if os.path.isfile(roce):
        with open(roce, encoding="utf-8") as fh:
            rtext = fh.read()
        if "def proxy_library" in rtext:
            src = "cuda/roce_proxy.c"
            with open(os.path.join(pkg, src), "rb") as fh:
                h = hashlib.sha256(fh.read()).hexdigest()[:16]
            found.append(Loader("cuda/roce.py", "proxy_library", f"roce/roce_proxy-{h}.so", [src],
                                "proxy_library: cc -O2 -std=gnu11 -shared -fPIC ... -libverbs -lpthread",
                                content_keyed=True))
    names = [x.name for x in found]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise ValueError(f"extension names loaded from two places: {dup}")
    for x in found:
        c: set[str] = set()
        for s in x.sources:
            includes(pkg, s, c)
        x.closure = sorted(c)
    return found


def digest(pkg: str, rels: list[str]) -> str:
    h = hashlib.sha256()
    for r in sorted(rels):
        with open(os.path.join(pkg, r), "rb") as fh:
            h.update(r.encode() + b"\0" + fh.read() + b"\0")
    return h.hexdigest()


LABEL_RE = re.compile(r"^[0-9a-f]{12}$")   # the recipe's start.sh: KCACHE must match this, else the image id's folder
# Labels a kit must never produce: the synced base's kernel folder (v110sync5/6) and the upstream recipe's patches hash.
RESERVED = frozenset({"c2154670148a", "a1897d591f70"})


def label(pkg: str, reserved=RESERVED) -> str:
    """A kernel-cache label keyed on CONTENT, as 12 lowercase hex digits: the recipe's start.sh mounts the folder
    ``~/.cache/tensorfold-glm53/<tf.patches label>`` only when the label matches ``^[0-9a-f]{12}$`` (it falls back to
    the image id's first 12 hex otherwise: a prefixed label was silently never used). The hash covers every compiled
    source of the package plus every loader's call text (its flags): two packages with the same compiled bytes and flags
    get the same label (their builds are interchangeable), any compiled change a new one. A hash that lands on a
    ``reserved`` label (the base's folder) is re-hashed with a counter, so a kit never shares the base's folder."""
    h = hashlib.sha256(b"tensorfold-glm53 hunt kernel cache\0")
    h.update(digest(pkg, _files(pkg, COMPILED)).encode())
    for x in sorted(scan(pkg), key=lambda y: y.name):
        h.update(f"{x.name}\0{x.call}\0".encode())
    out, n = h.hexdigest()[:12], 0
    while out in reserved:
        n += 1
        out = hashlib.sha256(f"{h.hexdigest()}\0{n}".encode()).hexdigest()[:12]
    assert LABEL_RE.match(out), out
    return out


def plan(new_pkg: str, base_pkg: str) -> list[tuple[Loader, str]]:
    """Each loader of ``new_pkg`` with its status against ``base_pkg``: same | CHANGED (same name, other sources or
    flags: the base's build must not be reused) | NEW-NAME (no base loader of that name: a fresh build). Base loaders
    the new package no longer has come back as (loader, 'GONE')."""
    new, base = scan(new_pkg), {x.name: x for x in scan(base_pkg)}
    out: list[tuple[Loader, str]] = []
    for x in new:
        b = base.pop(x.name, None)
        if b is None:
            out.append((x, "NEW-NAME"))
        elif x.closure != b.closure or x.call != b.call or digest(new_pkg, x.closure) != digest(base_pkg, b.closure):
            out.append((x, "CHANGED"))
        else:
            out.append((x, "same"))
    out += [(b, "GONE") for b in base.values()]
    return out
