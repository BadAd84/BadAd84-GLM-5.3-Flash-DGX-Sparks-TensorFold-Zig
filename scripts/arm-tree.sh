#!/usr/bin/env bash
# arm-tree.sh N [OUTDIR] - an arm tree for the one-patch-at-a-time series: the pin + patches 0001..N + every repair
# patch (0032-0039) that belongs on that stack. Run from the repo root; needs work/pin/tree (a clone at the pin).
# Prints which repairs applied and which were refused, so two arms can be compared. OUTDIR defaults to work/s<N>.
# GIT (third argument) defaults to git.exe: work/pin/tree is a --shared clone whose alternates are Windows paths.
#
# What "belongs" means, each rule from a build that failed without it:
#   - a repair goes in when `git apply --check` takes it, except 0034, which passes the argument 0007 adds: its
#     context matches the pin's test file too, where the result does not compile, so it needs N >= 7;
#   - 0037 repairs what 0019 drops; where its context has moved (arms 19-22) arm-fill-fix.sh puts the line in;
#   - 0032 names kernels that later patches add: catalog-check.py drops the entries whose source the arm lacks.
set -uo pipefail
N=${1:?usage: arm-tree.sh N [OUTDIR]}
OUT=${2:-work/s$(printf %04d "$N")}
GIT=${3:-/mnt/c/Program Files/Git/cmd/git.exe}
[ -e "$OUT" ] && { echo "$OUT exists" >&2; exit 2; }
mkdir -p "$OUT"
ROOT=$(pwd)
"$GIT" -c core.autocrlf=false clone -q --shared work/pin/tree "$OUT/tree" || exit 1
cd "$OUT/tree" || exit 1
"$GIT" config core.autocrlf false
P="$ROOT/patches/engine"
for f in $(ls "$P"/*.patch | sort); do
  n=$((10#$(basename "$f" | cut -c1-4)))
  if [ "$n" -le "$N" ]; then
    "$GIT" apply --whitespace=nowarn "$(realpath --relative-to=. "$f")" || { echo "FAILED $(basename "$f")"; exit 1; }
  fi
done
applied=""; refused=""
for f in $(ls "$P"/*.patch | sort); do
  n=$((10#$(basename "$f" | cut -c1-4)))
  rel=$(realpath --relative-to=. "$f")
  if [ "$n" -ge 32 ] && [ "$n" -le 39 ] && [ "$n" -gt "$N" ]; then # 0032-0039 repair earlier patches; later ones add
    if [ "$n" = 34 ] && [ "$N" -lt 7 ]; then
      refused="$refused $n"
    elif "$GIT" apply --check --whitespace=nowarn "$rel" 2>/dev/null; then
      "$GIT" apply --whitespace=nowarn "$rel"; applied="$applied $n"
    else
      refused="$refused $n"
    fi
  fi
done
echo "arm $N: repairs applied:${applied:- none} refused:${refused:- none}"
case " $refused " in *" 37 "*) [ "$N" -ge 19 ] && bash "$ROOT/scripts/arm-fill-fix.sh" . ;; esac
python3 "$ROOT/scripts/catalog-check.py" --base "$ROOT/work/pin/tree" --fix .
