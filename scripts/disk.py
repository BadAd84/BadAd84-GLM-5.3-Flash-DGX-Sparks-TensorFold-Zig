#!/usr/bin/env python3
"""disk.py SUBCOMMAND PORT [options] - GLM's conversation states on disk (--learn-conversations, upstream PR #1411) on
the TP=3 serve: conversations that outlive an eviction, a SIGKILL of every rank and a clean restart, each resumed turn
checked against a cold server's reply to the same prompt (stdlib only; longctx.py beside it supplies the client).

Every result is one JSON row appended to --out; disk_table.py reads them. The prompts every measured turn sent are kept
under --prompts (index.jsonl plus one file a turn), so a cold server (`replay`, booted without the disk tier and with
`--prompt-cache-gib 0`) answers exactly the same messages: the correctness gate is that every resumed turn's reply
(token_sha and the text's hash) equals the cold reply.

Conversations (a state file each under --conv-dir):
  chain     production chainturn.py's conversation, byte for byte (longctx.chain_user): turn 1 the ~596k-token
            longdec text, then ~20k-token tool results; 128 tokens a reply
  marker    a numbered filler sized with the server's /tokenize to --size, with three marker sentences derived from
            the conversation's name at 2%, 50% and 97% of it; turn 1 asks for READY, every later turn asks for the
            three markers quoted in order, so a reply depends on rows from the start, middle and end of the state
Subcommands (common: PORT, --tag (the boot), --arm learn|ref, --n, --out, --timeout, --log-cmd, --prompts):
  facts     a boot's facts: longctx.py's (/health, /metrics, the startup line, MemAvailable on every node) plus the
            disk store's startup line (its directory, states, MiB, ranks' parts, staging permit) and /stats' disk block
  turn      CONV --kind chain|marker [--size N] --expect cold|ram|disk [--label L] [--quote] [--load N] [--drain]:
            the next turn of CONV (or with --quote a branch on top of it that quotes three of turn 1's lines, not
            kept in the conversation), with /stats' disk counters before and after, the store's 'prompt cache:' line,
            and with --load the other streams' decode gaps in four windows (before, prefill, reply, until the save is
            written); --drain waits for the turn's saves to be written
  drain     waits until the store has no save queued or in flight (before a SIGKILL or a stop)
  evict     cold fillers until the RAM store holds no state at --at (the turns after it read their states from disk)
  salt      the conversation's next prompt as a non-streamed request with "cache_salt" (--salt): whether a request
            of another salt resumes this conversation's state (production honours cache_salt; '' is the control)
  replay    the cold server: every recorded prompt (or --only CASE,...), in --order, each a 'ref' row
  logs      counts of the disk tier's warning and error lines in saved rank logs (--r0 FILE, --worker FILE ...),
            with the store's size on disk and --extra KEY=VALUE facts the window collected
Every turn row also carries the store's own lines logged since it was sent: 'imprint: N tokens on disk: ...' (each
save: new blocks, its own MiB, the state's MiB, MiB of rows it shares, ms) and 'imprint: read N tokens from disk ...'.
"""
import argparse
import hashlib
import json
import os
import random
import re
import statistics
import sys
import threading
import time
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.environ.setdefault("LONGCTX_WORKERS", "")
import longctx  # noqa: E402  (scripts/longctx.py, beside this file on the box)
import disk_table  # noqa: E402  (the checks' one owner)

GRID = 2048  # the engine keeps a state at the last 2,048-row grid point of a prompt pass
ASK1 = "\n\nRead the reference text above. Reply with the single word READY."
ASKQ = ('Quote the three sentences of the reference text that begin with "Marker", exactly and in order, '
        'one a line, and nothing else.')
STORE_LINE = re.compile(r"glm: conversation states on disk in (?P<dir>\S+) \((?P<states>\d+) states, (?P<held_mib>\d+) MiB "
                        r"of (?P<cap_mib>\d+) MiB; (?P<ranks>\d+) ranks' parts; a save stages up to (?P<staging_mib>\d+) MiB\)")
