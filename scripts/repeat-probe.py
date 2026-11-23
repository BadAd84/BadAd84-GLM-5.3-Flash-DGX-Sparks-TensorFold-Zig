#!/usr/bin/env python3
"""repeat-probe.py BASE [--max-tokens N] [--rounds R] [--out JSONL]: one prompt whose tail repeats the head of its own
context, so a copied continuation is possible, with the spec-decoding counters read before and after each request.

The copy window is planned only when a stream's own context repeats the continuation (core/lanes/windows.zig), and a
bench prompt never does: this probe builds that shape (a block, a different line, then the block's first half again)
and prints the rounds, drafted and accepted counts a copy proposal moves. Same instrument as streams.py (the server's
own /metrics counters), so an arm's cells are read the same way.
"""
import json
import sys
import time
import urllib.request

COUNTERS = ("mtp_drafted_total", "mtp_accepted_total", "decode_rounds_total")


def opt(name, default, argv):
    if name in argv:
        return argv[argv.index(name) + 1]
    return default


def counters(base, timeout=60):
    got = {}
    with urllib.request.urlopen(base + "/metrics", timeout=timeout) as r:
        for line in r.read().decode().splitlines():
            if not line or line.startswith("#"):
                continue
            name, _, value = line.rpartition(" ")
            name = name.rsplit(":", 1)[-1]
            if name in COUNTERS:
                try:
                    got[name] = float(value)
                except ValueError:
                    pass
    return got


def model_id(base):
    return json.load(urllib.request.urlopen(base + "/v1/models", timeout=10))["data"][0]["id"]


def ask(base, prompt, max_tokens):
    body = {
        "model": model_id(base),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    req = urllib.request.Request(
        base + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=1800) as r:
        out = json.load(r)
    return out, time.perf_counter() - t0


def text_of(out):
    choice = out["choices"][0]["message"]
    return (choice.get("reasoning_content") or "") + (choice.get("content") or "")


def main(argv):
    base = argv[1].rstrip("/") if len(argv) > 1 else "http://127.0.0.1:8300"
    max_tokens = int(opt("--max-tokens", "256", argv))
    rounds = int(opt("--rounds", "3", argv))
    out_path = opt("--out", "", argv)
    block = "the cat sat on the mat and looked at the door. " * 40
    other = "then it walked outside and did not come back. "
    prompt = block + other + block[: len(block) // 2]  # the tail repeats the block's head
    rows = []
    for i in range(rounds):
        before = counters(base)
        out, wall = ask(base, prompt, max_tokens)
        after = counters(base)
        got = {k: after.get(k, 0) - before.get(k, 0) for k in COUNTERS}
        accepted, drafted = got[COUNTERS[1]], got[COUNTERS[0]]
        row = {
            "round": i,
            "wall_s": round(wall, 2),
            "rounds": int(got[COUNTERS[2]]),
            "drafted": int(drafted),
            "accepted": int(accepted),
            "acceptance": round(accepted / drafted, 4) if drafted else 0.0,
            "ms_per_round": round(wall * 1000 / got[COUNTERS[2]], 1) if got[COUNTERS[2]] else 0.0,
            "chars": len(text_of(out)),
        }
        rows.append(row)
        print(json.dumps(row))
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main(sys.argv)
