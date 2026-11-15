#!/usr/bin/env bash
# apply.sh [--check] TREE - apply this package to TREE; RECORD.md names the tree TREE must hold and the tree it makes.
# --check: every patch is checked and applied to a temporary index built from TREE's working tree; the working tree
# and TREE's own index are not touched. It prints the tree id the package would make.
set -euo pipefail
CHECK=0; [ "${1:-}" = "--check" ] && { CHECK=1; shift; }
TREE=${1:?usage: apply.sh [--check] TREE}
HERE=$(cd "$(dirname "$0")" && pwd)
git -C "$TREE" rev-parse --git-dir > /dev/null 2>&1 || { echo "no git checkout at $TREE" >&2; exit 2; }
idx=$(mktemp); rm -f "$idx"; trap 'rm -f "$idx"' EXIT  # git wants no file or a real index, not an empty one
GIT_INDEX_FILE=$idx git -C "$TREE" read-tree HEAD  # tracked files .gitignore matches (receipt logs) stay in the tree
GIT_INDEX_FILE=$idx git -C "$TREE" add -A
echo "before: $(GIT_INDEX_FILE=$idx git -C "$TREE" write-tree)"
n=0
for p in "$HERE"/*.patch; do
  if ! GIT_INDEX_FILE=$idx git -C "$TREE" apply --cached --check "$p" 2>/dev/null; then
    echo "does not apply: $(basename "$p")" >&2; exit 1
  fi
  GIT_INDEX_FILE=$idx git -C "$TREE" apply --cached "$p"
  [ "$CHECK" = 1 ] || git -C "$TREE" apply "$p"
  n=$((n + 1))
done
echo "$([ "$CHECK" = 1 ] && echo checked || echo applied) $n patch(es); tree id: $(GIT_INDEX_FILE=$idx git -C "$TREE" write-tree)"
