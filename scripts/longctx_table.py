#!/usr/bin/env python3
"""longctx_table.py ROWS.jsonl [...] [--tol 0.02] [--allow-rejects] - the long-prompt window's comparison table against
production's SPEED-TARGET numbers (stdlib only).

Reads the JSONL rows longctx.py writes (one JSON object a line, as streams.py writes its rows) and the rows streams.py /
streams_ids.py write for the decode cells, and prints:
  1. rejected rows: every row that fails the instrument checks below, with its reasons; they are left out of the tables;
  2. boot facts per arm: seconds from launch to the first /health 200, MemAvailable a node, the prompt cache budget, the
     stream windows (P x context) and the kept states the budget holds (derived bytes a token, see STATE_BYTES_A_TOKEN);
  3. first token per case and load (median / p90 of the client's time to first token, the server's prefill seconds),
     beside production's value and ours / production;
  4. the long conversation (chain turns, server prefill seconds, as production's tier_chain reports them) and the
     longest prompt that fits;
  5. decode with N clients against the serve (streams rows; N past --parallel queue for a lane), beside production's
     section-1 cells, which are N clients against its --parallel 4 serve;
  6. cold prompts sent to more than one arm (the same --seed sends the same prompt): each arm's reply digest.
Every arm is labelled with the boot shape it ran on, "(P=4, ctx 1,048,576)", read from its boot row (an arm 'd4/c6' is
boot 'd4'), and every section names production's shape, so a measurement on another shape is visible as one.

The checks (verify(), the one owner: longctx.py imports it to flag rows as it writes them, and this script runs it
again on every row and ignores the row's own flags):
  LEN      a sized prompt's usage prompt_tokens is more than --tol of its target from it, or more than the row's own
           target_slack tokens when that is tighter (a warm turn: its ~2k new tokens, not 2% of the whole prompt);
           longest: above its ceiling or more than --tol under it;
  TOK      usage prompt_tokens differs from the /tokenize count the instrument sized the prompt with;
  NOUSAGE  no usage prompt_tokens; NOCACHE no cached_tokens (a cold or warm claim cannot be checked);
  NOTCOLD  a cold prompt with more than 5% of it from kept states, or a server-logged resume past row 0;
  NOTWARM  a warm turn (or a chain turn from the pool) with less than half of it from kept states;
  NOLOAD   a loaded sample sent while fewer than the asked streams decoded;
  NOTTFT   no first token; ERR the request failed.
Exit 0: rows read, none rejected. Exit 1: a row was rejected (0 with --allow-rejects). Exit 2: no rows or bad input.
"""
import json
import math
import statistics
import sys

TOL = 0.02        # a sized prompt's usage count within 2% of its target
COLD_MAX = 0.05   # a cold prompt: at most 5% of it from kept states (production ttft.py's NOTCOLD)
WARM_MIN = 0.50   # a warm turn: at least half of it from kept states (production ttft.py's NOTWARM)
REQUESTS = ("cold", "warm", "chain", "longest")

# Kept-state bytes a token on each rank: zig/src/families/glm/cuda_snapshot_layout.zig rows() (lines 86-95) on the
# checkpoint's config (11 deepseek_sparse_attention layers, kv_lora_rank 512 at 1 byte under --kv-cache fp8 plus a 4-byte
# f32 scale a row, pooled index keys of index_head_dim 128 in bf16 every index_kpool 4 rows): 11 x (512 + 4 + 64).
# Derived from the layout, not measured; a window of the live stream holds the same rows.
STATE_BYTES_A_TOKEN = 11 * (512 + 4 + 64)

