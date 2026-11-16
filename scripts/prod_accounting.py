"""prod_accounting.py N... - the live production serve's round accounting at N client streams, from its /health counters.

For each N: one run with --rounds 1 and one with --rounds 3 of streams_ids.py (production's 33-token prompt ids) against 127.0.0.1:8888,
each between two /health snapshots, and the difference of the two: exactly two measured waves with the warm-up wave cancelled. Prints tokens a
round, acceptance (accepted over drafted) and the counters. rounds_total counts a round of one sequence, as the Zig engine's draft_rounds does.
decode_seconds_total is stream-time while a stream decodes, so it equals wall time only at one stream: read ms a round at N=1 only.
Every run waits for production to be idle (no request running) first, for at most 10 minutes, and stops rather than loading a busy serve.
Run on the head, beside streams_ids.py and prose33.json: python3 prod_accounting.py 1 2 4
"""
import json, os, subprocess, sys, time, urllib.request
G = os.path.expanduser("~/work/glm53-zig")
KEYS = ["completion_tokens_total", "rounds_total", "drafted_total", "accepted_total", "decode_seconds_total", "prefill_seconds_total", "prompt_tokens_total", "cached_tokens_total"]


def health():
    return json.load(urllib.request.urlopen("http://127.0.0.1:8888/health", timeout=10))


def wait_idle(limit=600):
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            d = health()
            if d.get("requests_running", 1) == 0 and not d.get("busy", True):
                return True
        except Exception:
            pass
        time.sleep(10)
    return False


def run(n, rounds):
    if not wait_idle():
        raise SystemExit(f"production stayed busy before N={n} rounds={rounds}")
    time.sleep(2)
    a = health()
    t0 = time.time()
    subprocess.run([sys.executable, f"{G}/streams_ids.py", "8888", str(n), "--ids", f"{G}/prose33.json", "--max-tokens", "400", "--rounds", str(rounds),
                    "--tag", f"acct-{n}-{rounds}", "--out", f"/tmp/acct-{n}-{rounds}.jsonl"], capture_output=True, text=True)
    time.sleep(2)
    b = health()
    return {k: (b.get(k) or 0) - (a.get(k) or 0) for k in KEYS}, time.time() - t0


print("keys", KEYS)
for n in [int(x) for x in sys.argv[1:]]:
    d1, w1 = run(n, 1)
    d3, w3 = run(n, 3)
    d = {k: d3[k] - d1[k] for k in KEYS}
    toks, rounds = d["completion_tokens_total"], d["rounds_total"]
    print(f"N={n}: two measured waves: tokens {toks}, rounds {rounds}, drafted {d['drafted_total']}, accepted {d['accepted_total']}, decode_s {d['decode_seconds_total']:.2f}")
    if rounds:
        print(f"   tokens/round {toks / rounds:.3f}, acceptance {d['accepted_total'] / max(d['drafted_total'], 1):.3f}, decode ms/round {1000 * d['decode_seconds_total'] / rounds:.1f}, decode tok/s (tokens/decode_s) {toks / max(d['decode_seconds_total'], 1e-9):.1f}")
    print(f"   raw 1 round: {d1}")
    print(f"   raw 3 rounds: {d3}")
    for f in (f"/tmp/acct-{n}-1.jsonl", f"/tmp/acct-{n}-3.jsonl"):
        try:
            os.remove(f)
        except OSError:
            pass
