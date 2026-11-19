#!/usr/bin/env python3
"""prefill_stages.py SQLITE [--gap S] [--json OUT] [--layers] - rank 0's cold prompt passes, stage by stage, from an
Nsight Systems export of the GLM Zig serve (read-only on the export; stdlib only).

The main stream is the one carrying tf_glm_put_words, which starts every lane step. A prompt pass starts at a
tf_glm_embed_b16 whose next main-stream kernel is a glue kernel, and is a prompt pass when its kernels include the EXL3
prompt experts (tf_exl3_prompt_gu, tf_exl3_prompt_down). Its head is the run of put_words, broadcast and all-reduce
kernels just before the embed (the chunk gate's all-reduces). Inside the pass the glue kernels (tf_glm_hc_*,
tf_glm_stream_mean) come in runs, one a site: run 0 is layer 0's hc_pre, then each site's compute is followed by its
glue run (mixer site, FFN site; 45 layers: 91 runs). Site s is layer s // 2, its mixer when s is even. MLA layers are
3, 7, ..., 43 and dense FFN layers 0-2 (GLM-5.3-Flash's config). After the last glue run come the head, the draw, the
drafter's prompt ingest and the commit (the tail). Passes form a request until a decode step or an idle of --gap s.

Busy is the union of the main stream's kernels, copies and memsets. Each idle gap on the main stream is named by what
follows it: a glue kernel (wait_exchange: the piece's partials), the first compute kernel after a glue run
(wait_share: the glued rows), the embed (gate_gap: the host's synchronize after the gate and its next launches), or
any other kernel (launch_gap). The side stream is every other stream with NCCL kernels inside the pass; exposed is the
part of its NCCL time when the main stream is idle.
"""
import argparse
import collections
import json
import re
import sqlite3
import sys

LAYERS = 45
MLA = frozenset(range(3, 45, 4))
DENSE = frozenset((0, 1, 2))
GLUE = re.compile(r"^tf_glm_(hc_|stream_mean)")
EXPERTS = frozenset(("tf_exl3_prompt_gu", "tf_exl3_prompt_down"))
HEAD_KERNELS = re.compile(r"^(tf_glm_put_words|ncclDevKernel_(AllReduce|Broadcast))")
SYNC_APIS = ("cuStreamSynchronize", "cuCtxSynchronize", "cuEventSynchronize", "cudaStreamSynchronize",
             "cudaDeviceSynchronize")

# kernel name -> category; first match wins
CATEGORIES = (
    ("nccl", lambda n: n.startswith(("ncclDevKernel_", "tp_roce"))),
    ("embed", lambda n: n == "tf_glm_embed_b16"),
    ("glue", lambda n: GLUE.match(n) is not None),
    ("experts", lambda n: n.startswith("tf_exl3_") or n == "plan_kernel"),
    ("combine", lambda n: n in ("tf_glm_put_slot", "tf_glm_combine")),
    ("router", lambda n: n.startswith(("tf_glm_router", "tf_glm_slice_sum", "tf_glm_topk"))),
    ("kda", lambda n: n.startswith(("tf_glm_kda", "glm_kda", "tf_glm_conv_shift"))),
    ("index", lambda n: n.startswith(("tf_glm_index", "tf_glm_pool_keys", "tf_glm_scores", "tf_glm_select",
                                      "glm_index", "tf_glm_tokens", "tf_glm_dsa_tokens"))),
    ("attention", lambda n: n.startswith(("tf_glm_chunks", "tf_glm_merge", "glm_onepass", "tf_glm_sparse",
                                          "tf_glm_dense", "tf_glm_onepass", "tf_glm_lat_write", "tf_glm_absorb",
                                          "tf_glm_expand"))),
    ("matmul", lambda n: n.startswith(("glm_mm", "qmm", "tf_qmm", "group_kernel", "tf_glm_mm", "tf_nvfp4",
                                       "tf_glm_swiglu")) or "gemm" in n),
    ("norm", lambda n: n.startswith("tf_glm_rmsnorm")),
    ("taps", lambda n: n == "df_tap"),
    ("drafter", lambda n: n.startswith("df_")),
    ("other", lambda n: True),
)
# a category's name inside a site of each kind (what the kernel does there)
RENAME = {
    "kda": {"matmul": "kda_proj", "kda": "kda_chain"},
    "mla": {"matmul": "mla_proj", "norm": "mla_proj", "router": "mla_index", "index": "mla_index",
            "attention": "mla_attn", "nccl": "mla_nccl"},
    "dense": {"matmul": "dense_mlp"},
    "moe": {"router": "moe_router", "experts": "moe_experts", "matmul": "moe_shared", "combine": "moe_combine"},
}
KINDS = (("kda", "KDA mixer", 34), ("mla", "MLA mixer", 11), ("dense", "dense FFN", 3), ("moe", "MoE FFN", 42))


