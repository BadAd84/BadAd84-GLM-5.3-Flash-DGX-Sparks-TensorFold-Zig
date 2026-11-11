#!/usr/bin/env python3
"""N concurrent greedy streams against an OpenAI-compatible serve (stdlib only).

Recipe: the measurement instrument for scripts/serve.sh. Copied from the OTS repro lanes
(ai-engine docs/repro/dsv41-cellc-r1-lane/streams.py, itself a glm copy). OTS-656 copy of glm-tp2-lane/streams.py.

Usage: streams.py PORT N --kind prose|code [--max-tokens 400] [--rounds 3] [--tag X] [--out FILE.jsonl] [--each 1]
       [--pad WORDS]
--kind picks a prompt set (all N streams prose, or all N code; stream i = SET[i % 4]).
--pad puts WORDS filler words (about 1.5 tokens a word, the same text on every arm) in front of each prompt, so the
prompt pass crosses the 2,048-row chunk and 6,144-token pair thresholds a short prompt never reaches.
Steady window per stream = first content chunk to last content chunk (TTFT excluded); round decode aggregate =
sum(tokens - 1) / (last content of any stream - first content of any stream).
Each round sends N different prompts at once (prompt i = PROMPTS[i % len]), thinking off, temperature 0, stream with
include_usage. Per stream: TTFT (first content chunk), decode tok/s = (completion_tokens - 1) / (last content chunk -
first content chunk) (sparkDash's DecodeBench rule, as sdbench.py), the reply's sha256. Per round: aggregate tok/s =
sum(completion_tokens) / (last finish - first send) and decode-phase aggregate = sum(completion_tokens - 1) / (last
content - earliest first content). One warm-up round of 32 tokens first (not recorded).
Round 0 (N streams) replies are compared across arms and against the solo replies (concurrent == solo).

Draft accounting (the spec-decoding record, per round): /metrics' mtp_drafted_total, mtp_accepted_total and
decode_rounds_total are counters over finished requests, so the delta across a round is that round's own. Each
round row therefore carries rounds, drafted, accepted, acceptance (accepted/drafted), ms_per_round and
tok_per_round; a serve without the counters yields nulls, never zeros.
"""
import hashlib, json, sys, threading, time, urllib.request

TAIL = ("Output only Python source. No comments, no docstrings, no markdown fences. "
        "Then add tests and the helpers this needs. Keep writing code.")
ALL = [
    ("prose", "Write a detailed step-by-step explanation of how a hash map works, including collision handling, "
              "resizing, and time complexity. Be thorough."),
    ("code", "binary_search\ndef binary_search(nums, target) -> int: index of target in a sorted list, or -1.\n" + TAIL),
    ("structured", "Count from 1 to 200. Output only the numbers, separated by spaces. No other text."),
    ("story", "Write a short story about a lighthouse keeper who finds a message in a bottle."),
    ("facts", "Explain how a refrigerator moves heat out of its cabinet, step by step."),
    ("json", "Return a JSON object listing ten European capitals with their population and one landmark each."),
    ("code2", "lru_cache\nclass LRUCache: get(key) and put(key, value) in O(1) with a capacity limit.\n" + TAIL),
    ("prose2", "Explain in depth how TCP congestion control works: slow start, congestion avoidance, fast retransmit "
               "and fast recovery, with examples. Be thorough."),
]

SETS = {"prose": [p for p in ALL if p[0] in ("prose", "story", "facts", "prose2")],
        "code": [p for p in ALL if p[0] in ("code", "code2")] + [
            ("code3", "trie\nclass Trie: insert(word), search(word), starts_with(prefix).\n" + TAIL),
            ("code4", "dijkstra\ndef dijkstra(graph, src) -> dict: shortest distances in a weighted adjacency dict.\n" + TAIL)]}

COUNTERS = ("mtp_drafted_total", "mtp_accepted_total", "decode_rounds_total")


