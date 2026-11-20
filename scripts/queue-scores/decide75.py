#!/usr/bin/env python3
"""decide75.py [ROWS75 [ROWS74]] - the adoption rule for queue75's candidates, written before the rows were read (scripts/queue-scores/score75.py's readers).

A candidate (each booted twice, forward and reversed order) goes into the recipe arm N of the final confirmation only when all four hold:
  1. replies: every cold digest, every chain turn's digest and every decode cell's reply set equals the controls' (rs1 to rs4).
  2. cold: both boots' first token is below the controls' mean at every size, and the pair's mean is below the controls' fastest boot
     at two of the three sizes (a gain larger than the controls' own spread).
  3. decode: in each of the six cells (prose and code at 1, 2 and 4 clients) the pair's mean is not below the controls' slowest boot.
  4. warm turns: the pair's mean of turns 2 to 8 is no more than 0.5% over the controls', and the first turn no more than 0.5% over.
"""
#
import statistics as st
import sys

d75 = sys.argv[1] if len(sys.argv) > 1 else "docs/audit-2026-11-12/queue-rows/queue75"
d74 = sys.argv[2] if len(sys.argv) > 2 else "docs/audit-2026-11-12/queue-rows/queue74"
sys.argv = ["score75", d75, d74]
import os  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score75 as S  # noqa: E402

CTL = S.CONTROLS
rs = S.cold_rows()
sizes = sorted({r["target_tokens"] for r in rs})


def cold_check(a, b):
    ok_both, wins = True, 0
    notes = []
    for size in sizes:
        ctl = S.ctl_list(lambda c: S.cold_ms(rs, c, size))
        x, y = S.cold_ms(rs, a, size), S.cold_ms(rs, b, size)
        if not ctl or x is None or y is None:
            return None, ["no cold rows"]
        m = st.mean(ctl)
        both_below = x < m and y < m
        win = st.mean([x, y]) < min(ctl)
        ok_both = ok_both and both_below
        wins += win
        notes.append(f"{size // 1000}k {S.pct(st.mean([x, y]), m)}{'' if both_below else ' (a boot above the controls)'}{' win' if win else ''}")
    return ok_both and wins >= 2, notes


def decode_check(a, b):
    notes, ok = [], True
    for kind in ("P", "C"):
        for n in (1, 2, 4):
            ctl = [S.cell(c, kind, n) for c in CTL]
            ctl = [c for c in ctl if c]
            x, y = S.cell(a, kind, n), S.cell(b, kind, n)
            if not ctl or not x or not y:
                return None, ["no decode rows"]
            pair = st.mean([x["agg"], y["agg"]])
            low = min(c["agg"] for c in ctl)
            bad = pair < low
            ok = ok and not bad
            notes.append(f"{kind}{n} {S.pct(pair, st.mean([c['agg'] for c in ctl]))}{' BELOW' if bad else ''}")
    return ok, notes


def reply_check(a, b):
    ok = True
    cold = [r for r in rs if r["tag"] in CTL + (a, b)]
    for size in sizes:
        for rep in {r["rep"] for r in cold if r["target_tokens"] == size}:
            if len({r["token_sha"] for r in cold if r["target_tokens"] == size and r["rep"] == rep}) != 1:
                ok = False
    ch = {t: S.chain_of(t) for t in CTL + (a, b)}
    ch = {t: c for t, c in ch.items() if c}
    for k in range(min(len(c) for c in ch.values())):
        if len({c[k]["token_sha"] for c in ch.values()}) != 1:
            ok = False
    for kind in ("P", "C"):
        for n in (1, 2, 4):
            shas = {S.cell(t, kind, n)["sha"] for t in CTL + (a, b) if S.cell(t, kind, n)}
            if len(shas) != 1:
                ok = False
    return ok


def chain_check(a, b):
    ctl = [S.chain_of(c) for c in CTL]
    ctl = [c for c in ctl if c]
    x, y = S.chain_of(a), S.chain_of(b)
    if not ctl or not x or not y:
        return None, ["no chain rows"]
    first = st.mean(c[0]["ttft_ms"] for c in ctl)
    warm = st.mean(st.mean(t["ttft_ms"] for t in c[1:]) for c in ctl)
    f = st.mean([x[0]["ttft_ms"], y[0]["ttft_ms"]]) / first - 1
    w = st.mean([st.mean(t["ttft_ms"] for t in x[1:]), st.mean(t["ttft_ms"] for t in y[1:])]) / warm - 1
    return f <= 0.005 and w <= 0.005, [f"first turn {f:+.2%}", f"turns 2+ {w:+.2%}"]


print(f"controls with cold rows: {[c for c in CTL if S.cold_ms(rs, c, sizes[0]) is not None]}")
for name, (a, b) in S.PAIRS.items():
    c, cn = cold_check(a, b)
    d, dn = decode_check(a, b)
    w, wn = chain_check(a, b)
    r = reply_check(a, b) if c is not None else None
    verdict = "ADOPT" if all(v is True for v in (c, d, w, r)) else "no" if any(v is False for v in (c, d, w, r)) else "incomplete"
    print(f"{name}: {verdict} | replies {r} | cold {c}: {'; '.join(cn)} | decode {d}: {' '.join(dn)} | warm {w}: {'; '.join(wn)}")
