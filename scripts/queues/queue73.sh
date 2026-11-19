#!/bin/bash
# queue73.sh - on spark1, detached: tonight's window. KNOBS=measured: the recipe is DEFS as committed (23 switches); R is the recipe before 2026-11-19
# (the seven new switches turned off by overrides), F the recipe. Images (queue73.env): IMG the main one (stack + learn-starts + solo-cuts + the latent
# rows and side priority patches, both off by default), IMGW the one without solo-cuts and the two (stack + learn-starts). Production is stopped at the start
# (prod-stop.sh) and stays down: it is not needed until the speed parity campaign ends. Every block starts only while the deadline allows. QUEUE73-DONE.
#  E  on IMGW: the disk tier with TF_GLM_REQUEST_STARTS=1 (patches/learn-starts' GPU check): scripts/queue-disk-tier.sh f73, every resumed reply
#     against a cold server's, after a SIGKILL and a clean restart.
#  S  on IMG: the glm-latent-rows GPU check (six PASS lines expected) and a smoke boot; a failed smoke boot sends the rest to IMGW, IMG-only arms skipped.
#  A  the final set against the old recipe at production's deployed shape (--parallel 4 --context 1048576), boots R F F R: greedy 1 2 4, sampled
#     1 2 4 (production's agent sampling) and the 24 prompts one at a time; replies compared across the four boots.
#  C  prompt-pass arms, cold first token at 8k / 32k / 120k twice with ONE seed on every boot (replies must be the same digests in every arm):
#       f1 f2        the recipe (8 row pieces under solo with the wire)
#       p2 p3 p4 p6  TF_GLM_OVERLAP_PIECES (production runs 2)
#       nr           TF_GLM_ROCE_MULTI=0 (pieces default 3)
#       mw           TF_GLM_OVN_MM_WIDE=1 (the prompt linears' 128 x 128 blocks; bit-exact by patch 0035's check, last measured neutral at +-1.4%)
#       sp           TF_GLM_OVN_SIDE_PRIO=1 (the exchanges' side stream at the highest priority without a pair); also greedy decode at 1, 2 and 4 clients
#       rs rs0 rsnp  TF_GLM_REQUEST_STARTS=1 on IMG (solo between starts), on IMGW (no solo with a start), and on IMG with TF_GLM_OVN_ONEPASS_PIPE=0;
#                    f1, rs and rs0 also run a growing conversation (longctx.py chain, ~113k)
#       lr2 lr4      TF_GLM_OVN_LATENT_ROWS=2 / 4 on IMG, only when block S glm-latent-rows check printed its six PASS lines; also greedy decode at 1, 2 and 4 clients
#  B  fresh --parallel 6 and --parallel 8 boots, R F F R each: greedy and sampled prose and code at that many clients.
# Env (queue73.env beside this file): IMG, IMGW, WORKERS, HOURS (the time budget from the start, default 5).
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue73.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=${IMG:?set IMG}; IMGW=${IMGW:?set IMGW}; LATOK=0; NEWIMG=1
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench
ROLD="-e TF_GLM_OVN_NO_COPY=0 -e TF_GLM_OVN_MM_DECTILE=0 -e TF_GLM_OVN_SWIGLU_REDUCE=0 -e TF_GLM_OVN_ONEPASS_PIPE=0 -e TF_GLM_CHUNK_SOLO=2048 -e TF_GLM_OVN_HOST_ONCE=0 -e TF_GLM_OVN_DRAFT_NOISE=0"
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE73-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-5} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q73] $(date -u +%T) start; IMG=$IMG; deadline $(date -u -d @$DEADLINE +%T)"
bad=0
for im in $IMG $IMGW; do
  ids=$( { docker images --no-trunc --format '{{.ID}}' "$im" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $im | head -1"; done; } )
  echo "[q73] $im ids: $(echo $ids)"
  { [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q73] IMAGE $im IS NOT THE SAME ON ALL THREE RANKS"; bad=1; }
done
[ "$bad" = 0 ] || { echo "[q73] aborting before production is touched"; exit 1; }
echo "[q73] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12) $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W1" "sha256sum $G/serve.sh | cut -c1-12") $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W2" "sha256sum $G/serve.sh | cut -c1-12")"
bash prod-stop.sh || { echo "[q73] PRODUCTION DID NOT STOP"; exit 1; }
boot() { # boot LABEL XENV [P [CTX]]: the Zig serve up on :8300, 0 when it is
  local label=$1 xenv=$2 p=${3:-4} ctx=${4:-1048576}; mkdir -p "$OUT/f73-boots"; stop
  if [ "$p" = 4 ]; then IMAGE=${BIMG:-$IMG} KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 "$ctx" > "$OUT/f73-boots/$label.log" 2>&1
  else IMAGE=${BIMG:-$IMG} KNOBS=measured XENV="$xenv" bash zig-tp3.sh "$p" > "$OUT/f73-boots/$label.log" 2>&1; fi && return 0
  echo "[q73] BOOT FAILED $label: $(tail -3 "$OUT/f73-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q73] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q73] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q73] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS
  local dir=$1 salt=$2 t1=$3 turns=$4 st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add 1000 --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q73] $salt turn $k FAILED"; return; }
  done
  echo "[q73] $(date -u +%T) $salt chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL XENV: longctx facts row for the boot just made
  local label=$1 xenv=$2
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "${BIMG:-$IMG}" "--xenv=$xenv" --out "$OUT/f73-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f73-c/$label-facts.out" 2>&1
}

