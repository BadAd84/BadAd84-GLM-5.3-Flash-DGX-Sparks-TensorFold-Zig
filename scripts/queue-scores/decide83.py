#!/usr/bin/env python3
"""decide83.py [--rows DIR] [--apply ENVFILE...] - queue83: which of patch 0038's switches join the final recipe N.

Rows (scripts/queues/queue83.sh): DIR/rows.jsonl (case cold: tag, target_tokens, rep, ttft_ms, token_sha), DIR/<arm>/chain.jsonl (tag c74), DIR/dec-<arm>/{P,C}<clients>.jsonl.
Each arm is N with request starts plus a set of switches, one boot; the sets are nested and every set has two boots, the controls ca and cb (no switch) around them:
  F = TF_GLM_OVN_PIECE_FRONT (boots fa fb), B = F + TF_GLM_OVN_PIECE_FFN (ba bb), M = B + TF_GLM_OVN_PIECE_MLA (ma mb).
The pair na nb (the setting queue81 read) and ga gb (M with it) are reported against the same controls and decide nothing here. The rule was written before any row existed:
  1. replies: every cold request, conversation turn and decode cell has the controls' digests, across every boot;
  2. a set joins only if the mean of its two boots' cold first token is at least 1.0% under the controls' mean at two of the three sizes (8k, 32k, 120k), neither boot is over the
     slower control at any size, and each boot's first turn and turns 2 to 8 are not over the slower control's;
  3. nested sets: a larger set keeps its extra switch only if its mean cold gain over the three sizes beats the adopted smaller set's by 0.3 points or more; the set that joins is the
     largest one that passes 1 and 2 in that way.
With --apply, each ENVFILE's NEWX line gains the set's flags once and its IMG line becomes glm53-zig:v129zc (the image that carries the switches).
"""
import json
import os
import re
import statistics as st
import sys

SETS = {"F": ("fa", "fb"), "B": ("ba", "bb"), "M": ("ma", "mb")}
FLAGS = {"F": ["-e TF_GLM_OVN_PIECE_FRONT=1"], "B": ["-e TF_GLM_OVN_PIECE_FRONT=1", "-e TF_GLM_OVN_PIECE_FFN=1"],
         "M": ["-e TF_GLM_OVN_PIECE_FRONT=1", "-e TF_GLM_OVN_PIECE_FFN=1", "-e TF_GLM_OVN_PIECE_MLA=1"]}
CONTROLS = ("ca", "cb")
EXTRA = {"na nb (pp)": ("na", "nb"), "ga gb (M + pp)": ("ga", "gb")}
SIZES = (8000, 32000, 120000)
KINDS = ("P", "C")
LEVELS = (1, 4)
IMAGE = "glm53-zig:v129zc"
MIN_GAIN, MIN_STEP = 0.01, 0.003

args = sys.argv[1:]
apply_to = []
if "--apply" in args:
    cut = args.index("--apply")
    apply_to = args[cut + 1:]
    args = args[:cut]
D = os.path.expanduser("~/bench/f83-c")
if "--rows" in args:
    D = args[args.index("--rows") + 1]


