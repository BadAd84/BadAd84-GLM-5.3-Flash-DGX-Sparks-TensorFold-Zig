#!/usr/bin/env python3
"""decide84.py [--rows DIR] [--apply ENVFILE...] - queues 84, 87, 88, 89 and 90: which TF_GLM_OVN_FRONT_ROWS value, TF_GLM_OVERLAP_PIECES count and whether TF_GLM_OVN_PIECE_KDA, TF_GLM_OVN_SOLO_TO_START and TF_GLM_OVN_RESTORE_HELD join the final recipe N'.

Rows (scripts/queues/queue84.sh): DIR/rows.jsonl (case cold: tag, target_tokens, rep, ttft_ms, token_sha), DIR/<boot>/chain.jsonl (tag c74), DIR/dec-<boot>/{P,C}1.jsonl.
Blocks, each a setting's boots against the block's controls (the recipe as it stands, run at both ends of the block):
  front: controls r4a r4b; TF_GLM_OVN_FRONT_ROWS=512 (r5a r5b), 768 (r7a r7b), 2048 (r2a r2b);
  pieces: controls k4a k4b; TF_GLM_OVERLAP_PIECES=2 (k2a k2b), 3 (k3a k3b), 6 (k6a k6b), 8 (k8a k8b);
  kda (queue87, rows in the same directory): controls n9a n9b; TF_GLM_OVN_PIECE_KDA=1 (d9a d9b), read by the piece-count rule.
  warm3 (queue88, rows in the same directory): controls w4a w4b w4c w4d (4 pieces); TF_GLM_OVERLAP_PIECES=3 (w3a w3b w3c w3d), run in the order w4a w3a w3b w4b w4c w3c w3d w4d.
  held (queue90, rows in the same directory): controls h0a h0b h0c h0d; TF_GLM_OVN_RESTORE_HELD=1 (h1a h1b h1c h1d), run in the order h0a h1a h1b h0b h0c h1c h1d h0d, read by rule 7.
  solo (queue89, rows in the same directory): controls s0a s0b; TF_GLM_OVN_SOLO_TO_START=1 (s1a s1b), read by rule 6 on a conversation whose turns add about 3,000 rows (DIR/<boot>/chain.jsonl, tag c3k).
kca (TF_GLM_OVN_KDA_CHUNKED=1) and kva (TF_GLM_OVN_KVB8=1) change numerics: they are reported against the pieces block's controls and join nothing.
The rule was written before any row existed (OVERNIGHT section 59):
  1. replies: every cold request, conversation turn and decode cell has the block's digests, across the controls and the setting's boots;
  2. neither boot of a setting is over the slower control by more than 1.0% at any cold size or on the first turn (a boot's cold time varies about 1.5% between boots),
     and greedy decode at one client (the mean of the prose and code runs) is not more than 1.0% under the controls' mean;
  3. a FRONT_ROWS value: the mean of turns 2 to 8 is at least 1.0% under the controls' mean and the mean of the three cold sizes is not over the controls' mean by more than 0.3%;
     a piece count: the mean of the three cold sizes is at least 0.5% under the controls' mean and turns 2 to 8 are not over their mean by more than 0.3%;
  4. of the values of a block that pass, the one with the larger sum of its cold gain and its warm gain joins.
  5. warm3 was written after queue84's pieces block was read and before its own rows exist; the lead was k3a k3b, turns 2 to 8 at -1.93% and -1.83% of the controls' time with the cold prompt level.
     It reads as a FRONT_ROWS value does (rule 3: turns 2 to 8 at least 1.0% under the controls' mean, the cold mean not over by more than 0.3%), and in addition every 3-piece
     boot's turns 2 to 8 mean is under every control's (one chance in 70 with no difference, four boots against four). The ~250k conversation (tag c250) is printed, never part of the rule.
  6. solo was written before queue89's rows exist. The switch takes one prompt pass off a request whose last stretch before the reply's start is over one grid step: the 8k and 32k cold prompts
     (not the 120k one) and a warm turn that adds 2,307 to 4,096 rows, which the c74 conversation's ~1,290 rows a turn never do. Expected from queue85's nsys capture (whose 8k request read
     0.75% over an un-profiled boot's a row): the two short passes took 1,903.5 ms where one pass of their 4,084 rows takes about 1,694, so about -210 ms, -5.5% of the 8k cold first token and
     -1.5% of the 32k one, level at 120k, and a pass less on every c3k turn. The rule reads the case the switch is for, the c3k conversation (--add 2500, about 3,000 uncached rows a turn):
     its turns 2 on at least 1.0% under the controls' mean, with the cold mean and the c74 turns 2 to 8 each not over the controls' by more than 0.3%. It is undecided unless every c3k turn
     2 on of every boot has uncached rows that the switch changes ((rows - 3) mod 4,096 of 2,304 or more). The cold gain at each size is printed.
  7. held was written before queue90's rows exist. The switch removes most of a warm turn's restore copy (queue85's capture: 850 MiB in 10.8 ms of an 822 to 838 ms first token at ~113k, the state 7.5 MiB a
     1,000 rows), so about 1.2% of a turn at ~113k and about 2% at ~250k, and nothing on a cold prompt. Boot-to-boot spread of a warm turn is 1.8% (queue88's controls), so the mean of four boots against four has
     a noise of about 0.5% and the rule reads rule 3's first form with 0.8% in place of 1.0%: the c74 turns 2 to 8 at least 0.8% faster than the controls' mean, the cold mean not over by more than 0.3%, equal
     replies, no boot over the slower control by 1.0% at a cold size or on the first turn, decode at one client not more than 1.0% under. The ~250k conversation (tag c250) is printed, never part of the rule.
With --apply, each ENVFILE's NEWX line gains TF_GLM_OVN_FRONT_ROWS=N, has TF_GLM_OVERLAP_PIECES=4 replaced by the count (the pieces block, then warm3) or gains TF_GLM_OVN_PIECE_KDA=1
or TF_GLM_OVN_SOLO_TO_START=1 or TF_GLM_OVN_RESTORE_HELD=1, and its IMG line becomes glm53-zig:v129zd (v129ze when kda joins: the image with patch 0039; v129zf when solo joins: that image plus the solo-cuts
package's second patch; v129zg when held joins: that image plus patches/restore-held, which holds the others' code too).
"""
import json
import os
import re
import statistics as st
import sys

