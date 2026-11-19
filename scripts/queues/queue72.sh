#!/bin/bash
# queue72.sh - on spark1, detached, after queue71: the measured wins on together, checked against the recipe at every level, and where
# that stands against production (owner 2026-11-18: "turn on the wins together, then benchmark and see where we are vs the old production
# python build"). Both engines at production's deployed shape: one --parallel 4 --context 1048576 serve for every level, 6 and 8 clients
# queueing as they do on production. Image glm53-zig:v129v, KNOBS=measured; the candidate is the recipe plus WINS (each measured alone
# against the recipe in OVERNIGHT sections 45 to 49 and queue71, never yet together), so DEFS changes only when z1/z0/z0b/z3 show no level
# slower. Every prompt production is sent is new to it: its prefix cache persists (section 49), so each arm has its own seeds and salts.
#  p1   production before the window, each leg only while it is idle: greedy prose and code ids at 1 2 4 6 8 clients; sampled at 1 2 4;
#       the 24 prompts one at a time; cold 8k / 32k / 120k twice; warm turns (ttft.py's method) at ~100k +2,000 and ~250k +600, idle,
#       and ~250k beside three decoding streams; two growing conversations (longctx.py chain: a ~100k first turn then 7 turns of +1,000
#       tokens, a ~250k first turn then 5 turns, a 128-token reply every turn); decode at ~100k and ~250k deep (longdec_ids.json, 2 reps)
#  z1   the candidate, the same legs
#  z0   the recipe without WINS: greedy at 1 2 4 6 8 and the 24 prompts; z0b the same on a second boot
#  z3   the candidate on a second boot: greedy at 1 2 4 6 8, sampled at 1 2 4, the 24 prompts (pairs z1-z0 and z3-z0b, adjacent)
#  z2   the candidate with TF_GLM_REQUEST_STARTS=1: cold, warm turns and the two growing conversations (the switch's payoff is the next
#       turn of the same conversation, which only the growing conversation sends)
#  dt   the disk tier window on the candidate (scripts/queue-disk-tier.sh f72, XENV_KNOBS=WINS, RESTORE=0): restarts, kills and resumes
#  pf   where a cold prompt's time goes on the candidate (lane PrefillGap's nsys-prefill.sh f72: rank 0 under nsys for 8k and 32k cold
#       prompts, then every rank's TF_GLM_PROF prompt lines): ~/bench/pf-f72/
#  p2   production after its restore: the legs of p1 with new seeds
# Production stopped on every rank (prod-stop.sh), KEEP=1, production restored before p2. QUEUE72-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
WORKERS=${WORKERS:?set WORKERS to the ssh targets of ranks 1 and 2, space separated}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=glm53-zig:v129v
ZLOG='docker logs --since {since} glm53-zig-r0'
WINS="-e TF_GLM_OVN_NO_COPY=1 -e TF_GLM_OVN_MM_DECTILE=100000 -e TF_GLM_OVN_SWIGLU_REDUCE=1 -e TF_GLM_OVN_ONEPASS_PIPE=1 -e TF_GLM_CHUNK_SOLO=4096 -e TF_GLM_OVN_HOST_ONCE=1"
until grep -q QUEUE71-DONE queue71.log 2>/dev/null; do sleep 30; done
idle() { # 0 when production answers /health with no request running
  python3 - <<'EOF'
import json, sys, urllib.request
try:
    d = json.load(urllib.request.urlopen("http://127.0.0.1:8888/health", timeout=5))
except Exception:
    sys.exit(2)
sys.exit(0 if (d.get("requests_running", 1) == 0 and not d.get("busy", True)) else 1)
EOF
}
wait_idle() { [ "$1" = 8888 ] || return 0; for i in $(seq 1 60); do idle && return 0; sleep 10; done; return 1; }
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
greedy() { # greedy DIR PORT LEVELS...
  local dir=$1 port=$2 tag; tag=$(basename "$1"); shift 2; mkdir -p "$dir"
  for N in "$@"; do
    wait_idle "$port" || { echo "[q72] $tag $N SKIPPED: production stayed busy"; continue; }
    python3 streams_ids.py "$port" "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py "$port" "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q72] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR PORT LEVELS...
  local dir=$1 port=$2 tag; tag=$(basename "$1"); shift 2; mkdir -p "$dir"
  for N in "$@"; do
    wait_idle "$port" || { echo "[q72] $tag $N sampled SKIPPED: production stayed busy"; continue; }
    python3 streams_sampled.py "$port" "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py "$port" "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q72] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { # prompts DIR PORT: the 24 prompts one at a time (per_prompt.py waits for an idle serve itself)
  mkdir -p "$1"; python3 per_prompt.py "$2" --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1
  echo "[q72] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"
}
longdec() { # longdec DIR PORT
  mkdir -p "$1"; python3 per_prompt.py "$2" --ids longdec_ids.json --reps 2 --out "$1/ld.jsonl" > "$1/ld.out" 2>&1
  echo "[q72] $(date -u +%T) $(basename "$1") longdec rc=$?"
}
cold_warm() { # cold_warm DIR PORT SEED LOGCMD: cold 8k / 32k / 120k twice, then ttft.py's warm turns
  local dir=$1 port=$2 seed=$3 lc=$4 tag; tag=$(basename "$1"); mkdir -p "$dir"
  wait_idle "$port" || { echo "[q72] $tag cold SKIPPED: busy"; return; }
  python3 longctx.py probe "$port" --tag "$tag-cold" --n 4 --out "$dir/lc.jsonl" --log-cmd "$lc" --seed "$seed" --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$dir/cold.out" 2>&1; local r1=$?
  wait_idle "$port"
  python3 longctx.py probe "$port" --tag "$tag-wt100" --n 4 --out "$dir/lc.jsonl" --log-cmd "$lc" --seed "$seed-wt100" --cold-sizes '' --warm-base 100000 --warm-add 2000 --reps 3 --load 0 > "$dir/wt100.out" 2>&1; local r2=$?
  wait_idle "$port"
  python3 longctx.py probe "$port" --tag "$tag-wt250" --n 4 --out "$dir/lc.jsonl" --log-cmd "$lc" --seed "$seed-wt250" --cold-sizes '' --warm-base 250000 --warm-add 600 --reps 3 --load 0 > "$dir/wt250.out" 2>&1; local r3=$?
  wait_idle "$port"
  python3 longctx.py probe "$port" --tag "$tag-wt250L" --n 4 --out "$dir/lc.jsonl" --log-cmd "$lc" --seed "$seed-wt250" --cold-sizes '' --warm-base 250000 --warm-add 600 --reps 3 --load 3 > "$dir/wt250L.out" 2>&1; local r4=$?
  echo "[q72] $(date -u +%T) $tag cold rc=$r1 warm rc=$r2 $r3 $r4"
}
chain() { # chain DIR PORT SALT T1 TURNS LOGCMD: a growing conversation, +1,000 tokens a turn after the first
  local dir=$1 port=$2 salt=$3 t1=$4 turns=$5 lc=$6 st; st="$1/chain-$3.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    wait_idle "$port" || { echo "[q72] $salt turn $k SKIPPED: busy"; return; }
    python3 longctx.py chain "$port" "$st" --t1 "$t1" --add 1000 --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$lc" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q72] $salt turn $k FAILED"; return; }
  done
  echo "[q72] $(date -u +%T) $salt chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