def jl(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


ROWS = [r for r in jl(f"{D}/rows.jsonl") if r.get("case") == "cold"]


def cold(boot, size):
    v = [r["ttft_ms"] for r in ROWS if r["tag"] == boot and r["target_tokens"] == size]
    return st.mean(v) if v else None


def cold_sha(boot, size):
    return frozenset((r["rep"], r["token_sha"]) for r in ROWS if r["tag"] == boot and r["target_tokens"] == size)


def chain(boot):
    return [r for r in jl(f"{D}/{boot}/chain.jsonl") if r.get("tag") == "c74"]


def dec_sha(boot, kind, n):
    r = jl(f"{D}/dec-{boot}/{kind}{n}.jsonl")
    return tuple(sorted({tuple(x["sha"]) for x in r})) if r else None


def have(boot):
    return all(cold(boot, s) is not None for s in SIZES) and bool(chain(boot))


def digests(boot):
    d = {("cold", s): cold_sha(boot, s) for s in SIZES}
    d.update({("turn", k): x["token_sha"] for k, x in enumerate(chain(boot))})
    d.update({("dec", k, n): dec_sha(boot, k, n) for k in KINDS for n in LEVELS if dec_sha(boot, k, n)})
    return d


def warm(boot):
    return st.mean(x["ttft_ms"] for x in chain(boot)[1:])


ctl = [c for c in CONTROLS if have(c)]
print("controls with rows:", " ".join(ctl))
if len(ctl) < 2:
    print("NOT DECIDED: fewer than two controls")
    sys.exit(0)
ctl_cold = {s: [cold(c, s) for c in ctl] for s in SIZES}
ctl_first = [chain(c)[0]["ttft_ms"] for c in ctl]
ctl_warm = [warm(c) for c in ctl]
ref = digests(ctl[0])
same_ctl = all(digests(c) == ref for c in ctl)


def read(boots):
    """(gains per size, replies equal, never over the slower control, first and warm not over, notes) for a set's boots."""
    boots = [b for b in boots if have(b)]
    if len(boots) < 2:
        return None
    gains = [1 - st.mean(cold(b, s) for b in boots) / st.mean(ctl_cold[s]) for s in SIZES]
    same = same_ctl and all(all(k not in ref or v == ref[k] for k, v in digests(b).items()) for b in boots)
    never_over = all(cold(b, s) <= max(ctl_cold[s]) for b in boots for s in SIZES)
    warm_ok = all(chain(b)[0]["ttft_ms"] <= max(ctl_first) and warm(b) <= max(ctl_warm) for b in boots)
    first = st.mean(chain(b)[0]["ttft_ms"] for b in boots)
    notes = [f"cold {' '.join(f'{g:+.2%}' for g in gains)} (mean {st.mean(gains):+.2%}, at least 1.0% at {sum(g >= MIN_GAIN for g in gains)} of 3 sizes)",
             f"replies equal {same}", f"no boot over the slower control {never_over}",
             f"first turn {first:.0f} ms (controls {min(ctl_first)} to {max(ctl_first)}), turns 2+ {st.mean(warm(b) for b in boots):.0f} ms (controls {min(ctl_warm):.0f} to {max(ctl_warm):.0f}), not over {warm_ok}"]
    return gains, same, never_over, warm_ok, notes


adopted = None
adopted_gain = 0.0
for name, boots in SETS.items():
    r = read(boots)
    if r is None:
        print(f"{name}: NOT DECIDED (boots missing)")
        continue
    gains, same, never_over, warm_ok, notes = r
    ok = same and sum(g >= MIN_GAIN for g in gains) >= 2 and never_over and warm_ok
    step = st.mean(gains) - adopted_gain
    joins = ok and (adopted is None or step >= MIN_STEP)
    print(f"{name} ({' '.join(FLAGS[name])}): {'JOINS' if joins else ('passes, extra switch not worth it' if ok else 'no')} | " + " | ".join(notes) + (f" | over the adopted set {step:+.2%}" if adopted else ""))
    if joins:
        adopted, adopted_gain = name, st.mean(gains)
for label, boots in EXTRA.items():
    r = read(boots)
    print(f"{label}: " + ("NOT DECIDED (boots missing)" if r is None else "reported | " + " | ".join(r[4])))

if adopted:
    print("ADD " + " ".join(FLAGS[adopted]))
for path in apply_to:
    text = open(path, encoding="utf-8").read()
    m = re.search(r'^NEWX="([^"]*)"', text, re.M)
    if not m or not adopted:
        continue
    add = " ".join(f for f in FLAGS[adopted] if f not in m.group(1))
    new = text[:m.end(1)] + (" " + add if add else "") + text[m.end(1):]
    new = re.sub(r"^IMG=.*$", f"IMG={IMAGE}", new, flags=re.M)
    if new != text:
        open(path, "w", encoding="utf-8", newline="\n").write(new)
        print(f"{path}: NEWX gains {add or 'nothing'}, IMG={IMAGE}")
