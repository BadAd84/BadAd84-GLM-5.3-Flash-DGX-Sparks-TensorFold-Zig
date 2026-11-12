#!/usr/bin/env bash
# series-chain.sh MARKER_FILE MARKER TAG... - on the head: wait until MARKER appears in MARKER_FILE (the job
# ahead on these GPUs), then for each TAG build ai-engine:TAG from ~/work/glm53-zig/TAG-src.tar, copy the image
# to the two workers and bench it (bench-arm.sh: P=1,2,4,6,8, knobs off, drafts on). Strictly one after
# another: a build beside a bench shares the box's memory bandwidth and would move the cells.
# A tag whose build fails is logged and skipped. Log lines go to stdout; cells to ~/bench/TAG/. With NOBENCH=1 the
# images are built and distributed only (a stage queued behind this one runs its own cells on them).
set -uo pipefail
FILE=${1:?usage: series-chain.sh MARKER_FILE MARKER TAG...}; MARK=${2:?marker}; shift 2
G="$HOME/work/glm53-zig"; cd "$G" || exit 1
until grep -q "$MARK" "$FILE" 2>/dev/null; do sleep 30; done
echo "[series] $(date +%T) $MARK seen, starting: $*"
fails=0
for tag in "$@"; do
  if ! docker image inspect "ai-engine:$tag" >/dev/null 2>&1; then
    bash "$G/ai-build.sh" "$tag" "$G/$tag-src.tar" > "$G/build-$tag.out" 2>&1 \
      || { fails=$((fails + 1)); echo "[series] $(date +%T) $tag BUILD FAILED: $(grep -a "error:" "$G/build-$tag.out" | head -3 | cut -c1-200)"; continue; }
  fi
  ok=1
  for w in spark2 spark3; do
    docker save "ai-engine:$tag" | ssh -o BatchMode=yes "adam@$w.ots-int.net" docker load >/dev/null 2>&1 || ok=0
  done
  [ "$ok" = 1 ] || { fails=$((fails + 1)); echo "[series] $(date +%T) $tag DISTRIBUTE FAILED"; continue; }
  echo "[series] $(date +%T) $tag built and distributed"
  [ "${NOBENCH:-0}" = 1 ] && continue
  XENV="" KNOBS=off DRAFTER=1 bash "$G/bench-arm.sh" "ai-engine:$tag" "$tag" > "$G/bench-$tag.out" 2>&1
  echo "[series] $(date +%T) $tag benched"
done
# With STRICT=1 a failed build holds the stages queued behind this one: they wait on the DONE marker.
if [ "${STRICT:-0}" = 1 ] && [ "$fails" -gt 0 ]; then echo "SERIES-CHAIN-FAILED $(date +%T) ($fails)"; exit 1; fi
echo "SERIES-CHAIN-DONE $(date +%T)"
