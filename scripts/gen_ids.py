#!/usr/bin/env python3
"""gen_ids.py N SEED: a JSON array of N token ids for tools/bench_cache.py --prompt-file, on stdout.

The ids are drawn from 1,000 to 49,999 by a seeded generator, so a file is the same on every run and two seeds share no prefix. They are not text: a cold prompt's speed does
not depend on what the ids say, and a receipt that uses them says so.
"""
import json
import random
import sys

N, SEED = int(sys.argv[1]), int(sys.argv[2])
rng = random.Random(f"gen_ids-{SEED}")
print(json.dumps([rng.randrange(1000, 50000) for _ in range(N)]))
