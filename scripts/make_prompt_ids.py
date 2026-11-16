#!/usr/bin/env python3
"""make_prompt_ids.py TOKENIZER.json OUT.json - the per-prompt bench set as token ids, in production's thinking-off rendering.

Twenty-four single-turn prompts: streams.py's eight (prose and code) and sixteen more kinds of agent work (explanations, stories, code in
other languages, shell, SQL, JSON, reviews, plans, maths). Each is rendered as production renders a thinking-off chat
(`[gMASK]<sop><|user|>` + content + `<|assistant|><think></think>`) and tokenized with the checkpoint's tokenizer, so both engines
receive the same ids on /v1/completions and neither's chat template is involved. Light tooling: runs on the workstation.
"""
import json
import os
import sys

from tokenizers import Tokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import streams  # noqa: E402

MORE = [
    ("dns", "Explain what happens, step by step, when a browser resolves a domain name it has never seen, from the stub resolver to the authoritative server. Be thorough."),
    ("raft", "Explain how the Raft consensus algorithm elects a leader and replicates a log, including what happens when a leader fails. Be thorough."),
    ("gc", "Compare reference counting with tracing garbage collection: how each works, what each costs, and where each fails. Be thorough."),
    ("letter", "Write a formal letter from a tenant to a landlord asking for a broken boiler to be repaired, with dates and a clear request."),
    ("dialogue", "Write a dialogue between a ship's engineer and its captain during a storm, as the engine begins to fail."),
    ("fable", "Write a fable about a fox and a heron who must share one fishing pool through a dry summer."),
    ("review", "Review this function and list every problem you see, most serious first, then rewrite it:\n\ndef avg(xs):\n    t = 0\n    for i in range(len(xs)):\n        t = t + xs[i]\n    return t / len(xs)\n"),
    ("plan", "Write a step-by-step plan for migrating a production PostgreSQL database to a new server with less than five minutes of downtime."),
    ("sql", "orders(id, customer_id, placed_at, total) and customers(id, name, country). Write SQL queries for: the top ten customers by spend last year, monthly revenue by country, and customers with no orders. Explain each query."),
    ("shell", "Write a bash script that rotates the log files in a directory: compress those older than a day, delete those older than thirty days, and print a summary. Then explain each part."),
    ("rust", "ring_buffer\nstruct RingBuffer<T>: push, pop, len, is_full, with a fixed capacity.\nOutput only Rust source. No comments, no markdown fences. Then add tests and the helpers this needs. Keep writing code."),
    ("go", "rate_limiter\ntype Limiter: a token bucket with Allow() bool, safe for concurrent use.\nOutput only Go source. No comments, no markdown fences. Then add tests and the helpers this needs. Keep writing code."),
    ("json", "Produce a JSON document describing a library catalogue of twelve books: title, author, year, genres, copies and a nested list of loans with borrower and due date. Output only JSON."),
    ("math", "A train leaves a station at 09:10 at 72 km/h. A second train leaves the same station at 09:40 on the same line at 96 km/h. Work out, step by step, when and where the second train catches the first, then check the answer a second way."),
    ("history", "Describe the causes and the course of the printing revolution in fifteenth-century Europe and what it changed in the following hundred years."),
    ("bug", "A web service returns HTTP 502 for about one request in two hundred, only under load, and only behind the load balancer. List the likely causes in order and how to test each."),
]


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    tok = Tokenizer.from_file(argv[0])
    prompts = [p for kind in ("prose", "code") for p in streams.SETS[kind]] + MORE
    out = []
    for name, content in prompts:
        text = "[gMASK]<sop><|user|>" + content + "<|assistant|><think></think>"
        ids = tok.encode(text, add_special_tokens=False).ids
        out.append({"name": name, "ids": ids, "rendering": "production thinking_off"})
    names = [e["name"] for e in out]
    assert len(set(names)) == len(names) == 24, names
    with open(argv[1], "w") as f:
        json.dump(out, f)
    print(f"wrote {argv[1]}: {len(out)} prompts, {min(len(e['ids']) for e in out)} to {max(len(e['ids']) for e in out)} ids")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
