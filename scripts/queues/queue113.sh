#!/bin/bash
# queue113.sh - the T/X split: two arms, T alone and X alone, each against the recipe with neither, at 4 and 8 clients and on the cold prompt.
# queue105 held T and X TOGETHER (scripts/queues/queue105.sh, docs/OVERNIGHT-2026-11-12.md section 84): greedy prose 7.51% faster at 8 clients, sampled prose 2.18%
# slower, control spread 18.54% - so the bundle is unresolved and no single boot inside that spread can separate anything. This queue splits the bundle instead of
# re-confirming it. QUEUE113-DONE.
# queue113.env: IMG (glm53-zig:m130a) and WORKERS, the names queue91.sh requires from queue91.env, plus HOURS (default 6) and WAIT_FOR (none by default); those
# two have defaults, so a file that omits them still runs.
#
#   image: IMG must be ONE id on all three ranks, as in queue102: absent from spark1, or a different id on a rank, stops the queue with a line, and nothing is
#     built here.
#   arms. Every boot is KNOBS=dev and names all ten T/X variables through XENV, so no arm depends on which of dev.env's candidate lines are present:
#     control  (the recipe with neither): T and X all off
#     T alone : TF_GLM_OVN_MM_WIDE=1, TF_GLM_OVN_SIDE_PRIO=1, TF_GLM_OVN_LATENT_ROWS=2, NCCL_NCHANNELS_PER_NET_PEER=4; X off
#     X alone : TF_GLM_OVERLAP_PIECES=4, TF_GLM_OVN_PIECE_FRONT=1, TF_GLM_OVN_PIECE_FFN=1, TF_GLM_OVN_PIECE_MLA=1, TF_GLM_OVN_SOLO_TO_START=1,
#               TF_GLM_OVN_RESTORE_HELD=1; T off
#     "off" is the value the recipe resolves with neither set: 0 for the switches (cuda_ovn.on() reads exactly "1"), LATENT_ROWS=0 (absorbFn's "today's" arm),
#     OVERLAP_PIECES=8 (dev.env's CHUNK_SOLO=4096 plus the wire serve.sh adds at P<=4 resolve to 8; the readback below refuses a boot without TF_GLM_ROCE_MULTI=1,
#     because without the wire the recipe's own default would be 3 and the control would not be the recipe), NCCL_NCHANNELS_PER_NET_PEER=1 (NCCL's default).
#     dev.env's ABSORB_VEC stays set in every arm: it is a candidate of its own, and this queue is not its measurement.
#   sixteen boots, each one fresh, each measuring BOTH levels: the control eight (c1..c8), T four (t1..t4), X four (x1..x4). Mirrored so drift lands on every
#     group: c1 t1 x1 c2 c3 x2 t2 c4 t3 x3 c5 c6 x4 t4 c7 c8 - each arm's four boots straddle the middle of the run and the controls bracket them at the ends
#     and between. Per level that is eight control boots against four of each arm, which is what queue105's 18.54% control spread asks for.
#   every boot: the cold first token at 8k and 32k (two requests, seed pf74, the sizes both bundles were sold on), the four decode cells (greedy and sampled,
#     prose and code, three rounds of 400 tokens each) at 4 AND at 8 clients, and the 24 prompts one at a time for their digests. Rows go to $HOME/bench/f113-c
#     in queue91's layout (<label>/chain.jsonl unused, dec-<label>/{P,C,SP,SC}<4|8>.jsonl, rows.jsonl), so score91.py's readers and score113.py apply.
#   guards: after every boot each rank's ten variables and image id are read back and refused unless they are exactly this arm's, kept as
#     $HOME/bench/f113-c/<label>-env.txt; the first boot smoke-probes every instrument with seed smk (a prompt set the units' pf74 probes never use).
#   scripts/queue-scores/score113.py reads the rows; its rules were written before they existed (score113.py's docstring).
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue113.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=${IMG:?set IMG}
WAIT_FOR=${WAIT_FOR:-}
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench; R=$OUT/f113-c
VARS=(TF_GLM_OVN_MM_WIDE TF_GLM_OVN_SIDE_PRIO TF_GLM_OVN_LATENT_ROWS NCCL_NCHANNELS_PER_NET_PEER TF_GLM_OVERLAP_PIECES
      TF_GLM_OVN_PIECE_FRONT TF_GLM_OVN_PIECE_FFN TF_GLM_OVN_PIECE_MLA TF_GLM_OVN_SOLO_TO_START TF_GLM_OVN_RESTORE_HELD)
