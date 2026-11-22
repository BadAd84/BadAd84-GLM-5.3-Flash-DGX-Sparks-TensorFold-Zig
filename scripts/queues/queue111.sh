#!/usr/bin/env bash
# queue111 - the prefill-behind-decode controls with prompts that are actually long.
#
# queue108 read NOT DECIDED because `bench_concurrent.py --mixed` uses the built-in short prompt pool and the tool
# refuses `--prompts` together with `--mixed`, so no request ever held a long prompt behind decoders. This queue does
# what that one intended: upstream's own `bench_concurrent.py` with `--prompts` on a JSON list whose long entry is
# about 8,300 tokens, at levels 4 and 8, the same eight mirrored arms and the same scorer (score108.py's rules are the
# rule; there is one implementation of it).
#
# The base is KNOBS=dev, the recipe plus every candidate this repo carries, because that is the configuration under
development; prod.env is the frozen baseline the campaign compares against and is not what an arm here runs.
#
# Reading the verdict: score108.py --q108 <dir>. Its W0 refuses any run whose 8-stream cell never carried a request
# above 8,000 prompt tokens, W2 needs decode within 1.0% at both levels, W3 needs the worst wait at least 10% lower at
# both, and W4 adopts only when both levels win.
set -uo pipefail
cd "$HOME/work/glm53-zig" || exit 1
G="$HOME/work/glm53-zig"
OUT="$HOME/bench"
R="$OUT/f111-c"
MODEL=${MODEL:-ots-glm/glm-53-flash-exl3}
IMG=${IMG:-glm53-zig:m130a}
HOURS=${HOURS:-6}
WAIT_FOR=${WAIT_FOR:-}
[ -f "$G/queue111.env" ] && . "$G/queue111.env"
WORKERS=${WORKERS:?set WORKERS}
W1=${WORKERS%% *}; W2=${WORKERS##* }
B512="-e TENSORFOLD_PREFILL_BUDGET=512"
B2048="-e TENSORFOLD_PREFILL_BUDGET=2048"
S50="-e TENSORFOLD_PREFILL_SHARE=0.5"
T="$G/tools-up/tools"

log() { echo "[q111] $(date -u +%T) $*"; }
flag() { echo "[q111] $*" > "$R/ABORT"; log "$*"; }

if [ -z "$WAIT_FOR" ] && [ "${ALLOW_NOWAIT:-0}" != 1 ]; then
  log "no WAIT_FOR in queue111.env; refusing to boot beside another queue (ALLOW_NOWAIT=1 overrides)"
  exit 1
fi

log "start; waiting for $WAIT_FOR"
while pgrep -f "bash $WAIT_FOR" > /dev/null; do sleep 30; done
log "waited $WAIT_FOR out; starting"

stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE111-DONE $(date -u +%T)"; }
trap finish EXIT
mkdir -p "$R" "$OUT/f111-boots"

ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1" 2>/dev/null; done; } )
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then
  flag "IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS"; exit 1
fi
log "$IMG ids: $(echo $ids | cut -c1-60)"

# the prompt pool: one long entry above 8,000 tokens so the 8-stream cell always carries a prefill behind decoders
python3 - "$R/prompts-long.json" <<'PY' || { flag "PROMPT FILE FAILED"; exit 1; }
import json, sys
para = ("The calibration report covers a coordinate measuring machine whose bridge and Z column were serviced last "
        "quarter, and the probe head's linearisation table was rebuilt from the service tool after the wrist was "
        "swapped. Each section states a measurand, the reference artefact used, the number of repeats, and the "
        "observed spread against the manufacturer's tolerance. ")
body = para * 130          # about 11,000 tokens, comfortably above the 8,000 guard
short = para * 13          # about 1,000 tokens
items = [{"name": "long", "kind": "completion", "prompt": body},
         {"name": "short", "kind": "completion", "prompt": short}]
json.dump(items, open(sys.argv[1], "w"), indent=1)
print("prompt file:", len(body), len(short), "chars")
PY

for arm in "c1|" "b512a|$B512" "b2048a|$B2048" "s50a|$S50" "s50b|$S50" "b2048b|$B2048" "b512b|$B512" "c2|"; do
  label=${arm%%|*}; env=${arm#*|}
  dir="$R/$label"
  if [ -f "$dir/concurrent.json" ]; then log "$label already complete; skip"; continue; fi
  stop
  IMAGE=$IMG KNOBS=dev XENV="$env" bash zig-tp3.sh 4 1048576 > "$OUT/f111-boots/$label.log" 2>&1 \
    || { flag "BOOT FAILED $label: $(tail -2 "$OUT/f111-boots/$label.log" | tr '\n' ' ' | cut -c1-200)"; exit 1; }
  mkdir -p "$dir"
  python3 "$T/bench_concurrent.py" http://127.0.0.1:8300 "$MODEL" --levels 4,8 --tokens 256 --reps 3 \
    --prompts "$R/prompts-long.json" --label "$label" --output "$dir/concurrent.json" \
    > "$dir/concurrent.out" 2>&1
  log "$label: concurrent rc=$? $(grep -o '"aggregate_tps": [0-9.]*' "$dir/concurrent.out" 2>/dev/null | tr '\n' ' ')"
  docker logs glm53-zig-r0 2>&1 | grep -a 'prefill\|fill' | tail -n 40 > "$dir/fill-lines.txt" 2>/dev/null || true
done

log "done; score with: python scripts/queue-scores/score108.py --q108 $R"