def category(name, memo={}):
    c = memo.get(name)
    if c is None:
        c = memo[name] = next(cat for cat, test in CATEGORIES if test(name))
    return c


def site_kind(s):
    """(layer, kind) of site s: kinds kda / mla for a mixer site, dense / moe for an FFN site."""
    layer = s // 2
    if s % 2 == 0:
        return layer, "mla" if layer in MLA else "kda"
    return layer, "dense" if layer in DENSE else "moe"


def union_len(iv, lo=None, hi=None):
    """Length of the union of [s, e) intervals, clipped to [lo, hi) when given."""
    tot, cs, ce = 0, None, None
    for s, e in sorted(iv):
        if lo is not None:
            s, e = max(s, lo), min(e, hi)
        if e <= s:
            continue
        if ce is None or s > ce:
            if ce is not None:
                tot += ce - cs
            cs, ce = s, e
        else:
            ce = max(ce, e)
    if ce is not None:
        tot += ce - cs
    return tot


def merged(iv):
    out = []
    for s, e in sorted(iv):
        if e <= s:
            continue
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def overlap_len(a, b):
    """Length of the intersection of two interval unions."""
    a, b = merged(a), merged(b)
    i = j = tot = 0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if hi > lo:
            tot += hi - lo
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return tot


def has_table(c, name):
    return c.execute("select count(*) from sqlite_master where type='table' and name=?", (name,)).fetchone()[0] > 0


def load(path):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        names = dict(c.execute("select id, value from StringIds"))
        ks = [(s, e, st, names.get(n, str(n)), gx, gy) for s, e, st, n, gx, gy in c.execute(
            "select start, end, streamId, shortName, gridX, gridY from CUPTI_ACTIVITY_KIND_KERNEL order by start")]
        copies = []
        if has_table(c, "CUPTI_ACTIVITY_KIND_MEMCPY"):
            copies += [(s, e, st, b, "copy") for s, e, st, b in c.execute(
                "select start, end, streamId, bytes from CUPTI_ACTIVITY_KIND_MEMCPY")]
        if has_table(c, "CUPTI_ACTIVITY_KIND_MEMSET"):
            copies += [(s, e, st, b, "memset") for s, e, st, b in c.execute(
                "select start, end, streamId, bytes from CUPTI_ACTIVITY_KIND_MEMSET")]
        syncs = []
        if has_table(c, "CUPTI_ACTIVITY_KIND_RUNTIME"):
            ids = [i for i, v in names.items() if v.split("_v")[0] in SYNC_APIS]
            if ids:
                q = "select start, end from CUPTI_ACTIVITY_KIND_RUNTIME where nameId in (%s)" % ",".join("?" * len(ids))
                syncs = c.execute(q, ids).fetchall()
    finally:
        c.close()
    return ks, sorted(copies), sorted(syncs)


