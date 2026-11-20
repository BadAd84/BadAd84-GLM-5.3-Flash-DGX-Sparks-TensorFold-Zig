#!/usr/bin/env python3
"""test_decide79.py - scripts/queue-scores/decide79.py adopts a candidate that wins every cell, and refuses one that is level, one that loses a cell
below the slower control and one whose replies differ; a boot missing leaves only its own candidate undecided; --apply appends once.
Plain asserts: python scripts/tests/test_decide79.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "queue-scores", "decide79.py")
CELLS = [(k, n) for k in ("P", "C") for n in (1, 2, 4, 6, 8)]
BOOTS = ("n1", "x1", "i1", "d1", "u1", "u2", "d2", "i2", "x2", "n2")


def write(root, speed, sha=None, drop=None):
    """speed(boot, cell) -> tok/s; sha(boot, cell) -> digest string; drop: a boot with no rows."""
    for b in BOOTS:
        if b == drop:
            continue
        for k, n in CELLS:
            d = os.path.join(root, f"dec-{b}")
            os.makedirs(d, exist_ok=True)
            digest = (sha or (lambda *_: "a"))(b, (k, n))
            with open(os.path.join(d, f"{k}{n}.jsonl"), "w", encoding="utf-8") as f:
                for _ in range(3):
                    f.write(json.dumps({"agg_tok_s": speed(b, (k, n)), "sha": [digest]}) + "\n")


def run(root, *extra):
    r = subprocess.run([sys.executable, SCRIPT, root, *extra], capture_output=True, text=True, check=True)
    return r.stdout


def verdicts(out):
    got = {}
    for line in out.splitlines():
        if line[:3] in ("x (", "i (", "d (", "u (") or line[:2] in ("x:", "i:", "d:", "u:"):
            got[line[0]] = line.split("|")[0].split("): ")[1].strip() if "): " in line.split("|")[0] else line.split(":")[1].split(",")[0].strip()
    return got


with tempfile.TemporaryDirectory() as t:
    base = 100.0

    def speed(b, c):  # x is 2% faster in every cell, i is level, d is 3% faster but loses one cell below the slower control, u is 1.5% faster in nine cells and level in one
        v = base * (1.0 + 0.004 * (b[1] == "2"))  # the two controls differ by 0.4%
        if b[0] == "x":
            v *= 1.02
        if b[0] == "d":
            v *= 1.03 if c != ("C", 8) else 0.98
        if b[0] == "u":
            v *= 1.015
        return v
    write(t, speed)
    v = verdicts(run(t))
    assert v == {"x": "ADOPT", "i": "no", "d": "no", "u": "ADOPT"}, v

with tempfile.TemporaryDirectory() as t:  # one reply of x2 differs
    write(t, lambda b, c: 100.0 * (1.02 if b[0] == "x" else 1.0), sha=lambda b, c: "b" if (b == "x2" and c == ("P", 4)) else "a")
    assert verdicts(run(t))["x"] == "no"

with tempfile.TemporaryDirectory() as t:  # a boot of x is missing: x is undecided, u (also faster here) is still decided
    write(t, lambda b, c: 100.0 * (1.02 if b[0] in "xu" else 1.0), drop="x2")
    out = run(t)
    assert "x: NOT DECIDED" in out
    assert verdicts(out)["u"] == "ADOPT"

with tempfile.TemporaryDirectory() as t:  # a control boot is missing: nothing is decided
    write(t, lambda b, c: 100.0 * (1.02 if b[0] == "x" else 1.0), drop="n2")
    out = run(t)
    assert out.count("NOT DECIDED") == 4 and "ADOPT" not in out

with tempfile.TemporaryDirectory() as t:  # --apply appends the winners once
    write(t, lambda b, c: 100.0 * (1.02 if b[0] == "x" else 1.0))
    env = os.path.join(t, "queue77.env")
    with open(env, "w", encoding="utf-8") as f:
        f.write('IMG=a\nNEWX="-e TF_GLM_OVN_MM_WIDE=1"\nHOURS=6\n')
    run(t, "--apply", env)
    assert open(env, encoding="utf-8").read() == 'IMG=a\nNEWX="-e TF_GLM_OVN_MM_WIDE=1 -e TF_GLM_OVN_X3_NC=2"\nHOURS=6\n'
    run(t, "--apply", env)  # applying twice adds nothing
    assert open(env, encoding="utf-8").read().count("X3_NC=2") == 1

print("ok")
