#!/usr/bin/env bash
# gates.sh TREE [NAME] - the README's gates on an applied tree, from WSL on the workstation (x86_64 host tests):
#   zig build check-native-cuda-host, zig build test-cuda-host, zig fmt --check zig/
# and the steps those two do not reach:
#   zig build compile-cuda-tests      compiles the GPU test binary (zig/tests/cuda): a check nothing imports from
#                                     main.zig is otherwise never compiled at all
#   the standalone host steps listed in STANDALONE below, each only if the tree's build defines it
# The tree is first copied to ~/gt/NAME on the WSL filesystem and the gates run on the copy. Run in place on the
# Windows mount (/mnt/c), 26 upstream tests that need POSIX file modes, symlinks or FIFOs fail on the pin itself, and
# under load the test binary that spawns child processes hangs instead of failing (zombie children, then a debug-info
# lookup on a socket; three gate runs sat there until killed). On the copy those 26 pass.
# Prints each step's exit code and the failing test names. Logs: ~/gates/NAME-<step>.log. Exit 1 if a step failed.
# Needs ~/tools/zig-x86_64-linux-<.zig-version>. Each step has a 40-minute ceiling. The lean gate is scripts/lean.sh.
set -uo pipefail
TREE=${1:?usage: gates.sh TREE [NAME]}; NAME=${2:-$(basename "$(dirname "$TREE")")}
STANDALONE="test-glm-ring-host test-glm-logprobs-host test-glm-onepass-order-host test-rows-host"
[ -f "$TREE/.zig-version" ] || { echo "no tree at $TREE"; exit 2; }
V=$(cat "$TREE/.zig-version")
Z="$HOME/tools/zig-x86_64-linux-$V/zig"
[ -x "$Z" ] || { echo "no zig at $Z"; exit 2; }
COPY="$HOME/gt/$NAME"
mkdir -p "$COPY" "$HOME/gates"
rsync -a --delete --exclude .git --exclude .zig-cache --exclude zig-out "$TREE/" "$COPY/" || { echo "copy to $COPY failed"; exit 2; }
cd "$COPY" || exit 1
[ -d "$HOME/tools/ibverbs/root/usr/include" ] && export CPATH="$HOME/tools/ibverbs/root/usr/include${CPATH:+:$CPATH}"
export ZIG_GLOBAL_CACHE_DIR="$HOME/zc-gates-global"
export DEBUGINFOD_URLS=
bad=0
steps=$("$Z" build --cache-dir "$HOME/zc-gates-$NAME" -l 2>/dev/null | awk '{print $1}')
for step in check-native-cuda-host test-cuda-host compile-cuda-tests $STANDALONE; do
  if ! grep -qx "$step" <<< "$steps"; then echo "$step: not a step of this tree"; continue; fi
  log="$HOME/gates/$NAME-$step.log"
  timeout -k 30 2400 "$Z" build "$step" --cache-dir "$HOME/zc-gates-$NAME" --summary all > "$log" 2>&1 < /dev/null; rc=$?
  [ "$rc" = 124 ] && echo "$step: TIMED OUT after 40 minutes" | tee -a "$log"
  echo "$step rc=$rc | $(grep -E '^Build Summary' "$log" | tail -1)"
  if [ "$rc" -ne 0 ]; then
    bad=1
    grep -E "^error: '" "$log" | sed "s/ exited.*//" | sort -u | head -40
    grep -E "^[^ ].*: error: " "$log" | head -12 | cut -c1-240
  fi
done
"$Z" fmt --check zig/ > "$HOME/gates/$NAME-fmt.log" 2>&1; rc=$?
echo "fmt rc=$rc $(head -5 "$HOME/gates/$NAME-fmt.log" | tr '\n' ' ' | cut -c1-300)"
[ "$rc" -ne 0 ] && bad=1
echo "GATES-DONE $NAME bad=$bad"
exit $bad
