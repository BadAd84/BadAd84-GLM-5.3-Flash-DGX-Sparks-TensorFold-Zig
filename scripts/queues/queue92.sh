#!/bin/bash
# queue92.sh - on spark1, detached, after queue91: did anyone else's work speed the serve up. The same boxes, instrument and shape as queue91 (--parallel 4 --context 1048576, 6 and 8
# clients queue on it), every arm KNOBS=off (the runtime section of env/prod.env, no knob of ours), so a rung is what a user of upstream gets.
# queue92.env: WORKERS, HOURS, IMGB (the pristine main of queue91, glm53-zig:m130base). Production is down for the campaign and stays down. QUEUE92-DONE.
#
#   0  wait for QUEUE91-DONE in ~/bench/queue91.log, then build from stage/src-TAG.tar when the image is absent and copy it to the other two ranks, one image id on all three:
#        u129 u1210 u130   pristine upstream v1.2.9, v1.2.10 and v1.3.0 (git archive of the tag)
#        ud ui             main 3661a4281 (the dependent launches in, our 16-pair item plan out) and main 32c361db9 (the item plan in, the lanes' draft-depth hold out)
#        p3616 p3659 p2279 the pin 1ece6e6db plus one open pull request's own change (work/pr-trees/RECORD.md); an arm whose tar is not staged is skipped and logged
#   1  units, each a fresh P=4 boot: the cold first token at 8k / 32k / 120k (two requests, one seed on every boot), a growing conversation (salt c74: a 100k first turn and seven
#      turns of about 1,300 rows), greedy and sampled decode at 1, 2, 4, 6 and 8 clients, and the 24 prompts one at a time. Order, interleaved so a drifting box shows:
#        s9a sm2 smz s13a ud1 ui1 smr pd pm pg s10a s9b s13b sm3
#      s9 s10 s13  the stock tags v1.2.9 v1.2.10 v1.3.0                     sm  the pristine main (m130base), beside queue91's mps
#      ud1 ui1     the two main commits between v1.3.0 and the pin            smz sm with TF_GLM_PDL=0 (the dependent launches off)
#      smr         sm with TF_GLM_REQUEST_STARTS=1 (upstream's own warm-turn setting)
#      pd pm pg    the pin plus #3616 (TF_GLM_DRAFT_SPLIT=1), #3659 (TF_GLM_MOE_DIRECT=1) and #2279 (TF_GLM_GRAPHS=1), each with its switch on
#   scripts/queue-scores/score92.py reads the rows; its rules were written before they existed.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue92.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMGB=${IMGB:?set IMGB}
RSX="-e TF_GLM_REQUEST_STARTS=1"
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE92-DONE $(date -u +%T)"; }
echo "[q92] $(date -u +%T) start; waiting for queue91"
while pgrep -f 'queue91.sh' > /dev/null; do sleep 60; done
trap finish EXIT
echo "[q92] queue91 log's last line: $(tail -1 "$OUT/queue91.log" | cut -c1-120)"
DEADLINE=$(( $(date +%s) + ${HOURS:-8} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
echo "[q92] $(date -u +%T) queue91 is done; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids_of() { { docker images --no-trunc --format '{{.ID}}' "$1" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $1 | head -1"; done; }; }
HAVE=" "; DPIDS=""
for tag in u129 u1210 u130 ud ui p3616 p3659 p2279; do
  image="glm53-zig:$tag"
  if ! docker images --format '{{.ID}}' "$image" | grep -q .; then
    if [ ! -f "stage/src-$tag.tar" ]; then echo "[q92] no stage/src-$tag.tar: arm $tag is skipped"; continue; fi
    bash build-image.sh "$tag" "stage/src-$tag.tar" > "stage/build-$tag.out" 2>&1 || { echo "[q92] BUILD FAILED $image: $(tail -3 "stage/build-$tag.out" | tr '\n' ' ' | cut -c1-300)"; continue; }
    echo "[q92] $(date -u +%T) built $image: $(docker images --format '{{.ID}}' "$image" | head -1)"
    # the copy to the other two ranks runs beside the next build: no bench is running in this phase
    bash dist-image.sh "$tag" > "stage/dist-$tag.out" 2>&1 &
    DPIDS="$DPIDS $!"
  fi
