#!/bin/bash
# queue-prod-compare.sh - on spark1, detached: in one sitting and with the SAME client (streams_ids.py, production's 33-token prompt ids, 400 tokens, 3 rounds, 1 2 4 6 8 streams):
#   pm1  production (the live serve on :8888), measured only while it is idle (no request running); a level is skipped, not forced, when production is busy
#   pd-a3  a Zig boot at production's deployed shape (--parallel 4 --context 1048576, the v1.2.9 stack, KNOBS=measured), production stopped for it
#   pm2  production again after its restore
# The three bracket production / Zig / production with one instrument (tables: python3 prod_table.py pm1 pd-a3 pm2, or cells.py). Production restored at the end; PRODCOMPARE-DONE.
# Env: WORKERS (required), IMG (default glm53-zig:v129t).
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
WORKERS=${WORKERS:?set WORKERS to the ssh targets of ranks 1 and 2, space separated}
export WORKERS
IMG=${IMG:-glm53-zig:v129t}
idle() { # idle: 0 when production answers /health with no request running
  python3 - <<'EOF'
import json, sys, urllib.request
try:
    d = json.load(urllib.request.urlopen("http://127.0.0.1:8888/health", timeout=5))
except Exception:
    sys.exit(2)
sys.exit(0 if (d.get("requests_running", 1) == 0 and not d.get("busy", True)) else 1)
EOF
}
wait_idle() { for i in $(seq 1 60); do idle && return 0; sleep 10; done; return 1; }
measure() { # measure TAG PORT: levels 1 2 4 6 8 with streams_ids.py, each only while the target is idle when PORT is 8888
  local tag=$1 port=$2 OUT="$HOME/bench/$1"; mkdir -p "$OUT"
  for N in 1 2 4 6 8; do
    if [ "$port" = 8888 ]; then wait_idle || { echo "[pc] $tag $N clients SKIPPED: production stayed busy"; continue; }; fi
    python3 "$G/streams_ids.py" "$port" "$N" --ids "$G/prose33.json" --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$OUT/P$N.jsonl" > "$OUT/P$N.out" 2>&1
    echo "[pc] $(date -u +%T) $tag $N clients rc=$? $(tail -1 "$OUT/P$N.out" | cut -c1-150)"
  done
}
restore_prod() {
  curl -sf localhost:8888/health > /dev/null 2>&1 || {
    setsid nohup bash ~/glm-v110-start.sh > "$HOME/bench/prod-restore-pc.log" 2>&1 < /dev/null &
    for i in $(seq 1 90); do curl -sf localhost:8888/health > /dev/null 2>&1 && break; sleep 10; done; }
}
restore_prod
wait_idle || echo "[pc] production not idle at the start: pm1 levels may be skipped"
measure pm1 8888
docker rm -f glm53-flash-tf samplers pwcap > /dev/null 2>&1; echo "[pc] production stopped for the Zig boot"
OUT="$HOME/bench/pd-a3"; mkdir -p "$OUT"
IMAGE=$IMG KNOBS=measured CTX=1048576 bash zig-tp3.sh 4 > "$OUT/boot.log" 2>&1 && measure pd-a3 8300 || echo "[pc] Zig BOOT FAILED"
bash zig-tp3-stop.sh > /dev/null 2>&1; docker rm -f glm53-zig-r0 > /dev/null 2>&1; sleep 10
restore_prod
curl -sf localhost:8888/health > /dev/null 2>&1 && echo "[pc] production healthy" || echo "[pc] PRODUCTION NOT HEALTHY"
wait_idle || echo "[pc] production not idle after its restore: pm2 levels may be skipped"
measure pm2 8888
curl -sf localhost:8888/health > /dev/null 2>&1 && echo "[pc] production healthy at the end" || echo "[pc] PRODUCTION NOT HEALTHY AT THE END"
echo "PRODCOMPARE-DONE $(date -u +%T)"
