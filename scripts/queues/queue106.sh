#!/bin/bash
# queue106.sh - the cells that TF_GLM_OVN_DRAFT_NOISE=1 never had: sampled decode at 6 and 8 clients on the recipe as committed.
# The knob is in prod.env, and its own row in docs/KNOBS.md says "its 6 and 8 stream sampled cells are open". The repo's rule is that a knob ships only on
# cells at 1, 2, 4, 6 and 8, so this measures the missing two levels of the only cells it touches: the recipe as committed (the knob on, the default) against
# the same recipe with `-e TF_GLM_OVN_DRAFT_NOISE=0`. Eight boots, A B B A twice, order on1 off1 off2 on2 on3 off3 off4 on4, cells sampled prose and sampled
# code at 6 and 8 clients, three rounds each, into $HOME/bench/f106-c/dec-<label>/{SP6,SC6,SP8,SC8}.jsonl in queue91's row shape.
# queue106.env: IMG (glm53-zig:m130a), WORKERS, WAIT_FOR (default queue102.sh), HOURS. QUEUE106-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue106.env
IMG=${IMG:?set IMG}; WORKERS=${WORKERS:?set WORKERS}; WAIT_FOR=${WAIT_FOR:-queue102.sh}
W1=${WORKERS%% *}; W2=${WORKERS##* }
OUT=$HOME/bench; R=$OUT/f106-c
OFF="-e TF_GLM_OVN_DRAFT_NOISE=0"
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE106-DONE $(date -u +%T)"; }
echo "[q106] $(date -u +%T) start; waiting for $WAIT_FOR"
while pgrep -f "$WAIT_FOR" > /dev/null; do sleep 60; done
trap finish EXIT
mkdir -p "$R" "$OUT/f106-boots"
flag() { echo "[q106] $*" > "$R/ABORT"; echo "[q106] $*"; }
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then flag "IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS: nothing measured (ids: $(echo $ids | tr '\n' ' '))"; exit 1; fi
echo "[q106] $IMG ids: $(echo $ids | cut -c1-80); serve.sh $(sha256sum serve.sh | cut -c1-12); env $(cat env/prod.env env/dev.env | sha256sum | cut -c1-12)"
bash prod-stop.sh || { flag "PRODUCTION DID NOT STOP"; exit 1; }
unit() { # unit LABEL XENV: one fresh boot, the four sampled cells, three rounds each
  local label=$1 xenv=$2 dir="$R/dec-$1" n r
  stop
  IMAGE=$IMG KNOBS=prod XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/f106-boots/$label.log" 2>&1 \
    || { flag "BOOT FAILED $label: $(tail -3 "$OUT/f106-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1; }
  mkdir -p "$dir"
  for n in 6 8; do
    python3 streams_sampled.py 8300 "$n" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$label-SP$n" --out "$dir/SP$n.jsonl" > "$dir/SP$n.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$n" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$label-SC$n" --out "$dir/SC$n.jsonl" > "$dir/SC$n.out" 2>&1; local r2=$?
    echo "[q106] $(date -u +%T) $label at $n clients: sampled prose rc=$r1 $(agg "$dir/SP$n.out") code rc=$r2 $(agg "$dir/SC$n.out")"
  done
  docker logs glm53-zig-r0 2>&1 | grep -a -m1 'TF_GLM_OVN_DRAFT_NOISE' > "$R/$label-noise.txt" 2>/dev/null || true
  [ -s "$R/$label-noise.txt" ] || echo NONE > "$R/$label-noise.txt"
}
for arm in "on1|" "off1|$OFF" "off2|$OFF" "on2|" "on3|" "off3|$OFF" "off4|$OFF" "on4|"; do
  label=${arm%%|*}; xenv=${arm#*|}
  unit "$label" "$xenv" || { echo "[q106] stopping at $label; the rows so far are kept"; exit 1; }
done
echo "[q106] $(date -u +%T) done; score with: python scripts/queue-scores/score106.py --q106 ~/bench/f106-c"
