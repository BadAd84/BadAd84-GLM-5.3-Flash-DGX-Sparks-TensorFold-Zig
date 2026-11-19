#!/bin/bash
# queue74.sh - on spark1, detached: tonight's window. KNOBS=measured: the recipe is DEFS as committed (23 switches). One image (queue74.env: IMG):
# the stack with solo-cuts revised (a solo step spans the plan's own cut at its middle grid point; the index ring holds a solo pass's rows and one pool
# more) and patches/disk-any-position (a conversation state of any position reaches the disk). Production is down for the campaign and stays down
# (prod-stop.sh is safe when it is). Every block starts only while the deadline allows. QUEUE74-DONE.
#  S  a smoke boot of IMG that answers a chat.
#  C1 request starts against the recipe, cold first token at 8k / 32k / 120k twice with ONE seed on every boot (the same digests in every arm), a growing
#     conversation (longctx.py chain, ~113k, ONE salt so every arm's turns are the same prompts: the replies must be the same digests) and greedy decode
#     at 1, 2 and 4 clients, boots f1 rs1 rs2 f2 (A B B A): rs is TF_GLM_REQUEST_STARTS=1.
#  E  the disk tier with request starts (patches/learn-starts' and patches/disk-any-position's GPU check): scripts/queue-disk-tier.sh f74, every resumed
#     reply against a cold server's, after a SIGKILL and a clean restart.
#  C2 prompt-pass candidates against the recipe, the same measures but no chain: f2 above and f3 f4 below are the controls.
#       mw   TF_GLM_OVN_MM_WIDE=1            sp   TF_GLM_OVN_SIDE_PRIO=1
#       p4   TF_GLM_OVERLAP_PIECES=4         lr2  TF_GLM_OVN_LATENT_ROWS=2
#       all  the four together
#     order: mw sp p4 lr2 all f3 all lr2 p4 sp mw f4 (every candidate once before the middle control and once after it, the second pass reversed).
# Env (queue74.env beside this file): IMG, WORKERS, HOURS (the time budget from the start, default 5).
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue74.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=${IMG:?set IMG}
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE74-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-5} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q74] $(date -u +%T) start; IMG=$IMG; deadline $(date -u -d @$DEADLINE +%T)"
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
echo "[q74] $IMG ids: $(echo $ids)"
{ [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q74] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
echo "[q74] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12) $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W1" "sha256sum $G/serve.sh | cut -c1-12") $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W2" "sha256sum $G/serve.sh | cut -c1-12")"
bash prod-stop.sh || { echo "[q74] PRODUCTION DID NOT STOP"; exit 1; }
boot() { # boot LABEL XENV [P [CTX]]: the Zig serve up on :8300, 0 when it is
  local label=$1 xenv=$2 p=${3:-4} ctx=${4:-1048576}; mkdir -p "$OUT/f74-boots"; stop
  if [ "$p" = 4 ]; then IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 "$ctx" > "$OUT/f74-boots/$label.log" 2>&1
  else IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh "$p" > "$OUT/f74-boots/$label.log" 2>&1; fi && return 0
  echo "[q74] BOOT FAILED $label: $(tail -3 "$OUT/f74-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q74] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
chain() { # chain DIR SALT T1 TURNS
  local dir=$1 salt=$2 t1=$3 turns=$4 st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add 1000 --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q74] $salt turn $k FAILED"; return; }
  done
  echo "[q74] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL XENV: longctx facts row for the boot just made
  local label=$1 xenv=$2
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$IMG" "--xenv=$xenv" --out "$OUT/f74-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f74-c/$label-facts.out" 2>&1
}
mkdir -p "$OUT/f74-c"
arm() { # arm LABEL XENV [chain [dec]]: a boot, its facts, the cold probe, then the chain and greedy decode at 1, 2 and 4 clients when asked
  local label=$1 xenv=$2 withchain=${3:-} withdec=${4:-}
  room || return
  boot "c74-$label" "$xenv" || return
  facts "$label" "$xenv"
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f74-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f74-c/$label-probe.out" 2>&1
  echo "[q74] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f74-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  [ -n "$withchain" ] && chain "$OUT/f74-c/$label" "c74" 100000 8
  [ -n "$withdec" ] && greedy "$OUT/f74-c/dec-$label" 1 2 4
  keeplog "$OUT/f74-c/r0-$label.log"
}

# S: a smoke boot that answers a chat
if room; then
  if boot smoke74 ""; then
    echo "[q74] $(date -u +%T) smoke boot ok: $(curl -s -m 120 http://127.0.0.1:8300/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"x","messages":[{"role":"user","content":"Say hello."}],"max_tokens":24,"temperature":0}' | head -c 300)"
  else echo "[q74] SMOKE BOOT FAILED: nothing else runs"; exit 1; fi
fi

# C1: request starts against the recipe
ALL="-e TF_GLM_OVN_MM_WIDE=1 -e TF_GLM_OVN_SIDE_PRIO=1 -e TF_GLM_OVERLAP_PIECES=4 -e TF_GLM_OVN_LATENT_ROWS=2"
RS="-e TF_GLM_REQUEST_STARTS=1"
arm f1 "" chain dec
arm rs1 "$RS" chain dec
arm rs2 "$RS" chain dec
arm f2 "" chain dec

# E: the disk tier with request starts
if room; then
  stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1
  IMAGE=$IMG KNOBS=measured XENV_KNOBS="$RS" RESTORE=0 bash queue-disk-tier.sh f74 > "$OUT/f74-disktier.log" 2>&1
  echo "[q74] $(date -u +%T) disk tier rc=$? $(tail -2 "$OUT/f74-disktier.log" | tr '\n' ' ' | cut -c1-200)"
fi

# C2: the prompt-pass candidates
arm mw "-e TF_GLM_OVN_MM_WIDE=1" "" dec
arm sp "-e TF_GLM_OVN_SIDE_PRIO=1" "" dec
arm p4 "-e TF_GLM_OVERLAP_PIECES=4" "" dec
arm lr2 "-e TF_GLM_OVN_LATENT_ROWS=2" "" dec
arm all "$ALL" "" dec
arm f3 "" "" dec
arm all2 "$ALL" "" dec
arm lr22 "-e TF_GLM_OVN_LATENT_ROWS=2" "" dec
arm p42 "-e TF_GLM_OVERLAP_PIECES=4" "" dec
arm sp2 "-e TF_GLM_OVN_SIDE_PRIO=1" "" dec
arm mw2 "-e TF_GLM_OVN_MM_WIDE=1" "" dec
arm f4 "" "" dec
exit 0