def parse_metrics(text):
    """The three draft counters from a Prometheus text body; absent ones are None, a label set does not confuse it."""
    got = dict.fromkeys(COUNTERS, None)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, rest = line.partition("{")
        if "{" in line:
            _, _, rest = line.partition("}")
            parts = rest.split()
        else:
            parts = line.split()
            name = parts[0] if parts else ""
        name = name.rsplit(":", 1)[-1]  # the server prefixes its families: tensorfold:mtp_drafted_total
        if name in got and len(parts) >= 1:
            try:
                got[name] = float(parts[-1])
            except ValueError:
                pass
    return got


def fetch_metrics(base, timeout=10):
    """Tolerant: a serve without /metrics or a transient error yields all-None counters."""
    try:
        with urllib.request.urlopen(base + "/metrics", timeout=timeout) as r:
            return parse_metrics(r.read().decode("utf-8", "replace"))
    except Exception:
        return dict.fromkeys(COUNTERS, None)


def account(before, after, tokens, span_s):
    """One round's draft accounting: counter deltas plus the two ratios, None wherever a denominator is 0 or a
    counter is missing, so a serve without counters never reports a fabricated 0% acceptance."""
    def delta(name):
        b, a = before.get(name), after.get(name)
        if b is None or a is None or a < b:
            return None
        return int(a - b)
    rounds = delta(COUNTERS[2])
    drafted = delta(COUNTERS[0])
    accepted = delta(COUNTERS[1])
    return {
        "rounds": rounds,
        "drafted": drafted,
        "accepted": accepted,
        "acceptance": (accepted / drafted) if (drafted and accepted is not None) else None,
        "tok_per_round": (tokens / rounds) if (rounds and rounds > 0) else None,
        "ms_per_round": (span_s * 1e3 / rounds) if (rounds and rounds > 0 and span_s is not None) else None,
    }


def opt(name, default, argv):
    if name in argv:
        i = argv.index(name); v = argv[i + 1]; del argv[i:i + 2]; return v
    return default