# production/SPEED-TARGET.md and PRODUCTION.md on branch production: tensorfold-glm53:v110hunt4-shard, every
# measurement on one shape, --parallel 4 with --context 1048576 (and its spill tier).
PROD_SHAPE = (4, 1048576)
# Section 3, first token in seconds (the internal notes do not name that table's instrument; production's ttft.py is
# the instrument named for the missing cases and this window mirrors its cases); None: "not measured on this serve".
PROD_FIRST = {
    ("cold", 1000, 0): 0.54,
    ("cold", 8000, 0): 2.82,
    ("cold", 32000, 0): 10.93,
    ("cold", 120000, 0): 42.86,
    ("warm", None, 3): 1.217,
    ("warm", None, 0): None,
    ("cold", 32000, 3): None,
}
# Section 3, a growing conversation (tier_chain.sh / chainturn.py): the server's prefill seconds a turn.
PROD_CHAIN = {
    1: ("cold at ~596k tokens", 224.68),
    2: ("from the pool", 12.54),
    3: ("after every rank was SIGKILLed: from the spill tier, 619,392 tokens cached", 12.80),
    4: ("after a clean restart", 12.90),
}
# Section 4 (at --parallel 4) and section 5.
PROD_POOL_TOKENS = {4: 14407680}
PROD_MEM_GIB = {4: (18.6, 20.2, 21.2)}
# Section 1: N clients (streams.py, prose, 400 tokens, 3 rounds) against the --parallel 4 serve: aggregate tok/s, decode
# aggregate tok/s, first token ms.
PROD_DECODE = {
    1: (81.73, 83.62, "121 to 122"),
    2: (89.22, 90.42, "101 to 239"),
    4: (117.98, 119.69, "225 to 228"),
    6: (114.78, 115.56, "129 to 332; the 6 that waited for a slot 9,807 to 11,894"),
    8: (131.28, 131.96, "128 to 332; the 12 that waited for a slot 9,555 to 14,858"),
}


def verify(row, tol=TOL):
    """The reasons `row` cannot stand as the measurement it claims ([] when it can). Recomputed from raw fields."""
    case = row.get("case")
    if case not in REQUESTS:
        return []
    out = []
    if row.get("error"):
        out.append("ERR")
    p = row.get("prompt_tokens")
    if isinstance(p, bool) or not isinstance(p, int) or p <= 0:
        out.append("NOUSAGE")
        return out
    t = row.get("target_tokens")
    if isinstance(t, int) and t > 0:
        slack = row.get("target_slack")
        allowed = min(slack, tol * t) if isinstance(slack, int) and slack > 0 else tol * t  # a row's slack only tightens
        if case == "longest":
            if p > t or p < t * (1 - tol):
                out.append("LEN")
        elif abs(p - t) > allowed:
            out.append("LEN")
    k = row.get("tokenized_tokens")
    if k is not None and k != p:
        out.append("TOK")
    cached = row.get("cached_tokens")
    note = row.get("note") or ""
    cold = case in ("cold", "longest") or (case == "chain" and note == "cold")
    warm = case == "warm" or (case == "chain" and note == "pool")
    if cached is None:
        if cold or warm:
            out.append("NOCACHE")
    else:
        if cold and (cached > COLD_MAX * p or (row.get("resumed_at") or 0) > 0):
            out.append("NOTCOLD")
        if warm and cached < WARM_MIN * p:
            out.append("NOTWARM")
    load = row.get("load") or 0
    if load and (row.get("others") or 0) < load:
        out.append("NOLOAD")
    if row.get("ttft_ms") is None:
        out.append("NOTTFT")
    return out


def load_rows(paths):
    rows = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError as exc:
                    raise ValueError(f"{path}:{n}: not JSON ({exc})") from None
                if not isinstance(obj, dict):
                    raise ValueError(f"{path}:{n}: not a JSON object")
                rows.append(obj)
    return rows


def p90(values):
    s = sorted(values)
    return s[max(0, math.ceil(0.9 * len(s)) - 1)]


def med(values):
    v = [x for x in values if x is not None]
    return statistics.median(v) if v else None


def fmt(v, digits=2):
    if v is None:
        return "-"
    if isinstance(v, int):
        return f"{v:,}"
    return f"{v:,.{digits}f}"


def size_label(t):
    if not t:
        return "-"
    return f"{t // 1000}k" if t % 1000 == 0 else str(t)


def load_label(n):
    return "idle" if not n else f"load{n}"


