#!/bin/bash
# queue94.sh - on spark1, detached: the GPU receipts of two upstream levers, TF_GLM_HEAD_SKIP (branch up/head-skip) and TF_GLM_SOLO_TO_START (branch up/solo-to-start), pristine upstream
# main 9f904af48 against each branch on the same three boxes, with upstream's own tools from ITS OWN base (stage/tools-up94.tar, tools/ at 9f904af48).
# queue107.env: WORKERS, HOURS (default 7), WAIT_FOR (default queue93.sh), MODEL (the served id, default GLM-5.3-Flash-EXL3). Production is down for the campaign.
# QUEUE107-DONE. The successor to queue94's head-skip half: the same five arms, the same cells and score94's rules unchanged, with KNOBS=prod and request starts on every arm
# so a turn keeps the prompt state H5 measures. queue94's arms ran KNOBS=off, kept none, and its H5 could not be evaluated
# (docs/audit-2026-11-12/queue94-headskip-h5-defect.md). One fresh boot a row at --parallel 4 --context 1048576, the same environment on all three ranks.
#
#   images (built from stage/src-TAG.tar when absent, copied to the other two ranks beside the next build): p9f = main 9f904af48 (the control for BOTH levers),
#     phsk = the head-skip branch (stage/src-phsk.tar), psts = the solo-to-start branch (stage/src-psts.tar). An arm whose image is missing or whose build fails is skipped with a line
#     saying so; no control means exit 1.
#   boots in the order run, palindromic so a drifting box shows in the controls and cancels in the group means (XS = -e TF_GLM_CHUNK_SOLO=4096 -e TF_GLM_REQUEST_STARTS=1):
#     head skip: hk-A1 p9f   hk-B1a phsk +TF_GLM_HEAD_SKIP=1   hk-B0 phsk, switch unset   hk-B1b phsk +TF_GLM_HEAD_SKIP=1   hk-A2 p9f
#     solo to start: st-A1 p9f XS   st-B1a psts "XS +TF_GLM_SOLO_TO_START=1"   st-B0 psts XS   st-B1x psts "TF_GLM_CHUNK_SOLO=4096 +TF_GLM_SOLO_TO_START=1", request starts OFF
#       st-B1b psts "XS +TF_GLM_SOLO_TO_START=1"   st-A2 p9f XS
#     then, only if there is room: hk-P0 phsk +TF_GLM_PROF=1 and hk-P1 phsk +TF_GLM_PROF=1 +TF_GLM_HEAD_SKIP=1, each one cold 8,192-id request and rank 0's profile lines of it.
#   every boot: tools/bench_concurrent.py at 1, 2 and 4 streams, both temperatures, --alone --serial; tools/bench_openai.py; tools/bench_cache.py --require-cold at 2,048 / 8,192 /
#   32,768 / 65,536 prompt ids (scripts/gen_ids.py, distinct seeds); the memory of the three boxes after the boot and after the cells. Head-skip boots also keep the prompt cache's gauges
#   (/metrics) in metrics-after.txt and every rank 0 log line that names TF_GLM_HEAD_SKIP in head-skip-line.txt; solo-to-start boots also run OUR cells, the ones upstream has no driver for
#   because it sends completion ids: queue89's cold chat first token at 8k / 32k / 120k (longctx.py probe, salt pf74, two requests a size) and its two conversations, c74 (8 turns, about
#   1,290 rows a turn) and c3k (10 turns, --add 2500, about 3,000), rows in <boot>/ours-rows.jsonl as longctx.py writes them (and <boot>/chain.jsonl for decide84.py and score91.py).
#   solo-to-start boots also run UPSTREAM'S chat-turn tool, tools/bench_warm_turns.py --phase cold, at about 8,192 / 32,768 / 122,880 prompt tokens (warm-8k.json, warm-32k.json,
#   warm-120k.json): one chat turn plus a short continuation, the shape whose message structure carries request starts, so the report's first_turn.prefill_widths are this lever's chunk
#   widths straight from the server. Its line counts come from two calibration runs on the first st boot (400 and 800 lines, tokens = a + b*lines), kept in $OUT/warm-lines.json and reused
#   on every later boot; each size's first turn must be cold (cached_tokens 0, printed) and a tool failure prints its rc and never stops the queue. Our cells stay: they cover the cold
#   sizes and conversations upstream's tool does not send. score94.py prints the warm reports as a report only.
#   Before the boots, the device checks: glm-synth's 2-layer checkpoint once, then queue93-style glm-lanes-concurrent and glm-lanes-cover on phsk with and without the switch (no drafter on
#   those checks, so the head runs either way: they show the switch leaves the default path's bytes alone, which is all a synthetic checkpoint can show), then queue89's glm-solo-check on
#   psts, one GPU with the switch off and on and the three ranks on the real checkpoint with it off and on. A check that fails drops that image's arms and the queue says so.
#   scripts/queue-scores/score94.py reads the reports; its rules were written before the rows existed.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue107.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMGA=glm53-zig:p9f
MODEL=${MODEL:-GLM-5.3-Flash-EXL3}
WAIT_FOR=${WAIT_FOR:-queue106.sh}
OUT=$HOME/bench/f107-c
TOOLS=$G/tools-up/tools
URL=http://127.0.0.1:8300
ZLOG='docker logs --since {since} glm53-zig-r0'
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE107-DONE $(date -u +%T)"; }
echo "[q107] $(date -u +%T) start; waiting for $WAIT_FOR"
while pgrep -f "$WAIT_FOR" > /dev/null; do sleep 60; done
trap finish EXIT
DEADLINE=$(( $(date +%s) + ${HOURS:-7} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
echo "[q107] $(date -u +%T) $WAIT_FOR is done; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids_of() { { docker images --no-trunc --format '{{.ID}}' "$1" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $1 | head -1"; done; }; }
HAVE=" "; DPIDS=""
for tag in p9f phsk psts; do
  image="glm53-zig:$tag"
  if ! docker images --format '{{.ID}}' "$image" | grep -q .; then
    if [ ! -f "stage/src-$tag.tar" ]; then echo "[q107] no stage/src-$tag.tar: arms on $tag are skipped"; continue; fi
    bash build-image.sh "$tag" "stage/src-$tag.tar" > "stage/build-$tag.out" 2>&1 || { echo "[q107] BUILD FAILED $image: $(tail -3 "stage/build-$tag.out" | tr '\n' ' ' | cut -c1-300)"; continue; }
    echo "[q107] $(date -u +%T) built $image: $(docker images --format '{{.ID}}' "$image" | head -1)"
    bash dist-image.sh "$tag" > "stage/dist-$tag.out" 2>&1 &
    DPIDS="$DPIDS $!"
  fi
