#!/usr/bin/env python3
"""streams_ids.py - streams.py's measurement with the prompt given as token ids on /v1/completions (measurement M-a).

Usage: streams_ids.py PORT N --ids FILE [--max-tokens 400] [--rounds 3] [--tag X] [--out FILE.jsonl]
FILE is JSON: [{"name": ..., "ids": [...]}, ...]; stream i sends entry i % len. Every rule is streams.py's own (one
warm-up wave of 32 tokens, temperature 0, top_p 1, stream with include_usage, TTFT and decode tok/s from the first to
the last content chunk, the reply's sha256 prefix, /metrics draft counters as deltas a wave, the same JSONL row):
those functions are imported from streams.py, only the request differs. The point is the prompt: production renders
the bench's prose prompt with thinking off in 33 tokens (no effort line), we render it in 40, so this sends
production's 33 ids to our serve and the reply is our engine's answer to production's prompt.
"""
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
for d in (HERE, os.path.join(HERE, "..", "..", "scripts")):
    if os.path.exists(os.path.join(d, "streams.py")):
        sys.path.insert(0, d)
        break
import streams  # noqa: E402  (streams.py beside this file on the box, the repo's scripts/ here)


def one(base, model, ids, maxt, res, idx, t_send):
    """streams.one with the prompt as ids on /v1/completions (text deltas in choices[].text)."""
    body = {"model": model, "prompt": ids, "max_tokens": maxt, "temperature": 0, "top_p": 1, "stream": True,
            "stream_options": {"include_usage": True}}
    req = urllib.request.Request(base + "/v1/completions", data=json.dumps(body).encode(),
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
                c = ch.get("text")
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
                "finish": finish, "sha": hashlib.sha256(reply.encode()).hexdigest()[:12], "chars": len(reply),
                "prompt_tokens": (usage or {}).get("prompt_tokens")}


def wave(base, model, prompts, n, maxt):
    """streams.wave with this file's request."""
    res = [None] * n; th = []
    before = streams.fetch_metrics(base)
    t0 = time.perf_counter()
    for i in range(n):
        t = threading.Thread(target=one, args=(base, model, prompts[i % len(prompts)][1], maxt, res, i, time.perf_counter()))
        t.start(); th.append(t)
    for t in th:
        t.join()
    after = streams.fetch_metrics(base)
    toks = sum(r["completion_tokens"] for r in res)
    end = max(r["end"] for r in res)
    lasts = [r["last"] for r in res if r["last"] is not None]
    firsts = [r["first"] for r in res if r["first"] is not None]
    whole = len(lasts) == len(res) and len(firsts) == len(res)
    dagg = sum((r["completion_tokens"] - 1) for r in res) / max(1e-9, max(lasts) - min(firsts)) if whole else None
    span = (max(lasts) - min(firsts)) if whole else None
    return {"streams": res, "agg_tok_s": toks / (end - t0), "wall_s": end - t0, "decode_agg_tok_s": dagg,
            "drafts": streams.account(before, after, sum((r["completion_tokens"] - 1) for r in res), span)}


def main(argv):
    max_tokens = int(streams.opt("--max-tokens", "400", argv)); rounds = int(streams.opt("--rounds", "3", argv))
    tag = streams.opt("--tag", "", argv); out = streams.opt("--out", "", argv)
    entries = json.load(open(streams.opt("--ids", "", argv)))
    prompts = [(e["name"], [int(x) for x in e["ids"]]) for e in entries]
    port, n = argv[1], int(argv[2])
    base = f"http://127.0.0.1:{port}"
    model = streams.model_id(base)
    cold = wave(base, model, prompts, n, 32)
    rows = []
    for k in range(rounds):
        w = wave(base, model, prompts, n, max_tokens)
        row = streams.round_row(tag, n, k, w, prompts)
        row["prompt_tokens"] = [s["prompt_tokens"] for s in w["streams"]]
        if k == 0:
            row["cold_ttft_ms"] = [round((s["ttft_s"] or 0) * 1e3) for s in cold["streams"]]
        rows.append(row)
        print(json.dumps(row), flush=True)
    if out:
        with open(out, "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main(sys.argv)