def gib(kib_or_bytes, unit):
    if kib_or_bytes is None:
        return None
    return kib_or_bytes / (1 << 20 if unit == "kib" else 1 << 30)


def shape_text(p, ctx):
    return f"P={p if p else '?'}, ctx {fmt(ctx) if ctx else '?'}"


PROD_LABEL = "production (" + shape_text(*PROD_SHAPE) + ")"


def shapes(rows):
    """{boot tag: (P, context)} from the boot rows: the shape every arm of that boot ran on."""
    out = {}
    for r in rows:
        if r.get("case") == "boot":
            out[r.get("tag")] = (r.get("n"), r.get("context_length") or r.get("ctx"))
    return out


def arm(tag, sh, row=None):
    """`tag (P=.., ctx ..)`: the boot shape of the arm (tag 'd4/c6' ran on boot 'd4'); a row's own context as a fallback."""
    base = str(tag).split("/", 1)[0]
    p, ctx = sh.get(base, (None, None))
    if row is not None and ctx is None:
        ctx = row.get("context_length")
    if row is not None and p is None and base == tag:
        p = row.get("n")
    return f"{tag} ({shape_text(p, ctx)})"


def boot_section(rows, sh):
    out = ["## Boot facts (a fresh boot an arm; production serves one shape: " + shape_text(*PROD_SHAPE) + ")", "",
           "| arm (boot shape) | boot s (to /health 200) | up s (zig-tp3) | MemAvailable GiB spark1 / 2 / 3 (after boot) | "
           "prompt cache GiB | stream windows, tokens | kept states the cache holds, tokens (derived) | production |",
           "|---|---:|---:|---|---:|---:|---:|---|"]
    for r in rows:
        if r.get("case") != "boot":
            continue
        n = r.get("n")
        mem = r.get("mem_after_boot_kib") or {}
        mems = " / ".join(fmt(gib(mem.get(h), "kib"), 1) for h in ("spark1", "spark2", "spark3"))
        budget = (r.get("metrics") or {}).get("prompt_cache_budget_bytes")
        ctx = r.get("context_length") or r.get("ctx")
        windows = n * ctx if isinstance(n, int) and isinstance(ctx, int) else None
        kept = int(budget // STATE_BYTES_A_TOKEN) if budget else None
        if n in PROD_POOL_TOKENS:
            prod = (f"{PROD_LABEL}: pool {PROD_POOL_TOKENS[n]:,} tokens (windows and kept states together, three "
                    "shards); MemAvailable " + " / ".join(f"{x:.1f}" for x in PROD_MEM_GIB[n]) + "; boot time not measured")
        else:
            prod = f"not measured: production serves P={PROD_SHAPE[0]} only"
        state = "" if r.get("ok") else " BOOT FAILED: " + str(r.get("error") or "see boot log")
        out.append(f"| {arm(r.get('tag'), sh)}{state} | {fmt(r.get('boot_s'), 1)} | {fmt(r.get('up_s'), 1)} | {mems} | "
                   f"{fmt(gib(budget, 'bytes'), 1)} | {fmt(windows)} | {fmt(kept)} | {prod} |")
    out += ["", f"Kept states: the prompt cache budget over {STATE_BYTES_A_TOKEN:,} bytes a token a rank (the layout's "
            "arithmetic, every rank a full copy). This engine's /health has no pool_tokens: its KV is P windows of the "
            "context each plus that cache.", ""]
    return out


def first_section(rows, sh):
    groups = {}
    for r in rows:
        if r.get("case") not in ("cold", "warm"):
            continue
        key = (r.get("tag"), r.get("case"), r.get("target_tokens") if r.get("case") == "cold" else None, r.get("load") or 0)
        groups.setdefault(key, []).append(r)
    out = [f"## First token (client time to first token; server prefill seconds; against {PROD_LABEL})", "",
           "| arm (boot shape) | case | size | load | n | prompt tokens (median) | cached (median) | TTFT s median | p90 | "
           "prefill s median | production s | ours / production |",
           "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]

    def order(k):
        return (str(k[0]), k[1] != "cold", k[3], k[2] or 0)
    for key in sorted(groups, key=order):
        tag, case, size, load = key
        rs = groups[key]
        ttft = [r["ttft_ms"] / 1000 for r in rs]
        prod = PROD_FIRST.get((case, size, load))
        ours = med(ttft)
        ratio = f"{ours / prod:.2f}x" if prod and ours else "-"
        prod_txt = fmt(prod, 3 if prod and prod < 2 else 2) if prod is not None else "not measured"
        if case == "cold":
            label = size_label(size)
        else:
            add = med([r.get("add_tokens") for r in rs])
            label = f"+{fmt(int(add))} on a kept conversation" if add is not None else "a kept conversation"
        out.append(f"| {arm(tag, sh, rs[0])} | {case} | {label} | {load_label(load)} | "
                   f"{len(rs)} | {fmt(int(med([r['prompt_tokens'] for r in rs])))} | "
                   f"{fmt(int(med([r.get('cached_tokens') or 0 for r in rs])))} | {fmt(ours, 3)} | {fmt(p90(ttft), 3)} | "
                   f"{fmt(med([r.get('prefill_s') for r in rs]), 3)} | {prod_txt} | {ratio} |")
    out.append("")
    return out


def chain_section(rows, sh):
    out = [f"## Long conversation (production tier_chain.sh's turns; server prefill seconds; against {PROD_LABEL})", "",
           "| arm (boot shape) | turn | how | prompt tokens | cached | new | resumed at (log) | TTFT s | prefill s | "
           "production turn | production prefill s | ours / production |",
           "|---|---:|---|---:|---:|---:|---:|---:|---:|---|---:|---:|"]
    for r in rows:
        if r.get("case") != "chain":
            continue
        turn = r.get("turn")
        p, c = r.get("prompt_tokens"), r.get("cached_tokens")
        new = p - c if isinstance(p, int) and isinstance(c, int) else None
        how, prod = PROD_CHAIN.get(turn, ("-", None))
        pre = r.get("prefill_s")
        ratio = f"{pre / prod:.2f}x" if prod and pre else "-"
        out.append(f"| {arm(r.get('tag'), sh, r)} | {turn} | {r.get('note') or '-'} | {fmt(p)} | {fmt(c)} | {fmt(new)} | "
                   f"{fmt(r.get('resumed_at'))} | {fmt((r.get('ttft_ms') or 0) / 1000 or None, 2)} | {fmt(pre, 2)} | "
                   f"{how} | {fmt(prod, 2)} | {ratio} |")
    longest = [r for r in rows if r.get("case") == "longest"]
    if longest:
        out += ["", "| arm (boot shape) | longest prompt that fits, tokens | context | TTFT s | prefill s |",
                "|---|---:|---:|---:|---:|"]
        for r in longest:
            out.append(f"| {arm(r.get('tag'), sh, r)} | {fmt(r.get('prompt_tokens'))} | {fmt(r.get('max_model_len'))} | "
                       f"{fmt((r.get('ttft_ms') or 0) / 1000 or None, 2)} | {fmt(r.get('prefill_s'), 2)} |")
    out += ["", "Production has a disk tier (turns 3 and 4 resume from it); a turn this serve could not resume shows its "
            "cached tokens as 0 and its prefill as a cold pass.", ""]
    return out


def decode_section(rows, sh):
    """streams.py / streams_ids.py rows (a round each): N clients against the arm's serve, and production's cell."""
    groups = {}
    for r in rows:
        if "agg_tok_s" in r and isinstance(r.get("round"), int):
            groups.setdefault(r.get("tag"), []).append(r)
    if not groups:
        return []
    out = [f"## Decode with N clients (past --parallel they queue for a lane; production's cells are N clients against "
           f"{PROD_LABEL}, streams.py, its own prompt rendering)", "",
           "| arm (boot shape) | clients | rounds | aggregate tok/s (mean) | decode aggregate tok/s (mean) | first token ms "
           "(min to max) | production aggregate | production decode aggregate | production first token ms | "
           "ours / production |",
           "|---|---:|---:|---:|---:|---|---:|---:|---|---:|"]
    for tag in sorted(groups, key=str):
        rs = groups[tag]
        n = rs[0].get("n")
        agg = statistics.fmean(r["agg_tok_s"] for r in rs)
        dec = [r.get("decode_agg_tok_s") for r in rs if r.get("decode_agg_tok_s") is not None]
        firsts = [t for r in rs for t in (r.get("ttft_ms") or [])]
        prod = PROD_DECODE.get(n)
        out.append(f"| {arm(tag, sh)} | {n} | {len(rs)} | {fmt(agg)} | {fmt(statistics.fmean(dec) if dec else None)} | "
                   f"{fmt(min(firsts)) if firsts else '-'} to {fmt(max(firsts)) if firsts else '-'} | "
                   f"{fmt(prod[0]) if prod else '-'} | {fmt(prod[1]) if prod else '-'} | {prod[2] if prod else '-'} | "
                   f"{f'{agg / prod[0]:.2f}x' if prod else '-'} |")
    out.append("")
    return out


def digest_section(rows):
    """Cold prompts sent to more than one arm (the same seed sends the same prompt): each arm's reply digest."""
    by = {}
    for r in rows:
        if r.get("case") == "cold" and r.get("sha"):
            by.setdefault((r.get("target_tokens"), r.get("load") or 0, r.get("rep")), {})[r.get("tag")] = r["sha"]
    shared = {k: v for k, v in by.items() if len(v) > 1}
    if not shared:
        return []
    out = ["## The same cold prompt on several arms: reply digests", "", "| size | load | rep | digests by arm | equal |",
           "|---|---|---:|---|---|"]
    for (size, load, rep), tags in sorted(shared.items(), key=lambda kv: (kv[0][1], kv[0][0] or 0, kv[0][2] or 0)):
        out.append(f"| {size_label(size)} | {load_label(load)} | {rep} | "
                   f"{', '.join(f'{t} {s}' for t, s in sorted(tags.items()))} | {'yes' if len(set(tags.values())) == 1 else 'NO'} |")
    out.append("")
    return out


def render(rows, tol=TOL):
    rejected = [(r, verify(r, tol)) for r in rows]
    rejected = [(r, why) for r, why in rejected if why]
    bad = {id(r) for r, _ in rejected}
    kept = [r for r in rows if id(r) not in bad]
    sh = shapes(rows)
    lines = ["# Long prompts and resumed conversations: this serve against production/SPEED-TARGET.md", ""]
    lines.append(f"## Rejected rows: {len(rejected)}")
    lines.append("")
    for r, why in rejected:
        which = f"rep {r['rep']}" if r.get("rep") is not None else (f"turn {r['turn']}" if r.get("turn") is not None else "-")
        lines.append(f"- {r.get('tag')} {r.get('case')} {size_label(r.get('target_tokens'))} {load_label(r.get('load'))} "
                     f"{which}: {' '.join(why)} (prompt_tokens {r.get('prompt_tokens')}, target {r.get('target_tokens')}, "
                     f"tokenized {r.get('tokenized_tokens')}, cached {r.get('cached_tokens')}, error {r.get('error')})")
    lines.append("")
    lines += (boot_section(kept, sh) + first_section(kept, sh) + chain_section(kept, sh) + decode_section(kept, sh)
              + digest_section(kept))
    return "\n".join(lines), len(rejected)


def main(argv):
    args = list(argv[1:])
    tol = TOL
    allow = False
    if "--tol" in args:
        i = args.index("--tol")
        tol = float(args[i + 1])
        del args[i:i + 2]
    if "--allow-rejects" in args:
        args.remove("--allow-rejects")
        allow = True
    if not args:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    try:
        rows = load_rows(args)
    except (OSError, ValueError) as exc:
        print(f"longctx_table: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print("longctx_table: no rows", file=sys.stderr)
        return 2
    text, n_rejected = render(rows, tol)
    print(text)
    return 1 if n_rejected and not allow else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
