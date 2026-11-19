#!/usr/bin/env python3
"""prompt_trace.py LOG [LOG ...] [--rows N] [--json OUT] - every rank's prompt chunks from TF_GLM_PROF=1 logs, stage
by stage (stdlib only).

Each rank logs, per prompt chunk, `glm prompt chunk rank= slot= start= rows= wall_ms= spans=` and one line per span:
`glm prompt stage rank= slot= start= rows= layer= piece= site= stage= stream=main|side ms=` (zig/src/families/glm/
cuda_prompt_trace.zig). A span is the time between two events on one stream, so a wait span is the stream's blocked
time. Spans nest where the code calls one stage inside another: ffn holds router and experts (cuda_moe.zig),
output_projection holds shared_expert (moe.fill), gate holds control_reduce (the gate's all-reduce) and draw holds
token_gather; a parent is reported exclusive of its children (matched on rank, chunk, layer, site and piece). Layer
kinds are GLM-5.3-Flash's: MLA at 3, 7, ..., 43, dense FFN at layers 0-2.
"""
import argparse
import collections
import json
import re
import sys

MLA = frozenset(range(3, 45, 4))
DENSE = frozenset((0, 1, 2))
NEST = {"ffn": ("router", "experts"), "output_projection": ("shared_expert",), "gate": ("control_reduce",),
        "draw": ("token_gather",)}
CHUNK = re.compile(r"glm prompt chunk rank=(\d+) slot=(\d+) start=(\d+) rows=(\d+) wall_ms=([\d.]+) spans=(\d+)")
STAGE = re.compile(r"glm prompt stage rank=(\d+) slot=(\d+) start=(\d+) rows=(\d+) layer=(\w+) piece=(\w+) "
                   r"site=(\w+) stage=(\w+) stream=(\w+) ms=([\d.]+)")
INVALID = re.compile(r"glm prompt invalid rank=(\d+) slot=(\d+) start=(\d+) rows=(\d+) reason=(\w+)")


def kind(layer, site):
    if site == "chunk":  # the engine logs no layer outside a site, and a site's spans always carry one
        return "chunk"
    if site == "mixer":
        return "mla" if layer in MLA else "kda"
    return "dense" if layer in DENSE else "moe"


def parse(paths):
    """{(rank, slot, start, rows): {"wall": ms, "spans": [(layer, piece, site, stage, stream, ms)]}} and invalid keys."""
    chunks, invalid = {}, []
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = STAGE.search(line)
                if m:
                    key = tuple(int(x) for x in m.group(1, 2, 3, 4))
                    layer = None if m[5] == "null" else int(m[5])
                    piece = None if m[6] == "null" else int(m[6])
                    chunks.setdefault(key, {"wall": None, "spans": []})["spans"].append(
                        (layer, piece, m[7], m[8], m[9], float(m[10])))
                    continue
                m = CHUNK.search(line)
                if m:
                    key = tuple(int(x) for x in m.group(1, 2, 3, 4))
                    chunks.setdefault(key, {"wall": None, "spans": []})["wall"] = float(m[5])
                    continue
                m = INVALID.search(line)
                if m:
                    invalid.append(tuple(int(x) for x in m.group(1, 2, 3, 4)) + (m[5],))
    return chunks, invalid


def exclusive(spans):
    """{(kind, stage, stream): ms} of one chunk, parents less their children."""
    by = collections.defaultdict(float)
    for layer, piece, site, stage, stream, ms in spans:
        by[(layer, piece, site, stage, stream)] += ms
    for (layer, piece, site, stage, stream), ms in list(by.items()):
        for child in NEST.get(stage, ()):
            by[(layer, piece, site, stage, stream)] -= by.get((layer, piece, site, child, stream), 0.0)
    out = collections.defaultdict(float)
    for (layer, piece, site, stage, stream), ms in by.items():
        out[(kind(layer, site), stage, stream)] += ms
    return out