BLOCKS = {
    "front": {"controls": ("r4a", "r4b"), "settings": {"512": ("r5a", "r5b"), "768": ("r7a", "r7b"), "2048": ("r2a", "r2b")}},
    "pieces": {"controls": ("k4a", "k4b"), "settings": {"2": ("k2a", "k2b"), "3": ("k3a", "k3b"), "6": ("k6a", "k6b"), "8": ("k8a", "k8b")}},
    "kda": {"controls": ("n9a", "n9b"), "settings": {"1": ("d9a", "d9b")}},
    "warm3": {"controls": ("w4a", "w4b", "w4c", "w4d"), "settings": {"3": ("w3a", "w3b", "w3c", "w3d")}},
    "solo": {"controls": ("s0a", "s0b"), "settings": {"1": ("s1a", "s1b")}},
    "held": {"controls": ("h0a", "h0b", "h0c", "h0d"), "settings": {"1": ("h1a", "h1b", "h1c", "h1d")}},
}
RULES = {"front": "warm", "pieces": "cold", "kda": "cold", "warm3": "strict", "solo": "long", "held": "warm"}  # warm: rule 3's first form; cold: its second; strict: warm plus rule 5's ordering; long: rule 6
GRID, SOLO_ROWS, MIN_CHUNK, HEADER = 2048, 4096, 256, 3  # a prompt chunk, a solo step, the server's least chunk before a message start, the reply header's rows
NUMERICS = {"kca": "TF_GLM_OVN_KDA_CHUNKED=1", "kva": "TF_GLM_OVN_KVB8=1"}
SIZES = (8000, 32000, 120000)
KINDS = ("P", "C")
TOL = 0.01
MIN_WARM, MIN_COLD, SLACK = 0.01, 0.005, 0.003
MIN_WARM_OF = {"held": 0.008}  # a block's own warm minimum where rule 3's 1.0% does not apply
IMAGE = "glm53-zig:v129zd"
IMAGE_KDA = "glm53-zig:v129ze"  # the image that carries patch 0039
IMAGE_SOLO = "glm53-zig:v129zf"  # that image plus patches/solo-cuts/0002
IMAGE_HELD = "glm53-zig:v129zg"  # that image plus patches/restore-held

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


def chain_at(boot, tag):
    return [r for r in jl(f"{D}/{boot}/chain.jsonl") if r.get("tag") == tag]


def chain(boot):
    return chain_at(boot, "c74")


def late_note(ctl, boots):
    """Report only: turns 2 and on of the ~250k conversation, the setting's boots against the controls', when every boot has them."""
    rows = [chain_at(b, "c250") for b in list(boots) + list(ctl)]
    if not all(len(r) > 1 for r in rows):
        return "no ~250k conversation rows"
    mean = lambda bs: st.mean(st.mean(x["ttft_ms"] for x in chain_at(b, "c250")[1:]) for b in bs)
    return f"~250k conversation, turns 2+ {1 - mean(boots) / mean(ctl):+.2%} (report only)"


def warm(boot):
    return st.mean(x["ttft_ms"] for x in chain(boot)[1:])


def long_turns(boot):
    return chain_at(boot, "c3k")[1:]


def long_mean(boot):
    return st.mean(x["ttft_ms"] for x in long_turns(boot))


