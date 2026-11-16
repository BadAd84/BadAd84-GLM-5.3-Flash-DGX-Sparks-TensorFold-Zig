#!/usr/bin/env python3
"""per_prompt.py PORT --ids FILE --out OUT.jsonl [--max-tokens 400] [--reps 2] [--text] - one request at a time, each prompt's own rounds.

For each entry of FILE ([{"name", "ids"}, ...]): the serve's draft counters before, one greedy streamed /v1/completions request with the
ids, the counters after. The difference is exactly that request: rounds, drafted, accepted. A sequence's rounds do not depend on how many
other streams decode beside it (production: 133 + 199 + 139 + 159 alone, 630 a wave at four clients), so this is the per-text quantity
behind any tokens-a-round figure, and a set of prompts shows whether two engines differ systematically or by the text each wrote.
Counters: /health's rounds_total, drafted_total and accepted_total where the serve has them (production's Python engine), else /metrics
through streams.py's reader (this repo's engine). A serve that answers /health is measured only while idle (no request running; it waits
up to 15 minutes a request), so it is safe against a live serve. One JSON row a request: name, rep, sha12, tokens, rounds, drafted,
accepted, ttft_s, span_s (first to last chunk). Run on the head, beside streams.py.
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import streams  # noqa: E402

HEALTH = ("rounds_total", "drafted_total", "accepted_total")


def health(base):
    try:
        return json.load(urllib.request.urlopen(base + "/health", timeout=10))
    except Exception:
        return None


def counters(base):
    """(rounds, drafted, accepted), from /health when it carries them, else from /metrics."""
    h = health(base)
    if h and all(k in h for k in HEALTH):
        return tuple(h[k] for k in HEALTH)
    m = streams.fetch_metrics(base)
    return (m.get(streams.COUNTERS[2]), m.get(streams.COUNTERS[0]), m.get(streams.COUNTERS[1]))


def wait_idle(base, limit=900):
    """True once /health reports no request running; a serve whose /health has no such field is taken as idle."""
    t0 = time.time()
    while time.time() - t0 < limit:
        h = health(base)
        if h is None or "requests_running" not in h:
            return True
        if h["requests_running"] == 0 and not h.get("busy", False):
            return True
        time.sleep(5)
    return False


def ask(base, model, ids, maxt):
    body = {"model": model, "prompt": ids, "max_tokens": maxt, "temperature": 0, "top_p": 1, "stream": True,
            "stream_options": {"include_usage": True}}
    req = urllib.request.Request(base + "/v1/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.perf_counter(); first = last = None; text = []; usage = {}
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
                if ch.get("text"):
                    now = time.perf_counter()
                    first = first or now; last = now
                    text.append(ch["text"])
    return "".join(text), usage, (first - t0) if first else None, (last - first) if first else None


def delta(a, b):
    return None if a is None or b is None or b < a else int(b - a)


def main(argv):
    port = argv[0]
    ids_path = streams.opt("--ids", None, argv)
    out_path = streams.opt("--out", None, argv)
    maxt = int(streams.opt("--max-tokens", "400", argv))
    reps = int(streams.opt("--reps", "2", argv))
    keep_text = "--text" in argv  # --text: each row also carries the reply's text (teacher-forced runs need it)
    if not ids_path or not out_path:
        print(__doc__)
        return 2
    base = f"http://127.0.0.1:{port}"
    model = streams.model_id(base)
    with open(out_path, "w") as out:
        for e in json.load(open(ids_path)):
            for rep in range(reps):
                if not wait_idle(base):
                    print(f"{e['name']}: the serve stayed busy, stopping", flush=True)
                    return 1
                time.sleep(0.5)
                a = counters(base)
                text, usage, ttft, span = ask(base, model, e["ids"], maxt)
                time.sleep(0.5)
                b = counters(base)
                row = {"name": e["name"], "rep": rep, "sha12": hashlib.sha256(text.encode()).hexdigest()[:12], "tokens": usage.get("completion_tokens"),
                       "prompt_tokens": usage.get("prompt_tokens"), "rounds": delta(a[0], b[0]), "drafted": delta(a[1], b[1]), "accepted": delta(a[2], b[2]),
                       "ttft_s": ttft, "span_s": span}
                if keep_text:
                    row["text"] = text
                out.write(json.dumps(row) + "\n"); out.flush()
                print(f"{row['name']} {rep}: sha {row['sha12']} tokens {row['tokens']} rounds {row['rounds']} drafted {row['drafted']} accepted {row['accepted']} span {span:.2f}s", flush=True)
    print("PER-PROMPT-DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
