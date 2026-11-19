#!/usr/bin/env bash
# nsys-prefill.sh TAG - where a cold prompt's time goes at production's shape (--parallel 4 --context 1048576), run on
# the head (spark1) beside zig-tp3.sh, serve.sh, longctx.py, longctx_table.py, nsys-kern.py, prefill_stages.py and
# prompt_trace.py, with production stopped (it stays down for the campaign; this script
# refuses to start otherwise and never starts production itself).
#   nsys  rank 0 under `nsys launch` through zig-tp3.sh (so it has exactly the serve's env), one warm-up cold prompt
#         of 4,096 tokens, then `nsys start`, one cold prompt of each SIZES (8,192 and 32,768 tokens, distinct text, a
#         5 s idle between), `nsys stop`; every box's GPU clock, power and temperature sampled meanwhile; the capture
#         exported (cuda_gpu_kern_sum and its sqlite) and read by prefill_stages.py.
#   prof  the same boot with TF_GLM_PROF=1 and no profiler: the warm-up, the SIZES again (other text), every rank's
#         `glm prompt` lines from its own docker log, read by prompt_trace.py (2,048-row chunks, all three ranks).
# Output: ~/nsys/pf-TAG.nsys-rep, pf-TAG.sqlite, pf-TAG_cuda_gpu_kern_sum.csv; ~/bench/pf-TAG/ (rows.jsonl, clocks-r*.csv,
# trace-r*.log, stages.txt, stages.json, kern.txt, trace.txt, provenance.txt). PREFILL-DONE closes the log.
# Env: IMAGE (glm53-zig:rs2x3), KNOBS (measured), XENV (an arm's extra -e list), P (4), CTX (1048576), SIZES
# ("8192 32768"), WARM (4096), PHASES ("nsys prof"), WORKERS (the ssh targets of ranks 1 and 2, required), WARMCHAIN (0: that many
# turns of a growing conversation are captured after the cold sizes, ~1,300 rows each, its first turn of CHAIN_T1 tokens, default
# 100000, running before the capture starts; needs TF_GLM_REQUEST_STARTS=1 in XENV to resume at the previous turn's end), and every
# command it drives as a variable (ZTP3, ZSTOP, DOCKER, SSH, PY, CURL, NVSMI, SYSTEMCTL, SLEEP) for dry runs.
set -uo pipefail
TAG=${1:?usage: nsys-prefill.sh TAG}
G=${G:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}
IMAGE=${IMAGE:-glm53-zig:rs2x3}
KNOBS=${KNOBS:-measured}
XENV=${XENV:-}
P=${P:-4}
CTX=${CTX:-1048576}
SIZES=${SIZES:-8192 32768}
WARM=${WARM:-4096}
PHASES=${PHASES:-nsys prof}
WARMCHAIN=${WARMCHAIN:-0}
CHAIN_T1=${CHAIN_T1:-100000}
ZPORT=${ZPORT:-8300}
PROD_PORT=${PROD_PORT:-8888}
NS=${NS:-$HOME/nsys}
OUT=${OUT:-$HOME/bench/pf-$TAG}
ZTP3=${ZTP3:-$G/zig-tp3.sh}
ZSTOP=${ZSTOP:-$G/zig-tp3-stop.sh}
DOCKER=${DOCKER:-docker}
SSH=${SSH:-ssh}
PY=${PY:-python3}
CURL=${CURL:-curl}
NVSMI=${NVSMI:-nvidia-smi}
SYSTEMCTL=${SYSTEMCTL:-systemctl}
SLEEP=${SLEEP:-sleep}
WORKERS=${WORKERS:?set WORKERS to the ssh targets of ranks 1 and 2, space separated}
export LONGCTX_WORKERS="${WORKERS// /,}"
LOGCMD="$DOCKER logs --since {since} glm53-zig-r0"
CLOCKS="timestamp,clocks.sm,clocks.max.sm,power.draw,temperature.gpu,utilization.gpu,clocks_event_reasons.active"

say() { echo "[prefill] $(date -u +%T) $*"; }
abort() { say "$*"; echo "PREFILL-ABORTED $(date -u +%T)"; exit 1; }

# the window's opener stops production and the watchdogs; this script never runs beside them
$CURL -sf -o /dev/null --max-time 3 "localhost:$PROD_PORT/health" && abort "production answers on :$PROD_PORT: stop it first"
$DOCKER ps --format '{{.Names}}' 2>/dev/null | grep -qx glm53-flash-tf && abort "glm53-flash-tf runs here: stop production"
for w in $WORKERS; do
  $SSH -n -o BatchMode=yes "$w" "docker ps --format '{{.Names}}'" 2>/dev/null | grep -qx glm53-flash-tf \
    && abort "glm53-flash-tf runs on $w: stop production"