OFF="-e TF_GLM_OVN_MM_WIDE=0 -e TF_GLM_OVN_SIDE_PRIO=0 -e TF_GLM_OVN_LATENT_ROWS=0 -e NCCL_NCHANNELS_PER_NET_PEER=1 -e TF_GLM_OVERLAP_PIECES=8 -e TF_GLM_OVN_PIECE_FRONT=0 -e TF_GLM_OVN_PIECE_FFN=0 -e TF_GLM_OVN_PIECE_MLA=0 -e TF_GLM_OVN_SOLO_TO_START=0 -e TF_GLM_OVN_RESTORE_HELD=0"
T_ON="-e TF_GLM_OVN_MM_WIDE=1 -e TF_GLM_OVN_SIDE_PRIO=1 -e TF_GLM_OVN_LATENT_ROWS=2 -e NCCL_NCHANNELS_PER_NET_PEER=4"
X_ON="-e TF_GLM_OVERLAP_PIECES=4 -e TF_GLM_OVN_PIECE_FRONT=1 -e TF_GLM_OVN_PIECE_FFN=1 -e TF_GLM_OVN_PIECE_MLA=1 -e TF_GLM_OVN_SOLO_TO_START=1 -e TF_GLM_OVN_RESTORE_HELD=1"
T_ARM="$T_ON -e TF_GLM_OVERLAP_PIECES=8 -e TF_GLM_OVN_PIECE_FRONT=0 -e TF_GLM_OVN_PIECE_FFN=0 -e TF_GLM_OVN_PIECE_MLA=0 -e TF_GLM_OVN_SOLO_TO_START=0 -e TF_GLM_OVN_RESTORE_HELD=0"
X_ARM="$X_ON -e TF_GLM_OVN_MM_WIDE=0 -e TF_GLM_OVN_SIDE_PRIO=0 -e TF_GLM_OVN_LATENT_ROWS=0 -e NCCL_NCHANNELS_PER_NET_PEER=1"
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE113-DONE $(date -u +%T)"; }
echo "[q113] $(date -u +%T) start${WAIT_FOR:+; waiting for $WAIT_FOR}"
while [ -n "$WAIT_FOR" ] && pgrep -f "$WAIT_FOR" > /dev/null; do sleep 60; done
trap finish EXIT
DEADLINE=$(( $(date +%s) + ${HOURS:-6} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
mkdir -p "$OUT" "$R" "$OUT/f113-boots"
echo "[q113] $(date -u +%T) IMG=$IMG; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids_of() { { docker images --no-trunc --format '{{.ID}}' "$1" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $1 | head -1"; done; }; }
ids=$(ids_of "$IMG")
if [ "$(echo "$ids" | grep -c .)" != 3 ] || [ "$(echo "$ids" | sort -u | wc -l)" != 1 ]; then
  echo "[q113] IMAGE $IMG IS NOT ONE ID ON ALL THREE RANKS: nothing measured (ids: $(echo $ids | tr '\n' ' '))"; exit 1
