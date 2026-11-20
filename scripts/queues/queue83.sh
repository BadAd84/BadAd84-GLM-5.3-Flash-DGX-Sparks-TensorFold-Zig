#!/bin/bash
# queue83.sh - on spark1, detached, after queue81: patch 0038's TF_GLM_OVN_PIECE_FRONT (the next KDA layer's projections piece by piece as an ffn site's rows land), _MLA (the same
# for a DSA layer's projections, norms, indexer and absorbed query) and _FFN (a MoE ffn's router and top-k pick piece by piece as a mixer site's rows land). The nsys timeline of
# queue76's capture f76w shows the main stream waiting about 2.5 ms a site for the side stream's last piece (exchange, glue, share) before the next block's first kernels; bits are
# unchanged. The image glm53-zig:$TAG is built here first from stage/src-$TAG.tar (the 45-patch stack) and copied to the workers. Arms (final recipe N plus request starts, one boot
# each), in the order ca fa ba ma mb bb fb cb: control (ca cb), the KDA front (fa fb), with the router front (ba bb), with the DSA front too (ma mb); then the pair control / all three
# with 4 NCCL channels a net peer (na ga gb nb), the setting queue81's pp arm read (-1.8 to -2.0% cold). Each: the cold first token at 8k / 32k / 120k (two requests, ONE seed), the growing conversation (salt c74)
# and greedy decode at 1 and 4 clients; the switches only act on prompt chunks, so decode is a replies check.
# queue83.env: IMG, WORKERS, HOURS, NEWX. Production is down for the campaign and stays down. QUEUE83-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue83.env
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
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE83-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-5} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q83] $(date -u +%T) start; IMG=$IMG; NEWX='$NEWX'; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
# the image: built on this box (queue81 is done, nothing else uses the GPUs or the memory bandwidth), then copied to the workers
TAG=${IMG#glm53-zig:}
if ! docker images --format '{{.ID}}' "$IMG" | grep -q .; then
  bash build-image.sh "$TAG" "stage/src-$TAG.tar" > "stage/build-$TAG.out" 2>&1 || { echo "[q83] BUILD FAILED: $(tail -3 "stage/build-$TAG.out" | tr '\n' ' ' | cut -c1-300)"; exit 1; }
  echo "[q83] $(date -u +%T) built $IMG: $(docker images --format '{{.ID}}' "$IMG" | head -1)"
  bash dist-image.sh "$TAG" > "stage/dist-$TAG.out" 2>&1
  echo "[q83] $(date -u +%T) distributed: $(tail -1 "stage/dist-$TAG.out" | cut -c1-200)"
fi
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
echo "[q83] $IMG ids: $(echo $ids)"
{ [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q83] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
echo "[q83] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12) $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W1" "sha256sum $G/serve.sh | cut -c1-12") $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W2" "sha256sum $G/serve.sh | cut -c1-12")"
bash prod-stop.sh || { echo "[q83] PRODUCTION DID NOT STOP"; exit 1; }
boot() { # boot LABEL XENV [P [CTX]]: the Zig serve up on :8300, 0 when it is
  local label=$1 xenv=$2 p=${3:-4} ctx=${4:-1048576}; mkdir -p "$OUT/f83-boots"; stop
  if [ "$p" = 4 ]; then IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 "$ctx" > "$OUT/f83-boots/$label.log" 2>&1
  else IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh "$p" > "$OUT/f83-boots/$label.log" 2>&1; fi && return 0
  echo "[q83] BOOT FAILED $label: $(tail -3 "$OUT/f83-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q83] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q83] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q83] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS
  local dir=$1 salt=$2 t1=$3 turns=$4 st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add 1000 --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q83] $salt turn $k FAILED"; return; }
  done
  echo "[q83] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL XENV: longctx facts row for the boot just made
  local label=$1 xenv=$2
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$IMG" "--xenv=$xenv" --out "$OUT/f83-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f83-c/$label-facts.out" 2>&1
}
mkdir -p "$OUT/f83-c"
unit() { # unit LABEL XENV [LEVELS]: a P=4 boot, the cold probe, the growing conversation and greedy decode at LEVELS clients (default 1 and 4)
  local label=$1 xenv=$2 levels=${3:-1 4}
  room || return
  boot "c83-$label" "$xenv" || return
  facts "$label" "$xenv"
  echo "[q83] $label piece-front boot lines: $(docker logs glm53-zig-r0 2>&1 | grep -a 'hand the next block' | head -1 | cut -c1-160)"
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f83-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f83-c/$label-probe.out" 2>&1
  echo "[q83] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f83-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f83-c/$label" "c74" 100000 8
  greedy "$OUT/f83-c/dec-$label" $levels
  keeplog "$OUT/f83-c/r0-$label.log"
}
B="$NEWX $RSX"
PF="-e TF_GLM_OVN_PIECE_FRONT=1"
PB="-e TF_GLM_OVN_PIECE_FRONT=1 -e TF_GLM_OVN_PIECE_FFN=1"
PM="-e TF_GLM_OVN_PIECE_FRONT=1 -e TF_GLM_OVN_PIECE_FFN=1 -e TF_GLM_OVN_PIECE_MLA=1"
PP="-e NCCL_NCHANNELS_PER_NET_PEER=4"
unit ca "$B" "1 4"
unit fa "$B $PF" "1 4"
unit ba "$B $PB" "1 4"
unit ma "$B $PM" "1 4"
unit mb "$B $PM" "1 4"
unit bb "$B $PB" "1 4"
unit fb "$B $PF" "1 4"
unit cb "$B" "1 4"
unit na "$B $PP" "1 4"
unit ga "$B $PP $PM" "1 4"
unit gb "$B $PP $PM" "1 4"
unit nb "$B $PP" "1 4"
exit 0
