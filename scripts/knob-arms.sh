#!/usr/bin/env bash
# knob-arms.sh [IMAGE] - the recipe's knobs ONE AT A TIME on the full patch stack: for each knob in serve.sh's
# DEFS, one bench-arm.sh arm (P=1,2,4,6,8, a fresh boot per level) with only that knob on, between two
# all-knobs-off arms that give the run's own noise floor. Cells land in ~/bench/k-<knob>/P<N>.jsonl.
# A patch whose code is behind a default-off knob is only judged by its knob-on arm; the block arms
# (PATCH-EVAL.md phase 3) ran every knob off and so measured the patches' unconditional code alone.
set -uo pipefail
IMAGE=${1:-glm53-zig:fix4}
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
defs=$(awk '/^DEFS="/{f=1} f{print} f&&/"$/{exit}' "$here/serve.sh" | tr -d '"' | sed 's/^DEFS=//')
[ -n "$defs" ] || { echo "no DEFS found in serve.sh" >&2; exit 2; }
arm() { # arm TAG [KNOB=VALUE]
  local xenv=""; [ -n "${2:-}" ] && xenv="-e $2"
  XENV="$xenv" KNOBS=off DRAFTER=1 bash "$here/bench-arm.sh" "$IMAGE" "$1"
}
arm k-base-a
for kv in $defs; do
  name=$(echo "${kv%%=*}" | sed 's/^TF_GLM_//; s/^OVN_//' | tr 'A-Z' 'a-z')
  arm "k-$name" "$kv"
done
arm k-base-b
echo "KNOB-ARMS-DONE $(date +%T)"