COUNTERS = ("reads", "read_bytes", "writes", "written_bytes", "skipped", "failed", "evicted", "failure_count",
            "prefetch_made", "prefetch_used")
LOG_PATTERNS = {
    "staging_full": r"skipped \(StagingFull\)",
    "save_skipped": r"imprint: saving \d+ tokens skipped",
    "write_failed": r"imprint: writing \d+ tokens failed",
    "restore_failed": r"disk restore of \d+ tokens failed",
    "check_failed": r"failed (its|their) check",
    "unwritten_at_stop": r"the stop's deadline passed",
    "ranks_differ": r"RanksDiffer",
    "disk_world": r"DiskWorld",
    "disk_layout": r"DiskLayout",
    "disk_words": r"DiskWords",
    "snapshot_size": r"SnapshotSize",
    "ranks_not_asleep": r"the ranks did not sleep after a disk step",
    "error_lines": r"^(error|err)\b|\berror\(",
}
WRITE_LINE = re.compile(r"imprint: (?P<at>\d+) tokens on disk: (?P<blocks>\d+) new blocks and its own (?P<own_mib>\d+) MiB "
                        r"\((?P<state_mib>\d+) MiB this state, (?P<shared_mib>\d+) MiB of rows it shares\) in (?P<ms>\d+) ms")
READ_LINE = re.compile(r"imprint: read (?P<at>\d+) tokens from disk \((?P<mib>\d+) MiB in (?P<ms>\d+) ms(?P<ahead>, read ahead)?\)")


def store_lines(log_cmd, since):
    """The store's write and read lines logged since `since` (epoch s): ([write dicts], [read dicts])."""
    text = longctx.run_log(log_cmd, since)
    writes = [{k: int(v) for k, v in m.groupdict().items()} for m in WRITE_LINE.finditer(text)]
    reads = [{k: (bool(v) if k == "ahead" else int(v)) for k, v in m.groupdict().items()} for m in READ_LINE.finditer(text)]
    return writes, reads


def now_iso(t=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t if t is not None else time.time()))


def emit(path, row):
    row["flags"] = disk_table.verify(row)
    text = json.dumps(row)
    print(text, flush=True)
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def stats(c):
    """/stats' disk block (None: no disk tier, or no answer) with the RAM store's cumulative keeps as '_kept' (every
    keep queues one save: prompt_cache_keep.zig), and the prefill reuse block."""
    try:
        j = c.get_json("/stats", 30)
    except (OSError, ValueError, urllib.error.URLError):
        return None, None
    d = j.get("disk")
    if isinstance(d, dict):
        d = dict(d, _kept=(j.get("prompt_cache") or {}).get("kept"))
    return d, j.get("prefill_reuse")


def delta(before, after):
    if not before or not after:
        return None
    out = {k: (after.get(k) or 0) - (before.get(k) or 0) for k in COUNTERS}
    out["kept"] = (after.get("_kept") or 0) - (before.get("_kept") or 0)
    for k in ("read_ms_last", "write_ms_last", "queue_len", "states", "held_bytes", "last_error"):
        out[k] = after.get(k)
    return out


def settled(s):
    return sum((s.get(k) or 0) for k in ("writes", "skipped", "failed"))


