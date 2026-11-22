#!/usr/bin/env bash
# queue117 - the receipt `0036`'s vec_x2 patch owes: the absorb and expand shares of the prompt path, and decode at
# 1 and 4 clients, on an image built from the patched tree.
#
# What the patch changed: absorb_rows<R, VEC> and expand_rows<R, VEC> take both the two-row step (one barrier pair a
# two rows) and eight-wide loads, where before the dispatch made the two forms exclusive and the vector form cost 1.0
# to 2.5% at decode. The vector form is now gated to rows >= prompt_rows through TF_GLM_OVN_ABSORB_VEC.
#
# What the receipt must show, written before any boot:
#   1. DIGESTS: the same replies as the m130a image at the same settings, cell for cell. A difference stops the report.
#   2. DECODE: 1 and 4 clients within the boot spread of m130a's cells (dev recipe: 81.6 at 1, 112.1 at 4 from queue116).
#      This is the point of the patch: decode must not pay what the vector form cost.
#   3. PROMPT: an nsys capture of rank 0 over one cold request each at 8k, 32k and 120k, for
#      `scripts/prefill_passes.py capture.sqlite passes` to compare the absorb and expand shares against ABSORB_VEC
#      alone's 765.5 ms over 1,419 launches and 841.4 ms over 935.
#
# A decode regression beyond the spread is a HOLD and goes back to the patch; a share that does not fall is a HOLD with
# the numbers; a digest difference is a stop and an owner report.
set -uo pipefail
cd "$HOME/work/glm53-zig" || exit 1
G="$HOME/work/glm53-zig"
OUT="$HOME/bench"; R="$OUT/f117-c"
IMG=${IMG:-glm53-zig:vecx2}
WORKERS=${WORKERS:?set WORKERS}
WAIT_FOR=${WAIT_FOR:-}
[ -f "$G/queue117.env" ] && . "$G/queue117.env"
W1=${WORKERS%% *}; W2=${WORKERS##* }

log() { echo "[q117] $(date -u +%T) $*"; }
if [ -z "$WAIT_FOR" ] && [ "${ALLOW_NOWAIT:-0}" != 1 ]; then
  log "no WAIT_FOR in queue117.env; refusing to boot beside another queue (ALLOW_NOWAIT=1 overrides)"; exit 1
fi
log "start; waiting for $WAIT_FOR"
while pgrep -f "bash $WAIT_FOR" > /dev/null; do sleep 30; done
log "waited $WAIT_FOR out; starting"

stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE117-DONE $(date -u +%T)"; }
trap finish EXIT
mkdir -p "$R" "$OUT/f117-boots"

ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1" 2>/dev/null; done; } )
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then
  log "IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS (run dist-image.sh first)"; exit 1
fi
log "$IMG ids: $(echo $ids | cut -c1-60)"

# ---- 1 and 2: decode at 1 and 4 clients, digests, on a plain boot
stop
log "decode boot"
IMAGE="$IMG" KNOBS=dev LEVELS="1 4" bash "$G/bench-arm.sh" "$IMG" "f117-c/dec" > "$OUT/f117-boots/dec.log" 2>&1
log "decode boot rc=$? ($(ls "$R/dec"/P*.jsonl 2>/dev/null | wc -l) levels)"

# ---- 3: an nsys capture of rank 0 over three cold prompts, then the three decode-free sizes
stop
log "capture boot"
WRAP0="nsys profile -o /out/r0 --trace=cuda --sample=none --cpuctxsw=none --force-overwrite true" \
XRUN0="-v $R/nsys:/out" IMAGE="$IMG" KNOBS=dev bash zig-tp3.sh 4 1048576 > "$OUT/f117-boots/capture.log" 2>&1 \
  || { log "CAPTURE BOOT FAILED: $(tail -2 "$OUT/f117-boots/capture.log" | tr '\n' ' ')"; exit 1; }
mkdir -p "$R/nsys"
for PK in 8192 32768 120000; do
  python3 - "$PK" "$R/ids-$PK.json" <<'PY'
import json, sys
n = int(sys.argv[1])
para = json.load(open("prose33.json"))[0]["ids"]
ids = list(para)
while len(ids) < n: ids.extend(para)
json.dump(ids[:n], open(sys.argv[2], "w"))
PY
  timeout 600 python3 tools-up/tools/bench_cache.py http://127.0.0.1:8300 ots-glm/glm-53-flash-exl3 \
    --prompt-file "$R/ids-$PK.json" --expected-prompt-tokens "$PK" --require-cold --tokens 8 --repeats 1 \
    --output "$R/cold-$PK.json" > "$R/cold-$PK.out" 2>&1
  log "cold $PK rc=$? $(grep -o '"qualified": [a-z]*' "$R/cold-$PK.json" 2>/dev/null | head -1)"
done
stop
sleep 5
ls -la "$R/nsys" | head -4

log "done; read the shares with scripts/prefill_passes.py over $R/nsys/r0.nsys-rep, and the decode cells in $R/dec"
