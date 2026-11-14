#!/usr/bin/env python3
"""longctx.py SUBCOMMAND PORT [options] - long prompts and resumed conversations against an OpenAI-compatible serve
(stdlib only). Every result is one JSON row appended to --out, as streams.py appends its rows; longctx_table.py reads
them and compares with production/SPEED-TARGET.md.

The cases mirror production's own instruments so the numbers sit beside its table: production ttft.py (cold prompts of
1k / 8k / 32k / 120k tokens, k = 1000, behind a salt line; a warm turn of ~2k new tokens on a kept ~100k conversation,
re-primed before every turn; load3 = three other streams decoding, each measured request sent only once all three
decode) and production chainturn.py (the ~596k conversation that grows by ~20k-token tool results, byte for byte the
same text). Thinking off, temperature 0, streamed with include_usage. A sized prompt is fitted with the server's own
/tokenize (the chat route's rendering) before it is sent, and every row records the usage field's prompt_tokens and
cached_tokens: the table checks them against the target and the /tokenize count (longctx_table.verify, the checks'
one owner; rows are flagged here with the same function).

Subcommands (PORT: the serve's port; common: --tag, --n (streams the serve was booted with), --out, --timeout,
--log-cmd (rank 0's log since {since}, for the 'prompt cache:' line: resumed at, kept states, the store), --seed):
  facts    a boot's facts: --boot-start / --health-at / --up-at (epoch s), --boot-rc, --ctx; /health, /v1/models,
           /metrics (prompt cache budget, device memory), the startup line, MemAvailable on spark1 and --workers (over
           --ssh) after the boot and after one short warm-up request
  probe    --cold-sizes 1000,8000,32000,120000 --warm-base 100000 --warm-add 2000 --reps 3 --load 0|N
  chain    STATE.json [--note cold|pool|after-kill]: the next turn of chainturn.py's conversation (128 tokens a reply)
  longest  the longest prompt the context admits: max_model_len - --max-tokens, filled to within --margin of it
"""
import argparse
import hashlib
import json
import os
import random
import re
import shlex
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import longctx_table  # noqa: E402  (beside this file on the box and here: the checks' one owner)

WORDS = ("lattice probe ferrule datum spindle gauge trellis offset stylus kinematic fixture wafer cosine baseline "
         "granite bearing encoder servo axis spline tolerance flatness runout").split()
ASK = "\n\nContinue the numbered list above from where it stops, in the same format."
LINE_TOKENS = 19.1   # production ttft.py: GLM-5.3 tokens a filler line, the first guess the fit corrects
LOG_CMD = "docker logs --since {since} glm53-zig-r0"
WORKERS = os.environ["LONGCTX_WORKERS"]  # comma separated ssh targets of ranks 1 and 2, for example adam@spark2,adam@spark3
CACHE_LINE = re.compile(
    r"prompt cache: (?P<prompt>\d+) tokens, resumed at (?P<resumed>\d+), kept (?P<kept>\d+); (?P<states>\d+) states, "
    r"(?P<held_mib>\d+) MiB and (?P<spare_mib>\d+) MiB spare of (?P<budget_mib>\d+) MiB \(hits (?P<hits>\d+), "
    r"misses (?P<misses>\d+), evicted (?P<evicted>\d+), refused (?P<refused>\d+), failed (?P<failed>\d+), "
    r"trimmed (?P<trimmed>\d+)\)")
STARTUP = re.compile(r"model (?P<model_gib>[\d.]+) GiB.*?; (?P<streams>\d+) streams? at once, .*?of (?P<left_gib>[\d.]+) "
                     r"GiB left after a (?P<reserve_gib>[\d.]+) GiB reserve")
STARTUP_CACHE = re.compile(r"a (?P<cache_gib>[\d.]+) GiB prompt cache")
METRICS = ("prompt_cache_budget_bytes", "prompt_cache_minimum_state_bytes", "prompt_cache_bytes", "prompt_cache_states",
           "device_memory_bytes", "device_memory_peak_bytes", "pinned_memory_bytes")


def lines(rnd, n, start=0):
    """Production's numbered filler: n lines of eleven words from `rnd` (ttft.py, chainturn.py, longdec.py)."""
    return [f"{start + i:06d} " + " ".join(rnd.choice(WORDS) for _ in range(11)) for i in range(n)]


def seeded(label):
    """A stable seed for a text label (Python's str hash is salted per process)."""
    return zlib.crc32(label.encode())


