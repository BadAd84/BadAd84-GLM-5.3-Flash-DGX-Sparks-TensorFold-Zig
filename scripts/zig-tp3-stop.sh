#!/usr/bin/env bash
# zig-tp3-stop.sh - stop the recipe's Zig GLM TP=3 containers on spark1-3. Run from spark1.
set -uo pipefail
docker rm -f glm53-zig-r0 >/dev/null 2>&1 || true
for h in spark2 spark3; do
  ssh -n "adam@$h.ots-int.net" 'docker rm -f glm53-zig-r1 glm53-zig-r2 >/dev/null 2>&1 || true'
done
echo "[zig-tp3] stopped"
