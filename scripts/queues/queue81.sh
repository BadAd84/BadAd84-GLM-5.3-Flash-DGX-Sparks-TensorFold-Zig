#!/bin/bash
# queue81.sh - on spark1, detached, after queue76: does NCCL's own tuning speed up the prompt exchanges? The nsys timeline of queue76's capture f76w (scripts/site_timeline.py)
# shows the exchange chain on the side stream saturated: at the MLA site of a 4,096-row pass the side stream's NCCL kernels run 4.3 ms of the site's 4.9 ms span (partials
# exchanges 0.5 to 1.0 ms for about 11 MB a rank, shares 0.26 to 0.49 ms for 5.6 MB, against 0.2 and 0.1 ms at the links' line rate), and the main stream waits 2.5 ms after
# its last fill for the side stream's tail (18 + 24 us a row, 9.3% of the pass). The levers are env-only (NCCL moves bytes, it does not change a sum): the recipe pins
# NCCL_MIN/MAX_NCHANNELS=4 (production's shape),
# one queue pair a connection and NCCL's default chunk and buffer sizes. Each arm is the final recipe N with request starts plus one NCCL setting, one boot: the cold first
# token at 8k / 32k / 120k (two requests, ONE seed), the growing conversation (salt c74) and greedy decode at 1 and 4 clients (prose and code); controls c1 c2 c3 between.
# queue81.env: IMG, WORKERS, HOURS, NEWX. Production is down for the campaign and stays down. QUEUE81-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue81.env
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
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE81-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-5} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q81] $(date -u +%T) start; IMG=$IMG; NEWX='$NEWX'; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
echo "[q81] $IMG ids: $(echo $ids)"
{ [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q81] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
echo "[q81] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12) $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W1" "sha256sum $G/serve.sh | cut -c1-12") $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W2" "sha256sum $G/serve.sh | cut -c1-12")"
bash prod-stop.sh || { echo "[q81] PRODUCTION DID NOT STOP"; exit 1; }
boot() { # boot LABEL XENV [P [CTX]]: the Zig serve up on :8300, 0 when it is
  local label=$1 xenv=$2 p=${3:-4} ctx=${4:-1048576}; mkdir -p "$OUT/f81-boots"; stop
  if [ "$p" = 4 ]; then IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 "$ctx" > "$OUT/f81-boots/$label.log" 2>&1
  else IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh "$p" > "$OUT/f81-boots/$label.log" 2>&1; fi && return 0
  echo "[q81] BOOT FAILED $label: $(tail -3 "$OUT/f81-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q81] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q81] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q81] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS
  local dir=$1 salt=$2 t1=$3 turns=$4 st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add 1000 --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q81] $salt turn $k FAILED"; return; }
  done
  echo "[q81] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL XENV: longctx facts row for the boot just made
  local label=$1 xenv=$2
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$IMG" "--xenv=$xenv" --out "$OUT/f81-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f81-c/$label-facts.out" 2>&1
}
mkdir -p "$OUT/f81-c"
unit() { # unit LABEL XENV [LEVELS]: a P=4 boot, the cold probe, the growing conversation and greedy decode at LEVELS clients (default 1 and 4)
  local label=$1 xenv=$2 levels=${3:-1 4}
  room || return
  boot "c81-$label" "$xenv" || return
  facts "$label" "$xenv"
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f81-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f81-c/$label-probe.out" 2>&1
  echo "[q81] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f81-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f81-c/$label" "c74" 100000 8
  greedy "$OUT/f81-c/dec-$label" $levels
  keeplog "$OUT/f81-c/r0-$label.log"
}
B="$NEWX $RSX"
# what NCCL reports about its transport (GPU Direct RDMA or not, the HCAs, channels, the tuning tables' algorithm and protocol bandwidths): one boot, rank 0's lines
if room && boot "c81-dbg" "$B -e NCCL_DEBUG=INFO -e NCCL_DEBUG_SUBSYS=INIT,NET,GRAPH,TUNING"; then
  docker logs glm53-zig-r0 2>&1 | grep -a "NCCL INFO" | head -n 700 > "$OUT/f81-c/nccl-info.txt"
  echo "[q81] $(date -u +%T) NCCL INFO captured: $(wc -l < "$OUT/f81-c/nccl-info.txt") lines; GDR: $(grep -a -c -i 'GDRDMA\|GPU Direct RDMA Enabled' "$OUT/f81-c/nccl-info.txt")"
fi
unit c1 "$B" "1 2 4 6 8"
# the decode wire's ceiling: gathers up to TF_TP_MAILBOX_MAX_KB (default 256 KiB a rank) ride fabric/tp's RoCE, larger ones NCCL's LL all-gather; a verify window of 16 rows
# or more has fp32 partials past 256 KiB (24 rows 393 KB), and the nsys capture of queue76 shows 90 NCCL all-gathers of 64 us a four-client round and almost no wire launches
unit mb "$B -e TF_TP_MAILBOX_MAX_KB=1024" "1 2 4 6 8"
unit q4 "$B -e NCCL_IB_QPS_PER_CONNECTION=4"
unit n8 "$B -e NCCL_MIN_NCHANNELS=8 -e NCCL_MAX_NCHANNELS=8"
unit ch "$B -e NCCL_P2P_NET_CHUNKSIZE=524288"
unit c2 "$B"
unit bf "$B -e NCCL_BUFFSIZE=16777216"
unit qn "$B -e NCCL_IB_QPS_PER_CONNECTION=4 -e NCCL_MIN_NCHANNELS=8 -e NCCL_MAX_NCHANNELS=8"
unit n2 "$B -e NCCL_MIN_NCHANNELS=2 -e NCCL_MAX_NCHANNELS=2"
unit c3 "$B" "1 2 4 6 8"
exit 0
