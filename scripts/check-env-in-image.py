#!/usr/bin/env python3
"""check-env-in-image.py: every engine setting our env files set exists in the image we serve.

The engine's settings table is compiled into the served binary, so the binary's own strings are the oracle for "does
this option still exist". A setting our env sets that the binary does not carry is either a library variable the engine
never reads (NCCL_*, HF_*) or a row the engine has dropped - and a dropped row is silently ignored, so the serve runs
without it while the env says it is on.

Usage:
  docker run --rm --entrypoint sh IMAGE -c 'strings /opt/tensorfold/native/bin/tensorfold-native' \
    | grep -oE '^(TF|TENSORFOLD)_[A-Z0-9_]+$' | sort -u > image-env.txt
  python scripts/check-env-in-image.py --image-names image-env.txt --env scripts/env/prod.env [--env scripts/env/dev.env]

The engine-prefixed names only are compared: NCCL_* and HF_* are library variables that a container must carry and that
never appear in the table, so they are not findings.
"""
import argparse
import pathlib
import sys

PREFIXES = ("TF_", "TENSORFOLD_")


def env_names(path):
    names = {}
    for raw in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name = line.split("=", 1)[0]
        if name.startswith(PREFIXES):
            names[name] = line
    return names


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--image-names", required=True)
    ap.add_argument("--env", action="append", required=True)
    args = ap.parse_args(argv[1:])
    have = {l.strip() for l in pathlib.Path(args.image_names).read_text(encoding="utf-8").splitlines() if l.strip()}
    problems = []
    total = 0
    for env in args.env:
        names = env_names(env)
        total += len(names)
        for name in sorted(names):
            if name not in have:
                problems.append(f"MISSING {name}: set in {pathlib.Path(env).name}, not in the served binary")
    print(f"env in image: {total} engine settings checked against {len(have)} in the binary, {len(problems)} findings")
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
