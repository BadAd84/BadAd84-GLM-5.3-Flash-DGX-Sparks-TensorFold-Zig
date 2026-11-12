#!/bin/bash
# dist-image.sh TAG - on spark1: copy glm53-zig:TAG to spark2 and spark3 (docker save | ssh docker load, both at once),
# then check the image ids agree on all three. Logs: ~/dist-TAG.log.
set -u
T=${1:?tag}; IMG=glm53-zig:$T; LOG=$HOME/dist-$T.log
: > "$LOG"
for h in spark2 spark3; do
  ( docker save "$IMG" | ssh -o BatchMode=yes adam@$h.ots-int.net docker load >> "$LOG" 2>&1; echo "$h load rc=$?" >> "$LOG" ) &
done
wait
for h in localhost spark2.ots-int.net spark3.ots-int.net; do
  if [ "$h" = localhost ]; then docker images --format '{{.ID}}' "$IMG" | head -1; else ssh -o BatchMode=yes adam@$h "docker images --format '{{.ID}}' $IMG | head -1"; fi
done | tr '\n' ' ' >> "$LOG"
echo "DIST-DONE $T" >> "$LOG"; tail -3 "$LOG"
