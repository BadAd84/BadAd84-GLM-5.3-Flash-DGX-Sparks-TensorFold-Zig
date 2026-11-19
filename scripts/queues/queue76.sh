#!/bin/bash
# queue76.sh - on spark1, detached, after queue75: does TF_GLM_REQUEST_STARTS=1 change decode, and where the final recipe's decode round goes.
# KNOBS=measured, one image (queue76.env: IMG, the same glm53-zig:v129za). Production is down for the campaign and stays down. QUEUE76-DONE.
#  D  greedy decode at 1, 2 and 4 clients (the same prompt ids as production's cells, three rounds each) on eight fresh boots, f rs rs f f rs rs f: f is the
#     recipe, rs the recipe with TF_GLM_REQUEST_STARTS=1. queue74's four boots (f rs rs f) read the rs boots 0.4 to 1.2% under the control mean with the two
#     controls 0.6 to 1.1% apart, rounds and tokens a round equal in every cell, so the cells here settle whether that is a cost of the switch or boot-to-boot spread.
#  N  rank 0 under Nsight Systems, first because the profiles feed the next patches: through zig-tp3.sh (scripts/nsys-rank0.sh) one decode cell of 400 tokens, 4 clients
#     on code prompts and 1 client on prose, at production's shape, for the ranked per-kernel table of a decode round; then scripts/nsys-prefill.sh: a cold 8,192 and a
#     cold 32,768 prompt and three warm turns (about 1,300 rows each, request starts) of a 100k conversation, stage by stage (the recipe plus request starts).
# Env (queue76.env beside this file): IMG, WORKERS, HOURS (the time budget from the start, default 3).
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue76.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
export KEEP=1
IMG=${IMG:?set IMG}
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE76-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-3} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q76] $(date -u +%T) start; IMG=$IMG; deadline $(date -u -d @$DEADLINE +%T)"
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
echo "[q76] $IMG ids: $(echo $ids)"
{ [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q76] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
bash prod-stop.sh || { echo "[q76] PRODUCTION DID NOT STOP"; exit 1; }
boot() { # boot LABEL XENV: the Zig serve up on :8300, 0 when it is
  local label=$1 xenv=$2; mkdir -p "$OUT/f76-boots"; stop
  IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/f76-boots/$label.log" 2>&1 && return 0
  echo "[q76] BOOT FAILED $label: $(tail -3 "$OUT/f76-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q76] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
mkdir -p "$OUT/f76-d"
arm() { # arm LABEL XENV: a boot and greedy decode at 1, 2 and 4 clients
  local label=$1 xenv=$2
  room || return
  boot "d76-$label" "$xenv" || return
  greedy "$OUT/f76-d/dec-$label" 1 2 4
  docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 400 > "$OUT/f76-d/r0-$label.log"
}
RS="-e TF_GLM_REQUEST_STARTS=1"

# N: the decode round's kernels under nsys
if room; then
  mkdir -p "$OUT/f76-n"
  IMAGE=$IMG KNOBS=measured XENV="$RS" KIND=code TOKENS=400 CTX=1048576 bash nsys-rank0.sh dec4code 4 > "$OUT/f76-n/dec4code.out" 2>&1
  echo "[q76] $(date -u +%T) nsys decode 4 clients code: $(tail -3 "$OUT/f76-n/dec4code.out" | tr '\n' ' ' | cut -c1-200)"
fi
if room; then
  IMAGE=$IMG KNOBS=measured XENV="$RS" KIND=prose TOKENS=400 CTX=1048576 bash nsys-rank0.sh dec1prose 1 > "$OUT/f76-n/dec1prose.out" 2>&1
  echo "[q76] $(date -u +%T) nsys decode 1 client prose: $(tail -3 "$OUT/f76-n/dec1prose.out" | tr '\n' ' ' | cut -c1-200)"
fi
if room; then
  IMAGE=$IMG KNOBS=measured XENV="$RS" PHASES=nsys SIZES="8192 32768" WARMCHAIN=3 CTX=1048576 bash nsys-prefill.sh f76w > "$OUT/f76-n/prefill.out" 2>&1
  echo "[q76] $(date -u +%T) nsys prefill (cold 8k, 32k, three warm turns): $(tail -3 "$OUT/f76-n/prefill.out" | tr '\n' ' ' | cut -c1-200)"
fi

# D: decode with and without request starts
arm f5 ""
arm rs5 "$RS"
arm rs6 "$RS"
arm f6 ""
arm f7 ""
arm rs7 "$RS"
arm rs8 "$RS"
arm f8 ""
exit 0
