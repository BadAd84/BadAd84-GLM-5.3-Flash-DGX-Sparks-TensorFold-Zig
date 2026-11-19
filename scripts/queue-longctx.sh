#!/bin/bash
# queue-longctx.sh [TAG] - on spark1, detached, with production stopped (it stays down for the speed-parity campaign; the GLM
# watchdogs stay inactive): long prompts, resumed conversations and loaded decode on the recipe as scripts/serve.sh defines it (image rs2x3,
# KNOBS=measured), each arm a fresh boot through zig-tp3.sh, measured by longctx.py (and streams_ids.py for the decode cells)
# into ~/bench/longctx-TAG/rows.jsonl, compared with production/SPEED-TARGET.md by longctx_table.py (table.md, every arm
# labelled with its boot shape); production is left down. LONGCTX-DONE in the log.
#   d4     the deployed shape, P=4 with context 1,048,576 (production's --parallel 4 --context 1048576; its --spill-gib and
#          --snapshot-dir are refused by this engine for GLM, so no tier flag is passed): boot facts; cold 1k/8k/32k/120k x3
#          idle; warm turn (kept 100k + 2k) x3 idle; under three decoding streams: cold 32k x3 and the warm turn x3; decode
#          cells of 4, 6 and 8 clients (streams_ids.py, production's prompts as ids; past 4 they queue for a lane);
#          production's tier_chain conversation, turn 1 (~596k, cold) and turn 2 (from the kept states)
#   d4k    every rank SIGKILLed at once, the deployed shape booted again: boot facts after a kill; chain turn 3 (this engine
#          keeps no disk tier for GLM: a cold pass); the longest prompt a 1,048,576 window admits
#   d1 d8  boot facts at P=1 and P=8 with context 1,048,576, where they boot
#   r2 r4 r6 r8  boot facts at zig-tp3.sh's per-P contexts (262,144; P=8 196,608)
#   rs4    the deployed shape plus TF_GLM_REQUEST_STARTS=1 (upstream's message-start cuts, default off, an arithmetic change):
#          the warm turn x3 idle and x3 under load, cold 32k x3
#   solo4  the deployed shape plus TF_GLM_CHUNK_SOLO=4096 (two grid chunks a pass while nothing decodes): cold 8k/32k/120k x2
# If the deployed shape does not boot, its cases run where this engine holds them, each row labelled with that shape: the
# first-token and decode cases on r4 (P=4, 262,144), the conversation on P=1 at 1,048,576 (d1c, then d1k after the kill),
# rs4 and solo4 at 262,144.
# Every arm (and the longest prompt) starts only if its worst case (EST_<arm> minutes) fits what is left of BUDGET_MIN (165),
# and a long request's timeout is what is left less 5 minutes, so the window ends inside about three hours.
# Env: ARMS (the list above, in order), BUDGET_MIN, EST_<arm>, IMAGE, the sizes below. Every command it drives is a variable
# (ZTP3, ZSTOP, DOCKER, SSH, SYSTEMCTL, PROD_START, the ports), so dryrun.sh runs it end to end on stubs.
set -u
TAG=${1:-$(date -u +%m%d-%H%M)}
G=${G:-$HOME/work/glm53-zig}
OUT=${OUT:-$HOME/bench/longctx-$TAG}
IMAGE=${IMAGE:-glm53-zig:rs2x3}
ZPORT=${ZPORT:-8300}
PROD_PORT=${PROD_PORT:-8888}
PROD_START=${PROD_START:-$HOME/glm-v110-start.sh}
PROD_POLL=${PROD_POLL:-10}
ZTP3=${ZTP3:-$G/zig-tp3.sh}
ZSTOP=${ZSTOP:-$G/zig-tp3-stop.sh}
DOCKER=${DOCKER:-docker}
SSH=${SSH:-ssh}
SYSTEMCTL=${SYSTEMCTL:-systemctl}
WORKERS=${WORKERS:?set WORKERS to the ssh targets of ranks 1 and 2, space separated, for example "adam@spark2 adam@spark3"}
export LONGCTX_WORKERS="${WORKERS// /,}"
ARMS=${ARMS:-d4 d4k d1 d8 r2 r4 r6 r8 rs4 solo4}
BUDGET_MIN=${BUDGET_MIN:-165}
EST_d4=${EST_d4:-50}
EST_d4k=${EST_d4k:-30}
EST_longest=${EST_longest:-35}
EST_d1=${EST_d1:-4}
EST_d8=${EST_d8:-4}
EST_r2=${EST_r2:-4}
EST_r4=${EST_r4:-4}
EST_r6=${EST_r6:-4}
EST_r8=${EST_r8:-4}
EST_rs4=${EST_rs4:-15}
EST_solo4=${EST_solo4:-12}
CHAIN_TIMEOUT=${CHAIN_TIMEOUT:-3600}
LONGEST_TIMEOUT=${LONGEST_TIMEOUT:-5400}
COLD_SIZES=${COLD_SIZES:-1000,8000,32000,120000}
COLD_LOAD=${COLD_LOAD:-32000}
SOLO_SIZES=${SOLO_SIZES:-8000,32000,120000}
REPS=${REPS:-3}
WARM_BASE=${WARM_BASE:-100000}
WARM_ADD=${WARM_ADD:-2000}
LOAD_TOKENS=${LOAD_TOKENS:-3000}
LOAD_MAX=${LOAD_MAX:-8192}
DECODE_CLIENTS=${DECODE_CLIENTS:-4 6 8}
DECODE_TOKENS=${DECODE_TOKENS:-400}
DECODE_ROUNDS=${DECODE_ROUNDS:-3}
CHAIN_T1=${CHAIN_T1:-520000}
CHAIN_ADD=${CHAIN_ADD:-20000}
CTX1=${CTX1:-1048576}
CTX4=${CTX4:-262144}
CTX8=${CTX8:-196608}
DCTX=${DCTX:-$CTX1}
LOGCMD="$DOCKER logs --since {since} glm53-zig-r0"
BOOT_SETTLE=${BOOT_SETTLE:-5}

