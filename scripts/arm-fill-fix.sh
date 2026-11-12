#!/usr/bin/env bash
# arm-fill-fix.sh TREE - patch 0037 by meaning, for arm-tree.sh arms where its context does not match: after the forward's
# `try kda_block.bodyProfile(` call, restore `if (out) |o| try kda_block.fill(...)` when the next line lacks it.
# Prints what it did; exits 1 when the call site is not found exactly once.
set -uo pipefail
F="${1:?usage: fill-fix.sh TREE}/zig/src/families/glm/cuda_forward.zig"
n=$(grep -c 'try kda_block.bodyProfile(' "$F")
[ "$n" = 1 ] || { echo "fill-fix: $n bodyProfile call sites in $F (want 1)"; exit 1; }
if grep -A1 'try kda_block.bodyProfile(' "$F" | grep -q 'kda_block.fill('; then
  echo "fill-fix: fill already present"; exit 0
fi
awk '{ print } /try kda_block\.bodyProfile\(/ { match($0, /^ */); printf "%sif (out) |o| try kda_block.fill(f.set(), f.stream, k, s, 0, rows, o);\n", substr($0, 1, RLENGTH) }' "$F" > "$F.new" && mv "$F.new" "$F"
grep -A1 'try kda_block.bodyProfile(' "$F" | grep -q 'kda_block.fill(' && echo "fill-fix: fill restored" || { echo "fill-fix: FAILED"; exit 1; }
