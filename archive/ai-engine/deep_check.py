#!/usr/bin/env python3
"""deep_check.py BUNDLE UPSTREAM_CLONE [REF_SUBSTR] - are ALL objects (blobs too) of the bundle's refs present?

Restores the bundle into a throwaway clone sharing UPSTREAM_CLONE's objects, then walks every restored ref
with `rev-list --objects --missing=print` and counts objects that are missing. Two ways this fails, both
seen for real: git refuses a bundle that does not carry every object its refs need, and a walk over a
restored ref finds objects the clone cannot produce. Some of the clones this archive drew from were
blobless partial clones, which is why the walk exists rather than trusting the fetch.
"""
import os
import shutil
import subprocess
import sys
import tempfile

bundle, upstream = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
only = sys.argv[3] if len(sys.argv) > 3 else ""


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


print("upstream clone partial:", git(upstream, "config", "--get-regexp", r"(promisor|partialclone)").stdout.strip() or "no")
tmp = tempfile.mkdtemp(prefix="deep-")
try:
    repo = os.path.join(tmp, "r.git")
    r = git(tmp, "clone", "-q", "--bare", "--shared", upstream, repo)
    if r.returncode:
        print("deep_check: could not clone the upstream repository:", r.stderr.strip()[:300])
        sys.exit(1)
    git(repo, "config", "--unset-all", "remote.origin.promisor")
    r = git(repo, "fetch", "-q", bundle, "refs/*:refs/restored/*")
    if r.returncode:
        print("deep_check: the bundle did not restore:", r.stderr.strip()[:300])
        sys.exit(1)
    refs = [x for x in git(repo, "for-each-ref", "--format=%(refname)", "refs/restored").stdout.split() if only in x]
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
    p = subprocess.run(["git", "rev-list", "--objects", "--missing=print", *refs],
                       cwd=repo, capture_output=True, text=True, env=env)
    lines = p.stdout.splitlines()
    missing = [x for x in lines if x.startswith("?")]
    print(f"deep_check: {len(refs)} refs, {len(lines) - len(missing)} objects walked, "
          f"{len(missing)} missing (rc {p.returncode}) {p.stderr.strip()[:300]}")
    for m in missing[:5]:
        print("  missing", m)
    sys.exit(1 if missing or p.returncode else 0)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