def tables(chunks, rows=None):
    """Per rank: chunk count, mean wall, and mean exclusive ms by (kind, stage, stream) over chunks of `rows` rows."""
    per = collections.defaultdict(lambda: {"n": 0, "wall": 0.0, "stages": collections.defaultdict(float)})
    for (rank, slot, start, nrows), c in sorted(chunks.items()):
        if rows is not None and nrows != rows or c["wall"] is None:
            continue
        p = per[rank]
        p["n"] += 1
        p["wall"] += c["wall"]
        for key, ms in exclusive(c["spans"]).items():
            p["stages"][key] += ms
    out = {}
    for rank, p in per.items():
        n = max(p["n"], 1)
        out[rank] = {"chunks": p["n"], "wall": p["wall"] / n,
                     "stages": {k: v / n for k, v in sorted(p["stages"].items())}}
    return out


def skew(chunks, rows=None):
    """[(slot, start, rows, {rank: wall}, {rank: main-stream waits})] for chunks every rank logged."""
    keys = collections.defaultdict(dict)
    for (rank, slot, start, nrows), c in chunks.items():
        if (rows is None or nrows == rows) and c["wall"] is not None:
            keys[(slot, start, nrows)][rank] = c
    out = []
    for (slot, start, nrows), by in sorted(keys.items()):
        waits = {r: sum(ms for _, _, _, st, stream, ms in c["spans"] if st.startswith("wait") and stream == "main")
                 for r, c in by.items()}
        out.append((slot, start, nrows, {r: c["wall"] for r, c in sorted(by.items())}, waits))
    return out


def report(chunks, invalid, rows=None, out=sys.stdout):
    w = out.write
    t = tables(chunks, rows)
    ranks = sorted(t)
    w(f"prompt chunks{f' of {rows} rows' if rows else ''}: " +
      ", ".join(f"rank {r} {t[r]['chunks']} (wall {t[r]['wall']:.1f} ms a chunk)" for r in ranks) + "\n")
    if invalid:
        w(f"invalid traces: {len(invalid)} ({', '.join(str(x) for x in invalid[:4])})\n")
    keys = sorted({k for r in ranks for k in t[r]["stages"]}, key=lambda k: (k[2], k[0], k[1]))
    w(f"  {'stream':6} {'layer kind':10} {'stage':20} " + " ".join(f"{'rank ' + str(r):>9}" for r in ranks) + "\n")
    for key in keys:
        vals = [t[r]["stages"].get(key, 0.0) for r in ranks]
        if max(vals) >= 0.005:
            w(f"  {key[2]:6} {key[0]:10} {key[1]:20} " + " ".join(f"{v:9.2f}" for v in vals) + "\n")
    for stream in ("main", "side"):
        w(f"  {stream + ' total':38} " + " ".join(
            f"{sum(v for k, v in t[r]['stages'].items() if k[2] == stream):9.2f}" for r in ranks) + "\n")
    sk = skew(chunks, rows)
    if sk and len(ranks) > 1:
        w("  chunk start: wall ms by rank / main-stream waits by rank\n")
        for slot, start, nrows, walls, waits in sk:
            w(f"  {start:9d} {nrows:5d}: " + " ".join(f"{walls[r]:8.1f}" for r in sorted(walls)) + " / " +
              " ".join(f"{waits[r]:7.1f}" for r in sorted(waits)) + "\n")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--rows", type=int, default=None, help="only chunks of this many rows (default: every chunk)")
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    chunks, invalid = parse(a.logs)
    if not chunks:
        print("no glm prompt chunk lines: was the serve booted with TF_GLM_PROF=1?")
        return 1
    report(chunks, invalid, a.rows)
    if a.json:
        t = tables(chunks, a.rows)
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({str(r): {"chunks": v["chunks"], "wall": v["wall"],
                                "stages": {"|".join(k): ms for k, ms in v["stages"].items()}} for r, v in t.items()},
                      fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
