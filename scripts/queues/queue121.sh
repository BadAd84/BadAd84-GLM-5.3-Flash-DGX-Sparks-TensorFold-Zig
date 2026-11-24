#!/usr/bin/env bash
# queue121 - the two settings that cleared the fast screen's band, as proper arms, and the levels
# PROMPT_STEPS=0 needs to settle its apparent loss.
#
# Phase A, proper arms for the two that read above 2% at one and two clients in BOTH rounds:
#   TF_DRAFT_NODES=8 and TF_GLM_LINK_WAIT=1, two boots each plus two control boots, five levels inside
#   each boot. Rule before any row: adopt when an arm is not more than 1.0% slower at any of 1, 2, 4, 6
#   and 8 clients and at least 1.0% faster in the mean of the five; hold otherwise. A level whose control
#   boots disagree by more than 3% is NOT DECIDED for that level rather than a loss.
#
# Phase B, the 6 and 8 client levels for PROMPT_STEPS=0 only: two boots each of the arm and the control,
# measured at 6 and 8 clients inside the boot, because those are the cells whose controls disagreed by
# 6% in the last run and are the whole question between +1.3% at four and a claimed -3.6% at six.
set -uo pipefail
cd "$HOME/work/glm53-zig" || exit 1
G="$HOME/work/glm53-zig"; OUT="$HOME/bench"; R="$OUT/s121"
IMG=${IMG:-glm53-zig:m130a}
[ -f "$G/queue121.env" ] && . "$G/queue121.env"
WORKERS=${WORKERS:?set WORKERS}
W1=${WORKERS%% *}; W2=${WORKERS##* }
WAIT_FOR=${WAIT_FOR:-}

log() { echo "[s121] $(date -u +%T) $*"; }
if [ -z "$WAIT_FOR" ] && [ "${ALLOW_NOWAIT:-0}" != 1 ]; then
  log "no WAIT_FOR; refusing to boot beside another queue"; exit 1
fi
log "start; waiting for $WAIT_FOR"
while pgrep -f "bash $WAIT_FOR" > /dev/null; do sleep 20; done

stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "S121-DONE $(date -u +%T)"; }
trap finish EXIT
mkdir -p "$R" "$OUT/s121-boots"

ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1" 2>/dev/null; done; } )
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then
  log "IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS"; exit 1
fi
bash prod-stop.sh > /dev/null 2>&1 || { log "PRODUCTION DID NOT STOP"; exit 1; }

run() { # run LABEL XENV LEVELS
  local label=$1 xe=$2 levels=$3
  local d="$R/$label"; mkdir -p "$d"
  if [ -f "$d/P$levels.jsonl" ]; then log "$label done; skip"; return 0; fi
  stop
  docker run --rm --privileged --entrypoint sh "$IMG" -c 'sync; echo 3 > /proc/sys/vm/drop_caches' > /dev/null 2>&1
  log "$label boot (xenv='${xe}')"
  IMAGE="$IMG" KNOBS=dev XENV="$xe" bash zig-tp3.sh 4 1048576 > "$OUT/s121-boots/$label.log" 2>&1 \
    || { log "$label BOOT FAILED: $(tail -2 "$OUT/s121-boots/$label.log" | tr '\n' ' ' | cut -c1-140)"; return 1; }
  for N in $levels; do
    python3 streams.py 8300 "$N" --kind prose --max-tokens 400 --rounds 3 --tag "s121-$label-$N" \
      --out "$d/P$N.jsonl" > "$d/P$N.out" 2>&1
  done
  log "$label levels: $(for N in $levels; do grep -o '\"agg_tok_s\": [0-9.]*' "$d/P$N.jsonl" 2>/dev/null | head -1 | sed 's/.*: //' | tr -d '\n'; printf ' '; done)"
}

# Phase A
run ctlA "" "1 2 4 6 8"
run nodes1 "-e TF_DRAFT_NODES=8" "1 2 4 6 8"
run nodes2 "-e TF_DRAFT_NODES=8" "1 2 4 6 8"
run ctlB "" "1 2 4 6 8"
run lw1 "-e TF_GLM_LINK_WAIT=1" "1 2 4 6 8"
run lw2 "-e TF_GLM_LINK_WAIT=1" "1 2 4 6 8"
run ctlC "" "1 2 4 6 8"

# Phase B: the 6 and 8 client question for PROMPT_STEPS=0
run ctlS1 "" "6 8"
run stS1 "-e TF_GLM_PROMPT_STEPS=0" "6 8"
run stS2 "-e TF_GLM_PROMPT_STEPS=0" "6 8"
run ctlS2 "" "6 8"

log "done; compare in $R"
