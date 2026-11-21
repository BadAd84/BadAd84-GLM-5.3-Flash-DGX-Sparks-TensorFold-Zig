"""e2e_score98.py OUTDIR --tools DIR [--capacity N] [--prefix N] [--rounds N] - upstream's real bench_cache_agents.py against a fake server, then score98.py on its output.

DIR is upstream's tools/ directory at the commit whose client the queue uses (queue98 uses main 46c6ee229), for example
  git -C <upstream clone> archive --format=tar 46c6ee229 tools | tar -x -C work/tools98     (then --tools work/tools98/tools)
The client's own tests/agent_http_fixture.py supplies the in-memory HTTP transport. The fake keeps one whole-prompt state per request in an LRU of a token budget
(a state a later prompt extends in full is replaced in place, any other prompt adds a state) and takes its victims by one of two policies: main is least recently
used first; decayed ages a state by 8 ticks for each of its first two resumes, which is the bounded recency credit of TF_CACHE_EVICT=decayed_resume. Replies carry a
token hash of the request alone, so the two arms' replies are equal by construction; only the cached counts and the time to the first token differ (the fake sleeps
20 microseconds per rebuilt row). The point is the PIPELINE: the real client writes both reports and runs its own compare, and score98.py reads that output. The
fake's cached counts are exact prefix lengths, not 2,048-row chunk boundaries, and its R is a property of its toy parameters, not evidence about the engine.

Exit 0 only when both client runs and the client's compare exit 0, score98.py exits 0 and its verdict is HOLDS (the default capacity oversubscribes the main policy).
"""
import argparse
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

SECONDS_PER_ROW = 2e-5
CREDIT_TICKS, CREDIT_RESUMES = 8, 2


class State:
    def __init__(self, text, tick):
        self.text, self.used, self.resumes = text, tick, 0


def load_client(tools):
    sys.path.insert(0, str(tools))
    sys.path.insert(0, str(tools / "tests"))
    import bench_cache_agents as bench
    from agent_http_fixture import Fixture, MemoryHTTP
    return bench, Fixture, MemoryHTTP


def make_fixture(Fixture):
    class CacheFixture(Fixture):
        def __init__(self, policy, capacity):
            super().__init__()
            self.policy, self.capacity, self.states, self.tick = policy, capacity, [], 0

        def age(self, s):
            credit = CREDIT_TICKS * min(s.resumes, CREDIT_RESUMES) if self.policy == "decayed" else 0
            return max(0, (self.tick - s.used) - credit)

        def serve(self, text):
            self.tick += 1
            best, lcp = None, 0
            for s in self.states:
                n = 0
                for a, b in zip(s.text, text):
                    if a != b:
                        break
                    n += 1
                if n > lcp:
                    best, lcp = s, n
            if best is not None and lcp == len(best.text):
                best.text, best.used = text, self.tick
                best.resumes += 1
                current = best
            else:
                current = State(text, self.tick)
                self.states.append(current)
            while sum(len(s.text) for s in self.states) > self.capacity and len(self.states) > 1:
                self.states.remove(max((s for s in self.states if s is not current), key=lambda s: (self.age(s), -s.used)))
            return lcp

        def response(self, path, body, authorization):
            if path != "/v1/chat/completions":
                return super().response(path, body, authorization)
            self.seen.append((path, body, authorization))
            self.chat.append(body)
            text = "".join(m["role"] + ":" + m["content"] + "\n" for m in body["messages"])
            prompt = len(text)
            cached = self.serve(text)
            time.sleep((prompt - cached) * SECONDS_PER_ROW)
            usage = {"prompt_tokens": prompt, "completion_tokens": 2, "prompt_tokens_details": {"cached_tokens": cached}}
            token_sha = hashlib.sha256(json.dumps({k: v for k, v in body.items() if k != "model"}, sort_keys=True).encode()).hexdigest()
            chunks = [{"choices": [{"index": 0, "delta": {"content": "MODEL-PRIVATE-REPLY"}, "finish_reason": "stop"}]},
                      {"choices": [], "tensorfold": {"token_sha": token_sha[:12], "token_sha256": token_sha}, "usage": usage}]
            wire = b"".join(b"data: " + json.dumps(c).encode() + b"\n\n" for c in chunks) + b"data: [DONE]\n\n"
            return 200, wire
    return CacheFixture


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outdir")
    ap.add_argument("--tools", required=True, help="upstream's tools/ directory (the client and its tests/agent_http_fixture.py)")
    ap.add_argument("--capacity", type=int, default=48000, help="the fake cache's budget in tokens")
    ap.add_argument("--prefix", type=int, default=2048)
    ap.add_argument("--rounds", type=int, default=24)
    args = ap.parse_args()
    out, tools = Path(args.outdir), Path(args.tools).resolve()
    bench, Fixture, MemoryHTTP = load_client(tools)
    CacheFixture = make_fixture(Fixture)
    failed = False
    for label, policy in (("ce-A", "main"), ("ce-B", "decayed")):
        (out / label).mkdir(parents=True, exist_ok=True)
        fixture = CacheFixture(policy, args.capacity)
        argv = ["run", "http://127.0.0.1:1", fixture.model, "--trace", "agent_loops", "--conversations", "6", "--rounds", str(args.rounds),
                "--prefix-tokens", str(args.prefix), "--tokens", "16", "--seed", "11", "--output", str(out / label / "trace.json")]
        with patch.object(bench.urllib.request, "urlopen", side_effect=MemoryHTTP(fixture)), contextlib.redirect_stdout(io.StringIO()):
            code = bench.main(argv)
        print(label, policy, "client rc", code)
        failed |= code != 0
    with contextlib.redirect_stdout(io.StringIO()):
        code = bench.main(["compare", str(out / "ce-A" / "trace.json"), str(out / "ce-B" / "trace.json"), "--output", str(out / "compare.json")])
    print("client compare rc", code)
    failed |= code != 0
    scorer = Path(__file__).resolve().parents[1] / "queue-scores" / "score98.py"
    done = subprocess.run([sys.executable, str(scorer), "--dir", str(out)], capture_output=True, text=True)
    print(done.stdout, end="")
    print("score98 exit", done.returncode)
    verdict = [ln for ln in done.stdout.splitlines() if ln.startswith("VERDICT:")]
    holds = bool(verdict) and verdict[-1].startswith("VERDICT: HOLDS")
    print("verdict line:", verdict[-1] if verdict else "none", "->", "as expected" if holds else "NOT HOLDS")
    return 1 if failed or done.returncode != 0 or not holds else 0


if __name__ == "__main__":
    sys.exit(main())
