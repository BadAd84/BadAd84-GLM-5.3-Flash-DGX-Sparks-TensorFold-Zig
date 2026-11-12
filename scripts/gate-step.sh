#!/usr/bin/env bash
# gate-step.sh TREE NAME STEP... - run named `zig build` steps on a tree the way gates.sh does (same zig, same caches,
# same log names), for rerunning one failed step after a fix. Exit 1 if any failed.
set -uo pipefail
TREE=${1:?usage: gate-step.sh TREE NAME STEP...}; NAME=${2:?name}; shift 2
cd "$TREE" || exit 1
Z="$HOME/tools/zig-x86_64-linux-$(cat .zig-version)/zig"
[ -d "$HOME/tools/ibverbs/root/usr/include" ] && export CPATH="$HOME/tools/ibverbs/root/usr/include${CPATH:+:$CPATH}"
export ZIG_GLOBAL_CACHE_DIR="$HOME/zc-gates-global"
mkdir -p "$HOME/gates"; bad=0
for step in "$@"; do
  log="$HOME/gates/$NAME-$step.log"
  "$Z" build "$step" --cache-dir "$HOME/zc-gates-$NAME" --summary all > "$log" 2>&1; rc=$?
  echo "$step rc=$rc | $(grep -E '^Build Summary' "$log" | tail -1)"
  [ "$rc" -ne 0 ] && { bad=1; grep -E "^error: '|^[^ ].*: error: " "$log" | head -12 | cut -c1-240; }
done
exit $bad
