#!/bin/bash
# queue78.sh - on spark1, detached, after queue77: a screen of the registered prompt-side switches on top of the final recipe N (queue78.env: IMG, WORKERS,
# HOURS, NEWX, the same -e list as queue77's N). Each screen is one boot with the cold first token at 8k / 32k / 120k (two requests, ONE seed on every boot) and the
# growing conversation (salt c74), the instrument that read the candidates of queue75 to 0.1 to 0.3%; the screens were last read on decode cells or on a noisier cold
# probe. A control (N alone) boots first, last and after every third screen, so a screen is read against the controls around it. Replies must be the same digests.
#   switches (each bit-exact where its record says so; the value is the one that turns it on for prompt passes):
#     glue_row     TF_GLM_OVN_GLUE_ROW=128       a prompt piece of at least 128 rows glues in one kernel
#     absorb_vec   TF_GLM_OVN_ABSORB_VEC=1
#     index_sched  TF_GLM_OVN_INDEX_SCHED=1      the prompt scorer's own schedule
#     sparse_one   TF_GLM_OVN_SPARSE_ONEPASS=1
#     pools32      TF_GLM_OVN_POOLS32=1
#     index_regr   TF_GLM_OVN_INDEX_REGROUP=1    prompt launches score with the reduce-scatter head sum
#     router_warm  TF_GLM_OVN_ROUTER_WARM=2      the router kernels and the prompt-path mixer
#     pdl_early    TF_GLM_OVN_PDL_EARLY=2        decode windows' and prompt chunks' glue launches dependent-ready
#     index_cuda   TF_GLM_INDEX_CUDA=all
# Every block starts only while the deadline allows. QUEUE78-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue78.env
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
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE78-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-5} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q78] $(date -u +%T) start; IMG=$IMG; NEWX='$NEWX'; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
echo "[q78] $IMG ids: $(echo $ids)"
{ [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q78] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
echo "[q78] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12) $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W1" "sha256sum $G/serve.sh | cut -c1-12") $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W2" "sha256sum $G/serve.sh | cut -c1-12")"
bash prod-stop.sh || { echo "[q78] PRODUCTION DID NOT STOP"; exit 1; }
boot() { # boot LABEL XENV [P [CTX]]: the Zig serve up on :8300, 0 when it is
  local label=$1 xenv=$2 p=${3:-4} ctx=${4:-1048576}; mkdir -p "$OUT/f78-boots"; stop
  if [ "$p" = 4 ]; then IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 "$ctx" > "$OUT/f78-boots/$label.log" 2>&1
  else IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh "$p" > "$OUT/f78-boots/$label.log" 2>&1; fi && return 0
  echo "[q78] BOOT FAILED $label: $(tail -3 "$OUT/f78-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q78] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q78] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q78] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS
  local dir=$1 salt=$2 t1=$3 turns=$4 st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add 1000 --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q78] $salt turn $k FAILED"; return; }
  done
  echo "[q78] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL XENV: longctx facts row for the boot just made
  local label=$1 xenv=$2
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$IMG" "--xenv=$xenv" --out "$OUT/f78-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f78-c/$label-facts.out" 2>&1
}
mkdir -p "$OUT/f78-c"
unitlite() { # unitlite LABEL XENV: a P=4 boot, the cold probe and the growing conversation only (a switch that touches prompt passes alone)
  local label=$1 xenv=$2
  room || return
  boot "c77-$label" "$xenv" || return
  facts "$label" "$xenv"
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f78-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f78-c/$label-probe.out" 2>&1
  echo "[q78] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f78-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f78-c/$label" "c74" 100000 8
  keeplog "$OUT/f78-c/r0-$label.log"
}


SCREENS=(
  "glue_row:-e TF_GLM_OVN_GLUE_ROW=128"
  "absorb_vec:-e TF_GLM_OVN_ABSORB_VEC=1"
  "index_sched:-e TF_GLM_OVN_INDEX_SCHED=1"
  "sparse_one:-e TF_GLM_OVN_SPARSE_ONEPASS=1"
  "pools32:-e TF_GLM_OVN_POOLS32=1"
  "index_regr:-e TF_GLM_OVN_INDEX_REGROUP=1"
  "router_warm:-e TF_GLM_OVN_ROUTER_WARM=2"
  "pdl_early:-e TF_GLM_OVN_PDL_EARLY=2"
  "index_cuda:-e TF_GLM_INDEX_CUDA=all"
)
n=0; c=0
unitlite "C0" "$NEWX"
for s in "${SCREENS[@]}"; do
  n=$((n + 1))
  unitlite "$n-${s%%:*}" "$NEWX ${s#*:}"
  if [ $((n % 3)) = 0 ]; then c=$((c + 1)); unitlite "C$c" "$NEWX"; fi
done
exit 0
