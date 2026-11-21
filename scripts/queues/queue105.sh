#!/bin/bash
# queue105.sh - the 8-client confirmation that decides whether queue95's T and X candidate sets enter prod.env.
# Queue95 measured both PROMOTABLE on the 12 decode cells at 1, 2 and 4 clients, on the four prompt cells (+5.24/5.89/5.71 cold and +4.64 warm for T,
# +3.03/2.91/2.74 and +3.72 for X) and on the digests, and at 6 clients both are positive in all four cells. At 8 clients both arms are bimodal
# within one arm (T's boots land at about 116 or about 137 tok/s), so 8 clients is the only cell the rule has not settled and it is the only thing
# this queue measures. T and X run together (the additive arm): queue95's K5 read T+X at 8.26 / 8.81 / 8.45 / 8.35% against the bundle's 8.88 /
# 9.44 / 8.99 / 8.47, so the bundle is the sum of its parts. Eight boots, A B B A twice, order ca1 tx1 tx2 ca2 ca3 tx3 tx4 ca4, one image id on
# all three ranks, no build. Rows go to $HOME/bench/f105-c/dec-<label>/{P,C,SP,SC}8.jsonl in queue91's row shape, so score91's readers apply.
# queue105.env: IMG (glm53-zig:m130a) and WAIT_FOR (default queue94.sh). QUEUE105-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue105.env
IMG=${IMG:?set IMG}; WAIT_FOR=${WAIT_FOR:-queue94.sh}
OUT=$HOME/bench; R=$OUT/f105-c
T="-e TF_GLM_OVN_MM_WIDE=1 -e TF_GLM_OVN_SIDE_PRIO=1 -e TF_GLM_OVN_LATENT_ROWS=2 -e NCCL_NCHANNELS_PER_NET_PEER=4"
X="-e TF_GLM_OVERLAP_PIECES=4 -e TF_GLM_OVN_PIECE_FRONT=1 -e TF_GLM_OVN_PIECE_FFN=1 -e TF_GLM_OVN_PIECE_MLA=1 -e TF_GLM_OVN_SOLO_TO_START=1 -e TF_GLM_OVN_RESTORE_HELD=1"
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE105-DONE $(date -u +%T)"; }
echo "[q105] $(date -u +%T) start; waiting for $WAIT_FOR"
while pgrep -f "$WAIT_FOR" > /dev/null; do sleep 60; done
trap finish EXIT
mkdir -p "$R" "$OUT/f105-boots"
flag() { echo "[q105] $*" > "$R/ABORT"; echo "[q105] $*"; }
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in spark2 spark3; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "adam@$h.ots-int.net" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then flag "IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS: nothing measured (ids: $(echo $ids | tr '\n' ' '))"; exit 1; fi
echo "[q105] $IMG ids: $(echo $ids | cut -c1-80); serve.sh $(sha256sum serve.sh | cut -c1-12); env $(cat env/prod.env env/dev.env | sha256sum | cut -c1-12)"
bash prod-stop.sh || { flag "PRODUCTION DID NOT STOP"; exit 1; }
unit() { # unit LABEL XENV: one fresh boot and the four 8-client cells, three rounds each
  local label=$1 xenv=$2 dir="$R/dec-$1"
  stop
  IMAGE=$IMG KNOBS=prod XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/f105-boots/$label.log" 2>&1 \
    || { flag "BOOT FAILED $label: $(tail -3 "$OUT/f105-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1; }
  docker logs glm53-zig-r0 2>&1 | grep -a -m1 'dflash2: drafter from' > "$R/$label-drafter.txt" 2>/dev/null
  mkdir -p "$dir"
  python3 streams_ids.py 8300 8 --ids prose33.json --max-tokens 400 --rounds 3 --tag "$label-P8" --out "$dir/P8.jsonl" > "$dir/P8.out" 2>&1; local r1=$?
  python3 streams_ids.py 8300 8 --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$label-C8" --out "$dir/C8.jsonl" > "$dir/C8.out" 2>&1; local r2=$?
  python3 streams_sampled.py 8300 8 --ids prose33.json --max-tokens 400 --rounds 3 --tag "$label-SP8" --out "$dir/SP8.jsonl" > "$dir/SP8.out" 2>&1; local r3=$?
  python3 streams_sampled.py 8300 8 --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$label-SC8" --out "$dir/SC8.jsonl" > "$dir/SC8.out" 2>&1; local r4=$?
  echo "[q105] $(date -u +%T) $label 8 clients: prose rc=$r1 $(agg "$dir/P8.out") code rc=$r2 $(agg "$dir/C8.out") sampled prose rc=$r3 $(agg "$dir/SP8.out") sampled code rc=$r4 $(agg "$dir/SC8.out")"
}
for arm in "ca1|" "tx1|$T $X" "tx2|$T $X" "ca2|" "ca3|" "tx3|$T $X" "tx4|$T $X" "ca4|"; do
  label=${arm%%|*}; xenv=${arm#*|}
  unit "$label" "$xenv" || { echo "[q105] stopping at $label; the rows so far are kept"; exit 1; }
done
echo "[q105] $(date -u +%T) done; score with: python scripts/queue-scores/score105.py --q105 ~/bench/f105-c"
