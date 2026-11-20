#!/bin/bash
# gpu-check-tp3.sh IMG CHECK OUTDIR [XENV] - on spark1: one of tf-cuda-test's multi-rank GLM checks (glm-solo-check, glm-pair-check, glm-lanes-cover: "<ckpt> <dc.json> <rank> <world> <idfile>")
# on the three ranks, with serve.sh's NCCL environment and weight formats. Rank 0 starts first and writes NCCL's unique id under the mounted Hugging Face cache; the file is copied to the
# two workers, which then start. Every serve must be down: the check loads the checkpoint on each rank. XENV: extra "-e NAME=VALUE" words for every rank (the recipe's knobs, a switch under test).
# rc 0 when all three containers exit 0 inside LIMIT seconds (default 1500); each rank's output is OUTDIR/r<rank>.log. Env: WORKERS (two ssh targets, rank 1 then rank 2), DC_CAPACITY (rows a
# sequence holds, default 12288), NCCL_SOCKET_IFNAME (default enP7s7: the bootstrap address is that interface's).
set -u
IMG=${1:?usage: gpu-check-tp3.sh IMG CHECK OUTDIR [XENV]}; CHECK=${2:?check}; OUT=${3:?outdir}; XENV=${4:-}
WORKERS=${WORKERS:?set WORKERS}; W1=${WORKERS%% *}; W2=${WORKERS##* }
LIMIT=${LIMIT:-1500}
IF=${NCCL_SOCKET_IFNAME:-enP7s7}
ADDR=$(ip -4 -o addr show "$IF" 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)
[ -n "$ADDR" ] || { echo "[check] no IPv4 address on $IF"; exit 2; }
HF=/root/.cache/huggingface
MODEL=$HF/hub/models--Mia-AiLab--GLM-5.3-Flash-EXL3-4bpw-TensorFold/snapshots/078455ffe6472f9a52fbc1139f58b9db2881b25c
DIR=glm53-zig-check
NAME=glm53-chk
HOSTDIR=$HOME/.cache/huggingface/$DIR
SSH="ssh -n -o BatchMode=yes -o ConnectTimeout=15"
cmd() { # cmd RANK: the docker command line of one rank ($HOME is left for the box that runs it)
  echo "docker run -d --name $NAME-r$1 --gpus all --ipc=host --network host --shm-size 16g --cap-add IPC_LOCK --ulimit memlock=-1 --ulimit stack=67108864 --device /dev/infiniband" \
    "-v \$HOME/.cache/huggingface:$HF -e HF_HUB_OFFLINE=1 -e TENSORFOLD_NO_UPDATE_CHECK=1 -e TENSORFOLD_MEMORY_RESERVE_GIB=13.0 -e TF_GLM_RANK=$1 -e TF_GLM_WORLD=3" \
    "-e TF_GLM_HEAD_BITS=8 -e TF_GLM_DENSE_BITS=4 -e NCCL_COMM_ID=$ADDR:29571 -e NCCL_P2P_DISABLE=1 -e NCCL_SHM_DISABLE=1 -e NCCL_MIN_NCHANNELS=4 -e NCCL_MAX_NCHANNELS=4" \
    "-e NCCL_CROSS_NIC=1 -e NCCL_IB_SUBNET_AWARE_ROUTING=1 -e NCCL_IB_GID_INDEX=3 -e NCCL_IB_HCA=roceP2p1s0f0,roceP2p1s0f1,rocep1s0f0,rocep1s0f1 -e NCCL_SOCKET_IFNAME=$IF" \
    "$XENV --entrypoint /opt/tensorfold/bin/tf-cuda-test $IMG $CHECK $MODEL $HF/$DIR/dc.json $1 3 $HF/$DIR/id.hex"
}
clean() { docker rm -f $NAME-r0 > /dev/null 2>&1; for h in "$W1" "$W2"; do $SSH "$h" "docker rm -f $NAME-r1 $NAME-r2 > /dev/null 2>&1"; done; }
takeid() { docker exec $NAME-r0 cat "$HF/$DIR/id.hex" > "$OUT/id.hex" 2>/dev/null; [ "$(wc -c < "$OUT/id.hex")" = 256 ]; } # read inside the container: the file is root's
mkdir -p "$OUT" "$HOSTDIR"
clean
rm -f "$HOSTDIR/id.hex"
echo "{\"capacity\": ${DC_CAPACITY:-12288}}" > "$HOSTDIR/dc.json"
for h in "$W1" "$W2"; do
  $SSH "$h" "mkdir -p \$HOME/.cache/huggingface/$DIR && rm -f \$HOME/.cache/huggingface/$DIR/id.hex" || { echo "[check] $h is not reachable"; exit 2; }
  scp -q -o BatchMode=yes "$HOSTDIR/dc.json" "$h:.cache/huggingface/$DIR/dc.json" < /dev/null || { echo "[check] dc.json did not reach $h"; exit 2; }
done
t0=$(date +%s)
echo "[check] $(date -u +%T) $CHECK on $IMG, XENV='$XENV'"
eval "$(cmd 0)" > /dev/null || { echo "[check] rank 0 did not start"; exit 2; }
for _ in $(seq 1 60); do takeid && break; sleep 2; done
if ! takeid; then
  echo "[check] rank 0 wrote no unique id in 120 s: $(docker logs $NAME-r0 2>&1 | tail -3 | tr '\n' ' ' | cut -c1-300)"
  docker logs $NAME-r0 > "$OUT/r0.log" 2>&1; clean; exit 2
fi
rank=1
for h in "$W1" "$W2"; do
  scp -q -o BatchMode=yes "$OUT/id.hex" "$h:.cache/huggingface/$DIR/id.hex" < /dev/null || echo "[check] the unique id did not reach $h"
  $SSH "$h" "$(cmd $rank)" > /dev/null || echo "[check] rank $rank did not start"
  rank=$((rank + 1))
done
late=0
while [ "$(docker inspect -f '{{.State.Running}}' $NAME-r0 2>/dev/null)" = true ]; do
  if [ $(( $(date +%s) - t0 )) -gt "$LIMIT" ]; then late=1; echo "[check] still running after $LIMIT s: stopped"; break; fi
  sleep 5
done
rc0=$(docker inspect -f '{{.State.ExitCode}}' $NAME-r0 2>/dev/null); [ "$late" = 1 ] && rc0=124
docker logs $NAME-r0 > "$OUT/r0.log" 2>&1
rcs="${rc0:-none}"; rank=1
for h in "$W1" "$W2"; do
  for _ in $(seq 1 12); do [ "$late" = 1 ] && break; [ "$($SSH "$h" "docker inspect -f '{{.State.Running}}' $NAME-r$rank" 2>/dev/null)" = true ] || break; sleep 5; done
  rc=$($SSH "$h" "docker inspect -f '{{.State.Running}} {{.State.ExitCode}}' $NAME-r$rank" 2>/dev/null)
  case "$rc" in "false "*) rc=${rc#false } ;; *) rc=124 ;; esac
  $SSH "$h" "docker logs $NAME-r$rank 2>&1" > "$OUT/r$rank.log" 2>&1
  rcs="$rcs $rc"; rank=$((rank + 1))
done
clean
echo "[check] $(date -u +%T) $CHECK on $IMG: rc $rcs (ranks 0 1 2) in $(( $(date +%s) - t0 )) s; rank 0: $(grep -c '^PASS' "$OUT/r0.log") PASS, $(grep -c 'FAIL' "$OUT/r0.log") FAIL lines"
grep -a '^PASS\|FAIL\|REFUSE\|error' "$OUT/r0.log" | head -6 | cut -c1-400
[ "$rcs" = "0 0 0" ]
