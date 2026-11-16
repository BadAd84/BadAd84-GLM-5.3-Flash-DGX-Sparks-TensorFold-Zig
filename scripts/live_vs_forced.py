#!/usr/bin/env python3
"""live_vs_forced.py FORCED.json live.log rounds.log - does the drafter draft the same chain mid-stream as right after a prompt pass?

A forced-arm.sh run with LIVE=1 on this engine's OWN reply (FORCED.json: its prompt and that reply) leaves two logs of the same text:
live.log, the one unforced request, whose rounds draft from a context the decode rounds built (each round's kept rows); and rounds.log,
the teacher-forced requests, whose first round at every position drafts from a context a prompt pass built over the same tokens.
For each live round (anchor at reply position p) this pairs the 7 picks with the forced request's 7 picks at p and prints: how many
chains are identical, the correct lead L of each (against the reply) and its mean, the reach by depth for both, and the rounds each
would take over the reply if every correct draft were kept (the live log's own anchors would take the live rounds only where the cut
kept every correct draft). Equal picks: the forced method measures the live drafter, and a text's rounds are the text's. Shorter live
leads: drafting mid-stream is weaker than after a prompt pass, which no forced run can see.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chain_log  # noqa: E402


def lead(drafts, ref):
    n = 0
    while n < len(drafts) and n < len(ref) and drafts[n] == ref[n]:
        n += 1
    return n


def greedy(n_tokens, step):
    """Rounds over reply tokens 1..n-1, each keeping step(i) drafts at anchor i."""
    i = rounds = 0
    while i < n_tokens - 1:
        i += step(i) + 1
        rounds += 1
    return rounds


def main(argv):
    forced = json.load(open(argv[1]))
    prompt, reply = forced["prompt"], forced["reply"]
    live = chain_log.requests(chain_log.parse(argv[2]))
    if len(live) != 1:
        raise SystemExit(f"{argv[2]} holds {len(live)} requests, not the one unforced run")
    live = live[0]
    after = {}
    for req in chain_log.requests(chain_log.parse(argv[3])):
        p = req[0][2] - len(prompt)
        if p >= 0:
            after[p] = req[0]
    pairs, off_text = [], 0
    for r in live:
        p = r[2] - len(prompt)
        if p < 0 or p + 8 > len(reply) or p not in after:
            continue
        if r[4] != reply[p] or after[p][4] != reply[p]:
            off_text += 1
            continue
        ref = reply[p + 1:p + 8]
        pairs.append((p, r[5], after[p][5], lead(r[5], ref), lead(after[p][5], ref)))
    n = len(pairs)
    same = sum(a == b for _, a, b, _, _ in pairs)
    first = sum(a[:1] == b[:1] for _, a, b, _, _ in pairs)
    print(f"{len(live)} live rounds, {n} paired with a forced request at the same position ({off_text} off the text, the rest within 7 of the end)")
    print(f"identical 7-pick chains at {same} of {n} ({same / n:.1%}); identical first pick at {first} of {n}")
    for label, k in (("mid-stream (live)", 3), ("after a prompt pass (forced)", 4)):
        ls = [x[k] for x in pairs]
        print(f"{label}: mean correct lead {sum(ls) / n:.3f}; reach k=1..7 " + " ".join(f"{sum(v >= d for v in ls) / n:.3f}" for d in range(1, 8)))
    shorter = sum(x[3] < x[4] for x in pairs); longer = sum(x[3] > x[4] for x in pairs)
    print(f"live lead shorter than forced at {shorter}, longer at {longer}, equal at {n - shorter - longer}")
    allp = {p: lead(r[5], reply[p + 1:p + 8]) for p, r in after.items() if r[4] == reply[p]}
    f7 = greedy(len(reply), lambda i: allp.get(i, 0))
    own = forced.get("prod") or {}
    print(f"every correct forced draft kept: {f7} rounds over the reply; the live run took {own.get('rounds')} rounds ({len(live)} logged)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