def find_passes(main):
    """[(head_index, embed_index, end_index, embeds)] of every prompt pass in the main stream's kernel list. A paired
    step (TF_GLM_PROMPT_PAIR) embeds its two chunks back to back with their glue on the side stream: its embeds are
    one pass, of both chunks' rows."""
    starts = []
    for i, k in enumerate(main):
        if k[3] == "tf_glm_embed_b16" and i + 1 < len(main) and GLUE.match(main[i + 1][3]):
            h = i
            while h > 0 and HEAD_KERNELS.match(main[h - 1][3]):
                h -= 1
            starts.append((h, i))
    out, embeds = [], []
    for n, (h, i) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(main)
        # a pass ends at its own lane step's end: the next put_words that is not this pass's head
        for j in range(i + 1, end):
            if main[j][3] == "tf_glm_put_words":
                end = j
                break
        if embeds and embeds[-1][1] == h and h == i:  # a paired step's second chunk: no step marker or gate of its own
            h = embeds[-1][0]
        else:
            embeds = []
        embeds.append((h, end, i))
        if any(main[j][3] in EXPERTS for j in range(i, end)):
            out.append((h, embeds[0][2], end, [x[2] for x in embeds]))
            embeds = []
    return out


def segment(ks):
    """Glue runs of a pass's kernels from its embed on: [(first, last)] indexes into ks."""
    runs, i = [], 0
    while i < len(ks):
        if GLUE.match(ks[i][3]):
            j = i
            while j + 1 < len(ks) and GLUE.match(ks[j + 1][3]):
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    return runs


def analyse_pass(main, copies, side, syncs, h, i, end, embeds=None):
    head, body = main[h:i], main[i:end]
    t0 = head[0][0] if head else body[0][0]
    t1 = max(k[1] for k in body)
    stream = main[0][2]
    mine = [(s, e, b, kind) for s, e, st, b, kind in copies if st == stream and t0 <= s < t1]
    copy_iv = [(s, e) for s, e, b, kind in mine]
    busy_iv = [(k[0], k[1]) for k in head + body] + copy_iv
    embeds = embeds or [i]
    rec = {"rows": sum(main[x][4] for x in embeds), "chunks": len(embeds), "t0": t0, "t1": t1, "span": t1 - t0,
           "busy": union_len(busy_iv), "ms": collections.Counter(), "n": collections.Counter(),
           "names": collections.Counter()}
    ms, n = rec["ms"], rec["n"]
    for k in head:
        key = "head_" + ("gate" if "AllReduce" in k[3] else "step")
        ms[key] += k[1] - k[0]
        n[key] += 1
    runs = segment(body)
    rec["glue_runs"] = len(runs)
    rec["segmented"] = len(runs) >= 2 * LAYERS + 1
    role = ["pre"] * len(body)  # embed and run 0: the pass's front
    where = [None] * len(body)  # (layer, kind) of a site's compute and glue
    if rec["segmented"]:
        for s in range(2 * LAYERS):
            lk = site_kind(s)
            for j in range(runs[s][1] + 1, runs[s + 1][0]):
                role[j], where[j] = "compute", lk
            for j in range(runs[s + 1][0], runs[s + 1][1] + 1):
                role[j], where[j] = "glue", lk
        for j in range(runs[2 * LAYERS][1] + 1, len(body)):
            role[j] = "tail"
    else:
        for j in range(len(body)):
            role[j] = "glue" if GLUE.match(body[j][3]) else ("pre" if j == 0 else "compute")
    layer_ms = collections.defaultdict(float)
    kind_wait = collections.defaultdict(float)
    prev_end = head[-1][1] if head else body[0][0]
    ci = 0
    for j, k in enumerate(body):
        d = k[1] - k[0]
        cat = category(k[3])
        if role[j] == "compute":
            kind = where[j][1] if where[j] else "unsegmented"
            key = RENAME.get(kind, {}).get(cat, kind + "_" + cat)
            if where[j]:
                layer_ms[where[j]] += d
        elif role[j] == "glue":
            key = "glue"
            if where[j]:
                layer_ms[where[j]] += d
        elif role[j] == "tail":
            key = "tail_" + cat
        else:
            key = "front_" + cat
        ms[key] += d
        n[key] += 1
        rec["names"][k[3]] += d
        # idle before this kernel: from the main stream's last end, less its copies and memsets in between
        gap = k[0] - prev_end
        while ci < len(copy_iv) and copy_iv[ci][0] < k[0]:
            if gap > 0:
                gap -= max(0, min(copy_iv[ci][1], k[0]) - max(copy_iv[ci][0], prev_end))
            prev_end = max(prev_end, copy_iv[ci][1])
            ci += 1
        if gap > 0:
            if j == 0:
                gk = "gate_gap"
            elif role[j] == "glue":
                gk = "wait_exchange"
                if where[j]:
                    kind_wait[(where[j][1], "exchange")] += gap
            elif role[j] in ("compute", "tail") and role[j - 1] == "glue":
                gk = "wait_share"
                if where[j - 1]:
                    kind_wait[(where[j - 1][1], "share")] += gap
            else:
                gk = "launch_gap"
            ms[gk] += gap
            n[gk] += 1
        prev_end = max(prev_end, k[1])
    for s, e, b, kind in mine:
        ms["main_" + kind] += e - s
        n["main_" + kind] += 1
        ms["main_" + kind + "_bytes"] += b
    rec["kind_wait"] = {f"{k}:{w}": v / 1e6 for (k, w), v in kind_wait.items()}
    sk = [k for k in side if t0 <= k[0] < t1]
    nccl = [(k[0], k[1]) for k in sk if k[3].startswith("ncclDevKernel_")]
    main_busy = merged(busy_iv)
    idle, cur = [], t0
    for s, e in main_busy:
        if s > cur:
            idle.append((cur, s))
        cur = max(cur, e)
    if cur < t1:
        idle.append((cur, t1))
    rec["side"] = {"nccl": len(nccl), "nccl_ms": sum(e - s for s, e in nccl) / 1e6,
                   "nccl_union_ms": union_len(nccl) / 1e6, "exposed_ms": overlap_len(nccl, idle) / 1e6,
                   "busy_ms": union_len([(k[0], k[1]) for k in sk]) / 1e6}
    rec["syncs"] = sum(1 for s, e in syncs if t0 <= s < t1)
    rec["sync_ms"] = sum(min(e, t1) - s for s, e in syncs if t0 <= s < t1) / 1e6
    rec["layers"] = {f"{lk[0]}:{lk[1]}": v / 1e6 for lk, v in sorted(layer_ms.items())}
    rec["ms"] = {k: (v / 1e6 if not k.endswith("_bytes") else v) for k, v in ms.items()}
    rec["n"] = dict(n)
    rec["names"] = {k: v / 1e6 for k, v in rec["names"].most_common()}
    return rec


