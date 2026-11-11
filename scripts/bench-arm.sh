#!/usr/bin/env bash
# bench-arm.sh IMAGE TAG - one arm of the stock-vs-patches benchmark: for P=1,2,4,6,8
# (a fresh boot per level, the fleet rule), boot the image and run the recipe's streams
# instrument, saving the JSONL and the console output per level. Digests in the JSONL are
# the cross-arm bit check (same prompts, same rounds).
#   bash bench-arm.sh glm53-zig:pin9c9 pin
#   bash bench-arm.sh glm53-zig:9c9bf54 full
set -uo pipefail
IMAGE=${1:?usage: bench-arm.sh IMAGE TAG}; TAG=${2:?usage: bench-arm.sh IMAGE TAG}
OUT="$HOME/bench/$TAG"; mkdir -p "$OUT"
G="$HOME/work/glm53-zig"
for P in 1 2 4 6 8; do
  echo "[bench $TAG] P=$P boot at $(date +%T)"
  IMAGE="$IMAGE" KNOBS="${KNOBS:-off}" DRAFTER="${DRAFTER:-1}" CTX="${CTX:-}" bash "$G/zig-tp3.sh" "$P" > "$OUT/boot-P$P.log" 2>&1 \
    || { echo "[bench $TAG] BOOT FAILED P=$P"; bash "$G/zig-tp3-stop.sh" >/dev/null 2>&1; sleep 10; continue; }
  python3 "$G/streams.py" 8300 "$P" --kind prose --max-tokens 400 --rounds 3 \
      --tag "$TAG-P$P" --out "$OUT/P$P.jsonl" > "$OUT/P$P.out" 2>&1 \
    || echo "[bench $TAG] STREAMS FAILED P=$P"
  tail -3 "$OUT/P$P.out" 2>/dev/null
  bash "$G/zig-tp3-stop.sh" >/dev/null 2>&1
  sleep 10
done
echo "DONE $TAG at $(date +%T)"
