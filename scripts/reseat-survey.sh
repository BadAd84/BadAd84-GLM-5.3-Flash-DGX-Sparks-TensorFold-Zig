#!/usr/bin/env bash
# reseat-survey.sh REF OUTDIR PATCHDIR... - how a patch series sits on another upstream base, before any re-seat work.
# Makes OUTDIR/tree, a pristine checkout of REF (a --shared clone of work/parity/tree, which holds upstream's
# history), then takes every .patch of the PATCHDIRs in file-name order and, against the tree as the patches before
# it left it, records one of:
#   clean      git apply --check takes it whole; it is applied
#   absorbed   it does not apply but its reverse does: the base already has every line of it; nothing is applied
#   partial    some hunks apply; it is applied with --reject (rejects counted, their .rej files removed), so later
#              patches are judged against as much of the series as will go on
#   refused    no hunk applies (files moved or gone); nothing is applied
# One line a patch on stdout and in OUTDIR/survey.tsv (name, verdict, hunks, rejected hunks, files, files missing in
# the base). A verdict here is about text only: a patch that applies clean can still be wrong on the new base, and
# an absorbed one still needs the commit that absorbed it named before it is retired.
set -uo pipefail
REF=${1:?usage: reseat-survey.sh REF OUTDIR PATCHDIR...}; OUT=${2:?out dir}; shift 2
GIT="/mnt/c/Program Files/Git/cmd/git.exe"
ROOT=$(pwd)
[ -e "$OUT" ] && { echo "$OUT exists" >&2; exit 2; }
mkdir -p "$OUT"
"$GIT" -c core.autocrlf=false clone -q --shared --no-checkout work/parity/tree "$OUT/tree" < /dev/null || exit 1
( cd "$OUT/tree" && "$GIT" config core.autocrlf false && "$GIT" -c advice.detachedHead=false checkout -q "$REF" < /dev/null ) || exit 1
echo "base $REF = $(cd "$OUT/tree" && "$GIT" rev-parse --short=10 HEAD < /dev/null)"
: > "$OUT/survey.tsv"
exec < /dev/null
for d in "$@"; do
  for f in $(ls "$ROOT/$d"/*.patch | sort); do
    name=$(basename "$f")
    rel=$(cd "$OUT/tree" && realpath --relative-to=. "$f")
    hunks=$(grep -c '^@@' "$f")
    files=$(grep -c '^diff --git ' "$f")
    missing=0
    for p in $(grep '^--- a/' "$f" | sed 's|^--- a/||'); do [ -f "$OUT/tree/$p" ] || missing=$((missing + 1)); done
    rej=0
    if ( cd "$OUT/tree" && "$GIT" apply --check --whitespace=nowarn "$rel" 2>/dev/null ); then
      ( cd "$OUT/tree" && "$GIT" apply --whitespace=nowarn "$rel" ); verdict=clean
    elif ( cd "$OUT/tree" && "$GIT" apply -R --check --whitespace=nowarn "$rel" 2>/dev/null ); then
      verdict=absorbed
    else
      ( cd "$OUT/tree" && "$GIT" apply --reject --whitespace=nowarn "$rel" > /dev/null 2>&1 )
      rej=$(find "$OUT/tree" -name '*.rej' -not -path '*/.git/*' -exec grep -c '^@@' {} + 2>/dev/null | awk -F: '{s += $NF} END {print s + 0}')
      find "$OUT/tree" -name '*.rej' -not -path '*/.git/*' -delete
      if [ "$rej" -ge "$hunks" ]; then verdict=refused; else verdict=partial; fi
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$verdict" "$hunks" "$rej" "$files" "$missing" | tee -a "$OUT/survey.tsv"
  done
done
echo "SURVEY: $(cut -f2 "$OUT/survey.tsv" | sort | uniq -c | tr '\n' ' ')"
