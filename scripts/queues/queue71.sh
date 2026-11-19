#!/bin/bash
# queue71.sh - on spark1, detached: the runs still missing before the measured wins go on together (owner 2026-11-18). Image glm53-zig:v129v,
# the recipe (KNOBS=measured), --parallel 4 --context 1048576 on every boot.
#  0  production, live, each leg only while it is idle: longdec_ids.json (a ~100k and a ~250k context, a prose and a code question each,
#     production's rendering) through per_prompt.py, 2 reps: ~/bench/ld71-prod/pp.jsonl; the sampled prose and code ids at 1 2 4 clients
#     (streams_sampled.py, temperature 1.0, top-p 0.95, top-k 20, seed 7): ~/bench/s71-prod/
#  A  prompt-pass exactness and the combination, cold 8k / 32k / 120k twice with ONE seed on every boot (queue69 seeded each boot apart, so
#     its replies could not be compared): rec1 ps1 psx1 pipe1 solo1 psx2 ps2 rec2; pipe = ONEPASS_PIPE=1, solo = CHUNK_SOLO=4096, ps = both,
#     psx = both + EXCHANGE_KB=4096 (a 4,096-row chunk's exchange posted in 4 MiB pieces): ~/bench/pf71/rows.jsonl
#  B  decode at depth and at the bench's short prompts: rec1 all1 split1 win1 win2 split2 all2 rec2; all = TF_GLM_INDEX_CUDA=all (decode
#     windows on the index kernels), split = TF_GLM_OVN_DECODE_INDEX=33, win = TF_GLM_DFLASH2_WIN=1024 (a draft attends to 1,024 positions,
#     not 2,048): longdec_ids.json 2 reps, then the greedy prose and code ids at 1 2 4: ~/bench/ld71-<arm><n>/
#  C  the draft rule: rec1 marg1 noise1 noise2 marg2 rec2; marg = TF_GLM_OVN_PLAIN_MARGIN=100 (the core's 1.05 becomes 1.00), noise =
#     TF_GLM_OVN_DRAFT_NOISE=1 (a sampled stream's draft picks with the target's keyed Gumbel draws): greedy and sampled prose and code ids
#     at 1 2 4: ~/bench/dr71-<arm><n>/{P,C,SP,SC}<n>.jsonl
# Production stopped on every rank (prod-stop.sh), KEEP=1 on every boot, production restored at the end. QUEUE71-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
WORKERS=${WORKERS:?set WORKERS to the ssh targets of ranks 1 and 2, space separated}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=glm53-zig:v129v
LOGCMD='docker logs --since {since} glm53-zig-r0'
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
wait_idle() { for i in $(seq 1 60); do idle && return 0; sleep 10; done; return 1; }
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
greedy() { # greedy DIR PORT LEVELS...: production's prose and code ids, 3 waves each
  local dir=$1 port=$2 tag; tag=$(basename "$1"); shift 2; mkdir -p "$dir"
  for N in "$@"; do
    if [ "$port" = 8888 ]; then wait_idle || { echo "[q71] $tag $N SKIPPED: production stayed busy"; continue; }; fi
    python3 streams_ids.py "$port" "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py "$port" "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q71] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR PORT LEVELS...: the same ids, sampled and seeded
  local dir=$1 port=$2 tag; tag=$(basename "$1"); shift 2; mkdir -p "$dir"
  for N in "$@"; do
    if [ "$port" = 8888 ]; then wait_idle || { echo "[q71] $tag $N sampled SKIPPED: production stayed busy"; continue; }; fi
    python3 streams_sampled.py "$port" "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py "$port" "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q71] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
