#!/bin/bash
# queue114.sh - the targeted rerun of the one cell queue113 held both arms on: sampled code at eight clients. Nothing else is measured.
# queue113 (score113.py) read T at cold -7.13% and X at -2.83%, every four-client cell inside half a percent, and held both arms on sampled code at eight
# clients (+2.05% for T, +1.78% for X). That cell is also queue113's widest control spread (11.57%, 160.6 to 180.1 against 4.7 to 9.6% in the other three),
# so the reading sits inside a boot-to-boot spread five times its size and the cell, not the verdict, is what this queue re-measures. QUEUE114-DONE.
# queue114.env: IMG (glm53-zig:m130a) and WORKERS, the names queue91.sh requires from queue91.env, plus HOURS (default 5) and WAIT_FOR (none by default);
# those two have defaults, so a file that omits them still runs.
#
#   image: IMG must be ONE id on all three ranks, as in queue102 and queue113: absent from spark1, or a different id on a rank, stops the queue with a
#     line, and nothing is built here.
#   arms, exactly as queue113 ran them (env-exact, never file-dependent): every boot is KNOBS=dev and names all ten T/X variables through XENV:
#     control (the recipe with neither): all ten off, "off" the recipe's own resolved value (0 for the switches, LATENT_ROWS=0, OVERLAP_PIECES=8,
#             NCCL_NCHANNELS_PER_NET_PEER=1)
#     T alone: MM_WIDE=1, SIDE_PRIO=1, LATENT_ROWS=2, NCHANNELS_PER_NET_PEER=4; X off
#     X alone: OVERLAP_PIECES=4, PIECE_FRONT=1, PIECE_FFN=1, PIECE_MLA=1, SOLO_TO_START=1, RESTORE_HELD=1; T off
#     dev.env's ABSORB_VEC stays set in every arm. The readback refuses a boot whose ten values or image id differ from its arm's, and refuses the whole
#     queue without TF_GLM_ROCE_MULTI=1, because without the wire the recipe's OWN OVERLAP_PIECES would resolve to 3 and the control would not be the recipe.
#   eighteen boots, mirrored: c1 t1 x1 x2 t2 c2 c3 t3 x3 x4 t4 c4 c5 t5 x5 x6 t6 c6 - six control, six T, six X, each arm's six straddling the run and
#     each control pair bracketing an arm pair in one orientation then the other. Every boot runs ONE cell: streams_sampled.py at 8 clients on code_ids,
#     three rounds of 400 tokens, rows to $HOME/bench/f114-c/dec-<label>/SC8.jsonl in the queue's own shape (agg_tok_s and sha a round). No cold probe,
#     no four-client cell, no 24 prompts: those readings are queue113's and are not repeated.
#   guards: the first boot smoke-probes streams_sampled once, tiny, before a unit is spent; every boot's environment is read back on all three ranks and
#     kept as $HOME/bench/f114-c/<label>-env.txt; rank 0's log is kept a boot.
#   scripts/queue-scores/score114.py reads the rows; its rules were written before they existed (score114.py's docstring, the NOISE clause included).
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue114.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=${IMG:?set IMG}
WAIT_FOR=${WAIT_FOR:-}
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench; R=$OUT/f114-c
VARS=(TF_GLM_OVN_MM_WIDE TF_GLM_OVN_SIDE_PRIO TF_GLM_OVN_LATENT_ROWS NCCL_NCHANNELS_PER_NET_PEER TF_GLM_OVERLAP_PIECES
      TF_GLM_OVN_PIECE_FRONT TF_GLM_OVN_PIECE_FFN TF_GLM_OVN_PIECE_MLA TF_GLM_OVN_SOLO_TO_START TF_GLM_OVN_RESTORE_HELD)
