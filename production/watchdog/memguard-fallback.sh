#!/bin/bash
# memguard-fallback.sh v2 (spark1, nohup): closes the memguard's "no idle window -> 45 min cooldown ->
# kernel OOM" gap.  It follows the guard's own restart to its END, not just for 10 minutes:
#
#   MEMGUARD line appears -> watch ~/prof/restart-<label>.log every 15 s until one of:
#     * "idle: stopping" or "health 200"  -> the guard did it; done.
#     * "no idle window" (the guard gave up) -> the guard's path is exhausted; act:
#         - if MemAvailable >= 5 GiB: log and leave it (the guard will retry after its cooldown);
#         - else one bounded `restart_when_idle.sh memguard-fallback-<ts> 900` (it may catch a brief idle);
#           if THAT also gives up and MemAvailable < 4 GiB -> last-resort stop+start, logging how many
#           requests were cut off (/health requests_running just before). A kernel OOM would cut them too,
#           and would also take the user session and leave the stack to the 20-minute watchdog path.
#   A hard cap (MEMGUARD_FALLBACK_MAX_S, default 2700) ends the watch after the guard times out.
#
# Testable: WD, PROF, DRY=1, FAKE_AVAIL (GiB) are overridable - DRY prints the actions it would take and
# runs none of them.  Test: see the self-test at the bottom (MEMGUARD_FALLBACK_SELFTEST=1).
set -u
WD=${WD:-$HOME/glm-watchdog.log}
PROF=${PROF:-$HOME/prof}
DRY=${DRY:-0}
LOG=$PROF/memguard-fallback.log
HEALTH=${HEALTH:-http://127.0.0.1:8888/health}
export PATH="$HOME/.local/bin:$PATH"
mkdir -p "$PROF"
say() { echo "$(date '+%F %T') $*" >> "$LOG"; }
avail_gib() {
  if [ -n "${FAKE_AVAIL:-}" ]; then printf '%s' "$FAKE_AVAIL"; return; fi
  awk '/^MemAvailable:/{printf "%.1f", $2/1048576}' /proc/meminfo
}
lt() { awk -v a="$1" -v b="$2" 'BEGIN{exit !(a < b)}'; }
running_now() {
  curl -s -m 3 "$HEALTH" 2>/dev/null | python3 -c 'import json,sys
try: d=json.load(sys.stdin); print(d.get("requests_running", 0))
except Exception: print(0)' 2>/dev/null || echo 0
}
do_restart() {   # do_restart <label> <maxwait>
  if [ "$DRY" = 1 ]; then say "DRY: would run restart_when_idle.sh $1 $2"; return 0; fi
  setsid nohup "$HOME/restart_when_idle.sh" "$1" "$2" </dev/null >>"$LOG" 2>&1 &
  say "launched restart_when_idle.sh $1 $2"
}
do_last_resort() {   # last resort: bounded stop+start, logged with the cut-off request count
  local cut; cut=$(running_now)
  if [ "$DRY" = 1 ]; then say "DRY: would last-resort stop+start (cutting $cut in-flight request(s))"; return 0; fi
  say "LAST RESORT: stop+start now, cutting $cut in-flight request(s)"
  spark-model glm stop >>"$LOG" 2>&1
  sleep 10
  spark-model glm start >>"$LOG" 2>&1
}

handle() {   # handle <label>; follows the guard's restart to its end
  local label=$1 rlog="$PROF/restart-$1.log" end avail bwait
  end=$((SECONDS + ${MEMGUARD_FALLBACK_MAX_S:-2700}))
  say "following $rlog (max ${MEMGUARD_FALLBACK_MAX_S:-2700}s)"
  while [ $SECONDS -lt $end ]; do
    if [ -f "$rlog" ] && grep -qE "idle: stopping|health 200" "$rlog"; then
      say "the guard's restart proceeded ($(grep -oE 'idle: stopping|health 200' "$rlog" | head -1)) - done"; return 0
    fi
    if [ -f "$rlog" ] && grep -q "no idle window" "$rlog"; then
      avail=$(avail_gib)
      say "the guard gave up ('no idle window'); avail ${avail} GiB"
      if lt "$avail" 5; then
        do_restart "memguard-fallback-$(date +%Y%m%d-%H%M%S)" 900
        local fb; fb=$(ls -t "$PROF"/restart-memguard-fallback-*.log 2>/dev/null | head -1)
        for _ in $(seq ${MEMGUARD_FB_STEPS:-60}); do
          sleep ${MEMGUARD_FB_PERIOD:-15}
          if [ -n "$fb" ] && grep -qE "idle: stopping|health 200" "$fb"; then
            say "fallback restart proceeded - done"; return 0
          fi
          if [ -n "$fb" ] && grep -q "no idle window" "$fb"; then
            avail=$(avail_gib)
            if lt "$avail" 4; then do_last_resort; else say "fallback gave up too but avail ${avail} GiB >= 4 - leaving it"; fi
            return 0
          fi
        done
        say "fallback restart: no verdict in 15 min; leaving it to the guard/watchdog"; return 0
      else
        say "guard gave up but avail ${avail} GiB >= 5 - leaving it (the guard retries after its cooldown)"; return 0
      fi
    fi
    sleep 15
  done
  say "watch cap reached without a verdict; leaving it to the guard/watchdog"
}

if [ "${MEMGUARD_FALLBACK_SELFTEST:-0}" = 1 ]; then
  # branch test with fake logs, no recursion: functions are called in THIS shell.
  T=$(mktemp -d)
  LOG="$T/memguard-fallback.log"; PROF="$T"; DRY=1
  MEMGUARD_FALLBACK_MAX_S=45; MEMGUARD_FB_STEPS=2; MEMGUARD_FB_PERIOD=1
  R="$T/restart-memguard-20261029-030000.log"
  printf 'waiting up to 1800s for an idle serve\n2026-10-29 03:30:00 no idle window in 1800s: nothing changed\n' > "$R"
  FAKE_AVAIL=4.2; say "SELFTEST 1 (expect: fallback restart, dry)"; handle memguard-20261029-030000
  printf 'idle: stopping\n2026-10-29 03:05:00 health 200 after 130 s\n' > "$R"
  FAKE_AVAIL=4.2; say "SELFTEST 2 (expect: done, no action)"; handle memguard-20261029-030000
  printf '2026-10-29 03:30:00 no idle window in 1800s: nothing changed\n' > "$R"
  FAKE_AVAIL=6.0; say "SELFTEST 3 (expect: armed but no action, avail >= 5)"; handle memguard-20261029-030000
  echo "--- selftest log:"; cut -c1-140 "$LOG"
  rm -rf "$T"; exit 0
fi
last=$(grep -c "MEMGUARD:" "$WD" 2>/dev/null || echo 0)
say "memguard-fallback v2 started; MEMGUARD lines so far: $last; avail $(avail_gib) GiB"
while true; do
  sleep 30
  now=$(grep -c "MEMGUARD:" "$WD" 2>/dev/null || echo 0)
  if [ "$now" -gt "$last" ]; then
    last=$now
    label=$(grep "MEMGUARD:" "$WD" | tail -1 | grep -oE 'memguard-[0-9-]+' | tail -1)
    say "trigger seen: ${label:-<no label>}; avail $(avail_gib) GiB"
    [ -n "${label:-}" ] && handle "$label"
    say "handled; avail $(avail_gib) GiB"
  fi
done
