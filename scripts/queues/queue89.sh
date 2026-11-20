#!/bin/bash
# queue89.sh - on spark1, detached, after queue87 and before queue77: the solo-cuts package's second patch, TF_GLM_OVN_SOLO_TO_START. With request starts a chat prompt ends in a message start 3 rows before
# its last row, and a solo prompt step was refused wherever a start lay inside its second chunk, so a last stretch of more than 2,048 rows ran as two passes where the rows before it ran as one (queue85's
# capture: an 8,183-row prompt as 4,096 + 2,048 + 2,036 + 3 rows, the two short passes 1,903.5 ms where one pass of their rows takes about 1,694). With the switch the solo step ends at the start: expected
# about -210 ms, -5.5% of the 8k cold first token and -1.5% of the 32k one, level at 120k (the capture's request read 0.75% over an un-profiled boot's a row, so its pass times stand).
# A warm turn that adds 2,307 to 4,096 rows (a tool result) is cut the same way, so each boot also runs a conversation that adds about 3,000 rows a turn (salt c3k, --add 2500, 10 turns): three passes a turn
# without the switch, two with it.
# It builds glm53-zig:v129zf from stage/src-v129zf.tar (the 47-patch stack: patch 0039 and this one) and copies it to the other two ranks, then runs tf-cuda-test glm-solo-check, which runs ten prompts a chunk
# a step and solo, two of them with request starts, and compares first token, the next window's logits and tokens, the rings' bases and every state byte: first on one GPU on glm-synth's 2-layer checkpoint,
# without the switch and with it (both must pass or no boot is measured), then on the three ranks on the real checkpoint (gpu-check-tp3.sh, the launcher's first use) four times: without the switch and
# with it, each in the check's plain environment and in the recipe's (serve.sh's DEFS and queue89.env's NEWX). A FAIL line there stops the queue; a run that reaches no verdict is reported and does not. Then A B B A:
# s0a s0b are the recipe with request starts, s1a s1b the same with TF_GLM_OVN_SOLO_TO_START=1. Each boot: the cold first token at 8k / 32k / 120k (two requests), the growing conversation (salt c74), the
# c3k conversation and greedy decode at 1 client. The switch merges two cold chunks into one pass, so every reply must be one digest across the four boots. Rows go to f84-c, where decide84.py reads its solo
# block (rule 6, written before these rows): the c3k turns 2 on at least 1.0% under the controls' mean, the cold mean and the c74 turns not over by more than 0.3%. queue89.env: IMG, WORKERS, HOURS, NEWX.
# Production is down for the campaign and stays down. QUEUE89-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue89.env
IMG=glm53-zig:v129zf
HOURS=3 # the image, four runs of the check and four boots of about nine minutes
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=${IMG:?set IMG}
NEWX=${NEWX:-}
RSX="-e TF_GLM_REQUEST_STARTS=1"
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE89-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-5} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q89] $(date -u +%T) start; IMG=$IMG; NEWX='$NEWX'; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
# the image: built on this box (no serve is up, nothing else uses the GPUs or the memory bandwidth), then copied to the workers
TAG=${IMG#glm53-zig:}
if ! docker images --format '{{.ID}}' "$IMG" | grep -q .; then
  bash build-image.sh "$TAG" "stage/src-$TAG.tar" > "stage/build-$TAG.out" 2>&1 || { echo "[q89] BUILD FAILED: $(tail -3 "stage/build-$TAG.out" | tr '\n' ' ' | cut -c1-300)"; exit 1; }
  echo "[q89] $(date -u +%T) built $IMG: $(docker images --format '{{.ID}}' "$IMG" | head -1)"
  bash dist-image.sh "$TAG" > "stage/dist-$TAG.out" 2>&1
  echo "[q89] $(date -u +%T) distributed: $(tail -1 "stage/dist-$TAG.out" | cut -c1-200)"
fi
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
echo "[q89] $IMG ids: $(echo $ids)"
{ [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q89] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
echo "[q89] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12) $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W1" "sha256sum $G/serve.sh | cut -c1-12") $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W2" "sha256sum $G/serve.sh | cut -c1-12")"
bash prod-stop.sh || { echo "[q89] PRODUCTION DID NOT STOP"; exit 1; }
stop
DEFS=$(awk '/^DEFS="/{f=1} f{print} f&&/"$/{exit}' serve.sh | tr '\n' ' ' | sed 's/^DEFS="//; s/" *$//')
[ "$(echo $DEFS | wc -w)" -ge 20 ] || { echo "[q89] serve.sh's DEFS did not parse: '$DEFS'"; exit 1; }
RECIPE="$(for kv in $DEFS; do printf -- '-e %s ' "$kv"; done)$NEWX"
TEST=/opt/tensorfold/bin/tf-cuda-test
passed() { # passed LOG STATE: the log's one PASS line names ten prompts and the switch's STATE, and no line says FAIL
  [ "$(grep -c '^PASS' "$1")" = 1 ] && [ "$(grep -c 'FAIL' "$1")" = 0 ] && grep -q "^PASS.* 10 prompts.*a solo step to a start: $2)" "$1"
}
# one GPU, glm-synth's 2-layer checkpoint: the same check on a model that fits one rank, so a launcher fault across the ranks cannot hide a result
SYN="$OUT/f89-check/synth"; mkdir -p "$SYN"
docker run --rm --gpus all -v "$SYN:/s" --entrypoint $TEST "$IMG" glm-synth /s/ckpt > "$SYN/synth.log" 2>&1; echo "[q89] $(date -u +%T) glm-synth rc=$?: $(grep -a '^PASS' "$SYN/synth.log" | head -1 | cut -c1-160)"
synth() { # synth NAME STATE XENV: glm-solo-check at one rank on the synthetic checkpoint; 0 when it passes
  docker run --rm --gpus all --ipc=host -v "$SYN:/s" -e TF_GLM_LAYERS=2 -e TF_GLM_CHUNK_SOLO=4096 $3 --entrypoint $TEST "$IMG" glm-solo-check /s/ckpt /s/ckpt/dc.json 0 1 "/s/id-$1" > "$SYN/$1.log" 2>&1; local rc=$?
  echo "[q89] $(date -u +%T) glm-solo-check, one rank, synthetic, switch $2: rc=$rc, $(grep -c '^PASS' "$SYN/$1.log") PASS, $(grep -c 'FAIL' "$SYN/$1.log") FAIL lines"
  [ "$rc" = 0 ] && passed "$SYN/$1.log" "$2"
}
bad=0
synth off off "" || bad=1
synth on on "-e TF_GLM_OVN_SOLO_TO_START=1" || bad=1
docker run --rm -v "$SYN:/s" --entrypoint rm "$IMG" -rf /s/ckpt > /dev/null 2>&1
[ "$bad" = 0 ] || { echo "[q89] GLM-SOLO-CHECK DID NOT PASS ON THE SYNTHETIC CHECKPOINT: no boot with TF_GLM_OVN_SOLO_TO_START is measured"; exit 1; }
solocheck() { # solocheck NAME STATE XENV: glm-solo-check on the three ranks, the real checkpoint; 0 passed, 1 a FAIL line or a wrong PASS line, 2 it did not run to a verdict
  local dir="$OUT/f89-check/$1" rc
  WORKERS="$WORKERS" LIMIT=1200 bash gpu-check-tp3.sh "$IMG" glm-solo-check "$dir" "$3"; rc=$?
  if [ "$rc" = 0 ] && passed "$dir/r0.log" "$2"; then return 0; fi
  if grep -q 'FAIL' "$dir/r0.log" 2>/dev/null || [ "$(grep -c '^PASS' "$dir/r0.log" 2>/dev/null)" != 0 ]; then return 1; fi
  return 2
}
ran=0
for spec in "plain-off|off|-e TF_GLM_CHUNK_SOLO=4096" "plain-on|on|-e TF_GLM_CHUNK_SOLO=4096 -e TF_GLM_OVN_SOLO_TO_START=1" "recipe-off|off|$RECIPE" "recipe-on|on|$RECIPE -e TF_GLM_OVN_SOLO_TO_START=1"; do
  name=${spec%%|*}; rest=${spec#*|}; state=${rest%%|*}; xenv=${rest#*|}
  solocheck "$name" "$state" "$xenv"; rc=$?
  case $rc in 0) ran=$((ran + 1)) ;; 1) bad=1; echo "[q89] glm-solo-check $name: A FAIL LINE OR A WRONG PASS LINE" ;; *) echo "[q89] glm-solo-check $name did not run to a verdict (the launcher or a rank; see $OUT/f89-check/$name)" ;; esac
