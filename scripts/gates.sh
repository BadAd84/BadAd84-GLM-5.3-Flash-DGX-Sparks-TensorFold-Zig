#!/usr/bin/env bash
# gates.sh TREE [NAME] - the README's gates on an applied tree, from WSL on the workstation (x86_64 host tests):
#   zig build check-native-cuda-host, zig build test-cuda-host, zig fmt --check zig/
# Prints each step's exit code and, for the host tests, the failing test names (compare the NAME set with the pin's,
# which exits 0 on 9c9bf542). Logs: ~/gates/NAME-<step>.log. Exit 1 if any step failed.
# Needs ~/tools/zig-x86_64-linux-<.zig-version>; the lean gate (base against head) is separate: tools/zig/lean_new.py.
set -uo pipefail
TREE=${1:?usage: gates.sh TREE [NAME]}; NAME=${2:-$(basename "$(dirname "$TREE")")}
cd "$TREE" || exit 1
V=$(cat .zig-version)
Z="$HOME/tools/zig-x86_64-linux-$V/zig"
[ -x "$Z" ] || { echo "no zig at $Z"; exit 2; }
[ -d "$HOME/tools/ibverbs/root/usr/include" ] && export CPATH="$HOME/tools/ibverbs/root/usr/include${CPATH:+:$CPATH}"
export ZIG_GLOBAL_CACHE_DIR="$HOME/zc-gates-global"
mkdir -p "$HOME/gates"
bad=0
for step in check-native-cuda-host test-cuda-host; do
  log="$HOME/gates/$NAME-$step.log"
  "$Z" build "$step" --cache-dir "$HOME/zc-gates-$NAME" --summary all > "$log" 2>&1; rc=$?
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
