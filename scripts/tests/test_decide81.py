#!/usr/bin/env python3
"""test_decide81.py - scripts/queue-scores/decide81.py: an NCCL setting joins on a cold gain with equal replies, a wire setting on a decode gain with the cold prompt not slower,
and at most one of each kind joins; a changed reply, a slower cold prompt, a loss in one decode cell, a missing arm and fewer than two controls all keep a setting out;
--apply appends once. Plain asserts: python scripts/tests/test_decide81.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "queue-scores", "decide81.py")
SIZES = (8000, 32000, 120000)
LEVELS = (1, 2, 4, 6, 8)
C81, C82 = ("c1", "c2", "c3"), ("c4", "c5")
A81 = ("mb", "q4", "n8", "ch", "bf", "qn", "n2", "pp", "p8")
A82 = ("rf", "mf")
FULL = {"c1", "c3", "c4", "c5", "mb", "rf", "mf"}  # the boots with decode at all five levels


def write(root, boots, cold=lambda b, s: 1000.0 * s / 8000, warm=lambda b: 850.0, first=lambda b: 50000.0, speed=lambda b, k, n: 100.0, sha=lambda b, k: "a", drop=()):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "rows.jsonl"), "w", encoding="utf-8") as f:
        for b in boots:
            if b in drop:
                continue
            for s in SIZES:
                for rep in (1, 2):
                    f.write(json.dumps({"case": "cold", "tag": b, "target_tokens": s, "rep": rep, "ttft_ms": cold(b, s), "token_sha": sha(b, ("cold", s, rep))}) + "\n")
    for b in boots:
        if b in drop:
            continue
        os.makedirs(os.path.join(root, b), exist_ok=True)
        with open(os.path.join(root, b, "chain.jsonl"), "w", encoding="utf-8") as f:
            for k in range(8):
                f.write(json.dumps({"tag": "c74", "ttft_ms": first(b) if k == 0 else warm(b), "token_sha": sha(b, ("turn", k)), "prompt_tokens": 100000 + k}) + "\n")
        d = os.path.join(root, f"dec-{b}")
        os.makedirs(d, exist_ok=True)
        for kind in ("P", "C"):
            for n in (LEVELS if b in FULL else (1, 4)):
                with open(os.path.join(d, f"{kind}{n}.jsonl"), "w", encoding="utf-8") as f:
                    for _ in range(3):
                        f.write(json.dumps({"agg_tok_s": speed(b, kind, n), "sha": [sha(b, ("dec", kind, n))]}) + "\n")


def run(r81, r82, *extra):
    r = subprocess.run([sys.executable, SCRIPT, "--rows81", r81, "--rows82", r82, *extra], capture_output=True, text=True, check=True)
    return r.stdout


def passes(out):
    got = {}
    for line in out.splitlines():
        if ": PASSES" in line or line.split(" (")[0] in A81 + A82 and ": no" in line:
            got[line.split(" ")[0]] = "PASSES" if ": PASSES" in line else "no"
    return got


with tempfile.TemporaryDirectory() as t:
    r81, r82 = os.path.join(t, "f81"), os.path.join(t, "f82")

    def cold(b, s):  # n8 is 2% faster, p8 1.5% faster, ch 2% faster at 120k only, q4 2% slower, the others level
        f = {"n8": 0.98, "p8": 0.985, "q4": 1.02}.get(b, 1.0)
        if b == "ch" and s == 120000:
            f = 0.98
        return 1000.0 * s / 8000 * f

    def warm(b):
        return 850.0 * {"n8": 0.98, "p8": 0.985}.get(b, 1.0)

    def speed(b, k, n):  # mb +3% everywhere, mf +2%, rf +0.5%: the best wire arm is not the last one
        return 100.0 * {"mb": 1.03, "rf": 1.005, "mf": 1.02}.get(b, 1.0)

    write(r81, C81 + A81, cold, warm, speed=speed)
    write(r82, C82 + A82, cold, warm, speed=speed)
    out = run(r81, r82)
    got = passes(out)
    assert got["n8"] == "PASSES" and got["p8"] == "PASSES" and got["ch"] == "no" and got["q4"] == "no", got
    assert got["mb"] == "PASSES" and got["mf"] == "PASSES" and got["rf"] == "no", got
    adds = [l for l in out.splitlines() if l.startswith("ADD ")]
    assert adds == ["ADD -e NCCL_MIN_NCHANNELS=8 -e NCCL_MAX_NCHANNELS=8 -e TF_TP_MAILBOX_MAX_KB=1024"], adds  # one of each kind, the strongest: n8 and mb

with tempfile.TemporaryDirectory() as t:  # a changed reply keeps n8 out
    r81, r82 = os.path.join(t, "f81"), os.path.join(t, "f82")
    cold = lambda b, s: 1000.0 * s / 8000 * (0.98 if b == "n8" else 1.0)
    write(r81, C81 + A81, cold, sha=lambda b, k: "b" if (b == "n8" and k == ("turn", 3)) else "a")
    write(r82, C82 + A82, cold)
    assert passes(run(r81, r82)).get("n8") == "no"

with tempfile.TemporaryDirectory() as t:  # a faster cold prompt does not excuse a first turn slower than every control
    r81, r82 = os.path.join(t, "f81"), os.path.join(t, "f82")
    cold = lambda b, s: 1000.0 * s / 8000 * (0.98 if b == "n8" else 1.0)
    first = lambda b: 50000.0 * (1.05 if b == "n8" else 1.0)
    write(r81, C81 + A81, cold, first=first)
    write(r82, C82 + A82, cold, first=first)
    assert passes(run(r81, r82)).get("n8") == "no"

with tempfile.TemporaryDirectory() as t:  # a wire arm that loses one decode cell below the slowest control, and one that makes the cold prompt slower
    r81, r82 = os.path.join(t, "f81"), os.path.join(t, "f82")
    speed = lambda b, k, n: 100.0 * (1.03 if b in ("mb", "mf") else 1.0) * (0.95 if (b == "mb" and (k, n) == ("C", 8)) else 1.0)
    cold = lambda b, s: 1000.0 * s / 8000 * (1.05 if b == "mf" else 1.0)
    write(r81, C81 + A81, cold, speed=speed)
    write(r82, C82 + A82, cold, speed=speed)
    got = passes(run(r81, r82))
    assert got["mb"] == "no" and got["mf"] == "no", got

with tempfile.TemporaryDirectory() as t:  # an arm with no rows is undecided; one control alone decides nothing
    r81, r82 = os.path.join(t, "f81"), os.path.join(t, "f82")
    write(r81, C81 + A81, drop=("mb",))
    write(r82, C82 + A82)
    assert "mb: NOT DECIDED" in run(r81, r82)
    r81b, r82b = os.path.join(t, "g81"), os.path.join(t, "g82")
    write(r81b, ("c1",))
    write(r82b, ())
    assert "NOT DECIDED: fewer than two controls" in run(r81b, r82b)

with tempfile.TemporaryDirectory() as t:  # --apply appends the winners once
    r81, r82 = os.path.join(t, "f81"), os.path.join(t, "f82")
    cold = lambda b, s: 1000.0 * s / 8000 * (0.98 if b == "n8" else 1.0)
    write(r81, C81 + A81, cold)
    write(r82, C82 + A82, cold)
    env = os.path.join(t, "queue79.env")
    with open(env, "w", encoding="utf-8") as f:
        f.write('IMG=a\nNEWX="-e TF_GLM_OVN_MM_WIDE=1"\nHOURS=2\n')
    run(r81, r82, "--apply", env)
    run(r81, r82, "--apply", env)
    assert open(env, encoding="utf-8").read() == 'IMG=a\nNEWX="-e TF_GLM_OVN_MM_WIDE=1 -e NCCL_MIN_NCHANNELS=8 -e NCCL_MAX_NCHANNELS=8"\nHOURS=2\n'

print("ok")
