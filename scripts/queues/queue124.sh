#!/usr/bin/env bash
# queue124 - the fast screen's second batch: six more never-measured settings, one boot an arm.
#
# Each arm is a real alternative to the engine default its row carries:
#   TF_GLM_OVN_DECODE_INDEX   0 -> 1     (the decode index path on)
#   TF_GLM_EXPERT_FORM        unset -> classic (stop racing classic against factored at load)
#   TF_MTP_DRAFTS             3 -> 1     (fewer drafts)
#   TF_QMMF_HALF_BELOW        96 -> 0    (never take the half path)
#   TF_NO_TREES               0 -> 1
#   TF_GLM_INDEX_DECODE_FROM  0 -> 8192  (index kernels only past 8k, not at any depth)
#
# The rule is queue118's, unchanged and fixed before any row: one boot an arm, levels 1, 2 and 4 inside the
# boot; DEAD over 2.0% slower at any level, PROMISING over 2.0% faster somewhere with no level over 1.0%
# slower, UNCLEAR otherwise. Six and eight clients are excluded because their spread is 8 to 20% and a
# single boot cannot screen them.
set -uo pipefail
cd "$HOME/work/glm53-zig" || exit 1
G="$HOME/work/glm53-zig"; OUT="$HOME/bench"; R="$OUT/screen124"
IMG=${IMG:-glm53-zig:m130a}
[ -f "$G/queue124.env" ] && . "$G/queue124.env"
WORKERS=${WORKERS:?set WORKERS}
W1=${WORKERS%% *}; W2=${WORKERS##* }
WAIT_FOR=${WAIT_FOR:-}

log() { echo "[s124] $(date -u +%T) $*"; }
if [ -z "$WAIT_FOR" ] && [ "${ALLOW_NOWAIT:-0}" != 1 ]; then
  log "no WAIT_FOR in queue124.env; refusing to boot beside another queue"; exit 1
fi
log "start; waiting for $WAIT_FOR"
while pgrep -f "bash $WAIT_FOR" > /dev/null; do sleep 20; done

stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "S124-DONE $(date -u +%T)"; }
trap finish EXIT
mkdir -p "$R" "$OUT/screen124-boots"

ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1" 2>/dev/null; done; } )
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then
  log "IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS"; exit 1
fi
bash prod-stop.sh > /dev/null 2>&1 || { log "PRODUCTION DID NOT STOP"; exit 1; }

pairs="ctl:
decidx:TF_GLM_OVN_DECODE_INDEX=1
form:TF_GLM_EXPERT_FORM=classic
drafts:TF_MTP_DRAFTS=1
half:TF_QMMF_HALF_BELOW=0
notrees:TF_NO_TREES=1
idxfrom:TF_GLM_INDEX_DECODE_FROM=8192"

for arm in $pairs; do
  label=${arm%%:*}; kv=${arm#*:}
  d="$R/$label"
  if [ -f "$d/P4.jsonl" ]; then log "$label done; skip"; continue; fi
  stop
  docker run --rm --privileged --entrypoint sh "$IMG" -c 'sync; echo 3 > /proc/sys/vm/drop_caches' > /dev/null 2>&1
  if [ -n "$kv" ]; then xe="-e $kv"; else xe=""; fi
  log "$label boot (xenv='${xe}')"
  IMAGE="$IMG" KNOBS=dev XENV="$xe" bash zig-tp3.sh 4 1048576 > "$OUT/screen124-boots/$label.log" 2>&1 \
    || { log "$label BOOT FAILED: $(tail -2 "$OUT/screen124-boots/$label.log" | tr '\n' ' ' | cut -c1-140)"; continue; }
  mkdir -p "$d"
  for N in 1 2 4; do
    python3 streams.py 8300 "$N" --kind prose --max-tokens 400 --rounds 3 --tag "s124-$label-$N" \
      --out "$d/P$N.jsonl" > "$d/P$N.out" 2>&1
  done
  log "$label levels: $(for N in 1 2 4; do grep -o '\"agg_tok_s\": [0-9.]*' "$d/P$N.jsonl" 2>/dev/null | head -1 | sed 's/.*: //' | tr -d '\n'; printf ' '; done)"
done
log "done; compare each arm against ctl in $R"