say() { echo "[longctx] $(date -u +%T) $*"; }
prod_up() { curl -sf -o /dev/null --max-time 3 "localhost:$PROD_PORT/health"; }
abort() { say "$*"; echo "LONGCTX-ABORTED $(date -u +%T)"; exit 1; }

# Production is stopped before this runs (prod-stop.sh); this script never touches a production that is up.
prod_up && abort "production answers on :$PROD_PORT: stop it (~/glm-v110-stop.sh) and both GLM watchdogs first"
$DOCKER ps --format '{{.Names}}' 2>/dev/null | grep -qx glm53-flash-tf && abort "glm53-flash-tf runs on spark1: stop production first"
for w in $WORKERS; do
  $SSH -n -o BatchMode=yes "$w" "docker ps --format '{{.Names}}'" 2>/dev/null | grep -qx glm53-flash-tf \
    && abort "glm53-flash-tf runs on $w: stop production first"
done
$SYSTEMCTL is-active --quiet glm-watchdog-system.service 2>/dev/null \
  && abort "glm-watchdog-system is active: it restarts production under a boot; stop it first"
$SYSTEMCTL --user is-active --quiet glm-watchdog.service 2>/dev/null \
  && abort "the user unit glm-watchdog is active: it restarts production under a boot; stop it first"

[ -s "$OUT/rows.jsonl" ] && abort "$OUT/rows.jsonl holds rows of an earlier run: give this window a new TAG"
mkdir -p "$OUT"
T0=$(date +%s)
ROWS=$OUT/rows.jsonl
RESTORED=0
restore() {
  [ "$RESTORED" = 1 ] && return
  RESTORED=1
  if [ -s "$ROWS" ]; then
    python3 "$G/longctx_table.py" "$ROWS" > "$OUT/table.md" 2>&1
    say "table rc $? ($OUT/table.md; rc 1: a row was rejected, named at its top)"
    cat "$OUT/table.md"
  fi
  bash "$ZSTOP" > /dev/null 2>&1
  $DOCKER rm -f glm53-zig-r0 > /dev/null 2>&1
  if [ "${RESTORE:-0}" != 1 ]; then
    say "production left down (it stays down for the speed-parity campaign; RESTORE=1 starts it)"
  elif prod_up; then
    say "production already answers"
  else
    setsid nohup bash "$PROD_START" > "$OUT/prod-restore.log" 2>&1 < /dev/null &
    for _ in $(seq 1 90); do prod_up && { say "production healthy"; break; }; sleep "$PROD_POLL"; done
    prod_up || say "PRODUCTION NOT HEALTHY after $((90 * PROD_POLL)) s: $OUT/prod-restore.log"
  fi
  say "both GLM watchdogs stay inactive"
  echo "LONGCTX-DONE $(date -u +%T)"
}
trap restore EXIT
trap 'exit 130' INT TERM

left_s() { echo $(( BUDGET_MIN * 60 - ($(date +%s) - T0) )); }
cl() { local sub=$1; shift; python3 "$G/longctx.py" "$sub" "$ZPORT" "$@" --out "$ROWS" --log-cmd "$LOGCMD"; }

