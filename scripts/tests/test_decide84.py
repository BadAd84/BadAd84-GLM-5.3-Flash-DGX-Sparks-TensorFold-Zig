#!/usr/bin/env python3
"""test_decide84.py - scripts/queue-scores/decide84.py: a FRONT_ROWS value joins on a warm gain of 1.0% with the cold mean not worse than 0.3%, a piece count on a cold gain of 0.5% with
the warm mean not worse than 0.3%; a changed reply, a boot over the slower control by more than 1.0%, a decode slower by more than 1.0%, missing boots and fewer than two controls
keep a setting out; the larger sum of cold and warm gains wins a block; the numerics boots join nothing; --apply edits NEWX once and names the image.
Plain asserts: python scripts/tests/test_decide84.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("DECIDE84") or os.path.join(HERE, "..", "queue-scores", "decide84.py")
SIZES = (8000, 32000, 120000)
FRONT_CTL, FRONT = ("r4a", "r4b"), {"512": ("r5a", "r5b"), "768": ("r7a", "r7b"), "2048": ("r2a", "r2b")}
PIECE_CTL, PIECES = ("k4a", "k4b"), {"2": ("k2a", "k2b"), "3": ("k3a", "k3b"), "6": ("k6a", "k6b"), "8": ("k8a", "k8b")}
ALL = list(FRONT_CTL) + [b for v in FRONT.values() for b in v] + list(PIECE_CTL) + [b for v in PIECES.values() for b in v] + ["kca", "kva"]


def write(root, plan=None, drop=(), sha=lambda b, k: "a"):
    """plan: boot -> dict(cold=factor, warm=factor, first=factor, speed=tok/s); a boot not in it is a control."""
    plan = plan or {}
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "rows.jsonl"), "w", encoding="utf-8") as f:
        for b in ALL:
            if b in drop:
                continue
            for s in SIZES:
                for rep in (1, 2):
                    f.write(json.dumps({"case": "cold", "tag": b, "target_tokens": s, "rep": rep, "ttft_ms": 1000.0 * s / 8000 * (lambda c: c.get(s, 1.0) if isinstance(c, dict) else c)(plan.get(b, {}).get("cold", 1.0)), "token_sha": sha(b, ("cold", s, rep))}) + "\n")
    for b in ALL:
        if b in drop:
            continue
        p = plan.get(b, {})
        os.makedirs(os.path.join(root, b), exist_ok=True)
        with open(os.path.join(root, b, "chain.jsonl"), "w", encoding="utf-8") as f:
            for k in range(8):
                f.write(json.dumps({"tag": "c74", "ttft_ms": 50000.0 * p.get("first", 1.0) if k == 0 else 800.0 * p.get("warm", 1.0), "token_sha": sha(b, ("turn", k))}) + "\n")
        d = os.path.join(root, f"dec-{b}")
        os.makedirs(d, exist_ok=True)
        for kind in ("P", "C"):
            with open(os.path.join(d, f"{kind}1.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"agg_tok_s": p.get("speed", 100.0), "sha": [sha(b, ("dec", kind))]}) + "\n")


def run(root, *extra):
    return subprocess.run([sys.executable, SCRIPT, "--rows", root, *extra], capture_output=True, text=True, check=True).stdout


def line(out, prefix):
    for l in out.splitlines():
        if l.startswith(prefix):
            return l
    raise AssertionError(f"no line {prefix!r}: {out}")


def verdict(out, block, value):
    return line(out, f"{block} {value} (").split("): ")[1].split(" |")[0]


def both(boots, **kw):
    return {b: dict(kw) for b in boots}


def front_plan(cold, warm):
    plan = {}
    for v, boots in FRONT.items():
        plan.update(both(boots, cold=cold[v], warm=warm[v]))
    return plan


with tempfile.TemporaryDirectory() as t:  # 512 and 768 read -1.5% warm, 2048 reads -2.5% warm and -1% cold: the larger sum, 2048, joins
    write(t, front_plan({"512": 1.0, "768": 1.0, "2048": 0.99}, {"512": 0.985, "768": 0.985, "2048": 0.975}))
    out = run(t)
    assert [verdict(out, "front", v) for v in FRONT] == ["passes"] * 3, out
    assert "front: 2048 JOINS" in out, out

with tempfile.TemporaryDirectory() as t:  # a warm gain under 1.0% keeps a value out; a cold mean over by 0.5% keeps one out; 0.2% over is allowed
    write(t, front_plan({"512": 1.0, "768": 1.005, "2048": 1.002}, {"512": 0.995, "768": 0.98, "2048": 0.98}))
    out = run(t)
    assert [verdict(out, "front", v) for v in FRONT] == ["no", "no", "passes"], out
    assert "front: 2048 JOINS" in out, out

with tempfile.TemporaryDirectory() as t:  # nothing passes: nothing joins and --apply leaves the file alone
    write(t, front_plan({"512": 1.0, "768": 1.0, "2048": 1.0}, {"512": 1.0, "768": 1.0, "2048": 1.0}))
    env = os.path.join(t, "q.env")
    open(env, "w", encoding="utf-8").write('IMG=glm53-zig:v129zc\nNEWX="-e TF_GLM_OVERLAP_PIECES=4"\n')
    out = run(t, "--apply", env)
    assert "front: nothing joins" in out and "pieces: nothing joins" in out, out
    assert open(env, encoding="utf-8").read() == 'IMG=glm53-zig:v129zc\nNEWX="-e TF_GLM_OVERLAP_PIECES=4"\n'

with tempfile.TemporaryDirectory() as t:  # a changed reply in one boot of a setting keeps it out
    write(t, front_plan({"512": 1.0, "768": 1.0, "2048": 1.0}, {"512": 0.98, "768": 0.98, "2048": 0.98}), sha=lambda b, k: "b" if (b == "r7b" and k == ("turn", 3)) else "a")
    out = run(t)
    assert [verdict(out, "front", v) for v in FRONT] == ["passes", "no", "passes"], out

with tempfile.TemporaryDirectory() as t:  # a boot 1.5% over the slower control at one size keeps a setting out; 0.5% over does not
    plan = front_plan({"512": 1.0, "768": 1.0, "2048": 1.0}, {"512": 0.98, "768": 0.98, "2048": 0.98})
    plan["r5a"]["cold"], plan["r7a"]["cold"] = 1.015, 1.005
    write(t, plan)
    out = run(t)
    assert [verdict(out, "front", v) for v in FRONT] == ["no", "passes", "passes"], out

with tempfile.TemporaryDirectory() as t:  # a first turn 1.5% over both controls keeps a setting out
    plan = front_plan({"512": 1.0, "768": 1.0, "2048": 1.0}, {"512": 0.98, "768": 0.98, "2048": 0.98})
    plan["r2a"]["first"] = 1.015
    write(t, plan)
    assert [verdict(run(t), "front", v) for v in FRONT] == ["passes", "passes", "no"]

with tempfile.TemporaryDirectory() as t:  # decode at one client 2% down keeps a setting out, 0.5% down does not
    plan = front_plan({"512": 1.0, "768": 1.0, "2048": 1.0}, {"512": 0.98, "768": 0.98, "2048": 0.98})
    plan["r5a"]["speed"], plan["r5b"]["speed"] = 98.0, 98.0
    plan["r7a"]["speed"], plan["r7b"]["speed"] = 99.5, 99.5
    write(t, plan)
    assert [verdict(run(t), "front", v) for v in FRONT] == ["no", "passes", "passes"]

with tempfile.TemporaryDirectory() as t:  # a piece count needs 0.5% cold: 3 reads -0.6% and passes, 2 reads -0.3% and does not, 8 reads -1.5% and wins over 6 at -1.0%
    plan = {}
    for v, c in {"2": 0.997, "3": 0.994, "6": 0.99, "8": 0.985}.items():
        plan.update(both(PIECES[v], cold=c))
    write(t, plan)
    out = run(t)
    assert [verdict(out, "pieces", v) for v in PIECES] == ["no", "passes", "passes", "passes"], out
    assert "pieces: 8 JOINS" in out, out

with tempfile.TemporaryDirectory() as t:  # the cold gain is the mean of the three sizes: -0.0%, -1.0% and -1.0% is 0.67% and passes, -0.9% at 8k alone and nothing else does not
    plan = both(PIECES["3"], cold={32000: 0.99, 120000: 0.99})
    plan.update(both(PIECES["6"], cold={8000: 0.991}))
    write(t, plan)
    assert [verdict(run(t), "pieces", v) for v in PIECES][1:3] == ["passes", "no"]

with tempfile.TemporaryDirectory() as t:  # the warm gain is the mean of the two boots: -1.5% and +1.0% is 0.25% and does not pass
    plan = {"r5a": {"warm": 0.985}, "r5b": {"warm": 1.01}}
    plan.update(both(FRONT["768"], warm=0.98))
    write(t, plan)
    assert [verdict(run(t), "front", v) for v in FRONT][:2] == ["no", "passes"]

with tempfile.TemporaryDirectory() as t:  # a piece count whose warm turns are 0.5% slower is out, 0.2% slower is allowed
    plan = {}
    for v, w in {"2": 1.005, "3": 1.002, "6": 1.0, "8": 1.0}.items():
        plan.update(both(PIECES[v], cold=0.98, warm=w))
    write(t, plan)
    assert [verdict(run(t), "pieces", v) for v in PIECES] == ["no", "passes", "passes", "passes"]

with tempfile.TemporaryDirectory() as t:  # missing boots are undecided; one control decides nothing
    write(t, front_plan({"512": 0.98, "768": 0.98, "2048": 0.98}, {"512": 0.98, "768": 0.98, "2048": 0.98}), drop=("r7b",))
    out = run(t)
    assert "front 768: NOT DECIDED (boots missing)" in out and verdict(out, "front", "512") == "passes", out
    t2 = os.path.join(t, "one")
    write(t2, drop=("r4b", "k4b"))
    out = run(t2)
    assert "front: NOT DECIDED (fewer than two controls" in out and "pieces: NOT DECIDED (fewer than two controls" in out, out

with tempfile.TemporaryDirectory() as t:  # the numerics boots are reported with their differing digests and join nothing
    write(t, {"kca": {"cold": 0.9, "warm": 0.9}}, sha=lambda b, k: "b" if (b == "kca" and k[0] == "turn") else "a")
    out = run(t)
    assert "kca (TF_GLM_OVN_KDA_CHUNKED=1): reported, joins nothing" in out and "8 of 16 reply digests differ" in out, out
    assert "kva (TF_GLM_OVN_KVB8=1): reported, joins nothing" in out and "0 of 16 reply digests differ" in out, out

with tempfile.TemporaryDirectory() as t:  # --apply adds FRONT_ROWS once (and replaces it), swaps the piece count, names the image, and is idempotent
    plan = front_plan({"512": 1.0, "768": 1.0, "2048": 1.0}, {"512": 0.98, "768": 0.97, "2048": 0.98})
    for v, c in {"6": 0.99}.items():
        plan.update(both(PIECES[v], cold=c))
    write(t, plan)
    env = os.path.join(t, "queue77.env")
    open(env, "w", encoding="utf-8").write('IMG=glm53-zig:v129zc\nNEWX="-e TF_GLM_OVN_MM_WIDE=1 -e TF_GLM_OVERLAP_PIECES=4 -e TF_GLM_OVN_FRONT_ROWS=256"\nHOURS=6\n')
    run(t, "--apply", env)
    run(t, "--apply", env)
    want = 'IMG=glm53-zig:v129zd\nNEWX="-e TF_GLM_OVN_MM_WIDE=1 -e TF_GLM_OVERLAP_PIECES=6 -e TF_GLM_OVN_FRONT_ROWS=768"\nHOURS=6\n'
    assert open(env, encoding="utf-8").read() == want, open(env, encoding="utf-8").read()
    env2 = os.path.join(t, "queue78.env")
    open(env2, "w", encoding="utf-8").write('IMG=glm53-zig:v129zc\nNEWX="-e TF_GLM_OVERLAP_PIECES=4"\n')
    run(t, "--apply", env2)
    run(t, "--apply", env2)
    assert open(env2, encoding="utf-8").read() == 'IMG=glm53-zig:v129zd\nNEWX="-e TF_GLM_OVERLAP_PIECES=6 -e TF_GLM_OVN_FRONT_ROWS=768"\n', open(env2, encoding="utf-8").read()

print("ok")
