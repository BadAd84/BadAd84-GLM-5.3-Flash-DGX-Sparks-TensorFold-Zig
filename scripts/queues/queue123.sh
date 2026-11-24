#!/usr/bin/env bash
# queue123 - the other half of the skew: capture ranks 1 and 2 in the same window shape, so "rank 0
# saturated" can become "rank 0 carries more work" or "all three carry the same".
#
# Rank 0's own capture reads 116.7% busy with tf_exl3_ovn_nc1 at 53.7% of its wall, which rules out
# "rank 0 waits" but cannot show what ranks 1 and 2 are doing. This takes one capture on spark2 (rank 1)
# and one on spark3 (rank 2) under the same four-client sampled load, then exports both to sqlite.
#
# Rule before any row: compare each rank's kernel time for the nc-family projection against its own wall.
#   - rank 1 or 2 under about 90% busy while rank 0 is over 110% is the imbalance the review measured;
#   - all three over 100% means the wall is compute on every rank and the skew is not wherever the review
#     placed it, which would retire the item rather than size it.
set -uo pipefail
cd "$HOME/work/glm53-zig" || exit 1
G="$HOME/work/glm53-zig"; OUT="$HOME/bench"; R="$OUT/rankcap"
IMG=${IMG:-glm53-zig:m130a}
[ -f "$G/queue123.env" ] && . "$G/queue123.env"
WORKERS=${WORKERS:?set WORKERS}
W1=${WORKERS%% *}; W2=${WORKERS##* }
WAIT_FOR=${WAIT_FOR:-}

log() { echo "[rc] $(date -u +%T) $*"; }
if [ -z "$WAIT_FOR" ] && [ "${ALLOW_NOWAIT:-0}" != 1 ]; then
  log "no WAIT_FOR; refusing to boot beside another queue"; exit 1
fi
log "start; waiting for $WAIT_FOR"
while pgrep -f "bash $WAIT_FOR" > /dev/null; do sleep 20; done

stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "RANKCAP-DONE $(date -u +%T)"; }
trap finish EXIT
mkdir -p "$R" "$OUT/rankcap-boots"

bash prod-stop.sh > /dev/null 2>&1 || { log "PRODUCTION DID NOT STOP"; exit 1; }

cap() { # cap RANK HOST
  local rank=$1 host=$2
  local rd=/tmp/nsysr$rank
  local d="$R/r$rank"; mkdir -p "$d"
  [ -f "$d/r.nsys-rep" ] && { log "rank $rank already captured; skip"; return 0; }
  stop
  docker run --rm --privileged --entrypoint sh "$IMG" -c 'sync; echo 3 > /proc/sys/vm/drop_caches' > /dev/null 2>&1
  ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$host" "rm -rf $rd && mkdir -p $rd" 2>/dev/null
  log "rank $rank boot with the profiler on $host"
  if [ "$rank" = 1 ]; then
    WRAP1="nsys launch --session-new=r$rank --trace=cuda-sw" XRUN1="-v $rd:/out" \
      IMAGE="$IMG" KNOBS=dev bash zig-tp3.sh 4 1048576 > "$OUT/rankcap-boots/r$rank.log" 2>&1
  else
    WRAP2="nsys launch --session-new=r$rank --trace=cuda-sw" XRUN2="-v $rd:/out" \
      IMAGE="$IMG" KNOBS=dev bash zig-tp3.sh 4 1048576 > "$OUT/rankcap-boots/r$rank.log" 2>&1
  fi || { log "rank $rank BOOT FAILED: $(tail -2 "$OUT/rankcap-boots/r$rank.log" | tr '\n' ' ' | cut -c1-140)"; return 1; }
  # one sampled load, the same client shape as the rank 0 capture
  python3 streams_sampled.py 8300 4 --ids code_ids.json --max-tokens 256 --rounds 2 \
    --tag "rankcap-r$rank" --out "$d/P4.jsonl" > "$d/P4.out" 2>&1
  log "rank $rank load rc=$?"
  ssh -n -o BatchMode=yes "$host" "docker exec glm53-zig-r$rank nsys stop --session=r$rank" > "$d/stop.out" 2>&1
  sleep 20
  ssh -n -o BatchMode=yes "$host" "ls -l $rd" > "$d/files.out" 2>&1
  ssh -n -o BatchMode=yes "$host" "docker run --rm -v $rd:/out --entrypoint nsys $IMG export --type sqlite --force-overwrite true -o /out/r.sqlite /out/r$rank.nsys-rep" > "$d/export.out" 2>&1
  ssh -n -o BatchMode=yes "$host" "cat $rd/r.sqlite" > "$d/r.sqlite" 2>/dev/null
  log "rank $rank sqlite $(stat -c %s "$d/r.sqlite" 2>/dev/null || echo missing) bytes"
}

cap 1 "$W1"
cap 2 "$W2"
log "done; compare rank 0 (work/pp118cap/dec4.sqlite) against $R/r1/r.sqlite and $R/r2/r.sqlite"