boot() { # boot LABEL P CTX [XENV]: zig-tp3.sh in the background, /health polled for the first 200, then the facts row
  local label=$1 p=$2 ctx=$3 xenv=${4:-} t0 th="" tu="" rc
  bash "$ZSTOP" > /dev/null 2>&1
  sleep "$BOOT_SETTLE"
  say "boot $label: P=$p ctx=$ctx image=$IMAGE xenv='$xenv' ($(left_s) s of the budget left)"
  t0=$(date +%s.%N)
  IMAGE="$IMAGE" KNOBS=measured XENV="$xenv" PORT="$ZPORT" bash "$ZTP3" "$p" "$ctx" > "$OUT/boot-$label.log" 2>&1 &
  local zpid=$!
  while kill -0 "$zpid" 2>/dev/null; do
    if [ -z "$th" ] && curl -sf -o /dev/null --max-time 2 "localhost:$ZPORT/health"; then th=$(date +%s.%N); fi
    sleep 0.5
  done
  wait "$zpid"
  rc=$?
  tu=$(date +%s.%N)
  if [ "$rc" = 0 ] && [ -z "$th" ]; then
    for _ in $(seq 1 120); do curl -sf -o /dev/null --max-time 2 "localhost:$ZPORT/health" && { th=$(date +%s.%N); break; }; sleep 0.5; done
  fi
  local args=(--tag "$label" --n "$p" --ctx "$ctx" --boot-start "$t0" --boot-rc "$rc" --image "$IMAGE" "--xenv=$xenv"
              --ssh "$SSH" --workers "${WORKERS// /,}")
  [ -n "$th" ] && args+=(--health-at "$th")
  [ "$rc" = 0 ] && args+=(--up-at "$tu")
  [ "$rc" = 0 ] || args+=("--error=$(tail -4 "$OUT/boot-$label.log" | tr '\n' ' ' | cut -c1-400)")
  cl facts "${args[@]}" > "$OUT/$label-facts.out" 2>&1
  say "boot $label: rc $rc; $(grep -o '"boot_s": [0-9.]*' "$OUT/$label-facts.out" | head -1)"
  return "$rc"
}

keep_log() { # the arm's rank-0 log lines, as bench-client.sh keeps them, plus the startup line
  $DOCKER logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error|debug)|CUDA sm_" | tail -n 4000 > "$OUT/r0-$1.log"
}

kill_all() { # every rank's container SIGKILLed at once, as production's tier_chain does
  say "SIGKILL every rank"
  $DOCKER kill -s KILL glm53-zig-r0 > /dev/null 2>&1 &
  local i=1 w
  for w in $WORKERS; do
    $SSH -n -o BatchMode=yes "$w" "docker kill -s KILL glm53-zig-r$i" > /dev/null 2>&1 &
    i=$((i + 1))
  done
  wait
}

optional() { # optional NAME: true when its worst case (EST_NAME minutes) fits what is left of the budget
  local est_var="EST_$1"
  local est=${!est_var:-0}
  if [ "$(left_s)" -lt $((est * 60)) ]; then
    say "SKIP $1: $(left_s) s of the budget left, it takes up to $est min"
    return 1
  fi
}

long_tmo() { # long_tmo CAP: a long request's timeout, at most CAP and what is left of the budget less 5 minutes
  local l=$(( $(left_s) - 300 ))
  if [ "$l" -lt "$1" ]; then echo "$l"; else echo "$1"; fi
}

chain() { # chain STATE TAG P OUT [NOTE]: one turn of production's tier_chain conversation, if the budget leaves time for it
  local t; t=$(long_tmo "$CHAIN_TIMEOUT")
  if [ "$t" -le 120 ]; then say "SKIP a chain turn of $2: the budget is spent"; return 1; fi
  cl chain "$1" --tag "$2" --n "$3" ${5:+--note "$5"} --t1 "$CHAIN_T1" --add "$CHAIN_ADD" --timeout "$t" > "$4" 2>&1
}

load_args=(--load 3 --load-tokens "$LOAD_TOKENS" --load-max-tokens "$LOAD_MAX")
warm_args=(--warm-base "$WARM_BASE" --warm-add "$WARM_ADD")
DEPLOYED=1  # 0 once d4 has failed to boot: the deployed shape's cases then run on the shapes that hold them

