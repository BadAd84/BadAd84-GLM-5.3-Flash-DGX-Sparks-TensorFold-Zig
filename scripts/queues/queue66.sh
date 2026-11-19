#!/bin/bash
# queue66.sh - on spark1, detached. Image glm53-zig:v129v = pin v1.2.9 + patches/engine 0001..0035 + pr1411 0001..0002 + cache-salt (stack tree 5137a5ef75ab, src sha256 3e010cb4e5e34a78).
#  0  build and copy the image beside production; production's 24 prompts one at a time while it is idle (pp66-prod1)
#  1  production stopped; tf-cuda-test glm-mm-ovn timed
#  A  --parallel 4 --context 1048576 boots: rec1 nc1 cand1 cand2 nc2 rec2 (rec = the recipe, nc = +TF_GLM_OVN_NO_COPY, cand = nc + MM_DECTILE + SWIGLU_REDUCE);
#     each boot: prose ids (prose33.json) and code ids (code_ids.json) at 1 2 4 clients, 3 waves; rec1 and cand1 also per_prompt.py over prompts24.json
#  B  fresh --parallel 6 and --parallel 8 boots (the default context), rec nc cand cand nc rec, prose and code ids at that many streams: h66-*
#  C  the disk tier window (queue-disk-tier.sh, KNOBS=measured, the series) on this image: disktier-v129v; it restores production
#  D  production's 24 prompts again (pp66-prod2). QUEUE66-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
WORKERS=${WORKERS:?set WORKERS to the ssh targets of ranks 1 and 2, space separated}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
IMG=glm53-zig:v129v
NC="-e TF_GLM_OVN_NO_COPY=1"
CAND="-e TF_GLM_OVN_NO_COPY=1 -e TF_GLM_OVN_MM_DECTILE=100000 -e TF_GLM_OVN_SWIGLU_REDUCE=1"
fin() { echo "QUEUE66-DONE $(date -u +%T)"; exit "${1:-0}"; }
restore_prod() {
  curl -sf localhost:8888/health > /dev/null 2>&1 || {
    setsid nohup bash ~/glm-v110-start.sh > "$HOME/bench/prod-restore-q66.log" 2>&1 < /dev/null &
    for i in $(seq 1 90); do curl -sf localhost:8888/health > /dev/null 2>&1 && break; sleep 10; done; }
  curl -sf localhost:8888/health > /dev/null 2>&1 && echo "[q66] $(date -u +%T) production healthy" || echo "[q66] PRODUCTION NOT HEALTHY"
}
[ "$(sha256sum v129v/src.tar | cut -c1-16)" = 3e010cb4e5e34a78 ] || { echo "[q66] src.tar is not the packed stack"; fin 1; }
echo "[q66] $(date -u +%T) build start"
bash build-image.sh v129v v129v/src.tar > v129v/build.out 2>&1; echo "[q66] $(date -u +%T) build rc=$?"
docker image inspect "$IMG" > /dev/null 2>&1 || { echo "[q66] NO IMAGE: $(tail -3 v129v/build.out | cut -c1-200)"; fin 1; }
bash dist-image.sh v129v > v129v/dist.out 2>&1; echo "[q66] $(date -u +%T) dist rc=$?"
a=$(docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1)
b=$(ssh -n -o BatchMode=yes -o ConnectTimeout=15 $W1 "docker images --no-trunc --format '{{.ID}}' $IMG | head -1")
c=$(ssh -n -o BatchMode=yes -o ConnectTimeout=15 $W2 "docker images --no-trunc --format '{{.ID}}' $IMG | head -1")
echo "[q66] image ids: ${a:7:12} ${b:7:12} ${c:7:12}; label $(docker image inspect "$IMG" --format '{{index .Config.Labels "glm53-zig.src-sha256"}}')"
[ -n "$a" ] && [ "$a" = "$b" ] && [ "$a" = "$c" ] || { echo "[q66] THE IMAGE IS NOT THE SAME ON THE THREE RANKS"; fin 1; }
mkdir -p "$HOME/bench/pp66-prod1"
python3 per_prompt.py 8888 --ids prompts24.json --out "$HOME/bench/pp66-prod1/rows.jsonl" > "$HOME/bench/pp66-prod1/run.out" 2>&1; echo "[q66] $(date -u +%T) production prompts rc=$? rows $(wc -l < "$HOME/bench/pp66-prod1/rows.jsonl")"
docker rm -f glm53-flash-tf samplers pwcap > /dev/null 2>&1; echo "[q66] $(date -u +%T) production stopped"
mkdir -p "$G/gpuchk"; t0=$(date +%s.%N)
timeout -k 30 2400 docker run --rm --gpus all --ipc=host --network host --shm-size 16g --cap-add IPC_LOCK --ulimit memlock=-1 \
  --entrypoint /opt/tensorfold/bin/tf-cuda-test "$IMG" glm-mm-ovn > "$G/gpuchk/glm-mm-ovn-v129v.log" 2>&1; rc=$?; t1=$(date +%s.%N)
