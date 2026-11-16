#!/usr/bin/env python3
"""teacher_forced.py - our engine teacher-forced on production's prose reply (stdlib only; runs on the head).

Usage: teacher_forced.py PORT --forced forced.json --out records.jsonl [--max-tokens 16] [--from 0] [--to N]
For each position p, one greedy /v1/completions request whose prompt is production's 33-token thinking-off rendering
plus the first p tokens of production's reply (forced.json; `zig/src/server/completion_prompt_test.zig`: ids are
served as given). The prompt pass draws our target's token at p; the first decode round drafts after it from a context
that is production's text; with TF_GLM_DFLASH2_LOG on, rank 0 logs that round's 7 drafts and the next round's kept
rows (forced_score.py reads them). Each record keeps our target's continuation text so the scorer can tell where our
target leaves production's text. One warm-up request (p = -1, the prompt alone) comes first, as the log's first
request. max_tokens 16 guarantees a second round, whose `kept` gives the first round's accepted drafts.
"""
import json
import sys
import time
import urllib.request


def opt(name, default, argv):
    if name in argv:
        i = argv.index(name); v = argv[i + 1]; del argv[i:i + 2]; return v
    return default


def ask(base, model, ids, maxt):
    body = {"model": model, "prompt": ids, "max_tokens": maxt, "temperature": 0, "top_p": 1, "stream": False}
    req = urllib.request.Request(base + "/v1/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.load(r)
    use = out.get("usage") or {}
    return out["choices"][0].get("text") or "", use.get("completion_tokens"), use.get("prompt_tokens")


def main(argv):
    forced = json.load(open(opt("--forced", "", argv)))
    out = opt("--out", "", argv)
    maxt = int(opt("--max-tokens", "16", argv))
    lo = int(opt("--from", "0", argv))
    hi = int(opt("--to", str(len(forced["reply"]) - 1), argv))
    base = f"http://127.0.0.1:{argv[1]}"
    model = json.load(urllib.request.urlopen(base + "/v1/models", timeout=10))["data"][0]["id"]
    prompt, reply = [int(x) for x in forced["prompt"]], [int(x) for x in forced["reply"]]
    rows = []
    for p in [-1] + list(range(lo, hi)):
        ids = prompt + (reply[:p] if p > 0 else [])
        t0 = time.perf_counter()
        text, ct, pt = ask(base, model, ids, 8 if p < 0 else maxt)
        rows.append({"p": p, "prompt_tokens": pt, "completion_tokens": ct, "text": text,
                     "s": round(time.perf_counter() - t0, 3)})
        if p % 50 == 0:
            print(f"p {p}: {pt} prompt tokens, {ct} out, {rows[-1]['s']} s", flush=True)
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} records to {out}")


if __name__ == "__main__":
    main(sys.argv)
