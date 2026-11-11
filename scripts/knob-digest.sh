#!/usr/bin/env bash
# knob-digest.sh IMAGE TAG [ENVSTR] - boot P=1 with an explicit knob set (KNOBS=off plus the
# XENV list), run one prose streams cell and print its reply digest against the stock digest.
# The stock digest for this cell on the pin and on every KNOBS=off arm is 3ec88b6418f7.
set -uo pipefail
IMAGE=${1:?image}; TAG=${2:?tag}; XENV_IN=${3:-}
G="$HOME/work/glm53-zig"
IMAGE="$IMAGE" KEEP="${KEEP:-1}" KNOBS=off DRAFTER=0 XENV="$XENV_IN" bash "$G/zig-tp3.sh" 1 > "$HOME/knob-$TAG.boot.log" 2>&1
docker logs glm53-zig-r0 2>&1 | grep -q "serving GLM" || { echo "[$TAG] BOOT FAILED"; bash "$G/zig-tp3-stop.sh" >/dev/null 2>&1; exit 1; }
python3 "$G/streams.py" 8300 1 --kind prose --max-tokens 400 --rounds 1 --tag "$TAG" 2>/dev/null | grep -o '"sha": \["[a-f0-9]*"\]' | head -1 | sed "s/^/[$TAG] /"
bash "$G/zig-tp3-stop.sh" >/dev/null 2>&1
