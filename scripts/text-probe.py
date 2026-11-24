#!/usr/bin/env python3
"""text-probe.py BASE [--out FILE] [--max-tokens N]: the same prompts' TEXT, so a numerics setting's drift can be read.

Our bench instrument records a digest per reply, which says only that two arms differ. A numerics change (a cache read at
a narrower width, a fused reduction in another order) needs the actual text: how far into a reply the first difference
falls, and how much of the rest changes, is the difference between "the same answer with a flipped token" and "another
answer". Prints one JSON row a prompt with the text, and a summary of the first divergence against the first arm's text
when run twice with --compare.
"""
import argparse
import difflib
import json
import pathlib
import sys
import urllib.request

PROMPTS = [
    ("prose", "Explain in one paragraph why a cargo ship's propeller is more efficient at low speed than a small boat's."),
    ("code", "Write a Python function that returns the n-th Fibonacci number modulo 1000, with a one-line docstring."),
    ("reason", "A workshop makes 3 parts an hour on Monday and 5 an hour on Tuesday; Monday runs 6 hours and Tuesday 4. "
               "How many parts does it make, and what is the average per hour across both days?"),
]


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
    with urllib.request.urlopen(req, timeout=1800) as r:
        out = json.load(r)
    ch = out["choices"][0]["message"]
    return (ch.get("reasoning_content") or "") + (ch.get("content") or "")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="http://127.0.0.1:8300")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--out", default="")
    ap.add_argument("--compare", default="", help="an earlier JSONL to diff against")
    args = ap.parse_args(argv[1:])
    base = args.base.rstrip("/")
    rows = []
    for name, prompt in PROMPTS:
        text = ask(base, prompt, args.max_tokens)
        rows.append({"prompt": name, "chars": len(text), "text": text})
        print(json.dumps({"prompt": name, "chars": len(text)}))
    if args.out:
        pathlib.Path(args.out).write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    if args.compare:
        before = {}
        for line in pathlib.Path(args.compare).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                before[r["prompt"]] = r["text"]
        for r in rows:
            a, b = before.get(r["prompt"], ""), r["text"]
            if a == b:
                print(f"{r['prompt']}: identical")
                continue
            sm = difflib.SequenceMatcher(None, a, b)
            first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            print(f"{r['prompt']}: first difference at char {first} of {len(a)}; "
                  f"similarity {sm.ratio():.4f}; lengths {len(a)} then {len(b)}")


if __name__ == "__main__":
    main(sys.argv)
