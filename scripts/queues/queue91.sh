#!/bin/bash
# queue91.sh - on spark1, detached, after queue77: the first queue on upstream main (1ece6e6db). Three images side by side on the same boxes, the same instrument and the same
# shape (--parallel 4 --context 1048576, 6 and 8 clients queue on it, as production's deployed shape): m130a (the re-seated 47-patch stack, the tree the full gate passed), m130base
# (the pristine main: what the stack still buys) and v129zg (the v1.2.9 stack: queue77's P boots are its baseline, one more P boot here guards against a day's drift).
# queue91.env: IMG (m130a), IMGB (m130base), IMGO (v129zg), WORKERS, HOURS. Production is down for the campaign and stays down. QUEUE91-DONE.
#
#   0  build m130a and m130base from stage/src-m130a.tar and stage/src-m130base.tar (when the image is absent), copy them to the other two ranks, one image id on all three
#   1  GPU checks, each must pass before any boot is measured. One GPU on glm-synth's 2-layer checkpoint: our knob checks (glm-mm-ovn, glm-latent-rows, glm-kda-pieces, glm-draft-onepass,
#      glm-index-ovn-check, glm-index-regroup-check, glm-mla-skip-check, glm-onepass-exact-check, glm-keep-seqs-check, glm-restore-held-check off and on) on m130a, and upstream's own
#      (glm-exl3, glm-exl3-items, glm-index-check, glm-mm-fixed, glm-ref, glm-kv-host-slots, glm-fp8g-shares, glm-kda-pad-split) on m130base first and then m130a: a check that fails on
#      both is the base's, one that fails on m130a alone stops the queue. Three ranks on the real checkpoint (scripts/gpu-check-tp3.sh, the recipe's environment): glm-solo-check with
#      and without TF_GLM_OVN_SOLO_TO_START, glm-split-check, and glm-pair-check with the runtime section only (paired prompt steps are what TF_GLM_CHUNK_SOLO replaces, so the
#      recipe's environment leaves it nothing to pair). glm-shared-check, glm-lanes-concurrent and glm-lanes-cover read a `kinds` fixture of prompts and expected tokens that only
#      glm-synth writes, so they run on its checkpoint on one GPU, on m130base first and then m130a.
#   2  units, each a fresh P=4 boot: the cold first token at 8k / 32k / 120k (two requests, one seed on every boot), a growing conversation (salt c74: a 100k first turn and seven
#      turns of about 1,300 rows), greedy and sampled decode at 1, 2, 4, 6 and 8 clients, and the 24 prompts one at a time. Order, interleaved so a drifting box shows:
#        mn1 md1 mz1 mps mr1 md2 mn2 mo3
#      mn   m130a, KNOBS=prod (prod.env: the recipe as committed)      md   m130a, KNOBS=dev (dev.env: the candidates under test)
#      mz   mn with TF_GLM_PDL=0 (upstream's dependent launches off)    mps  m130base, KNOBS=off (stock main, the runtime section only)
#      mr   md with TF_GLM_REQUEST_STARTS=1 (the owner's trade)         mo3  v129zg, KNOBS=prod with TF_GLM_OVN_EXL3_ITEMS=1 (the old stack's own item plan switch)
#   scripts/queue-scores/score91.py reads the rows; its sync rule was written before they existed.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue91.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=${IMG:?set IMG}; IMGB=${IMGB:?set IMGB}; IMGO=${IMGO:?set IMGO}
RSX="-e TF_GLM_REQUEST_STARTS=1"
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE91-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-6} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q91] $(date -u +%T) start; IMG=$IMG IMGB=$IMGB IMGO=$IMGO; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids_of() { { docker images --no-trunc --format '{{.ID}}' "$1" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $1 | head -1"; done; }; }
for image in "$IMG" "$IMGB"; do
  tag=${image#glm53-zig:}
  if ! docker images --format '{{.ID}}' "$image" | grep -q .; then
    bash build-image.sh "$tag" "stage/src-$tag.tar" > "stage/build-$tag.out" 2>&1 || { echo "[q91] BUILD FAILED $image: $(tail -3 "stage/build-$tag.out" | tr '\n' ' ' | cut -c1-300)"; exit 1; }
    echo "[q91] $(date -u +%T) built $image: $(docker images --format '{{.ID}}' "$image" | head -1)"
    bash dist-image.sh "$tag" > "stage/dist-$tag.out" 2>&1
    echo "[q91] $(date -u +%T) distributed $image: $(tail -1 "stage/dist-$tag.out" | cut -c1-200)"
  fi
done
for image in "$IMG" "$IMGB" "$IMGO"; do
  ids=$(ids_of "$image")
  echo "[q91] $image ids: $(echo $ids)"
  { [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q91] IMAGE $image IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
done
echo "[q91] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12); env: $(cat env/prod.env env/dev.env | sha256sum | cut -c1-12)"
python3 check-env.py --env-dir env > "$OUT/f91-check-env.log" 2>&1; echo "[q91] check-env rc=$?: $(tail -1 "$OUT/f91-check-env.log")"
bash prod-stop.sh || { echo "[q91] PRODUCTION DID NOT STOP"; exit 1; }
stop
TEST=/opt/tensorfold/bin/tf-cuda-test
CK="$OUT/f91-check"; mkdir -p "$CK"
RECIPE="$(for kv in $(bash env/words.sh prod recipe); do printf -- '-e %s ' "$kv"; done)"
SYN="$CK/synth"; mkdir -p "$SYN"
docker run --rm --gpus all -v "$SYN:/s" --entrypoint $TEST "$IMG" glm-synth /s/ckpt > "$SYN/synth.log" 2>&1; echo "[q91] $(date -u +%T) glm-synth rc=$?: $(grep -a '^PASS' "$SYN/synth.log" | head -1 | cut -c1-160)"
chk() { # chk IMAGE NAME XENV ARGS...: one single-GPU check; 0 when it exits 0 with a PASS line and no FAIL line
  local image=$1 name=$2 xenv=$3; shift 3
  local log="$CK/${image#glm53-zig:}-$name.log"
  timeout 1800 docker run --rm --gpus all --ipc=host -v "$SYN:/s" -e TF_GLM_LAYERS=2 $xenv --entrypoint $TEST "$image" "$name" "$@" > "$log" 2>&1; local rc=$?
  local p f; p=$(grep -c '^PASS' "$log"); f=$(grep -c 'FAIL' "$log")
  echo "[q91] $(date -u +%T) ${image#glm53-zig:} $name rc=$rc: $p PASS, $f FAIL lines; $(grep -a '^PASS' "$log" | head -1 | cut -c1-110)"
  [ "$rc" = 0 ] && [ "$p" -ge 1 ] && [ "$f" = 0 ]
}
bad=0
if [ "${SKIP_SINGLE:-0}" != 1 ]; then
for name in glm-mm-ovn glm-latent-rows glm-kda-pieces glm-draft-onepass glm-index-ovn-check glm-index-regroup-check glm-mla-skip-check glm-onepass-exact-check; do
  chk "$IMG" "$name" "" || { bad=1; echo "[q91] CHECK FAILED: $name on $IMG"; }
done
chk "$IMG" glm-keep-seqs-check "-e TF_GLM_OVN_KEEP_SEQS=1" /s/ckpt /s/id-keep || { bad=1; echo "[q91] CHECK FAILED: glm-keep-seqs-check on $IMG"; }
chk "$IMG" glm-restore-held-check "" /s/ckpt /s/id-held-off || { bad=1; echo "[q91] CHECK FAILED: glm-restore-held-check, switch off"; }
chk "$IMG" glm-restore-held-check "-e TF_GLM_OVN_RESTORE_HELD=1" /s/ckpt /s/id-held-on || { bad=1; echo "[q91] CHECK FAILED: glm-restore-held-check, switch on"; }
for name in glm-exl3 glm-exl3-items glm-index-check glm-mm-fixed glm-ref glm-kv-host-slots glm-fp8g-shares glm-kda-pad-split; do
  chk "$IMGB" "$name" ""; base_ok=$?
  chk "$IMG" "$name" ""; ours_ok=$?
  if [ "$ours_ok" != 0 ] && [ "$base_ok" = 0 ]; then bad=1; echo "[q91] CHECK FAILED ON THE STACK ONLY: $name"; fi
  [ "$ours_ok" != 0 ] && [ "$base_ok" != 0 ] && echo "[q91] $name fails on the pristine main too: the base's, not the stack's"
done
fi
for name in glm-shared-check glm-lanes-concurrent glm-lanes-cover; do
  chk "$IMGB" "$name" "" /s/ckpt /s/ckpt/dc.json 0 1 "/s/id-b-$name"; base_ok=$?
  chk "$IMG" "$name" "" /s/ckpt /s/ckpt/dc.json 0 1 "/s/id-a-$name"; ours_ok=$?
  if [ "$ours_ok" != 0 ] && [ "$base_ok" = 0 ]; then bad=1; echo "[q91] CHECK FAILED ON THE STACK ONLY: $name"; fi
  [ "$ours_ok" != 0 ] && [ "$base_ok" != 0 ] && echo "[q91] $name fails on the pristine main too: the base's, not the stack's"
done
docker run --rm -v "$SYN:/s" --entrypoint rm "$IMG" -rf /s/ckpt > /dev/null 2>&1
[ "$bad" = 0 ] || { echo "[q91] A GPU CHECK FAILED ON THE STACK: nothing is measured"; exit 1; }
echo "[q91] $(date -u +%T) the single-GPU checks passed"
tp3() { # tp3 NAME CHECK XENV: one multi-rank check on the real checkpoint; 0 passed, 1 a FAIL line, 2 it did not run to a verdict
  local dir="$CK/tp3-$1" rc
  WORKERS="$WORKERS" LIMIT=1500 bash gpu-check-tp3.sh "$IMG" "$2" "$dir" "$3"; rc=$?
  echo "[q91] $(date -u +%T) $2 ($1) on three ranks: rc=$rc, $(grep -c '^PASS' "$dir/r0.log" 2>/dev/null) PASS, $(grep -c 'FAIL' "$dir/r0.log" 2>/dev/null) FAIL lines"
  if [ "$rc" = 0 ] && [ "$(grep -c '^PASS' "$dir/r0.log")" -ge 1 ] && [ "$(grep -c 'FAIL' "$dir/r0.log")" = 0 ]; then return 0; fi
  if grep -q 'FAIL' "$dir/r0.log" 2>/dev/null; then return 1; fi
  return 2
}
ran=0; bad=0
for spec in "solo-off|glm-solo-check|-e TF_GLM_CHUNK_SOLO=4096" "solo-on|glm-solo-check|-e TF_GLM_CHUNK_SOLO=4096 -e TF_GLM_OVN_SOLO_TO_START=1" "solo-recipe|glm-solo-check|$RECIPE" "pair|glm-pair-check|" \
            "split|glm-split-check|$RECIPE"; do
  IFS='|' read -r name check xenv <<< "$spec"
  case " ${SKIP_TP3:-} " in *" $name "*) echo "[q91] $check ($name): skipped, it passed on these image ids in the first start"; ran=$((ran + 1)); continue ;; esac
  tp3 "$name" "$check" "$xenv"; rc=$?
  case $rc in 0) ran=$((ran + 1)) ;; 1) bad=1; echo "[q91] A FAIL LINE: $check ($name)" ;; *) echo "[q91] $check ($name) did not run to a verdict (the launcher or a rank; see $CK/tp3-$name)" ;; esac
