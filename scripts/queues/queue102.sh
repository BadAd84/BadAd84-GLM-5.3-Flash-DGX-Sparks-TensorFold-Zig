#!/bin/bash
# queue102.sh - on spark1, detached, after queue105: the 120k arms for the DSA indexer's prompt-scoring pair and for the vector loads, on the stack on the pin (image m130a). Three
# default-off knobs were never measured where they could matter (docs/KNOB-PROVENANCE.md classes B and C): TF_GLM_OVN_INDEX_SCHED and TF_GLM_OVN_POOLS32 (patch 0012) act on the
# indexer's prompt scoring, whose cost grows with the context, and were read only on decode cells and cold 8k / 32k prompts; TF_GLM_OVN_ABSORB_VEC (its rows in patch 0020, its code
# in 0023) gained about 1% on cold prompts and lost 1.0 to 2.5% on short TTFT and per-stream decode, and the prompt-only gate its own ledger asks for was never built. Production is down
# for the campaign and stays down. QUEUE102-DONE.
# queue102.env: IMG (glm53-zig:m130a) and WORKERS, the names queue91.sh requires from queue91.env, plus HOURS (default 4) and WAIT_FOR (default queue105.sh); those two have
# defaults, so a file that omits them still runs.
#
#   image: IMG m130a (the stack on the pin, docs/OVERNIGHT-2026-11-12.md section 72). It must be ONE id on all three ranks; absent from spark1, or a different id on a rank,
#     skips every arm with a line saying so. Nothing is built here.
#   units, mirrored so a drifting box shows in the pairs (every boot is fresh, and the two boots of one arm sit on either side of the other arm's pair):
#     lc1  IMG, KNOBS=prod, no XENV                                              the recipe as committed: the control
#     ls1  IMG, KNOBS=prod, -e TF_GLM_OVN_INDEX_SCHED=1 -e TF_GLM_OVN_POOLS32=1  S: the indexer's prompt scoring, patch 0012
#     lv1  IMG, KNOBS=prod, -e TF_GLM_OVN_ABSORB_VEC=1                           V: the vector loads, patch 0020
#     lv2  as lv1                                                                V's second boot
#     ls2  as ls1                                                                S's second boot
#     lc2  as lc1                                                                the control's second boot
#   every unit is a fresh boot at --parallel 4 --context 1048576 and runs queue91's cells exactly: the cold first token at 8k / 32k / 120k (two requests, seed pf74), the growing
#     conversation (salt c74: a 100k first turn and seven turns of about 1,300 rows), greedy and sampled decode at 1, 2, 4, 6 and 8 clients, and the 24 prompts one at a time.
#     Rows go to $HOME/bench/f102-c in queue91's f91-c layout (<label>/, dec-<label>/, rows.jsonl), so score91.py's readers apply unchanged.
#   guards: KNOBS=prod's settings name none of the three (env/prod.env's parsed lines, its comments excluded), so the controls are the unset arm and each arm's XENV is the only
#     source of its switch. After every boot each rank container's environment and image id are read back, refused when they are not exactly what the arm needs (unset where
#     XENV does not name a variable), and kept as $HOME/bench/f102-c/<label>-env.txt: score102.py's L0 reads that proof and a unit without one is VOID. The first boot's smoke
#     probe uses seed smk, which shares no prompt with the units' pf74 probes (scripts/tests/check_smoke_probe.py).
#   files: $HOME/bench/f102-c/ (the rows, the six readback proofs and the per-boot reports), $HOME/bench/f102-boots/<label>.log (the launcher logs), $HOME/bench/f102-check-env.log.
#   scripts/queue-scores/score102.py reads the rows; its rules were written before they existed.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue102.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=${IMG:?set IMG}
WAIT_FOR=${WAIT_FOR:-queue105.sh}
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE102-DONE $(date -u +%T)"; }
echo "[q102] $(date -u +%T) start; waiting for $WAIT_FOR"
while pgrep -f "$WAIT_FOR" > /dev/null; do sleep 60; done
trap finish EXIT
DEADLINE=$(( $(date +%s) + ${HOURS:-4} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
mkdir -p "$OUT"
echo "[q102] $(date -u +%T) $WAIT_FOR is done; IMG=$IMG; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids_of() { { docker images --no-trunc --format '{{.ID}}' "$1" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $1 | head -1"; done; }; }
HAVE=" "
image=$IMG
if ! docker images --format '{{.ID}}' "$image" | grep -q .; then echo "[q102] IMAGE $image IS ABSENT on spark1: its arms are skipped (nothing is built here)"; else
  ids=$(ids_of "$image")
  if [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; then
    HAVE="$HAVE$image "; echo "[q102] $image ids: $(echo $ids | cut -c1-80)"
  else
    echo "[q102] IMAGE $image IS NOT THE SAME ON ALL THREE RANKS: its arms are skipped (ids: $(echo $ids | tr '\n' ' '))"
  fi
fi
case "$HAVE" in *" $IMG "*) ;; *) echo "[q102] the stack's image $IMG is not usable on all three ranks: nothing to measure"; exit 1 ;; esac
echo "[q102] images in the window:$HAVE"
echo "[q102] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12); env: $(cat env/prod.env env/dev.env | sha256sum | cut -c1-12)"
python3 check-env.py --env-dir env > "$OUT/f102-check-env.log" 2>&1; echo "[q102] check-env rc=$?: $(tail -1 "$OUT/f102-check-env.log")"
named=$(bash env/words.sh prod all | tr ' ' '\n' | grep -E '^TF_GLM_OVN_(INDEX_SCHED|POOLS32|ABSORB_VEC)=' || true)
if [ -n "$named" ]; then
  echo "[q102] KNOBS=prod's settings name $(echo "$named" | tr '\n' ' '), so the controls would not be the unset arm: nothing is measured"
  exit 1