def padded(prompts, words):
    """Each prompt behind `words` deterministic filler words: a long prompt pass with the same question at its end."""
    if words <= 0:
        return prompts
    lines = [f"Note {i}: shelf {i % 97} of the archive holds ledger {i * 7 % 1013}." for i in range(words // 9 + 1)]
    filler = " ".join(lines)
    return [(name, filler + "\n\nIgnore the notes above. " + text) for name, text in prompts]


def model_id(base):
    return json.load(urllib.request.urlopen(base + "/v1/models", timeout=10))["data"][0]["id"]


def one(base, model, prompt, maxt, res, idx, t_send):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": maxt, "temperature": 0,
            "top_p": 1, "stream": True, "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    first = last = None; text = []; usage = None; finish = None
    with urllib.request.urlopen(req, timeout=1800) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            ev = json.loads(data)
            if ev.get("usage"):
                usage = ev["usage"]
            for ch in ev.get("choices") or []:
                d = ch.get("delta") or {}
                c = d.get("content") or d.get("reasoning_content")
                if c:
                    now = time.perf_counter()
                    if first is None:
                        first = now
                    last = now
                    text.append(c)
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
    end = time.perf_counter()
    ct = (usage or {}).get("completion_tokens", 0)
    reply = "".join(text)
    res[idx] = {"ttft_s": (first - t_send) if first else None, "first": first, "last": last, "end": end,
                "completion_tokens": ct, "decode_tok_s": (ct - 1) / (last - first) if first and last and last > first else None,
                "finish": finish, "sha": hashlib.sha256(reply.encode()).hexdigest()[:12], "chars": len(reply)}


def wave(base, model, prompts, n, maxt):
    res = [None] * n; th = []
    before = fetch_metrics(base)
    t0 = time.perf_counter()
    for i in range(n):
        t = threading.Thread(target=one, args=(base, model, prompts[i % len(prompts)][1], maxt, res, i, time.perf_counter()))
        t.start(); th.append(t)
    for t in th:
        t.join()
    after = fetch_metrics(base)
    toks = sum(r["completion_tokens"] for r in res)
    end = max(r["end"] for r in res)
    lasts = [r["last"] for r in res if r["last"] is not None]
    firsts = [r["first"] for r in res if r["first"] is not None]
    dagg = (sum((r["completion_tokens"] - 1) for r in res) / max(1e-9, max(lasts) - min(firsts))
            if len(lasts) == len(res) and len(firsts) == len(res) else None)
    span = (max(lasts) - min(firsts)) if len(lasts) == len(res) and len(firsts) == len(res) else None
    return {"streams": res, "agg_tok_s": toks / (end - t0), "wall_s": end - t0, "decode_agg_tok_s": dagg,
            "drafts": account(before, after, sum((r["completion_tokens"] - 1) for r in res), span)}


def round_row(tag, n, k, w, prompts):
    d = w["drafts"]
    return {"tag": tag, "n": n, "round": k, "agg_tok_s": round(w["agg_tok_s"], 2),
            "decode_agg_tok_s": round(w["decode_agg_tok_s"], 2) if w["decode_agg_tok_s"] is not None else None,
            "wall_s": round(w["wall_s"], 2),
            "per_stream": [round(s["decode_tok_s"] or 0, 2) for s in w["streams"]],
            "ttft_ms": [round((s["ttft_s"] or 0) * 1e3) for s in w["streams"]],
            "tokens": [s["completion_tokens"] for s in w["streams"]],
            "sha": [s["sha"] for s in w["streams"]], "names": [prompts[i % len(prompts)][0] for i in range(n)],
            "draft_rounds": d["rounds"], "drafted": d["drafted"], "accepted": d["accepted"],
            "acceptance": round(d["acceptance"], 3) if d["acceptance"] is not None else None,
            "ms_per_round": round(d["ms_per_round"], 1) if d["ms_per_round"] is not None else None,
            "tok_per_round": round(d["tok_per_round"], 2) if d["tok_per_round"] is not None else None}


def main(argv):
    max_tokens = int(opt("--max-tokens", "400", argv)); rounds = int(opt("--rounds", "3", argv))
    tag = opt("--tag", "", argv); out = opt("--out", "", argv)
    prompts = padded(SETS[opt("--kind", "prose", argv)], int(opt("--pad", "0", argv)))
    each = opt("--each", "0", argv) == "1"
    port, n = argv[1], int(argv[2])
    base = f"http://127.0.0.1:{port}"
    model = model_id(base)
    wave(base, model, prompts, n, 32)       # warm-up
    rows = []
    for k in range(rounds):
        w = wave(base, model, prompts, n, max_tokens)
        row = round_row(tag, n, k, w, prompts)
        rows.append(row)
        print(json.dumps(row), flush=True)
    if each:                 # each of the N prompts alone, one after another: the solo replies concurrent ones must equal
        solo = []
        before = fetch_metrics(base)
        for i in range(n):
            res = [None]
            one(base, model, prompts[i % len(prompts)][1], max_tokens, res, 0, time.perf_counter())
            solo.append(res[0])
        after = fetch_metrics(base)
        span = (max(s["last"] for s in solo) - min(s["first"] for s in solo)) if all(s["first"] and s["last"] for s in solo) else None
        d = account(before, after, sum(max(0, s["completion_tokens"] - 1) for s in solo), span)
        row = {"tag": tag, "n": n, "round": "solo", "per_stream": [round(s["decode_tok_s"] or 0, 2) for s in solo],
               "ttft_ms": [round((s["ttft_s"] or 0) * 1e3) for s in solo], "tokens": [s["completion_tokens"] for s in solo],
               "sha": [s["sha"] for s in solo], "names": [prompts[i % len(prompts)][0] for i in range(n)],
               "draft_rounds": d["rounds"], "drafted": d["drafted"], "accepted": d["accepted"],
               "acceptance": round(d["acceptance"], 3) if d["acceptance"] is not None else None,
               "ms_per_round": round(d["ms_per_round"], 1) if d["ms_per_round"] is not None else None,
               "tok_per_round": round(d["tok_per_round"], 2) if d["tok_per_round"] is not None else None}
        rows.append(row)
        print(json.dumps(row), flush=True)
    if out:
        with open(out, "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main(sys.argv)