first_cases() { # first_cases TAG P: cold and warm idle, cold 32k and warm beside three decoding streams, decode cells
  cl probe --tag "$1" --n "$2" --cold-sizes "$COLD_SIZES" --reps "$REPS" "${warm_args[@]}" > "$OUT/$1-idle.out" 2>&1
  cl probe --tag "$1" --n "$2" --cold-sizes "$COLD_LOAD" --reps "$REPS" "${warm_args[@]}" "${load_args[@]}" > "$OUT/$1-load3.out" 2>&1
  local c
  for c in $DECODE_CLIENTS; do
    python3 "$G/streams_ids.py" "$ZPORT" "$c" --ids "$G/prose33.json" --max-tokens "$DECODE_TOKENS" --rounds "$DECODE_ROUNDS" \
      --tag "$1/c$c" --out "$ROWS" > "$OUT/$1-c$c.out" 2>&1
  done
}

conversation() { # conversation TAG P: production's tier_chain turns 1 (cold) and 2 (from the kept states)
  chain "$OUT/chain.json" "$1" "$2" "$OUT/$1-chain1.out" && chain "$OUT/chain.json" "$1" "$2" "$OUT/$1-chain2.out"
}

after_kill() { # after_kill TAG P CTX: every rank SIGKILLed, TAG booted, chain turn 3, then the longest prompt the window admits
  if [ -s "$OUT/chain.json" ]; then kill_all; else say "$1: no conversation to resume: the boot and the longest prompt only"; fi
  boot "$1" "$2" "$3" || return
  [ -s "$OUT/chain.json" ] && chain "$OUT/chain.json" "$1" "$2" "$OUT/$1-chain3.out" after-kill
  if optional longest; then
    cl longest --tag "$1" --n "$2" --timeout "$(long_tmo "$LONGEST_TIMEOUT")" > "$OUT/$1-longest.out" 2>&1
  fi
}

mctx() { if [ "$DEPLOYED" = 1 ]; then echo "$DCTX"; else echo "$CTX4"; fi; }

run_arm() {
  case $1 in
    d4)
      if boot d4 4 "$DCTX"; then
        first_cases d4 4
        conversation d4 4
      else
        DEPLOYED=0
        say "the deployed shape (P=4, ctx $DCTX) did not boot: its cases run on r4 and on P=1, labelled with their shapes"
      fi ;;
    d4k)
      if [ "$DEPLOYED" = 1 ]; then
        after_kill d4k 4 "$DCTX"
      else
        boot d1c 1 "$CTX1" && conversation d1c 1
        after_kill d1k 1 "$CTX1"
      fi ;;
    d1) boot d1 1 "$CTX1" ;;
    d8) boot d8 8 "$DCTX" ;;
    r2) boot r2 2 "$CTX4" ;;
    r4) boot r4 4 "$CTX4" && [ "$DEPLOYED" = 0 ] && first_cases r4 4 ;;
    r6) boot r6 6 "$CTX4" ;;
    r8) boot r8 8 "$CTX8" ;;
    rs4)
      boot rs4 4 "$(mctx)" "-e TF_GLM_REQUEST_STARTS=1" || return
      cl probe --tag rs4 --n 4 --cold-sizes "$COLD_LOAD" --reps "$REPS" "${warm_args[@]}" > "$OUT/rs4-idle.out" 2>&1
      cl probe --tag rs4 --n 4 --cold-sizes "" --reps "$REPS" "${warm_args[@]}" "${load_args[@]}" > "$OUT/rs4-load3.out" 2>&1 ;;
    solo4)
      boot solo4 4 "$(mctx)" "-e TF_GLM_CHUNK_SOLO=4096" || return
      cl probe --tag solo4 --n 4 --cold-sizes "$SOLO_SIZES" --reps 2 --warm-base 0 > "$OUT/solo4.out" 2>&1 ;;
    *) say "unknown arm $1" ;;
  esac
}

say "window $TAG: arms '$ARMS', budget $BUDGET_MIN min, rows $ROWS"
{ sha256sum "$G/zig-tp3.sh" "$G/serve.sh" "$G/longctx.py" "$G/longctx_table.py" "$G/streams_ids.py" "$0"
  $DOCKER image inspect --format '{{.Id}} {{.RepoTags}}' "$IMAGE"; } > "$OUT/provenance.txt" 2>&1
df -h /home > "$OUT/disk-start.txt" 2>&1
for arm in $ARMS; do
  a0=$(date +%s)
  if optional "$arm"; then
    run_arm "$arm"
    keep_log "$arm"
    say "arm $arm done in $(( $(date +%s) - a0 )) s"
  fi
done
df -h /home > "$OUT/disk-end.txt" 2>&1
