#!/bin/bash
# queue93.sh - on spark1, detached: the receipts of the two pilot levers, KEEP_SEQS and NO_COPY, main against each branch on the same boxes with UPSTREAM's own bench tools
# (tools/bench_concurrent.py --alone --serial, tools/bench_openai.py, tools/bench_cache.py --require-cold, from upstream main 9ba855b3b, which the branches were cut from).
# queue93.env: IMGA (default glm53-zig:pm9), WORKERS, HOURS, WAIT_FOR (default queue92.sh), MODEL (the served id, default GLM-5.3-Flash-EXL3). Production is down for the campaign.
# QUEUE93-DONE. Every arm is KNOBS=off (the runtime section of env/prod.env, no knob of ours) at --parallel 4, one fresh boot a row, the same environment on all three ranks.
#
#   images (built from stage/src-TAG.tar when absent, copied to the other two ranks beside the next build):
#     pm9  upstream main 9ba855b3b          pks  the keep-seqs branch (tree 37d550a25f2a)          pnc  the no-copy branch (stage/src-pnc.tar; its arms are skipped when the tar is absent)
#   boots at --context 1048576, palindromic so a drifting box shows in the controls and cancels in the means of the arms:
#     ks1m-A1  pm9                 ks1m-B1a  pks + TF_GLM_KEEP_SEQS=1     nc-B1a  pnc + TF_GLM_NO_COPY=1     nc-B0  pnc, switch unset     ks1m-B0  pks, switch unset
#     nc-B1b   pnc + TF_GLM_NO_COPY=1     ks1m-B1b  pks + TF_GLM_KEEP_SEQS=1     ks1m-A2  pm9
#     (the order run: ks1m-A1 ks1m-B1a nc-B1a nc-B0 ks1m-B0 nc-B1b ks1m-B1b ks1m-A2; the two pm9 boots are the A group of both levers, so ks1m-A1 and ks1m-A2 are copied to nc-A1 and nc-A2)
#   boots at --context 262144 for keep-seqs: ks262-A1 ks262-B1a ks262-B1b ks262-A2
#   every boot: tools/bench_concurrent.py at 1, 2 and 4 streams (1 and 4 at 262144), both temperatures, --alone --serial; tools/bench_openai.py; tools/bench_cache.py --require-cold at
#   2,048 / 8,192 / 32,768 / 65,536 prompt ids (scripts/gen_ids.py, distinct seeds); at 1048576 the 24 prompts one at a time; the memory of the three boxes after the boot and after the cells.
#   before the boots, the device checks of the receipts plans on glm-synth's checkpoint on one GPU: glm-keep-seqs-check on pks with the switch on, glm-lanes-concurrent and glm-lanes-cover
#   on pm9, on pks with and without TF_GLM_KEEP_SEQS=1 and on pnc with and without TF_GLM_NO_COPY=1; a branch whose check fails is dropped from the window and the queue says so.
#   scripts/queue-scores/score93.py reads the reports; its rules were written before they existed.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue93.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
export KEEP=1
IMGA=${IMGA:-glm53-zig:pm9}
MODEL=${MODEL:-GLM-5.3-Flash-EXL3}
WAIT_FOR=${WAIT_FOR:-queue92.sh}
OUT=$HOME/bench/f93-c
TOOLS=$G/tools-up/tools
URL=http://127.0.0.1:8300
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE93-DONE $(date -u +%T)"; }
echo "[q93] $(date -u +%T) start; waiting for $WAIT_FOR"
while pgrep -f "$WAIT_FOR" > /dev/null; do sleep 60; done
trap finish EXIT
DEADLINE=$(( $(date +%s) + ${HOURS:-6} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
echo "[q93] $(date -u +%T) $WAIT_FOR is done; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids_of() { { docker images --no-trunc --format '{{.ID}}' "$1" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $1 | head -1"; done; }; }
HAVE=" "; DPIDS=""
for tag in pm9 pks pnc; do
  image="glm53-zig:$tag"
  if ! docker images --format '{{.ID}}' "$image" | grep -q .; then
    if [ ! -f "stage/src-$tag.tar" ]; then echo "[q93] no stage/src-$tag.tar: arms on $tag are skipped"; continue; fi
    bash build-image.sh "$tag" "stage/src-$tag.tar" > "stage/build-$tag.out" 2>&1 || { echo "[q93] BUILD FAILED $image: $(tail -3 "stage/build-$tag.out" | tr '\n' ' ' | cut -c1-300)"; continue; }
    echo "[q93] $(date -u +%T) built $image: $(docker images --format '{{.ID}}' "$image" | head -1)"
    bash dist-image.sh "$tag" > "stage/dist-$tag.out" 2>&1 &
    DPIDS="$DPIDS $!"
  fi
