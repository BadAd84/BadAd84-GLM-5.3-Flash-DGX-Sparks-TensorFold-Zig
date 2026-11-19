#!/bin/bash
# queue-disk-tier.sh [TAG] - on spark1, detached, with production stopped (it stays down for the speed-parity campaign; the
# GLM watchdogs stay inactive): GLM-5.3-Flash's conversation states on disk (--learn-conversations, upstream PR #1411) on the
# TP=3 serve at the deployed shape (--parallel 4 --context 1048576), each boot through zig-tp3.sh, measured by
# disk.py into ~/bench/disktier-TAG/rows.jsonl and tabled by disk_table.py (table.md); production is left down.
# DISKTIER-DONE in the log.
#   k1   a boot with the disk tier on a fresh store: conversations M32 and M120 (markers at 2%, 50%, 97%) turn 1 cold
#        and turn 2 from RAM; the long conversation L (production's tier_chain text, ~596k tokens) turn 1 cold beside
#        three decoding streams (the first save of a long state, and the other streams' decode while it is staged and
#        written) and turn 2 from RAM; M32 and M120 turn 3 after eviction (fillers only if L's states left theirs in
#        RAM); every save drained
#   k2   every rank SIGKILLed once the saves are written, booted again on the same store: L turn 3 from disk, its
#        quote probe (turn 1's lines at 2%, 50%, 97%) on the state that left, M32 and M120 turn 4 from disk
#   k3   a clean stop (SIGTERM, rank 0 first, its saves written), booted again: L turn 4, M32 and M120 turn 5 from disk
#   ref  a boot without the disk tier and with --prompt-cache-gib 0: every recorded prompt cold, REF_ORDER first, while
#        the budget lasts. The gate: every resumed turn's reply equals the cold reply to the same messages
# Image: IMAGE (default glm53-zig:pr1411, built from the PR head tree), KNOBS=off with XENV_KNOBS, the recipe knobs that
# tree reads (TF_GLM_KDA_PAD, TF_GLM_INDEX_CUDA; the TF_GLM_OVN_* and TF_EXL3_DEC_ORDER switches are this repo's
# patches). For an image of our series plus the PR: KNOBS=measured XENV_KNOBS=''.
# The store lives under the Zig containers' own mount: LEARN_HOST ($HOME/.cache/huggingface/glm53-zig-learn/TAG) is
# LEARN_CTR inside every rank's container (rank 0 alone writes it). The engine writes it as root and makes its
# directories 0700, so this script reads its size and removes it through a container of the same image; it is kept
# when a disk tier check failed (table rc 3) or KEEP_LEARN=1.
# Every step starts only if its worst case fits what is left of BUDGET_MIN; production is left down at the end unless
# RESTORE=1 (the owner ending the campaign). Every command it drives is a variable (ZTP3, ZSTOP, DOCKER, SSH,
# SYSTEMCTL, PROD_START, the ports), so dryrun.sh runs it end to end on stubs.
set -u
TAG=${1:-$(date -u +%m%d-%H%M)}
G=${G:-$HOME/work/glm53-zig}
OUT=${OUT:-$HOME/bench/disktier-$TAG}
IMAGE=${IMAGE:-glm53-zig:pr1411}
KNOBS=${KNOBS:-off}
XENV_KNOBS=${XENV_KNOBS--e TF_GLM_KDA_PAD=1 -e TF_GLM_INDEX_CUDA=1}  # unset: the PR tree's two knobs; '' for KNOBS=measured
P=${P:-4}
CTX=${CTX:-1048576}
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
LEARN_HOST=${LEARN_HOST:-$HOME/.cache/huggingface/glm53-zig-learn/$TAG}
LEARN_CTR=${LEARN_CTR:-/root/.cache/huggingface/glm53-zig-learn/$TAG}
LEARN_GIB=${LEARN_GIB:-128}
LEARN_DAILY_GIB=${LEARN_DAILY_GIB:-512}
LEARN_MIN_FREE_GIB=${LEARN_MIN_FREE_GIB:-40}
LEARN_FLAGS="--learn-conversations --learn-dir $LEARN_CTR --learn-gib $LEARN_GIB --learn-daily-gib $LEARN_DAILY_GIB --learn-min-free-gib $LEARN_MIN_FREE_GIB"
REF_FLAGS=${REF_FLAGS:---prompt-cache-gib 0}
STEPS=${STEPS:-k1 k2 k3 ref}
BUDGET_MIN=${BUDGET_MIN:-150}
EST_k1=${EST_k1:-25}
EST_k2=${EST_k2:-12}
EST_k3=${EST_k3:-12}
EST_ref=${EST_ref:-12}
M_SIZES=${M_SIZES:-32000 120000}
CHAIN_T1=${CHAIN_T1:-520000}
CHAIN_ADD=${CHAIN_ADD:-20000}
LOAD=${LOAD:-3}
LOAD_TOKENS=${LOAD_TOKENS:-3000}
LOAD_MAX=${LOAD_MAX:-8192}
BASE_S=${BASE_S:-15}
FILLER=${FILLER:-100000}
FILLERS_MAX=${FILLERS_MAX:-4}
QUOTE=${QUOTE:-1}
FLUSH=${FLUSH:-1}                 # k2 ends with S<FLUSH_SIZE>'s first save in flight at the clean stop; k3 resumes it
FLUSH_SIZE=${FLUSH_SIZE:-120000}
ENOSPC_SIZE=${ENOSPC_SIZE:-4g}    # the enospc step's tmpfs (opt-in: add enospc to STEPS)
ENOSPC_INODES=${ENOSPC_INODES:-600}
DRAIN_TIMEOUT=${DRAIN_TIMEOUT:-900}
DRAIN_STABLE=${DRAIN_STABLE:-3}
DRAIN_STILL=${DRAIN_STILL:-30}
STOP_GRACE=${STOP_GRACE:-180}
REF_ORDER=${REF_ORDER:-M32000/t2,M32000/t3,M32000/t4,M32000/t5,M120000/t2,M120000/t3,M120000/t4,M120000/t5,S120000/t2,L/t3,L/t3q,L/t4,L/t2,E32000/t2,M32000/t1,M120000/t1,S120000/t1,E32000/t1,E120000/t1,L/t1}
REF_MIN_LEFT=${REF_MIN_LEFT:-660}
LOGCMD="$DOCKER logs --since {since} glm53-zig-r0"
BOOT_SETTLE=${BOOT_SETTLE:-5}