done
wait $DPIDS
for tag in p9f phsk psts; do
  image="glm53-zig:$tag"
  docker images --format '{{.ID}}' "$image" | grep -q . || continue
  ids=$(ids_of "$image")
  if [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; then HAVE="$HAVE$tag "; echo "[q107] $image ids: $(echo $ids | cut -c1-80)"
  else echo "[q107] IMAGE $image IS NOT THE SAME ON ALL THREE RANKS: arms on $tag are skipped"; fi
done
case "$HAVE" in *" p9f "*) ;; *) echo "[q107] no control image p9f: nothing to compare against"; exit 1 ;; esac
echo "[q107] images ready:$HAVE; serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12)"
rm -rf tools-up && mkdir tools-up
tar -xf stage/tools-up94.tar -C tools-up || { echo "[q107] stage/tools-up94.tar did not extract: upstream's tools from 9f904af48 are required"; exit 1; }
echo "[q107] upstream tools (9f904af48, stage/tools-up94.tar): $(ls tools-up/tools/*.py | wc -l) python files, bench_concurrent sha256 $(sha256sum "$TOOLS/bench_concurrent.py" | cut -c1-12)"
mkdir -p "$OUT" ids
for spec in "2048 11" "8192 12" "32768 13" "65536 14"; do set -- $spec; [ -s "ids/ids-$1.json" ] || python3 gen_ids.py "$1" "$2" > "ids/ids-$1.json"; done
bash prod-stop.sh || { echo "[q107] PRODUCTION DID NOT STOP"; exit 1; }
stop
RT=$(bash env/words.sh prod recipe)
[ -n "$RT" ] || { echo "[q107] env/words.sh printed no recipe section: the arm's own switches cannot be checked"; exit 1; }
echo "[q107] KNOBS=prod applies prod.env's recipe ($(echo $RT | wc -w) settings); it names TF_GLM_CHUNK_SOLO $(grep -o "TF_GLM_CHUNK_SOLO=" <<< " $RT " | wc -l) time(s) and TF_GLM_REQUEST_STARTS $(grep -o "TF_GLM_REQUEST_STARTS=" <<< " $RT " | wc -l), so an arm's XH is the only source of either"
XS="-e TF_GLM_CHUNK_SOLO=4096 -e TF_GLM_REQUEST_STARTS=1"
HS="-e TF_GLM_HEAD_SKIP=1"
XH="-e TF_GLM_CHUNK_SOLO=4096 -e TF_GLM_REQUEST_STARTS=1"  # a kept state a turn resumes, which H5 reads
STS="-e TF_GLM_SOLO_TO_START=1"
dry() { # dry LABEL TAG XENV: serve.sh's line and effective environment for one arm, starting nothing
  local label=$1 tag=$2 xenv=$3
  local f="$OUT/serve-dryrun-$label.txt"  # separate: the shell expands every word before `local` runs, so $label here would be read unset under set -u
  IMAGE="glm53-zig:$tag" WORLD=3 COMM_ID=rank0:29583 KNOBS=prod XENV="$xenv" DRYRUN=1 bash serve.sh 0 4 1048576 > "$f" 2>&1 || true
  echo "[q107] DRYRUN $label $tag: $(grep -o -- ' -e ' "$f" | wc -l) -e settings on the line; CHUNK_SOLO $(grep -o 'TF_GLM_CHUNK_SOLO=4096' "$f" | wc -l), REQUEST_STARTS $(grep -o 'TF_GLM_REQUEST_STARTS=1' "$f" | wc -l), HEAD_SKIP $(grep -o 'TF_GLM_HEAD_SKIP=1' "$f" | wc -l), SOLO_TO_START $(grep -o 'TF_GLM_SOLO_TO_START=1' "$f" | wc -l), PROF $(grep -o 'TF_GLM_PROF=1' "$f" | wc -l)"
}
dry hk-A1 p9f ""; dry hk-B1a phsk "$HS"; dry hk-B0 phsk ""; dry hk-B1b phsk "$HS"; dry hk-A2 p9f ""
dry st-A1 p9f "$XS"; dry st-B1a psts "$XS $STS"; dry st-B0 psts "$XS"; dry st-B1x psts "-e TF_GLM_CHUNK_SOLO=4096 $STS"; dry st-B1b psts "$XS $STS"; dry st-A2 p9f "$XS"
dry hk-P0 phsk "-e TF_GLM_PROF=1"; dry hk-P1 phsk "-e TF_GLM_PROF=1 $HS"
TEST=/opt/tensorfold/bin/tf-cuda-test
CK="$OUT/checks"; SYN="$CK/synth"; mkdir -p "$SYN"
SYNIMG=$IMGA; case "$HAVE" in *" psts "*) SYNIMG=glm53-zig:psts ;; esac
case "$HAVE" in *" phsk "*|*" psts "*)
  docker run --rm --gpus all -v "$SYN:/s" --entrypoint $TEST "$SYNIMG" glm-synth /s/ckpt > "$SYN/synth.log" 2>&1; echo "[q107] $(date -u +%T) glm-synth on $SYNIMG rc=$?: $(grep -a '^PASS' "$SYN/synth.log" | head -1 | cut -c1-120)"
  ;; *) echo "[q107] neither phsk nor psts is in the window: no device check needs the synthetic checkpoint" ;; esac
