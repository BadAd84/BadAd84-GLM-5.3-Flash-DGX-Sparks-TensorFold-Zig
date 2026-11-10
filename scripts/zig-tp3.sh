#!/usr/bin/env bash
# zig-tp3.sh P [CTX] - boot the recipe's Zig GLM TP=3 on spark1-3, run from spark1 (the head).
# Rank order matches production's GLM_WORKERS (r0 spark1 local, r1 spark2, r2 spark3).
# serve.sh carries the model path, the drafter and the production-shaped NCCL env; this driver
# only names the ranks, the bootstrap address and the box each rank lands on.
# Env: IMAGE (default glm53-zig:9c9bf54), KNOBS (off|measured|all), DRAFTER (1|0),
#      COMM_ID (default 192.168.99.11:29561), PORT (default 8300), XENV, XSERVE extras.
# Bring-up only: production must be STOPPED first (glm-v110-stop.sh) and the GLM watchdogs paused,
# because a TP=3 boot occupies all three boxes' GPUs.
set -euo pipefail
P=${1:?usage: zig-tp3.sh P [CTX]}; CTX=${2:-${CTX:-}}
[[ -n "$CTX" ]] || { case $P in 1) CTX=1048576 ;; 8) CTX=196608 ;; *) CTX=262144 ;; esac; }
IMAGE=${IMAGE:-glm53-zig:9c9bf54}
COMM_ID=${COMM_ID:-192.168.99.11:29561}
SNAP_HOST="$HOME/.cache/huggingface/hub/models--Mia-AiLab--GLM-5.3-Flash-EXL3-4bpw-TensorFold/snapshots/078455ffe6472f9a52fbc1139f58b9db2881b25c"
[ -d "$SNAP_HOST" ] || { echo "weights snapshot missing: $SNAP_HOST" >&2; exit 3; }

boot() { # boot RANK - rank 0 runs locally, workers over ssh (spark1 has keys to its workers)
  local rank=$1
  local envstr="IMAGE='$IMAGE' XENV='${XENV:-}' XSERVE='${XSERVE:-}' KNOBS='${KNOBS:-off}' DRAFTER='${DRAFTER:-1}' KEEP='${KEEP:-0}' COMM_ID='$COMM_ID' PORT='${PORT:-8300}'"
  if [ "$rank" = 0 ]; then
    nohup bash -c "$envstr bash "$(dirname "${BASH_SOURCE[0]}")/serve.sh" $rank $P $CTX" \
      > "$HOME/glm-zig-r0-$(date +%H%M%S).log" 2>&1 < /dev/null &
  else
    nohup ssh -n "adam@spark$((rank + 1)).ots-int.net" "$envstr bash ~/work/glm53-zig/serve.sh $rank $P $CTX" \
      > "$HOME/glm-zig-r$rank-$(date +%H%M%S).log" 2>&1 < /dev/null &
  fi
}
echo "[zig-tp3] $(date -Is) $IMAGE P=$P ctx=$CTX knobs=${KNOBS:-off} drafter=${DRAFTER:-1} comm=$COMM_ID"
docker rm -f glm53-zig-r0 >/dev/null 2>&1 || true
boot 0
for rank in 1 2; do
  ssh -n "adam@spark$((rank + 1)).ots-int.net" 'docker rm -f glm53-zig-r1 glm53-zig-r2 >/dev/null 2>&1 || true'
  boot $rank
done
t0=$(date +%s); deadline=1200
while :; do
  if curl -sf "http://127.0.0.1:${PORT:-8300}/v1/models" >/dev/null 2>&1; then
    echo "[zig-tp3] up in $(( $(date +%s) - t0 )) s"; exit 0
  fi
  elapsed=$(( $(date +%s) - t0 ))
  if ! docker inspect glm53-zig-r0 >/dev/null 2>&1; then
    if [ "$elapsed" -gt 60 ]; then
      echo "[zig-tp3] rank 0 never created its container (${elapsed}s)"
      tail -30 "$(ls -t "$HOME"/glm-zig-r0-*.log 2>/dev/null | head -1)" 2>/dev/null || true
      exit 1
    fi
  else
    running=$(docker inspect -f '{{.State.Running}}' glm53-zig-r0 2>/dev/null | tr -d '[:space:]')
    if [ "$running" = false ]; then
      echo "[zig-tp3] rank 0 container exited (${elapsed}s)"
      docker logs --tail 40 glm53-zig-r0 2>&1 || true
      exit 1
    fi
  fi
  if [ "$elapsed" -ge "$deadline" ]; then
    echo "[zig-tp3] TIMED OUT after ${elapsed}s"
    docker logs --tail 40 glm53-zig-r0 2>&1 || true
    exit 1
  fi
  sleep 5
done