fi
echo "[q113] $IMG ids: $(echo $ids | cut -c1-80); serve.sh $(sha256sum serve.sh | cut -c1-12); env $(cat env/prod.env env/dev.env | sha256sum | cut -c1-12)"
python3 check-env.py --env-dir env > "$OUT/f113-check-env.log" 2>&1; echo "[q113] check-env rc=$?: $(tail -1 "$OUT/f113-check-env.log")"
bash prod-stop.sh || { echo "[q113] PRODUCTION DID NOT STOP"; exit 1; }
stop
boot() { # boot LABEL XENV: the Zig serve up on :8300 at --parallel 4 --context 1048576
  local label=$1 xenv=$2; stop
  IMAGE=$IMG KNOBS=dev XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/f113-boots/$label.log" 2>&1 && return 0
  echo "[q113] BOOT FAILED $label: $(tail -3 "$OUT/f113-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
cenv() { # cenv HOST CONTAINER: the container's environment, one NAME=value a line
  if [ "$1" = "-" ]; then docker inspect "$2" --format '{{range .Config.Env}}{{println .}}{{end}}' 2> /dev/null
  else ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$1" "docker inspect $2 --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null"; fi
}
cid() { if [ "$1" = "-" ]; then docker inspect "$2" --format '{{.Image}}' 2> /dev/null; else ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$1" "docker inspect $2 --format '{{.Image}}' 2>/dev/null"; fi; }
readback() { # readback LABEL XENV: all ten variables and the image id on all three ranks, refused unless exactly this arm's
  local label=$1 xenv=$2 pair envs name want seen image line rank=0 proof
  proof="$R/$label-env.txt"; : > "$proof"
  for pair in "-:glm53-zig-r0" "$W1:glm53-zig-r1" "$W2:glm53-zig-r2"; do
    envs=$(cenv "${pair%%:*}" "${pair#*:}"); image=$(cid "${pair%%:*}" "${pair#*:}")
    printf '%s\n' "$envs" | grep -a -q '^TF_GLM_RANK=' || { echo "[q113] $label: cannot read the environment of ${pair#*:} (host ${pair%%:*}): stopping the queue"; exit 1; }
    [ -n "$image" ] || { echo "[q113] $label: cannot read the image id of ${pair#*:} (host ${pair%%:*}): stopping the queue"; exit 1; }
    printf '%s\n' "$envs" | grep -a -q '^TF_GLM_ROCE_MULTI=1$' || { echo "[q113] $label: ${pair#*:} has no TF_GLM_ROCE_MULTI=1, so the recipe's own OVERLAP_PIECES would resolve to 3 and the control would not be the recipe: stopping the queue"; exit 1; }
    line="rank$rank container=${pair#*:} image=$image"
    for name in "${VARS[@]}"; do
      want=$(printf '%s\n' "$xenv" | grep -o "[-]e $name=[A-Za-z0-9_]*" | head -1 | sed 's/^-e //'); seen=$(printf '%s\n' "$envs" | grep -a "^$name=" | head -1)
      [ "$seen" = "$want" ] || { echo "[q113] $label: ${pair#*:} carries '${seen:-$name unset}' but this arm needs '${want:-$name unset}': stopping the queue"; exit 1; }
      line="$line $name=${seen#*=}"
    done
    printf '%s\n' "$line" >> "$proof"
    rank=$(( rank + 1 ))
  done
  echo "[q113] $(date -u +%T) $label environment read back on all three ranks: $proof"
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
SMOKED=0
smoke() { # the first boot only: each instrument once, tiny, so one that cannot talk to the serve stops the queue before a unit is spent
  local d="$OUT/smoke113" a c e f; mkdir -p "$d"
  python3 -c "import json; d=json.load(open('prompts24.json')); json.dump(d[:2], open('$d/ids-smoke.json', 'w'))"
  python3 longctx.py probe 8300 --tag smoke --n 4 --out "$d/rows.jsonl" --log-cmd "$ZLOG" --seed smk --cold-sizes 8000 --warm-base 0 --reps 1 --load 0 > "$d/probe.out" 2>&1; a=$?
  python3 streams_ids.py 8300 4 --ids prose33.json --max-tokens 32 --rounds 1 --tag smoke-P4 --out "$d/P4.jsonl" > "$d/P4.out" 2>&1; c=$?
  python3 streams_sampled.py 8300 8 --ids prose33.json --max-tokens 32 --rounds 1 --tag smoke-SP8 --out "$d/SP8.jsonl" > "$d/SP8.out" 2>&1; e=$?
  python3 per_prompt.py 8300 --ids "$d/ids-smoke.json" --max-tokens 32 --reps 1 --out "$d/pp.jsonl" > "$d/pp.out" 2>&1; f=$?
  echo "[q113] $(date -u +%T) smoke: longctx probe rc=$a, streams_ids rc=$c, streams_sampled rc=$e, per_prompt rc=$f"
  if [ "$a" != 0 ] || [ "$c" != 0 ] || [ "$e" != 0 ] || [ "$f" != 0 ]; then
    for n in probe P4 SP8 pp; do echo "[q113] smoke $n.out: $(tail -4 "$d/$n.out" | tr '\n' ' ' | cut -c1-400)"; done
    echo "[q113] THE QUEUE'S INSTRUMENTS DO NOT RUN AGAINST THIS SERVE: nothing is measured"; exit 1
  fi
}
cells() { # cells LABEL: both levels' four decode cells, two reps of the two cold sizes, the 24 prompts' digests
  local label=$1 dir="$R/dec-$label" N
  mkdir -p "$dir"
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$R/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000 --warm-base 0 --reps 2 --load 0 > "$R/$label-probe.out" 2>&1
  echo "[q113] $(date -u +%T) $label cold rc=$? ttft 8k/32k: $(grep -o '"ttft_ms": [0-9]*' "$R/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  for N in 4 8; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$label-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$label-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$label-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r3=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$label-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r4=$?
    echo "[q113] $(date -u +%T) $label $N clients: prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out") sampled prose rc=$r3 $(agg "$dir/SP$N.out") sampled code rc=$r4 $(agg "$dir/SC$N.out")"
  done
  python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$dir/pp.jsonl" > "$dir/pp.out" 2>&1; echo "[q113] $(date -u +%T) $label 24 prompts rc=$?"
  keeplog "$R/r0-$label.log"
}
unit() { # unit LABEL XENV: one fresh boot, its readback, and the cells
  local label=$1 xenv=$2
  room || return
  boot "$label" "$xenv" || return
  readback "$label" "$xenv"
  echo "[q113] $(date -u +%T) $label up (KNOBS=dev); $(grep -a -m1 -E 'CUDA sm_|streams at once|drafter from' "$OUT/f113-boots/$label.log" 2>/dev/null | cut -c1-120)"
  if [ "$SMOKED" = 0 ]; then SMOKED=1; smoke; fi
  cells "$label"
}
# the sixteen boots, mirrored: each arm's four straddle the middle, the controls bracket them
unit c1 "$OFF";  unit t1 "$T_ARM"; unit x1 "$X_ARM"; unit c2 "$OFF"
unit c3 "$OFF";  unit x2 "$X_ARM"; unit t2 "$T_ARM"; unit c4 "$OFF"
unit t3 "$T_ARM"; unit x3 "$X_ARM"; unit c5 "$OFF"; unit c6 "$OFF"
unit x4 "$X_ARM"; unit t4 "$T_ARM"; unit c7 "$OFF"; unit c8 "$OFF"
echo "[q113] $(date -u +%T) done; score with: python scripts/queue-scores/score113.py --q113 ~/bench/f113-c"
exit 0
