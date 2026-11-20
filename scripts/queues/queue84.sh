#!/bin/bash
# queue84.sh - on spark1, detached, after queue82 and before queue79: the row-piece count of a prompt chunk (TF_GLM_OVERLAP_PIECES, 4 in N) with patch 0038's switches on. The timeline
# model (scripts/site_model.py) puts the tail of a site at the last piece's exchange, glue and share, so more and smaller pieces shorten it (6 equal-ish pieces read 0.74 ms a KDA
# site under the next block's front per piece); before 0038 row pieces 1, 2, 3 and 6 moved a warm turn by at most 1.4%. Arms are N' (the recipe with the switches decide83.py adopted,
# in queue84.env's NEWX, which the chain copies from queue79.env) plus request starts at 4, 6 and 8 pieces, one boot each, in the order k4a k6a k8a k8b k6b k4b. Each: the cold first
# token at 8k / 32k / 120k (two requests, ONE seed), the growing conversation (salt c74) and greedy decode at 1 and 4 clients. Replies must be one digest across the boots (row pieces
# never change a bit). Score: score81.py DIR --arms k4a,k6a,k8a,k8b,k6b,k4b --controls k4a,k4b. Then, to size two switches that change numerics (so they need the owner, and their replies are
# expected to differ from the controls'): kca (TF_GLM_OVN_KDA_CHUNKED=1: prompt chunks' KDA chain on production's chunked WY kernel) and kva (TF_GLM_OVN_KVB8=1: kv_b read as E4M3), one boot each.
# queue84.env: IMG, WORKERS, HOURS, NEWX. Production is down for the campaign and stays down. QUEUE84-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue84.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=${IMG:?set IMG}
NEWX=${NEWX:-}
RSX="-e TF_GLM_REQUEST_STARTS=1"
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE84-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-5} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q84] $(date -u +%T) start; IMG=$IMG; NEWX='$NEWX'; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
echo "[q84] $IMG ids: $(echo $ids)"
{ [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q84] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
echo "[q84] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12) $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W1" "sha256sum $G/serve.sh | cut -c1-12") $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W2" "sha256sum $G/serve.sh | cut -c1-12")"
bash prod-stop.sh || { echo "[q84] PRODUCTION DID NOT STOP"; exit 1; }
boot() { # boot LABEL XENV [P [CTX]]: the Zig serve up on :8300, 0 when it is
  local label=$1 xenv=$2 p=${3:-4} ctx=${4:-1048576}; mkdir -p "$OUT/f84-boots"; stop
  if [ "$p" = 4 ]; then IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 "$ctx" > "$OUT/f84-boots/$label.log" 2>&1
  else IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh "$p" > "$OUT/f84-boots/$label.log" 2>&1; fi && return 0
  echo "[q84] BOOT FAILED $label: $(tail -3 "$OUT/f84-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q84] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q84] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q84] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS
  local dir=$1 salt=$2 t1=$3 turns=$4 st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add 1000 --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q84] $salt turn $k FAILED"; return; }
  done
  echo "[q84] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL XENV: longctx facts row for the boot just made
  local label=$1 xenv=$2
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$IMG" "--xenv=$xenv" --out "$OUT/f84-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f84-c/$label-facts.out" 2>&1
}
mkdir -p "$OUT/f84-c"
unit() { # unit LABEL XENV [LEVELS]: a P=4 boot, the cold probe, the growing conversation and greedy decode at LEVELS clients (default 1 and 4)
  local label=$1 xenv=$2 levels=${3:-1 4}
  room || return
  boot "c84-$label" "$xenv" || return
  facts "$label" "$xenv"
  echo "[q84] $label piece-front boot lines: $(docker logs glm53-zig-r0 2>&1 | grep -a 'hand the next block' | head -1 | cut -c1-160)"
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f84-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f84-c/$label-probe.out" 2>&1
  echo "[q84] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f84-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f84-c/$label" "c74" 100000 8
  greedy "$OUT/f84-c/dec-$label" $levels
  keeplog "$OUT/f84-c/r0-$label.log"
}
B="$NEWX $RSX"
P6="${NEWX//TF_GLM_OVERLAP_PIECES=4/TF_GLM_OVERLAP_PIECES=6} $RSX"
P8="${NEWX//TF_GLM_OVERLAP_PIECES=4/TF_GLM_OVERLAP_PIECES=8} $RSX"
{ [ "$P6" != "$B" ] && [ "$P8" != "$B" ]; } || { echo "[q84] TF_GLM_OVERLAP_PIECES=4 IS NOT IN NEWX: $NEWX"; exit 1; }
unit k4a "$B" "1 4"
unit k6a "$P6" "1 4"
unit k8a "$P8" "1 4"
unit k8b "$P8" "1 4"
unit k6b "$P6" "1 4"
unit k4b "$B" "1 4"
unit kca "$B -e TF_GLM_OVN_KDA_CHUNKED=1" "1"
unit kva "$B -e TF_GLM_OVN_KVB8=1" "1"
exit 0
