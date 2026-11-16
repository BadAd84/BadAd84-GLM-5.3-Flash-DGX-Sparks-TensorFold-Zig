#!/usr/bin/env python3
"""per_prompt_table.py A.jsonl B.jsonl [--names A,B] - two engines' per_prompt.py rows paired by prompt: is a difference systematic?

Each engine answers each prompt with its own text, so a single prompt's tokens a round differ by the text; over a set of prompts the paired
ratios show whether one engine keeps more tokens a round systematically. Prints, per prompt: rounds, tokens a round and ms a round (span
over rounds, one stream) for both, and the ratios B over A; then the geometric mean of each ratio with a bootstrap 95% interval over
prompts (10,000 resamples, fixed seed), how many prompts favour each side, and the totals. A prompt whose two reps disagree within an
engine, or whose token count is not the same on both, is listed and left out.
"""
import json
import math
import random
import sys


def load(path):
    by = {}
    for line in open(path):
        r = json.loads(line)
        by.setdefault(r["name"], []).append(r)
    return by


def geo(xs):
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def boot(xs, n=10000, seed=1):
    rnd = random.Random(seed)
    means = sorted(geo([rnd.choice(xs) for _ in xs]) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


def main(argv):
    names = ["A", "B"]
    if "--names" in argv:
        i = argv.index("--names"); names = argv[i + 1].split(","); del argv[i:i + 2]
    a, b = load(argv[0]), load(argv[1])
    rows, skipped = [], []
    for name in a:
        if name not in b:
            skipped.append((name, "missing on the second")); continue
        ra, rb = a[name], b[name]
        if len({r["rounds"] for r in ra}) != 1 or len({r["sha12"] for r in ra}) != 1 or len({r["rounds"] for r in rb}) != 1 or len({r["sha12"] for r in rb}) != 1:
            skipped.append((name, "reps differ")); continue
        if not ra[0]["rounds"] or not rb[0]["rounds"] or ra[0]["tokens"] != rb[0]["tokens"]:
            skipped.append((name, f"tokens {ra[0]['tokens']} against {rb[0]['tokens']}, rounds {ra[0]['rounds']} against {rb[0]['rounds']}")); continue
        sa = sum(r["span_s"] for r in ra) / len(ra); sb = sum(r["span_s"] for r in rb) / len(rb)
        rows.append({"name": name, "tok": ra[0]["tokens"], "ra": ra[0]["rounds"], "rb": rb[0]["rounds"], "da": ra[0]["drafted"], "db": rb[0]["drafted"],
                     "ka": ra[0]["accepted"], "kb": rb[0]["accepted"], "sa": sa, "sb": sb, "same": ra[0]["sha12"] == rb[0]["sha12"]})
    A, B = names
    print(f"| prompt | tokens | rounds {A} | rounds {B} | tokens a round {A} | {B} | {B}/{A} | ms a round {A} | {B} | {B}/{A} | tok/s {B}/{A} | same text |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    tpr, mpr, tps = [], [], []
    for r in rows:
        ta, tb = r["tok"] / r["ra"], r["tok"] / r["rb"]
        ma, mb = 1e3 * r["sa"] / r["ra"], 1e3 * r["sb"] / r["rb"]
        tpr.append(tb / ta); mpr.append(mb / ma); tps.append(r["sa"] / r["sb"])
        print(f"| {r['name']} | {r['tok']} | {r['ra']} | {r['rb']} | {ta:.3f} | {tb:.3f} | {tb / ta:.3f} | {ma:.1f} | {mb:.1f} | {mb / ma:.3f} | {r['sa'] / r['sb']:.3f} | {'yes' if r['same'] else 'no'} |")
    n = len(rows)
    print(f"\n{n} prompts paired; skipped: {skipped if skipped else 'none'}")
    for label, xs in (("tokens a round", tpr), ("ms a round", mpr), ("decode tok/s (one stream, first to last chunk)", tps)):
        lo, hi = boot(xs)
        print(f"{label}, {B} over {A}: geometric mean {geo(xs):.4f} (95% bootstrap interval {lo:.4f} to {hi:.4f}); {B} higher on {sum(x > 1 + 1e-9 for x in xs)} of {n}, range {min(xs):.3f} to {max(xs):.3f}")
    Ra, Rb = sum(r["ra"] for r in rows), sum(r["rb"] for r in rows); T = sum(r["tok"] for r in rows)
    Sa, Sb = sum(r["sa"] for r in rows), sum(r["sb"] for r in rows)
    print(f"totals over the {n} prompts: {T} tokens; rounds {A} {Ra}, {B} {Rb} ({Rb / Ra - 1:+.1%}); tokens a round {A} {T / Ra:.3f}, {B} {T / Rb:.3f}; ms a round {A} {1e3 * Sa / Ra:.1f}, {B} {1e3 * Sb / Rb:.1f}; "
          f"decode seconds {A} {Sa:.1f}, {B} {Sb:.1f} ({B} tok/s {Sa / Sb - 1:+.1%})")
    print(f"drafted a round {A} {sum(r['da'] for r in rows) / Ra:.2f}, {B} {sum(r['db'] for r in rows) / Rb:.2f}; acceptance {A} {sum(r['ka'] for r in rows) / sum(r['da'] for r in rows):.3f}, {B} {sum(r['kb'] for r in rows) / sum(r['db'] for r in rows):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
