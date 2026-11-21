#!/usr/bin/env python3
"""chaindec.py DIR [DIR...] [--group NAME=TAG,TAG ...] - the decode rate at long context: per boot, the mean decode_tok_s of its resumed chain turns. A report: it decides nothing.

A boot's rows are DIR/TAG/chain.jsonl (longctx.py chain, one 128-token reply a turn, a conversation of 114k to 121k rows in the queues so far). A turn counts when its
decode_tok_s is set, its reply is at least 100 tokens and the cache held more than 50,000 of its rows (a resumed turn, not the cold first). Each --group prints the mean of its
boots' means and the spread between its boots (highest over lowest, minus one); a group of one boot has no spread.
"""
import argparse
import json
import pathlib
import statistics as st
import sys

MIN_CACHED = 50000
MIN_REPLY = 100


def resumed_turns(path):
    """The (decode_tok_s, prompt_tokens) of every counted turn in one chain.jsonl."""
    out = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("decode_tok_s") and (r.get("cached_tokens") or 0) > MIN_CACHED and (r.get("completion_tokens") or 0) >= MIN_REPLY:
            out.append((r["decode_tok_s"], r.get("prompt_tokens")))
    return out


def boot_rate(dirs, tag):
    """(turns, mean, min, max, lowest context, highest context) of boot TAG found under the first DIR that holds it, or None."""
    for d in dirs:
        f = pathlib.Path(d) / tag / "chain.jsonl"
        if f.exists():
            t = resumed_turns(f)
            if t:
                v = [x[0] for x in t]
                return len(v), st.mean(v), min(v), max(v), min(x[1] for x in t), max(x[1] for x in t)
    return None


def group_line(name, means):
    """The printed reading of a group: the mean of the boots' means and the spread between boots."""
    spread = f"spread between boots {(max(means) / min(means) - 1):.2%}" if len(means) > 1 else "one boot, no spread"
    return f"group {name}: {len(means)} boot(s), mean of means {st.mean(means):.2f} tok/s, {spread}"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--group", action="append", default=[], metavar="NAME=TAG,TAG")
    a = ap.parse_args(argv)
    groups = [g.split("=", 1) for g in a.group]
    tags = []
    for _, spec in groups:
        tags += [t for t in spec.split(",") if t not in tags]
    if not tags:
        tags = sorted({p.parent.name for d in a.dirs for p in pathlib.Path(d).glob("*/chain.jsonl")})
    means = {}
    for tag in tags:
        r = boot_rate(a.dirs, tag)
        if r is None:
            print(f"{tag:6s} no counted chain turn found")
            continue
        means[tag] = r[1]
        print(f"{tag:6s} {r[0]} resumed turns, mean {r[1]:7.2f} tok/s (min {r[2]:.2f}, max {r[3]:.2f}), context {r[4]} to {r[5]} rows")
    for name, spec in groups:
        got = [means[t] for t in spec.split(",") if t in means]
        print(group_line(name, got) if got else f"group {name}: no boot")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
