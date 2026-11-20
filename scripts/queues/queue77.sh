#!/bin/bash
# queue77.sh - on spark1, detached, after queue76: the final confirmation of the recipe at production's deployed shape (--parallel 4 --context 1048576, and
# 6 and 8 clients on fresh --parallel 6 and 8 boots), one image (queue77.env: IMG, the same glm53-zig:v129za), KNOBS=measured. Production is down for the
# campaign and stays down (prod-stop.sh is safe when it is). Every block starts only while the deadline allows. QUEUE77-DONE.
#   P  the recipe as committed (DEFS in serve.sh, no extra switch)
#   N  P plus the switches queue75 block A and queue76 settled (queue77.env: NEWX, the -e list), no request starts
#   R  N plus TF_GLM_REQUEST_STARTS=1 (the owner's trade: a cold prompt costs a little, a warm turn and a resume much less)
#  A  boots P N N P at --parallel 4: cold first token at 8k / 32k / 120k twice with ONE seed on every boot, a growing conversation (longctx.py chain, a 100k
#     first turn and seven turns of about 1,300 rows, the salt c74), greedy decode at 1, 2 and 4 clients, sampled decode at 1, 2 and 4 (production's agent
#     sampling) and the 24 prompts one at a time. Replies must be the same digests in every boot.
#  R  boots R1 R2 with the same content as A (the request-starts recipe against the same controls).
#  B  fresh --parallel 6 and --parallel 8 boots, P N N P each: greedy and sampled prose and code at that many clients.
#  E  the disk tier with N and request starts (scripts/queue-disk-tier.sh f77, the harness that clears the states a turn really resumes from): every
#     resumed reply against a cold server's, after a live eviction, a SIGKILL and a clean restart.
# Env (queue77.env beside this file): IMG, WORKERS, HOURS (the time budget from the start, default 5), NEWX.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue77.env
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
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE77-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-5} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q77] $(date -u +%T) start; IMG=$IMG; NEWX='$NEWX'; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
echo "[q77] $IMG ids: $(echo $ids)"
{ [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q77] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
echo "[q77] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12) $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W1" "sha256sum $G/serve.sh | cut -c1-12") $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W2" "sha256sum $G/serve.sh | cut -c1-12")"
bash prod-stop.sh || { echo "[q77] PRODUCTION DID NOT STOP"; exit 1; }
boot() { # boot LABEL XENV [P [CTX]]: the Zig serve up on :8300, 0 when it is
  local label=$1 xenv=$2 p=${3:-4} ctx=${4:-1048576}; mkdir -p "$OUT/f77-boots"; stop
  if [ "$p" = 4 ]; then IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 "$ctx" > "$OUT/f77-boots/$label.log" 2>&1
  else IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh "$p" > "$OUT/f77-boots/$label.log" 2>&1; fi && return 0
  echo "[q77] BOOT FAILED $label: $(tail -3 "$OUT/f77-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q77] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q77] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q77] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS
  local dir=$1 salt=$2 t1=$3 turns=$4 st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add 1000 --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q77] $salt turn $k FAILED"; return; }
  done
  echo "[q77] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL XENV: longctx facts row for the boot just made
  local label=$1 xenv=$2
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$IMG" "--xenv=$xenv" --out "$OUT/f77-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f77-c/$label-facts.out" 2>&1
}
mkdir -p "$OUT/f77-c"
unit() { # unit LABEL XENV: a P=4 boot and everything block A measures on it
  local label=$1 xenv=$2
  room || return
  boot "c77-$label" "$xenv" || return
  facts "$label" "$xenv"
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f77-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f77-c/$label-probe.out" 2>&1
  echo "[q77] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f77-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f77-c/$label" "c74" 100000 8
  greedy "$OUT/f77-c/dec-$label" 1 2 4 6 8 # 6 and 8 clients queue on this --parallel 4 boot: production's deployed shape, the cells to set beside its own
  sampled "$OUT/f77-c/dec-$label" 1 2 4 6 8
  prompts "$OUT/f77-c/dec-$label"
  keeplog "$OUT/f77-c/r0-$label.log"
}
unitlite() { # unitlite LABEL XENV: a P=4 boot, the cold probe and the growing conversation only (a switch that touches prompt passes alone)
  local label=$1 xenv=$2
  room || return
  boot "c77-$label" "$xenv" || return
  facts "$label" "$xenv"
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f77-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f77-c/$label-probe.out" 2>&1
  echo "[q77] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f77-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f77-c/$label" "c74" 100000 8
  keeplog "$OUT/f77-c/r0-$label.log"
}

# A: P N N P, then the prompt-only variants of N, then R: R1 R2. V1 is N with MM_WIDE=2 (the 32 x 32 warp variant, byte-checked by patch 0035 like
# MM_WIDE=1) when N sets MM_WIDE=1; X1 and X2 are N with TF_GLM_PREFILL_REDUCE=ring and =gather (the split exchanges passed along the ring, and every
# rank's partials gathered whole: the same adds in the same order, never measured on this stack).
unit P1 ""
unit N1 "$NEWX"
unit N2 "$NEWX"
unit P2 ""
NEWXV="${NEWX//TF_GLM_OVN_MM_WIDE=1/TF_GLM_OVN_MM_WIDE=2}"
[ "$NEWXV" != "$NEWX" ] && unitlite V1 "$NEWXV"
unitlite X1 "$NEWX -e TF_GLM_PREFILL_REDUCE=ring"
unitlite X2 "$NEWX -e TF_GLM_PREFILL_REDUCE=gather"
NEWXY="${NEWX//TF_GLM_OVERLAP_PIECES=4/TF_GLM_OVERLAP_PIECES=8}"
[ "$NEWXY" != "$NEWX" ] && unitlite Y1 "$NEWXY"
NEWXZ="${NEWX//TF_GLM_OVERLAP_PIECES=4/TF_GLM_OVERLAP_PIECES=3}" # three pieces read -2.2% and -1.3% on one boot in queue75 block B, beside four pieces' two boots
[ "$NEWXZ" != "$NEWX" ] && unitlite Y2 "$NEWXZ"
unit R1 "$NEWX $RSX"
unit R2 "$NEWX $RSX"

# B: fresh 6 and 8 stream boots, P N N P each
for P in 6 8; do
  n=0
  for a in P: N:"$NEWX" N:"$NEWX" P:; do
    room || break
    label="${a%%:*}"; xenv="${a#*:}"; n=$((n + 1)); tag="b77-$label$n-P$P"
    boot "$tag" "$xenv" "$P" || continue
    greedy "$OUT/f77-b/$tag" "$P"; sampled "$OUT/f77-b/$tag" "$P"; keeplog "$OUT/f77-b/$tag/r0.log"
  done
done

# E: the disk tier with N and request starts
if room; then
  stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1
  IMAGE=$IMG KNOBS=measured XENV_KNOBS="$NEWX $RSX" RESTORE=0 bash queue-disk-tier.sh f77 > "$OUT/f77-disktier.log" 2>&1
  echo "[q77] $(date -u +%T) disk tier rc=$? $(tail -2 "$OUT/f77-disktier.log" | tr '\n' ' ' | cut -c1-200)"
fi
exit 0
