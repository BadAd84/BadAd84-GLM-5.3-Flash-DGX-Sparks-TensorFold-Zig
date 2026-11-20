#!/usr/bin/env python3
"""check-spark-sync.py USER@HOST [REMOTE_DIR] - exit 1 unless every runtime script this repo authors is on the box byte for byte.

The serve and bench scripts are AUTHORED here and COPIED to the box; a stale copy silently changes what a window measures (a serve.sh
without the recipe's switches ran a whole day of cells on another decode path). Run it before every window and keep its output with the
results. Line endings are normalised. Repair a STALE file by copying the repo file to REMOTE_DIR/stage/ and moving it into place (a running
bash holds the old file). Run it from the top-level Windows shell (the ssh agent lives there; WSL bash has none): SPARK_GATES_SSH_SOCK
names the agent socket of a Windows workstation, as for spark-gates.py.
"""
import hashlib
import os
import subprocess
import sys

RUNTIME = """serve.sh zig-tp3.sh zig-tp3-stop.sh build-image.sh dist-image.sh bench-client.sh bench-arm.sh arms-client.sh arms-file.sh abba.sh
streams.py streams_ids.py prose33.json cells.py rounds.py nsys-rank0.sh nsys-rank.sh nsys-kern.py disk.py disk_table.py longctx.py queue-disk-tier.sh
queue-longctx.sh queue-prod-compare.sh prod_accounting.py prod_table.py per_prompt.py prompts24.json code_ids.json forced-arm.sh teacher_forced.py prod-stop.sh
streams_sampled.py longdec_ids.json nsys-prefill.sh prefill_stages.py prompt_trace.py gpu-check-tp3.sh""".split()


def digest(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()[:16]


def compare(local: dict, remote: dict):
    """Returns (lines, ok): one line a file the repo authors; a file the box lacks or holds differently is STALE."""
    lines, ok = [], True
    for name in RUNTIME:
        if name not in local:
            continue
        got = remote.get(name)
        if got is None:
            lines.append(f"STALE  {name}: not on the box")
            ok = False
        elif got != local[name]:
            lines.append(f"STALE  {name}: box {got}, repo {local[name]}")
            ok = False
        else:
            lines.append(f"same   {name} {got}")
    return lines, ok


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    host = argv[0]
    remote_dir = argv[1] if len(argv) > 1 else "work/glm53-zig"
    here = os.path.dirname(os.path.abspath(__file__))
    local = {}
    for name in RUNTIME:
        path = os.path.join(here, name)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                local[name] = digest(f.read())
    script = f"cd {remote_dir} 2>/dev/null && for f in {' '.join(RUNTIME)}; do [ -f $f ] && printf '%s %s\\n' \"$(tr -d '\\r' < $f | sha256sum | cut -c1-16)\" $f; done"
    env = dict(os.environ)
    if os.name == "nt" and os.environ.get("SPARK_GATES_SSH_SOCK"):
        env["SSH_AUTH_SOCK"] = os.environ["SPARK_GATES_SSH_SOCK"]
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", host, script], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, env=env)
    if r.returncode != 0 and not r.stdout:
        print(f"check-spark-sync: ssh to {host} failed: {r.stderr.strip()[:200]}")
        return 2
    remote = {}
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            remote[parts[1]] = parts[0]
    lines, ok = compare(local, remote)
    print("\n".join(lines))
    print("check-spark-sync: OK" if ok else "check-spark-sync: FAIL (copy the STALE files, then rerun)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