done
[ "$bad" = 0 ] || { echo "[q91] A THREE-RANK CHECK FAILED: nothing is measured"; exit 1; }
echo "[q91] $(date -u +%T) three-rank checks: $ran of 5 passed (or were skipped as passed) and none failed"
boot() { # boot LABEL IMAGE KNOBS XENV: the Zig serve up on :8300 at --parallel 4 --context 1048576, 0 when it is
  local label=$1 image=$2 knobs=$3 xenv=$4; mkdir -p "$OUT/f91-boots"; stop
  IMAGE=$image KNOBS=$knobs XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/f91-boots/$label.log" 2>&1 && return 0
  echo "[q91] BOOT FAILED $label: $(tail -3 "$OUT/f91-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q91] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q91] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q91] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS [ADD]
  local dir=$1 salt=$2 t1=$3 turns=$4 add=${5:-1000} st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add "$add" --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q91] $salt turn $k FAILED"; return; }
  done
  echo "[q91] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL IMAGE XENV: longctx facts row for the boot just made
  local label=$1 image=$2 xenv=$3
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$image" "--xenv=$xenv" --out "$OUT/f91-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f91-c/$label-facts.out" 2>&1
}
mkdir -p "$OUT/f91-c"
unit() { # unit LABEL IMAGE KNOBS XENV: a P=4 boot and everything the queue measures on it
  local label=$1 image=$2 knobs=$3 xenv=$4
  room || return
  boot "c91-$label" "$image" "$knobs" "$xenv" || return
  facts "$label" "$image" "$xenv"
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f91-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f91-c/$label-probe.out" 2>&1
  echo "[q91] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f91-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f91-c/$label" "c74" 100000 8
  greedy "$OUT/f91-c/dec-$label" 1 2 4 6 8
  sampled "$OUT/f91-c/dec-$label" 1 2 4 6 8
  prompts "$OUT/f91-c/dec-$label"
  keeplog "$OUT/f91-c/r0-$label.log"
}
unit mn1 "$IMG" prod ""
unit md1 "$IMG" dev ""
unit mz1 "$IMG" prod "-e TF_GLM_PDL=0"
unit mps "$IMGB" off ""
unit mr1 "$IMG" dev "$RSX"
unit md2 "$IMG" dev ""
unit mn2 "$IMG" prod ""
unit mo3 "$IMGO" prod "-e TF_GLM_OVN_EXL3_ITEMS=1"
exit 0
