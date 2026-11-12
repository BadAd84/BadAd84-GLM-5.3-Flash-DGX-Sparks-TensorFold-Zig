#!/usr/bin/env bash
# mkpatch.sh OUT HEADER A_DIR TREE PATH... - a patch file from saved pre-change copies: for each PATH, the diff from
# A_DIR/PATH (the file as it was before the change) to TREE/PATH; a PATH with no saved copy is written as a new file.
# HEADER (From / Subject / body, ending in a blank line) is copied in front. Run from the repo root.
# The way to cut one patch: copy every file you are about to edit into A_DIR under its tree-relative path, edit the
# tree, then run this. `git apply --check` of OUT on a tree without the change is the proof it is complete.
set -uo pipefail
OUT=${1:?out}; HDR=${2:?header}; A=${3:?a dir}; TREE=${4:?tree}; shift 4
cat "$HDR" > "$OUT"
for p in "$@"; do
  [ -f "$TREE/$p" ] || { echo "mkpatch: no $TREE/$p" >&2; exit 1; }
  echo "diff --git a/$p b/$p" >> "$OUT"
  if [ -f "$A/$p" ]; then
    diff -u --label "a/$p" --label "b/$p" "$A/$p" "$TREE/$p" >> "$OUT"
  else
    echo "new file mode 100644" >> "$OUT"
    diff -u --label /dev/null --label "b/$p" /dev/null "$TREE/$p" >> "$OUT"
  fi
done
echo "$OUT: $(grep -c '^@@' "$OUT") hunks, $(grep -c '^+[^+]' "$OUT") added, $(grep -c '^-[^-]' "$OUT") removed"
