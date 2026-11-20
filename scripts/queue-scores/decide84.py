#!/usr/bin/env python3
"""decide84.py [--rows DIR] [--apply ENVFILE...] - queue84: which TF_GLM_OVN_FRONT_ROWS value and which TF_GLM_OVERLAP_PIECES count join the final recipe N'.

Rows (scripts/queues/queue84.sh): DIR/rows.jsonl (case cold: tag, target_tokens, rep, ttft_ms, token_sha), DIR/<boot>/chain.jsonl (tag c74), DIR/dec-<boot>/{P,C}1.jsonl.
Two blocks, each a setting's two boots against the block's two controls (the recipe as it stands, both boots at its ends of the block):
  front: controls r4a r4b; TF_GLM_OVN_FRONT_ROWS=512 (r5a r5b), 768 (r7a r7b), 2048 (r2a r2b);
  pieces: controls k4a k4b; TF_GLM_OVERLAP_PIECES=2 (k2a k2b), 3 (k3a k3b), 6 (k6a k6b), 8 (k8a k8b).
kca (TF_GLM_OVN_KDA_CHUNKED=1) and kva (TF_GLM_OVN_KVB8=1) change numerics: they are reported against the pieces block's controls and join nothing.
The rule was written before any row existed (OVERNIGHT section 59):
  1. replies: every cold request, conversation turn and decode cell has the block's digests, across the controls and the setting's boots;
  2. neither boot of a setting is over the slower control by more than 1.0% at any cold size or on the first turn (a boot's cold time varies about 1.5% between boots),
     and greedy decode at one client (the mean of the prose and code runs) is not more than 1.0% under the controls' mean;
  3. a FRONT_ROWS value: the mean of turns 2 to 8 is at least 1.0% under the controls' mean and the mean of the three cold sizes is not over the controls' mean by more than 0.3%;
     a piece count: the mean of the three cold sizes is at least 0.5% under the controls' mean and turns 2 to 8 are not over their mean by more than 0.3%;
  4. of the values of a block that pass, the one with the larger sum of its cold gain and its warm gain joins.
With --apply, each ENVFILE's NEWX line gains TF_GLM_OVN_FRONT_ROWS=N (or has TF_GLM_OVERLAP_PIECES=4 replaced by the count) and its IMG line becomes glm53-zig:v129zd.
"""
import json
import os
import re
import statistics as st
import sys

BLOCKS = {
    "front": {"controls": ("r4a", "r4b"), "settings": {"512": ("r5a", "r5b"), "768": ("r7a", "r7b"), "2048": ("r2a", "r2b")}},
    "pieces": {"controls": ("k4a", "k4b"), "settings": {"2": ("k2a", "k2b"), "3": ("k3a", "k3b"), "6": ("k6a", "k6b"), "8": ("k8a", "k8b")}},
}
NUMERICS = {"kca": "TF_GLM_OVN_KDA_CHUNKED=1", "kva": "TF_GLM_OVN_KVB8=1"}
SIZES = (8000, 32000, 120000)
KINDS = ("P", "C")
TOL = 0.01
MIN_WARM, MIN_COLD, SLACK = 0.01, 0.005, 0.003
IMAGE = "glm53-zig:v129zd"

args = sys.argv[1:]
apply_to = []
if "--apply" in args:
    cut = args.index("--apply")
    apply_to = args[cut + 1:]
    args = args[:cut]
D = os.path.expanduser("~/bench/f84-c")
if "--rows" in args:
    D = args[args.index("--rows") + 1]


