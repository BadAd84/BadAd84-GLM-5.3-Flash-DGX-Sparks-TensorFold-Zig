#!/usr/bin/env bash
# queue116 - the shipping decision: the whole dev env against the current production recipe, five levels, fresh boot a level.
#
# What the two arms are, exactly:
#   prod  = KNOBS=prod: the recipe deployed today, 11 settings, no candidates.
#   dev   = KNOBS=dev:  the same 11 plus the 11 candidates this campaign measured positive, which is what the next
#           production env will be if it wins here.
#
# The candidates are: ABSORB_VEC (cold ~1%), T's four (MM_WIDE, SIDE_PRIO, LATENT_ROWS=2, NCCL_NCHANNELS_PER_NET_PEER=4,
# cold -6.90% at 8k and -7.36% at 32k in queue113) and X's six (OVERLAP_PIECES=4, PIECE_FRONT, PIECE_FFN, PIECE_MLA,
# SOLO_TO_START, RESTORE_HELD, cold -2.99% and -2.66%). Every one of them is enabled by KNOBS=dev today; the measurement
# below is the one that says whether all of them together beat the recipe in production's own configuration.
#
# The rule, written before any row: SHIP the dev env as the new production recipe when it is not slower at any of 1, 2, 4,
# 6 and 8 streams beyond the boot spread, and faster in at least one; a level slower beyond the spread is a trade and goes
# to the owner rather than being shipped. Two boots an arm per level, in the order prod-a dev-a dev-b prod-b, so drift
# lands on both.
set -uo pipefail
cd "$HOME/work/glm53-zig" || exit 1
G="$HOME/work/glm53-zig"
OUT="$HOME/bench"; R="$OUT/f116-c"
IMG=${IMG:-glm53-zig:m130a}
[ -f "$G/queue116.env" ] && . "$G/queue116.env"
WORKERS=${WORKERS:?set WORKERS}
WAIT_FOR=${WAIT_FOR:-}
W1=${WORKERS%% *}; W2=${WORKERS##* }

log() { echo "[q116] $(date -u +%T) $*"; }
if [ -z "$WAIT_FOR" ] && [ "${ALLOW_NOWAIT:-0}" != 1 ]; then
  log "no WAIT_FOR in queue116.env; refusing to boot beside another queue (ALLOW_NOWAIT=1 overrides)"; exit 1
fi
log "start; waiting for $WAIT_FOR"
while pgrep -f "bash $WAIT_FOR" > /dev/null; do sleep 30; done
log "waited $WAIT_FOR out; starting"

stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE116-DONE $(date -u +%T)"; }
trap finish EXIT
mkdir -p "$R" "$OUT/f116-boots"

ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1" 2>/dev/null; done; } )
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then
  log "IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS"; exit 1
fi
log "$IMG ids: $(echo $ids | cut -c1-60); serve.sh $(sha256sum serve.sh | cut -c1-12)"

bash prod-stop.sh > /dev/null 2>&1 || { log "PRODUCTION DID NOT STOP"; exit 1; }

for arm in prod-a dev-a dev-b prod-b; do
  case "$arm" in
    prod-*) knobs=prod ;;
    dev-*)  knobs=dev ;;
  esac
  [ -f "$R/$arm/P1.jsonl" ] && { log "$arm already complete; skip"; continue; }
  stop
  log "$arm start (KNOBS=$knobs, five levels)"
  IMAGE="$IMG" KNOBS="$knobs" LEVELS="1 2 4 6 8" bash "$G/bench-arm.sh" "$IMG" "f116-c/$arm" > "$OUT/f116-boots/$arm.log" 2>&1
  log "$arm rc=$? ($(ls "$R/$arm"/P*.jsonl 2>/dev/null | wc -l) levels)"
done

log "done; prod against dev, five levels each, two boots an arm"
