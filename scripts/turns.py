#!/usr/bin/env python3
"""turns.py PORT [--pad WORDS] [--turns 4] [--max-tokens 64] [--tag X] [--out FILE.jsonl] - first-token time of each
turn of one chat that grows the way an agent's does (stdlib only).

Turn 1 sends a system message of WORDS filler words (about 1.5 tokens a word) and a user question. Every later turn sends
the whole earlier conversation, the reply the serve gave, and a new user message. The prefix of turn k+1 is turn k's whole
prompt plus its reply, so a serve that keeps the state of a finished request (or one cut at each message start) only
prefills the new tail. Each row: turn, prompt_tokens (from usage), ttft_ms, decode tok/s, the reply's sha256 and the
cached tokens when the serve reports them. Thinking off, temperature 0, one warm-up chat first on a different system
text so Triton/graph start-up is not in turn 1. Run it twice on one boot for a second view of the cold turn: a repeat
of the same chat is the warmest case.
"""
import hashlib, json, sys, time, urllib.request


def arg(argv, name, default):
    if name in argv:
        i = argv.index(name); v = argv[i + 1]; del argv[i:i + 2]; return v
    return default


def chat(port, messages, max_tokens):
    body = json.dumps({"model": "glm", "messages": messages, "max_tokens": max_tokens, "temperature": 0,
                       "stream": True, "stream_options": {"include_usage": True},
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", body, {"Content-Type": "application/json"})
    t0 = time.time(); first = last = None; text = []; usage = {}
    with urllib.request.urlopen(req, timeout=900) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            obj = json.loads(line[5:])
            if obj.get("usage"):
                usage = obj["usage"]
            for ch in obj.get("choices", []):
                piece = (ch.get("delta") or {}).get("content")
                if piece:
                    now = time.time()
                    first = first or now; last = now; text.append(piece)
    reply = "".join(text)
    toks = usage.get("completion_tokens", 0)
    dec = (toks - 1) / (last - first) if first and last and last > first and toks > 1 else None
    return reply, {"ttft_ms": round((first - t0) * 1000) if first else None, "decode_tok_s": round(dec, 2) if dec else None,
                   "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": toks,
                   "cached": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
                   "sha": hashlib.sha256(reply.encode()).hexdigest()[:12]}


def filler(words, seed):
    vocab = ["lattice", "orbit", "granite", "copper", "harbor", "violet", "meadow", "ember", "quartz", "falcon", "mosaic", "tundra"]
    return " ".join(vocab[(i * 7 + seed) % len(vocab)] + str(i % 97) for i in range(words))


def main(argv):
    port = argv[1]; rest = argv[2:]
    pad = int(arg(rest, "--pad", "5000")); turns = int(arg(rest, "--turns", "4")); mt = int(arg(rest, "--max-tokens", "64"))
    tag = arg(rest, "--tag", "turns"); out = arg(rest, "--out", None)
    chat(port, [{"role": "system", "content": "warm-up " + filler(300, 5)}, {"role": "user", "content": "Say hello."}], 8)
    questions = ["Summarise the notes in one sentence.", "Which word came first in the notes?",
                 "Give one example of a number you saw.", "Now list three words from the notes.", "Say goodbye."]
    rows = []
    for repeat in (1, 2):
        msgs = [{"role": "system", "content": "Notes: " + filler(pad, 1)}]
        for k in range(turns):
            msgs.append({"role": "user", "content": questions[k % len(questions)]})
            reply, st = chat(port, msgs, mt)
            msgs.append({"role": "assistant", "content": reply})
            st.update({"tag": tag, "chat": repeat, "turn": k + 1})
            rows.append(st)
            print(json.dumps(st), flush=True)
    if out:
        with open(out, "w") as fh:
            fh.write("\n".join(json.dumps(r) for r in rows) + "\n")


if __name__ == "__main__":
    main(sys.argv)