OFF="-e TF_GLM_OVN_MM_WIDE=0 -e TF_GLM_OVN_SIDE_PRIO=0 -e TF_GLM_OVN_LATENT_ROWS=0 -e NCCL_NCHANNELS_PER_NET_PEER=1 -e TF_GLM_OVERLAP_PIECES=8 -e TF_GLM_OVN_PIECE_FRONT=0 -e TF_GLM_OVN_PIECE_FFN=0 -e TF_GLM_OVN_PIECE_MLA=0 -e TF_GLM_OVN_SOLO_TO_START=0 -e TF_GLM_OVN_RESTORE_HELD=0"
T_ARM="-e TF_GLM_OVN_MM_WIDE=1 -e TF_GLM_OVN_SIDE_PRIO=1 -e TF_GLM_OVN_LATENT_ROWS=2 -e NCCL_NCHANNELS_PER_NET_PEER=4 -e TF_GLM_OVERLAP_PIECES=8 -e TF_GLM_OVN_PIECE_FRONT=0 -e TF_GLM_OVN_PIECE_FFN=0 -e TF_GLM_OVN_PIECE_MLA=0 -e TF_GLM_OVN_SOLO_TO_START=0 -e TF_GLM_OVN_RESTORE_HELD=0"
X_ARM="-e TF_GLM_OVERLAP_PIECES=4 -e TF_GLM_OVN_PIECE_FRONT=1 -e TF_GLM_OVN_PIECE_FFN=1 -e TF_GLM_OVN_PIECE_MLA=1 -e TF_GLM_OVN_SOLO_TO_START=1 -e TF_GLM_OVN_RESTORE_HELD=1 -e TF_GLM_OVN_MM_WIDE=0 -e TF_GLM_OVN_SIDE_PRIO=0 -e TF_GLM_OVN_LATENT_ROWS=0 -e NCCL_NCHANNELS_PER_NET_PEER=1"
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE114-DONE $(date -u +%T)"; }
echo "[q114] $(date -u +%T) start${WAIT_FOR:+; waiting for $WAIT_FOR}"
while [ -n "$WAIT_FOR" ] && pgrep -f "$WAIT_FOR" > /dev/null; do sleep 60; done
trap finish EXIT
DEADLINE=$(( $(date +%s) + ${HOURS:-5} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
mkdir -p "$OUT" "$R" "$OUT/f114-boots"
echo "[q114] $(date -u +%T) IMG=$IMG; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids_of() { { docker images --no-trunc --format '{{.ID}}' "$1" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $1 | head -1"; done; }; }
ids=$(ids_of "$IMG")
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then
  echo "[q114] IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS: nothing measured (ids: $(echo $ids | tr '\n' ' '))"; exit 1
