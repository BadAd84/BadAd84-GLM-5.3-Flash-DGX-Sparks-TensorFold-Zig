#!/usr/bin/env bash
# queue118 - the fast screen for six never-measured GLM settings, one boot an arm.
#
# The purpose is to spend one boot per candidate, not five-level ABBA, and to kill the obvious losses
# and confirm the obvious wins before anything is measured properly.
#
# The rule, fixed before any row (also written to $R/RULE.txt on the box):
#   Levels: 1, 2 and 4 clients only, inside ONE boot per arm. The 6 and 8 client cells are excluded
#   because their boot-to-boot spread on this serve is 8 to 20%, which no single boot can screen; a
#   candidate that survives this screen is measured at those levels properly later.
#   DEAD      an arm more than 2.0% slower than the control at ANY of the three levels.
#   PROMISING an arm more than 2.0% faster than the control at any level, with NO level more than
#             1.0% slower. It graduates to a full arm.
#   UNCLEAR   everything else: within +-2%, or fast somewhere and slow somewhere. One confirm boot;
#             if the two boots agree within 1.0%, the setting stays at the engine default already recorded in
#             the env, and the register records it as measured-level with both rows. There is no default-ok
#             verdict: every setting is set explicitly, so 'level' is a measurement of the value in place.
#   A missing cell is NOT DECIDED for that arm, never a pass.
#
# The 2.0% dead band comes from the measured boot spread at these levels (1 to 3%), so a screen can
# only speak about differences larger than that, and it is not evidence for anything smaller.
set -uo pipefail
cd "$HOME/work/glm53-zig" || exit 1
G="$HOME/work/glm53-zig"; OUT="$HOME/bench"; R="$OUT/screen118"
IMG=${IMG:-glm53-zig:m130a}
[ -f "$G/queue118.env" ] && . "$G/queue118.env"
WORKERS=${WORKERS:?set WORKERS}
W1=${WORKERS%% *}; W2=${WORKERS##* }
# pair list: label|settings. Written as separate lines; a backslash-continued string collapses them
# into one line, which sent the whole list into the control's env and killed its boot.
mkdir -p "$R" "$OUT/screen118-boots"
PAIRS_FILE=${PAIRS_FILE:-$R/pairs.txt}
if [ ! -f "$PAIRS_FILE" ]; then
  cat > "$PAIRS_FILE" <<'PAIRS'
ctl|
conf|TF_GLM_DRAFT_CONFIDENCE=0.6
nodes|TF_DRAFT_NODES=8
steps|TF_GLM_PROMPT_STEPS=0
shared|TF_GLM_SHARED=0
linkwait|TF_GLM_LINK_WAIT=1
hostcache|TF_GLM_HOST_CACHE=1
PAIRS
fi

log() { echo "[s18] $(date -u +%T) $*"; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "SCREEN118-DONE $(date -u +%T)"; }
trap finish EXIT

ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1" 2>/dev/null; done; } )
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then
  log "IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS"; exit 1
fi
log "$IMG one id on three ranks: $(echo $ids | cut -c1-40)"
bash prod-stop.sh > /dev/null 2>&1 || { log "PRODUCTION DID NOT STOP"; exit 1; }

while IFS='|' read -r label xenv; do
  [ -z "$label" ] && continue
  d="$R/$label"
  if [ -f "$d/P4.jsonl" ]; then log "$label already done; skip"; continue; fi
  stop
  docker run --rm --privileged --entrypoint sh "$IMG" -c 'sync; echo 3 > /proc/sys/vm/drop_caches' > /dev/null 2>&1
  log "$label boot (xenv='${xenv}')"
  if [ -n "$xenv" ]; then XE="-e $xenv"; else XE=""; fi
  IMAGE="$IMG" KNOBS=dev XENV="$XE" bash zig-tp3.sh 4 1048576 > "$OUT/screen118-boots/$label.log" 2>&1 \
    || { log "$label BOOT FAILED: $(tail -2 "$OUT/screen118-boots/$label.log" | tr '\n' ' ' | cut -c1-160)"; continue; }
  mkdir -p "$d"
  for N in 1 2 4; do
    python3 streams.py 8300 "$N" --kind prose --max-tokens 400 --rounds 3 --tag "s18-$label-$N" \
      --out "$d/P$N.jsonl" > "$d/P$N.out" 2>&1
    echo "[s18] $label P$N rc=$? $(grep -o '"agg_tok_s": [0-9.]*' "$d/P$N.jsonl" 2>/dev/null | head -1)"
  done
done < "$PAIRS_FILE"
log "done; compare each arm against ctl in $R"