done
$SYSTEMCTL is-active --quiet glm-watchdog-system.service 2>/dev/null && abort "glm-watchdog-system is active"
$SYSTEMCTL --user is-active --quiet glm-watchdog.service 2>/dev/null && abort "the user unit glm-watchdog is active"
[ -s "$OUT/rows.jsonl" ] && abort "$OUT/rows.jsonl holds rows of an earlier run: use a new TAG"
mkdir -p "$OUT" "$NS" || abort "cannot make $OUT or $NS"
ROWS=$OUT/rows.jsonl
{ sha256sum "$0" "$ZTP3" "$G/serve.sh" "$G/longctx.py" "$G/prefill_stages.py" "$G/prompt_trace.py" 2>&1
  $DOCKER image inspect --format '{{.Id}} {{.RepoTags}}' "$IMAGE" 2>&1
  echo "TAG=$TAG IMAGE=$IMAGE KNOBS=$KNOBS P=$P CTX=$CTX SIZES='$SIZES' WARM=$WARM WARMCHAIN=$WARMCHAIN CHAIN_T1=$CHAIN_T1 XENV='$XENV'"; } > "$OUT/provenance.txt"
trap '$ZSTOP > /dev/null 2>&1; say "serve stopped; production stays down"' EXIT

probe() { # probe SEED SIZE MAXTOK: one cold prompt of SIZE tokens, salted by SEED, its row in ROWS
  $PY "$G/longctx.py" probe "$ZPORT" --tag "pf-$TAG" --n "$P" --cold-sizes "$2" --reps 1 --warm-base 0 \
    --max-tokens "$3" --seed "$1" --out "$ROWS" --log-cmd "$LOGCMD" > "$OUT/probe-$1.out" 2>&1
}

chain_turn() { # chain_turn K: turn K of a growing conversation (a CHAIN_T1-token first turn, then about 1,300 new rows a turn), its row in chain.jsonl
  $PY "$G/longctx.py" chain "$ZPORT" "$OUT/chain-$TAG.json" --t1 "$CHAIN_T1" --add 1000 --salt "pfw-$TAG" --tag "pfw-$TAG" --n "$P" \
    --out "$OUT/chain.jsonl" --log-cmd "$LOGCMD" > "$OUT/chain-$1.out" 2>&1
}

boot() { # boot LABEL EXTRA_XENV: zig-tp3.sh at P, CTX; KNOBS and XENV as the arm sets them
  $ZSTOP > /dev/null 2>&1
  say "boot $1: $IMAGE P=$P ctx=$CTX knobs=$KNOBS xenv='$XENV $2'"
  IMAGE="$IMAGE" KNOBS="$KNOBS" XENV="$XENV $2" PORT="$ZPORT" bash "$ZTP3" "$P" "$CTX" > "$OUT/boot-$1.log" 2>&1 \
    || { tail -5 "$OUT/boot-$1.log"; return 1; }
  say "boot $1: $(grep -o 'up in [0-9]* s' "$OUT/boot-$1.log" | tail -1)"
}

clocks_on() { # every box's clocks, power and temperature every 250 ms into OUT/clocks-r<rank>.csv
  $NVSMI --query-gpu="$CLOCKS" --format=csv,noheader -lms 250 > "$OUT/clocks-r0.csv" 2>&1 &
  CLOCK_PIDS=$!
  local i=1 w
  for w in $WORKERS; do
    $SSH -n -o BatchMode=yes "$w" "timeout 900 nvidia-smi --query-gpu=$CLOCKS --format=csv,noheader -lms 250" \
      > "$OUT/clocks-r$i.csv" 2>&1 &
    CLOCK_PIDS="$CLOCK_PIDS $!"
    i=$((i + 1))
  done
}

clocks_off() {
  kill $CLOCK_PIDS 2> /dev/null
  local w
  for w in $WORKERS; do $SSH -n -o BatchMode=yes "$w" "pkill -f 'nvidia-smi --query-gpu=$CLOCKS'" > /dev/null 2>&1; done
  wait $CLOCK_PIDS 2> /dev/null
}