suite() { # suite DIR PORT SEED LOGCMD: every leg of p1 / z1
  greedy "$1" "$2" 1 2 4 6 8
  sampled "$1" "$2" 1 2 4
  prompts "$1" "$2"
  cold_warm "$1" "$2" "$3" "$4"
  chain "$1" "$2" "$3-c100" 100000 8 "$4"
  chain "$1" "$2" "$3-c250" 250000 6 "$4"
  longdec "$1" "$2"
}
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
boot() { # boot LABEL XENV
  stop
  if IMAGE=$IMG KNOBS=measured XENV="$2" bash zig-tp3.sh 4 1048576 > "$HOME/bench/f72-boot-$1.log" 2>&1; then return 0; fi
  echo "[q72] BOOT FAILED $1: $(tail -3 "$HOME/bench/f72-boot-$1.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 2000 > "$1"; }
restore() {
  curl -sf localhost:8888/health > /dev/null 2>&1 && return 0
  setsid nohup bash ~/glm-v110-start.sh > "$HOME/bench/prod-restore-q72.log" 2>&1 < /dev/null &
  for i in $(seq 1 90); do curl -sf localhost:8888/health > /dev/null 2>&1 && return 0; sleep 10; done; return 1
}

echo "[q72] $(date -u +%T) DEFS: $(sed -n '/^DEFS="/,/"$/p' serve.sh | tr -s ' \n' ' ' | cut -c1-900)"
echo "[q72] WINS: $WINS"
suite "$HOME/bench/f72-p1" 8888 f72p1 ''
bash prod-stop.sh || { echo "[q72] PRODUCTION DID NOT STOP"; restore; echo "QUEUE72-DONE $(date -u +%T)"; exit 1; }
if boot z1 "$WINS"; then suite "$HOME/bench/f72-z1" 8300 f72z1 "$ZLOG"; keeplog "$HOME/bench/f72-z1/r0.log"; fi
if boot z0 ""; then greedy "$HOME/bench/f72-z0" 8300 1 2 4 6 8; prompts "$HOME/bench/f72-z0" 8300; keeplog "$HOME/bench/f72-z0/r0.log"; fi
if boot z0b ""; then greedy "$HOME/bench/f72-z0b" 8300 1 2 4 6 8; prompts "$HOME/bench/f72-z0b" 8300; keeplog "$HOME/bench/f72-z0b/r0.log"; fi
if boot z3 "$WINS"; then greedy "$HOME/bench/f72-z3" 8300 1 2 4 6 8; sampled "$HOME/bench/f72-z3" 8300 1 2 4; prompts "$HOME/bench/f72-z3" 8300; keeplog "$HOME/bench/f72-z3/r0.log"; fi
if boot z2 "$WINS -e TF_GLM_REQUEST_STARTS=1"; then
  cold_warm "$HOME/bench/f72-z2" 8300 f72z2 "$ZLOG"
  chain "$HOME/bench/f72-z2" 8300 f72z2-c100 100000 8 "$ZLOG"
  chain "$HOME/bench/f72-z2" 8300 f72z2-c250 250000 6 "$ZLOG"
  keeplog "$HOME/bench/f72-z2/r0.log"
fi
stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1
IMAGE=$IMG KNOBS=measured XENV_KNOBS="$WINS" RESTORE=0 bash queue-disk-tier.sh f72 > "$HOME/bench/f72-disktier.log" 2>&1; echo "[q72] $(date -u +%T) disk tier rc=$? $(tail -2 "$HOME/bench/f72-disktier.log" | tr '\n' ' ' | cut -c1-200)"
stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1
IMAGE=$IMG KNOBS=measured XENV="$WINS" P=4 CTX=1048576 bash nsys-prefill.sh f72 > "$HOME/bench/f72-prefill.log" 2>&1; echo "[q72] $(date -u +%T) prompt-pass profile rc=$? $(tail -1 "$HOME/bench/f72-prefill.log" | cut -c1-160)"
stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1
restore && echo "[q72] production healthy" || echo "[q72] PRODUCTION NOT HEALTHY"
suite "$HOME/bench/f72-p2" 8888 f72p2 ''
echo "QUEUE72-DONE $(date -u +%T)"