chk() { # chk IMAGE TAG NAME XENV ARGS...: one single-GPU check on the synthetic checkpoint; 0 when it exits 0 with a PASS line and no FAIL line
  local image=$1 tag=$2 name=$3 xenv=$4; shift 4
  local log="$CK/$tag-$name.log"
  timeout 1800 docker run --rm --gpus all --ipc=host -v "$SYN:/s" -e TF_GLM_LAYERS=2 $xenv --entrypoint $TEST "$image" "$name" "$@" > "$log" 2>&1; local rc=$?
  local p f; p=$(grep -c '^PASS' "$log"); f=$(grep -c 'FAIL' "$log")
  echo "[q107] $(date -u +%T) $tag $name ${xenv:+($xenv) }rc=$rc: $p PASS, $f FAIL lines; $(grep -a '^PASS' "$log" | head -1 | cut -c1-110)"
  [ "$rc" = 0 ] && [ "$p" -ge 1 ] && [ "$f" = 0 ]
}
drop() { HAVE=${HAVE/ $1 / }; echo "[q107] A DEVICE CHECK FAILED ON $1: its arms are dropped from the window"; }
has_cmd() { # has_cmd IMAGE NAME: the runner's usage names the command (tf-cuda-test with no command prints its usage)
  docker run --rm --gpus all --entrypoint $TEST "$1" 2>&1 | grep -q "  $2 "
}
LC="/s/ckpt /s/ckpt/dc.json 0 1"
case "$HAVE" in *" phsk "*)
  if has_cmd glm53-zig:phsk glm-lanes-concurrent && has_cmd glm53-zig:phsk glm-lanes-cover; then
    chk glm53-zig:phsk phsk glm-lanes-concurrent "$HS" $LC /s/id-h1 || drop phsk
    chk glm53-zig:phsk phsk glm-lanes-concurrent "" $LC /s/id-h2 || drop phsk
    chk glm53-zig:phsk phsk glm-lanes-cover "$HS" $LC /s/id-h3 || drop phsk
    chk glm53-zig:phsk phsk glm-lanes-cover "" $LC /s/id-h4 || drop phsk
  else echo "[q107] phsk's tf-cuda-test does not list both lane checks: no phsk device check (its receipts plan asks none)"; fi ;; esac
