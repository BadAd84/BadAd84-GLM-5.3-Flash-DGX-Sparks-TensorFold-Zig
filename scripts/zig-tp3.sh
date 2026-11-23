#!/usr/bin/env bash
# zig-tp3.sh P [CTX] - boot the recipe's Zig GLM TP=3 on spark1-3, run from spark1 (the head).
# Rank order matches production's GLM_WORKERS (r0 spark1 local, r1 spark2, r2 spark3).
# serve.sh carries the model path, the drafter and the production-shaped NCCL env; this driver
# only names the ranks, the bootstrap address and the box each rank lands on.
# Env: IMAGE (default glm53-zig:9c9bf54), KNOBS (off|measured|all|prod|dev: serve.sh's environment files), DRAFTER (1|0),
#      COMM_ID (default 192.168.99.11:29561), PORT (default 8300), XENV, XSERVE extras,
#      WRAP0 / XRUN0 (rank 0 only: serve.sh's WRAP and XRUN, for profiling the head rank); WRAP1 / XRUN1 and WRAP2 / XRUN2 do the same for a worker rank.
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
  local envstr="IMAGE='$IMAGE' XENV='${XENV:-}' XSERVE='${XSERVE:-}' KNOBS='${KNOBS:-off}' DRAFTER='${DRAFTER:-1}' KEEP='${KEEP:-0}' LEARN='${LEARN:-1}' LEARN_NAME='${LEARN_NAME:-serve}' LEARN_GIB='${LEARN_GIB:-128}' LEARN_DAILY_GIB='${LEARN_DAILY_GIB:-512}' LEARN_MIN_FREE_GIB='${LEARN_MIN_FREE_GIB:-40}' COMM_ID='$COMM_ID' PORT='${PORT:-8300}'"
  if [ "$rank" = 0 ]; then
    nohup bash -c "$envstr WRAP='${WRAP0:-}' XRUN='${XRUN0:-}' bash "$(dirname "${BASH_SOURCE[0]}")/serve.sh" $rank $P $CTX" \
      > "$HOME/glm-zig-r0-$(date +%H%M%S).log" 2>&1 < /dev/null &
  else
    local wv="WRAP$rank" xv="XRUN$rank"
    nohup ssh -n "adam@spark$((rank + 1)).ots-int.net" "$envstr WRAP='${!wv:-}' XRUN='${!xv:-}' bash ~/work/glm53-zig/serve.sh $rank $P $CTX" \
      > "$HOME/glm-zig-r$rank-$(date +%H%M%S).log" 2>&1 < /dev/null &
  fi
}
echo "[zig-tp3] $(date -Is) $IMAGE P=$P ctx=$CTX knobs=${KNOBS:-off} drafter=${DRAFTER:-1} comm=$COMM_ID"
# production's ranks 1 and 2 outlive a removal of its head by about two minutes (their NCCL timeout), and a Zig worker
# started beside one exits at once: wait until no box runs production's container (prod-stop.sh stops all three)
busy=""
for i in $(seq 1 48); do
  busy=""
  if docker ps --format '{{.Names}}' | grep -qx glm53-flash-tf; then busy="$busy spark1"; fi
  for h in spark2 spark3; do
    if ssh -n -o BatchMode=yes -o ConnectTimeout=15 "adam@$h.ots-int.net" "docker ps --format '{{.Names}}'" 2>/dev/null \
      | grep -qx glm53-flash-tf; then busy="$busy $h"; fi
  done
  [ -z "$busy" ] && break
  [ "$i" = 1 ] && echo "[zig-tp3] production's container still runs on:$busy; waiting for it to exit"
  sleep 5
done
[ -n "$busy" ] && { echo "[zig-tp3] production still runs on:$busy after 240 s: stop it on every rank first (prod-stop.sh)"; exit 1; }
docker rm -f glm53-zig-r0 >/dev/null 2>&1 || true
boot 0
for rank in 1 2; do
  ssh -n "adam@spark$((rank + 1)).ots-int.net" 'docker rm -f glm53-zig-r1 glm53-zig-r2 >/dev/null 2>&1 || true'
  # the worker runs the head's copy of the recipe files, never one left there by an earlier session
  # serve.sh reads scripts/env/prod.env and dev.env beside itself, so the two files go with it
  ssh -n -o BatchMode=yes "adam@spark$((rank + 1)).ots-int.net" 'mkdir -p work/glm53-zig/env' < /dev/null
  scp -q -o BatchMode=yes "$(dirname "${BASH_SOURCE[0]}")/serve.sh" "$(dirname "${BASH_SOURCE[0]}")/config.sh" "adam@spark$((rank + 1)).ots-int.net:work/glm53-zig/" < /dev/null
  scp -q -o BatchMode=yes "$(dirname "${BASH_SOURCE[0]}")/env/prod.env" "$(dirname "${BASH_SOURCE[0]}")/env/dev.env" "adam@spark$((rank + 1)).ots-int.net:work/glm53-zig/env/" < /dev/null
  boot $rank
done
workers() { # the worker ranks' containers, for a failed boot's report
  local rank
  for rank in 1 2; do
    echo "[zig-tp3] rank $rank: $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "adam@spark$((rank + 1)).ots-int.net" \
      "docker ps -a --format '{{.Names}} {{.Status}}' | grep -x 'glm53-zig-r$rank .*' || echo 'no container'" 2>/dev/null)"
  done
}
t0=$(date +%s); deadline=1200; seen=0
while :; do
  if curl -sf "http://127.0.0.1:${PORT:-8300}/v1/models" >/dev/null 2>&1; then
    echo "[zig-tp3] up in $(( $(date +%s) - t0 )) s"; exit 0
  fi
  elapsed=$(( $(date +%s) - t0 ))
  if ! docker inspect glm53-zig-r0 >/dev/null 2>&1; then
    if [ "$seen" = 1 ]; then
      echo "[zig-tp3] rank 0's container exited after ${elapsed}s and was removed (serve.sh's --rm; KEEP=1 keeps its log)"
      workers
      exit 1
    fi
    if [ "$elapsed" -gt 60 ]; then
      echo "[zig-tp3] rank 0 never created its container (${elapsed}s)"
      tail -30 "$(ls -t "$HOME"/glm-zig-r0-*.log 2>/dev/null | head -1)" 2>/dev/null || true
      exit 1
    fi
  else
    seen=1
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
