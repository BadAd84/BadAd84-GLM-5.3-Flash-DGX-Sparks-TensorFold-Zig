#!/usr/bin/env python3
"""score68.py - queue68's candidate against the recipe as adjacent pairs.

1, 2, 4 clients: boots r1 c1 c2 r2 r3 c3 c4 r4 (b68-*), pairs (r1,c1) (c2,r2) (r3,c3) (c4,r4): each pair's ratio, their mean, sd, se,
and whether every candidate cell beats its partner. 6 and 8 streams: e68 r1 c1 c2 r2, pairs (r1,c1) (c2,r2). Prose and code ids.
Rounds and reply sets checked equal within an arm. Then the 24 prompts: per prompt the candidate's mean decode time over its four boots
against the recipe's, geometric mean with a bootstrap interval, by kind.
"""
import json, math, os, random, statistics as st, sys

D = sys.argv[1] if len(sys.argv) > 1 else "docs/audit-2026-11-12/queue-rows/queue68"


def cell(arm, kind, n):
    rows = [json.loads(l) for l in open(f"{D}/{arm}/{kind}{n}.jsonl") if l.strip()]
    return {"agg": st.mean(r["agg_tok_s"] for r in rows), "rounds": tuple(r["draft_rounds"] for r in rows),
            "sha": tuple(sorted({tuple(r["sha"]) for r in rows}))}


def pairs(pre, levels, plist):
    for kind, label in (("P", "prose"), ("C", "code")):
        print(f"== {label}")
        for n in levels:
            c = {a: cell(f"{pre}-{a}", kind, n) for p in plist for a in p}
            ratios = [c[b]["agg"] / c[a]["agg"] - 1 for a, b in plist]  # (recipe, candidate) in each pair
            mean = st.mean(ratios); sd = st.stdev(ratios) if len(ratios) > 1 else 0.0
            rec = [c[a]["agg"] for a, _ in plist]; cand = [c[b]["agg"] for _, b in plist]
            r_rounds = {c[a]["rounds"] for a, _ in plist}; c_rounds = {c[b]["rounds"] for _, b in plist}
            shas = {c[x]["sha"] for x in c}
            print(f"{n}: recipe {' '.join(f'{x:.2f}' for x in rec)} | candidate {' '.join(f'{x:.2f}' for x in cand)} | pairs "
                  + " ".join(f"{x:+.2%}" for x in ratios) + f" | mean {mean:+.2%} sd {sd:.2%} se {sd / math.sqrt(len(ratios)):.2%}"
                  + f" | candidate above its partner in {sum(x > 0 for x in ratios)} of {len(ratios)}; above every recipe cell: {min(cand) > max(rec)}"
                  + f" | rounds recipe {sorted(r_rounds)[0][0] if len(r_rounds) == 1 else r_rounds} candidate {sorted(c_rounds)[0][0] if len(c_rounds) == 1 else c_rounds}"
                  + f" | reply sets {len(shas)}")


def geo(xs):
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def boot(xs, n=10000, seed=1):
    rnd = random.Random(seed)
    m = sorted(geo([rnd.choice(xs) for _ in xs]) for _ in range(n))
    return m[int(0.025 * n)], m[int(0.975 * n)]


def prompts():
    def load(arm):
        by = {}
        for l in open(f"{D}/{arm}/pp.jsonl"):
            r = json.loads(l); by[r["name"]] = r
        return by
    R = [load(f"b68-{a}") for a in ("r1", "r2", "r3", "r4")]
    C = [load(f"b68-{a}") for a in ("c1", "c2", "c3", "c4")]
    names = list(R[0])
    same = all(len({x[n]["sha12"] for x in R + C}) == 1 for n in names)
    rr = {n: st.mean(x[n]["span_s"] for x in R) for n in names}
    cc = {n: st.mean(x[n]["span_s"] for x in C) for n in names}
    code = ["code", "code2", "code3", "code4", "rust", "go", "json", "shell", "math"]
    print(f"== 24 prompts: replies equal across all eight boots: {same}")
    for label, ns in (("all 24", names), ("code-like 9", [n for n in names if n in code]), ("prose-like 15", [n for n in names if n not in code])):
        xs = [rr[n] / cc[n] for n in ns]; lo, hi = boot(xs)
        print(f"{label}: candidate over recipe decode tok/s {geo(xs):.4f} ({lo:.4f} to {hi:.4f}), faster on {sum(x > 1 for x in xs)} of {len(xs)}; "
              f"rounds recipe {sum(R[0][n]['rounds'] for n in ns)} candidate {sum(C[0][n]['rounds'] for n in ns)}; decode s {sum(rr[n] for n in ns):.1f} / {sum(cc[n] for n in ns):.1f}")
    for i, (x, y) in enumerate(zip(R, C)):
        print(f"   boot pair {i + 1}: decode s recipe {sum(x[n]['span_s'] for n in names):.2f} candidate {sum(y[n]['span_s'] for n in names):.2f}")

def warm():
    """queue68's warm turns (longctx.py probe rows, the seeds of queue67): first token ms with the tokens the server had cached."""
    WT = os.path.join(os.path.dirname(os.path.normpath(D)), "queue67-68-warm")
    print("== warm turns (queue68: prod2 = production again, zig2 = the recipe, zigrs2 = the recipe with TF_GLM_REQUEST_STARTS=1)")
    for who in ("prod2", "zig2", "zigrs2"):
        rs = [json.loads(l) for l in open(f"{WT}/{who}.jsonl") if l.strip()]
        by = {}
        for r in rs:
            if r.get("case") == "warm":
                by.setdefault(r["tag"], []).append(r)
        for tag, v in by.items():
            print(f"{tag}: {' '.join(str(r['ttft_ms']) for r in v)} ms; cached {sorted({r.get('cached_tokens') for r in v})} of {sorted({r['prompt_tokens'] for r in v})[:2]}; "
                  f"kept states {sorted({r.get('kept_states') for r in v})}")


if __name__ == "__main__":
    pairs("b68", (1, 2, 4), [("r1", "c1"), ("r2", "c2"), ("r3", "c3"), ("r4", "c4")])
    pairs("e68", (6, 8), [("r1", "c1"), ("r2", "c2")])
    prompts()
    warm()