done
wait $DPIDS
for tag in u129 u1210 u130 ud ui p3616 p3659 p2279; do
  image="glm53-zig:$tag"
  docker images --format '{{.ID}}' "$image" | grep -q . || continue
  [ -f "stage/dist-$tag.out" ] && echo "[q92] distributed $image: $(tail -1 "stage/dist-$tag.out" | cut -c1-200)"
  ids=$(ids_of "$image")
  if [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; then HAVE="$HAVE$tag "; echo "[q92] $image ids: $(echo $ids)"
  else echo "[q92] IMAGE $image IS NOT THE SAME ON ALL THREE RANKS: arm $tag is skipped"; fi
done
ids=$(ids_of "$IMGB"); { [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q92] IMAGE $IMGB IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
echo "[q92] images ready:$HAVE m130base; serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12); env: $(cat env/prod.env env/dev.env | sha256sum | cut -c1-12)"
bash prod-stop.sh || { echo "[q92] PRODUCTION DID NOT STOP"; exit 1; }
stop
boot() { # boot LABEL IMAGE KNOBS XENV: the Zig serve up on :8300 at --parallel 4 --context 1048576, 0 when it is
  local label=$1 image=$2 knobs=$3 xenv=$4; mkdir -p "$OUT/f92-boots"; stop
  IMAGE=$image KNOBS=$knobs XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/f92-boots/$label.log" 2>&1 && return 0
  echo "[q92] BOOT FAILED $label: $(tail -3 "$OUT/f92-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q92] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q92] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q92] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS [ADD]
  local dir=$1 salt=$2 t1=$3 turns=$4 add=${5:-1000} st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add "$add" --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q92] $salt turn $k FAILED"; return; }
  done
  echo "[q92] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL IMAGE XENV: longctx facts row for the boot just made
  local label=$1 image=$2 xenv=$3
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$image" "--xenv=$xenv" --out "$OUT/f92-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f92-c/$label-facts.out" 2>&1
}
mkdir -p "$OUT/f92-c"
unit() { # unit LABEL IMAGE KNOBS XENV [EXPECT]: a P=4 boot and everything the queue measures on it; EXPECT is a regex that rank 0's log must hold when the arm's switch took effect
  local label=$1 image=$2 knobs=$3 xenv=$4 expect=${5:-}
  room || return
  case "$image" in glm53-zig:u*|glm53-zig:p*) case "$HAVE" in *" ${image#glm53-zig:} "*) ;; *) echo "[q92] $label: image $image not ready: skipped"; return ;; esac ;; esac
  boot "c92-$label" "$image" "$knobs" "$xenv" || return
  facts "$label" "$image" "$xenv"
  if [ -n "$expect" ]; then echo "[q92] $label switch line /$expect/ in rank 0's log: $(docker logs glm53-zig-r0 2>&1 | grep -a -c -E "$expect") line(s)"; fi
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f92-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f92-c/$label-probe.out" 2>&1
  echo "[q92] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f92-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f92-c/$label" "c74" 100000 8
  greedy "$OUT/f92-c/dec-$label" 1 2 4 6 8
  sampled "$OUT/f92-c/dec-$label" 1 2 4 6 8
  prompts "$OUT/f92-c/dec-$label"
  keeplog "$OUT/f92-c/r0-$label.log"
}
unit s9a glm53-zig:u129 off ""
unit sm2 "$IMGB" off ""
unit smz "$IMGB" off "-e TF_GLM_PDL=0"
unit s13a glm53-zig:u130 off ""
unit ud1 glm53-zig:ud off ""
unit ui1 glm53-zig:ui off ""
unit smr "$IMGB" off "$RSX"
unit pd glm53-zig:p3616 off "-e TF_GLM_DRAFT_SPLIT=1" "${EXPECT_PD:-DRAFT_SPLIT}"
unit pm glm53-zig:p3659 off "-e TF_GLM_MOE_DIRECT=1" "${EXPECT_PM:-MOE_DIRECT}"
unit pg glm53-zig:p2279 off "-e TF_GLM_GRAPHS=1" "${EXPECT_PG:-GRAPHS}"
unit s10a glm53-zig:u1210 off ""
unit s9b glm53-zig:u129 off ""
unit s13b glm53-zig:u130 off ""
unit sm3 "$IMGB" off ""
exit 0