passed() { # passed LOG STATE: the log's one PASS line names ten prompts and the switch's STATE, and no line says FAIL (queue89's check)
  [ "$(grep -c '^PASS' "$1")" = 1 ] && [ "$(grep -c 'FAIL' "$1")" = 0 ] && grep -q "^PASS.* 10 prompts.*a solo step to a start: $2)" "$1"
}
synth() { # synth NAME STATE XENV: glm-solo-check at one rank on the synthetic checkpoint; 0 when it passes
  local name=$1 state=$2 xenv=$3 log="$CK/psts-solo-synth-$1.log"
  docker run --rm --gpus all --ipc=host -v "$SYN:/s" -e TF_GLM_LAYERS=2 -e TF_GLM_CHUNK_SOLO=4096 $xenv --entrypoint $TEST glm53-zig:psts glm-solo-check /s/ckpt /s/ckpt/dc.json 0 1 "/s/id-$name" > "$log" 2>&1; local rc=$?
  echo "[q107] $(date -u +%T) psts glm-solo-check, one rank, synthetic, switch $state: rc=$rc, $(grep -c '^PASS' "$log") PASS, $(grep -c 'FAIL' "$log") FAIL lines"
  [ "$rc" = 0 ] && passed "$log" "$state"
}
solocheck() { # solocheck NAME STATE XENV: glm-solo-check on the three ranks, the real checkpoint; 0 when every rank exits 0 and rank 0's PASS line names the state
  local dir="$CK/$1" rc
  WORKERS="$WORKERS" LIMIT=1200 bash gpu-check-tp3.sh glm53-zig:psts glm-solo-check "$dir" "$3"; rc=$?
  if [ "$rc" = 0 ] && passed "$dir/r0.log" "$2"; then return 0; fi
  echo "[q107] glm-solo-check $1 did not pass: $(grep -a -m1 -E 'FAIL|REFUSE' "$dir/r0.log" 2>/dev/null | cut -c1-200)"
  return 1
}
case "$HAVE" in *" psts "*)
  if synth off off "" && synth on on "$STS" && solocheck psts-solo-off off "$XS" && solocheck psts-solo-on on "$XS $STS"; then
    echo "[q107] $(date -u +%T) glm-solo-check: passed on the synthetic checkpoint without the switch and with it, and on the three ranks without and with it"
  else drop psts; fi ;; esac