echo "[q66] glm-mm-ovn rc=$rc in $(python3 -c "print(round($t1-$t0,2))") s, container start included; PASS=$(grep -c '^PASS' "$G/gpuchk/glm-mm-ovn-v129v.log") FAIL=$(grep -c '^FAIL' "$G/gpuchk/glm-mm-ovn-v129v.log")"
measure() { # measure TAG PORT LEVELS
  local tag=$1 port=$2 OUT="$HOME/bench/$1"; shift 2
  for N in "$@"; do
    python3 streams_ids.py "$port" "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$OUT/P$N.jsonl" > "$OUT/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py "$port" "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$OUT/C$N.jsonl" > "$OUT/C$N.out" 2>&1; local r2=$?
    echo "[q66] $(date -u +%T) $tag $N streams prose rc=$r1 $(tail -1 "$OUT/P$N.out" | grep -o '"agg_tok_s": [0-9.]*') code rc=$r2 $(tail -1 "$OUT/C$N.out" | grep -o '"agg_tok_s": [0-9.]*')"
  done
}
armA() { # armA TAG XENV [pp]
  local tag=$1 xenv=$2 OUT="$HOME/bench/$1"; mkdir -p "$OUT"
  if IMAGE=$IMG KNOBS=measured CTX=1048576 XENV="$xenv" bash zig-tp3.sh 4 > "$OUT/boot.log" 2>&1; then
    docker inspect glm53-zig-r0 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep "NO_COPY\|MM_DECTILE\|SWIGLU_REDUCE" | sort | tr '\n' ' ' > "$OUT/knobs.txt"
    measure "$tag" 8300 1 2 4
    if [ -n "${3:-}" ]; then python3 per_prompt.py 8300 --ids prompts24.json --out "$OUT/pp.jsonl" > "$OUT/pp.out" 2>&1; echo "[q66] $(date -u +%T) $tag prompts rc=$?"; fi
  else echo "[q66] BOOT FAILED $tag"; fi
  bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10
}
armA a66-rec1 "" pp; armA a66-nc1 "$NC"; armA a66-cand1 "$CAND" pp; armA a66-cand2 "$CAND"; armA a66-nc2 "$NC"; armA a66-rec2 ""
armB() { # armB TAG XENV: a fresh boot at 6 and one at 8 streams
  local tag=$1 xenv=$2
  for N in 6 8; do
    local OUT="$HOME/bench/$tag"; mkdir -p "$OUT"
    if IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh "$N" > "$OUT/boot-P$N.log" 2>&1; then measure "$tag" 8300 "$N"; else echo "[q66] BOOT FAILED $tag P=$N"; fi
    bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10
  done
}
armB h66-rec1 ""; armB h66-nc1 "$NC"; armB h66-cand1 "$CAND"; armB h66-cand2 "$CAND"; armB h66-nc2 "$NC"; armB h66-rec2 ""
docker rm -f glm53-zig-r0 > /dev/null 2>&1
IMAGE=$IMG KNOBS=measured XENV_KNOBS='' bash queue-disk-tier.sh v129v > q66-disktier.log 2>&1; echo "[q66] $(date -u +%T) disk tier rc=$? $(grep -c . "$HOME/bench/disktier-v129v/rows.jsonl" 2>/dev/null) rows"
restore_prod
mkdir -p "$HOME/bench/pp66-prod2"
python3 per_prompt.py 8888 --ids prompts24.json --out "$HOME/bench/pp66-prod2/rows.jsonl" > "$HOME/bench/pp66-prod2/run.out" 2>&1; echo "[q66] $(date -u +%T) production prompts again rc=$? rows $(wc -l < "$HOME/bench/pp66-prod2/rows.jsonl")"
fin 0
