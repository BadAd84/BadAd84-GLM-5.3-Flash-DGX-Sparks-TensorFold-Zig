#!/usr/bin/env bash
# prod-stop.sh - on spark1, inside an owner-opened window: stop production on all three ranks and return once none runs.
# Removing the head's container alone (docker rm -f glm53-flash-tf on spark1) leaves production's ranks 1 and 2 running on
# spark2 and spark3 until their NCCL timeout, about two minutes, and a Zig worker started beside one exits at once. The
# GLM watchdogs are the window opener's to stop. Restore: setsid nohup bash ~/glm-v110-start.sh. Exit 1 if a rank remains.
set -u
docker rm -f glm53-flash-tf samplers pwcap > /dev/null 2>&1
for h in spark2 spark3; do
  ssh -n -o BatchMode=yes -o ConnectTimeout=15 "adam@$h.ots-int.net" 'docker rm -f glm53-flash-tf > /dev/null 2>&1' &
done
wait
left=""
for i in $(seq 1 30); do
  left=""
  docker ps --format '{{.Names}}' | grep -qx glm53-flash-tf && left="$left spark1"
  for h in spark2 spark3; do
    ssh -n -o BatchMode=yes -o ConnectTimeout=15 "adam@$h.ots-int.net" "docker ps --format '{{.Names}}'" 2>/dev/null \
      | grep -qx glm53-flash-tf && left="$left $h"
  done
  [ -z "$left" ] && { echo "[prod-stop] $(date -u +%T) production stopped on spark1-3"; exit 0; }
  sleep 2
done
echo "[prod-stop] $(date -u +%T) production still runs on:$left"
exit 1