done
[ "$bad" = 0 ] || { echo "[q89] GLM-SOLO-CHECK FAILED ON THE THREE RANKS: no boot with TF_GLM_OVN_SOLO_TO_START is measured"; exit 1; }
echo "[q89] $(date -u +%T) glm-solo-check: passed on the synthetic checkpoint without the switch and with it; on the three ranks $ran of 4 runs passed and none failed"
boot() { # boot LABEL XENV [P [CTX]]: the Zig serve up on :8300, 0 when it is
  local label=$1 xenv=$2 p=${3:-4} ctx=${4:-1048576}; mkdir -p "$OUT/f89-boots"; stop
  if [ "$p" = 4 ]; then IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 "$ctx" > "$OUT/f89-boots/$label.log" 2>&1
  else IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh "$p" > "$OUT/f89-boots/$label.log" 2>&1; fi && return 0
  echo "[q89] BOOT FAILED $label: $(tail -3 "$OUT/f89-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q89] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q89] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q89] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS [ADD]
  local dir=$1 salt=$2 t1=$3 turns=$4 add=${5:-1000} st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add "$add" --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q89] $salt turn $k FAILED"; return; }
  done
  echo "[q89] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL XENV: longctx facts row for the boot just made
  local label=$1 xenv=$2
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$IMG" "--xenv=$xenv" --out "$OUT/f84-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f84-c/$label-facts.out" 2>&1
}
mkdir -p "$OUT/f84-c"
unit() { # unit LABEL XENV [LEVELS]: a P=4 boot, the cold probe, the growing conversation and greedy decode at LEVELS clients (default 1 and 4)
  local label=$1 xenv=$2 levels=${3:-1 4}
  room || return
  boot "c89-$label" "$xenv" || return
  facts "$label" "$xenv"
  echo "[q89] $label solo-to-start boot line: $(docker logs glm53-zig-r0 2>&1 | grep -a 'solo prompt step may end' | head -1 | cut -c1-160)"
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f84-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f84-c/$label-probe.out" 2>&1
  echo "[q89] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f84-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f84-c/$label" "c74" 100000 8
  chain "$OUT/f84-c/$label" "c3k" 100000 10 2500
  greedy "$OUT/f84-c/dec-$label" $levels
  keeplog "$OUT/f84-c/r0-$label.log"
}
B="$NEWX $RSX"
S="$B -e TF_GLM_OVN_SOLO_TO_START=1"
unit s0a "$B" "1"
unit s1a "$S" "1"
unit s1b "$S" "1"
unit s0b "$B" "1"
exit 0
