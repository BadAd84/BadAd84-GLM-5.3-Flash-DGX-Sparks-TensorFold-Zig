#!/usr/bin/env python3
"""Tests for streams.py's draft accounting: the /metrics parse, the per-round deltas and ratios, and one
end-to-end run of the real harness against a fake serve that scripts the counters."""
import json, os, subprocess, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import streams


PROM = """# HELP mtp_drafted_total Draft tokens verified on finished requests.
# TYPE mtp_drafted_total counter
mtp_drafted_total 1200
mtp_accepted_total 700
# a labelled series of another counter does not confuse the parse
something_else_total{rank="0"} 5
decode_rounds_total 400
"""


PROM_PREFIXED = """# TYPE tensorfold:mtp_drafted_total counter
tensorfold:mtp_drafted_total 111
tensorfold:mtp_accepted_total 66
tensorfold:decode_rounds_total 33
"""


class ParseMetrics(unittest.TestCase):
    def test_the_servers_prefixed_families(self):
        m = streams.parse_metrics(PROM_PREFIXED)
        self.assertEqual(m["mtp_drafted_total"], 111.0)
        self.assertEqual(m["mtp_accepted_total"], 66.0)
        self.assertEqual(m["decode_rounds_total"], 33.0)

    def test_reads_the_three_counters(self):
        m = streams.parse_metrics(PROM)
        self.assertEqual(m["mtp_drafted_total"], 1200.0)
        self.assertEqual(m["mtp_accepted_total"], 700.0)
        self.assertEqual(m["decode_rounds_total"], 400.0)

    def test_missing_counter_is_none_not_zero(self):
        m = streams.parse_metrics("mtp_accepted_total 3\n")
        self.assertIsNone(m["mtp_drafted_total"])
        self.assertEqual(m["mtp_accepted_total"], 3.0)
        self.assertIsNone(m["decode_rounds_total"])

    def test_labelled_counter_line(self):
        m = streams.parse_metrics('mtp_drafted_total{rank="1"} 9\n')
        self.assertEqual(m["mtp_drafted_total"], 9.0)

    def test_garbage_value_is_ignored(self):
        m = streams.parse_metrics("mtp_drafted_total not-a-number\n")
        self.assertIsNone(m["mtp_drafted_total"])


class Account(unittest.TestCase):
    def base(self, d=0, a=0, r=0):
        return {"mtp_drafted_total": d, "mtp_accepted_total": a, "decode_rounds_total": r}

    def test_ratios_from_deltas(self):
        out = streams.account(self.base(1000, 500, 100), self.base(1040, 524, 180), tokens=60, span_s=0.5)
        self.assertEqual((out["rounds"], out["drafted"], out["accepted"]), (80, 40, 24))
        self.assertAlmostEqual(out["acceptance"], 0.6)
        self.assertAlmostEqual(out["tok_per_round"], 0.75)
        self.assertAlmostEqual(out["ms_per_round"], 6.25)

    def test_zero_drafted_gives_no_acceptance(self):
        out = streams.account(self.base(0, 0, 10), self.base(0, 0, 20), tokens=5, span_s=1.0)
        self.assertIsNone(out["acceptance"])
        self.assertEqual(out["tok_per_round"], 0.5)

    def test_zero_rounds_gives_no_per_round_figures(self):
        out = streams.account(self.base(9, 9, 7), self.base(9, 9, 7), tokens=5, span_s=1.0)
        self.assertIsNone(out["tok_per_round"])
        self.assertIsNone(out["ms_per_round"])

    def test_counter_reset_is_none(self):
        out = streams.account(self.base(100, 50, 10), self.base(3, 1, 2), tokens=5, span_s=2.0)
        self.assertIsNone(out["rounds"])

    def test_missing_counters_are_none(self):
        empty = dict.fromkeys(streams.COUNTERS, None)
        out = streams.account(empty, empty, tokens=5, span_s=2.0)
        for k in ("rounds", "drafted", "accepted", "acceptance", "tok_per_round", "ms_per_round"):
            self.assertIsNone(out[k], k)

    def test_no_span_gives_no_ms_per_round(self):
        out = streams.account(self.base(0, 0, 0), self.base(10, 5, 4), tokens=40, span_s=None)
        self.assertIsNone(out["ms_per_round"])
        self.assertAlmostEqual(out["tok_per_round"], 10.0)


class FakeServe(BaseHTTPRequestHandler):
    """A minimal OpenAI-compatible serve: /v1/models, an SSE chat completion of `tokens` deltas, and /metrics
    whose counters advance by `step` on every poll after the first."""
    tokens = 8
    step = {"mtp_drafted_total": 3, "mtp_accepted_total": 2, "decode_rounds_total": 4}
    polls = 0

    def log_message(self, *a):
        pass

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            return self._json({"data": [{"id": "fake-model"}]})
        if self.path == "/metrics":
            n = FakeServe.polls
            FakeServe.polls += 1
            text = "".join(f"{k} {v * n}\n" for k, v in FakeServe.step.items())
            body = text.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for i in range(FakeServe.tokens):
            ev = {"choices": [{"delta": {"content": f"t{i} "}, "finish_reason": None}]}
            self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
        usage = {"choices": [], "usage": {"completion_tokens": FakeServe.tokens}}
        self.wfile.write(f"data: {json.dumps(usage)}\n\n".encode())
        done = {"choices": [{"delta": {}, "finish_reason": "length"}]}
        self.wfile.write(f"data: {json.dumps(done)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


class EndToEnd(unittest.TestCase):
    def test_harness_records_the_rounds_accounting(self):
        srv = HTTPServer(("127.0.0.1", 0), FakeServe)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        FakeServe.polls = 0
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "rows.jsonl")
            run = subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "streams.py"), str(port), "1",
                                  "--rounds", "1", "--max-tokens", "8", "--tag", "t", "--out", out],
                                 capture_output=True, text=True, timeout=120)
            srv.shutdown()
            self.assertEqual(run.returncode, 0, run.stderr)
            rows = [json.loads(l) for l in open(out)]
            row = [r for r in rows if r.get("round") == 0][0]
            self.assertIn("acceptance", row)
            self.assertIn("tok_per_round", row)
            self.assertIn("ms_per_round", row)
            # the warm-up consumes the first before/after pair, so a recorded round's delta is one step
            self.assertEqual(row["drafted"], FakeServe.step["mtp_drafted_total"])
            self.assertEqual(row["accepted"], FakeServe.step["mtp_accepted_total"])
            self.assertEqual(row["draft_rounds"], FakeServe.step["decode_rounds_total"])
            self.assertAlmostEqual(row["acceptance"], round(2 / 3, 3))
            self.assertIsNotNone(row["tok_per_round"])
            self.assertIsNotNone(row["ms_per_round"])


if __name__ == "__main__":
    unittest.main()