say() { echo "[disktier] $(date -u +%T) $*"; }
prod_up() { curl -sf -o /dev/null --max-time 3 "localhost:$PROD_PORT/health"; }
abort() { say "$*"; echo "DISKTIER-ABORTED $(date -u +%T)"; exit 1; }

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
[ -n "$(ls -A "$LEARN_HOST" 2>/dev/null)" ] && abort "$LEARN_HOST is not empty: a store of an earlier run; give this window a new TAG"
free_gib=$(df -BG --output=avail "$(dirname "$LEARN_HOST")" 2>/dev/null | tail -1 | tr -dc 0-9)
need=$((LEARN_GIB + LEARN_MIN_FREE_GIB))
[ -n "$free_gib" ] && [ "$free_gib" -lt "$need" ] && abort "$free_gib GiB free under $(dirname "$LEARN_HOST"); the store may take $LEARN_GIB GiB and keeps $LEARN_MIN_FREE_GIB free"

mkdir -p "$OUT/conv" "$OUT/prompts" "$LEARN_HOST"
T0=$(date +%s)
ROWS=$OUT/rows.jsonl
RESTORED=0
RC_TABLE=""
learn_in() { # learn_in CMD ARGS...: CMD inside a container of IMAGE with the store's parent at /learn (the store is root's)
  local cmd=$1; shift
  $DOCKER run --rm -v "$(dirname "$LEARN_HOST"):/learn" --entrypoint "$cmd" "$IMAGE" "$@"
}
restore() {
  [ "$RESTORED" = 1 ] && return
  RESTORED=1
  if [ -s "$ROWS" ]; then
    python3 "$G/disk_table.py" "$ROWS" > "$OUT/table.md" 2>&1
    RC_TABLE=$?
    say "table rc $RC_TABLE ($OUT/table.md; rc 1: a row was rejected, rc 3: a disk tier check failed, both named at its top)"
    cat "$OUT/table.md"
  fi
  bash "$ZSTOP" > /dev/null 2>&1
  $DOCKER rm -f glm53-zig-r0 > /dev/null 2>&1
  if [ "${KEEP_LEARN:-0}" = 1 ] || [ "$RC_TABLE" = 3 ]; then
    say "the store stays at $LEARN_HOST (root's; remove it with: docker run --rm -v $(dirname "$LEARN_HOST"):/learn --entrypoint rm $IMAGE -rf /learn/$(basename "$LEARN_HOST"))"
  else
    learn_in rm -rf "/learn/$(basename "$LEARN_HOST")" > /dev/null 2>&1 && say "the store at $LEARN_HOST removed"
  fi
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
  echo "DISKTIER-DONE $(date -u +%T)"
}
trap restore EXIT
trap 'exit 130' INT TERM

