#!/usr/bin/env bash
# queue112 - the stock rung at the five levels, with the page cache dropped before EVERY boot.
#
# queue101 could not measure the unpatched engine: all four boots refused with "the checkpoint's 61.3 GiB of weights do
# not fit the 55.x GiB the CUDA memory budget grants". The audit (docs/audit-2026-11-12/memory-preflight-fa13df5.md)
# shows why: the weights load through the page cache, so a boot that follows another boot finds the previous one's
# weights counted as occupied. Dropping the cache and compacting returns about 46 GiB and the same image boots
# KNOBS=off at --parallel 4, measured up in 125 s on 2026-11-22.
#
# So this queue drops the cache on all three boxes before each boot and runs the stock configuration at 1, 2, 4, 6 and 8
# streams, two boots a level (a and b), which gives the spread a single-arm baseline needs. It is a BASELINE measurement,
# not an arm: no switch is being decided, and the numbers go beside our recipe's cells with the rung named.
set -uo pipefail
cd "$HOME/work/glm53-zig" || exit 1
G="$HOME/work/glm53-zig"
OUT="$HOME/bench"; R="$OUT/f112-c"
IMG=${IMG:-glm53-zig:m130a}
[ -f "$G/queue112.env" ] && . "$G/queue112.env"
WORKERS=${WORKERS:?set WORKERS}
W1=${WORKERS%% *}; W2=${WORKERS##* }
WAIT_FOR=${WAIT_FOR:-}

log() { echo "[q112] $(date -u +%T) $*"; }

if [ -z "$WAIT_FOR" ] && [ "${ALLOW_NOWAIT:-0}" != 1 ]; then
  log "no WAIT_FOR in queue112.env; refusing to boot beside another queue (ALLOW_NOWAIT=1 overrides)"
  exit 1
fi
log "start; waiting for $WAIT_FOR"
while pgrep -f "bash $WAIT_FOR" > /dev/null; do sleep 30; done
log "waited $WAIT_FOR out; starting"

stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE112-DONE $(date -u +%T)"; }
trap finish EXIT
mkdir -p "$R" "$OUT/f112-boots"

# drop the page cache on all three boxes: the rung the memory audit found, and it runs before EVERY boot
drops() {
  local cmd="docker run --rm --privileged --entrypoint sh $IMG -c 'sync; echo 3 > /proc/sys/vm/drop_caches; echo 1 > /proc/sys/vm/compact_memory'"
  eval "$cmd" > /dev/null 2>&1
  for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "$cmd" > /dev/null 2>&1; done
  local a; a=$(awk '/^MemAvailable:/{printf "%.1f", $2/1048576}' /proc/meminfo)
  log "caches dropped; spark1 MemAvailable ${a} GiB"
}

for L in 1 2 4 6 8; do
  for b in a b; do
    dir="$R/P$L-$b"
    [ -f "$dir/P$L.jsonl" ] && { log "P$L-$b already complete; skip"; continue; }
    stop; drops
    IMAGE=$IMG KNOBS=off LEVELS="$L" bash "$G/bench-arm.sh" "$IMG" "f112-c/P$L-$b" > "$OUT/f112-boots/P$L-$b.log" 2>&1
    log "P$L-$b rc=$? ($(ls "$dir"/P*.jsonl 2>/dev/null | wc -l) jsonl)"
    grep -a "do not fit" "$OUT/f112-boots/P$L-$b.log" | tail -1 | cut -c1-120
  done
done
log "done; the stock rung's cells are in $R, one directory a boot"
