#!/usr/bin/env bash
# restack.sh LIST BASE_N OUTDIR - cut numbered patches for patches/engine from lane patches, in a final order.
# LIST lines: `NNNN-slug.patch|source patch|fixup script (optional)|extra paths the fixup touches (space separated)`.
# Makes a fresh arm tree (pin + patches/engine through BASE_N) in OUTDIR/tree; for each line, saves the files the
# source patch (and the fixup) touches, applies the source patch with `git apply` (a refusal stops the run), runs the
# fixup script with the tree as its argument if one is named, and cuts OUTDIR/NNNN-slug.patch with scripts/mkpatch.sh:
# the source patch's own header in front of the diff from the saved files to the tree. So every output patch is what
# the tree actually did at that step, whatever was merged by hand, and the outputs applied in order rebuild the tree.
# Blank lines and # lines are skipped. Run from the repo root under WSL.
set -uo pipefail
LIST=${1:?usage: restack.sh LIST BASE_N OUTDIR}; N=${2:?base patch number}; OUT=${3:?out dir}
GIT="/mnt/c/Program Files/Git/cmd/git.exe"
ROOT=$(pwd)
[ -e "$OUT" ] && { echo "$OUT exists" >&2; exit 2; }
bash scripts/arm-tree.sh "$N" "$OUT" | tail -2 || exit 1
while IFS='|' read -r name src fix extra; do
  case "$name" in ''|'#'*) continue ;; esac
  step="$OUT/steps/${name%.patch}"; mkdir -p "$step/a"
  paths=$( { grep '^diff --git ' "$src" | sed 's|^diff --git a/||; s| b/.*||'; for p in $extra; do echo "$p"; done; } | sort -u )
  for p in $paths; do
    if [ -f "$OUT/tree/$p" ]; then mkdir -p "$step/a/$(dirname "$p")"; cp "$OUT/tree/$p" "$step/a/$p"; fi
  done
  ( cd "$OUT/tree" && "$GIT" apply --whitespace=nowarn "$(realpath --relative-to=. "$ROOT/$src")" ) || { echo "REFUSED $name ($src)"; exit 1; }
  if [ -n "$fix" ]; then bash "$fix" "$OUT/tree" || { echo "FIXUP FAILED $name ($fix)"; exit 1; }; fi
  awk '/^diff --git /{exit} {print}' "$src" > "$step/header.txt"
  live=""
  for p in $paths; do
    if [ -f "$OUT/tree/$p" ]; then live="$live $p"
    elif [ -f "$step/a/$p" ]; then echo "restack: $name deletes $p, which mkpatch.sh cannot record" >&2; exit 1; fi
  done
  # shellcheck disable=SC2086
  bash scripts/mkpatch.sh "$OUT/$name" "$step/header.txt" "$step/a" "$OUT/tree" $live || exit 1
done < "$LIST"
echo "RESTACK-DONE $(ls "$OUT"/*.patch | wc -l) patches in $OUT"
