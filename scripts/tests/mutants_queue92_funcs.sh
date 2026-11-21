#!/bin/bash
# mutants_queue92_funcs.sh: faithful mutants of queue92.sh's cenv, readback and effect; each must make test_queue92_funcs.sh fail. Run from the repo root.
set -u
ROOT=$(pwd); SRC=scripts/queues/queue92.sh
D=$(mktemp -d "$ROOT/work/q101mut.XXXXXX"); trap 'rm -rf "$D"' EXIT
base=$(Q92=$ROOT/$SRC bash scripts/tests/test_queue92_funcs.sh > /dev/null 2>&1; echo $?)
echo "unmutated copy: test rc=$base (must be 0)"
[ "$base" = 0 ] || exit 1
n=0; killed=0
mut() { # mut NAME PATTERN REPLACEMENT : the anchor must match exactly once
  local name=$1 pat=$2 rep=$3 cnt
  cnt=$(grep -c -F -- "$pat" "$SRC")
  if [ "$cnt" != 1 ]; then echo "ANCHOR MISS ($cnt matches): $name"; return; fi
  python3 - "$SRC" "$D/m.sh" "$pat" "$rep" <<'EOF'
import sys
src, dst, pat, rep = sys.argv[1:5]
open(dst, "w", encoding="utf-8", newline="").write(open(src, encoding="utf-8", newline="").read().replace(pat, rep, 1))
EOF
  n=$((n + 1))
  local rc; rc=$(Q92=$D/m.sh bash scripts/tests/test_queue92_funcs.sh > "$D/out.txt" 2>&1; echo $?)
  if [ "$rc" != 0 ]; then killed=$((killed + 1)); echo "killed  $name (first failure: $(grep -m1 '^FAIL' "$D/out.txt" | cut -c1-90))"; else echo "SURVIVED $name"; fi
}
mut "comparison always true" '[ "$seen" = "$want" ] || { echo "[q92] $label: ${pair#*:} carries' 'true || { echo "[q92] $label: ${pair#*:} carries'
mut "DSCORES dropped from the checked names" 'for name in TF_GLM_DRAFT_SPLIT TF_GLM_DSCORES; do' 'for name in TF_GLM_DRAFT_SPLIT; do'
mut "DRAFT_SPLIT dropped from the checked names" 'for name in TF_GLM_DRAFT_SPLIT TF_GLM_DSCORES; do' 'for name in TF_GLM_DSCORES; do'
mut "rank readability guard removed" "grep -a -q '^TF_GLM_RANK=' ||" "true ||"
mut "rank 2 not checked" '"$W1:glm53-zig-r1" "$W2:glm53-zig-r2"; do' '"$W1:glm53-zig-r1"; do'
mut "rank 0 not checked" 'for pair in "-:glm53-zig-r0" "$W1:glm53-zig-r1"' 'for pair in "$W1:glm53-zig-r1"'
mut "effect drafter fallback removed" '[ -s "$OUT/f92-c/$label-drafter.txt" ] || echo MISSING > "$OUT/f92-c/$label-drafter.txt"' ':'
mut "effect dscores fallback removed" '[ -s "$OUT/f92-c/$label-dscores.txt" ] || echo NONE > "$OUT/f92-c/$label-dscores.txt"' ':'
mut "effect drafter keeps every match" "grep -a -m1 'dflash2: drafter from'" "grep -a 'dflash2: drafter from'"
mut "effect dscores pattern widened" "grep -a 'TF_GLM_DSCORES' >" "grep -a 'TF_GLM' >"
mut "want taken from the first name only" 'want=$(printf '"'"'%s\n'"'"' "$xenv" | grep -o "$name=[A-Za-z0-9_]*" | head -1)' 'want=$(printf '"'"'%s\n'"'"' "$xenv" | grep -o "TF_GLM_DRAFT_SPLIT=[A-Za-z0-9_]*" | head -1)'
mut "split limit raised to 0.9" 'g + 0 < 0.6' 'g + 0 < 0.9'
mut "split limit made inclusive" 'g + 0 < 0.6' 'g + 0 <= 0.6'
mut "split check never skips" "awk -v g=\"\${gib:-}\" 'BEGIN { exit !(g != \"\" && g + 0 < 0.6) }' ||" 'true ||'
mut "a missing drafter line passes" 'g != "" && g + 0 < 0.6' 'g + 0 < 0.6'
mut "split check tests the wrong value" 'if [ "$split" = 1 ]; then' 'if [ "$split" = 0 ]; then'
mut "split check runs on every arm" 'if [ "$split" = 1 ]; then' 'if true; then'
mut "gib parsed without its decimals" "grep -a -o '[0-9.]* GiB on the device'" "grep -a -o '[0-9]* GiB on the device'"
echo "mutants run $n, killed $killed"
[ "$n" = "$killed" ]