def chain_user(turn, t1=520000, add=20000):
    """chainturn.py's user message for `turn`, byte for byte: turn 1 longdec seed 591, then ~20k-token tool results."""
    if turn == 1:
        return "[longdec 591]\n" + "\n".join(lines(random.Random(591), int(t1 / 17))) + ASK
    return f"[tool result {turn}]\n" + "\n".join(lines(random.Random(10000 + turn), int(add / 17), start=1000000 * turn)) + ASK


def fit(count, build, target, slack, ceiling=None, tries=8, first=None):
    """(lines, messages, tokens): the line count whose rendered prompt `count` puts within `slack` tokens of `target`
    and at most `ceiling`; after `tries` the closest admissible try (the row's checks then name what it missed).
    `first`: the first line count to try (default: target over production's tokens a line)."""
    lo, hi = target - slack, target + slack
    if ceiling is not None:
        hi = min(hi, ceiling)
    n = max(1, first if first is not None else round(target / LINE_TOKENS))
    seen = []
    best = None
    for _ in range(tries):
        msgs = build(n)
        c = count(msgs)
        seen.append((n, c))
        fits = ceiling is None or c <= ceiling
        if fits and (best is None or abs(c - target) < abs(best[2] - target)):
            best = (n, msgs, c)
        if lo <= c <= hi:
            return n, msgs, c
        if len(seen) >= 2 and seen[-1][0] != seen[-2][0]:
            slope = (seen[-1][1] - seen[-2][1]) / (seen[-1][0] - seen[-2][0])
        else:
            slope = c / n
        step = round((target - c) / slope) if slope > 0 else 0
        if step == 0:
            step = 1 if c < target else -1
        n = max(1, n + step)
    if best is None:
        n, msgs, c = seen[-1][0], build(seen[-1][0]), seen[-1][1]
        return n, msgs, c
    return best