left_s() { echo $(( BUDGET_MIN * 60 - ($(date +%s) - T0) )); }
BOOT=""
dk() { local sub=$1; shift; python3 "$G/disk.py" "$sub" "$ZPORT" --tag "$BOOT" --n "$P" --out "$ROWS" --log-cmd "$LOGCMD" \
  --prompts "$OUT/prompts" --drain-timeout "$DRAIN_TIMEOUT" --drain-stable "$DRAIN_STABLE" --drain-still "$DRAIN_STILL" "$@"; }
turn() { # turn CONV EXPECT LABEL [disk.py turn options]: the next turn of CONV, its saves drained
  local conv=$1 expect=$2 label=$3; shift 3
  local kind=marker size=0 drain=--drain
  case $conv in L) kind=chain ;; [MSE]*) size=${conv:1} ;; esac
  if [ "${1:-}" = --no-drain ]; then drain=""; shift; fi
  dk turn "$conv" --conv-dir "$OUT/conv" --kind "$kind" --size "$size" --t1 "$CHAIN_T1" --add "$CHAIN_ADD" \
    --expect "$expect" --label "$label" $drain "$@" > "$OUT/$BOOT-$conv-$label.out" 2>&1
  say "$BOOT $conv $label: rc $? $(grep -o '"case_id": "[^"]*"\|"cached_tokens": [0-9]*\|"ttft_ms": [0-9]*' "$OUT/$BOOT-$conv-$label.out" | tr '\n' ' ')"
}
grid_of() { # grid_of CONV: the position of CONV's newest kept state (disk.py newest_kept: its last turn that kept one)
  python3 -c "import json,sys; sys.path.insert(0, sys.argv[2]); import disk; print(disk.newest_kept(json.load(open(sys.argv[1]))))" \
    "$OUT/conv/$1.json" "$G" 2>/dev/null
}

boot() { # boot LABEL ARM XSERVE [XRUN0]: zig-tp3.sh in the background, /health polled for the first 200, the facts row
  local label=$1 arm=$2 xserve=$3 xrun0=${4:-} t0 th="" tu="" rc
  bash "$ZSTOP" > /dev/null 2>&1
  sleep "$BOOT_SETTLE"
  BOOT=$label
  say "boot $label ($arm): P=$P ctx=$CTX image=$IMAGE knobs=$KNOBS xenv='$XENV_KNOBS' xserve='$xserve' ($(left_s) s of the budget left)"
  t0=$(date +%s.%N)
  IMAGE="$IMAGE" KNOBS="$KNOBS" XENV="$XENV_KNOBS" XSERVE="$xserve" XRUN0="$xrun0" PORT="$ZPORT" bash "$ZTP3" "$P" "$CTX" \
    > "$OUT/boot-$label.log" 2>&1 &
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
  local args=(--arm "$arm" --ctx "$CTX" --boot-start "$t0" --boot-rc "$rc" --image "$IMAGE" "--xenv=$XENV_KNOBS" "--xserve=$xserve"
              --ssh "$SSH" --workers "${WORKERS// /,}")
  [ -n "$th" ] && args+=(--health-at "$th")
  [ "$rc" = 0 ] && args+=(--up-at "$tu")
  [ "$rc" = 0 ] || args+=("--error=$(tail -4 "$OUT/boot-$label.log" | tr '\n' ' ' | cut -c1-400)")
  dk facts "${args[@]}" > "$OUT/$label-facts.out" 2>&1
  say "boot $label: rc $rc; $(grep -o '"boot_s": [0-9.]*\|"store": {[^}]*}' "$OUT/$label-facts.out" | tr '\n' ' ')"
  return "$rc"
}

