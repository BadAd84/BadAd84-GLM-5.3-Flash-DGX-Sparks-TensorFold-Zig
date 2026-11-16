#!/usr/bin/env python3
"""chain_log.py - one stream's DFlash2 rounds from rank 0's log (TF_GLM_DFLASH2_LOG lines), scored against the reply.

A line is `dflash2 round C: slot S pos P kept N anchor A drafts { d0, ..., d6 }` (Z:dflash.zig:356): the anchor (the
round's pending token) sits at position P (Z:cuda_engine.zig:480-484, Z:dflash.zig:337-340), the 7 drafts are the
selector's whole chain before any cut, N is the rows the round kept from the previous one (0 at a request's first
round, Z:cuda_lanes.zig:521-526). So the previous round committed its anchor plus N - 1 drafts, the next anchor sits at
P + N, and the reply is rebuilt from the lines alone. Per round, L = how many of the 7 drafts equal the reply (the
chain's own quality, no cut) and K = N_next - 1 (what the cut and the verify kept). Two logs of the same text compare
picks (L, which the edge weight moves) and stops (K against L, which the chance temperature and the cut move).

Usage: chain_log.py r0-P1.log [other-arm r0-P1.log]
"""
import re
import sys

LINE = re.compile(r"dflash2 round (\d+): slot (\d+) pos (\d+) kept (\d+) anchor (\d+) drafts [\[{]([^\]}]*)[\]}]")


def parse(path):
    """[(call, slot, pos, kept, anchor, drafts)] in log order."""
    out = []
    for line in open(path, errors="replace"):
        m = LINE.search(line)
        if m:
            drafts = [int(x) for x in re.findall(r"\d+", m.group(6))]
            out.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)), drafts))
    return out


def requests(rows):
    """The lines cut into requests: a request starts at a round that kept nothing (its first, anchored on the prompt
    pass's token). Checks that every other round's position is the previous one's plus its kept rows. Rounds before
    the first request start are the tail of a request the log's head cut off (bench-arm.sh keeps rank 0's last 800
    lines): they are skipped and counted on stderr."""
    reqs, cur, skipped = [], None, 0
    for r in rows:
        if r[3] == 0:
            cur = []
            reqs.append(cur)
        elif cur is None:
            skipped += 1
            continue
        elif r[2] != cur[-1][2] + r[3]:
            raise ValueError(f"round {r[0]}: pos {r[2]} is not {cur[-1][2]} + kept {r[3]}")
        cur.append(r)
    if skipped:
        print(f"chain_log: skipped {skipped} rounds before the first request start (a head the log cut off)",
              file=sys.stderr)
    return reqs


def score(req):
    """The rebuilt reply (from the first token to the last round's anchor) and, per round with 7 known successors,
    (L, K): the chain's correct prefix and what the round kept."""
    text = []
    for r, nxt in zip(req, req[1:]):
        n = nxt[3]
        if n - 1 > len(r[5]):
            raise ValueError(f"round {nxt[0]} keeps {n} rows, more than its 7 drafts allow")
        text += [r[4]] + r[5][:n - 1]
    text.append(req[-1][4])
    p0 = req[0][2]
    per = []
    for r, nxt in zip(req, req[1:]):
        at = r[2] - p0
        if at + 1 + len(r[5]) > len(text) - 1:      # the last round's anchor is the last token known for sure
            break
        ref = text[at + 1:at + 1 + len(r[5])]
        L = 0
        while L < len(r[5]) and r[5][L] == ref[L]:
            L += 1
        per.append((L, nxt[3] - 1))
    return text, per


def summary(per):
    n = len(per)
    if not n:
        return {}
    reach = [sum(L >= k for L, _ in per) / n for k in range(1, 8)]
    kept = sum(K for _, K in per) / n
    full = sum(L for L, _ in per) / n
    cut_early = [(L, K) for L, K in per if K < L]
    return {"rounds": n, "mean_L": full, "mean_K": kept, "reach": reach, "cut_early": len(cut_early) / n,
            "lost": sum(L - K for L, K in cut_early) / n}


def report(path):
    reqs = requests(parse(path))
    out = []
    for i, req in enumerate(reqs):
        text, per = score(req)
        s = summary(per)
        out.append((text, s))
        if s:
            print(f"{path} request {i}: {len(text)} tokens known, {s['rounds']} scored rounds, kept {s['mean_K']:.3f} "
                  f"a round, whole-chain correct {s['mean_L']:.3f}, reach k=1..7 "
                  + " ".join(f"{x:.3f}" for x in s["reach"])
                  + f", cut before the first miss in {s['cut_early']:.1%} of rounds ({s['lost']:.3f} drafts a round)")
    return out


def main(argv):
    a = report(argv[1])
    if len(argv) > 2:
        b = report(argv[2])
        for i, ((ta, sa), (tb, sb)) in enumerate(zip(a, b)):
            n = min(len(ta), len(tb))
            same = ta[:n] == tb[:n]
            print(f"request {i}: the two logs' replies {'agree' if same else 'DIFFER'} over {n} tokens"
                  + (f"; picks (mean L) {sa['mean_L']:.3f} -> {sb['mean_L']:.3f}, kept {sa['mean_K']:.3f} -> "
                     f"{sb['mean_K']:.3f}" if same and sa and sb else ""))


if __name__ == "__main__":
    main(sys.argv)