done
wait $DPIDS
for tag in pm9 pks pnc; do
  image="glm53-zig:$tag"
  docker images --format '{{.ID}}' "$image" | grep -q . || continue
  ids=$(ids_of "$image")
  if [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; then HAVE="$HAVE$tag "; echo "[q93] $image ids: $(echo $ids | cut -c1-80)"
  else echo "[q93] IMAGE $image IS NOT THE SAME ON ALL THREE RANKS: arms on $tag are skipped"; fi
done
case "$HAVE" in *" pm9 "*) ;; *) echo "[q93] no control image pm9: nothing to compare against"; exit 1 ;; esac
echo "[q93] images ready:$HAVE; serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12)"
rm -rf tools-up && mkdir tools-up && tar -xf stage/tools-up.tar -C tools-up && echo "[q93] upstream tools: $(ls tools-up/tools/*.py | wc -l) python files, bench_concurrent sha256 $(sha256sum "$TOOLS/bench_concurrent.py" | cut -c1-12)"
mkdir -p "$OUT" ids
for spec in "2048 11" "8192 12" "32768 13" "65536 14"; do set -- $spec; [ -s "ids/ids-$1.json" ] || python3 gen_ids.py "$1" "$2" > "ids/ids-$1.json"; done
bash prod-stop.sh || { echo "[q93] PRODUCTION DID NOT STOP"; exit 1; }
stop
IMAGE="$IMGA" WORLD=3 COMM_ID=rank0:29583 KNOBS=off DRYRUN=1 bash serve.sh 0 4 1048576 > "$OUT/serve-dryrun.txt" 2>&1 || true  # the serve line and environment of every arm, for the receipts
TEST=/opt/tensorfold/bin/tf-cuda-test
CK="$OUT/checks"; SYN="$CK/synth"; mkdir -p "$SYN"
docker run --rm --gpus all -v "$SYN:/s" --entrypoint $TEST "$IMGA" glm-synth /s/ckpt > "$SYN/synth.log" 2>&1; echo "[q93] $(date -u +%T) glm-synth rc=$?: $(grep -a '^PASS' "$SYN/synth.log" | head -1 | cut -c1-120)"
chk() { # chk IMAGE LABEL NAME XENV ARGS...: one single-GPU check on the synthetic checkpoint; 0 when it exits 0 with a PASS line and no FAIL line
  local image=$1 tag=$2 name=$3 xenv=$4; shift 4
  local log="$CK/$tag-$name.log"
  timeout 1800 docker run --rm --gpus all --ipc=host -v "$SYN:/s" -e TF_GLM_LAYERS=2 $xenv --entrypoint $TEST "$image" "$name" "$@" > "$log" 2>&1; local rc=$?
  local p f; p=$(grep -c '^PASS' "$log"); f=$(grep -c 'FAIL' "$log")
  echo "[q93] $(date -u +%T) $tag $name ${xenv:+($xenv) }rc=$rc: $p PASS, $f FAIL lines; $(grep -a '^PASS' "$log" | head -1 | cut -c1-110)"
  [ "$rc" = 0 ] && [ "$p" -ge 1 ] && [ "$f" = 0 ]
}
drop() { HAVE=${HAVE/ $1 / }; echo "[q93] A DEVICE CHECK FAILED ON $1: its arms are dropped from the window"; }
LC="/s/ckpt /s/ckpt/dc.json 0 1"
chk "$IMGA" pm9 glm-lanes-concurrent "" $LC /s/id-m1; chk "$IMGA" pm9 glm-lanes-cover "" $LC /s/id-m2
case "$HAVE" in *" pks "*)
  chk glm53-zig:pks pks glm-keep-seqs-check "-e TF_GLM_KEEP_SEQS=1" /s/ckpt /s/id-k1 || drop pks
  chk glm53-zig:pks pks glm-lanes-concurrent "-e TF_GLM_KEEP_SEQS=1" $LC /s/id-k2 || drop pks
  chk glm53-zig:pks pks glm-lanes-concurrent "" $LC /s/id-k3 || drop pks
  chk glm53-zig:pks pks glm-lanes-cover "-e TF_GLM_KEEP_SEQS=1" $LC /s/id-k4 || drop pks ;; esac
