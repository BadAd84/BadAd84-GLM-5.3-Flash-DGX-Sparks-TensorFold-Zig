#!/bin/bash
# queue68.sh - on spark1, detached. Image glm53-zig:v129v (stack tree 5137a5ef75ab: pin + patches/engine 0001..0035 + pr1411 0001..0002 + cache-salt).
#  0  production's warm turns while it is idle (longctx.py probe, the seeds of queue67): wt-prod2
#  1  production stopped on every rank (prod-stop.sh); KEEP=1 on every boot, so a crashed rank keeps its log
#  2  one warm-up boot of the recipe, discarded: the first boot of every earlier window read 1.5 to 2.5% high
#  3  the candidate (TF_GLM_OVN_NO_COPY, MM_DECTILE=100000, SWIGLU_REDUCE) against the recipe, --parallel 4 --context 1048576,
#     r c c r r c c r: prose ids and code ids at 1 2 4 clients (3 waves) and per_prompt.py over prompts24.json (1 rep) each boot: b68-*
#  4  the same at 6 and 8 streams, fresh --parallel 6 and 8 boots, r c c r: e68-*
#  5  warm turns on the recipe (wt-zig2) and with TF_GLM_REQUEST_STARTS=1 (wt-zigrs2), the seeds of queue67
#  production restored at the end. QUEUE68-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
WORKERS=${WORKERS:?set WORKERS to the ssh targets of ranks 1 and 2, space separated}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=glm53-zig:v129v
CAND="-e TF_GLM_OVN_NO_COPY=1 -e TF_GLM_OVN_MM_DECTILE=100000 -e TF_GLM_OVN_SWIGLU_REDUCE=1"
probes() { # probes NAME PORT LOGCMD
  local who=$1 port=$2 OUT="$HOME/bench/wt-$1"; mkdir -p "$OUT"
  python3 longctx.py probe "$port" --tag "wt100-$who" --n 4 --out "$OUT/rows.jsonl" --log-cmd "$3" --seed wt100 --cold-sizes '' --warm-base 100000 --warm-add 2000 --reps 3 --load 0 > "$OUT/wt100.out" 2>&1
  echo "[q68] $(date -u +%T) $who wt100 rc=$?"
  python3 longctx.py probe "$port" --tag "wt250-$who" --n 4 --out "$OUT/rows.jsonl" --log-cmd "$3" --seed wt250 --cold-sizes '' --warm-base 250000 --warm-add 600 --reps 3 --load 0 > "$OUT/wt250.out" 2>&1
  echo "[q68] $(date -u +%T) $who wt250 rc=$?"
  python3 longctx.py probe "$port" --tag "wt250L-$who" --n 4 --out "$OUT/rows.jsonl" --log-cmd "$3" --seed wt250 --cold-sizes '' --warm-base 250000 --warm-add 600 --reps 3 --load 3 > "$OUT/wt250L.out" 2>&1
  echo "[q68] $(date -u +%T) $who wt250L rc=$?"
}
for i in $(seq 1 60); do
  [ "$(curl -s -m 5 localhost:8888/health | python3 -c 'import json,sys; d=json.load(sys.stdin); print(int(d.get("requests_running",1)==0 and not d.get("busy",True)))' 2>/dev/null)" = 1 ] && break; sleep 10
done
probes prod2 8888 ''
bash prod-stop.sh || { echo "[q68] PRODUCTION DID NOT STOP"; setsid nohup bash ~/glm-v110-start.sh > "$HOME/bench/prod-restore-q68.log" 2>&1 < /dev/null & echo "QUEUE68-DONE $(date -u +%T)"; exit 1; }
measure() { # measure TAG LEVELS...
  local tag=$1 OUT="$HOME/bench/$1"; shift
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$OUT/P$N.jsonl" > "$OUT/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$OUT/C$N.jsonl" > "$OUT/C$N.out" 2>&1; local r2=$?
    echo "[q68] $(date -u +%T) $tag $N streams prose rc=$r1 $(tail -1 "$OUT/P$N.out" | grep -o '"agg_tok_s": [0-9.]*') code rc=$r2 $(tail -1 "$OUT/C$N.out" | grep -o '"agg_tok_s": [0-9.]*')"
  done
}
boot4() { # boot4 TAG XENV -> 0 when up
  local OUT="$HOME/bench/$1"; mkdir -p "$OUT"
  IMAGE=$IMG KNOBS=measured CTX=1048576 XENV="$2" bash zig-tp3.sh 4 > "$OUT/boot.log" 2>&1 || { echo "[q68] BOOT FAILED $1: $(tail -4 "$OUT/boot.log" | tr '\n' ' ' | cut -c1-300)"; return 1; }
  docker inspect glm53-zig-r0 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep "NO_COPY\|MM_DECTILE\|SWIGLU_REDUCE\|REQUEST_STARTS" | sort | tr '\n' ' ' > "$OUT/knobs.txt"
}
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
if boot4 b68-warmup ""; then measure b68-warmup 1; fi; stop
for a in r1:"" c1:"$CAND" c2:"$CAND" r2:"" r3:"" c3:"$CAND" c4:"$CAND" r4:""; do
  tag="b68-${a%%:*}"; xenv="${a#*:}"
  if boot4 "$tag" "$xenv"; then
    measure "$tag" 1 2 4
    python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$HOME/bench/$tag/pp.jsonl" > "$HOME/bench/$tag/pp.out" 2>&1; echo "[q68] $(date -u +%T) $tag prompts rc=$?"
  fi
  stop
done
for a in r1:"" c1:"$CAND" c2:"$CAND" r2:""; do
  tag="e68-${a%%:*}"; xenv="${a#*:}"; mkdir -p "$HOME/bench/$tag"
  for N in 6 8; do
    if IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh "$N" > "$HOME/bench/$tag/boot-P$N.log" 2>&1; then measure "$tag" "$N"
    else echo "[q68] BOOT FAILED $tag P=$N: $(tail -4 "$HOME/bench/$tag/boot-P$N.log" | tr '\n' ' ' | cut -c1-300)"; fi
    stop
  done
done
if boot4 wt-zig2-boot ""; then probes zig2 8300 'docker logs --since {since} glm53-zig-r0'; fi; stop
if boot4 wt-zigrs2-boot "-e TF_GLM_REQUEST_STARTS=1"; then probes zigrs2 8300 'docker logs --since {since} glm53-zig-r0'; fi; stop
docker rm -f glm53-zig-r0 > /dev/null 2>&1
curl -sf localhost:8888/health > /dev/null 2>&1 || {
  setsid nohup bash ~/glm-v110-start.sh > "$HOME/bench/prod-restore-q68.log" 2>&1 < /dev/null &
  for i in $(seq 1 90); do curl -sf localhost:8888/health > /dev/null 2>&1 && break; sleep 10; done; }
curl -sf localhost:8888/health > /dev/null 2>&1 && echo "[q68] production healthy" || echo "[q68] PRODUCTION NOT HEALTHY"
echo "QUEUE68-DONE $(date -u +%T)"