fi
echo "[q114] $IMG ids: $(echo $ids | cut -c1-80); serve.sh $(sha256sum serve.sh | cut -c1-12); env $(cat env/prod.env env/dev.env | sha256sum | cut -c1-12)"
python3 check-env.py --env-dir env > "$OUT/f114-check-env.log" 2>&1; echo "[q114] check-env rc=$?: $(tail -1 "$OUT/f114-check-env.log")"
bash prod-stop.sh || { echo "[q114] PRODUCTION DID NOT STOP"; exit 1; }
stop
boot() { # boot LABEL XENV: the Zig serve up on :8300 at --parallel 4 --context 1048576
  local label=$1 xenv=$2; stop
  IMAGE=$IMG KNOBS=dev XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/f114-boots/$label.log" 2>&1 && return 0
  echo "[q114] BOOT FAILED $label: $(tail -3 "$OUT/f114-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
cenv() { if [ "$1" = "-" ]; then docker inspect "$2" --format '{{range .Config.Env}}{{println .}}{{end}}' 2> /dev/null; else ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$1" "docker inspect $2 --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null"; fi; }
cid() { if [ "$1" = "-" ]; then docker inspect "$2" --format '{{.Image}}' 2> /dev/null; else ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$1" "docker inspect $2 --format '{{.Image}}' 2>/dev/null"; fi; }
readback() { # readback LABEL XENV: all ten variables and the image id on all three ranks, refused unless exactly this arm's
  local label=$1 xenv=$2 pair envs name want seen image line rank=0 proof
  proof="$R/$label-env.txt"; : > "$proof"
  for pair in "-:glm53-zig-r0" "$W1:glm53-zig-r1" "$W2:glm53-zig-r2"; do
    envs=$(cenv "${pair%%:*}" "${pair#*:}"); image=$(cid "${pair%%:*}" "${pair#*:}")
    printf '%s\n' "$envs" | grep -a -q '^TF_GLM_RANK=' || { echo "[q114] $label: cannot read the environment of ${pair#*:} (host ${pair%%:*}): stopping the queue"; exit 1; }
    [ -n "$image" ] || { echo "[q114] $label: cannot read the image id of ${pair#*:} (host ${pair%%:*}): stopping the queue"; exit 1; }
    printf '%s\n' "$envs" | grep -a -q '^TF_GLM_ROCE_MULTI=1$' || { echo "[q114] $label: ${pair#*:} has no TF_GLM_ROCE_MULTI=1, so the recipe's own OVERLAP_PIECES would resolve to 3 and the control would not be the recipe: stopping the queue"; exit 1; }
    line="rank$rank container=${pair#*:} image=$image"
    for name in "${VARS[@]}"; do
      want=$(printf '%s\n' "$xenv" | grep -o "[-]e $name=[A-Za-z0-9_]*" | head -1 | sed 's/^-e //'); seen=$(printf '%s\n' "$envs" | grep -a "^$name=" | head -1)
      [ "$seen" = "$want" ] || { echo "[q114] $label: ${pair#*:} carries '${seen:-$name unset}' but this arm needs '${want:-$name unset}': stopping the queue"; exit 1; }
      line="$line $name=${seen#*=}"
    done
    printf '%s\n' "$line" >> "$proof"
    rank=$(( rank + 1 ))
  done
  echo "[q114] $(date -u +%T) $label environment read back on all three ranks: $proof"
}
SMOKED=0
smoke() { # the first boot only: streams_sampled once, tiny, so an instrument that cannot talk to the serve stops the queue before a unit is spent
  local d="$OUT/smoke114"; mkdir -p "$d"
  python3 streams_sampled.py 8300 8 --ids code_ids.json --max-tokens 32 --rounds 1 --tag smoke-SC8 --out "$d/SC8.jsonl" > "$d/SC8.out" 2>&1; local rc=$?
  echo "[q114] $(date -u +%T) smoke: streams_sampled rc=$rc"
  if [ "$rc" != 0 ]; then echo "[q114] smoke SC8.out: $(tail -4 "$d/SC8.out" | tr '\n' ' ' | cut -c1-400)"; echo "[q114] THE QUEUE'S INSTRUMENT DOES NOT RUN AGAINST THIS SERVE: nothing is measured"; exit 1; fi
}
unit() { # unit LABEL XENV: one fresh boot, its readback, and the one cell
  local label=$1 xenv=$2 dir="$R/dec-$1"
  room || return
  boot "$label" "$xenv" || return
  readback "$label" "$xenv"
  echo "[q114] $(date -u +%T) $label up (KNOBS=dev); $(grep -a -m1 -E 'CUDA sm_|streams at once|drafter from' "$OUT/f114-boots/$label.log" 2>/dev/null | cut -c1-120)"
  if [ "$SMOKED" = 0 ]; then SMOKED=1; smoke; fi
  mkdir -p "$dir"
  python3 streams_sampled.py 8300 8 --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$label-SC8" --out "$dir/SC8.jsonl" > "$dir/SC8.out" 2>&1; local rc=$?
  echo "[q114] $(date -u +%T) $label sampled code 8 clients rc=$rc $(agg "$dir/SC8.out")"
  docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 400 > "$R/r0-$label.log"
}
# the eighteen boots, mirrored: each arm's six straddle the run, each control pair brackets an arm pair in both orientations
unit c1 "$OFF";   unit t1 "$T_ARM"; unit x1 "$X_ARM"; unit x2 "$X_ARM"; unit t2 "$T_ARM"; unit c2 "$OFF"
unit c3 "$OFF";   unit t3 "$T_ARM"; unit x3 "$X_ARM"; unit x4 "$X_ARM"; unit t4 "$T_ARM"; unit c4 "$OFF"
unit c5 "$OFF";   unit t5 "$T_ARM"; unit x5 "$X_ARM"; unit x6 "$X_ARM"; unit t6 "$T_ARM"; unit c6 "$OFF"
echo "[q114] $(date -u +%T) done; score with: python scripts/queue-scores/score114.py --q114 ~/bench/f114-c"
exit 0
