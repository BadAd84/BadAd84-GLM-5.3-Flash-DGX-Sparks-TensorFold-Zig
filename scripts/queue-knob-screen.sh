#!/usr/bin/env bash
# queue-knob-screen.sh: the upstream settings this repo's serve can reach, one boot an arm, the control in the
# same directory. The image must carry the re-seated series (the settings live in upstream's table).
#   IMG=glm53-zig:reseat bash queue-knob-screen.sh
# Each arm is the dev env plus one setting; a changed reply digest rejects the arm before its numbers are read.
set -uo pipefail
IMG=${IMG:?usage: IMG=glm53-zig:TAG bash queue-knob-screen.sh}
G="$HOME/work/glm53-zig"
run() {
  tag=$1; xenv=$2
  echo "[knob $tag] $xenv at $(date +%T)"
  LEVELS="1 2 4 6 8" SPLOTS=4 CTX=1048576 KNOBS="${KNOBS:-dev}" XENV="$xenv" bash "$G/bench-arm.sh" "$IMG" "$tag"
}
run screen-ctl ""
run screen-moe1 "-e TF_GLM_MOE_DIRECT=1"
run screen-idx0 "-e TF_GLM_INDEX_SPLIT=0"
run screen-idx4096 "-e TF_GLM_INDEX_SPLIT=4096"
echo "[knob] KNOB-SCREEN-DONE at $(date +%T)"
