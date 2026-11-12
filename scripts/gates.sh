#!/usr/bin/env bash
# gates.sh TREE [NAME] - the README's gates on an applied tree, from WSL on the workstation (x86_64 host tests):
#   zig build check-native-cuda-host, zig build test-cuda-host, zig fmt --check zig/
# and the steps those two do not reach:
#   zig build compile-cuda-tests      compiles the GPU test binary (zig/tests/cuda): a check nothing imports from
#                                     main.zig is otherwise never compiled at all
#   the standalone host steps listed in STANDALONE below, each only if the tree's build defines it
# Prints each step's exit code and, for the host tests, the failing test names (compare the NAME set with the pin's
# through gate-names.sh: on this filesystem the pin itself fails 26 file-permission tests). Logs: ~/gates/NAME-<step>.log.
# Exit 1 if a step failed. Needs ~/tools/zig-x86_64-linux-<.zig-version>. The lean gate is scripts/lean.sh.
set -uo pipefail
TREE=${1:?usage: gates.sh TREE [NAME]}; NAME=${2:-$(basename "$(dirname "$TREE")")}
STANDALONE="test-glm-ring-host test-glm-logprobs-host test-glm-onepass-order-host test-rows-host"
cd "$TREE" || exit 1
V=$(cat .zig-version)
Z="$HOME/tools/zig-x86_64-linux-$V/zig"
[ -x "$Z" ] || { echo "no zig at $Z"; exit 2; }
[ -d "$HOME/tools/ibverbs/root/usr/include" ] && export CPATH="$HOME/tools/ibverbs/root/usr/include${CPATH:+:$CPATH}"
export ZIG_GLOBAL_CACHE_DIR="$HOME/zc-gates-global"
mkdir -p "$HOME/gates"
bad=0
steps=$("$Z" build --cache-dir "$HOME/zc-gates-$NAME" -l 2>/dev/null | awk '{print $1}')
for step in check-native-cuda-host test-cuda-host compile-cuda-tests $STANDALONE; do
  if ! grep -qx "$step" <<< "$steps"; then echo "$step: not a step of this tree"; continue; fi
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
