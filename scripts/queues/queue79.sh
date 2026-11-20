#!/bin/bash
# queue79.sh - on spark1, detached, after queue76 and before queue77: decode screens on the final recipe N (queue79.env: IMG, WORKERS, HOURS, NEWX, the same -e list as
# queue77's N). The nsys capture of queue76 puts 75% of a four-client verify round in one kernel, tf_exl3_ovn_nc1 (the routed experts' decode GEMM), so the decode
# switches that touch it or the round around it are read first, each on ten boots in the order n x i d u | u d i x n (a symmetric order, so a drift of the box cancels):
#     n   N alone (the control; two boots)
#     x   TF_GLM_OVN_X3_NC=2   the trellis loads 2 k steps ahead instead of 1 (never measured on this stack; DEFS sets 1)
#     i   TF_GLM_INDEX_CUDA=all  decode windows' index scoring on the GPU too (earlier cells +0.7 to +2.0%, inside the boot spread)
#     d   TF_GLM_OVN_DECODE_INDEX=33  (earlier cells +0.5 to +1.5%, inside the boot spread)
#     u   TF_GLM_OVN_DRAFT_CUTS=1:0.15  the draft chain's cut at every stream count, half the recipe's 0.3: a four-client verify window holds 22 rows (5.5 a stream) at an
#         acceptance of 0.92 on code, against a stream's seven drafts at one client, so a deeper chain may buy tokens at three to four ms a row (replies cannot change)
# Greedy decode at 1, 2, 4, 6 and 8 clients (production's prompt ids, three rounds each) at the deployed shape (--parallel 4 --context 1048576; 6 and 8 clients queue),
# KNOBS=measured, one image. decide79.py (the rule, written before the rows) turns a candidate that wins into an addition to queue77.env and queue78.env.
# Production is down for the campaign and stays down. QUEUE79-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue79.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
export KEEP=1
IMG=${IMG:?set IMG}
NEWX=${NEWX:-}
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE79-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-2} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q79] $(date -u +%T) start; IMG=$IMG; NEWX='$NEWX'; deadline $(date -u -d @$DEADLINE +%T)"
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
echo "[q79] $IMG ids: $(echo $ids)"
{ [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q79] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
bash prod-stop.sh || { echo "[q79] PRODUCTION DID NOT STOP"; exit 1; }
boot() { # boot LABEL XENV: the Zig serve up on :8300, 0 when it is
  local label=$1 xenv=$2; mkdir -p "$OUT/f79-boots"; stop
  IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/f79-boots/$label.log" 2>&1 && return 0
  echo "[q79] BOOT FAILED $label: $(tail -3 "$OUT/f79-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q79] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
mkdir -p "$OUT/f79-d"
arm() { # arm LABEL XENV: a boot and greedy decode at 1, 2, 4, 6 and 8 clients
  local label=$1 xenv=$2
  room || return
  boot "d79-$label" "$xenv" || return
  greedy "$OUT/f79-d/dec-$label" 1 2 4 6 8
  docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 400 > "$OUT/f79-d/r0-$label.log"
}
arm n1 "$NEWX"
arm x1 "$NEWX -e TF_GLM_OVN_X3_NC=2"
arm i1 "$NEWX -e TF_GLM_INDEX_CUDA=all"
arm d1 "$NEWX -e TF_GLM_OVN_DECODE_INDEX=33"
arm u1 "$NEWX -e TF_GLM_OVN_DRAFT_CUTS=1:0.15"
arm u2 "$NEWX -e TF_GLM_OVN_DRAFT_CUTS=1:0.15"
arm d2 "$NEWX -e TF_GLM_OVN_DECODE_INDEX=33"
arm i2 "$NEWX -e TF_GLM_INDEX_CUDA=all"
arm x2 "$NEWX -e TF_GLM_OVN_X3_NC=2"
arm n2 "$NEWX"
exit 0