def decode_steps(main):
    """Start times of main-stream steps that are not prompt passes (verify, drafter, keep)."""
    pw = [j for j, k in enumerate(main) if k[3] == "tf_glm_put_words"]
    out = []
    for a, b in zip(pw, pw[1:] + [len(main)]):
        names = {k[3] for k in main[a:b]}
        if not names & EXPERTS and ("tf_glm_embed_b16" in names or any(x.startswith("df_") for x in names)):
            out.append(main[a][0])
    return out


def analyse(path, gap_s=1.0):
    ks, copies, syncs = load(path)
    counts = collections.Counter(k[2] for k in ks if k[3] == "tf_glm_put_words")
    if not counts:
        raise SystemExit(f"{path}: no tf_glm_put_words kernel: not a capture of the GLM Zig serve's rank 0")
    stream = counts.most_common(1)[0][0]
    main = [k for k in ks if k[2] == stream]
    nccl_streams = {k[2] for k in ks if k[2] != stream and k[3].startswith("ncclDevKernel_")}
    side = [k for k in ks if k[2] in nccl_streams]
    passes = [analyse_pass(main, copies, side, syncs, h, i, e, em) for h, i, e, em in find_passes(main)]
    decodes = decode_steps(main)
    reqs, cur = [], []
    for p in passes:
        if cur and (any(cur[-1]["t1"] <= t < p["t0"] for t in decodes) or p["t0"] - cur[-1]["t1"] > gap_s * 1e9):
            reqs.append(cur)
            cur = []
        cur.append(p)
    if cur:
        reqs.append(cur)
    return {"path": path, "main_stream": stream, "side_streams": sorted(nccl_streams), "requests": reqs}