def drain(c, base=None, timeout=900.0, stable_s=3.0, still_s=30.0, poll=1.0):
    """Wait until every save queued since `base` (/stats taken earlier; {} counts from the boot) is settled: written,
    skipped or failed, as many as the RAM store kept, nothing queued and the counters still for `stable_s` ('count').
    The store's queue does not count a save being written, so the count decides; a save dropped with its entry is
    never settled, so `still_s` with nothing queued and nothing moving also ends the wait ('still')."""
    t0 = time.monotonic()
    first, _ = stats(c)
    if first is None:
        return {"wait_s": 0.0, "settled": None, "timed_out": False, "no_disk": True}
    base = first if base is None else base
    last = still_since = None
    s = first
    while True:
        cur, _ = stats(c)
        if cur is not None:
            s = cur
            want = (s.get("_kept") or 0) - (base.get("_kept") or 0)
            got = settled(s) - settled(base)
            sig = (s.get("queue_len"), settled(s), s.get("written_bytes"), s.get("_kept"))
            if sig != last:
                last, still_since = sig, time.monotonic()
            idle = (s.get("queue_len") or 0) == 0
            held = time.monotonic() - still_since
            how = "count" if idle and got >= want and held >= stable_s else ("still" if idle and held >= still_s else None)
            if how:
                return {"wait_s": round(time.monotonic() - t0, 2), "settled": got, "kept": want, "by": how,
                        "timed_out": False, "queue_len": 0, "write_ms_last": s.get("write_ms_last"),
                        "written_bytes": (s.get("written_bytes") or 0) - (base.get("written_bytes") or 0)}
        if time.monotonic() - t0 > timeout:
            return {"wait_s": round(time.monotonic() - t0, 2), "settled": settled(s) - settled(base),
                    "kept": (s.get("_kept") or 0) - (base.get("_kept") or 0), "timed_out": True,
                    "queue_len": s.get("queue_len")}
        time.sleep(poll)


def marker(name, k):
    rnd = random.Random(longctx.seeded(f"{name}|{k}"))
    return f"Marker {k}: the {rnd.choice(longctx.WORDS)} {rnd.choice(longctx.WORDS)} reads {rnd.randrange(10 ** 6):06d}."


def marker_text(name, n):
    """The marker conversation's turn 1: n filler lines with markers A, B, C at 2%, 50% and 97% of them."""
    body = longctx.lines(random.Random(longctx.seeded(name)), n)
    for frac, k in sorted(((0.02, "A"), (0.50, "B"), (0.97, "C")), reverse=True):
        body.insert(min(len(body), int(frac * n)), marker(name, k))
    return f"[marker {name}]\n" + "\n".join(body) + ASK1


def quote_lines(t1):
    """Three of chain turn 1's line numbers, at 2%, 50% and 97% of its filler."""
    n = int(t1 / 17)
    return [f"{int(f * n):06d}" for f in (0.02, 0.50, 0.97)]


