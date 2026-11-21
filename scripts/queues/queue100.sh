#!/bin/bash
# queue100.sh - on spark1, detached, after queue99.sh: the five-level reading of TF_GLM_REQUEST_STARTS=1 against the recipe as committed (KNOBS=prod, no extra XENV), on the stack on
# the pin (image m130a), AT 1, 2, 4, 6 AND 8 CLIENTS WITH COLD FIRST TOKENS, WARM TURNS AND EQUAL REPLIES. TF_GLM_REQUEST_STARTS=1 makes a chat's next turn resume where its previous
# turn's history ends instead of at the last 2,048-row point (scripts/env/dev.env line 79, the owner's trade). This window ALWAYS RUNS: there is no gate on another queue's compare
# report and nothing reads a compare.json. Production is down for the campaign and stays down. QUEUE100-DONE.
# queue100.env (on spark1, not in the repo): IMG (glm53-zig:m130a) and WORKERS, plus HOURS (default 4) and WAIT_FOR (default queue99.sh); those two have defaults, so a file that omits
# them still runs.
#
#   THE QUESTION IS APPLES TO APPLES: the recipe as committed against the same recipe plus this one variable, at every level this window measures, cold and warm, with equal replies.
#   queue91 measured the switch on the dev stack and queue92 on stock main: the growing conversation's warm turns 34 to 36% faster, and a few 6 and 8 client decode cells reading slower
#   (sampled code at 8 clients 9.33% slower on one boot, against a control spread of 1.06%), which is why the 6 and 8 client cells are what this window's two boots each must settle.
#   labels: ca1 and ca2 are the control (the change unset), ce1 and ce2 are the change under test; they are score99's own labels, so score99.py's readers and rules apply to the rows
#   unchanged. queue100 is scored by scripts/queue-scores/score100.py, which calls score99's report and adds the adoption reading (C5): the warm turns are where this switch pays, so
#   ADOPT needs them at least 5.0% faster with C1 accepted and C4 equal.
#   images: IMG m130a (the stack on the pin). The image must be ONE id on all three ranks; absent from spark1, or a different id on a rank, stops the queue, because both arms
#     must run the same stack. Nothing is built here.
#   units, in ABBA order, one FRESH boot each (the change's two boots sit between the control's two, so a box that drifts shows as a ca/ce difference that reverses between the pairs):
#     ca1  IMG, KNOBS=prod, XENV ""                              TF_GLM_REQUEST_STARTS unset: the control, the recipe as committed
#     ce1  IMG, KNOBS=prod, XENV "-e TF_GLM_REQUEST_STARTS=1"    the change
#     ce2  IMG, KNOBS=prod, XENV "-e TF_GLM_REQUEST_STARTS=1"    the change again
#     ca2  IMG, KNOBS=prod, XENV ""                              the control again
#   every unit is the deployed shape, --parallel 4 --context 1048576, and runs queue95's and queue91's cells exactly: the cold first token at 8k / 32k / 120k (two requests, seed
#     pf74), the growing conversation (salt c74: a 100k first turn and seven turns of about 1,300 rows), greedy and sampled decode at 1, 2, 4, 6 and 8 clients, and the 24 prompts
#     one at a time. Rows go to $HOME/bench/f100-c in queue91's f91-c layout (<label>/, dec-<label>/, rows.jsonl), so score91.py's readers apply unchanged.
#   guards: KNOBS=prod is checked to name no TF_GLM_REQUEST_STARTS (env/prod.env and its runtime section), so ca1 and ca2 are the unset arm and the CE boots' XENV is the only source of
#     the switch; after each boot every rank container's environment is read back and must carry exactly this arm's TF_GLM_REQUEST_STARTS (unset for the controls), else the queue stops.
#   files: $HOME/bench/f100-c/ (the rows and the per-boot reports), $HOME/bench/f100-boots/<label>.log (the launcher logs), $HOME/bench/f100-check-env.log (the env check).
#   the cells name no served model (queue95's instruments take the port and ids only, checked), so no SERVED name is needed here; serve.sh reads MODEL as the container's model
#     path and nothing here passes it.
#   scripts/queue-scores/score100.py reads the rows; its rule was fixed by the parent before they existed.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue100.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
export LEARN=0 XSERVE=""  # zig-tp3.sh forwards both to every rank, as queue98 does: no disk tier and no extra serve flags, so every boot starts with an empty cache
IMG=${IMG:?set IMG}
WAIT_FOR=${WAIT_FOR:-queue99.sh}
BENCH=$HOME/bench; OUT=$BENCH
ZLOG='docker logs --since {since} glm53-zig-r0'
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
BOOTED=0  # 1 from the first boot on: the exit handler stops and removes only a container this queue made, so an exit before any boot removes nothing
finish() { [ "$BOOTED" = 1 ] && { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; }; echo "QUEUE100-DONE $(date -u +%T)"; }
echo "[q100] $(date -u +%T) start; waiting for $WAIT_FOR"
while pgrep -f "$WAIT_FOR" > /dev/null; do sleep 60; done
trap finish EXIT
DEADLINE=$(( $(date +%s) + ${HOURS:-4} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
mkdir -p "$OUT"
echo "[q100] $(date -u +%T) $WAIT_FOR is done; IMG=$IMG; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids_of() { { docker images --no-trunc --format '{{.ID}}' "$1" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $1 | head -1"; done; }; }
docker images --format '{{.ID}}' "$IMG" | grep -q . || { echo "[q100] IMAGE $IMG IS ABSENT on spark1: nothing to measure (nothing is built here)"; exit 1; }
ids=$(ids_of "$IMG")
if [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; then
  echo "[q100] $IMG ids: $(echo $ids | cut -c1-80)"
else
  echo "[q100] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS: nothing to measure (ids: $(echo $ids | tr '\n' ' '))"; exit 1
fi
echo "[q100] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12); env/prod.env: $(sha256sum env/prod.env | cut -c1-12) (KNOBS=prod applies this file)"
python3 check-env.py --env-dir env > "$BENCH/f100-check-env.log" 2>&1; echo "[q100] check-env rc=$?: $(tail -1 "$BENCH/f100-check-env.log")"
RT=$(bash env/words.sh prod runtime 2> /dev/null)
if grep -q 'TF_GLM_REQUEST_STARTS' env/prod.env 2> /dev/null || printf '%s\n' "$RT" | grep -q 'TF_GLM_REQUEST_STARTS'; then
  echo "[q100] KNOBS=prod's recipe names TF_GLM_REQUEST_STARTS (env/prod.env or its runtime section), so ca1 would not be the unset arm: nothing is measured"; exit 1
fi
echo "[q100] KNOBS=prod names no TF_GLM_REQUEST_STARTS (env/prod.env, and $(echo "$RT" | wc -w) runtime settings), so ca1 and ca2 are the unset arm and the CE boots' XENV is the only source of the switch"
bash prod-stop.sh || { echo "[q100] PRODUCTION DID NOT STOP"; exit 1; }
stop
boot() { # boot LABEL IMAGE KNOBS XENV: the Zig serve up on :8300 at --parallel 4 --context 1048576, 0 when it is
  local label=$1 image=$2 knobs=$3 xenv=$4; mkdir -p "$BENCH/f100-boots"; stop; BOOTED=1
  IMAGE=$image KNOBS=$knobs XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$BENCH/f100-boots/$label.log" 2>&1 && return 0
  echo "[q100] BOOT FAILED $label: $(tail -3 "$BENCH/f100-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
mem() { # mem FILE: what the three boxes and rank 0's container hold now
  { echo "== $(date -u +%T) spark1"; free -m | sed -n 2p; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' glm53-zig-r0 2> /dev/null
    for h in "$W1" "$W2"; do echo "== $h"; ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "free -m | sed -n 2p; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' 2>/dev/null | head -2"; done; } > "$1" 2>&1
}
cenv() { # cenv HOST CONTAINER: the container's environment, one NAME=value a line; HOST - is spark1
  if [ "$1" = "-" ]; then docker inspect "$2" --format '{{range .Config.Env}}{{println .}}{{end}}' 2> /dev/null
  else ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$1" "docker inspect $2 --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null"; fi
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q100] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q100] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q100] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS [ADD]
  local dir=$1 salt=$2 t1=$3 turns=$4 add=${5:-1000} st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add "$add" --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q100] $salt turn $k FAILED"; return; }
  done
  echo "[q100] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL IMAGE XENV: longctx facts row for the boot just made
  local label=$1 image=$2 xenv=$3
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$image" "--xenv=$xenv" --out "$OUT/f100-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f100-c/$label-facts.out" 2>&1
}
SMOKED=0
smoke() { # the first boot only: each of THIS queue's instruments once, tiny, so one that cannot talk to the serve stops the queue before a unit is spent on it
  local d="$OUT/smoke100" a b c e f; mkdir -p "$d"
  python3 -c "import json; d=json.load(open('prompts24.json')); json.dump(d[:2], open('$d/ids-smoke.json', 'w'))"
  python3 longctx.py probe 8300 --tag smoke --n 4 --out "$d/rows.jsonl" --log-cmd "$ZLOG" --seed smk --cold-sizes 8000 --warm-base 0 --reps 1 --load 0 > "$d/probe.out" 2>&1; a=$?
  python3 longctx.py chain 8300 "$d/chain.json" --t1 8000 --add 500 --salt smk --tag smk --n 4 --out "$d/chain.jsonl" --log-cmd "$ZLOG" > "$d/chain.out" 2>&1; b=$?
  python3 streams_ids.py 8300 1 --ids prose33.json --max-tokens 32 --rounds 1 --tag smoke-P1 --out "$d/P1.jsonl" > "$d/P1.out" 2>&1; c=$?
  python3 streams_sampled.py 8300 1 --ids prose33.json --max-tokens 32 --rounds 1 --tag smoke-SP1 --out "$d/SP1.jsonl" > "$d/SP1.out" 2>&1; e=$?
  python3 per_prompt.py 8300 --ids "$d/ids-smoke.json" --max-tokens 32 --reps 1 --out "$d/pp.jsonl" > "$d/pp.out" 2>&1; f=$?
  echo "[q100] $(date -u +%T) smoke: longctx probe rc=$a chain rc=$b, streams_ids rc=$c, streams_sampled rc=$e, per_prompt rc=$f"
  if [ "$a" != 0 ] || [ "$b" != 0 ] || [ "$c" != 0 ] || [ "$e" != 0 ] || [ "$f" != 0 ]; then
    for n in probe chain P1 SP1 pp; do echo "[q100] smoke $n.out: $(tail -4 "$d/$n.out" | tr '\n' ' ' | cut -c1-400)"; done
    echo "[q100] THE QUEUE'S INSTRUMENTS DO NOT RUN AGAINST THIS SERVE: nothing is measured"; exit 1
  fi
}
mkdir -p "$OUT/f100-c"
unit() { # unit LABEL IMAGE KNOBS XENV: a P=4 boot, its environment read back on every rank, and everything the queue measures on it
  local label=$1 image=$2 knobs=$3 xenv=$4 want envs seen pair
  room || { echo "[q100] $label: the deadline $(date -u -d @$DEADLINE +%T) has passed, this arm is skipped"; return; }
  boot "c100-$label" "$image" "$knobs" "$xenv" || return
  want=$(printf '%s\n' "$xenv" | grep -o 'TF_GLM_REQUEST_STARTS=[0-9]*' | head -1)
  for pair in "-:glm53-zig-r0" "$W1:glm53-zig-r1" "$W2:glm53-zig-r2"; do
    envs=$(cenv "${pair%%:*}" "${pair#*:}"); seen=$(printf '%s\n' "$envs" | grep -a '^TF_GLM_REQUEST_STARTS=' | head -1)
    printf '%s\n' "$envs" | grep -a -q '^TF_GLM_RANK=' || { echo "[q100] $label: cannot read the environment of ${pair#*:} (host ${pair%%:*}): stopping the queue"; exit 1; }
    [ "$seen" = "$want" ] || { echo "[q100] $label: ${pair#*:} carries '${seen:-TF_GLM_REQUEST_STARTS unset}' but this arm needs '${want:-TF_GLM_REQUEST_STARTS unset}', so the arms would not differ as designed: stopping the queue"; exit 1; }
  done
  echo "[q100] $(date -u +%T) $label environment read back on all three ranks: ${want:-TF_GLM_REQUEST_STARTS unset}"
  facts "$label" "$image" "$xenv"
  mem "$OUT/f100-c/$label-mem-idle.txt"
  echo "[q100] $(date -u +%T) $label up (image $image, KNOBS=$knobs, XENV='$xenv'); $(grep -a -m1 -E 'CUDA sm_|streams at once' "$OUT/f100-c/$label-facts.out" 2>/dev/null | cut -c1-120)"
  if [ "$SMOKED" = 0 ]; then SMOKED=1; smoke; fi
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f100-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f100-c/$label-probe.out" 2>&1
  echo "[q100] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f100-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f100-c/$label" "c74" 100000 8
  greedy "$OUT/f100-c/dec-$label" 1 2 4 6 8
  sampled "$OUT/f100-c/dec-$label" 1 2 4 6 8
  prompts "$OUT/f100-c/dec-$label"
  keeplog "$OUT/f100-c/r0-$label.log"
  mem "$OUT/f100-c/$label-mem-after.txt"
}
unit ca1 "$IMG" prod ""
unit ce1 "$IMG" prod "-e TF_GLM_REQUEST_STARTS=1"
unit ce2 "$IMG" prod "-e TF_GLM_REQUEST_STARTS=1"
unit ca2 "$IMG" prod ""
echo "[q100] $(date -u +%T) done; score the run with: python scripts/queue-scores/score100.py --q100 $OUT/f100-c"
exit 0