# E: the disk tier with request starts, on the image without solo-cuts ($IMGW): learn-starts' own GPU check
if room; then
  stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1
  IMAGE=$IMGW KNOBS=measured XENV_KNOBS="-e TF_GLM_REQUEST_STARTS=1" RESTORE=0 bash queue-disk-tier.sh f73 > "$OUT/f73-disktier.log" 2>&1
  echo "[q73] $(date -u +%T) disk tier rc=$? $(tail -2 "$OUT/f73-disktier.log" | tr '\n' ' ' | cut -c1-200)"
fi

# S: the latent rows kernels' GPU check on IMG, then a smoke boot of IMG; a failed smoke boot sends the rest of the night to IMGW (solo-cuts and latent rows arms skipped)
if room; then
  docker run --rm --gpus all --entrypoint /opt/tensorfold/bin/tf-cuda-test "$IMG" glm-latent-rows > "$OUT/f73-latent-check.log" 2>&1; lrc=$?
  echo "[q73] $(date -u +%T) glm-latent-rows rc=$lrc: $(grep -c '^PASS' "$OUT/f73-latent-check.log") PASS, $(grep -c 'FAIL' "$OUT/f73-latent-check.log") FAIL lines"
  [ "$lrc" = 0 ] && [ "$(grep -c '^PASS' "$OUT/f73-latent-check.log")" = 6 ] && LATOK=1
  if boot smoke73 ""; then echo "[q73] $(date -u +%T) smoke boot of $IMG ok"; else echo "[q73] SMOKE BOOT OF $IMG FAILED: the rest runs on $IMGW"; IMG=$IMGW; NEWIMG=0; LATOK=0; fi
fi

# A: the final set against the old recipe
n=0
if room; then
  for a in R:"$ROLD" F: F: R:"$ROLD"; do
    label="${a%%:*}"; xenv="${a#*:}"; n=$((n + 1)); tag="a73-$label$n"
    boot "$tag" "$xenv" || continue
    greedy "$OUT/$tag" 1 2 4; sampled "$OUT/$tag" 1 2 4; prompts "$OUT/$tag"; keeplog "$OUT/$tag/r0.log"
  done
fi

# C: the prompt-pass arms
mkdir -p "$OUT/f73-c"
CHAIN="chain"
arm() { # arm LABEL XENV [chain [dec]]: dec also runs greedy prose and code at 1, 2 and 4 clients (the latent rows arms)
  local label=$1 xenv=$2 withchain=${3:-} withdec=${4:-}
  room || return
  boot "c73-$label" "$xenv" || return
  [ "$label" = sp ] && echo "[q73] sp boot log: $(docker logs glm53-zig-r0 2>&1 | grep -a -c 'side stream runs at the highest priority') priority line(s)"
  facts "$label" "$xenv"
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f73-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf73 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f73-c/$label-probe.out" 2>&1
  echo "[q73] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f73-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  [ -n "$withchain" ] && chain "$OUT/f73-c/$label" "c73$label" 100000 8
  [ -n "$withdec" ] && greedy "$OUT/f73-c/dec-$label" 1 2 4
  keeplog "$OUT/f73-c/r0-$label.log"
}
arm f1 "" chain
arm p2 "-e TF_GLM_OVERLAP_PIECES=2"
arm p3 "-e TF_GLM_OVERLAP_PIECES=3"
arm p4 "-e TF_GLM_OVERLAP_PIECES=4"
arm p6 "-e TF_GLM_OVERLAP_PIECES=6"
arm nr "-e TF_GLM_ROCE_MULTI=0"
arm mw "-e TF_GLM_OVN_MM_WIDE=1"
arm sp "-e TF_GLM_OVN_SIDE_PRIO=1" "" dec
[ "$NEWIMG" = 1 ] && arm rs "-e TF_GLM_REQUEST_STARTS=1" chain
BIMG=$IMGW arm rs0 "-e TF_GLM_REQUEST_STARTS=1" chain
[ "$NEWIMG" = 1 ] && arm rsnp "-e TF_GLM_REQUEST_STARTS=1 -e TF_GLM_OVN_ONEPASS_PIPE=0"
if [ "$LATOK" = 1 ]; then
  arm lr2 "-e TF_GLM_OVN_LATENT_ROWS=2" "" dec
  arm lr4 "-e TF_GLM_OVN_LATENT_ROWS=4" "" dec
fi
arm f2 ""

# B: fresh 6 and 8 stream boots
for P in 6 8; do
  n=0
  for a in R:"$ROLD" F: F: R:"$ROLD"; do
    room || break
    label="${a%%:*}"; xenv="${a#*:}"; n=$((n + 1)); tag="b73-$label$n-P$P"
    boot "$tag" "$xenv" "$P" || continue
    greedy "$OUT/$tag" "$P"; sampled "$OUT/$tag" "$P"; keeplog "$OUT/$tag/r0.log"
  done
done
exit 0