def summarize(req):
    """A request's sums and means over its passes."""
    keys = sorted({k for p in req for k in p["ms"] if not k.endswith("_bytes")})
    tot = {k: sum(p["ms"].get(k, 0) for p in req) for k in keys}
    rows = sum(p["rows"] for p in req)
    span = (req[-1]["t1"] - req[0]["t0"]) / 1e6
    side = {k: sum(p["side"][k] for p in req) for k in req[0]["side"]}
    return {"passes": len(req), "rows": rows, "rows_each": [p["rows"] for p in req], "span_ms": span,
            "pass_span_ms": sum(p["span"] for p in req) / 1e6, "busy_ms": sum(p["busy"] for p in req) / 1e6,
            "between_passes_ms": span - sum(p["span"] for p in req) / 1e6, "ms": tot, "side": side,
            "segmented": sum(p["segmented"] for p in req), "syncs": sum(p["syncs"] for p in req),
            "sync_ms": sum(p["sync_ms"] for p in req),
            "memset_bytes": sum(p["ms"].get("main_memset_bytes", 0) for p in req)}


GROUPS = (
    ("gate (all-reduces at a pass's head)", ("head_gate",)),
    ("host gap after the gate", ("gate_gap",)),
    ("step marker (put_words, broadcast)", ("head_step",)),
    ("front: embed, layer 0's hc_pre", ("front_",)),
    ("KDA mixer: projections, o_proj", ("kda_proj",)),
    ("KDA mixer: chain", ("kda_chain",)),
    ("KDA mixer: other", ("kda_",)),
    ("MLA mixer: projections, norms, o_proj", ("mla_proj",)),
    ("MLA mixer: indexer", ("mla_index",)),
    ("MLA mixer: attention, absorb, expand", ("mla_attn",)),
    ("MLA mixer: NCCL (index split)", ("mla_nccl",)),
    ("MLA mixer: other", ("mla_",)),
    ("dense FFN: MLP", ("dense_mlp",)),
    ("dense FFN: other", ("dense_",)),
    ("MoE FFN: router", ("moe_router",)),
    ("MoE FFN: routed experts", ("moe_experts",)),
    ("MoE FFN: shared expert", ("moe_shared",)),
    ("MoE FFN: combine", ("moe_combine",)),
    ("MoE FFN: other", ("moe_",)),
    ("glue (hc_post, hc_pre)", ("glue",)),
    ("wait: partials exchange", ("wait_exchange",)),
    ("wait: glued rows share", ("wait_share",)),
    ("launch gaps", ("launch_gap",)),
    ("tail: head, draw, drafter, commit", ("tail_",)),
    ("main-stream copies and memsets", ("main_copy", "main_memset")),
    ("unsegmented compute", ("unsegmented",)),
)


def grouped(ms):
    """(label, ms) for GROUPS, each key counted once (exact names first, then prefixes in order)."""
    left = {k: v for k, v in ms.items() if not k.endswith("_bytes")}
    out = []
    for label, keys in GROUPS:
        v = 0.0
        for key in keys:
            for k in [k for k in left if k == key]:
                v += left.pop(k)
        for key in keys:
            for k in [k for k in left if k.startswith(key)]:
                v += left.pop(k)
        out.append((label, v))
    out.append(("anything else", sum(left.values())))
    return out