def load_conv(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {"messages": [], "prompts": [], "lines": None}


def newest_kept(conv):
    """The position of the conversation's newest kept state: over its turns that kept one (a pass whose 'prompt cache:' line
    logged kept 0 left none; unknown counts as kept), the highest position the RAM store created during the turn ('newest': a
    request start or the prompt's end under TF_GLM_REQUEST_STARTS), else the turn's grid point. 0 before any."""
    at = [p.get("newest") or p["grid"] for p in conv["prompts"] if p.get("kept") != 0]
    return max(at) if at else 0


def save_conv(path, conv):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(conv, fh)
    os.replace(tmp, path)


def record_prompt(args, case_id, msgs, max_tokens, tokenized):
    """The prompt a measured turn sent, for the cold server's replay (index.jsonl, then one file a case)."""
    if not args.prompts:
        return
    os.makedirs(args.prompts, exist_ok=True)
    name = case_id.replace("/", "_") + ".json"
    with open(os.path.join(args.prompts, name), "w", encoding="utf-8") as fh:
        json.dump({"case_id": case_id, "messages": msgs, "max_tokens": max_tokens, "tokenized": tokenized}, fh)
    with open(os.path.join(args.prompts, "index.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"case_id": case_id, "file": name, "tokenized": tokenized}) + "\n")


def windows(bg, marks):
    """The other streams' decode in each [start, end) window: gaps (median / p99 / max ms) and deltas a second."""
    out = {}
    for name, (t0, t1) in marks.items():
        if t0 is None or t1 is None or t1 <= t0:
            out[name] = None
            continue
        g = bg.gaps(t0, t1)
        n = sum(1 for s in bg.stamps for x in list(s) if t0 <= x < t1)
        g["seconds"] = round(t1 - t0, 2)
        g["deltas_per_s"] = round(n / (t1 - t0), 2)
        out[name] = g
    return out


def turn_row(args, res, case_id, conv_name, turn, expect, tokenized, before, after, prefill_reuse, **kw):
    u = res["usage"] or {}
    rt = res["runtime"] or {}
    prompt = u.get("prompt_tokens")
    ct = u.get("completion_tokens")
    pre = rt.get("prefill_seconds", rt.get("prefill_s"))
    span = (res["t_last"] - res["t_first"]) if res["t_first"] is not None and res["t_last"] is not None else None
    row = {"tag": args.tag, "arm": args.arm, "n": args.n, "case": kw.get("case", "turn"), "conv": conv_name, "turn": turn,
           "kind": kw.get("kind"), "case_id": case_id, "expect": expect, "label": kw.get("label") or "",
           "load": kw.get("load", 0),
           "others": kw.get("others"), "tokenized_tokens": tokenized, "prompt_tokens": prompt,
           "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"), "completion_tokens": ct,
           "expect_cached": kw.get("expect_cached"),
           "ttft_ms": round(res["ttft"] * 1000) if res["ttft"] is not None else None,
           "server_ttft_ms": round(rt["time_to_first_token"] * 1000) if rt.get("time_to_first_token") is not None else None,
           "prefill_s": round(pre, 3) if isinstance(pre, (int, float)) else None,
           "decode_tok_s": round((ct - 1) / span, 2) if ct and ct > 1 and span else None,
           "wall_s": round(res["t_end"] - res["t_send"], 3), "finish": res["finish"],
           "sha": hashlib.sha256(res["text"].encode()).hexdigest()[:12], "token_sha": rt.get("token_sha"),
           "reply_head": res["text"][:160], "error": res["error"], "ts": now_iso(res["send_epoch"]),
           "disk": delta(before, after), "prefill_reuse": prefill_reuse}
    if isinstance(prompt, int):
        cache = longctx.cache_report(args.log_cmd, res["send_epoch"], prompt)
        if cache:
            row["resumed_at"], row["kept_states"], row["cache"] = cache["resumed"], cache["kept"], cache
    if kw.get("case", "turn") != "ref":
        row["log_writes"], row["log_reads"] = store_lines(args.log_cmd, res["send_epoch"] - 1)
    row.update(kw.get("extra") or {})
    return row


def cmd_facts(args):
    row = {"tag": args.tag, "arm": args.arm, "n": args.n, "case": "boot", "ctx": args.ctx, "boot_rc": args.boot_rc,
           "ok": args.boot_rc == 0, "image": args.image, "xenv": args.xenv, "xserve": args.xserve, "ts": now_iso()}
    if args.boot_start and args.health_at:
        row["boot_s"] = round(args.health_at - args.boot_start, 1)
    if args.boot_start and args.up_at:
        row["up_s"] = round(args.up_at - args.boot_start, 1)
    c = longctx.Client(args.port, timeout=600)
    since = max(0, args.boot_start - 5)
    text = longctx.run_log(args.log_cmd, since)
    hits = [m.groupdict() for m in STORE_LINE.finditer(text)]
    row["store"] = ({k: (v if k == "dir" else int(v)) for k, v in hits[-1].items()} if hits else None)
    row["store_errors"] = sorted({k for k in ("ranks_differ", "disk_world", "disk_layout") if re.search(LOG_PATTERNS[k], text)}
                                 | ({"kv_share"} if "KvShareWithLearnConversations" in text else set())
                                 | ({"too_many_ranks"} if "TooManyRanks" in text else set()))
    if row["ok"]:
        try:
            h = c.get_json("/health")
            row["health"] = {k: h.get(k) for k in ("status", "warming", "max_batch_size", "memory")}
            c.model_id()
            row["model"], row["context_length"] = c.model, c.context
            row["metrics"] = longctx.parse_metrics(c.get("/metrics").decode("utf-8", "replace"))
            row["stats_disk"], _ = stats(c)
        except (OSError, ValueError, KeyError, IndexError) as exc:
            row["ok"] = False
            row["error"] = f"facts: {type(exc).__name__}: {exc}"
    else:
        row["error"] = args.error or "the boot failed (boot log)"
    row["startup"] = longctx.startup(args.log_cmd, since)
    row["mem_after_boot_kib"] = longctx.mem_avail(args.ssh, args.workers, args.meminfo)
    emit(args.out, row)
    return 0 if row["ok"] else 1


def cmd_turn(args):
    c = longctx.Client(args.port, timeout=args.timeout)
    c.model_id()
    path = os.path.join(args.conv_dir, args.conv + ".json")
    conv = load_conv(path)
    msgs_so_far = conv["messages"]
    turn = len(msgs_so_far) // 2 + 1
    if args.quote:
        if not msgs_so_far:
            print("--quote needs a conversation with a turn", file=sys.stderr)
            return 2
        nums = quote_lines(args.t1) if args.kind == "chain" else None
        ask = (f"Quote the lines numbered {', '.join(nums[:-1])} and {nums[-1]} of the first block of text above, exactly, "
               "one a line, and nothing else." if nums else f"(probe) {ASKQ}")
        msgs = msgs_so_far + [{"role": "user", "content": ask}]
        case_id = f"{args.conv}/t{turn - 1}q"
        max_tokens = args.max_tokens or 128
        expect_cached = newest_kept(conv) or None
    elif args.kind == "chain":
        msgs = msgs_so_far + [{"role": "user", "content": longctx.chain_user(turn, args.t1, args.add)}]
        case_id = f"{args.conv}/t{turn}"
        max_tokens = args.max_tokens or 128
        expect_cached = newest_kept(conv)
    else:
        if turn == 1:
            first = None if conv["lines"] is None else conv["lines"]
            n, msgs, _ = longctx.fit(c.tokenize, lambda k: [{"role": "user", "content": marker_text(args.conv, k)}],
                                     args.size, round(args.tol * args.size), first=first)
            conv["lines"] = n
        else:
            msgs = msgs_so_far + [{"role": "user", "content": f"(turn {turn}) {ASKQ}"}]
        case_id = f"{args.conv}/t{turn}"
        max_tokens = args.max_tokens or 96
        expect_cached = newest_kept(conv)
    tokenized = c.tokenize(msgs)
    record_prompt(args, case_id, msgs, max_tokens, tokenized)
    bg = None
    if args.load:
        bg = longctx.Load(c, args.load, args.load_tokens, args.load_max_tokens)
        bg.start()
        if not bg.ready(args.load_wait):
            print(f"load: only {bg.active()} of {args.load} streams decoding", file=sys.stderr, flush=True)
        time.sleep(args.base_s)  # the window before the request: the other streams' decode with nothing else
    before, _ = stats(c)
    others = bg.active() if bg is not None else None
    t_base = time.perf_counter() - (args.base_s if bg is not None else 0)
    res = c.stream(msgs, max_tokens)
    after_req, reuse = stats(c)
    drained = None
    t_written = None
    if args.drain and not res["error"]:
        drained = drain(c, base=before, timeout=args.drain_timeout, stable_s=args.drain_stable, still_s=args.drain_still,
                        poll=min(1.0, max(0.1, args.drain_stable / 3)))
        t_written = time.perf_counter()
    after, _ = stats(c) if drained else (after_req, None)
    extra = {"drain": drained}
    if bg is not None:
        extra["windows"] = windows(bg, {"base": (t_base, res["t_send"]), "prefill": (res["t_send"], res["t_first"]),
                                        "reply": (res["t_first"], res["t_end"]), "save": (res["t_end"], t_written)})
        bg.close()
        extra["load_errors"] = bg.errors[-3:]
    row = turn_row(args, res, case_id, args.conv, turn - (1 if args.quote else 0), args.expect, tokenized, before, after,
                   reuse, label=args.label, load=args.load, others=others, expect_cached=expect_cached, extra=extra,
                   kind=args.kind)
    emit(args.out, row)
    if not res["error"] and not args.quote:
        prompt = row["prompt_tokens"] or tokenized
        conv["messages"] = msgs + [{"role": "assistant", "content": res["text"]}]
        made = ram_positions(c, since_ms=int(res["send_epoch"] * 1000))
        conv["prompts"].append({"case_id": case_id, "tokens": prompt, "grid": (prompt - 1) // GRID * GRID,
                                "kept": row.get("kept_states"), "newest": max([a for a in made or [] if a], default=None)})
        save_conv(path, conv)
    return 1 if res["error"] else 0


def ram_positions(c, before_ms=None, since_ms=None):
    """The positions of the states the RAM store holds (/stats' prompt_cache entries), only those created before
    `before_ms` and at or after `since_ms` (epoch ms) when given, or None without an answer."""
    try:
        j = c.get_json("/stats", 30)
    except (OSError, ValueError, urllib.error.URLError):
        return None
    entries = (j.get("prompt_cache") or {}).get("entries") or []
    return [e.get("at") for e in entries if (before_ms is None or (e.get("created_at_ms") or 0) < before_ms)
            and (since_ms is None or (e.get("created_at_ms") or 0) >= since_ms)]


def cmd_evict(args):
    """Cold fillers, each its own salt, until the RAM store holds no state at --at (the turns that follow must read
    their states from disk); a 'filler' row each, then an 'evict' row with what is left."""
    c = longctx.Client(args.port, timeout=args.timeout)
    c.model_id()
    want = {int(x) for x in args.at.split(",") if x.strip()}
    sent = 0
    t_ms = int(time.time() * 1000)  # a filler's own state can sit at the same position: only older states count
    held = ram_positions(c, t_ms)
    while held is not None and want & set(held) and sent < args.max:
        label = f"filler|{args.tag}|{sent}"
        n, msgs, count = longctx.fit(c.tokenize, lambda k, label=label: longctx.user_msgs(f"[filler {label}]",
                                                                                       longctx.seeded(label), k),
                                     args.size, round(0.02 * args.size))
        before, _ = stats(c)
        res = c.stream(msgs, 8)
        after, reuse = stats(c)
        emit(args.out, turn_row(args, res, f"filler/{sent}", "filler", sent, "cold", count, before, after, reuse,
                                case="filler", label="filler"))
        sent += 1
        held = ram_positions(c, t_ms)
    left = sorted(want & set(held or []))
    emit(args.out, {"tag": args.tag, "arm": args.arm, "n": args.n, "case": "evict", "ts": now_iso(), "at": sorted(want),
                    "fillers": sent, "still_held": left, "stats_unavailable": held is None})
    return 1 if left else 0


def cmd_drain(args):
    c = longctx.Client(args.port, timeout=args.timeout)
    d = drain(c, base={}, timeout=args.drain_timeout, stable_s=args.drain_stable, still_s=args.drain_still,
              poll=min(1.0, max(0.1, args.drain_stable / 3)))
    s, _ = stats(c)
    row = {"tag": args.tag, "arm": args.arm, "n": args.n, "case": "drain", "label": args.label, "ts": now_iso(),
           "drain": d, "stats_disk": s}
    emit(args.out, row)
    return 1 if d.get("timed_out") else 0


def cmd_replay(args):
    c = longctx.Client(args.port, timeout=args.timeout)
    c.model_id()
    with open(os.path.join(args.prompts, "index.jsonl"), encoding="utf-8") as fh:
        index = [json.loads(line) for line in fh if line.strip()]
    by_id = {x["case_id"]: x for x in index}
    order = [x for x in (args.order.split(",") if args.order else [x["case_id"] for x in index]) if x]
    only = set(x for x in args.only.split(",") if x) if args.only else None
    errors = 0
    for case_id in order:
        if case_id not in by_id or (only is not None and case_id not in only):
            continue
        with open(os.path.join(args.prompts, by_id[case_id]["file"]), encoding="utf-8") as fh:
            p = json.load(fh)
        left = args.deadline - time.time() if args.deadline else None
        if left is not None and left < args.min_left:
            print(f"replay: {case_id} skipped, {left:.0f} s of the budget left", file=sys.stderr, flush=True)
            continue
        if left is not None:
            c.timeout = max(60.0, left - args.min_left / 2)
        tokenized = c.tokenize(p["messages"])
        before, _ = stats(c)
        res = c.stream(p["messages"], p["max_tokens"])
        after, reuse = stats(c)
        conv, _, t = case_id.partition("/")
        row = turn_row(args, res, case_id, conv, int(re.sub(r"\D", "", t) or 0), "cold", tokenized, before, after, reuse,
                       case="ref", label="cold reference", expect_cached=0,
                       extra={"recorded_tokenized": p.get("tokenized")})
        emit(args.out, row)
        errors += bool(res["error"])
    return 1 if errors else 0


def cmd_salt(args):
    """The conversation's next prompt with "cache_salt": --salt, not kept in the conversation. Production's tier
    resumes a salted request only from states of its own salt; here the cached tokens say what this engine does."""
    c = longctx.Client(args.port, timeout=args.timeout)
    c.model_id()
    conv = load_conv(os.path.join(args.conv_dir, args.conv + ".json"))
    msgs = conv["messages"] + [{"role": "user", "content": f"(salt probe) {ASKQ}"}]
    body = {"model": c.model, "messages": msgs, "max_tokens": 8, "temperature": 0, "top_p": 1, "stream": False,
            "chat_template_kwargs": {"enable_thinking": False}}
    if args.salt:
        body["cache_salt"] = args.salt
    row = {"tag": args.tag, "arm": args.arm, "n": args.n, "case": "salt", "conv": args.conv, "salt": args.salt,
           "expect_cached": newest_kept(conv), "ts": now_iso(), "error": None}
    t0 = time.perf_counter()
    try:
        r = c.post_json("/v1/chat/completions", body, args.timeout)
        u = r.get("usage") or {}
        row.update({"prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
                    "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                    "token_sha": (r.get("tensorfold") or {}).get("token_sha")})
    except urllib.error.HTTPError as exc:
        row["error"] = f"HTTP {exc.code}: {exc.read()[:300]!r}"
    except OSError as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    row["wall_s"] = round(time.perf_counter() - t0, 3)
    emit(args.out, row)
    return 1 if row["error"] else 0


def cmd_logs(args):
    def count(path):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            return None
        return {k: len(re.findall(p, text, re.M)) for k, p in LOG_PATTERNS.items()}
    row = {"tag": args.tag, "arm": args.arm, "n": args.n, "case": "logs", "label": args.label, "ts": now_iso(),
           "r0": count(args.r0) if args.r0 else None,
           "workers": {os.path.basename(w): count(w) for w in args.worker}}
    if args.learn_bytes is not None:
        row["learn"] = {"bytes": args.learn_bytes, "files": args.learn_files, "dir": args.learn_dir}
    row["extra"] = dict(kv.split("=", 1) for kv in args.extra if "=" in kv)
    emit(args.out, row)
    return 0


def parser():
    ap = argparse.ArgumentParser(prog="disk.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("port")
    common.add_argument("--tag", default="")
    common.add_argument("--arm", default="learn", choices=("learn", "ref"))
    common.add_argument("--n", type=int, default=0, help="the --parallel the serve was booted with")
    common.add_argument("--out", default="")
    common.add_argument("--timeout", type=float, default=7200.0)
    common.add_argument("--log-cmd", default=longctx.LOG_CMD, help="rank 0's log since {since}; '' for none")
    common.add_argument("--prompts", default="", help="where measured turns record their prompts (replay reads them)")
    common.add_argument("--drain-timeout", type=float, default=900.0)
    common.add_argument("--drain-stable", type=float, default=3.0, help="seconds the store's counters hold still")
    common.add_argument("--drain-still", type=float, default=30.0,
                        help="seconds with nothing queued and nothing moving that end a wait short of the count")
    f = sub.add_parser("facts", parents=[common])
    f.add_argument("--ctx", type=int, default=0)
    f.add_argument("--boot-start", type=float, default=0.0)
    f.add_argument("--health-at", type=float, default=0.0)
    f.add_argument("--up-at", type=float, default=0.0)
    f.add_argument("--boot-rc", type=int, default=0)
    f.add_argument("--error", default="")
    f.add_argument("--image", default="")
    f.add_argument("--xenv", default="")
    f.add_argument("--xserve", default="")
    f.add_argument("--ssh", default="ssh")
    f.add_argument("--workers", default=os.environ.get("LONGCTX_WORKERS", ""))
    f.add_argument("--meminfo", default="/proc/meminfo")
    t = sub.add_parser("turn", parents=[common])
    t.add_argument("conv")
    t.add_argument("--conv-dir", required=True)
    t.add_argument("--kind", choices=("chain", "marker"), required=True)
    t.add_argument("--size", type=int, default=32000, help="a marker conversation's turn-1 tokens")
    t.add_argument("--tol", type=float, default=0.02)
    t.add_argument("--t1", type=int, default=520000, help="chainturn.py's filler budget for turn 1")
    t.add_argument("--add", type=int, default=20000, help="chainturn.py's filler budget a later turn")
    t.add_argument("--expect", choices=("cold", "ram", "disk"), required=True)
    t.add_argument("--label", default="")
    t.add_argument("--quote", action="store_true")
    t.add_argument("--max-tokens", type=int, default=0)
    t.add_argument("--drain", action="store_true")
    t.add_argument("--load", type=int, default=0)
    t.add_argument("--load-tokens", type=int, default=3000)
    t.add_argument("--load-max-tokens", type=int, default=8192)
    t.add_argument("--load-wait", type=float, default=600.0)
    t.add_argument("--base-s", type=float, default=10.0, help="the window before the request, with --load")
    d = sub.add_parser("drain", parents=[common])
    d.add_argument("--label", default="")
    ev = sub.add_parser("evict", parents=[common])
    ev.add_argument("--at", required=True, help="state positions that must leave the RAM store, comma separated")
    ev.add_argument("--size", type=int, default=120000, help="each filler's tokens")
    ev.add_argument("--max", type=int, default=4)
    sa = sub.add_parser("salt", parents=[common])
    sa.add_argument("conv")
    sa.add_argument("--conv-dir", required=True)
    sa.add_argument("--salt", default="")
    r = sub.add_parser("replay", parents=[common])
    r.add_argument("--order", default="", help="case ids in the order to send (default: as recorded)")
    r.add_argument("--only", default="")
    r.add_argument("--deadline", type=float, default=0.0, help="epoch s the replay must end by (0: none)")
    r.add_argument("--min-left", type=float, default=600.0, help="a case starts only with this much of the budget left")
    lg = sub.add_parser("logs", parents=[common])
    lg.add_argument("--label", default="")
    lg.add_argument("--r0", default="")
    lg.add_argument("--worker", action="append", default=[])
    lg.add_argument("--learn-bytes", type=int, default=None)
    lg.add_argument("--learn-files", type=int, default=None)
    lg.add_argument("--learn-dir", default="")
    lg.add_argument("--extra", action="append", default=[], help="KEY=VALUE facts the window collected")
    return ap


def main(argv):
    args = parser().parse_args(argv)
    return {"facts": cmd_facts, "turn": cmd_turn, "drain": cmd_drain, "evict": cmd_evict, "salt": cmd_salt,
            "replay": cmd_replay, "logs": cmd_logs}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
