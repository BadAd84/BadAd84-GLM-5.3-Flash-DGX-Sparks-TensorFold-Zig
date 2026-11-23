#!/usr/bin/env bash
# queue120 - the follow-through from the fast screen, plus the missing top-k point.
#
# 1. top_k=1024, the one cell queue119 never got: DRAW1's premise needs the top end of the range,
#    and k40 (150.69) and k128 (150.02) are within 0.5% of each other, so only 1024 can answer it.
# 2. TF_GLM_PROMPT_STEPS=0, which the screen made PROMISING (+3.37 / +2.36 / +1.24% at 1 / 2 / 4), as a
#    proper arm: two boots, five levels each inside the boot, against a control booted the same way.
#    The rule before any row: adopt when it is not more than 1.0% slower at any of 1, 2, 4, 6, 8 and at
#    least 1.0% faster in the mean; hold otherwise.
# 3. One confirm boot each for the three UNCLEAR arms (DRAFT_CONFIDENCE=0.6, DRAFT_NODES=8,
#    LINK_WAIT=1), because the screen's rule says an arm inside +-2% gets a second boot, and a setting is
#    recorded measured-level only when both boots agree within 1.0%.
set -uo pipefail
cd "$HOME/work/glm53-zig" || exit 1
G="$HOME/work/glm53-zig"; OUT="$HOME/bench"; R="$OUT/s120"
IMG=${IMG:-glm53-zig:m130a}
[ -f "$G/queue120.env" ] && . "$G/queue120.env"
WORKERS=${WORKERS:?set WORKERS}
W1=${WORKERS%% *}; W2=${WORKERS##* }
WAIT_FOR=${WAIT_FOR:-}

log() { echo "[s120] $(date -u +%T) $*"; }
if [ -z "$WAIT_FOR" ] && [ "${ALLOW_NOWAIT:-0}" != 1 ]; then
  log "no WAIT_FOR; refusing to boot beside another queue"; exit 1
fi
log "start; waiting for $WAIT_FOR"
while pgrep -f "bash $WAIT_FOR" > /dev/null; do sleep 20; done

stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "S120-DONE $(date -u +%T)"; }
trap finish EXIT
mkdir -p "$R" "$OUT/s120-boots"

ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1" 2>/dev/null; done; } )
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then
  log "IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS"; exit 1
fi
bash prod-stop.sh > /dev/null 2>&1 || { log "PRODUCTION DID NOT STOP"; exit 1; }

boot() { # boot LABEL XENV
  local label=$1 xe=$2
  stop
  docker run --rm --privileged --entrypoint sh "$IMG" -c 'sync; echo 3 > /proc/sys/vm/drop_caches' > /dev/null 2>&1
  log "$label boot (xenv='${xe}')"
  IMAGE="$IMG" KNOBS=dev XENV="$xe" bash zig-tp3.sh 4 1048576 > "$OUT/s120-boots/$label.log" 2>&1 \
    || { log "$label BOOT FAILED: $(tail -2 "$OUT/s120-boots/$label.log" | tr '\n' ' ' | cut -c1-140)"; return 1; }
  return 0
}

# 1. the missing top-k point
d="$R/k1024"; mkdir -p "$d"
if [ ! -f "$d/P4.jsonl" ] && boot k1024 ""; then
  python3 streams_sampled.py 8300 4 --ids code_ids.json --max-tokens 256 --rounds 3 --top-k 1024 \
    --tag s120-k1024 --out "$d/P4.jsonl" > "$d/P4.out" 2>&1
  log "k1024 rc=$? $(grep -o '\"agg_tok_s\": [0-9.]*' "$d/P4.jsonl" 2>/dev/null | head -1)"
fi

# 2. the promising arm, two boots at five levels inside each boot
for arm in ctl:0 st:1 ctl2:0 st2:1; do
  label=${arm%%:*}; val=${arm##*:}
  d="$R/$label"; mkdir -p "$d"
  if [ -f "$d/P8.jsonl" ]; then log "$label done; skip"; continue; fi
  if [ "$val" = 1 ]; then xe="-e TF_GLM_PROMPT_STEPS=0"; else xe=""; fi
  boot "$label" "$xe" || continue
  for N in 1 2 4 6 8; do
    python3 streams.py 8300 "$N" --kind prose --max-tokens 400 --rounds 3 --tag "s120-$label-$N" \
      --out "$d/P$N.jsonl" > "$d/P$N.out" 2>&1
  done
  log "$label levels: $(for N in 1 2 4 6 8; do grep -o '\"agg_tok_s\": [0-9.]*' "$d/P$N.jsonl" 2>/dev/null | head -1 | tr -d '\n' | sed 's/\"agg_tok_s\": //'; printf ' '; done)"
done

# 3. the three confirm boots
for arm in conf:TF_GLM_DRAFT_CONFIDENCE=0.6 nodes:TF_DRAFT_NODES=8 linkwait:TF_GLM_LINK_WAIT=1; do
  label=${arm%%:*}; kv=${arm##*:}
  d="$R/$label-c"; mkdir -p "$d"
  if [ -f "$d/P4.jsonl" ]; then log "$label confirm done; skip"; continue; fi
  boot "$label-c" "-e $kv" || continue
  for N in 1 2 4; do
    python3 streams.py 8300 "$N" --kind prose --max-tokens 400 --rounds 3 --tag "s120-$label-c-$N" \
      --out "$d/P$N.jsonl" > "$d/P$N.out" 2>&1
  done
  log "$label-c levels: $(for N in 1 2 4; do grep -o '\"agg_tok_s\": [0-9.]*' "$d/P$N.jsonl" 2>/dev/null | head -1 | tr -d '\n' | sed 's/\"agg_tok_s\": //'; printf ' '; done)"
done
log "done; compare in $R"
