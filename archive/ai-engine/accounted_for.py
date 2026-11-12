#!/usr/bin/env python3
"""accounted_for.py SOURCES.txt REFS.txt LEFT-OUT.txt [--live URL] - the reverse direction.

verify_bundle.py proves the bundle gives back everything it lists. This proves the other way round: that
every ref which existed in a source when the archive was taken is either in the bundle under the same sha,
or in the left-out list with the upstream ref that holds that sha. Nothing may be unaccounted for.

SOURCES.txt is tab separated: sha, where the ref lived, its name there, the name it has in this archive.
With --live URL the Gitea repository is read again with git ls-remote and compared against the snapshot,
which only works while the repository still exists.
"""
import subprocess
import sys


def rows(path):
    out = []
    for line in open(path, encoding="utf-8").read().splitlines():
        if line.strip() and not line.startswith("#"):
            out.append(line)
    return out


src_file, refs_file, left_file = sys.argv[1], sys.argv[2], sys.argv[3]
live_url = sys.argv[sys.argv.index("--live") + 1] if "--live" in sys.argv else None

refs = {}
for line in rows(refs_file):
    sha, ref = line.split()[0], line.split()[1]
    refs[ref] = sha
by_sha = {}
for ref, sha in refs.items():
    by_sha.setdefault(sha, []).append(ref)

left = {}
for line in rows(left_file):
    f = line.split()
    left[f[1]] = f[0]
left_by_sha = {}
for ref, sha in left.items():
    left_by_sha.setdefault(sha, []).append(ref)

sources = [line.split("\t") for line in rows(src_file)]
bad, by_reason = [], {"same name in the bundle": 0, "another name in the bundle": 0,
                      "left out, upstream holds it": 0, "left out under another name": 0}
for sha, origin, srcref, archref in sources:
    if refs.get(archref) == sha:
        by_reason["same name in the bundle"] += 1
    elif sha in by_sha:
        by_reason["another name in the bundle"] += 1
    elif left.get(archref) == sha:
        by_reason["left out, upstream holds it"] += 1
    elif sha in left_by_sha:
        by_reason["left out under another name"] += 1
    else:
        bad.append((sha, origin, srcref, archref))

print(f"accounted_for: {len(sources)} source refs checked against {len(refs)} bundled "
      f"and {len(left)} left out")
for k, v in by_reason.items():
    print(f"  {v:6d}  {k}")
print(f"  {len(bad):6d}  unaccounted for")
for b in bad[:20]:
    print("   UNACCOUNTED", " ".join(b))

drift = 0
if live_url:
    p = subprocess.run(["git", "ls-remote", live_url], capture_output=True, text=True)
    if p.returncode:
        print("live read failed:", p.stderr.strip()[:300])
        drift = 1
    else:
        now = {}
        for line in p.stdout.splitlines():
            sha, ref = line.split("\t")
            if not ref.endswith("^{}"):
                now[ref] = sha
        snap = {}
        for sha, origin, srcref, archref in sources:
            if origin.startswith("gitea"):
                snap[srcref] = sha
        for ref in sorted(set(now) | set(snap)):
            if now.get(ref) != snap.get(ref):
                drift += 1
                print(f"   LIVE DRIFT {ref}: snapshot {snap.get(ref)} now {now.get(ref)}")
        print(f"  live check: {len(now)} refs on the remote now, {drift} differences from the snapshot")

sys.exit(1 if bad or drift else 0)