docker run --rm -v "$SYN:/s" --entrypoint rm "$SYNIMG" -rf /s/ckpt > /dev/null 2>&1
echo "[q107] images in the window after the device checks:$HAVE"
boot() { # boot LABEL TAG XENV: the Zig serve up on :8300 at --parallel 4, 0 when it is
  local label=$1 tag=$2 xenv=$3; mkdir -p "$OUT/boots"; stop
  IMAGE="glm53-zig:$tag" KNOBS=prod XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/boots/$label.log" 2>&1 && return 0
  echo "[q107] BOOT FAILED $label: $(tail -3 "$OUT/boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
mem() { # mem FILE: what the three boxes and rank 0's container hold now
  { echo "== $(date -u +%T) spark1"; free -m | sed -n 2p; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' glm53-zig-r0 2> /dev/null
    for h in "$W1" "$W2"; do echo "== $h"; ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "free -m | sed -n 2p; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' 2>/dev/null | head -2"; done; } > "$1" 2>&1
}
cells() { # cells DIR LEVELS LABEL: upstream's tools against the serve on :8300
  local d=$1 levels=$2 label=$3; mkdir -p "$d"
  python3 "$TOOLS/bench_concurrent.py" "$URL" "$MODEL" --levels "$levels" --tokens 256 --reps 3 --temperatures 0,1.0 --alone --serial --label "$label" --output "$d/concurrent.json" > "$d/concurrent.out" 2>&1
  echo "[q107] $(date -u +%T) $label bench_concurrent rc=$? $(grep -c '^{' "$d/concurrent.out") cells"
  python3 "$TOOLS/bench_openai.py" "$URL" "$MODEL" --tokens 256 --reps 3 --temperatures 0 --label "$label" --output "$d/decode.json" > "$d/decode.out" 2>&1
  echo "[q107] $(date -u +%T) $label bench_openai rc=$?"
  for n in 2048 8192 32768 65536; do
    python3 "$TOOLS/bench_cache.py" "$URL" "$MODEL" --tokens 64 --repeats 2 --streams 1 --prompt-file "ids/ids-$n.json" --expected-prompt-tokens "$n" --require-cold --output "$d/cache-$n.json" > "$d/cache-$n.out" 2>&1
    echo "[q107] $(date -u +%T) $label bench_cache $n rc=$? $(python3 -c "
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
  echo "[q107] $(date -u +%T) smoke: bench_concurrent rc=$a, bench_openai rc=$b, bench_cache rc=$c"
  if [ "$a" != 0 ] || [ "$b" != 0 ] || [ "$c" != 0 ]; then
    for f in concurrent decode cache; do echo "[q107] smoke $f.out: $(tail -4 "$d/$f.out" | tr '\n' ' ' | cut -c1-400)"; done
    echo "[q107] UPSTREAM'S TOOLS DO NOT RUN AGAINST THIS SERVE: nothing is measured"; exit 1
  fi
}
ours() { # ours DIR LABEL: queue89's cold chat cells and its two conversations; longctx.py's rows, which score91.py and decide84.py already read
  local d=$1 label=$2 salt t1 turns add k
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$d/ours-rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$d/ours-probe.out" 2>&1
  echo "[q107] $(date -u +%T) $label cold chat rc=$? $(grep -o '"ttft_ms": [0-9]*' "$d/ours-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  for spec in "c74 100000 8 1000" "c3k 100000 10 2500"; do
    read -r salt t1 turns add <<< "$spec"; rm -f "$d/chain-$salt.json"
    for k in $(seq 1 "$turns"); do
      python3 longctx.py chain 8300 "$d/chain-$salt.json" --t1 "$t1" --add "$add" --salt "$salt" --tag "$salt" --n 4 --out "$d/ours-rows.jsonl" --log-cmd "$ZLOG" > "$d/chain-$salt-$k.out" 2>&1 || { echo "[q107] $salt turn $k FAILED"; break; }
    done
    echo "[q107] $(date -u +%T) $label chain $salt: $(grep -a -c "\"tag\": \"$salt\"" "$d/ours-rows.jsonl") turn row(s) so far"
  done
  grep -a '"case": "chain"' "$d/ours-rows.jsonl" > "$d/chain.jsonl"  # where decide84.py and score91.py read a boot's conversation
  grep -a '"case": "cold"' "$d/ours-rows.jsonl" >> "$OUT/rows.jsonl"  # where score91.py reads a boot's cold cells (tag = label)
}
warm_lines() { # warm_lines: the line counts for the three warm sizes, calibrated once per queue (the first st boot) into $OUT/warm-lines.json and reused on every later boot; 0 when the file is ready
  if [ -s "$OUT/warm-lines.json" ]; then
    echo "[q107] $(date -u +%T) warm lines reused: $(python3 -c "import json; r = json.load(open('$OUT/warm-lines.json')); print('lines', r['lines'], 'from', r['calibration'])" 2>&1 | tail -1)"
    return 0
  fi
  local n rc
  for n in 400 800; do
    python3 "$TOOLS/bench_warm_turns.py" "$URL" "$MODEL" --phase cold --case-id "q94-cal-$n" --repeat-lines "$n" --max-tokens 8 --seed 4100 --output "$OUT/warm-cal-$n.json" > "$OUT/warm-cal-$n.out" 2>&1
    rc=$?
    if [ ! -s "$OUT/warm-cal-$n.json" ]; then
      echo "[q107] $(date -u +%T) warm calibration at $n lines: rc=$rc no report ($(tail -1 "$OUT/warm-cal-$n.out" | cut -c1-160))"
      return 1
    fi
    echo "[q107] $(date -u +%T) warm calibration at $n lines: rc=$rc $(python3 -c "import json; print('prompt_tokens', json.load(open('$OUT/warm-cal-$n.json'))['first_prompt_tokens_tokenizer'])" 2>&1 | tail -1)"
  done
  # tokens = a + b*lines from the two runs; the line count for a target token count is (target - a) / b
  python3 -c "
import json
p = {n: json.load(open('$OUT/warm-cal-%d.json' % n))['first_prompt_tokens_tokenizer'] for n in (400, 800)}
b = (p[800] - p[400]) / 400.0
a = p[400] - b * 400
targets = {'8k': 8192, '32k': 32768, '120k': 122880}
lines = {size: int(round((target - a) / b)) for size, target in targets.items()}
json.dump({'targets': targets, 'lines': lines, 'calibration': {'400': p[400], '800': p[800]}, 'a': a, 'b': b}, open('$OUT/warm-lines.json', 'w'))
print('a', round(a, 2), 'b', round(b, 4), 'lines', lines)" > "$OUT/warm-lines.out" 2>&1
  if [ -s "$OUT/warm-lines.json" ]; then echo "[q107] $(date -u +%T) warm lines calibrated: $(tail -1 "$OUT/warm-lines.out")"; return 0; fi
  echo "[q107] $(date -u +%T) warm calibration failed: $(tail -2 "$OUT/warm-lines.out" | tr '\n' ' ' | cut -c1-300)"
  return 1
}
warm() { # warm DIR LABEL: upstream's chat-turn tool at the three sizes, a report only; a tool failure prints its rc and never stops the queue
  local d=$1 label=$2 size target seed lines rc
  warm_lines || { echo "[q107] $(date -u +%T) $label warm cells skipped: no $OUT/warm-lines.json"; return 0; }
  for spec in "8k 8192 8192" "32k 32768 32768" "120k 122880 122880"; do
    read -r size target seed <<< "$spec"
    lines=$(python3 -c "import json; print(json.load(open('$OUT/warm-lines.json'))['lines']['$size'])" 2>/dev/null)
    [ -n "$lines" ] || { echo "[q107] $label warm $size: no line count in $OUT/warm-lines.json"; continue; }
    python3 "$TOOLS/bench_warm_turns.py" "$URL" "$MODEL" --phase cold --case-id "q94-$size" --repeat-lines "$lines" --max-tokens 8 --seed "$seed" --output "$d/warm-$size.json" > "$d/warm-$size.out" 2>&1
    rc=$?
    if [ -s "$d/warm-$size.json" ]; then
      echo "[q107] $(date -u +%T) $label warm $size: rc=$rc $(python3 -c "
import json
r = json.load(open('$d/warm-$size.json'))
f = r['first_turn']
print('prompt_tokens', r['first_prompt_tokens_tokenizer'], 'of target $target;', 'repeat_lines', r['repeat_lines'], '; cached_tokens', f.get('cached_tokens'), '; engine_ttft_s', f.get('engine_time_to_first_token_seconds'), '; widths', f.get('prefill_widths'), '; qualified', r['qualified'])" 2>&1 | tail -1)"
    else echo "[q107] $(date -u +%T) $label warm $size: rc=$rc no report ($(tail -1 "$d/warm-$size.out" | cut -c1-160))"; fi
  done
}
unit() { # unit LABEL TAG XENV MODE: a fresh boot and every cell; MODE hk keeps the prompt cache's gauges and the switch's log lines, st adds our own cells and upstream's warm turns
  local label=$1 tag=$2 xenv=$3 mode=$4
  room || return
  case "$HAVE" in *" $tag "*) ;; *) echo "[q107] $label: image glm53-zig:$tag is not in the window (absent, unbuilt or dropped by a device check): skipped"; return ;; esac
  boot "$label" "$tag" "$xenv" || return
  local d="$OUT/$label"; mkdir -p "$d"
  docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | head -n 300 > "$d/r0-boot.log"
  echo "[q107] $label up (image $tag, XENV='$xenv'): $(grep -a -c -E 'TF_GLM_(HEAD_SKIP|SOLO_TO_START)' "$d/r0-boot.log") switch line(s) in rank 0's boot log; $(grep -a -m1 -E 'CUDA sm_|streams at once' "$d/r0-boot.log" | cut -c1-160)"
  mem "$d/mem-idle.txt"
  if [ "$SMOKED" = 0 ]; then SMOKED=1; smoke; fi
  cells "$d" 1,2,4 "$label"
  case "$mode" in
    hk)
      curl -sf "$URL/metrics" 2> /dev/null | grep -a -E 'prompt_cache_(states|bytes)' > "$d/metrics-after.txt"
      echo "[q107] $(date -u +%T) $label metrics-after: $(grep -a -c 'prompt_cache_states' "$d/metrics-after.txt") states line(s), $(grep -a -m1 'prompt_cache_bytes' "$d/metrics-after.txt" | cut -c1-120)"
      docker logs glm53-zig-r0 2>&1 | grep -a 'TF_GLM_HEAD_SKIP' > "$d/head-skip-line.txt"
      echo "[q107] $(date -u +%T) $label head-skip line: $(grep -a -c 'TF_GLM_HEAD_SKIP=1: the MTP head absorbs no prompt rows' "$d/head-skip-line.txt") line(s) in the whole rank 0 log" ;;
    st)
      ours "$d" "$label"
      warm "$d" "$label"
      echo "[q107] $label solo-to-start boot line: $(docker logs glm53-zig-r0 2>&1 | grep -a -m1 'a solo prompt step may end' | cut -c1-160)" ;;
  esac
  mem "$d/mem-after.txt"
  docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 400 > "$d/r0-after.log"
}
profunit() { # profunit LABEL XENV: a phsk boot with TF_GLM_PROF=1, ONE cold 8,192-id cache request, and rank 0's profile lines of that request
  local label=$1 xenv=$2
  room || return
  case "$HAVE" in *" phsk "*) ;; *) echo "[q107] $label: image phsk is not in the window (absent, unbuilt or dropped by a device check): skipped"; return ;; esac
  boot "$label" phsk "$xenv" || return
  local d="$OUT/$label" since; mkdir -p "$d"
  docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | head -n 300 > "$d/r0-boot.log"
  since=$(date +%s)
  python3 "$TOOLS/bench_cache.py" "$URL" "$MODEL" --tokens 64 --repeats 1 --streams 1 --prompt-file ids/ids-8192.json --expected-prompt-tokens 8192 --require-cold --output "$d/cache-8192.json" > "$d/cache-8192.out" 2>&1
  echo "[q107] $(date -u +%T) $label one cold 8,192-id request rc=$? $(python3 -c "
import json
r = json.load(open('$d/cache-8192.json'))
print('qualified', r['qualified'], 'first ttft_s', r['rows'][0].get('ttft_s'), 'cache_state', r['rows'][0].get('cache_state'))" 2>&1 | tail -1)"
  docker logs --since "$since" glm53-zig-r0 2>&1 | grep -a 'glm prompt' > "$d/prof.txt"
  echo "[q107] $label prof: $(grep -a -c 'glm prompt chunk' "$d/prof.txt") chunk line(s), $(grep -a -c 'stage=mtp' "$d/prof.txt") mtp stage line(s)"
  mem "$d/mem-after.txt"
}
unit hk-A1 p9f "$XH" hk
unit hk-B1a phsk "$XH $HS" hk
unit hk-B0 phsk "$XH" hk
unit hk-B1b phsk "$XH $HS" hk
unit hk-A2 p9f "$XH" hk
exit 0
