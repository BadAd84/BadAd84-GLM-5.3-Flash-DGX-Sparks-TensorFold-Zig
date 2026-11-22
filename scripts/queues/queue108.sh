#!/bin/bash
# queue108.sh - the prompt-behind-decode trade at 4 and 8 streams: upstream's own controls, swept, because the millisecond fill slice never left the retired fork.
# Upstream at our pin has four controls (`lane_host_fill.zig`, `lane_host_env.zig`), none of which our recipe sets: TENSORFOLD_PREFILL_SHARE (the fraction of wall
# time prompt steps get beside decoders), TENSORFOLD_PREFILL_BUDGET (rows a visit fills before the decoders' round, 0 by default), TENSORFOLD_PREFILL_POLICY
# (stock or fcfs) and TENSORFOLD_PREFILL_TOKENS (2,048, clamped 64 to 16,384). Its own source records the trade: fcfs at 2,048 stalls decoders about 1.7 s a
# chunk (8,192: about 5.9 s) for about +13% last TTFT at 8 streams on 14,336-row prompts.
#
# Eight boots, mirrored, order c1 b512a b2048a s50a s50b b2048b b512b c2, each running upstream's tools/bench_concurrent.py at levels 4 and 8 with --mixed (the
# request set mixes prompt lengths) and three reps, into $OUT/f108-c/<label>/concurrent.json, plus one cold 8,192 request (bench_cache) so a setting that slows a
# lone prompt cannot hide. Cells: aggregate_tps and ttft_s_max per level. QUEUE108-DONE.
# queue108.env: IMG (glm53-zig:m130a), WORKERS, WAIT_FOR (default queue107.sh), HOURS.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue108.env
IMG=${IMG:?set IMG}; WORKERS=${WORKERS:?set WORKERS}; WAIT_FOR=${WAIT_FOR:-queue107.sh}
W1=${WORKERS%% *}; W2=${WORKERS##* }
OUT=$HOME/bench; R=$OUT/f108-c
B512="-e TENSORFOLD_PREFILL_BUDGET=512"
B2048="-e TENSORFOLD_PREFILL_BUDGET=2048"
S50="-e TENSORFOLD_PREFILL_SHARE=0.5"
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE108-DONE $(date -u +%T)"; }
echo "[q108] $(date -u +%T) start; waiting for $WAIT_FOR"
while pgrep -f "$WAIT_FOR" > /dev/null; do sleep 60; done
trap finish EXIT
mkdir -p "$R" "$OUT/f108-boots"
flag() { echo "[q108] $*" > "$R/ABORT"; echo "[q108] $*"; }
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then flag "IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS: nothing measured"; exit 1; fi
echo "[q108] $IMG ids: $(echo $ids | cut -c1-80); serve.sh $(sha256sum serve.sh | cut -c1-12); env $(cat env/prod.env env/dev.env | sha256sum | cut -c1-12)"
bash prod-stop.sh || { flag "PRODUCTION DID NOT STOP"; exit 1; }
unit() { # unit LABEL XENV: one fresh boot, the mixed probe at 4 and 8 streams, and one cold 8,192 request
  local label=$1 xenv=$2 dir="$R/$1"
  stop
  IMAGE=$IMG KNOBS=prod XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/f108-boots/$label.log" 2>&1 \
    || { flag "BOOT FAILED $label: $(tail -3 "$OUT/f108-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1; }
  mkdir -p "$dir"
  python3 "$G/tools-up/tools/bench_concurrent.py" http://127.0.0.1:8300 "$MODEL" --levels 4,8 --tokens 256 --reps 3 --mixed \
    --label "$label" --output "$dir/concurrent.json" > "$dir/concurrent.out" 2>&1; local r1=$?
  python3 "$G/tools-up/tools/bench_cache.py" http://127.0.0.1:8300 "$MODEL" 8192 --require-cold \
    --output "$dir/cache-8192.json" > "$dir/cache-8192.out" 2>&1; local r2=$?
  echo "[q108] $(date -u +%T) $label: concurrent rc=$r1 $(grep -o '"aggregate_tps": [0-9.]*' "$dir/concurrent.out" 2>/dev/null | tr '\n' ' ') | cold 8k rc=$r2"
}
for arm in "c1|" "b512a|$B512" "b2048a|$B2048" "s50a|$S50" "s50b|$S50" "b2048b|$B2048" "b512b|$B512" "c2|"; do
  label=${arm%%|*}; xenv=${arm#*|}
  unit "$label" "$xenv" || { echo "[q108] stopping at $label; the rows so far are kept"; exit 1; }
done
echo "[q108] $(date -u +%T) done; score with: python scripts/queue-scores/score108.py --q108 ~/bench/f108-c"
