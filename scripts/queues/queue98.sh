#!/bin/bash
# queue98.sh - on spark1, detached, after queue96.sh: E3, the served A/B of upstream's opt-in prompt-cache victim policy, TF_CACHE_EVICT unset against TF_CACHE_EVICT=decayed_resume, on
# the stack on the pin (image m130a), with upstream's own client from its main tip. No build and no device check: m130a already exists on all three ranks, and the same-image-id check
# below refuses the window rather than measure a stack that differs on a rank. Production is down for the campaign and stays down. QUEUE98-DONE.
# queue98.env: IMG (m130a) and WORKERS, plus HOURS (default 6) and WAIT_FOR (default queue96.sh); those two have defaults, so a file that omits them still runs.
#
#   The question: does decayed_resume rebuild fewer prompt rows on a long agent trace at the deployed cache budget? A host-only replay (work/cache-replay-lane/REPORT.md, sections 4 to 6)
#   predicts 0% for short or few conversations and 44% to 50% fewer rebuilt rows for six conversations at a 32,768-token prefix under every byte model it tried. E3 is that run.
#
#   images: IMG m130a (the stack on the pin). Each image must be ONE id on all three ranks; absent from spark1, or a different id on a rank, stops the queue, because both arms must
#     run the same stack. Nothing is built here.
#   units, in this order, one FRESH boot each (the policy's effect is a deterministic count of rebuilt rows, so one boot an arm decides it; the wall clock is secondary):
#     ce-A  IMG, KNOBS=prod, XENV ""                                   TF_CACHE_EVICT unset: the engine's own victim order
#     ce-B  IMG, KNOBS=prod, XENV "-e TF_CACHE_EVICT=decayed_resume"   the policy
#   every boot is the deployed shape, --parallel 4 --context 1048576, the cache budget the engine derives (no --prompt-cache-gib anywhere), the same environment on all three ranks.
#     KNOBS=prod is checked to name no TF_CACHE_EVICT (env/prod.env and its runtime section), so ce-A is the unset arm and ce-B's XENV is the only source of the policy.
#   each boot's cells, in order:
#     the SAME tiny smoke on both boots, upstream's client at --conversations 1 --rounds 1 --prefix-tokens 1024 --tokens 8 --seed 3: the client is known to work before an hour is
#       spent on it, and the two arms' STARTING CACHES ARE EQUAL BECAUSE THE SMOKE IS THE SAME REQUEST ON BOTH. A failed smoke stops the queue with a line saying so.
#     the E3 trace, upstream's client: --trace agent_loops --conversations 6 --rounds 24 --prefix-tokens 32768 --tokens 16 --seed 11, one request at a time, each measured assistant
#       reply carried into the next turn's history, two unique one-offs after every agent turn.
#     then, once both boots are done, the client's compare of ce-A's trace against ce-B's, rc logged: it exits 0 only when every reply's full token fingerprint, every request
#       identity and every prompt count agree.
#   guards: after each boot every rank container's environment is read back and must carry exactly this arm's TF_CACHE_EVICT (unset for ce-A), else the queue stops; ce-B is
#     skipped when ce-A's client did not exit 0, because P0 needs both arms qualified and ce-B would have nothing to be compared with.
#   the tools: stage/tools-up98.tar (upstream's tools/ at 46c6ee229, already staged and hash-verified), extracted into tools-up/ here exactly as queue94 extracts tools-up94.tar.
#     queue93 and queue94 also extract into tools-up/, and each queue re-extracts its own tar at its start, so this window uses its own copy whatever ran before it.
#   each arm's box, $HOME/bench/f98-c/<ce-A|ce-B>/: trace.json (the client's report), trace.out (the client's stdout, the same JSON), smoke.json and smoke.out, r0-boot.log (rank 0's
#     first 300 info/warn/error lines), r0-after.log (the log's "prompt cache" lines of the real run: the kept states, the budget and any eviction counter the engine prints),
#     metrics-before.txt and metrics-after.txt (the /metrics prompt_cache_ gauges before and after the real run), mem-idle.txt and mem-after.txt (the three boxes and rank 0's
#     container's memory after the boot and after the run). Each boot's launcher log is $HOME/bench/f98-boots/<label>.log, the check-env log $HOME/bench/f98-check-env.log, and
#     compare.json and compare.out sit in $HOME/bench/f98-c/.
#   scripts/queue-scores/score98.py reads trace.json and compare.json; its rules were written before any row existed.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue98.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
export KEEP=1
export LEARN=0 XSERVE=""  # zig-tp3.sh forwards both to every rank: no disk tier and no extra serve flags, so both arms start with an empty cache and differ only in XENV
IMG=${IMG:?set IMG}
SERVED=GLM-5.3-Flash-EXL3  # the name rank 0 serves under (serve.sh --name); not MODEL, which serve.sh reads as the container's model path
WAIT_FOR=${WAIT_FOR:-queue96.sh}
BENCH=$HOME/bench; OUT=$BENCH/f98-c
URL=http://127.0.0.1:8300
TOOLS=$G/tools-up/tools
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE98-DONE $(date -u +%T)"; }
echo "[q98] $(date -u +%T) start; waiting for $WAIT_FOR"
while pgrep -f "$WAIT_FOR" > /dev/null; do sleep 60; done
trap finish EXIT
DEADLINE=$(( $(date +%s) + ${HOURS:-6} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
mkdir -p "$OUT"
echo "[q98] $(date -u +%T) $WAIT_FOR is done; IMG=$IMG; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids_of() { { docker images --no-trunc --format '{{.ID}}' "$1" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $1 | head -1"; done; }; }
docker images --format '{{.ID}}' "$IMG" | grep -q . || { echo "[q98] IMAGE $IMG IS ABSENT on spark1: nothing to measure (nothing is built here)"; exit 1; }
ids=$(ids_of "$IMG")
if [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; then
  echo "[q98] $IMG ids: $(echo $ids | cut -c1-80)"
else
  echo "[q98] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS: nothing to measure (ids: $(echo $ids | tr '\n' ' '))"; exit 1
fi
echo "[q98] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12); env: $(cat env/prod.env env/dev.env | sha256sum | cut -c1-12)"
python3 check-env.py --env-dir env > "$BENCH/f98-check-env.log" 2>&1; echo "[q98] check-env rc=$?: $(tail -1 "$BENCH/f98-check-env.log")"
RT=$(bash env/words.sh prod runtime 2> /dev/null)
if grep -q 'TF_CACHE_EVICT' env/prod.env 2> /dev/null || printf '%s\n' "$RT" | grep -q 'TF_CACHE_EVICT'; then
  echo "[q98] KNOBS=prod's recipe names TF_CACHE_EVICT (env/prod.env or its runtime section), so ce-A would not be the unset arm: nothing is measured"; exit 1
fi
echo "[q98] KNOBS=prod names no TF_CACHE_EVICT (env/prod.env, and $(echo "$RT" | wc -w) runtime settings), so ce-A is the unset arm and ce-B's XENV is the only source of the policy"
bash prod-stop.sh || { echo "[q98] PRODUCTION DID NOT STOP"; exit 1; }
stop
rm -rf tools-up && mkdir tools-up
tar -xf stage/tools-up98.tar -C tools-up || { echo "[q98] stage/tools-up98.tar did not extract: upstream's client from 46c6ee229 is required"; exit 1; }
echo "[q98] upstream tools (46c6ee229, stage/tools-up98.tar): $(ls tools-up/tools/*.py | wc -l) python files, bench_cache_agents sha256 $(sha256sum "$TOOLS/bench_cache_agents.py" | cut -c1-12)"
boot() { # boot LABEL IMAGE KNOBS XENV: the Zig serve up on :8300 at --parallel 4 --context 1048576, 0 when it is
  local label=$1 image=$2 knobs=$3 xenv=$4; mkdir -p "$BENCH/f98-boots"; stop
  IMAGE=$image KNOBS=$knobs XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$BENCH/f98-boots/$label.log" 2>&1 && return 0
  echo "[q98] BOOT FAILED $label: $(tail -3 "$BENCH/f98-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
mem() { # mem FILE: what the three boxes and rank 0's container hold now
  { echo "== $(date -u +%T) spark1"; free -m | sed -n 2p; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' glm53-zig-r0 2> /dev/null
    for h in "$W1" "$W2"; do echo "== $h"; ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "free -m | sed -n 2p; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' 2>/dev/null | head -2"; done; } > "$1" 2>&1
}
cenv() { # cenv HOST CONTAINER: the container's environment, one NAME=value a line; HOST - is spark1
  if [ "$1" = "-" ]; then docker inspect "$2" --format '{{range .Config.Env}}{{println .}}{{end}}' 2> /dev/null
  else ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$1" "docker inspect $2 --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null"; fi
}
headline() { # headline FILE: the client report's own flags and sums on one line, or why there is none
  python3 -c "
import json, sys
try:
    r = json.load(open(sys.argv[1], encoding='utf-8'))
    s = r.get('summary') or {}
    print('qualified', r.get('qualified'), 'completed_schedule', r.get('completed_schedule'), 'requests', s.get('requests'),
          'rebuilt_rows', s.get('rebuilt_rows'), 'ttft_sum_s', s.get('ttft_sum_s'), 'setup_error', r.get('setup_error'))
except Exception as exc:
    print('no report (' + type(exc).__name__ + ')')
" "$1" 2>&1 | tail -1
}
unit() { # unit LABEL XENV: a fresh P=4 boot, the identical smoke, the E3 trace, and the logs, gauges and memory of both
  local label=$1 xenv=$2 d="$OUT/$1" rc since t0 wall
  LASTRC=none
  room || { echo "[q98] $label: the deadline $(date -u -d @$DEADLINE +%T) has passed, this arm is skipped"; return; }
  boot "$label" "$IMG" prod "$xenv" || return
  mkdir -p "$d"
  want=$(printf '%s\n' "$xenv" | grep -o 'TF_CACHE_EVICT=[a-z_]*' | head -1)
  for pair in "-:glm53-zig-r0" "$W1:glm53-zig-r1" "$W2:glm53-zig-r2"; do
    envs=$(cenv "${pair%%:*}" "${pair#*:}"); seen=$(printf '%s\n' "$envs" | grep -a '^TF_CACHE_EVICT=' | head -1)
    printf '%s\n' "$envs" | grep -a -q '^TF_GLM_RANK=' || { echo "[q98] $label: cannot read the environment of ${pair#*:} (host ${pair%%:*}): stopping the queue"; exit 1; }
    [ "$seen" = "$want" ] || { echo "[q98] $label: ${pair#*:} carries '${seen:-TF_CACHE_EVICT unset}' but this arm needs '${want:-TF_CACHE_EVICT unset}', so the arms would not differ as designed: stopping the queue"; exit 1; }
  done
  echo "[q98] $(date -u +%T) $label environment read back on all three ranks: ${want:-TF_CACHE_EVICT unset}"
  docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | head -n 300 > "$d/r0-boot.log"
  echo "[q98] $(date -u +%T) $label up (image $IMG, KNOBS=prod, XENV='$xenv'): $(grep -a -m1 'prompt cache' "$d/r0-boot.log" | cut -c1-160)"
  mem "$d/mem-idle.txt"
  curl -sf "$URL/metrics" 2> /dev/null | grep -a 'prompt_cache_' > "$d/metrics-before.txt"
  echo "[q98] $(date -u +%T) $label metrics-before: $(grep -a -c 'prompt_cache_' "$d/metrics-before.txt") prompt cache gauge line(s); $(grep -a -m1 'prompt_cache_bytes' "$d/metrics-before.txt" | cut -c1-100)"
  timeout 3600 python3 "$TOOLS/bench_cache_agents.py" run "$URL" "$SERVED" --trace agent_loops --conversations 1 --rounds 1 --prefix-tokens 1024 --tokens 8 --seed 3 --output "$d/smoke.json" > "$d/smoke.out" 2>&1; rc=$?
  echo "[q98] $(date -u +%T) $label smoke (1 conversation, 1 round, prefix 1024, 8 reply tokens, seed 3) rc=$rc: $(headline "$d/smoke.json")"
  if [ "$rc" != 0 ] || [ ! -s "$d/smoke.json" ]; then
    echo "[q98] THE SMOKE DID NOT PASS ON $label, so upstream's client does not run against this serve and the E3 trace is not started: stopping the queue"
    tail -4 "$d/smoke.out" | sed 's/^/[q98]   /'
    exit 1
  fi
  since=$(date +%s); t0=$(date +%s)
  timeout 43200 python3 "$TOOLS/bench_cache_agents.py" run "$URL" "$SERVED" --trace agent_loops --conversations 6 --rounds 24 --prefix-tokens 32768 --tokens 16 --seed 11 --output "$d/trace.json" > "$d/trace.out" 2>&1; rc=$?
  wall=$(( $(date +%s) - t0 ))
  curl -sf "$URL/metrics" 2> /dev/null | grep -a 'prompt_cache_' > "$d/metrics-after.txt"
  docker logs --since "$since" glm53-zig-r0 2>&1 | grep -a -i 'prompt cache' > "$d/r0-after.log"
  mem "$d/mem-after.txt"
  echo "[q98] $(date -u +%T) $label E3 trace (6 conversations, 24 rounds, prefix 32768, seed 11) rc=$rc wall=${wall}s: $(headline "$d/trace.json")"
  echo "[q98] $(date -u +%T) $label metrics-after: $(grep -a -c 'prompt_cache_' "$d/metrics-after.txt") prompt cache gauge line(s); r0-after: $(wc -l < "$d/r0-after.log") prompt cache log line(s)"
  LASTRC=$rc
}
unit ce-A ""
if [ "$LASTRC" = 0 ]; then
  unit ce-B "-e TF_CACHE_EVICT=decayed_resume"
else
  echo "[q98] ce-A did not produce a qualified trace (client rc: $LASTRC): ce-B is skipped, because P0 needs both arms qualified and there would be nothing to compare it with"
fi
if [ -s "$OUT/ce-A/trace.json" ] && [ -s "$OUT/ce-B/trace.json" ]; then
  python3 "$TOOLS/bench_cache_agents.py" compare "$OUT/ce-A/trace.json" "$OUT/ce-B/trace.json" --output "$OUT/compare.json" > "$OUT/compare.out" 2>&1; rc=$?
  echo "[q98] $(date -u +%T) compare rc=$rc: $(python3 -c "
import json
try:
    r = json.load(open('$OUT/compare.json', encoding='utf-8'))
    t = (r.get('traces') or {}).get('agent_loops') or {}
    a, b = t.get('a') or {}, t.get('b') or {}
    print('qualified', r.get('qualified'), 'token_exact', r.get('token_exact'), 'issues', r.get('issues'),
          'rebuilt_rows A', a.get('rebuilt_rows'), 'B', b.get('rebuilt_rows'), 'ttft_sum_s A', a.get('ttft_sum_s'), 'B', b.get('ttft_sum_s'))
except Exception as exc:
    print('no compare report (' + type(exc).__name__ + ')')
" 2>&1 | tail -1)"
else
  echo "[q98] compare not run: $OUT/ce-A/trace.json or $OUT/ce-B/trace.json is missing (an arm was skipped or its client failed)"
fi
echo "[q98] $(date -u +%T) done; score the run with: python scripts/queue-scores/score98.py --dir $OUT"
exit 0