class Client:
    def __init__(self, port, host="127.0.0.1", timeout=7200.0):
        self.base = f"http://{host}:{port}"
        self.timeout = timeout
        self.model = "glm"
        self.context = None
        self.max_model_len = None

    def get(self, path, timeout=30):
        with urllib.request.urlopen(self.base + path, timeout=timeout) as r:
            return r.read()

    def get_json(self, path, timeout=30):
        return json.loads(self.get(path, timeout))

    def post_json(self, path, body, timeout):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def model_id(self):
        data = self.get_json("/v1/models")["data"][0]
        self.model = data["id"]
        self.context = data.get("context_length") or data.get("max_model_len")
        return self.model

    def tokenize(self, msgs):
        """The chat route's prompt length for `msgs` (vLLM's /tokenize with messages: the same rendering)."""
        r = self.post_json("/tokenize", {"model": self.model, "messages": msgs, "add_generation_prompt": True,
                                         "chat_template_kwargs": {"enable_thinking": False}}, 900)
        self.max_model_len = r.get("max_model_len") or self.max_model_len
        return int(r["count"])

    def stream(self, msgs, max_tokens, on_first=None, stop=None, stamps=None):
        """One streamed chat request: the client's first-token time, usage, the server's tensorfold block, the reply."""
        body = {"model": self.model, "messages": msgs, "max_tokens": max_tokens, "temperature": 0, "top_p": 1,
                "stream": True, "stream_options": {"include_usage": True},
                "chat_template_kwargs": {"enable_thinking": False}}
        out = {"ttft": None, "admit": None, "text": "", "usage": {}, "runtime": {}, "finish": None, "error": None,
               "t_send": None, "t_first": None, "t_last": None, "t_end": None, "send_epoch": time.time()}
        req = urllib.request.Request(self.base + "/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        t0 = out["t_send"] = time.perf_counter()
        try:
            r = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            out["error"] = f"HTTP {exc.code}: {exc.read()[:300]!r}"
            out["t_end"] = time.perf_counter()
            return out
        except OSError as exc:
            out["error"] = f"{type(exc).__name__}: {exc}"
            out["t_end"] = time.perf_counter()
            return out
        parts = []
        done = False
        try:
            with r:
                out["admit"] = time.perf_counter() - t0
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        done = True
                        break
                    try:
                        ev = json.loads(payload)
                    except ValueError:
                        out["error"] = f"not JSON: {payload[:120]!r}"
                        break
                    if ev.get("error"):
                        out["error"] = str(ev["error"])[:300]
                        break
                    if ev.get("usage"):
                        out["usage"] = ev["usage"]
                    if isinstance(ev.get("tensorfold"), dict):
                        out["runtime"] = ev["tensorfold"]
                    for ch in ev.get("choices") or []:
                        d = ch.get("delta") or {}
                        piece = d.get("content") or d.get("reasoning_content")
                        if piece or d.get("tool_calls"):
                            now = time.perf_counter()
                            if out["t_first"] is None:
                                out["t_first"], out["ttft"] = now, now - t0
                                if on_first is not None:
                                    on_first()
                            out["t_last"] = now
                            if stamps is not None:
                                stamps.append(now)
                            if piece:
                                parts.append(piece)
                        if ch.get("finish_reason"):
                            out["finish"] = ch["finish_reason"]
                    if stop is not None and stop.is_set():
                        break
        except OSError as exc:
            out["error"] = out["error"] or f"{type(exc).__name__}: {exc}"
        out["t_end"] = time.perf_counter()
        out["text"] = "".join(parts)
        if out["error"] is None and not (stop is not None and stop.is_set()):
            if not done:
                out["error"] = "the stream ended without [DONE]"
            elif out["t_first"] is None:
                out["error"] = "no content or reasoning token"
        return out


class Load:
    """N background streams decoding (production ttft.py's load): each its own ~`tokens` prompt, long replies, restarted
    when one ends, until close(); every chunk's arrival kept so a measured request's stall on them can be read."""

    def __init__(self, client, n, tokens, max_tokens):
        self.client, self.n, self.max_tokens = client, n, max_tokens
        self.stop = threading.Event()
        self.decoding = [False] * n
        self.errors = []
        self.stamps = [[] for _ in range(n)]
        self.msgs = [[{"role": "user", "content": f"[ttft-load {i}]\n" +
                       "\n".join(lines(random.Random(4100 + i), max(1, round(tokens / LINE_TOKENS)))) + ASK}]
                     for i in range(n)]
        self.threads = [threading.Thread(target=self._run, args=(i,), daemon=True) for i in range(n)]

    def _run(self, i):
        while not self.stop.is_set():
            def first():
                self.decoding[i] = True
            res = self.client.stream(self.msgs[i], self.max_tokens, on_first=first, stop=self.stop, stamps=self.stamps[i])
            self.decoding[i] = False
            if res["error"] and not self.stop.is_set():
                self.errors.append(f"stream {i}: {res['error']}")
                self.stop.wait(2)

    def start(self):
        for t in self.threads:
            t.start()

    def active(self):
        return sum(self.decoding)

    def ready(self, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end and not self.stop.is_set():
            if self.active() == self.n:
                return True
            time.sleep(0.05)
        return self.active() == self.n

    def gaps(self, t0, t1):
        """The other streams' chunk gaps whose later chunk fell in [t0, t1]: median / p99 / max ms and the count."""
        win = []
        for s in self.stamps:
            st = list(s)
            win += [b - a for a, b in zip(st, st[1:]) if t0 <= b <= t1]
        if not win:
            return {"gap_n": 0}
        win.sort()
        return {"gap_n": len(win), "gap_median_ms": round(1000 * statistics.median(win)),
                "gap_p99_ms": round(1000 * win[min(len(win) - 1, int(0.99 * len(win)))]), "gap_max_ms": round(1000 * win[-1])}

    def close(self):
        self.stop.set()
        for t in self.threads:
            t.join(30)


def run_log(log_cmd, since):
    """Rank 0's log since `since` (epoch s) through `log_cmd` ('' or a failure: '')."""
    if not log_cmd:
        return ""
    cmd = [w.replace("{since}", str(int(since))) for w in shlex.split(log_cmd)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (r.stdout or "") + (r.stderr or "")


def cache_report(log_cmd, since, prompt_tokens):
    """The store's line for the request whose prompt was `prompt_tokens` long (the last such since `since`), or None."""
    hit = None
    for line in run_log(log_cmd, since - 2).splitlines():
        m = CACHE_LINE.search(line)
        if m and int(m["prompt"]) == prompt_tokens:
            hit = m
    return {k: int(v) for k, v in hit.groupdict().items()} if hit else None


def startup(log_cmd, since=0):
    """The server's startup line ('CUDA sm_...') logged since `since` (epoch s) and the numbers in it."""
    found = ""
    for line in run_log(log_cmd, since).splitlines():
        if "CUDA sm_" in line:
            found = line.strip()
    out = {"line": found[:1200]}
    m = STARTUP.search(found)
    if m:
        out.update({k: (int(v) if k == "streams" else float(v)) for k, v in m.groupdict().items()})
    m = STARTUP_CACHE.search(found)
    if m:
        out["cache_gib"] = float(m["cache_gib"])
    return out


def meminfo_kib(text):
    m = re.search(r"^MemAvailable:\s+(\d+) kB", text or "", re.M)
    return int(m[1]) if m else None


def mem_avail(ssh, workers, meminfo="/proc/meminfo"):
    """MemAvailable in KiB on this box (spark1) and each worker (spark2, spark3) over `ssh`."""
    try:
        with open(meminfo, encoding="utf-8") as fh:
            out = {"spark1": meminfo_kib(fh.read())}
    except OSError:
        out = {"spark1": None}
    for i, host in enumerate([w for w in workers.split(",") if w], 2):
        try:
            r = subprocess.run(shlex.split(ssh) + ["-n", "-o", "BatchMode=yes", host, "cat /proc/meminfo"],
                               capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
            out[f"spark{i}"] = meminfo_kib(r.stdout)
        except (OSError, subprocess.SubprocessError):
            out[f"spark{i}"] = None
    return out


def parse_metrics(text):
    """The prompt cache and memory gauges of a Prometheus body (names with or without the 'tensorfold:' prefix)."""
    got = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("{", 1)[0].split()[0]
        short = name.rsplit(":", 1)[-1]
        if short == "kv_capacity_mode":
            m = re.search(r'mode="([^"]+)"', line)
            got["kv_capacity_mode"] = m[1] if m else None
        elif short in METRICS:
            try:
                got[short] = int(float(line.split()[-1]))
            except ValueError:
                pass
    return got


def emit(path, row):
    row["flags"] = longctx_table.verify(row)
    text = json.dumps(row)
    print(text, flush=True)
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def request_row(args, case, res, **kw):
    """One measured request as a row: what the usage field and the server's block say, and the store's log line."""
    u = res["usage"] or {}
    rt = res["runtime"] or {}
    prompt = u.get("prompt_tokens")
    ct = u.get("completion_tokens")
    span = (res["t_last"] - res["t_first"]) if res["t_first"] is not None and res["t_last"] is not None else None
    pre = rt.get("prefill_seconds", rt.get("prefill_s"))
    row = {"tag": args.tag, "n": args.n, "case": case, "load": kw.get("load", 0), "rep": kw.get("rep"),
           "turn": kw.get("turn"), "note": kw.get("note"), "target_tokens": kw.get("target"),
           "target_slack": kw.get("slack"), "tokenized_tokens": kw.get("tokenized"), "prompt_tokens": prompt,
           "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"), "completion_tokens": ct,
           "ttft_ms": round(res["ttft"] * 1000) if res["ttft"] is not None else None,
           "admit_ms": round(res["admit"] * 1000) if res["admit"] is not None else None,
           "server_ttft_ms": round(rt["time_to_first_token"] * 1000) if rt.get("time_to_first_token") is not None else None,
           "prefill_s": round(pre, 3) if isinstance(pre, (int, float)) else None,
           "decode_tok_s": round((ct - 1) / span, 2) if ct and ct > 1 and span else None,
           "wall_s": round(res["t_end"] - res["t_send"], 3), "finish": res["finish"],
           "sha": hashlib.sha256(res["text"].encode()).hexdigest()[:12], "token_sha": rt.get("token_sha"),
           "others": kw.get("others"), "error": res["error"],
           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(res["send_epoch"]))}
    if isinstance(prompt, int):
        cache = cache_report(args.log_cmd, res["send_epoch"], prompt)
        if cache:
            row["resumed_at"], row["kept_states"], row["cache"] = cache["resumed"], cache["kept"], cache
    row.update(kw.get("extra") or {})
    return row


def user_msgs(header, seed, n):
    return [{"role": "user", "content": header + "\n" + "\n".join(lines(random.Random(seed), n)) + ASK}]


def cmd_facts(args):
    row = {"tag": args.tag, "n": args.n, "case": "boot", "ctx": args.ctx, "boot_rc": args.boot_rc,
           "ok": args.boot_rc == 0, "image": args.image, "xenv": args.xenv}
    if args.boot_start and args.health_at:
        row["boot_s"] = round(args.health_at - args.boot_start, 1)
    if args.boot_start and args.up_at:
        row["up_s"] = round(args.up_at - args.boot_start, 1)
    c = Client(args.port, timeout=600)
    if row["ok"]:
        try:
            h = c.get_json("/health")
            row["health"] = {k: h.get(k) for k in ("status", "warming", "max_batch_size", "memory")}
            c.model_id()
            row["model"], row["context_length"] = c.model, c.context
            row["metrics"] = parse_metrics(c.get("/metrics").decode("utf-8", "replace"))
        except (OSError, ValueError, KeyError, IndexError) as exc:
            row["ok"] = False
            row["error"] = f"facts: {type(exc).__name__}: {exc}"
    else:
        row["error"] = args.error or "the boot failed (boot log)"
    row["startup"] = startup(args.log_cmd, max(0, args.boot_start - 5))
    row["mem_after_boot_kib"] = mem_avail(args.ssh, args.workers, args.meminfo)
    if row["ok"]:
        res = c.stream([{"role": "user", "content": "Say hello."}], 8)
        row["warmup"] = {"ttft_ms": round(res["ttft"] * 1000) if res["ttft"] is not None else None,
                         "prompt_tokens": (res["usage"] or {}).get("prompt_tokens"), "error": res["error"]}
        row["mem_after_warmup_kib"] = mem_avail(args.ssh, args.workers, args.meminfo)
    emit(args.out, row)
    return 0 if row["ok"] else 1


def cmd_probe(args):
    c = Client(args.port, timeout=args.timeout)
    c.model_id()
    sizes = [int(x) for x in args.cold_sizes.split(",") if x.strip()]
    bg = None
    errors = 0
    if args.load:
        bg = Load(c, args.load, args.load_tokens, args.load_max_tokens)
        bg.start()
        if not bg.ready(args.load_wait):
            print(f"load: only {bg.active()} of {args.load} streams decoding after {args.load_wait:.0f} s {bg.errors[-1:]}",
                  file=sys.stderr, flush=True)
    conversation = base = None
    if args.warm_base > 0:
        label = f"{args.seed}|warm-base"
        n, base, base_count = fit(c.tokenize, lambda k: user_msgs(f"[ttft-warm {label}]", seeded(label), k),
                                  args.warm_base, round(args.tol * args.warm_base))
        prime = c.stream(base, 32)
        emit(args.out, request_row(args, "prime", prime, load=args.load, tokenized=base_count, note="first"))
        if prime["error"]:
            errors += 1
        else:
            conversation = base + [{"role": "assistant", "content": prime["text"]}]
    for rep in range(1, args.reps + 1):
        for size in sizes:
            label = f"{args.seed}|cold|{size}|{args.load}|{rep}"
            n, msgs, count = fit(c.tokenize, lambda k, label=label: user_msgs(f"[lc {label}]", seeded(label), k),
                                 size, round(args.tol * size))
            if bg is not None:
                bg.ready(args.load_wait)
            others = bg.active() if bg is not None else None
            res = c.stream(msgs, args.max_tokens)
            extra = bg.gaps(res["t_send"], res["t_first"] or res["t_end"]) if bg is not None else None
            row = request_row(args, "cold", res, rep=rep, target=size, tokenized=count, load=args.load, others=others,
                              extra=extra)
            errors += bool(res["error"])
            emit(args.out, row)
        if conversation is not None:
            if bg is not None:
                bg.ready(args.load_wait)
            pr = c.stream(base, 32)  # re-prime before every warm turn (ttft.py): a refill is logged, never measured
            emit(args.out, request_row(args, "prime", pr, load=args.load, rep=rep, note="re-prime"))
            label = f"{args.seed}|warm|{args.load}|{rep}"
            head = c.tokenize(conversation + user_msgs(f"[ttft turn {label}]", seeded(label), 0))
            target = head + args.warm_add
            slack = max(32, round(args.tol * args.warm_add))
            n, msgs, count = fit(c.tokenize, lambda k, label=label: conversation + user_msgs(f"[ttft turn {label}]",
                                                                                              seeded(label), k),
                                 target, slack, first=round(args.warm_add / LINE_TOKENS))
            if bg is not None:
                bg.ready(args.load_wait)
            others = bg.active() if bg is not None else None
            res = c.stream(msgs, args.max_tokens)
            extra = bg.gaps(res["t_send"], res["t_first"] or res["t_end"]) if bg is not None else {}
            extra = dict(extra or {}, add_tokens=count - head)
            errors += bool(res["error"])
            emit(args.out, request_row(args, "warm", res, rep=rep, target=target, slack=slack, tokenized=count,
                                       load=args.load, others=others, extra=extra))
    if bg is not None:
        bg.close()
        for e in bg.errors:
            print(f"load error: {e}", file=sys.stderr, flush=True)
    return 1 if errors else 0


def cmd_chain(args):
    c = Client(args.port, timeout=args.timeout)
    c.model_id()
    conv = []
    if os.path.exists(args.state):
        with open(args.state, encoding="utf-8") as fh:
            conv = json.load(fh)
    turn = len(conv) // 2 + 1
    msgs = conv + [{"role": "user", "content": chain_user(turn, args.t1, args.add)}]
    tokenized = c.tokenize(msgs)
    res = c.stream(msgs, 128)
    if not res["error"]:
        with open(args.state, "w", encoding="utf-8") as fh:
            json.dump(msgs + [{"role": "assistant", "content": res["text"]}], fh)
    note = args.note or ("cold" if turn == 1 else "pool")
    emit(args.out, request_row(args, "chain", res, turn=turn, tokenized=tokenized, note=note))
    return 1 if res["error"] else 0


def cmd_longest(args):
    c = Client(args.port, timeout=args.timeout)
    c.model_id()
    label = f"{args.seed}|longest"
    c.tokenize(user_msgs(f"[lc {label}]", seeded(label), 1))  # max_model_len: the window the chat route admits by
    window = c.max_model_len or c.context
    ceiling = window - args.max_tokens  # the chat route: the prompt leaves room for the reply it asks
    n, msgs, count = fit(c.tokenize, lambda k: user_msgs(f"[lc {label}]", seeded(label), k), ceiling - args.margin,
                         args.margin, ceiling=ceiling)
    res = c.stream(msgs, args.max_tokens)
    emit(args.out, request_row(args, "longest", res, target=ceiling, tokenized=count, extra={"max_model_len": window}))
    return 1 if res["error"] else 0


def parser():
    ap = argparse.ArgumentParser(prog="longctx.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("port")
    common.add_argument("--tag", default="")
    common.add_argument("--n", type=int, default=0, help="the --parallel the serve was booted with")
    common.add_argument("--out", default="")
    common.add_argument("--timeout", type=float, default=7200.0)
    common.add_argument("--log-cmd", default=LOG_CMD, help="rank 0's log since {since}; '' for none")
    common.add_argument("--seed", default="lc1", help="the salt family: the same seed sends the same prompts")
    common.add_argument("--tol", type=float, default=longctx_table.TOL)
    f = sub.add_parser("facts", parents=[common])
    f.add_argument("--ctx", type=int, default=0)
    f.add_argument("--boot-start", type=float, default=0.0)
    f.add_argument("--health-at", type=float, default=0.0)
    f.add_argument("--up-at", type=float, default=0.0)
    f.add_argument("--boot-rc", type=int, default=0)
    f.add_argument("--error", default="")
    f.add_argument("--image", default="")
    f.add_argument("--xenv", default="")
    f.add_argument("--ssh", default="ssh")
    f.add_argument("--workers", default=WORKERS)
    f.add_argument("--meminfo", default="/proc/meminfo")
    p = sub.add_parser("probe", parents=[common])
    p.add_argument("--cold-sizes", default="1000,8000,32000,120000")
    p.add_argument("--warm-base", type=int, default=100000)
    p.add_argument("--warm-add", type=int, default=2000)
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--load", type=int, default=0)
    p.add_argument("--load-tokens", type=int, default=3000)
    p.add_argument("--load-max-tokens", type=int, default=8192)
    p.add_argument("--load-wait", type=float, default=600.0)
    p.add_argument("--max-tokens", type=int, default=16)
    c = sub.add_parser("chain", parents=[common])
    c.add_argument("state")
    c.add_argument("--note", default="")
    c.add_argument("--t1", type=int, default=520000, help="chainturn.py's filler budget for turn 1")
    c.add_argument("--add", type=int, default=20000, help="chainturn.py's filler budget a later turn")
    lg = sub.add_parser("longest", parents=[common])
    lg.add_argument("--max-tokens", type=int, default=16)
    lg.add_argument("--margin", type=int, default=1024)
    return ap


def main(argv):
    args = parser().parse_args(argv)
    return {"facts": cmd_facts, "probe": cmd_probe, "chain": cmd_chain, "longest": cmd_longest}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
