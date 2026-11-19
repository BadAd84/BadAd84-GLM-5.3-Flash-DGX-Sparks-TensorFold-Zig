#!/bin/bash
# queue75.sh - on spark1, detached: the rest of queue74's plan, in a better order. queue74's C1 (f1 rs1 rs2 f2) ran; its disk tier block refused to start for want of
# disk (164 GiB free against the 128 GiB store plus 40 GiB kept free; the docker build cache was pruned since) and its candidate arms were stopped after one boot,
# so this queue runs the disk tier first. KNOBS=measured, TF_GLM_REQUEST_STARTS=1 on every arm (the control is rs, the request-starts recipe), one image
# (queue75.env: IMG, the same glm53-zig:v129za). Production is down for the campaign and stays down (prod-stop.sh is safe when it is). Every block starts only
# while the deadline allows. QUEUE75-DONE.
#  E  the disk tier with request starts (patches/learn-starts' and patches/disk-any-position's GPU check): scripts/queue-disk-tier.sh f75, every resumed reply
#     against a cold server's, after an eviction, a SIGKILL and a clean restart.
#  B  warm turns against the exchanges' row pieces: a growing conversation (longctx.py chain, a 100k first turn and seven turns of about 1,300 new rows, the
#     salt c74 of queue74, so every arm's turns are the same prompts and the replies must be the same digests) and greedy decode at 1, 2 and 4 clients.
#     A warm turn is a chunk of about 1,300 rows and the pieces are cut on 128-row boundaries, so 8 pieces make 256-row pieces there against 512-row pieces in a
#     4,096-row solo step. Arms w1 w2 w3 w6 (TF_GLM_OVERLAP_PIECES=1 / 2 / 3 / 6) and nr (TF_GLM_ROCE_MULTI=0).
#  A  prompt-pass candidates against the request-starts recipe: cold first token at 8k / 32k / 120k twice with ONE seed on every boot (the same digests in every
#     arm), the chain and greedy decode as in B:
#       mw   TF_GLM_OVN_MM_WIDE=1            sp   TF_GLM_OVN_SIDE_PRIO=1
#       p4   TF_GLM_OVERLAP_PIECES=4         lr2  TF_GLM_OVN_LATENT_ROWS=2
#       all  the four together
#     order: mw sp p4 lr2 all rs3 all lr2 p4 sp mw rs4 (every candidate once before the middle control and once after it, the second pass reversed); queue74's
#     rs1 and rs2 are the first two controls.
# Env (queue75.env beside this file): IMG, WORKERS, HOURS (the time budget from the start, default 5).
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue75.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=${IMG:?set IMG}
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE75-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-5} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q75] $(date -u +%T) start; IMG=$IMG; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
echo "[q75] $IMG ids: $(echo $ids)"
{ [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q75] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
echo "[q75] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12) $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W1" "sha256sum $G/serve.sh | cut -c1-12") $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W2" "sha256sum $G/serve.sh | cut -c1-12")"
bash prod-stop.sh || { echo "[q75] PRODUCTION DID NOT STOP"; exit 1; }
boot() { # boot LABEL XENV: the Zig serve up on :8300, 0 when it is
  local label=$1 xenv=$2; mkdir -p "$OUT/f75-boots"; stop
  IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/f75-boots/$label.log" 2>&1 && return 0
  echo "[q75] BOOT FAILED $label: $(tail -3 "$OUT/f75-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q75] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
chain() { # chain DIR SALT T1 TURNS
  local dir=$1 salt=$2 t1=$3 turns=$4 st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add 1000 --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q75] $salt turn $k FAILED"; return; }
  done
  echo "[q75] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL XENV: longctx facts row for the boot just made
  local label=$1 xenv=$2
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$IMG" "--xenv=$xenv" --out "$OUT/f75-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f75-c/$label-facts.out" 2>&1
}
mkdir -p "$OUT/f75-c"
RS="-e TF_GLM_REQUEST_STARTS=1"
arm() { # arm LABEL XENV COLD: a boot, its facts, the cold probe when COLD is "cold", the chain (the salt c74) and greedy decode at 1, 2 and 4 clients
  local label=$1 xenv="$RS $2" cold=${3:-}
  room || return
  boot "c75-$label" "$xenv" || return
  facts "$label" "$xenv"
  if [ "$cold" = cold ]; then
    python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f75-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f75-c/$label-probe.out" 2>&1
    echo "[q75] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f75-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  fi
  chain "$OUT/f75-c/$label" "c74" 100000 8
  greedy "$OUT/f75-c/dec-$label" 1 2 4
  keeplog "$OUT/f75-c/r0-$label.log"
}
ALL="-e TF_GLM_OVN_MM_WIDE=1 -e TF_GLM_OVN_SIDE_PRIO=1 -e TF_GLM_OVERLAP_PIECES=4 -e TF_GLM_OVN_LATENT_ROWS=2"

# E: the disk tier with request starts
if room; then
  stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1
  IMAGE=$IMG KNOBS=measured XENV_KNOBS="$RS" RESTORE=0 bash queue-disk-tier.sh f75 > "$OUT/f75-disktier.log" 2>&1
  echo "[q75] $(date -u +%T) disk tier rc=$? $(tail -2 "$OUT/f75-disktier.log" | tr '\n' ' ' | cut -c1-200)"
fi

# B: warm turns against the exchanges' row pieces
arm w1 "-e TF_GLM_OVERLAP_PIECES=1"
arm w2 "-e TF_GLM_OVERLAP_PIECES=2"
arm w3 "-e TF_GLM_OVERLAP_PIECES=3"
arm w6 "-e TF_GLM_OVERLAP_PIECES=6"
arm nr "-e TF_GLM_ROCE_MULTI=0"

# A: the prompt-pass candidates
arm mw "-e TF_GLM_OVN_MM_WIDE=1" cold
arm sp "-e TF_GLM_OVN_SIDE_PRIO=1" cold
arm p4 "-e TF_GLM_OVERLAP_PIECES=4" cold
arm lr2 "-e TF_GLM_OVN_LATENT_ROWS=2" cold
arm all "$ALL" cold
arm rs3 "" cold
arm all2 "$ALL" cold
arm lr22 "-e TF_GLM_OVN_LATENT_ROWS=2" cold
arm p42 "-e TF_GLM_OVERLAP_PIECES=4" cold
arm sp2 "-e TF_GLM_OVN_SIDE_PRIO=1" cold
arm mw2 "-e TF_GLM_OVN_MM_WIDE=1" cold
arm rs4 "" cold
exit 0
