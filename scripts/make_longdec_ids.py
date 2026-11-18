#!/usr/bin/env python3
"""make_longdec_ids.py TOKENIZER.json OUT.json - decode at long context: four prompts as token ids, production's thinking-off rendering.

A context of numbered filler lines (longctx.py's words, a fixed seed) of about 100k tokens, and the same context extended to about 250k,
each followed by a prose question (prose2's) and a code question (code2's) that ignore the list. The 250k prompts start with the 100k
prompts' exact ids and the two questions of a size share the whole context, so a serve with a prompt cache prefills about 250k tokens once
a boot; per_prompt.py's decode time (first to last chunk) is then decode at that depth. The ids are concatenated from separately encoded
pieces, so both engines receive the same ids whatever their tokenizers would make of the joined text. Light tooling: the workstation.
"""
import json
import os
import random
import sys

from tokenizers import Tokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import streams  # noqa: E402

WORDS = ("lattice probe ferrule datum spindle gauge trellis offset stylus kinematic fixture wafer cosine baseline "
         "granite bearing encoder servo axis spline tolerance flatness runout").split()
SIZES = (100_000, 250_000)


def filler(tok, start_line, target, rnd):
    """Encoded numbered lines from start_line until `target` ids: (ids, next line number)."""
    ids, n = [], start_line
    while len(ids) < target:
        line = f"{n} " + " ".join(rnd.choice(WORDS) for _ in range(12)) + "\n"
        ids += tok.encode(line, add_special_tokens=False).ids
        n += 1
    return ids, n


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    tok = Tokenizer.from_file(argv[0])
    enc = lambda s: tok.encode(s, add_special_tokens=False).ids
    head = enc("[gMASK]<sop><|user|>")
    tail = enc("<|assistant|><think></think>")
    asks = {name: enc("\n\nIgnore the numbered list above. " + text) for name, text in
            ((n, t) for n, t in streams.SETS["prose"] + streams.SETS["code"] if n in ("prose2", "code2"))}
    rnd = random.Random(20261117)
    context, line = [], 1
    out = []
    for size in SIZES:
        more, line = filler(tok, line, size - len(head) - len(context), rnd)
        context += more
        for kind in ("prose2", "code2"):
            ids = head + context + asks[kind] + tail
            out.append({"name": f"ctx{size // 1000}k-{kind}", "ids": ids, "rendering": "production thinking_off, pieces concatenated"})
    first = out[0]["ids"][:-(len(asks["prose2"]) + len(tail))]  # head and the ~100k context
    assert all(e["ids"][:len(first)] == first for e in out), "every prompt starts with the ~100k prompts' context"
    with open(argv[1], "w") as f:
        json.dump(out, f)
    for e in out:
        print(f"{e['name']}: {len(e['ids'])} ids")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
