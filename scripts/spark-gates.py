#!/usr/bin/env python3
"""spark-gates.py: run this repo's gates on another box; nothing is compiled on the workstation.

Run it from the repo root with the Windows python in the top-level shell, never through WSL: it reaches the host with
Git for Windows' ssh and scp, points them at the YubiKey agent itself, and every ssh and scp reads /dev/null. The host
(default: the Paperclip box) needs ~/tools/zig-<arch>-linux-<the pin's .zig-version>, rsync, python3 and flock. Every
run there goes under `nice -n 15` (--nice) and, where a systemd user scope exists, a 14 GiB MemoryMax with no swap
(--mem-max), and does not start when the load is above 8 (--max-load) or less memory than the cap is available.

  gates   --pin REF --tree NAME[=DIR[,DIR...]] ... [--expect NAME=TREEID ...] [--jobs 6] [--clean]
          Ships `git archive REF` of work/parity/tree (cached on the host by commit), the patch directories and
          scripts/{gates,gate-names,lean}.sh, then detaches a runner on the host. It builds every tree (the pin, then
          each DIR's *.patch in file-name order, the DIRs in the order given), checks each tree id against --expect
          (a tree with no DIR against the pin's own tree), runs gates.sh on each, then gate-names.sh and lean.sh of
          base against every other tree. A tree named base with no DIR is the pristine pin; without --tree base one
          is added. The three scripts run with HOME=~/spark-gates/RUN/home, so their copies, caches and logs (and
          whatever the tests write under HOME) stay in the run dir. Prints the run name and returns at once. Log:
          ~/spark-gates/RUN/run.log, ending with SPARK-GATES-DONE. --clean empties the run's trees and home but for
          the gate logs after a passing verdict.
  wait    [--run RUN]  Polls the run (default: the newest) every 60 s until the marker, then prints the log tail and
          the verdict table. Exit 0 only when every non-base tree passes, 1 on any failure, 2 when it could not tell.
  iter    --pin REF --dir DIR[,DIR] [check] [fmt] [test] [lean]  The fast loop: rebuilds one tree on the host and runs
          the named steps there in the foreground (default: check fmt). Exit 0 when every step had rc 0.
  verdict RUN_LOG  The verdict table of a run.log; the runner calls it on the host at the end of every run.
"""
import argparse
import functools
import hashlib
import io
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

# The gate host comes from SPARK_GATES_HOST (user@host of a shared x86_64 or aarch64 box with rsync, python3 and
# ~/tools/zig-<arch>-linux-<version>); it is a shared machine, so the defaults below are gentle: 6 jobs at nice 15, a
# 14 GiB cap, and a refusal to start above load 8. The ssh agent socket of a Windows workstation comes from
# SPARK_GATES_SSH_SOCK (on other systems SSH_AUTH_SOCK is used as it is).
DEFAULT_HOST = os.environ.get("SPARK_GATES_HOST", "")
DEFAULT_JOBS, DEFAULT_NICE, DEFAULT_MEM_GIB, DEFAULT_MAX_LOAD = 6, 15, 14, 8.0
AGENT_SOCK = os.environ.get("SPARK_GATES_SSH_SOCK", "")
SSH_OPTS = ("-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=6")
SCRIPTS = ("gates.sh", "gate-names.sh", "lean.sh")
REMOTE = "spark-gates"  # under the host user's home
GIB_PER_TREE = 6  # spark5, 2026-11-15: a tree's zig cache took 3.8 to 5.3 GB, the tree and its gates.sh copy 0.4 GB
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
RUN_RE = re.compile(r"^sg-\d{8}-\d{6}$")
ID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/+-]*$")
PATCH_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.patch$")
TEST_STEP = "test-cuda-host"
REQUIRED_STEPS = ("check-native-cuda-host", TEST_STEP, "fmt")  # gates.sh runs these on every tree of this engine
ITER_STEPS = ("check", "fmt", "test", "lean")


def die(msg, rc=2):
    print(f"spark-gates: {msg}", file=sys.stderr, flush=True)
    sys.exit(rc)


def refuse_wsl():
    """The agent socket and the ssh that understands it are Windows ones; a WSL python has neither."""
    if "microsoft" in platform.release().lower() or os.environ.get("WSL_DISTRO_NAME"):
        die("run spark-gates.py with the Windows python from the top-level shell, not through WSL")


def ssh_env():
    env = dict(os.environ)
    if os.name == "nt" and AGENT_SOCK:
        env["SSH_AUTH_SOCK"] = AGENT_SOCK
    return env


@functools.lru_cache(maxsize=None)
def tool(name):
    """Git for Windows' ssh or scp: Windows' own OpenSSH cannot reach the agent-gui socket."""
    if os.name == "nt":
        cands = []
        git = shutil.which("git")
        if git:
            cands.append(Path(git).resolve().parent.parent / "usr" / "bin" / f"{name}.exe")
        cands.append(Path(r"C:\Program Files\Git\usr\bin") / f"{name}.exe")
        for c in cands:
            if c.is_file():
                return str(c)
    found = shutil.which(name)
    if not found:
        die(f"no {name} found")
    return found


