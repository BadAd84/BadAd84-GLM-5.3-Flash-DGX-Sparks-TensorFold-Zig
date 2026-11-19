#!/usr/bin/env python3
"""score69.py [ROWS_DIR] - queue69: CHUNK_SOLO and ONEPASS_PIPE against the recipe, and HOST_ONCE on warm turns.

A: boots rec1 solo1 pipe1 pipe2 solo2 rec2 (--parallel 4 --context 1048576): cold first token at 8k / 32k / 120k (two reps a boot) and the
prose and code ids at 1 / 2 / 4 clients; each arm's mean over its two boots against the recipe's, with each boot's value shown, rounds and
reply digests compared across arms. B: ONEPASS_PIPE at 6 / 8 streams, boots r1 p1 p2 r2, pairs (r1, p1) (p2, r2). C: warm turns at ~250k,
both arms with request starts, boots r1 h1 h2 r2: idle and with three decoding streams.
"""
import json
import statistics as st
import sys

D = sys.argv[1] if len(sys.argv) > 1 else "docs/audit-2026-11-12/queue-rows/queue69"


def rows(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def cell(arm, kind, n):
    rs = rows(f"{D}/{arm}/{kind}{n}.jsonl")
    return {"agg": st.mean(r["agg_tok_s"] for r in rs), "rounds": tuple(r["draft_rounds"] for r in rs),
            "sha": tuple(sorted({tuple(r["sha"]) for r in rs}))}


def part_a():
    arms = {"rec": ("rec1", "rec2"), "solo": ("solo1", "solo2"), "pipe": ("pipe1", "pipe2")}
    cold = [r for r in rows(f"{D}/pf69/rows.jsonl") if r.get("case") == "cold"]
    print("== A cold first token, ms (each boot's two reps averaged; arm = mean of its two boots)")
    sizes = sorted({r["target_tokens"] for r in cold})
    for size in sizes:
        by = {}
        for a, boots in arms.items():
            by[a] = [st.mean(r["ttft_ms"] for r in cold if r["tag"] == b and r["target_tokens"] == size) for b in boots]
        shas = {a: {r["token_sha"] for r in cold if r["tag"] in arms[a] and r["target_tokens"] == size} for a in arms}
        rec = st.mean(by["rec"])
        line = f"{size // 1000}k: rec {by['rec'][0]:.0f} {by['rec'][1]:.0f}"
        for a in ("solo", "pipe"):
            m = st.mean(by[a])
            line += f" | {a} {by[a][0]:.0f} {by[a][1]:.0f} = {m / rec - 1:+.2%} (both boots under both rec boots: {max(by[a]) < min(by['rec'])})"
        line += f" | reply digests equal across arms: {len(set().union(*shas.values())) == 1}"
        print(line)
    for kind, label in (("P", "prose"), ("C", "code")):
        print(f"== A decode {label}, aggregate tok/s")
        for n in (1, 2, 4):
            c = {b: cell(f"a69-{b}", kind, n) for boots in arms.values() for b in boots}
            rec = st.mean(c[b]["agg"] for b in arms["rec"])
            line = f"{n}: rec " + " ".join(f"{c[b]['agg']:.2f}" for b in arms["rec"])
            for a in ("solo", "pipe"):
                m = st.mean(c[b]["agg"] for b in arms[a])
                line += f" | {a} " + " ".join(f"{c[b]['agg']:.2f}" for b in arms[a]) + f" = {m / rec - 1:+.2%}"
            rounds = {a: {c[b]["rounds"] for b in boots} for a, boots in arms.items()}
            line += f" | rounds {dict((a, sorted(v)) for a, v in rounds.items()) if len(set().union(*rounds.values())) > 1 else next(iter(rounds['rec']))[0]}"
            line += f" | reply sets {len({c[b]['sha'] for b in c})}"
            print(line)


def part_b():
    for kind, label in (("P", "prose"), ("C", "code")):
        print(f"== B ONEPASS_PIPE {label} at 6 / 8 streams, pairs (r1, p1) (p2, r2)")
        for n in (6, 8):
            c = {b: cell(f"b69-{b}", kind, n) for b in ("r1", "p1", "p2", "r2")}
            pairs = [("r1", "p1"), ("r2", "p2")]
            ratios = [c[p]["agg"] / c[r]["agg"] - 1 for r, p in pairs]
            print(f"{n}: rec {c['r1']['agg']:.2f} {c['r2']['agg']:.2f} | pipe {c['p1']['agg']:.2f} {c['p2']['agg']:.2f} | pairs "
                  + " ".join(f"{x:+.2%}" for x in ratios) + f" mean {st.mean(ratios):+.2%}"
                  + " | rounds " + " ".join(f"{b} {sum(c[b]['rounds'])}" for b in c)
                  + f" | reply sets {len({c[b]['sha'] for b in c})}")


def part_c():
    print("== C warm turn at ~250k (request starts on in both arms), first token ms")
    out = {}
    for b in ("r1", "h1", "h2", "r2"):
        rs = [r for r in rows(f"{D}/wt69-{b}/rows.jsonl") if r.get("case") == "warm"]
        idle = [r["ttft_ms"] for r in rs if r["load"] == 0]
        load = [r["ttft_ms"] for r in rs if r["load"] == 3]
        resumed = {r["resumed_at"] for r in rs}
        out[b] = (idle, load)
        print(f"{b}: idle {idle} load {load} resumed_at {sorted(resumed)} sha {sorted({r['token_sha'] for r in rs})}")
    for i, label in ((0, "idle"), (1, "loaded")):
        rec = st.mean(x for b in ("r1", "r2") for x in out[b][i])
        host = st.mean(x for b in ("h1", "h2") for x in out[b][i])
        print(f"{label}: recipe {rec:.1f} ms, HOST_ONCE {host:.1f} ms = {host / rec - 1:+.2%}")


if __name__ == "__main__":
    part_a()
    part_b()
    part_c()