keep_logs() { # keep_logs LABEL: every rank's log of this boot (the containers go with --rm), then the disk lines counted
  $DOCKER logs glm53-zig-r0 2>&1 | tail -n 200000 > "$OUT/r0-$1.log"
  local i=1 w ws=()
  for w in $WORKERS; do
    $SSH -n -o BatchMode=yes "$w" "docker logs glm53-zig-r$i 2>&1 | tail -n 200000" > "$OUT/r$i-$1.log" 2>/dev/null
    ws+=(--worker "$OUT/r$i-$1.log")
    i=$((i + 1))
  done
  local bytes files
  bytes=$(learn_in du -sb "/learn/$(basename "$LEARN_HOST")" 2>/dev/null | awk '{print $1}')
  files=$(learn_in find "/learn/$(basename "$LEARN_HOST")" -type f 2>/dev/null | wc -l)
  dk logs --label "$1" --r0 "$OUT/r0-$1.log" "${ws[@]}" ${bytes:+--learn-bytes "$bytes"} --learn-files "${files:-0}" \
    --learn-dir "$LEARN_HOST" > "$OUT/$1-logs.out" 2>&1
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

stop_all() { # a clean stop: rank 0 first (it writes what waits while the other ranks still answer), then each worker
  local t0 i=1 w
  t0=$(date +%s.%N)
  $DOCKER stop -t "$STOP_GRACE" glm53-zig-r0 > /dev/null 2>&1
  say "rank 0 stopped in $(python3 -c "import sys; print(round($(date +%s.%N) - float(sys.argv[1]), 1))" "$t0") s"
  for w in $WORKERS; do
    $SSH -n -o BatchMode=yes "$w" "docker stop -t 60 glm53-zig-r$i" > /dev/null 2>&1
    i=$((i + 1))
  done
}

optional() { # optional NAME: true when its worst case (EST_NAME minutes) fits what is left of the budget
  local est_var="EST_$1"
  local est=${!est_var:-0}
  if [ "$(left_s)" -lt $((est * 60)) ]; then
    say "SKIP $1: $(left_s) s of the budget left, it takes up to $est min"
    return 1
  fi
}

K_OK=0  # 1 once k1 has booted with the disk tier: k2 and k3 resume what it kept
run_step() {
  case $1 in
    k1)
      boot k1 learn "$LEARN_FLAGS" || { say "k1 did not boot with the disk tier: nothing to resume, k2 and k3 skip"; keep_logs k1; return; }
      K_OK=1
      local m
      for m in $M_SIZES; do turn "M$m" cold cold; turn "M$m" ram ram; done
      turn L cold cold --load "$LOAD" --load-tokens "$LOAD_TOKENS" --load-max-tokens "$LOAD_MAX" --base-s "$BASE_S"
      turn L ram ram
      local at="" a
      for m in $M_SIZES; do a=$(grid_of "M$m"); [ -n "$a" ] && at="${at:+$at,}$a"; done
      [ -n "$at" ] && dk evict --at "$at" --size "$FILLER" --max "$FILLERS_MAX" > "$OUT/k1-evict.out" 2>&1
      say "k1 evict: $(tail -1 "$OUT/k1-evict.out" 2>/dev/null | grep -o '"fillers": [0-9]*\|"still_held": \[[^]]*\]' | tr '\n' ' ')"
      for m in $M_SIZES; do turn "M$m" disk evicted; done
      # production honours cache_salt (a salted request resumes only its own salt's states); '' is the control
      for s in other ""; do dk salt "M${M_SIZES%% *}" --conv-dir "$OUT/conv" --salt "$s" >> "$OUT/k1-salt.out" 2>&1; done
      dk drain --label "before the SIGKILL" > "$OUT/k1-drain.out" 2>&1
      keep_logs k1
      kill_all ;;
    k2)
      [ "$K_OK" = 1 ] || { say "SKIP k2: no store from k1"; return; }
      boot k2 learn "$LEARN_FLAGS" || { keep_logs k2; return; }
      turn L disk kill
      [ "$QUOTE" = 1 ] && turn L ram quote --quote
      for m in $M_SIZES; do turn "M$m" disk kill; done
      dk drain --label "before the clean stop" > "$OUT/k2-drain.out" 2>&1
      keep_logs k2
      # the clean stop's flush: a long first save still being written when SIGTERM comes must reach the disk
      $DOCKER logs -f --since 1s glm53-zig-r0 > "$OUT/r0-k2-stop.log" 2>&1 &
      local follower=$!
      [ "$FLUSH" = 1 ] && turn "S$FLUSH_SIZE" cold flush --no-drain
      stop_all
      wait "$follower" 2>/dev/null
      dk logs --label "k2 stop" --r0 "$OUT/r0-k2-stop.log" > "$OUT/k2-stop-logs.out" 2>&1 ;;
    k3)
      [ "$K_OK" = 1 ] || { say "SKIP k3: no store from k1"; return; }
      boot k3 learn "$LEARN_FLAGS" || { keep_logs k3; return; }
      turn L disk restart --load "$LOAD" --load-tokens "$LOAD_TOKENS" --load-max-tokens "$LOAD_MAX" --base-s "$BASE_S"
      [ "$FLUSH" = 1 ] && turn "S$FLUSH_SIZE" disk flushed
      for m in $M_SIZES; do turn "M$m" disk restart; done
      dk drain --label "the end" > "$OUT/k3-drain.out" 2>&1
      keep_logs k3 ;;
    ref)
      [ -s "$OUT/prompts/index.jsonl" ] || { say "SKIP ref: no prompts were recorded"; return; }
      boot ref ref "$REF_FLAGS" || return
      dk replay --arm ref --order "$REF_ORDER" --deadline $(( T0 + BUDGET_MIN * 60 )) --min-left "$REF_MIN_LEFT" \
        > "$OUT/ref-replay.out" 2>&1
      say "ref: $(grep -c '"case": "ref"' "$OUT/ref-replay.out") cold references"
      keep_logs ref ;;
    enospc)
      # a store on an inode-limited tmpfs in rank 0's container: E32's save fits, E120's runs out of inodes mid-write
      # (the admission counts bytes only, so this is a real ENOSPC); the server must keep serving and leave no .part
      boot enospc learn "--learn-conversations --learn-dir /learnfull --learn-gib 64 --learn-daily-gib 512 --learn-min-free-gib 0" \
        "--tmpfs /learnfull:rw,size=${ENOSPC_SIZE},nr_inodes=${ENOSPC_INODES},mode=0700" || { keep_logs enospc; return; }
      turn E32 cold cold
      turn E120 cold cold
      turn E32 ram ram
      local parts used
      parts=$($DOCKER exec glm53-zig-r0 sh -c 'find /learnfull -name "*.part" | wc -l' 2>/dev/null | tr -dc 0-9)
      used=$($DOCKER exec glm53-zig-r0 sh -c 'df -i /learnfull | tail -1' 2>/dev/null | tr -s ' ' | cut -d' ' -f2-5)
      keep_logs enospc
      dk logs --label "enospc probe" --extra "part_files=${parts:-?}" --extra "inodes=${used:-?}" > "$OUT/enospc-probe.out" 2>&1 ;;
  esac
}

say "window $TAG: steps '$STEPS', budget $BUDGET_MIN min, image $IMAGE, rows $ROWS, store $LEARN_HOST"
{ sha256sum "$G/zig-tp3.sh" "$G/serve.sh" "$G/longctx.py" "$G/disk.py" "$G/disk_table.py" "$0"
  $DOCKER image inspect --format '{{.Id}} {{.RepoTags}} {{index .Config.Labels "glm53-zig.src-sha256"}}' "$IMAGE"; } > "$OUT/provenance.txt" 2>&1
df -h /home "$(dirname "$LEARN_HOST")" > "$OUT/disk-start.txt" 2>&1
for step in $STEPS; do
  s0=$(date +%s)
  if optional "$step"; then
    run_step "$step"
    say "step $step done in $(( $(date +%s) - s0 )) s"
  fi
done
df -h /home "$(dirname "$LEARN_HOST")" > "$OUT/disk-end.txt" 2>&1
