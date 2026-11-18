#!/usr/bin/env python3
"""streams_sampled.py - streams.py's or streams_ids.py's measurement with every request sampled and seeded.

Usage: streams_sampled.py PORT N [--temperature 1.0] [--top-p 0.95] [--top-k 20] [--seed 7] [the instrument's options]
With --ids FILE it runs streams_ids.py (production's prompt ids on /v1/completions), else streams.py (chat requests). The instrument
builds, sends and parses every request and writes the JSONL row; this file only sets the four sampling fields on each request body
before it is sent (a Request subclass, so urllib's own type checks hold). The greedy bench cannot see TF_GLM_OVN_DRAFT_NOISE, which
acts on sampled streams only. With a fixed seed the engine's keyed sampler draws the same reply in every drafter arm (the draft rule
never changes the target's sample), so this repo's arms compare as the greedy bench does: equal digests, exact draft counters. Another
engine's sampler draws other replies, so a comparison with production is a speed comparison only. The defaults are the sampling of
production's sampled agent-turn records (temperature 1.0, top-p 0.95, top-k 20, seed 7).
"""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import streams  # noqa: E402

ENDPOINTS = ("/v1/chat/completions", "/v1/completions")


def sampling(argv):
    """The sampling fields from argv, streams.opt's way."""
    return {"temperature": float(streams.opt("--temperature", "1.0", argv)),
            "top_p": float(streams.opt("--top-p", "0.95", argv)),
            "top_k": int(streams.opt("--top-k", "20", argv)),
            "seed": int(streams.opt("--seed", "7", argv))}


def sampled_request(base, fields):
    """A urllib Request type that sets `fields` on a completion request's JSON body; every other request unchanged."""
    class Sampled(base):
        def __init__(self, url, data=None, *args, **kw):
            if data is not None and url.endswith(ENDPOINTS):
                body = json.loads(data)
                body.update(fields)
                data = json.dumps(body).encode()
            super().__init__(url, data, *args, **kw)
    return Sampled


def main(argv):
    argv = list(argv)
    fields = sampling(argv)
    urllib.request.Request = sampled_request(urllib.request.Request, fields)
    if "--ids" in argv:
        import streams_ids  # noqa: E402  (imported after the patch so its module-level name binds to the sampled type)
        streams_ids.main(argv)
    else:
        streams.main(argv)


if __name__ == "__main__":
    main(sys.argv)
