#!/usr/bin/env bash
# queue122 - the HC_DEC arm on the image built from its package, against the same image with the switch off.
#
# The package is screened (check fmt test ctest rc 0 on tree e1f52b62b7a2) and its engine code is in the image;
# what has never been measured on THIS series is whether rows under 64 on hc.cu's grid, launched dependently
# under PDL_EARLY, is faster than today's hc_partial8 path. The fork's +1.0% at P8 and +0.4% at P4 predate the
# re-seat and are not evidence.
#
# The rule, before any row: adopt TF_GLM_OVN_HC_DEC=1 when it is not more than 1.0% slower at any of 1, 2, 4, 6
# and 8 clients and at least 1.0% faster in the mean of the five. A level whose two control boots disagree by more
# than 3% is NOT DECIDED for that level rather than a loss. Two boots a side, levels measured inside each boot.
set -uo pipefail
cd "$HOME/work/glm53-zig" || exit 1
G="$HOME/work/glm53-zig"; OUT="$HOME/bench"; R="$OUT/hc-dec-arm"
IMG=${IMG:-glm53-zig:hc1}
[ -f "$G/queue122.env" ] && . "$G/queue122.env"
WORKERS=${WORKERS:?set WORKERS}
W1=${WORKERS%% *}; W2=${WORKERS##* }
WAIT_FOR=${WAIT_FOR:-}

log() { echo "[hc] $(date -u +%T) $*"; }
if [ -z "$WAIT_FOR" ] && [ "${ALLOW_NOWAIT:-0}" != 1 ]; then
  log "no WAIT_FOR; refusing to boot beside another queue"; exit 1
fi
log "start; waiting for $WAIT_FOR and for the image"
while pgrep -f "bash $WAIT_FOR" > /dev/null; do sleep 20; done
# the image is built by the chain AFTER the queue this waits on, so wait for the image itself rather than a process
# the build finishes locally first and dist copies to spark2 and spark3 afterwards, so the image must
# be waited for on ALL THREE ranks; checking only here is what failed the check on the next line
have_all() {
  local ids n
  ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1" 2>/dev/null; done; } )
  n=$(echo "$ids" | grep -c .)
  [ "$n" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]
}
for i in $(seq 1 240); do have_all && break; sleep 30; done
have_all || { log "image $IMG never reached all three ranks after two hours; stopping"; exit 1; }

stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "HCDEC-DONE $(date -u +%T)"; }
trap finish EXIT
mkdir -p "$R" "$OUT/hc-dec-boots"

ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1" 2>/dev/null; done; } )
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then
  log "IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS (is the build finished and distributed?)"; exit 1
fi
bash prod-stop.sh > /dev/null 2>&1 || { log "PRODUCTION DID NOT STOP"; exit 1; }

run() { # run LABEL XENV
  local label=$1 xe=$2
  local d="$R/$label"; mkdir -p "$d"
  if [ -f "$d/P8.jsonl" ]; then log "$label done; skip"; return 0; fi
  stop
  docker run --rm --privileged --entrypoint sh "$IMG" -c 'sync; echo 3 > /proc/sys/vm/drop_caches' > /dev/null 2>&1
  log "$label boot (xenv='${xe}')"
  IMAGE="$IMG" KNOBS=dev XENV="$xe" bash zig-tp3.sh 4 1048576 > "$OUT/hc-dec-boots/$label.log" 2>&1 \
    || { log "$label BOOT FAILED: $(tail -2 "$OUT/hc-dec-boots/$label.log" | tr '\n' ' ' | cut -c1-140)"; return 1; }
  for N in 1 2 4 6 8; do
    python3 streams.py 8300 "$N" --kind prose --max-tokens 400 --rounds 3 --tag "hc-$label-$N" \
      --out "$d/P$N.jsonl" > "$d/P$N.out" 2>&1
  done
  log "$label levels: $(for N in 1 2 4 6 8; do grep -o '\"agg_tok_s\": [0-9.]*' "$d/P$N.jsonl" 2>/dev/null | head -1 | sed 's/.*: //' | tr -d '\n'; printf ' '; done)"
}

run ctl1 ""
run dec1 "-e TF_GLM_OVN_HC_DEC=1"
run dec2 "-e TF_GLM_OVN_HC_DEC=1"
run ctl2 ""
log "done; compare in $R"
