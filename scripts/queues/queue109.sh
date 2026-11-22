#!/usr/bin/env bash
# queue109 - TF_GLM_OVN_ABSORB_VEC at the five levels, fresh boot a level, mirrored.
#
# queue102 read V (TF_GLM_OVN_ABSORB_VEC=1) at +0.96 / +1.04 / +0.84% on the cold prompt at 8k / 32k / 120k with both
# arm boots under both control boots, and decode +0.62% over twelve cells with none negative. The campaign requires a
# five-level run before adoption, so this queue benches the recipe (KNOBS=prod, the switch unset) against the same
# recipe with the switch on, at 1, 2, 4, 6 and 8 clients in the mirrored order av0 av1 av1 av0 av0 av1 av1 av0 so drift
# lands on both arms: that is ten boots of the recipe's streams instrument per level.
#
# The eight boots of queue102 belong to the same image; this run's job is the other three levels and the mirrored
# separation at the two it already has.
#
# Verdict is read by hand from the five-level table (no scorer: the rule is the fleet rule - no regression at any
# level, and a trade goes to the owner). Records: docs/audit-2026-11-12/queue-rows/queue109.
set -uo pipefail
cd "$HOME/work/glm53-zig" || exit 1
G="$HOME/work/glm53-zig"
HERE="$HOME/bench"
OUT="$HERE/f109-c"
mkdir -p "$OUT"
Q="q109"
IMG=${IMG:-glm53-zig:m130a}
HOURS=${HOURS:-6}
WAIT_FOR=${WAIT_FOR:-}
[ -f "$G/queue109.env" ] && . "$G/queue109.env"

log() { echo "[$Q] $(date -u +%H:%M:%S) $*" | tee -a "$HERE/queue109.log"; }

if [ -z "$WAIT_FOR" ] && [ "${ALLOW_NOWAIT:-0}" != 1 ]; then
  log "no WAIT_FOR in queue109.env; refusing to boot beside another queue (ALLOW_NOWAIT=1 overrides)"
  exit 1
fi

if [ -n "$WAIT_FOR" ]; then
  log "start; waiting for $WAIT_FOR"
  for _ in $(seq 1 $((HOURS * 720))); do
    pgrep -f "bash ${WAIT_FOR}" >/dev/null || break
    sleep 5
  done
  log "waited $WAIT_FOR out; starting"
fi

for u in av0a av1a av1b av0b av0c av1c av1d av0d; do
  [ -f "$OUT/$u/P1.jsonl" ] && { log "$u already complete; skip"; continue; }
  case "$u" in
    av0*) KNOBS=prod XENV="-e TF_GLM_OVN_ABSORB_VEC=0" ;;
    av1*) KNOBS=prod XENV="-e TF_GLM_OVN_ABSORB_VEC=1" ;;
  esac
  log "$u start"
  IMAGE="$IMG" KNOBS="$KNOBS" XENV="$XENV" LEVELS="1 2 4 6 8" \
    bash "$HOME/work/glm53-zig/bench-arm.sh" "$IMG" "f109-c/$u" >> "$OUT/$u.boot.log" 2>&1
  log "$u rc=$? ($(ls "$OUT/$u"/P*.jsonl 2>/dev/null | wc -l) levels)"
done

log "done; compare the five levels arm against control, av1 over av0 minus one, positive is the arm faster"
echo "QUEUE109-DONE $(date -u +%H:%M:%S)" | tee -a "$HERE/queue109.log"
