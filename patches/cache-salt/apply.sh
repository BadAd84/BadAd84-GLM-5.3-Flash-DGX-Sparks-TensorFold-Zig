#!/usr/bin/env bash
# apply.sh [--check] TREE - apply this package (upstream PR #3222 re-seated, and patch 0003) to TREE, a checkout that
# scripts/apply.sh and then patches/pr1411/apply.sh made (v1.2.7 plus patches/engine plus patches/pr1411, uncommitted).
# --check: every patch is checked and applied to a temporary index built from TREE's working tree; the working tree
# and TREE's own index are not touched. It prints the tree id the package would make; RECORD.md names the expected one.
set -euo pipefail
CHECK=0; [ "${1:-}" = "--check" ] && { CHECK=1; shift; }
TREE=${1:?usage: apply.sh [--check] TREE}
HERE=$(cd "$(dirname "$0")" && pwd)
[ -d "$TREE/.git" ] || { echo "no git checkout at $TREE" >&2; exit 2; }
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
