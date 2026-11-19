#!/bin/bash
# queue67.sh - on spark1, detached, after queue66: an agent's warm turn on production and on the recipe, the case that dominates real traffic
# (production's TTFT map: a turn adds ~600 tokens to a ~250k conversation). longctx.py probe, production's ttft.py method: prime a conversation,
# re-prime before every turn (not measured), then the warm turn's first token; thinking off, 3 reps each, the same seeds on both serves:
#   wt100   a ~100k conversation, +2,000 tokens a turn (section 29's case), idle
#   wt250   a ~250k conversation, +600 tokens a turn, idle
#   wt250L  the same with three other streams decoding (--load 3)
# production first (port 8888, while idle), then a recipe boot (glm53-zig:v129v, KNOBS=measured, --parallel 4 --context 1048576), then the same with
# TF_GLM_REQUEST_STARTS=1 (zigrs: replies must equal zig's, same seeds); production restored. QUEUE67-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
WORKERS=${WORKERS:?set WORKERS to the ssh targets of ranks 1 and 2, space separated}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
IMG=glm53-zig:v129v
until grep -q QUEUE66-DONE queue66.log 2>/dev/null; do sleep 30; done
probes() { # probes SERVE PORT LOGCMD
  local who=$1 port=$2 OUT="$HOME/bench/wt-$1"; mkdir -p "$OUT"
  python3 longctx.py probe "$port" --tag "wt100-$who" --n 4 --out "$OUT/rows.jsonl" --log-cmd "$3" --seed wt100 --cold-sizes '' --warm-base 100000 --warm-add 2000 --reps 3 --load 0 > "$OUT/wt100.out" 2>&1
  echo "[q67] $(date -u +%T) $who wt100 rc=$?"
  python3 longctx.py probe "$port" --tag "wt250-$who" --n 4 --out "$OUT/rows.jsonl" --log-cmd "$3" --seed wt250 --cold-sizes '' --warm-base 250000 --warm-add 600 --reps 3 --load 0 > "$OUT/wt250.out" 2>&1
  echo "[q67] $(date -u +%T) $who wt250 rc=$?"
  python3 longctx.py probe "$port" --tag "wt250L-$who" --n 4 --out "$OUT/rows.jsonl" --log-cmd "$3" --seed wt250 --cold-sizes '' --warm-base 250000 --warm-add 600 --reps 3 --load 3 > "$OUT/wt250L.out" 2>&1
  echo "[q67] $(date -u +%T) $who wt250L rc=$?"
}
for i in $(seq 1 60); do
  [ "$(curl -s -m 5 localhost:8888/health | python3 -c 'import json,sys; d=json.load(sys.stdin); print(int(d.get("requests_running",1)==0 and not d.get("busy",True)))' 2>/dev/null)" = 1 ] && break; sleep 10
done
probes prod 8888 ''
docker rm -f glm53-flash-tf samplers pwcap > /dev/null 2>&1; echo "[q67] $(date -u +%T) production stopped"
if IMAGE=$IMG KNOBS=measured CTX=1048576 bash zig-tp3.sh 4 > "$HOME/bench/wt-boot.log" 2>&1; then probes zig 8300 'docker logs --since {since} glm53-zig-r0'
else echo "[q67] ZIG BOOT FAILED"; fi
bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10
# the same probes with upstream's request-start cuts (a turn resumes where the previous turn's history ends; refused with --learn-conversations)
if IMAGE=$IMG KNOBS=measured CTX=1048576 XENV="-e TF_GLM_REQUEST_STARTS=1" bash zig-tp3.sh 4 > "$HOME/bench/wt-boot-rs.log" 2>&1; then probes zigrs 8300 'docker logs --since {since} glm53-zig-r0'
else echo "[q67] ZIG REQUEST_STARTS BOOT FAILED"; fi
bash zig-tp3-stop.sh > /dev/null 2>&1; docker rm -f glm53-zig-r0 > /dev/null 2>&1
curl -sf localhost:8888/health > /dev/null 2>&1 || {
  setsid nohup bash ~/glm-v110-start.sh > "$HOME/bench/prod-restore-q67.log" 2>&1 < /dev/null &
  for i in $(seq 1 90); do curl -sf localhost:8888/health > /dev/null 2>&1 && break; sleep 10; done; }
curl -sf localhost:8888/health > /dev/null 2>&1 && echo "[q67] production healthy" || echo "[q67] PRODUCTION NOT HEALTHY"
echo "QUEUE67-DONE $(date -u +%T)"