def exercised(boot):
    """Whether every c3k turn 2 on adds rows the switch changes: past the solo steps, a stretch to the reply's start that holds a grid step and a start listed after it."""
    rows = long_turns(boot)
    return bool(rows) and all((x["prompt_tokens"] - x["cached_tokens"] - HEADER) % SOLO_ROWS >= GRID + MIN_CHUNK for x in rows)


def dec(boot, kind):
    return jl(f"{D}/dec-{boot}/{kind}1.jsonl")


def have(boot):
    return all(cold(boot, s) is not None for s in SIZES) and len(chain(boot)) > 1 and all(dec(boot, k) for k in KINDS)


def speed(boot):
    return st.mean(st.mean(x["agg_tok_s"] for x in dec(boot, k)) for k in KINDS)


def digests(boot):
    d = {("cold", r["target_tokens"], r["rep"]): r["token_sha"] for r in ROWS if r["tag"] == boot}
    d.update({("turn", k): x["token_sha"] for k, x in enumerate(chain(boot))})
    d.update({("turn250", k): x["token_sha"] for k, x in enumerate(chain_at(boot, "c250"))})
    d.update({("turn3k", k): x["token_sha"] for k, x in enumerate(chain_at(boot, "c3k"))})
    d.update({("dec", k): tuple(sorted({tuple(x["sha"]) for x in dec(boot, k)})) for k in KINDS})
    return d


def read(ctl, boots, kind):
    """(passes, cold gain, warm gain, notes) of a setting's boots against the block's controls, or None when a boot is missing."""
    if len(boots) < 2 or not all(have(b) for b in boots):
        return None
    rule = RULES[kind]
    if rule == "long" and not all(exercised(b) for b in list(boots) + list(ctl)):
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
    min_warm = MIN_WARM_OF.get(kind, MIN_WARM)
    shape = warm_gain >= min_warm and cold_gain >= -SLACK if rule in ("warm", "strict") else cold_gain >= MIN_COLD and warm_gain >= -SLACK
    long_gain = 1 - st.mean(long_mean(b) for b in boots) / st.mean(long_mean(c) for c in ctl) if rule == "long" else 0.0
    if rule == "long":
        shape = long_gain >= MIN_WARM and cold_gain >= -SLACK and warm_gain >= -SLACK
    ordered = rule != "strict" or max(warm(b) for b in boots) < min(warm(c) for c in ctl)
    notes = f"cold mean {cold_gain:+.2%}, turns 2+ {warm_gain:+.2%}, decode at 1 client {decode:+.2%}, replies equal {same}, no boot over the slower control by more than 1.0% {not_over}"
    if rule == "strict":
        notes += f", every boot's turns 2+ under every control's {ordered}"
    if rule == "long":
        by_size = " / ".join(f"{1 - st.mean(cold(b, s) for b in boots) / st.mean(ctl_cold[s]):+.2%}" for s in SIZES)
        rows = st.mean(x["prompt_tokens"] - x["cached_tokens"] for b in boots for x in long_turns(b))
        notes += f", ~3k-row turns {long_gain:+.2%} ({rows:.0f} uncached rows a turn), cold by size {by_size}"
    return same and not_over and decode_ok and shape and ordered, cold_gain, warm_gain, notes


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
            print(f"{block} {value}: NOT DECIDED (boots missing{', or a c3k turn the switch does not change' if RULES[block] == 'long' else ''})")
            continue
        ok, cold_gain, warm_gain, notes = r
        print(f"{block} {value} ({' '.join(boots)}): {'passes' if ok else 'no'} | {notes}")
        if block in ("warm3", "held"):
            print(f"  {late_note(ctl, boots)}")
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
    if "warm3" in winners:
        newx = re.sub(r"TF_GLM_OVERLAP_PIECES=\d+", f"TF_GLM_OVERLAP_PIECES={winners['warm3']}", newx)
    if "kda" in winners and "TF_GLM_OVN_PIECE_KDA=1" not in newx:
        newx = f"{newx} -e TF_GLM_OVN_PIECE_KDA=1"
    if "solo" in winners and "TF_GLM_OVN_SOLO_TO_START=1" not in newx:
        newx = f"{newx} -e TF_GLM_OVN_SOLO_TO_START=1"
    if "held" in winners and "TF_GLM_OVN_RESTORE_HELD=1" not in newx:
        newx = f"{newx} -e TF_GLM_OVN_RESTORE_HELD=1"
    image = IMAGE_HELD if "held" in winners else IMAGE_SOLO if "solo" in winners else IMAGE_KDA if "kda" in winners else IMAGE
    new = text[:m.start(1)] + newx + text[m.end(1):]
    new = re.sub(r"^IMG=.*$", f"IMG={image}", new, flags=re.M)
    if new != text:
        open(path, "w", encoding="utf-8", newline="\n").write(new)
        print(f"{path}: NEWX is now '{newx}', IMG={image}")
