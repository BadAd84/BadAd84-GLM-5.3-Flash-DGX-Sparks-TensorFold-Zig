#!/usr/bin/env python3
"""forced_score.py - our drafter and our rule on a reply of production's, from a forced-arm.sh run.

Usage: forced_score.py forced.json records.jsonl rounds.log [cache.log]
Each forced request p (production's prompt plus its reply's first p tokens) is one request in rounds.log: its first
line holds our target's token at p (the anchor, at position len(prompt) + p) and our drafter's 7 drafts after it; the
request's later lines give what each round kept, so chain_log.score rebuilds our target's own continuation from p.
Per position: L = how many of the 7 drafts equal production's next tokens (the drafter alone, no cut), K = what our
rule and our target kept in the first round, G = how far our target follows production's text from p. K counts
against production's text exactly while our target follows it past the kept run (K + 1 < G); elsewhere min(K, L)
stands in and the position is flagged. Prints the reach by depth, the rounds our rule would take over production's
tokens beside production's own (the forced file's prod.rounds), and fixed-depth rounds f1..f7 (f7: every correct draft).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chain_log  # noqa: E402

CACHE = re.compile(r"prompt cache: (\d+) tokens, resumed at (\d+)")


def lead(a, b):
    n = 0
    while n < len(a) and n < len(b) and a[n] == b[n]:
        n += 1
    return n


def positions(forced, records, reqs):
    """Per forced position p >= 0: (agree, L, K, G); checks every request against its record."""
    prompt, reply = forced["prompt"], forced["reply"]
    if len(reqs) != len(records):
        raise ValueError(f"{len(reqs)} requests in the log, {len(records)} records")
    out = {}
    for rec, req in zip(records, reqs):
        p = rec["p"]
        first = req[0]
        if first[2] != len(prompt) + max(p, 0):
            raise ValueError(f"p {p}: the first round sits at {first[2]}, not {len(prompt) + max(p, 0)}")
        if p < 0:
            continue
        text, _ = chain_log.score(req) if len(req) > 1 else ([first[4]], [])
        G = lead(text, reply[p:])
        L = lead(first[5], reply[p + 1:p + 8])
        K = req[1][3] - 1 if len(req) > 1 else None
        if K is not None and not 0 <= K <= 7:
            raise ValueError(f"p {p}: the second round keeps {K + 1} rows; a round keeps 1 to 8")
        out[p] = (first[4] == reply[p], L, K, G)
    return out


def simulate(n_tokens, step):
    """Rounds over tokens 1..n-1 (token 0 is the prompt pass's), each keeping step(i) drafts at anchor i."""
    i = rounds = 0
    while i < n_tokens - 1:
        k = step(i)
        if not 0 <= k <= 7:
            raise ValueError(f"anchor {i}: a round cannot keep {k} drafts")
        i += k + 1
        rounds += 1
    return rounds


def paired(pos, reply, dump_path, edge, spec):
    """Our drafter against production's at every forced position both serves reach: production's chain walked on its
    own lattice for the same text (a TF_GLM_DRAFT_DUMP record of this reply) at pick edge `edge`, and `spec` (our rule)
    replayed on that lattice, so the rounds differ by the drafter alone."""
    import sim_rules                                  # draft_sim from the Python repo, read-only
    ds = sim_rules.ds
    d = ds.load_dump(dump_path)
    if [int(t) for t in d.tokens] != reply:
        raise ValueError(f"{dump_path} is not a record of this reply")
    d.meta["stop_eos"] = False          # rounds over the whole reply, as simulate() above counts them
    rule = ds.parse_rule(f"edge={edge}")
    both = [p for p, v in sorted(pos.items()) if v[0] and p < d.n]
    theirs = {p: lead(ds.walk(d, p, 7, rule).tokens, reply[p + 1:p + 8]) for p in both}
    worse = [p for p in both if pos[p][1] < theirs[p]]
    better = [p for p in both if pos[p][1] > theirs[p]]
    m = max(1, len(both))
    print(f"paired with production's lattice at edge {edge}: {len(both)} positions, whole-chain correct ours "
          f"{sum(pos[p][1] for p in both) / m:.3f} against production's {sum(theirs[p] for p in both) / m:.3f}; "
          f"ours shorter at {len(worse)}, longer at {len(better)}")
    for k in range(1, 8):
        print(f"  reach k={k}: ours {sum(pos[p][1] >= k for p in both) / m:.3f} production's "
              f"{sum(theirs[p] >= k for p in both) / m:.3f}")
    r = ds.run_policy([d], spec, sim_rules.OURS)
    print(f"  {spec} on production's lattice: {r.rounds} rounds, {(len(reply) - 1) / r.rounds:.3f} tokens a round "
          "(our rule, production's drafter; set beside our rule's rounds above, the difference is the drafter's)")
    return len(both), len(worse), len(better)


def main(argv):
    flags = {}
    while len(argv) > 2 and argv[-2].startswith("--"):
        flags[argv[-2]] = argv[-1]
        argv = argv[:-2]
    forced = json.load(open(argv[1]))
    records = [json.loads(line) for line in open(argv[2]) if line.strip()]
    reqs = chain_log.requests(chain_log.parse(argv[3]))
    if len(argv) > 4:
        resumed = [int(m.group(2)) for m in map(CACHE.search, open(argv[4], errors="replace")) if m]
        bad = sum(r != 0 for r in resumed)
        print(f"prompt cache lines {len(resumed)}, resumed past 0: {bad}" + ("  <- the measurement is void" if bad else ""))
    pos = positions(forced, records, reqs)
    n = len(forced["reply"])
    agree = [p for p, v in pos.items() if v[0]]
    exact = {p for p, (a, L, K, G) in pos.items() if a and K is not None and K + 1 < G}
    print(f"{len(pos)} positions forced, our target's token equals production's at {len(agree)}, "
          f"first-round K exact at {len(exact)}")
    reach = [sum(pos[p][1] >= k for p in agree) / max(1, len(agree)) for k in range(1, 8)]
    print("our drafter on production's text, reach k=1..7: " + " ".join(f"{x:.3f}" for x in reach)
          + f"; mean whole-chain correct {sum(pos[p][1] for p in agree) / max(1, len(agree)):.3f}")
    flagged = []

    def rule_step(i):
        v = pos.get(i)
        if v is None or not v[0] or v[2] is None:
            flagged.append(i)
            return 0
        if i not in exact:
            flagged.append(i)
            return min(v[2], v[1])
        return v[2]
    r = simulate(n, rule_step)
    prod = forced.get("prod") or {"rounds": 133}  # the first forced file (the prose reply) predates the prod field
    print(f"our rule on production's text: {r} rounds, {(n - 1) / r:.3f} tokens a round ({len(flagged)} rounds on "
          f"flagged positions); production's own: {prod['rounds']} rounds, {(n - 1) / prod['rounds']:.3f}")
    for depth in range(1, 8):
        rd = simulate(n, lambda i: min(depth, pos[i][1]) if i in pos and pos[i][0] else 0)
        print(f"  f{depth}: {rd} rounds, {(n - 1) / rd:.3f} tokens a round")
    if "--prod" in flags:
        paired(pos, forced["reply"], flags["--prod"], float(flags.get("--edge", "1.0")),
               flags.get("--rule", "fc7:0.7@edge=1.0"))


if __name__ == "__main__":
    main(sys.argv)
