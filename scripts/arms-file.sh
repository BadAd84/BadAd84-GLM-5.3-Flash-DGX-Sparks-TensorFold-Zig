#!/usr/bin/env bash
# arms-file.sh MARKER_FILE MARKER ARMS_FILE [IMAGE] - on the head: wait until MARKER appears in MARKER_FILE
# (the job ahead on these GPUs; pass /dev/null and "" to start at once), then run one bench-arm.sh arm per
# line of ARMS_FILE. A line is `tag|extra -e arguments|streams.py arguments|levels`: XENV for every rank, extra
# arguments for the instrument (for example --pad 6000) and the stream counts (default 1 2 4 6 8); the last
# three may be empty. Blank lines and # lines are skipped. Every arm: knobs off, drafts on, a fresh boot per
# level. Ends with ARMS-FILE-DONE.
set -uo pipefail
FILE=${1:?usage: arms-file.sh MARKER_FILE MARKER ARMS_FILE [IMAGE]}; MARK=$2; ARMS=${3:?arms file}
IMAGE=${4:-glm53-zig:fix4}
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "$MARK" ]; then until grep -q "$MARK" "$FILE" 2>/dev/null; do sleep 30; done; fi
echo "[arms] $(date +%T) starting $ARMS on $IMAGE"
while IFS='|' read -r tag xenv sargs levels; do
  case "$tag" in ''|'#'*) continue ;; esac
  echo "[arms] $(date +%T) $tag: env [${xenv:-}] streams [${sargs:-}] levels [${levels:-1 2 4 6 8}]"
  XENV="$xenv" SARGS="${sargs:-}" LEVELS="${levels:-1 2 4 6 8}" KNOBS=off DRAFTER=1 bash "$here/bench-arm.sh" "$IMAGE" "$tag" < /dev/null
done < "$ARMS"
echo "ARMS-FILE-DONE $(date +%T)"
