#!/usr/bin/env bash
# queue119 - the three-point top_k comparison DRAW1's premise needs, at four clients.
#
# DRAW1 would exchange only each rank's top-k candidates instead of whole rows. Its premise is that a
# larger top_k costs decode time on the whole-row path, so the screen is one image, one boot a cell,
# greedy plus top_k at 40, 128 and 1024, at four clients, same seed:
#   if top_k=1024 is at least 1.0% slower than top_k=40, the premise holds and the subsystem has a target;
#   if the three sampled cells are level (within 1.0%), the whole-row path is insensitive to top_k and
#   DRAW1 is not worth building on this evidence.
# A boot that fails or a missing cell is NOT DECIDED for that point, never a pass.
set -uo pipefail
cd "$HOME/work/glm53-zig" || exit 1
G="$HOME/work/glm53-zig"; OUT="$HOME/bench"; R="$OUT/topk2"
IMG=${IMG:-glm53-zig:m130a}
[ -f "$G/queue119.env" ] && . "$G/queue119.env"
WORKERS=${WORKERS:?set WORKERS}
W1=${WORKERS%% *}; W2=${WORKERS##* }
WAIT_FOR=${WAIT_FOR:-}

log() { echo "[tk2] $(date -u +%T) $*"; }
if [ -z "$WAIT_FOR" ] && [ "${ALLOW_NOWAIT:-0}" != 1 ]; then
  log "no WAIT_FOR in queue119.env; refusing to boot beside another queue"; exit 1
fi
log "start; waiting for $WAIT_FOR"
while pgrep -f "bash $WAIT_FOR" > /dev/null; do sleep 20; done
log "waited $WAIT_FOR out; starting"

stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "TOPK2-DONE $(date -u +%T)"; }
trap finish EXIT
mkdir -p "$R" "$OUT/topk2-boots"

ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1" 2>/dev/null; done; } )
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then
  log "IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS"; exit 1
fi
bash prod-stop.sh > /dev/null 2>&1 || { log "PRODUCTION DID NOT STOP"; exit 1; }

for cell in ctl:0 k40:40 k128:128 k1024:1024; do
  label=${cell%%:*}; k=${cell##*:}
  d="$R/$label"
  if [ -f "$d/P4.jsonl" ]; then log "$label already done; skip"; continue; fi
  stop
  docker run --rm --privileged --entrypoint sh "$IMG" -c 'sync; echo 3 > /proc/sys/vm/drop_caches' > /dev/null 2>&1
  log "$label boot (top_k=$k)"
  IMAGE="$IMG" KNOBS=dev bash zig-tp3.sh 4 1048576 > "$OUT/topk2-boots/$label.log" 2>&1 \
    || { log "$label BOOT FAILED: $(tail -2 "$OUT/topk2-boots/$label.log" | tr '\n' ' ' | cut -c1-140)"; continue; }
  mkdir -p "$d"
  args=()
  [ "$k" != 0 ] && args=(--top-k "$k")
  python3 streams_sampled.py 8300 4 --ids code_ids.json --max-tokens 256 --rounds 3 "${args[@]}" \
    --tag "tk2-$label" --out "$d/P4.jsonl" > "$d/P4.out" 2>&1
  log "$label rc=$? $(grep -o '\"agg_tok_s\": [0-9.]*' "$d/P4.jsonl" 2>/dev/null | head -1)"
done
log "done; compare k40, k128 and k1024 in $R"
