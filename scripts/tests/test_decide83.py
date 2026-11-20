#!/usr/bin/env python3
"""test_decide83.py - scripts/queue-scores/decide83.py: the nested sets F, B and M join on a cold gain with equal replies, a larger set only for 0.3 points over the adopted one;
a changed reply, a boot over the slower control, a slower first turn, missing boots and fewer than two controls keep a set out; --apply appends once and names the image.
Plain asserts: python scripts/tests/test_decide83.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("DECIDE83") or os.path.join(HERE, "..", "queue-scores", "decide83.py")
SIZES = (8000, 32000, 120000)
CTL = ("ca", "cb")
SETS = ("fa", "fb", "ba", "bb", "ma", "mb")
EXTRA = ("na", "nb", "ga", "gb")


def write(root, boots, factor=lambda b: 1.0, first=lambda b: 50000.0, sha=lambda b, k: "a", drop=(), warm=None):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "rows.jsonl"), "w", encoding="utf-8") as f:
        for b in boots:
            if b in drop:
                continue
            for s in SIZES:
                for rep in (1, 2):
                    f.write(json.dumps({"case": "cold", "tag": b, "target_tokens": s, "rep": rep, "ttft_ms": 1000.0 * s / 8000 * factor(b), "token_sha": sha(b, ("cold", s, rep))}) + "\n")
    for b in boots:
        if b in drop:
            continue
        os.makedirs(os.path.join(root, b), exist_ok=True)
        with open(os.path.join(root, b, "chain.jsonl"), "w", encoding="utf-8") as f:
            for k in range(8):
                f.write(json.dumps({"tag": "c74", "ttft_ms": first(b) if k == 0 else (warm(b) if warm else 850.0 * factor(b)), "token_sha": sha(b, ("turn", k))}) + "\n")
        d = os.path.join(root, f"dec-{b}")
        os.makedirs(d, exist_ok=True)
        for kind in ("P", "C"):
            for n in (1, 4):
                with open(os.path.join(d, f"{kind}{n}.jsonl"), "w", encoding="utf-8") as f:
                    f.write(json.dumps({"agg_tok_s": 100.0, "sha": [sha(b, ("dec", kind, n))]}) + "\n")


def run(root, *extra):
    return subprocess.run([sys.executable, SCRIPT, "--rows", root, *extra], capture_output=True, text=True, check=True).stdout


def verdict(out, name):
    for line in out.splitlines():
        if line.startswith(name + " ("):
            return line.split("): ")[1].split(" |")[0]
    raise AssertionError(f"no line for {name}: {out}")


def adds(out):
    return [l for l in out.splitlines() if l.startswith("ADD ")]


F, B, M = ("-e TF_GLM_OVN_PIECE_FRONT=1",), ("-e TF_GLM_OVN_PIECE_FRONT=1", "-e TF_GLM_OVN_PIECE_FFN=1"), ("-e TF_GLM_OVN_PIECE_FRONT=1", "-e TF_GLM_OVN_PIECE_FFN=1", "-e TF_GLM_OVN_PIECE_MLA=1")

with tempfile.TemporaryDirectory() as t:  # F -3%, B -3.1%, M -3.2%: the extra switches are not worth 0.1 points each, so F joins alone
    write(t, CTL + SETS + EXTRA, lambda b: {"f": 0.97, "b": 0.969, "m": 0.968}.get(b[0], 1.0) if b in SETS else 1.0)
    out = run(t)
    assert verdict(out, "F") == "JOINS" and verdict(out, "B") == "passes, extra switch not worth it" and verdict(out, "M") == "passes, extra switch not worth it", out
    assert adds(out) == ["ADD " + " ".join(F)], adds(out)

with tempfile.TemporaryDirectory() as t:  # F -3%, B -4%, M -4.1%: B joins (one point over F), M does not (0.1 over B)
    write(t, CTL + SETS + EXTRA, lambda b: {"f": 0.97, "b": 0.96, "m": 0.959}.get(b[0], 1.0) if b in SETS else 1.0)
    out = run(t)
    assert verdict(out, "F") == "JOINS" and verdict(out, "B") == "JOINS" and verdict(out, "M") == "passes, extra switch not worth it", out
    assert adds(out) == ["ADD " + " ".join(B)], adds(out)

with tempfile.TemporaryDirectory() as t:  # F, B and M each a point over the one before: M joins
    write(t, CTL + SETS + EXTRA, lambda b: {"f": 0.97, "b": 0.96, "m": 0.95}.get(b[0], 1.0) if b in SETS else 1.0)
    assert adds(run(t)) == ["ADD " + " ".join(M)]

with tempfile.TemporaryDirectory() as t:  # a gain under 1.0% joins nothing
    write(t, CTL + SETS + EXTRA, lambda b: 0.995 if b in SETS else 1.0)
    out = run(t)
    assert verdict(out, "F") == "no" and not adds(out), out

with tempfile.TemporaryDirectory() as t:  # a changed reply in one boot of F keeps F out
    write(t, CTL + SETS + EXTRA, lambda b: 0.97 if b in SETS else 1.0, sha=lambda b, k: "b" if (b == "fb" and k == ("turn", 3)) else "a")
    out = run(t)
    assert verdict(out, "F") == "no", out

with tempfile.TemporaryDirectory() as t:  # one boot of F over the slower control at one size keeps it out, though the mean is 3% under
    write(t, CTL + SETS + EXTRA, lambda b: 0.92 if b == "fa" else (1.04 if b == "fb" else (0.97 if b in SETS else 1.0)), warm=lambda b: 850.0)
    assert verdict(run(t), "F") == "no"

with tempfile.TemporaryDirectory() as t:  # the gain is the mean of the two boots: one at -1.5% and one level with the controls is -0.75%
    write(t, CTL + SETS + EXTRA, lambda b: 0.985 if b == "fa" else (1.0 if b == "fb" else (0.97 if b in SETS else 1.0)), warm=lambda b: 850.0)
    assert verdict(run(t), "F") == "no"

with tempfile.TemporaryDirectory() as t:  # a faster cold prompt does not excuse a first turn slower than both controls
    write(t, CTL + SETS + EXTRA, lambda b: 0.97 if b in SETS else 1.0, first=lambda b: 52000.0 if b == "fa" else 50000.0)
    assert verdict(run(t), "F") == "no"

with tempfile.TemporaryDirectory() as t:  # missing boots are undecided; one control decides nothing
    write(t, CTL + SETS + EXTRA, lambda b: 0.97 if b in SETS else 1.0, drop=("ma",))
    assert "M: NOT DECIDED" in run(t)
    t2 = os.path.join(t, "one")
    write(t2, ("ca",))
    assert "NOT DECIDED: fewer than two controls" in run(t2)

with tempfile.TemporaryDirectory() as t:  # --apply appends the flags once and names the image
    write(t, CTL + SETS + EXTRA, lambda b: {"f": 0.97, "b": 0.96}.get(b[0], 1.0) if b in SETS else 1.0)
    env = os.path.join(t, "queue77.env")
    with open(env, "w", encoding="utf-8") as f:
        f.write('IMG=glm53-zig:v129za\nNEWX="-e TF_GLM_OVN_MM_WIDE=1"\nHOURS=6\n')
    run(t, "--apply", env)
    run(t, "--apply", env)
    want = 'IMG=glm53-zig:v129zc\nNEWX="-e TF_GLM_OVN_MM_WIDE=1 ' + " ".join(B) + '"\nHOURS=6\n'
    assert open(env, encoding="utf-8").read() == want, open(env, encoding="utf-8").read()

print("ok")