def ssh(host, command, check=True):
    """Runs one command on the host; returns (rc, stdout and stderr as text)."""
    r = subprocess.run([tool("ssh"), *SSH_OPTS, host, command], env=ssh_env(), stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", "replace")
    if check and r.returncode != 0:
        die(f"ssh {host} '{command}' failed (rc={r.returncode}): {out.strip()[-1500:]}")
    return r.returncode, out


def ssh_stream(host, command):
    """Runs one command on the host with its output going straight to this terminal; returns its rc."""
    sys.stdout.flush()
    return subprocess.run([tool("ssh"), *SSH_OPTS, host, command], env=ssh_env(), stdin=subprocess.DEVNULL).returncode


def scp(host, local_dir, name, remote_path):
    """Copies local_dir/name to host:remote_path; run in local_dir so no drive letter reaches scp."""
    r = subprocess.run([tool("scp"), "-q", *SSH_OPTS, name, f"{host}:{remote_path}"], cwd=local_dir, env=ssh_env(),
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        die(f"scp {name} to {host}:{remote_path} failed (rc={r.returncode}): "
            f"{r.stdout.decode('utf-8', 'replace').strip()[-800:]}")


def git_out(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None


def repo_root():
    here = Path(__file__).resolve().parent
    top = git_out(here, "rev-parse", "--show-toplevel")
    if not top:
        die(f"cannot find the repo from {here}")
    return Path(top.strip())


def resolve_pin(pin_repo, pin):
    """(commit, tree, zig version) of REF in the upstream clone; nothing in it is written."""
    if not REF_RE.match(pin):
        die(f"--pin {pin!r}: give a tag, a branch or a sha")
    if git_out(pin_repo, "rev-parse", "--git-dir") is None:
        die(f"no git clone at {pin_repo}")
    commit = (git_out(pin_repo, "rev-parse", "--verify", "--quiet", f"{pin}^{{commit}}") or "").strip()
    if not ID_RE.match(commit):
        die(f"{pin} is not a commit in {pin_repo}")
    tree = (git_out(pin_repo, "rev-parse", f"{commit}^{{tree}}") or "").strip()
    zig = (git_out(pin_repo, "show", f"{commit}:.zig-version") or "").strip()
    if not re.match(r"^[0-9A-Za-z.+-]+$", zig):
        die(f"{pin} has no usable .zig-version ({zig!r})")
    return commit, tree, zig


def archive_pin(pin_repo, commit, dest):
    """Writes `git archive` of the commit to dest; returns (sha256, size)."""
    h = hashlib.sha256()
    size = 0
    with open(dest, "wb") as f:
        p = subprocess.Popen(["git", "-C", str(pin_repo), "archive", "--format=tar", commit], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE)
        for chunk in iter(lambda: p.stdout.read(1 << 20), b""):
            h.update(chunk)
            f.write(chunk)
            size += len(chunk)
        if p.wait() != 0:
            die(f"git archive {commit} failed")
    return h.hexdigest(), size


def shown(path):
    """A patch directory as the run log names it: relative to here, forward slashes."""
    try:
        s = os.path.relpath(path, os.getcwd())
    except ValueError:
        s = str(path)
    s = s.replace("\\", "/")
    if re.search(r"\s", s):
        die(f"{s}: a patch directory path with whitespace is not supported")
    return s


def split_dirs(values):
    out = []
    for v in values:
        for d in v.split(","):
            if not d.strip():
                die(f"empty directory in {v!r}")
            out.append(d.strip())
    return out


def collect_patches(trees):
    """Each distinct DIR once as dN; each tree's dN ids and its apply order as dN/FILE (DIRs as given, files by name)."""
    dirs, index, lists, ids = [], {}, {}, {}
    for name, given in trees.items():
        order, ids[name] = [], []
        for d in given:
            p = Path(d).resolve()
            key = os.path.normcase(str(p))
            if key not in index:
                if not p.is_dir():
                    die(f"tree {name}: {d} is not a directory")
                files = sorted(f.name for f in p.iterdir() if f.is_file() and f.name.endswith(".patch"))
                if not files:
                    die(f"tree {name}: {d} holds no *.patch file")
                bad = [f for f in files if not PATCH_FILE_RE.match(f)]
                if bad:
                    die(f"tree {name}: patch file names this tool does not ship: {bad}")
                index[key] = len(dirs)
                dirs.append((f"d{len(dirs)}", shown(p), p, files))
            did, _, _, files = dirs[index[key]]
            ids[name].append(did)
            order += [f"{did}/{f}" for f in files]
        lists[name] = order
    return dirs, lists, ids


class Ship:
    """A tar built in memory from given bytes, so nothing depends on the workstation's file modes or line ends."""

    def __init__(self):
        self.buf = io.BytesIO()
        self.tar = tarfile.open(fileobj=self.buf, mode="w", format=tarfile.PAX_FORMAT)
        self.now = int(time.time())

    def add(self, name, data, mode=0o644):
        data = data.encode("utf-8") if isinstance(data, str) else data
        info = tarfile.TarInfo(name)
        info.size, info.mode, info.mtime = len(data), mode, self.now
        self.tar.addfile(info, io.BytesIO(data))

    def add_common(self, root, dirs, lists):
        for s in SCRIPTS:
            self.add(f"scripts/{s}", (root / "scripts" / s).read_bytes(), 0o755)
        for did, _, path, files in dirs:
            for f in files:
                self.add(f"patches/{did}/{f}", (path / f).read_bytes())
        for name, order in lists.items():
            self.add(f"lists/{name}.list", "".join(f"{p}\n" for p in order))

    def write(self, path):
        self.tar.close()
        Path(path).write_bytes(self.buf.getvalue())


def fill(template, **values):
    out = template
    for k, v in values.items():
        out = out.replace(f"@{k}@", str(v))
    left = sorted(set(re.findall(r"@[A-Z0-9_]+@", out)))
    if left:
        die(f"internal: unfilled {left}")
    return out


# Shared by launch.sh and iter.sh: the tools, the toolchain the pin names, the load, memory and disk, the wrapper (nice
# level and memory cap) in $WRAP, and the pin archive itself. Exit 4 is a failed check; exit 3 asks the workstation to
# upload the pin archive and run the script again.
PREFLIGHT = r'''for c in git tar rsync python3 sha256sum flock setsid nice timeout awk nproc; do
  command -v "$c" > /dev/null || { echo "PREFLIGHT: $c is missing on $(hostname)"; exit 4; }
done
Z=$HOME/tools/zig-$(uname -m)-linux-@ZIG@/zig
[ -x "$Z" ] || { echo "PREFLIGHT: no zig at $Z (the pin's .zig-version is @ZIG@)"; exit 4; }
load=$(cut -d' ' -f1 /proc/loadavg)
avail=$(awk '/^MemAvailable:/ {print int($2 / 1048576)}' /proc/meminfo)
gib=$(df -Pk "$HOME" | awk 'NR == 2 {print int($4 / 1048576)}')
echo "PREFLIGHT $(hostname) $(uname -m), $(nproc) cpus: load $load, ${avail:-?} GiB memory available, ${gib:-?} GiB disk free"
if awk -v l="$load" -v m=@MAXLOAD@ 'BEGIN {exit !(l > m)}'; then echo "PREFLIGHT: load $load is above @MAXLOAD@, not starting"; exit 4; fi
[ "${avail:-0}" -ge @MEMMAX@ ] || { echo "PREFLIGHT: ${avail:-0} GiB available is under the @MEMMAX@ GiB cap, not starting"; exit 4; }
[ "${gib:-0}" -ge @NEED@ ] || { echo "PREFLIGHT: ${gib:-0} GiB free under $HOME, this needs about @NEED@ GiB"; exit 4; }
WRAP="nice -n @NICE@"
if [ @MEMMAX@ -gt 0 ]; then
  if systemd-run --user --scope -q -p MemoryMax=@MEMMAX@G -p MemorySwapMax=0 true 2> /dev/null; then
    WRAP="$WRAP systemd-run --user --scope -q -p MemoryMax=@MEMMAX@G -p MemorySwapMax=0 --"
  elif systemd-run --user --scope -q -p MemoryMax=@MEMMAX@G true 2> /dev/null; then
    WRAP="$WRAP systemd-run --user --scope -q -p MemoryMax=@MEMMAX@G --"
  else
    echo "NOTE: no systemd user scope on $(hostname), so no @MEMMAX@ GiB memory cap"
  fi
fi
PIN=$HOME/spark-gates/pins/@COMMIT@.tar
if [ -f "$PIN.part-@STAMP@" ]; then
  if [ "$(sha256sum < "$PIN.part-@STAMP@" | cut -c1-64)" != @SHA@ ]; then
    rm -f "$PIN.part-@STAMP@"; echo "PREFLIGHT: the uploaded pin archive does not hash to @SHA@"; exit 4
  fi
  mv -f "$PIN.part-@STAMP@" "$PIN"
fi
if [ ! -f "$PIN" ] || [ "$(sha256sum < "$PIN" | cut -c1-64)" != @SHA@ ]; then echo NEED-PIN; exit 3; fi
for f in "$HOME"/spark-gates/sg-*/runner.pid; do
  [ -f "$f" ] || continue
  r=$(basename "$(dirname "$f")"); p=$(cat "$f")
  [ "$r" = @STAMP@ ] && continue
  grep -qs runner.sh "/proc/$p/cmdline" && echo "NOTE: run $r is still running (pid $p) and shares the CPU"
done
'''

LAUNCH = r'''#!/bin/bash
# launch.sh: written by spark-gates.py for run @RUN@; checks the host, puts the pin archive in place, starts runner.sh
# detached under the nice level and memory cap the preflight settled.
set -u
RD=$HOME/spark-gates/@RUN@
cd "$RD" || exit 2
trap 'rc=$?; if [ "$rc" = 4 ]; then cd "$HOME" && rm -rf "$RD"; fi' EXIT
sed -i 's/\r$//' runner.sh status.sh scripts/*.sh
@PREFLIGHT@
(setsid nohup $WRAP bash runner.sh > run.log 2>&1 < /dev/null &)
sleep 3
pid=$(cat runner.pid 2>/dev/null)
if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
  echo "STARTED pid=$pid $(date -u +%FT%TZ) on $(hostname)"; tail -2 run.log; exit 0
fi
echo "the runner did not stay up; run.log:"; tail -20 run.log; exit 2
'''

STATUS = r'''#!/bin/bash
# status.sh: written by spark-gates.py for run @RUN@; DONE once run.log holds the marker, else RUNNING or DEAD.
RD=$HOME/spark-gates/@RUN@
if grep -q '^SPARK-GATES-DONE' "$RD/run.log" 2>/dev/null; then echo "DONE $(grep '^SPARK-GATES-DONE' "$RD/run.log" | tail -1)"; exit 0; fi
pid=$(cat "$RD/runner.pid" 2>/dev/null)
last=$(tail -1 "$RD/run.log" 2>/dev/null | cut -c1-200)
if [ -n "$pid" ] && grep -qs runner.sh "/proc/$pid/cmdline"; then
  echo "RUNNING $(date -u +%T) $last"
else
  echo "DEAD $(date -u +%T) $last"
fi
'''

RUNNER = r'''#!/bin/bash
# runner.sh: written by spark-gates.py for run @RUN@. Builds each tree from the pin archive plus its patch list, runs
# scripts/gates.sh on it, then gate-names.sh and lean.sh of base against it; `spark-gates.py verdict` reads run.log.
set -u
RUN=@RUN@
RD=$HOME/spark-gates/$RUN
H=$RD/home
PIN=$HOME/spark-gates/pins/@COMMIT@.tar
JOBS=@JOBS@
CLEAN=@CLEAN@
TREES="@TREES@"
cd "$RD" || exit 2
echo $$ > runner.pid
marked=0
finish() { marked=1; echo "SPARK-GATES-DONE $(date -u +%FT%TZ) $1"; }
trap 'rc=$?; [ "$marked" = 1 ] || { echo "SG runner exited early rc=$rc"; finish "verdict=FAIL (the runner exited early)"; }' EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
cat config.txt
cg=$(cut -d: -f3 /proc/self/cgroup)
echo "SG start $(date -u +%FT%TZ) host=$(hostname) arch=$(uname -m) cpus=$(nproc) nice=$(nice) memory.max=$(cat "/sys/fs/cgroup$cg/memory.max" 2>/dev/null || echo none) jobs=$JOBS"
sha256sum scripts/*.sh | sed 's/^/SG script /'
declare -A built
for n in $TREES; do
  t=$RD/trees/$n
  echo "== build $n $(date -u +%T)"
  mkdir -p "$t"
  if ! tar -xf "$PIN" -C "$t"; then echo "SG build-failed $n untar of the pin failed"; continue; fi
  if ! { git -C "$t" init -q && git -C "$t" add -f -A &&
         git -C "$t" -c user.name=spark-gates -c user.email=spark-gates@localhost commit -qm pin; }; then
    echo "SG build-failed $n git init, add or commit failed"; continue
  fi
  k=0; failed=
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    if ! git -C "$t" apply --whitespace=nowarn --index "$RD/patches/$p" > "$RD/apply-$n.log" 2>&1; then failed=$p; break; fi
    k=$((k + 1))
  done < "lists/$n.list"
  if [ -n "$failed" ]; then
    echo "PATCH FAILED $n $failed"
    head -20 "$RD/apply-$n.log" | sed "s/^/[$n apply] /"
    echo "SG patch-failed $n $failed applied=$k"
    continue
  fi
  git -C "$t" add -f -A
  echo "SG id $n $(git -C "$t" write-tree) applied=$k"
  built[$n]=1
done
# The three scripts keep their copies, caches and logs under $HOME: they get one inside this run, with each toolchain
# a tree names hardlinked in (a hardlink copy: removing it can never reach ~/tools).
mkdir -p "$H/tools"
for v in $(cat trees/*/.zig-version 2>/dev/null | sort -u) ibverbs; do
  case $v in *[!0-9A-Za-z.+-]*) continue ;; esac
  d=$([ "$v" = ibverbs ] && echo ibverbs || echo "zig-$(uname -m)-linux-$v")
  if [ -d "$HOME/tools/$d" ] && [ ! -e "$H/tools/$d" ]; then
    cp -al "$HOME/tools/$d" "$H/tools/" 2>/dev/null || cp -a "$HOME/tools/$d" "$H/tools/"
  fi
done
echo "SG home $H tools: $(ls "$H/tools" | tr '\n' ' ')"
for n in $TREES; do
  if [ -z "${built[$n]:-}" ]; then echo "SG skip $n not built"; continue; fi
  echo "== gates $n $(date -u +%T)"
  HOME=$H GATE_JOBS=$JOBS bash scripts/gates.sh "$RD/trees/$n" "$RUN-$n" 2>&1 | sed -u "s/^/[$n gates] /"
  echo "SG gates $n rc=${PIPESTATUS[0]}"
  [ "$n" = base ] && continue
  if [ -z "${built[base]:-}" ]; then echo "SG skip $n names and lean: base not built"; continue; fi
  echo "== gate-names base $n $(date -u +%T)"
  HOME=$H bash scripts/gate-names.sh "$RUN-base" "$RUN-$n" 2>&1 | sed -u "s/^/[$n names] /"
  echo "SG names $n rc=${PIPESTATUS[0]}"
  echo "== lean base $n $(date -u +%T)"
  HOME=$H bash scripts/lean.sh "$RD/trees/base" "$RD/trees/$n" "$RUN-$n" 2>&1 | sed -u "s/^/[$n lean] /"
  echo "SG lean $n rc=${PIPESTATUS[0]}"
done
rm -f /tmp/gate-names-"$RUN"-*.txt
echo "== verdict $(date -u +%T)"
python3 spark-gates.py verdict run.log 2>&1 | sed "s/^/[verdict] /"
vrc=${PIPESTATUS[0]}
echo "SG verdict rc=$vrc"
if [ "$CLEAN" = 1 ] && [ "$vrc" = 0 ]; then
  rm -rf "$RD/trees"
  find "$H" -mindepth 1 -maxdepth 1 ! -name gates -exec rm -rf {} +
  echo "SG cleaned $RD/trees and $H but for its gates logs: $(du -sh "$RD" | cut -f1) left in the run dir, $(df -h "$HOME" | awk 'NR == 2 {print $4}') free"
elif [ "$CLEAN" = 1 ]; then
  echo "SG clean skipped: the verdict is not a pass, so the trees and caches stay for diagnosis"
fi
if [ "$vrc" = 0 ]; then finish verdict=PASS; else finish verdict=FAIL; fi
'''

ITER = r'''#!/bin/bash
# iter.sh: written by spark-gates.py; checks the host, then runs iter-run.sh under the nice level and memory cap.
set -u
IN=$HOME/spark-gates/iter-@NAME@/in-@STAMP@
cd "$IN" || exit 2
trap 'rc=$?; if [ "$rc" = 4 ]; then cd "$HOME" && rm -rf "$IN"; fi' EXIT
sed -i 's/\r$//' iter-run.sh scripts/*.sh
@PREFLIGHT@
trap - EXIT
exec $WRAP bash "$IN/iter-run.sh"
'''

ITER_RUN = r'''#!/bin/bash
# iter-run.sh: written by spark-gates.py; rebuilds the iter-@NAME@ tree from the pin plus this call's patch list, prints
# its id and runs the asked steps on it with HOME, caches and logs in ~/spark-gates/iter-@NAME@.
set -u
IT=$HOME/spark-gates/iter-@NAME@
IN=$IT/in-@STAMP@
PIN=$HOME/spark-gates/pins/@COMMIT@.tar
Z=$HOME/tools/zig-$(uname -m)-linux-@ZIG@/zig
trap 'rm -rf "$IN"' EXIT
exec 9> "$IT/lock"
flock -n 9 || { echo "the iter slot @NAME@ is busy (lock $IT/lock); pass --name to use another"; exit 2; }
T=$IT/tree
echo "== tree iter-@NAME@ on $(hostname): @LABEL@ (@COMMIT@) plus $(grep -c . "$IN/lists/iter.list") patches; nice $(nice), memory.max $(cat "/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)/memory.max" 2>/dev/null || echo none)"
rm -rf "$T"; mkdir -p "$T"
tar -xf "$PIN" -C "$T" || { echo "untar of the pin failed"; exit 2; }
if ! { git -C "$T" init -q && git -C "$T" add -f -A &&
       git -C "$T" -c user.name=spark-gates -c user.email=spark-gates@localhost commit -qm pin; }; then
  echo "git init, add or commit of the tree failed"; exit 2
fi
k=0
while IFS= read -r p; do
  [ -n "$p" ] || continue
  if ! git -C "$T" apply --whitespace=nowarn --index "$IN/patches/$p" > "$IT/apply.log" 2>&1; then
    echo "PATCH FAILED $p (after $k applied)"; head -20 "$IT/apply.log"; echo "ITER-DONE rc=1"; exit 1
  fi
  k=$((k + 1))
done < "$IN/lists/iter.list"
git -C "$T" add -f -A
echo "tree id $(git -C "$T" write-tree) ($k patches applied)"
[ -d "$HOME/tools/ibverbs/root/usr/include" ] && export CPATH="$HOME/tools/ibverbs/root/usr/include${CPATH:+:$CPATH}"
mkdir -p "$IT/home"
export ZIG_GLOBAL_CACHE_DIR=$IT/global DEBUGINFOD_URLS=
C=$IT/cache
bad=0
cd "$T" || exit 2
for s in @STEPS@; do
  t0=$(date +%s)
  case $s in
    check)
      echo "== check-native-cuda-host"
      HOME=$IT/home timeout -k 30 1500 "$Z" build check-native-cuda-host -j@JOBS@ --cache-dir "$C" --summary all > "$IT/check.log" 2>&1 < /dev/null; rc=$?
      grep -E "error:|^Build Summary|failed command" "$IT/check.log" | awk '!seen[$0]++' | head -60 ;;
    fmt)
      echo "== fmt"
      "$Z" fmt --check zig/ > "$IT/fmt.log" 2>&1; rc=$?
      head -20 "$IT/fmt.log" ;;
    test)
      echo "== test-cuda-host"
      HOME=$IT/home timeout -k 30 2400 "$Z" build test-cuda-host -j@JOBS@ --cache-dir "$C" --summary all > "$IT/test.log" 2>&1 < /dev/null; rc=$?
      grep -E "^error: |: error: |^Build Summary" "$IT/test.log" | awk '!seen[$0]++' | head -80 ;;
    lean)
      echo "== lean, against the pristine pin"
      B=$HOME/spark-gates/pins/@COMMIT@
      if [ ! -d "$B" ]; then
        mkdir -p "$B.tmp-$$" && tar -xf "$PIN" -C "$B.tmp-$$" && mv -T "$B.tmp-$$" "$B" 2>/dev/null; rm -rf "$B.tmp-$$"
      fi
      HOME=$IT/home bash "$IN/scripts/lean.sh" "$B" "$T" "iter-@NAME@" > "$IT/lean.log" 2>&1; rc=$?
      tail -12 "$IT/lean.log" ;;
  esac
  [ "$rc" = 124 ] && echo "$s: TIMED OUT"
  echo "$s rc=$rc in $(( $(date +%s) - t0 )) s"
  [ "$rc" = 0 ] || bad=1
done
echo "ITER-DONE rc=$bad"
exit $bad
'''


def ship_and_start(host, tmp, remote_dir, entry, commit, stamp, size, stream):
    """Uploads ship.tar into ~/REMOTE/remote_dir, unpacks it and runs entry; uploads the pin archive when asked."""
    parent = "/".join([REMOTE, *remote_dir.split("/")[:-1]])
    ssh(host, f"mkdir -p {REMOTE}/pins {parent} && mkdir {REMOTE}/{remote_dir}")
    scp(host, tmp, "ship.tar", f"{REMOTE}/{remote_dir}/")
    first = f"cd {REMOTE}/{remote_dir} && tar -xf ship.tar && rm -f ship.tar && bash {entry}"
    again = f"bash {REMOTE}/{remote_dir}/{entry}"
    for attempt, command in enumerate((first, again)):
        if stream:
            rc, out = ssh_stream(host, command), ""
        else:
            rc, out = ssh(host, command, check=False)
            print(out.rstrip())
        if rc != 3 or attempt == 1:
            return rc
        t0 = time.monotonic()
        scp(host, tmp, "pin.tar", f"{REMOTE}/pins/{commit}.tar.part-{stamp}")
        print(f"pin archive uploaded ({size / 1e6:.1f} MB in {time.monotonic() - t0:.1f} s); starting again")
    return rc


def limits(a):
    """The nice level, memory cap and load ceiling for the preflight, checked."""
    if not 1 <= a.jobs <= 64:
        die("--jobs is 1 to 64")
    if not 0 <= a.nice <= 19:
        die("--nice is 0 to 19")
    if not 0 <= a.mem_max <= 4096:
        die("--mem-max is in GiB, 0 for no cap")
    if not 0 < a.max_load <= 1024:
        die("--max-load is a load average above 0")
    return {"NICE": a.nice, "MEMMAX": a.mem_max, "MAXLOAD": f"{a.max_load:g}"}


def parse_trees(values):
    trees = {}
    for v in values:
        name, _, rest = v.partition("=")
        if not NAME_RE.match(name):
            die(f"--tree {v!r}: a tree name is letters, digits, '.', '_' and '-'")
        if name in trees:
            die(f"--tree {name} given twice")
        trees[name] = split_dirs([rest]) if rest else []
    if "base" not in trees:
        print("no --tree base: adding base, the pristine pin")
        trees["base"] = []
    return {"base": trees["base"], **{k: v for k, v in trees.items() if k != "base"}}


def cmd_gates(a):
    refuse_wsl()
    root = repo_root()
    pin_repo = Path(a.pin_repo) if a.pin_repo else root / "work" / "parity" / "tree"
    trees = parse_trees(a.tree)
    if len(trees) < 2:
        die("give at least one tree besides base")
    limits(a)
    expects = {}
    for e in a.expect:
        name, _, tid = e.partition("=")
        if name not in trees or not ID_RE.match(tid):
            die(f"--expect {e!r}: NAME=TREEID for a tree given with --tree")
        expects[name] = (tid, "--expect")
    commit, pin_tree, zig = resolve_pin(pin_repo, a.pin)
    dirs, lists, ids = collect_patches(trees)
    for name in trees:
        if not lists[name] and name not in expects:
            expects[name] = (pin_tree, "pin-tree")
    run = time.strftime("sg-%Y%m%d-%H%M%S", time.gmtime())
    need = GIB_PER_TREE * len(trees) + 4
    print(f"pin {a.pin}: commit {commit}, tree {pin_tree}, zig {zig}")
    for name, given in trees.items():
        what = f"{len(lists[name])} patches: {', '.join(shown(Path(d).resolve()) for d in given)}" if given else "the pin"
        exp = f"expected {expects[name][0]} ({expects[name][1]})" if name in expects else "no expected id"
        print(f"  {name:<10} {what}; {exp}")
    work = root / "work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="spark-gates-", dir=work) as tmp:
        sha, size = archive_pin(pin_repo, commit, Path(tmp) / "pin.tar")
        print(f"pin archive {size / 1e6:.1f} MB, sha256 {sha}")
        config = [f"SG run {run}", f"SG pin {a.pin} commit={commit} tree={pin_tree} zig={zig} sha256={sha}"]
        config += [f"SG dir {did} {disp} files={len(files)}" for did, disp, _, files in dirs]
        config += [f"SG tree {n} patches={len(lists[n])} dirs={','.join(ids[n]) or '-'}" for n in trees]
        config += [f"SG expect {n} {tid} from={src}" for n, (tid, src) in expects.items()]
        config.append(f"SG options host={a.host} jobs={a.jobs} nice={a.nice} mem-max={a.mem_max}G "
                      f"max-load={a.max_load:g} clean={int(a.clean)}")
        ship = Ship()
        ship.add("config.txt", "".join(f"{c}\n" for c in config))
        ship.add("runner.sh", fill(RUNNER, RUN=run, COMMIT=commit, JOBS=a.jobs, CLEAN=int(a.clean),
                                   TREES=" ".join(trees)), 0o755)
        ship.add("launch.sh", fill(LAUNCH.replace("@PREFLIGHT@", PREFLIGHT), RUN=run, ZIG=zig, NEED=need,
                                   COMMIT=commit, SHA=sha, STAMP=run, **limits(a)), 0o755)
        ship.add("status.sh", fill(STATUS, RUN=run), 0o755)
        ship.add("spark-gates.py", Path(__file__).read_bytes(), 0o755)
        ship.add_common(root, dirs, lists)
        ship.write(Path(tmp) / "ship.tar")
        rc = ship_and_start(a.host, tmp, run, "launch.sh", commit, run, size, stream=False)
    if rc != 0:
        die(f"run {run} did not start on {a.host} (rc={rc})")
    me = sys.argv[0].replace("\\", "/")
    print(f"run {run} started on {a.host}: log ~/{REMOTE}/{run}/run.log")
    print(f"wait: python {me} wait --host {a.host} --run {run}")


def latest_run(host):
    _, out = ssh(host, f"ls -1 {REMOTE}", check=False)
    runs = sorted(x for x in out.split() if RUN_RE.match(x))
    if not runs:
        die(f"no runs under ~/{REMOTE} on {host}")
    return runs[-1]


def cmd_wait(a):
    refuse_wsl()
    run = a.run or latest_run(a.host)
    if not RUN_RE.match(run):
        die(f"--run {run!r}: a run is named sg-YYYYMMDD-HHMMSS")
    print(f"waiting for {run} on {a.host}, polling every {a.interval} s", flush=True)
    deadline = time.monotonic() + a.max_minutes * 60
    while True:
        rc, out = ssh(a.host, f"bash {REMOTE}/{run}/status.sh", check=False)
        last = out.strip().splitlines()[-1] if out.strip() else ""
        if rc == 0 and last.startswith(("DONE", "DEAD")):
            break
        if rc == 127 or "No such file" in out:
            die(f"no run {run} on {a.host}: {last}")
        print(last if rc == 0 else f"{time.strftime('%H:%M:%S')} ssh rc={rc}: {last[:200]} (trying again)", flush=True)
        if time.monotonic() > deadline:
            die(f"gave up after {a.max_minutes} minutes; the run goes on")
        time.sleep(a.interval)
    _, log = ssh(a.host, f"cat {REMOTE}/{run}/run.log")
    lines = log.splitlines()
    cut = next((i for i, x in enumerate(lines) if x.startswith("== verdict")), len(lines))
    print(f"run {run} on {a.host}: {last}")
    print(f"---- ~/{REMOTE}/{run}/run.log, the last {min(a.tail, cut)} lines before the verdict ----")
    for x in lines[max(0, cut - a.tail):cut]:
        print(x)
    print("---- verdict, computed here from run.log ----")
    r = parse_log(log)
    table, ok = judge(r)
    if last.startswith("DEAD"):
        dead = "the runner is gone and run.log has no SPARK-GATES-DONE (killed, OOM or a reboot)"
        if ok:
            table[-1] = f"VERDICT FAIL: {dead}"
        else:
            table.insert(len(table) - 1, f"run: {dead}")
        ok = False
    for x in table:
        print(x)
    if r.verdict_rc is not None and (r.verdict_rc == 0) != ok:
        print(f"note: the verdict the host computed at the end of the run had rc={r.verdict_rc}")
    if not any(x.startswith("SG cleaned") for x in lines):
        print(f"scratch kept for diagnosis: ~/{REMOTE}/{run}/trees and ~/{REMOTE}/{run}/home; keep only the logs: "
              f"ssh {a.host} 'cd ~/{REMOTE}/{run} && rm -rf trees && find home -mindepth 1 -maxdepth 1 ! -name gates "
              f"-exec rm -rf {{}} +'")
    sys.exit(0 if ok else 1)


def cmd_iter(a):
    refuse_wsl()
    root = repo_root()
    pin_repo = Path(a.pin_repo) if a.pin_repo else root / "work" / "parity" / "tree"
    if not NAME_RE.match(a.name):
        die(f"--name {a.name!r}: letters, digits, '.', '_' and '-'")
    steps = a.steps or ["check", "fmt"]
    for s in steps:
        if s not in ITER_STEPS:
            die(f"unknown step {s!r}; the steps are {' '.join(ITER_STEPS)}")
    limits(a)
    commit, pin_tree, zig = resolve_pin(pin_repo, a.pin)
    dirs, lists, _ = collect_patches({"iter": split_dirs(a.dir)})
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + f"-{os.getpid()}"
    print(f"pin {a.pin}: commit {commit}, tree {pin_tree}, zig {zig}; {len(lists['iter'])} patches from "
          f"{', '.join(d[1] for d in dirs)}; steps {' '.join(steps)} on {a.host}", flush=True)
    t0 = time.monotonic()
    work = root / "work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="spark-gates-", dir=work) as tmp:
        sha, size = archive_pin(pin_repo, commit, Path(tmp) / "pin.tar")
        ship = Ship()
        ship.add("iter.sh", fill(ITER.replace("@PREFLIGHT@", PREFLIGHT), NAME=a.name, STAMP=stamp, ZIG=zig,
                                 NEED=GIB_PER_TREE + 2, COMMIT=commit, SHA=sha, **limits(a)), 0o755)
        ship.add("iter-run.sh", fill(ITER_RUN, NAME=a.name, STAMP=stamp, ZIG=zig, COMMIT=commit, LABEL=a.pin,
                                     STEPS=" ".join(steps), JOBS=a.jobs), 0o755)
        ship.add_common(root, dirs, lists)
        ship.write(Path(tmp) / "ship.tar")
        rc = ship_and_start(a.host, tmp, f"iter-{a.name}/in-{stamp}", "iter.sh", commit, stamp, size, stream=True)
    print(f"iter rc={rc} in {time.monotonic() - t0:.0f} s on the workstation clock, shipping included")
    sys.exit(rc if rc in (0, 1) else 2)


# ---- the verdict: run.log in, a table and an exit code out -------------------------------------------------------

STEP_RE = re.compile(r"^(\S+) rc=(\d+)(?:\s|$)")
ABSENT_RE = re.compile(r"^(\S+): not a step of this tree$")
TIMEOUT_RE = re.compile(r"^(\S+): TIMED OUT")
TESTNAME_RE = re.compile(r"^error: '(.*)'(?: failed:.*)?$")
COMPILE_RE = re.compile(r"^[^ ].*: error: ")
PREFIX_RE = re.compile(r"^\[([A-Za-z0-9][A-Za-z0-9._-]*) (gates|names|lean|apply)\] ?(.*)$")


class Tree:
    def __init__(self, name):
        self.name = name
        self.configured = False
        self.npatches = 0
        self.dirs = []
        self.expect = self.expect_from = None
        self.id = self.applied = self.patch_failed = self.build_failed = None
        self.gates_rc = self.names_rc = self.lean_rc = None
        self.gates_done = False
        self.steps = {}  # step -> rc
        self.seen = []  # every step gates.sh named, in its order, the ones it said are not steps included
        self.absent = []
        self.timed_out = set()
        self.listed = {}  # step -> the failing test names gates.sh listed under it
        self.errors = {}  # step -> the compile error lines gates.sh listed under it
        self.gates_lines = []
        self.names = {"new": None, "gone": None, "count": None, "base_count": None, "build_failed": False,
                      "lines": []}
        self.lean = {"base": None, "head": None, "new": None, "details": [], "lines": []}


class Run:
    def __init__(self):
        self.run = self.pin = self.verdict_rc = None
        self.dirs = {}
        self.trees = {}
        self.order = []

    def tree(self, name):
        if name not in self.trees:
            self.trees[name] = Tree(name)
            self.order.append(name)
        return self.trees[name]


def keyvals(fields):
    return dict(f.split("=", 1) for f in fields if "=" in f)


def number(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def parse_log(text):
    r = Run()
    step_now, names_mode = {}, {}
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        m = re.match(r"^SG (\S+) ?(.*)$", line)
        if m:
            parse_sg(r, m.group(1), m.group(2).split())
            continue
        m = PREFIX_RE.match(line)
        if not m:
            continue
        t = r.tree(m.group(1))
        kind, body = m.group(2), m.group(3)
        if kind == "gates":
            parse_gates(t, body, step_now)
        elif kind == "names":
            parse_names(r, t, body, names_mode)
        elif kind == "lean":
            parse_lean(t, body)
    return r


def parse_sg(r, kind, f):
    kv = keyvals(f)
    if kind == "run" and f:
        r.run = f[0]
    elif kind == "pin" and f:
        r.pin = " ".join(f)
    elif kind == "dir" and len(f) >= 2:
        r.dirs[f[0]] = f[1]
    elif kind == "tree" and f:
        t = r.tree(f[0])
        t.configured, t.npatches = True, number(kv.get("patches")) or 0
        t.dirs = [] if kv.get("dirs", "-") == "-" else kv["dirs"].split(",")
    elif kind == "expect" and len(f) >= 2:
        t = r.tree(f[0])
        t.expect, t.expect_from = f[1], kv.get("from", "?")
    elif kind == "id" and len(f) >= 2:
        t = r.tree(f[0])
        t.id, t.applied = f[1], number(kv.get("applied"))
    elif kind == "patch-failed" and len(f) >= 2:
        t = r.tree(f[0])
        t.patch_failed, t.applied = f[1], number(kv.get("applied"))
    elif kind == "build-failed" and f:
        r.tree(f[0]).build_failed = " ".join(f[1:]) or "unknown"
    elif kind in ("gates", "names", "lean") and len(f) >= 2:
        setattr(r.tree(f[0]), f"{kind}_rc", number(kv.get("rc")))
    elif kind == "verdict":
        r.verdict_rc = number(kv.get("rc"))


def parse_gates(t, body, step_now):
    t.gates_lines.append(body)
    if body.startswith("GATES-DONE"):
        t.gates_done = True
        return
    m = STEP_RE.match(body)
    if m:
        t.steps[m.group(1)] = int(m.group(2))
        t.seen.append(m.group(1))
        step_now[t.name] = m.group(1)
        return
    m = ABSENT_RE.match(body)
    if m:
        t.absent.append(m.group(1))
        t.seen.append(m.group(1))
        return
    m = TIMEOUT_RE.match(body)
    if m:
        t.timed_out.add(m.group(1))
        return
    step = step_now.get(t.name)
    if step is None:
        return
    m = TESTNAME_RE.match(body)
    if m:
        t.listed.setdefault(step, []).append(m.group(1))
    elif COMPILE_RE.match(body):
        t.errors.setdefault(step, []).append(body)


def parse_names(r, t, body, mode):
    nm = t.names
    nm["lines"].append(body)
    head, base = f"{r.run}-{t.name}", f"{r.run}-base"
    if body.startswith(f"{head}: BUILD FAILED"):
        nm["build_failed"], mode[t.name] = True, None
        return
    if body.startswith(f"{base}: warning"):
        mode[t.name] = None
        return
    for who, key in ((head, "count"), (base, "base_count")):
        m = re.match(rf"^{re.escape(who)}: (\d+) failing names", body)
        if m:
            nm[key], mode[t.name] = int(m.group(1)), None
            return
    for who, key in ((head, "new"), (base, "gone")):
        prefix = f"only {who} fails: "
        if body.startswith(prefix):
            first = body[len(prefix):]
            nm[key], mode[t.name] = ([] if first == "none" else [first]), key
            return
    if mode.get(t.name):
        nm[mode[t.name]].append(body)


def parse_lean(t, body):
    ln = t.lean
    ln["lines"].append(body)
    m = re.match(r"^(base|head) (.*): (\d+) files, (\d+) problems$", body)
    if m:
        ln[m.group(1)] = (int(m.group(3)), int(m.group(4)))
        return
    m = re.match(r"^lean: (\d+) problems, (\d+) on the base, (\d+) new$", body)
    if m:
        ln["new"] = int(m.group(3))
        return
    ln["details"].append(body)


def patch_shown(r, p):
    did, _, f = p.partition("/")
    return f"{r.dirs.get(did, did)}/{f}"


def first_error(t, step):
    errs = t.errors.get(step)
    return f": {errs[0][:200]}" if errs else ""


def built_reasons(r, t):
    if t.patch_failed:
        return [f"PATCH FAILED: {patch_shown(r, t.patch_failed)} does not apply (after {t.applied} of {t.npatches})"]
    if t.build_failed:
        return [f"the tree was not built: {t.build_failed}"]
    if t.id is None:
        return ["the tree was not built: the runner stopped before it"]
    out = []
    if t.expect and t.id != t.expect:
        out.append(f"tree id {t.id} is not the expected {t.expect} ({t.expect_from})")
    if t.applied != t.npatches:
        out.append(f"{t.applied} of {t.npatches} patches applied")
    return out


def gates_reasons(t):
    if t.gates_rc is None:
        return ["gates.sh did not run"]
    if not t.gates_done:
        return [f"gates.sh stopped before GATES-DONE (rc={t.gates_rc}): {' | '.join(t.gates_lines[-3:]) or 'no output'}"]
    return []


def base_reasons(r, base):
    if base is None:
        return ["the run has no base tree"]
    out = built_reasons(r, base)
    if base.id is None:
        return out
    out += gates_reasons(base)
    if base.gates_done and TEST_STEP not in base.steps:
        out.append(f"{TEST_STEP} did not run on base, so there is no reference set of failing names")
    if base.errors.get(TEST_STEP):
        out.append(f"base's {TEST_STEP} has compile errors, so its failing names are no reference"
                   f"{first_error(base, TEST_STEP)}")
    return out


def head_reasons(r, t, base):
    out = built_reasons(r, t)
    if t.id is None:
        return out
    out += gates_reasons(t)
    if t.gates_done:
        for s in REQUIRED_STEPS:
            if s not in t.steps:
                why = "not a step of this tree: did `zig build -l` fail?" if s in t.absent else "no rc in the output"
                out.append(f"{s} did not run ({why})")
        for s in (base.steps if base else {}):
            if s not in t.steps and s not in REQUIRED_STEPS:
                out.append(f"{s} ran on base but not on this tree")
    for s, rc in t.steps.items():
        if s != TEST_STEP and rc != 0:
            out.append(f"{s} rc={rc}{' (timed out)' if s in t.timed_out else ''}{first_error(t, s)}")
    nm = t.names
    rc = t.steps.get(TEST_STEP)
    if rc not in (None, 0):
        if rc != 1:
            out.append(f"{TEST_STEP} rc={rc}{' (timed out)' if TEST_STEP in t.timed_out else ''}")
        elif nm["new"]:
            out.append(f"{TEST_STEP} fails {len(nm['new'])} test name(s) base does not: {'; '.join(nm['new'])}")
        elif nm["count"] == 0:
            out.append(f"{TEST_STEP} rc=1 but no failing test name explains it{first_error(t, TEST_STEP)}")
    if t.names_rc is None:
        out.append("gate-names.sh did not run")
    elif nm["count"] is None or nm["new"] is None:
        out.append(f"gate-names.sh output not understood (rc={t.names_rc}): {' | '.join(nm['lines'][-3:])}")
    elif t.names_rc != 0:
        out.append(f"gate-names rc={t.names_rc}"
                   + (": BUILD FAILED, the test-cuda-host log holds compile errors" if nm["build_failed"] else ""))
    ln = t.lean
    if t.lean_rc is None:
        out.append("lean.sh did not run")
    elif ln["base"] is None or ln["head"] is None:
        out.append(f"lean_check.py did not report on both sides (rc={t.lean_rc}): {' | '.join(ln['lines'][-3:])}")
    elif ln["new"] is None:
        out.append(f"lean.sh rc={t.lean_rc} without a 'N new' line: {' | '.join(ln['lines'][-3:])}")
    elif ln["new"] != 0:
        out.append(f"lean: {ln['new']} new problem(s): {'; '.join(ln['details']) or 'see the log'}")
    elif t.lean_rc != 0:
        out.append(f"lean.sh rc={t.lean_rc}")
    return out


def head_label(t, reasons):
    if not reasons:
        return "PASS"
    if t.patch_failed:
        return "PATCH FAILED"
    if any(t.errors.values()) or t.names["build_failed"]:
        return "BUILD FAILED"
    return "FAIL"


def step_cell(t, s, base_count):
    if s in t.steps:
        rc = t.steps[s]
        cell = str(rc) + (" timed out" if s in t.timed_out else "")
        if s == TEST_STEP and rc != 0:
            if t.name == "base":
                n = base_count if base_count is not None else len(t.listed.get(s, []))
                cell += f": {n} failing"
            elif t.names["count"] is not None:
                cell += f": {t.names['count']} failing, {len(t.names['new'] or [])} new"
        return cell
    return "n/a" if s in t.absent else "-"


def judge(r):
    """(lines, ok) for a parsed run.log: a pass needs a sound base and every other tree passing against it."""
    trees = [r.trees[n] for n in r.order if r.trees[n].configured] or [r.trees[n] for n in r.order]
    if not trees:
        return ["VERDICT FAIL: run.log names no tree"], False
    base = r.trees.get("base")
    heads = [t for t in trees if t.name != "base"]
    breasons = base_reasons(r, base)
    reasons = {t.name: head_reasons(r, t, base) for t in heads}
    labels = {t.name: head_label(t, reasons[t.name]) for t in heads}
    if base is not None:
        labels["base"] = "reference" if not breasons else "BROKEN"
    base_count = next((t.names["base_count"] for t in heads if t.names["base_count"] is not None), None)
    steps = []
    for t in trees:
        for i, s in enumerate(t.seen):
            if s not in steps:
                before = next((x for x in t.seen[i + 1:] if x in steps), None)
                steps.insert(steps.index(before) if before else len(steps), s)
    rows = [["", *[t.name for t in trees]],
            ["patches", *[f"{t.applied if t.applied is not None else '-'}/{t.npatches}" for t in trees]],
            ["tree id", *[t.id[:12] if t.id else "-" for t in trees]],
            ["expected", *[("-" if not t.expect else "match" if t.id == t.expect else "MISMATCH") for t in trees]]]
    rows += [[s, *[step_cell(t, s, base_count) for t in trees]] for s in steps]
    rows.append(["gate-names", *[("-" if t.name == "base" or t.names_rc is None else str(t.names_rc)) for t in trees]])
    rows.append(["lean new", *[("-" if t.name == "base" or t.lean["new"] is None else str(t.lean["new"]))
                               for t in trees]])
    rows.append(["verdict", *[labels.get(t.name, "-") for t in trees]])
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    out = [f"run {r.run or '?'}; pin {r.pin or '?'}"]
    out += ["  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip() for row in rows]
    out.append("rc per step from scripts/gates.sh (n/a: not a step of that tree, -: no result); test-cuda-host at rc 1"
               " passes only when gate-names finds every failing name in base's set")
    out.append(f"{TEST_STEP} failing names, as gates.sh listed them:")
    for t in trees:
        new = set(t.names["new"] or [])
        listed = t.listed.get(TEST_STEP, [])
        extra = "" if t.name == "base" or t.names["new"] is None else f", {len(new) or 'none'} new"
        out.append(f"  {t.name}: {len(listed) or 'none'} listed{extra}")
        out += [f"    {'NEW ' if n in new else ''}{n}" for n in listed]
    for t in heads:
        ln = t.lean
        if ln["base"] and ln["head"]:
            out.append(f"lean {t.name}: base {ln['base'][0]} files {ln['base'][1]} problems, head {ln['head'][0]} "
                       f"files {ln['head'][1]} problems, {ln['new']} new")
    bad = [(t.name, labels[t.name], reasons[t.name]) for t in heads if reasons[t.name]]
    if breasons:
        bad.insert(0, ("base", "BROKEN", breasons))
    if not heads:
        bad.append(("run", "FAIL", ["the run has no tree besides base"]))
    for name, label, why in bad:
        out.append(f"{name}: {label}")
        out += [f"  - {w}" for w in why]
    if bad:
        out.append("VERDICT FAIL: " + "; ".join(f"{name} {label}" for name, label, _ in bad))
        return out, False
    out.append(f"VERDICT PASS: {', '.join(t.name for t in heads)} pass against base")
    return out, True


def cmd_verdict(a):
    table, ok = judge(parse_log(Path(a.log).read_text(encoding="utf-8", errors="replace")))
    for x in table:
        print(x)
    sys.exit(0 if ok else 1)


def add_limits(parser):
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help=f"build jobs (default {DEFAULT_JOBS})")
    parser.add_argument("--nice", type=int, default=DEFAULT_NICE, help=f"nice level of everything (default {DEFAULT_NICE})")
    parser.add_argument("--mem-max", type=int, default=DEFAULT_MEM_GIB,
                        help=f"GiB cap of the run's user scope, 0 for none (default {DEFAULT_MEM_GIB})")
    parser.add_argument("--max-load", type=float, default=DEFAULT_MAX_LOAD,
                        help=f"do not start above this load average (default {DEFAULT_MAX_LOAD:g})")


def main():
    try:
        sys.stdout.reconfigure(errors="replace", line_buffering=True)
    except (AttributeError, ValueError):
        pass
    p = argparse.ArgumentParser(prog="spark-gates.py", description=__doc__.split("\n", 1)[0],
                                epilog=__doc__.split("\n\n", 2)[2], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gates", help="build trees on the host, gate them, compare them with base (detached)")
    g.add_argument("--host", default=DEFAULT_HOST, required=not DEFAULT_HOST, help="user@host (SPARK_GATES_HOST)")
    g.add_argument("--pin", required=True, help="the upstream tag or sha the trees start from")
    g.add_argument("--pin-repo", help="the upstream clone it is archived from (default: work/parity/tree)")
    g.add_argument("--tree", action="append", required=True, metavar="NAME[=DIR[,DIR...]]")
    g.add_argument("--expect", action="append", default=[], metavar="NAME=TREEID")
    add_limits(g)
    g.add_argument("--clean", action="store_true", help="after a passing verdict, remove the run's trees and caches")
    g.set_defaults(fn=cmd_gates)
    w = sub.add_parser("wait", help="poll a run until it finishes and print its verdict")
    w.add_argument("--host", default=DEFAULT_HOST, required=not DEFAULT_HOST, help="user@host (SPARK_GATES_HOST)")
    w.add_argument("--run", help="the run name gates printed (default: the newest run on the host)")
    w.add_argument("--interval", type=int, default=60, help="seconds between polls (default 60)")
    w.add_argument("--max-minutes", type=int, default=300, help="give up waiting after this long (default 300)")
    w.add_argument("--tail", type=int, default=30, help="log lines to print before the verdict (default 30)")
    w.set_defaults(fn=cmd_wait)
    i = sub.add_parser("iter", help="rebuild one tree on the host and run quick steps on it (foreground)")
    i.add_argument("--host", default=DEFAULT_HOST, required=not DEFAULT_HOST, help="user@host (SPARK_GATES_HOST)")
    i.add_argument("--pin", required=True)
    i.add_argument("--pin-repo", help="the upstream clone it is archived from (default: work/parity/tree)")
    i.add_argument("--dir", action="append", required=True, metavar="DIR[,DIR...]")
    add_limits(i)
    i.add_argument("--name", default="iter", help="the slot on the host: its tree and zig caches (default iter)")
    i.add_argument("steps", nargs="*", metavar="STEP", help="check fmt test lean (default: check fmt)")
    i.set_defaults(fn=cmd_iter)
    v = sub.add_parser("verdict", help="the verdict table of a run.log")
    v.add_argument("log")
    v.set_defaults(fn=cmd_verdict)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