fi
echo "[q102] KNOBS=prod's parsed settings name none of INDEX_SCHED, POOLS32 or ABSORB_VEC, so lc1 and lc2 are the unset arm and each arm's XENV is the only source of its switch"
bash prod-stop.sh || { echo "[q102] PRODUCTION DID NOT STOP"; exit 1; }
stop
boot() { # boot LABEL IMAGE KNOBS XENV: the Zig serve up on :8300 at --parallel 4 --context 1048576, 0 when it is
  local label=$1 image=$2 knobs=$3 xenv=$4; mkdir -p "$OUT/f102-boots"; stop
  IMAGE=$image KNOBS=$knobs XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/f102-boots/$label.log" 2>&1 && return 0
  echo "[q102] BOOT FAILED $label: $(tail -3 "$OUT/f102-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
mem() { # mem FILE: what the three boxes and rank 0's container hold now
  { echo "== $(date -u +%T) spark1"; free -m | sed -n 2p; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' glm53-zig-r0 2> /dev/null
    for h in "$W1" "$W2"; do echo "== $h"; ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "free -m | sed -n 2p; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' 2>/dev/null | head -2"; done; } > "$1" 2>&1
}
cenv() { # cenv HOST CONTAINER: the container's environment, one NAME=value a line; HOST - is spark1
  if [ "$1" = "-" ]; then docker inspect "$2" --format '{{range .Config.Env}}{{println .}}{{end}}' 2> /dev/null
  else ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$1" "docker inspect $2 --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null"; fi
}
cid() { # cid HOST CONTAINER: the image id the container was created from, empty when it cannot be read
  if [ "$1" = "-" ]; then docker inspect "$2" --format '{{.Image}}' 2> /dev/null
  else ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$1" "docker inspect $2 --format '{{.Image}}' 2>/dev/null"; fi
}
readback() { # readback LABEL XENV: every rank's three variables and image id, refused unless they are exactly this arm's, and kept as the unit's proof
  local label=$1 xenv=$2 pair envs name want seen image line rank=0 proof
  proof="$OUT/f102-c/$label-env.txt"; : > "$proof"
  for pair in "-:glm53-zig-r0" "$W1:glm53-zig-r1" "$W2:glm53-zig-r2"; do
    envs=$(cenv "${pair%%:*}" "${pair#*:}"); image=$(cid "${pair%%:*}" "${pair#*:}")
    printf '%s\n' "$envs" | grep -a -q '^TF_GLM_RANK=' || { echo "[q102] $label: cannot read the environment of ${pair#*:} (host ${pair%%:*}): stopping the queue"; exit 1; }
    [ -n "$image" ] || { echo "[q102] $label: cannot read the image id of ${pair#*:} (host ${pair%%:*}): stopping the queue"; exit 1; }
    line="rank$rank container=${pair#*:} image=$image"
    for name in TF_GLM_OVN_INDEX_SCHED TF_GLM_OVN_POOLS32 TF_GLM_OVN_ABSORB_VEC; do
      want=$(printf '%s\n' "$xenv" | grep -o "$name=[A-Za-z0-9_]*" | head -1); seen=$(printf '%s\n' "$envs" | grep -a "^$name=" | head -1)
      [ "$seen" = "$want" ] || { echo "[q102] $label: ${pair#*:} carries '${seen:-$name unset}' but this arm needs '${want:-$name unset}', so the arms would not differ as designed: stopping the queue"; exit 1; }
      seen=${seen#*=}; [ -n "$seen" ] || seen=unset
      line="$line $name=$seen"
    done
    printf '%s\n' "$line" >> "$proof"
    rank=$(( rank + 1 ))
  done
  echo "[q102] $(date -u +%T) $label environment read back on all three ranks and kept in $proof: ${xenv:-no extra environment}"
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q102] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q102] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q102] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS [ADD]
  local dir=$1 salt=$2 t1=$3 turns=$4 add=${5:-1000} st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add "$add" --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q102] $salt turn $k FAILED"; return; }
  done
  echo "[q102] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL IMAGE XENV: longctx facts row for the boot just made
  local label=$1 image=$2 xenv=$3
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$image" "--xenv=$xenv" --out "$OUT/f102-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f102-c/$label-facts.out" 2>&1
}
SMOKED=0
smoke() { # the first boot only: each of THIS queue's instruments once, tiny, so one that cannot talk to the serve stops the queue before a unit is spent on it
  local d="$OUT/smoke102" a b c e f; mkdir -p "$d"
  python3 -c "import json; d=json.load(open('prompts24.json')); json.dump(d[:2], open('$d/ids-smoke.json', 'w'))"
  python3 longctx.py probe 8300 --tag smoke --n 4 --out "$d/rows.jsonl" --log-cmd "$ZLOG" --seed smk --cold-sizes 8000 --warm-base 0 --reps 1 --load 0 > "$d/probe.out" 2>&1; a=$?
  python3 longctx.py chain 8300 "$d/chain.json" --t1 8000 --add 500 --salt smk --tag smk --n 4 --out "$d/chain.jsonl" --log-cmd "$ZLOG" > "$d/chain.out" 2>&1; b=$?
  python3 streams_ids.py 8300 1 --ids prose33.json --max-tokens 32 --rounds 1 --tag smoke-P1 --out "$d/P1.jsonl" > "$d/P1.out" 2>&1; c=$?
  python3 streams_sampled.py 8300 1 --ids prose33.json --max-tokens 32 --rounds 1 --tag smoke-SP1 --out "$d/SP1.jsonl" > "$d/SP1.out" 2>&1; e=$?
  python3 per_prompt.py 8300 --ids "$d/ids-smoke.json" --max-tokens 32 --reps 1 --out "$d/pp.jsonl" > "$d/pp.out" 2>&1; f=$?
  echo "[q102] $(date -u +%T) smoke: longctx probe rc=$a chain rc=$b, streams_ids rc=$c, streams_sampled rc=$e, per_prompt rc=$f"
  if [ "$a" != 0 ] || [ "$b" != 0 ] || [ "$c" != 0 ] || [ "$e" != 0 ] || [ "$f" != 0 ]; then
    for n in probe chain P1 SP1 pp; do echo "[q102] smoke $n.out: $(tail -4 "$d/$n.out" | tr '\n' ' ' | cut -c1-400)"; done
    echo "[q102] THE QUEUE'S INSTRUMENTS DO NOT RUN AGAINST THIS SERVE: nothing is measured"; exit 1
  fi
}
mkdir -p "$OUT/f102-c"
unit() { # unit LABEL IMAGE KNOBS XENV: a P=4 boot, its environment read back on every rank, and everything the queue measures on it
  local label=$1 image=$2 knobs=$3 xenv=$4
  room || return
  case "$HAVE" in *" $image "*) ;; *) echo "[q102] $label: image $image is not the same on all three ranks (absent, or a different id on a rank): skipped"; return ;; esac
  boot "c102-$label" "$image" "$knobs" "$xenv" || return
  readback "$label" "$xenv"
  facts "$label" "$image" "$xenv"
  mem "$OUT/f102-c/$label-mem-idle.txt"
  echo "[q102] $(date -u +%T) $label up (image $image, KNOBS=$knobs, XENV='$xenv'); $(grep -a -m1 -E 'CUDA sm_|streams at once' "$OUT/f102-c/$label-facts.out" 2>/dev/null | cut -c1-120)"
  if [ "$SMOKED" = 0 ]; then SMOKED=1; smoke; fi
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f102-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f102-c/$label-probe.out" 2>&1
  echo "[q102] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f102-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f102-c/$label" "c74" 100000 8
  greedy "$OUT/f102-c/dec-$label" 1 2 4 6 8
  sampled "$OUT/f102-c/dec-$label" 1 2 4 6 8
  prompts "$OUT/f102-c/dec-$label"
  keeplog "$OUT/f102-c/r0-$label.log"
  mem "$OUT/f102-c/$label-mem-after.txt"
}
unit lc1 "$IMG" prod ""
unit ls1 "$IMG" prod "-e TF_GLM_OVN_INDEX_SCHED=1 -e TF_GLM_OVN_POOLS32=1"
unit lv1 "$IMG" prod "-e TF_GLM_OVN_ABSORB_VEC=1"
unit lv2 "$IMG" prod "-e TF_GLM_OVN_ABSORB_VEC=1"
unit ls2 "$IMG" prod "-e TF_GLM_OVN_INDEX_SCHED=1 -e TF_GLM_OVN_POOLS32=1"
unit lc2 "$IMG" prod ""
exit 0
