#!/usr/bin/env bash
# bench-client.sh IMAGE TAG - bench-arm.sh's boot loop with another streams.py-shaped instrument: every level boots
# fresh through zig-tp3.sh, then CLIENT (a script beside zig-tp3.sh, then its own options) measures the serve and
# writes ~/bench/TAG/P<N>.jsonl as streams.py does. CLIENT defaults to measurement M-a's: streams_ids.py sending
# production's thinking-off rendering of the prose prompts as token ids (prose33.json) to /v1/completions. The
# NOISE arms set CLIENT=streams_sampled.py: seeded sampled chat requests, so digests stay equal across drafter arms.
# Env as bench-arm.sh: KNOBS, DRAFTER, CTX, XENV, XSERVE; LEVELS (default "1").
# On the head, beside zig-tp3.sh and streams.py: scp bench-client.sh, the client (and prose33.json) to ~/work/glm53-zig/.
#   XENV="<cr-ctl's list>" KNOBS=off bash ~/work/glm53-zig/bench-client.sh glm53-zig:rs2 ids-ctl
#   CLIENT=streams_sampled.py LEVELS="1 2 4 6 8" XENV="<list>" KNOBS=off bash ~/work/glm53-zig/bench-client.sh glm53-zig:rs2 sm-ctl
set -uo pipefail
IMAGE=${1:?usage: bench-client.sh IMAGE TAG}; TAG=${2:?usage: bench-client.sh IMAGE TAG}
OUT="$HOME/bench/$TAG"; mkdir -p "$OUT"
G="$HOME/work/glm53-zig"
read -r SCRIPT OPTS <<< "${CLIENT:-streams_ids.py --ids $G/prose33.json}"
for P in ${LEVELS:-1}; do
  echo "[bench-client $TAG] P=$P $SCRIPT boot at $(date +%T)"
  IMAGE="$IMAGE" KNOBS="${KNOBS:-off}" DRAFTER="${DRAFTER:-1}" CTX="${CTX:-}" bash "$G/zig-tp3.sh" "$P" > "$OUT/boot-P$P.log" 2>&1 \
    || { echo "[bench-client $TAG] BOOT FAILED P=$P"; bash "$G/zig-tp3-stop.sh" >/dev/null 2>&1; sleep 10; continue; }
  # shellcheck disable=SC2086  # OPTS is the client's own option list, split on purpose
  python3 "$G/$SCRIPT" 8300 "$P" $OPTS --max-tokens 400 --rounds 3 --tag "$TAG-P$P" --out "$OUT/P$P.jsonl" \
      > "$OUT/P$P.out" 2>&1 \
    || { echo "[bench-client $TAG] CLIENT FAILED P=$P"; docker logs --tail 12 glm53-zig-r0 > "$OUT/fail-P$P.log" 2>&1; }
  tail -3 "$OUT/P$P.out" 2>/dev/null
  docker logs glm53-zig-r0 2>&1 | grep -a "^info\|^warn\|^error\|^debug" | tail -n 800 > "$OUT/r0-P$P.log"
  bash "$G/zig-tp3-stop.sh" >/dev/null 2>&1
  sleep 10
done
echo "DONE $TAG at $(date +%T)"
