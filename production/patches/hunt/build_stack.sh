#!/bin/bash
# build_stack.sh <out dir> <list file>: a fresh copy of the synced base tree with every patch the list names applied in
# order (patch -p0 --batch from the directory holding tensorfold/). Lines: a patch path relative to this folder, or '#'
# comments. The base is BASE_TREE when set (a directory holding tensorfold/; the hunt record in scripts/glm53/v110/hunt
# holds no tree), else ./tree. Exit 1 on any failed hunk; prints one line a patch (failed / fuzz counts). Leaves no
# .orig/.rej files on success.
cd "$(dirname "$0")" || exit 1
OUT=$1 LIST=$2 BASE=${BASE_TREE:-tree}
[ -n "$OUT" ] && [ -f "$LIST" ] && [ -d "$BASE/tensorfold" ] || { echo "usage: [BASE_TREE=<base>] build_stack.sh <out> <list>"; exit 2; }
rm -rf "$OUT" && cp -r "$BASE" "$OUT" && rm -rf "$OUT/.kc" "$OUT/.tc" || exit 1
H=$(pwd)
bad=0
while read -r p; do
  case "$p" in ''|'#'*) continue ;; esac
  [ -f "$H/$p" ] || { echo "MISSING $p"; bad=1; continue; }
  r=$(cd "$OUT" && patch -p0 --batch < "$H/$p" 2>&1)
  nf=$(echo "$r" | grep -c "FAILED") nz=$(echo "$r" | grep -c "fuzz")
  echo "$(basename "$p"): $nf failed, $nz fuzz"
  [ "$nf" -eq 0 ] || { echo "$r" | grep -E "FAILED" | head -4; bad=1; }
done < "$LIST"
find "$OUT" -name "*.orig" -delete
[ "$(find "$OUT" -name '*.rej' | wc -l)" -eq 0 ] || { echo "REJECTS:"; find "$OUT" -name '*.rej'; bad=1; }
exit $bad