longdec() { # longdec DIR PORT: the long-context prompts one at a time, 2 reps
  local dir=$1 port=$2; mkdir -p "$dir"
  python3 per_prompt.py "$port" --ids longdec_ids.json --reps 2 --out "$dir/pp.jsonl" > "$dir/pp.out" 2>&1
  echo "[q71] $(date -u +%T) $(basename "$dir") longdec rc=$? $(python3 -c "
import json, sys
for l in open('$dir/pp.jsonl'):
    r = json.loads(l); print(f\"{r['name']}/{r['rep']}: ttft {r['ttft_s']:.1f}s {r['tokens'] / r['span_s']:.1f}tok/s\", end='; ')
" 2>/dev/null)"
}
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
boot() { # boot LABEL XENV LOGDIR: 0 when the Zig serve is up
  local label=$1 xenv=$2 logdir=$3; mkdir -p "$logdir"
  stop
  if IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$logdir/boot-$label.log" 2>&1; then return 0; fi
  echo "[q71] BOOT FAILED $label: $(tail -3 "$logdir/boot-$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 600 > "$1"; }

# 0: production, before the window
longdec "$HOME/bench/ld71-prod" 8888
sampled "$HOME/bench/s71-prod" 8888 1 2 4
bash prod-stop.sh || { echo "[q71] PRODUCTION DID NOT STOP"; setsid nohup bash ~/glm-v110-start.sh > "$HOME/bench/prod-restore-q71.log" 2>&1 < /dev/null & echo "QUEUE71-DONE $(date -u +%T)"; exit 1; }

# A: prompt-pass exactness, one seed for every boot
OUT=$HOME/bench/pf71; mkdir -p "$OUT"
PIPE="-e TF_GLM_OVN_ONEPASS_PIPE=1"; SOLO="-e TF_GLM_CHUNK_SOLO=4096"; XKB="-e TF_GLM_OVN_EXCHANGE_KB=4096"
for a in rec1:"" ps1:"$PIPE $SOLO" psx1:"$PIPE $SOLO $XKB" pipe1:"$PIPE" solo1:"$SOLO" psx2:"$PIPE $SOLO $XKB" ps2:"$PIPE $SOLO" rec2:""; do
  label="${a%%:*}"; xenv="${a#*:}"; t0=$(date +%s.%N)
  boot "$label" "$xenv" "$OUT"; rc=$?; tu=$(date +%s.%N)
  args=(--tag "$label" --n 4 --ctx 1048576 --boot-start "$t0" --boot-rc "$rc" --image "$IMG" "--xenv=$xenv")
  if [ "$rc" = 0 ]; then args+=(--up-at "$tu"); else args+=("--error=$(tail -4 "$OUT/boot-$label.log" | tr '\n' ' ' | cut -c1-400)"); fi
  python3 longctx.py facts 8300 "${args[@]}" --out "$OUT/rows.jsonl" --log-cmd "$LOGCMD" > "$OUT/$label-facts.out" 2>&1
  [ "$rc" = 0 ] || continue
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/rows.jsonl" --log-cmd "$LOGCMD" --seed pf71 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/$label-probe.out" 2>&1
  echo "[q71] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  keeplog "$OUT/r0-$label.log"
done

# B: decode at depth and short
ALL="-e TF_GLM_INDEX_CUDA=all"; SPLIT="-e TF_GLM_OVN_DECODE_INDEX=33"; WIN="-e TF_GLM_DFLASH2_WIN=1024"
for a in rec1:"" all1:"$ALL" split1:"$SPLIT" win1:"$WIN" win2:"$WIN" split2:"$SPLIT" all2:"$ALL" rec2:""; do
  label="${a%%:*}"; xenv="${a#*:}"; dir="$HOME/bench/ld71-$label"
  boot "$label" "$xenv" "$dir" || continue
  longdec "$dir" 8300
  greedy "$dir" 8300 1 2 4
  keeplog "$dir/r0.log"
done

# C: the draft rule, greedy and sampled
MARG="-e TF_GLM_OVN_PLAIN_MARGIN=100"; NOISE="-e TF_GLM_OVN_DRAFT_NOISE=1"
for a in rec1:"" marg1:"$MARG" noise1:"$NOISE" noise2:"$NOISE" marg2:"$MARG" rec2:""; do
  label="${a%%:*}"; xenv="${a#*:}"; dir="$HOME/bench/dr71-$label"
  boot "$label" "$xenv" "$dir" || continue
  greedy "$dir" 8300 1 2 4
  sampled "$dir" 8300 1 2 4
  keeplog "$dir/r0.log"
done

stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1
curl -sf localhost:8888/health > /dev/null 2>&1 || {
  setsid nohup bash ~/glm-v110-start.sh > "$HOME/bench/prod-restore-q71.log" 2>&1 < /dev/null &
  for i in $(seq 1 90); do curl -sf localhost:8888/health > /dev/null 2>&1 && break; sleep 10; done; }
curl -sf localhost:8888/health > /dev/null 2>&1 && echo "[q71] production healthy" || echo "[q71] PRODUCTION NOT HEALTHY"
echo "QUEUE71-DONE $(date -u +%T)"
