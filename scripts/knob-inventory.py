#!/usr/bin/env python3
"""knob-inventory.py [--upstream DIR] - every TF_* setting the engine series adds, one line each: the first patch that mentions it, the patches that do, whether upstream's pin
already has the name (then it is upstream's and is not listed), what scripts/env/prod.env and dev.env set, and the doc row's own text (which states the default).

A name counts as ours when it appears on an added line of a patch in patches/engine/ and the text of upstream's pin (scripts/config.sh TF_REF, under zig/ and docs/ of the clone
given by --upstream, default work/up/TensorFold) does not contain it. Names that are CUDA preprocessor macros (TF_EXL3_OVN_BLOCKS, TF_GLM_HC_*) or a bare prefix (TF_GLM_OVN) match
the pattern and are listed too; the doc row column reads "(no doc row)" for them, and docs/KNOB-PROVENANCE.md names them as not settings.

Read-only. Output is tab separated with a header line. docs/KNOB-PROVENANCE.md quotes its counts from this output."""
import argparse
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKEN = re.compile(r"TF_[A-Z0-9_]+")


def env_map(path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Z][A-Z0-9_]+)=(\S*)", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def series_names(patch_dir):
    """(first patch file name by token, patch numbers by token, doc-row text by token) over the added lines of every patch, in file-name order."""
    first, mentions, rows = {}, {}, {}
    for p in sorted(patch_dir.glob("*.patch")):
        plus = [ln[1:] for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("+") and not ln.startswith("+++")]
        for ln in plus:
            for tok in TOKEN.findall(ln):
                if tok.endswith("_"):
                    continue
                first.setdefault(tok, p.name)
                mentions.setdefault(tok, set()).add(p.name[:4])
            m = re.match(r"\| `(TF_[A-Z0-9_]+)` \| (.*)\|\s*$", ln)
            if m and m.group(1) not in rows:
                rows[m.group(1)] = m.group(2).strip()
    return first, mentions, rows


def at_pin(upstream, pin, tok):
    r = subprocess.run(["git", "grep", "-q", "-F", tok, pin, "--", "zig", "docs"], cwd=upstream, capture_output=True)
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--upstream", default=str(ROOT / "work/up/TensorFold"))
    a = ap.parse_args()
    pin = re.search(r'^TF_REF="?([0-9a-f]{9,40})', (ROOT / "scripts/config.sh").read_text(encoding="utf-8"), re.M).group(1)
    prod, dev = env_map(ROOT / "scripts/env/prod.env"), env_map(ROOT / "scripts/env/dev.env")
    first, mentions, rows = series_names(ROOT / "patches/engine")
    print("knob\tfirst patch\tpatches\tat upstream pin\tprod.env\tdev.env\tdoc row")
    for tok in sorted(first, key=lambda t: (first[t], t)):
        if at_pin(pathlib.Path(a.upstream), pin, tok):
            continue
        print("\t".join([tok, first[tok][:4], ",".join(sorted(mentions[tok])), "no", prod.get(tok, "-"), dev.get(tok, "-"), rows.get(tok, "(no doc row)")[:230]]))


if __name__ == "__main__":
    main()