case "$HAVE" in *" pnc "*)
  chk glm53-zig:pnc pnc glm-lanes-concurrent "-e TF_GLM_NO_COPY=1" $LC /s/id-n1 || drop pnc
  chk glm53-zig:pnc pnc glm-lanes-concurrent "" $LC /s/id-n2 || drop pnc
  chk glm53-zig:pnc pnc glm-lanes-cover "-e TF_GLM_NO_COPY=1" $LC /s/id-n3 || drop pnc
  chk glm53-zig:pnc pnc glm-lanes-cover "" $LC /s/id-n4 || drop pnc ;; esac
docker run --rm -v "$SYN:/s" --entrypoint rm "$IMGA" -rf /s/ckpt > /dev/null 2>&1
echo "[q93] images in the window after the device checks:$HAVE"
boot() { # boot LABEL IMAGE XENV CTX: the Zig serve up on :8300 at --parallel 4, 0 when it is
  local label=$1 image=$2 xenv=$3 ctx=$4; mkdir -p "$OUT/boots"; stop
  IMAGE=$image KNOBS=off XENV="$xenv" bash zig-tp3.sh 4 "$ctx" > "$OUT/boots/$label.log" 2>&1 && return 0
  echo "[q93] BOOT FAILED $label: $(tail -3 "$OUT/boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
mem() { # mem FILE: what the three boxes and rank 0's container hold now
  { echo "== $(date -u +%T) spark1"; free -m | sed -n 2p; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' glm53-zig-r0 2> /dev/null
    for h in "$W1" "$W2"; do echo "== $h"; ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "free -m | sed -n 2p; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' 2>/dev/null | head -2"; done; } > "$1" 2>&1
}
cells() { # cells DIR LEVELS LABEL: upstream's tools against the serve on :8300
  local d=$1 levels=$2 label=$3; mkdir -p "$d"
  python3 "$TOOLS/bench_concurrent.py" "$URL" "$MODEL" --levels "$levels" --tokens 256 --reps 3 --temperatures 0,1.0 --alone --serial --label "$label" --output "$d/concurrent.json" > "$d/concurrent.out" 2>&1
  echo "[q93] $(date -u +%T) $label bench_concurrent rc=$? $(grep -c '^{' "$d/concurrent.out") cells"
  python3 "$TOOLS/bench_openai.py" "$URL" "$MODEL" --tokens 256 --reps 3 --temperatures 0 --label "$label" --output "$d/decode.json" > "$d/decode.out" 2>&1
  echo "[q93] $(date -u +%T) $label bench_openai rc=$?"
  for n in 2048 8192 32768 65536; do
    python3 "$TOOLS/bench_cache.py" "$URL" "$MODEL" --tokens 64 --repeats 2 --streams 1 --prompt-file "ids/ids-$n.json" --expected-prompt-tokens "$n" --require-cold --output "$d/cache-$n.json" > "$d/cache-$n.out" 2>&1
    echo "[q93] $(date -u +%T) $label bench_cache $n rc=$? $(python3 -c "
import json
r = json.load(open('$d/cache-$n.json'))
print('qualified', r['qualified'], 'first ttft_s', r['rows'][0].get('ttft_s'), 'cache_state', r['rows'][0].get('cache_state'), 'prompt_tokens', r['rows'][0].get('prompt_tokens'))" 2>&1 | tail -1)"
  done
}
SMOKED=0
smoke() { # the first boot only: each of upstream's tools once, minimal, on ids of their own, so a tool that cannot talk to this server stops the queue before a unit is spent on it
  local d="$OUT/smoke"; mkdir -p "$d"
  python3 gen_ids.py 2048 99 > "$d/ids-smoke.json"
  python3 "$TOOLS/bench_concurrent.py" "$URL" "$MODEL" --levels 1 --tokens 8 --reps 1 --temperatures 0 --alone --serial --label smoke --output "$d/concurrent.json" > "$d/concurrent.out" 2>&1; local a=$?
  python3 "$TOOLS/bench_openai.py" "$URL" "$MODEL" --tokens 8 --reps 1 --temperatures 0 --label smoke --output "$d/decode.json" > "$d/decode.out" 2>&1; local b=$?
  python3 "$TOOLS/bench_cache.py" "$URL" "$MODEL" --tokens 8 --repeats 1 --streams 1 --prompt-file "$d/ids-smoke.json" --expected-prompt-tokens 2048 --require-cold --output "$d/cache.json" > "$d/cache.out" 2>&1; local c=$?
  echo "[q93] $(date -u +%T) smoke: bench_concurrent rc=$a, bench_openai rc=$b, bench_cache rc=$c"
  if [ "$a" != 0 ] || [ "$b" != 0 ] || [ "$c" != 0 ]; then
    for f in concurrent decode cache; do echo "[q93] smoke $f.out: $(tail -4 "$d/$f.out" | tr '\n' ' ' | cut -c1-400)"; done
    echo "[q93] UPSTREAM'S TOOLS DO NOT RUN AGAINST THIS SERVE: nothing is measured"; exit 1
  fi
}
unit() { # unit LABEL IMAGE XENV CTX LEVELS [COPY...]: a fresh boot and every cell; COPY labels receive a copy of the cells (the shared control boots)
  local label=$1 image=$2 xenv=$3 ctx=$4 levels=$5; shift 5
  room || return
  case "$HAVE" in *" ${image#glm53-zig:} "*) ;; *) echo "[q93] $label: image $image not ready: skipped"; return ;; esac
  boot "$label" "$image" "$xenv" "$ctx" || return
  local d="$OUT/$label"; mkdir -p "$d"
  docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | head -n 300 > "$d/r0-boot.log"
  echo "[q93] $label up: $(grep -a -c -E 'TF_GLM_(KEEP_SEQS|NO_COPY)' "$d/r0-boot.log") switch line(s) in rank 0's boot log; $(grep -a -m1 -E 'stream|window' "$d/r0-boot.log" | cut -c1-160)"
  mem "$d/mem-idle.txt"
  if [ "$SMOKED" = 0 ]; then SMOKED=1; smoke; fi
  cells "$d" "$levels" "$label"
  if [ "$ctx" = 1048576 ]; then
    python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$d/pp.jsonl" > "$d/pp.out" 2>&1; echo "[q93] $(date -u +%T) $label 24 prompts rc=$?"
  fi
  mem "$d/mem-after.txt"
  docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 400 > "$d/r0-after.log"
  for c in "$@"; do rm -rf "$OUT/$c"; cp -r "$d" "$OUT/$c"; done
}
NC1="-e TF_GLM_NO_COPY=1"; KS1="-e TF_GLM_KEEP_SEQS=1"
unit ks1m-A1 "$IMGA" "" 1048576 1,2,4 nc-A1
unit ks1m-B1a glm53-zig:pks "$KS1" 1048576 1,2,4
unit nc-B1a glm53-zig:pnc "$NC1" 1048576 1,2,4
unit nc-B0 glm53-zig:pnc "" 1048576 1,2,4
unit ks1m-B0 glm53-zig:pks "" 1048576 1,2,4
unit nc-B1b glm53-zig:pnc "$NC1" 1048576 1,2,4
unit ks1m-B1b glm53-zig:pks "$KS1" 1048576 1,2,4
unit ks1m-A2 "$IMGA" "" 1048576 1,2,4 nc-A2
unit ks262-A1 "$IMGA" "" 262144 1,4
unit ks262-B1a glm53-zig:pks "$KS1" 262144 1,4
unit ks262-B1b glm53-zig:pks "$KS1" 262144 1,4
unit ks262-A2 "$IMGA" "" 262144 1,4
exit 0
