#!/usr/bin/env bash
# words.sh ENV [SECTION] - the settings of scripts/env/ENV.env (ENV: prod or dev) as NAME=value words on one line, the shape serve.sh's DEFS had.
# SECTION is runtime, recipe, candidates or all (default all); a section starts at its `# --- NAME` line (prod.env has runtime and recipe, dev.env those and candidates).
# Blank lines and # comments are skipped; a line that is not NAME=value with no space in the value is refused.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
f=${1:?usage: words.sh ENV [runtime|recipe|all]}; want=${2:-all}
[[ $f = prod || $f = dev ]] || { echo "words.sh: ENV is prod or dev, not '$f'" >&2; exit 2; }
[[ $want = runtime || $want = recipe || $want = candidates || $want = all ]] || { echo "words.sh: SECTION is runtime, recipe, candidates or all" >&2; exit 2; }
[[ -r $here/$f.env ]] || { echo "words.sh: no $here/$f.env" >&2; exit 2; }
out=(); sec=runtime
while IFS= read -r line || [[ -n $line ]]; do
  line=${line#"${line%%[![:space:]]*}"}
  if [[ $line =~ ^"# --- "(runtime|recipe|candidates)([[:space:]]|$) ]]; then sec=${BASH_REMATCH[1]}; continue; fi
  [[ -z $line || $line == \#* ]] && continue
  [[ $want = all || $want = "$sec" ]] || continue
  line=${line%% #*}
  line=${line%"${line##*[![:space:]]}"}
  [[ $line =~ ^[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*$ ]] || { echo "words.sh: bad line in $f.env: $line" >&2; exit 2; }
  out+=("$line")
done < "$here/$f.env"
echo "${out[*]}"
