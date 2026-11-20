#!/bin/bash
# queue85.sh - on spark1, detached, after queue84: where a cold prompt's time goes now. One nsys capture of rank 0 on the final recipe N' (the switches decide83.py adopted are in
# queue85.env's NEWX, copied from queue79.env by the chain), the same capture as queue76's pf-f76w (cold 8,192 and 32,768 tokens, three warm turns of a growing conversation), read by
# prefill_stages.py: the main stream's wait rows against section 54's 18.3 us a row for the partials exchange and 24.5 for the share, per layer kind. The next lever is read off it. The second
# phase of nsys-prefill.sh (TF_GLM_PROF=1, no profiler; the switches are off under it) gives every rank's own stage lines, for the skew between ranks (a wait on a slower rank cannot be scheduled away).
# queue85.env: IMG, WORKERS, NEWX. Production is down for the campaign and stays down. QUEUE85-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue85.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=${IMG:?set IMG}
NEWX=${NEWX:-}
OUT=$HOME/bench
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE85-DONE $(date -u +%T)"; }
trap finish EXIT
echo "[q85] $(date -u +%T) start; IMG=$IMG; NEWX='$NEWX'"
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
echo "[q85] $IMG ids: $(echo $ids)"
{ [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q85] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
bash prod-stop.sh || { echo "[q85] PRODUCTION DID NOT STOP"; exit 1; }
mkdir -p "$OUT/f85-n"
IMAGE=$IMG KNOBS=measured XENV="$NEWX -e TF_GLM_REQUEST_STARTS=1" PHASES="nsys prof" SIZES="8192 32768" WARMCHAIN=3 CTX=1048576 bash nsys-prefill.sh f85w > "$OUT/f85-n/prefill.out" 2>&1
echo "[q85] $(date -u +%T) nsys prefill (cold 8k, 32k, three warm turns): $(tail -3 "$OUT/f85-n/prefill.out" | tr '\n' ' ' | cut -c1-200)"
exit 0