def report(res, show_layers=False, out=sys.stdout):
    w = out.write
    w(f"{res['path']}: main stream {res['main_stream']}, side streams {res['side_streams']}, "
      f"{len(res['requests'])} requests\n")
    for r, req in enumerate(res["requests"], 1):
        s = summarize(req)
        rows = max(s["rows"], 1)
        each = s["rows_each"]
        w(f"\nrequest {r}: {s['passes']} passes, {s['rows']} rows ({', '.join(map(str, each[:8]))}"
          f"{' ...' if len(each) > 8 else ''}), GPU span {s['span_ms']:.1f} ms = {1e3 * s['span_ms'] / rows:.1f} us "
          f"a row; passes {s['pass_span_ms']:.1f} ms, between passes {s['between_passes_ms']:.1f} ms; "
          f"{s['segmented']}/{s['passes']} passes cut into 45 layers (91 glue runs or more)\n")
        w(f"  {'stage':42} {'ms':>10} {'ms a pass':>10} {'us a row':>9} {'share':>6}\n")
        for label, v in grouped(s["ms"]):
            if v > 0:
                w(f"  {label:42} {v:10.1f} {v / s['passes']:10.2f} {1e3 * v / rows:9.2f} "
                  f"{100 * v / s['pass_span_ms']:5.1f}%\n")
        idle = s["pass_span_ms"] - s["busy_ms"]
        w(f"  {'main-stream busy / idle':42} {s['busy_ms']:10.1f} / {idle:.1f} ms\n")
        sd = s["side"]
        w(f"  side-stream NCCL: {sd['nccl']} kernels, {sd['nccl_ms']:.1f} ms ({sd['nccl_union_ms']:.1f} ms union), "
          f"exposed while the main stream idles {sd['exposed_ms']:.1f} ms\n")
        w(f"  host synchronizes inside the passes: {s['syncs']} ({s['sync_ms']:.1f} ms); main-stream memset bytes "
          f"{s['memset_bytes'] / 2**20:.1f} MiB\n")
        w("  per layer kind, a pass: compute + glue (ms a layer); waits on the exchange and the share\n")
        for kind, label, count in KINDS:
            v = sum(val for p in req for key, val in p["layers"].items() if key.endswith(":" + kind))
            wx = sum(p["kind_wait"].get(kind + ":exchange", 0) for p in req)
            ws = sum(p["kind_wait"].get(kind + ":share", 0) for p in req)
            if v or wx or ws:
                w(f"    {label:12} {v / s['passes']:9.2f} ms ({v / s['passes'] / count:6.3f} a layer, {count} layers); "
                  f"waits {wx / s['passes']:7.2f} + {ws / s['passes']:7.2f} ms\n")
        w(f"  {'pass':>5} {'rows':>6} {'start ms':>9} {'span ms':>9} {'gate':>7} {'gate gap':>8} {'wait x':>7} "
          f"{'wait s':>7} {'idle':>7} {'side NCCL':>9} {'exposed':>7} {'glue runs':>9}\n")
        for q, p in enumerate(req):
            m = p["ms"]
            w(f"  {q:5d} {p['rows']:6d} {(p['t0'] - req[0]['t0']) / 1e6:9.1f} {p['span'] / 1e6:9.1f} "
              f"{m.get('head_gate', 0):7.2f} {m.get('gate_gap', 0):8.2f} {m.get('wait_exchange', 0):7.2f} "
              f"{m.get('wait_share', 0):7.2f} {(p['span'] - p['busy']) / 1e6:7.2f} {p['side']['nccl_ms']:9.2f} "
              f"{p['side']['exposed_ms']:7.2f} {p['glue_runs']:9d}\n")
        if show_layers:
            for p in req:
                w(f"  pass at {(p['t0'] - req[0]['t0']) / 1e6:.1f} ms, {p['rows']} rows: " +
                  " ".join(f"{k}={v:.2f}" for k, v in p["layers"].items()) + "\n")
        top = collections.Counter()
        for p in req:
            top.update(p["names"])
        w("  kernels by time: " + ", ".join(f"{k} {v:.1f}" for k, v in top.most_common(12)) + "\n")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sqlite")
    ap.add_argument("--gap", type=float, default=1.0, help="idle seconds that end a request")
    ap.add_argument("--json", default="", help="write every pass's record here")
    ap.add_argument("--layers", action="store_true", help="print every pass's per-layer milliseconds")
    a = ap.parse_args(argv)
    res = analyse(a.sqlite, a.gap)
    report(res, a.layers)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"path": res["path"], "requests": [{"summary": summarize(r), "passes": r}
                                                         for r in res["requests"]]}, fh, indent=1, default=str)
    return 0 if res["requests"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