def jl(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


ROWS = [r for r in jl(f"{D}/rows.jsonl") if r.get("case") == "cold"]


def cold(boot, size):
    v = [r["ttft_ms"] for r in ROWS if r["tag"] == boot and r["target_tokens"] == size]
    return st.mean(v) if v else None


def chain(boot):
    return [r for r in jl(f"{D}/{boot}/chain.jsonl") if r.get("tag") == "c74"]


def warm(boot):
    return st.mean(x["ttft_ms"] for x in chain(boot)[1:])


def dec(boot, kind):
    return jl(f"{D}/dec-{boot}/{kind}1.jsonl")


def have(boot):
    return all(cold(boot, s) is not None for s in SIZES) and len(chain(boot)) > 1 and all(dec(boot, k) for k in KINDS)


def speed(boot):
    return st.mean(st.mean(x["agg_tok_s"] for x in dec(boot, k)) for k in KINDS)


def digests(boot):
    d = {("cold", r["target_tokens"], r["rep"]): r["token_sha"] for r in ROWS if r["tag"] == boot}
    d.update({("turn", k): x["token_sha"] for k, x in enumerate(chain(boot))})
    d.update({("dec", k): tuple(sorted({tuple(x["sha"]) for x in dec(boot, k)})) for k in KINDS})
    return d


def read(ctl, boots, kind):
    """(passes, cold gain, warm gain, notes) of a setting's boots against the block's controls, or None when a boot is missing."""
    if len(boots) < 2 or not all(have(b) for b in boots):
        return None
    ref = digests(ctl[0])
    same = all(digests(c) == ref for c in ctl) and all(digests(b) == ref for b in boots)
    ctl_cold = {s: [cold(c, s) for c in ctl] for s in SIZES}
    ctl_first = [chain(c)[0]["ttft_ms"] for c in ctl]
    cold_gain = st.mean(1 - st.mean(cold(b, s) for b in boots) / st.mean(ctl_cold[s]) for s in SIZES)
    warm_gain = 1 - st.mean(warm(b) for b in boots) / st.mean(warm(c) for c in ctl)
    not_over = all(cold(b, s) <= max(ctl_cold[s]) * (1 + TOL) for b in boots for s in SIZES) and all(chain(b)[0]["ttft_ms"] <= max(ctl_first) * (1 + TOL) for b in boots)
    decode = st.mean(speed(b) for b in boots) / st.mean(speed(c) for c in ctl) - 1
    decode_ok = decode >= -TOL
    shape = warm_gain >= MIN_WARM and cold_gain >= -SLACK if kind == "front" else cold_gain >= MIN_COLD and warm_gain >= -SLACK
    notes = f"cold mean {cold_gain:+.2%}, turns 2+ {warm_gain:+.2%}, decode at 1 client {decode:+.2%}, replies equal {same}, no boot over the slower control by more than 1.0% {not_over}"
    return same and not_over and decode_ok and shape, cold_gain, warm_gain, notes


winners = {}
for block, spec in BLOCKS.items():
    ctl = [c for c in spec["controls"] if have(c)]
    if len(ctl) < 2:
        print(f"{block}: NOT DECIDED (fewer than two controls with rows)")
        continue
    best = None
    for value, boots in spec["settings"].items():
        r = read(ctl, boots, block)
        if r is None:
            print(f"{block} {value}: NOT DECIDED (boots missing)")
            continue
        ok, cold_gain, warm_gain, notes = r
        print(f"{block} {value} ({' '.join(boots)}): {'passes' if ok else 'no'} | {notes}")
        if ok and (best is None or cold_gain + warm_gain > best[1]):
            best = (value, cold_gain + warm_gain)
    if best:
        winners[block] = best[0]
        print(f"{block}: {best[0]} JOINS (cold gain plus warm gain {best[1]:+.2%})")
    else:
        print(f"{block}: nothing joins")
pc = [c for c in BLOCKS["pieces"]["controls"] if have(c)]
for boot, flag in NUMERICS.items():
    if len(pc) < 2 or not have(boot):
        print(f"{boot} ({flag}): NOT DECIDED (boot or controls missing)")
        continue
    ref = digests(pc[0])
    now = digests(boot)
    differ = sum(1 for k in ref if now.get(k) != ref[k])
    cold_gain = st.mean(1 - cold(boot, s) / st.mean(cold(c, s) for c in pc) for s in SIZES)
    warm_gain = 1 - warm(boot) / st.mean(warm(c) for c in pc)
    print(f"{boot} ({flag}): reported, joins nothing | cold mean {cold_gain:+.2%}, turns 2+ {warm_gain:+.2%}, decode at 1 client {speed(boot) / st.mean(speed(c) for c in pc) - 1:+.2%}, "
          f"{differ} of {len(ref)} reply digests differ from the controls'")

for path in apply_to:
    text = open(path, encoding="utf-8").read()
    m = re.search(r'^NEWX="([^"]*)"', text, re.M)
    if not m or not winners:
        continue
    newx = m.group(1)
    if "front" in winners:
        flag = f"-e TF_GLM_OVN_FRONT_ROWS={winners['front']}"
        newx = re.sub(r"-e TF_GLM_OVN_FRONT_ROWS=\d+", flag, newx) if "TF_GLM_OVN_FRONT_ROWS=" in newx else f"{newx} {flag}"
    if "pieces" in winners:
        newx = re.sub(r"TF_GLM_OVERLAP_PIECES=\d+", f"TF_GLM_OVERLAP_PIECES={winners['pieces']}", newx)
    new = text[:m.start(1)] + newx + text[m.end(1):]
    new = re.sub(r"^IMG=.*$", f"IMG={IMAGE}", new, flags=re.M)
    if new != text:
        open(path, "w", encoding="utf-8", newline="\n").write(new)
        print(f"{path}: NEWX is now '{newx}', IMG={IMAGE}")