phase_nsys() {
  export WRAP0="nsys launch --session-new=pf --trace=cuda-sw" XRUN0="-v $NS:/out"
  boot nsys "" || { unset WRAP0 XRUN0; return 1; }
  unset WRAP0 XRUN0
  probe "pf-$TAG-warm" "$WARM" 16 || say "warm-up probe failed: $(tail -2 "$OUT/probe-pf-$TAG-warm.out")"
  if [ "$WARMCHAIN" -gt 0 ]; then rm -f "$OUT/chain-$TAG.json"; chain_turn 1 || say "chain turn 1 failed: $(tail -2 "$OUT/chain-1.out")"; fi
  clocks_on
  $DOCKER exec glm53-zig-r0 nsys start --session=pf --sample=none --cpuctxsw=none -o "/out/pf-$TAG" \
    --force-overwrite=true > "$OUT/nsys-start.log" 2>&1 || say "nsys start failed: $(tail -2 "$OUT/nsys-start.log")"
  local s first=1
  for s in $SIZES; do
    [ "$first" = 1 ] || $SLEEP 5
    first=0
    probe "pf-$TAG-nsys-$s" "$s" 4 || say "probe $s failed"
    say "cold $s: $(grep -o '"ttft_ms": [0-9]*' "$ROWS" | tail -1)"
  done
  local k
  for k in $(seq 2 $((WARMCHAIN + 1))); do
    $SLEEP 5
    chain_turn "$k" || say "chain turn $k failed: $(tail -2 "$OUT/chain-$k.out")"
    say "warm turn $k: $(grep -o '"ttft_ms": [0-9]*' "$OUT/chain.jsonl" | tail -1)"
  done
  $DOCKER exec glm53-zig-r0 nsys stop --session=pf > "$OUT/nsys-stop.log" 2>&1 || say "nsys stop failed"
  clocks_off
  $DOCKER logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 2000 > "$OUT/r0-nsys.log"
  $ZSTOP > /dev/null 2>&1
  $DOCKER run --rm --entrypoint nsys -v "$NS:/out" "$IMAGE" stats --report cuda_gpu_kern_sum --format csv \
    -o "/out/pf-$TAG" "/out/pf-$TAG.nsys-rep" > "$OUT/nsys-stats.log" 2>&1
  [ -s "$NS/pf-$TAG.sqlite" ] || { say "no sqlite export: $(tail -3 "$OUT/nsys-stats.log")"; return 1; }
  $PY "$G/nsys-kern.py" "$NS/pf-${TAG}_cuda_gpu_kern_sum.csv" 45 > "$OUT/kern.txt" 2>&1
  $PY "$G/prefill_stages.py" "$NS/pf-$TAG.sqlite" --json "$OUT/stages.json" --layers > "$OUT/stages.txt" 2>&1
  say "stages (rc $?): $OUT/stages.txt"
}

phase_prof() {
  boot prof "-e TF_GLM_PROF=1" || return 1
  probe "pf-$TAG-pwarm" "$WARM" 16 || say "warm-up probe failed"
  local since s i=1 w
  since=$(date +%s)
  for s in $SIZES; do
    probe "pf-$TAG-prof-$s" "$s" 4 || say "probe $s failed"
  done
  $DOCKER logs --since "$since" glm53-zig-r0 2>&1 | grep -a "glm prompt" > "$OUT/trace-r0.log"
  local logs=("$OUT/trace-r0.log")
  for w in $WORKERS; do
    $SSH -n -o BatchMode=yes "$w" "docker logs --since $since glm53-zig-r$i 2>&1 | grep -a 'glm prompt'" \
      > "$OUT/trace-r$i.log" 2>&1
    logs+=("$OUT/trace-r$i.log")
    i=$((i + 1))
  done
  $ZSTOP > /dev/null 2>&1
  $PY "$G/prompt_trace.py" "${logs[@]}" --rows 2048 --json "$OUT/trace.json" > "$OUT/trace.txt" 2>&1
  say "trace (rc $?): $OUT/trace.txt"
}

for phase in $PHASES; do
  case $phase in
    nsys) phase_nsys || say "phase nsys failed" ;;
    prof) phase_prof || say "phase prof failed" ;;
    *) say "unknown phase $phase" ;;
  esac
done
$PY "$G/longctx_table.py" "$ROWS" > "$OUT/table.md" 2>&1
[ -s "$OUT/stages.txt" ] && head -60 "$OUT/stages.txt"
[ -s "$OUT/trace.txt" ] && head -80 "$OUT/trace.txt"
echo "PREFILL-DONE $(date -u +%T)"
