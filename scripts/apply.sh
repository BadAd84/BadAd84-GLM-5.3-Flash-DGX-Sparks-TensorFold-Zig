#!/usr/bin/env bash
# Apply this recipe's engine patches to a fresh checkout of the pinned upstream engine.
#
#   scripts/apply.sh <work-dir> [engine-src]
#
# <work-dir> is created if absent and holds `tree/` (the engine at the pin plus every patch).
# [engine-src] is a local TensorFold clone to copy from; without it the pin is cloned from
# $TF_REPO. The pin is asserted before any patch is applied, so a moved ref fails loudly
# instead of building something unpinned.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"
# shellcheck source=/dev/null
. "$here/config.sh"

work="${1:?usage: scripts/apply.sh <work-dir> [engine-src]}"
src="${2:-}"
tree="$work/tree"

if ! git -C "$tree" rev-parse --git-dir >/dev/null 2>&1; then
  mkdir -p "$work"
  if [ -n "$src" ]; then
    cp -a "$src" "$tree"
  else
    git clone --quiet "$TF_REPO" "$tree"
  fi
fi

# the pin is immutable, so a clone is moved onto it rather than refused
if ! git -C "$tree" rev-parse --verify --quiet "$TF_REF^{commit}" >/dev/null; then
  git -C "$tree" fetch --quiet origin "$TF_REF" 2>/dev/null || true
fi
git -C "$tree" checkout --quiet --detach "$TF_REF"

got="$(git -C "$tree" rev-parse HEAD)"
if [ "$got" != "$TF_REF" ]; then
  echo "pin mismatch: tree is at $got, recipe pins $TF_REF" >&2
  echo "check out the pin first (git -C $tree checkout $TF_REF)" >&2
  exit 1
fi

applied=0
for p in "$root"/patches/engine/*.patch; do
  name="$(basename "$p")"
  if git -C "$tree" apply --check "$p" 2>/dev/null; then
    git -C "$tree" apply "$p"
    applied=$((applied + 1))
  elif git -C "$tree" apply --reverse --check "$p" 2>/dev/null; then
    echo "already applied: $name"
  else
    echo "does not apply: $name" >&2
    exit 1
  fi
done

echo "applied $applied patch(es) onto $TF_REF in $tree"
