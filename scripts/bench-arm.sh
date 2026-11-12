#!/usr/bin/env bash
# bench-arm.sh IMAGE TAG - one arm of the stock-vs-patches benchmark: for P=1,2,4,6,8
# (a fresh boot per level, the fleet rule), boot the image and run the recipe's streams
# instrument, saving the JSONL and the console output per level. Digests in the JSONL are
# the cross-arm bit check (same prompts, same rounds).
#   bash bench-arm.sh glm53-zig:pin9c9 pin
#   bash bench-arm.sh glm53-zig:9c9bf54 full
# Env: KNOBS, DRAFTER, CTX, XENV, XSERVE as zig-tp3.sh; LEVELS (default "1 2 4 6 8") the stream counts to run;
#      SARGS extra streams.py arguments (for example "--pad 6000" for a long prompt pass).
# Each level also keeps rank 0's engine log (its last 800 lines) as r0-P<N>.log: the startup facts and the per-request
# lines (kept states, paired prompt steps) a cell's numbers are read against.
set -uo pipefail
IMAGE=${1:?usage: bench-arm.sh IMAGE TAG}; TAG=${2:?usage: bench-arm.sh IMAGE TAG}
OUT="$HOME/bench/$TAG"; mkdir -p "$OUT"
G="$HOME/work/glm53-zig"
read -r -a SA <<< "${SARGS:-}"
for P in ${LEVELS:-1 2 4 6 8}; do
  echo "[bench $TAG] P=$P boot at $(date +%T)"
  IMAGE="$IMAGE" KNOBS="${KNOBS:-off}" DRAFTER="${DRAFTER:-1}" CTX="${CTX:-}" bash "$G/zig-tp3.sh" "$P" > "$OUT/boot-P$P.log" 2>&1 \
    || { echo "[bench $TAG] BOOT FAILED P=$P"; bash "$G/zig-tp3-stop.sh" >/dev/null 2>&1; sleep 10; continue; }
  python3 "$G/streams.py" 8300 "$P" --kind prose --max-tokens 400 --rounds 3 "${SA[@]}" \
      --tag "$TAG-P$P" --out "$OUT/P$P.jsonl" > "$OUT/P$P.out" 2>&1 \
    || { echo "[bench $TAG] STREAMS FAILED P=$P"; docker logs --tail 12 glm53-zig-r0 > "$OUT/fail-P$P.log" 2>&1; }
  tail -3 "$OUT/P$P.out" 2>/dev/null
  docker logs glm53-zig-r0 2>&1 | grep -a "^info\|^warn\|^error\|^debug" | tail -n 800 > "$OUT/r0-P$P.log"
  bash "$G/zig-tp3-stop.sh" >/dev/null 2>&1
  sleep 10
done
echo "DONE $TAG at $(date +%T)"
