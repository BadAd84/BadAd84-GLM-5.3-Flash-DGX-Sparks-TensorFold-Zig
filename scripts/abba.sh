#!/usr/bin/env bash
# abba.sh MARKER_FILE MARKER IMAGE_A IMAGE_B TAG LEVELS [XENV_A [XENV_B]] - on the head: wait for MARKER in
# MARKER_FILE (pass /dev/null and "" to start at once), then rerun the stream counts in LEVELS in the order A B B A,
# a fresh boot each: cells ~/bench/TAG-a1, TAG-b1, TAG-b2, TAG-a2 (knobs off, drafter on). XENV_A goes to every rank
# of the A cells; the B cells take XENV_B, or XENV_A when no XENV_B is given (two images, one environment). With one
# image and two environments it compares a switch. For confirming or clearing one losing cell of an A/B: compare the
# two A cells with the two B cells, and read A1 against A2 for the drift between boots. Ends with ABBA-DONE.
set -uo pipefail
FILE=${1:?usage: abba.sh MARKER_FILE MARKER IMAGE_A IMAGE_B TAG LEVELS [XENV_A [XENV_B]]}; MARK=$2
A=${3:?image A}; B=${4:?image B}; TAG=${5:?tag}; LV=${6:?levels}; XA=${7:-}; XB=${8-$XA}
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "$MARK" ]; then until grep -q "$MARK" "$FILE" 2>/dev/null; do sleep 30; done; fi
echo "[abba] $(date +%T) $TAG: A=$A [$XA] B=$B [$XB] levels [$LV]"
for cell in a1 b1 b2 a2; do
  case "$cell" in a*) img=$A; xe=$XA ;; *) img=$B; xe=$XB ;; esac
  XENV="$xe" LEVELS="$LV" KNOBS=off DRAFTER=1 bash "$here/bench-arm.sh" "$img" "$TAG-$cell" < /dev/null
done
echo "ABBA-DONE $(date +%T)"
