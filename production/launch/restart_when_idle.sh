#!/bin/bash
# restart_when_idle.sh <label> [max_wait_s] [post-check command...]   on spark1, detached (setsid nohup ... &):
# restart the production GLM serve (spark-model glm stop + start, i.e. glm-stack.env's GLM_STOP / GLM_START) only
# once it has been idle for three /health samples in a row (busy false, requests_running 0, 5 s apart). Gives up -
# changing nothing - when no idle window comes within max_wait_s (default 1800). After health 200 it runs the
# post-check command. The watchdog is NOT touched: it is the system unit glm-watchdog-system.service (since
# 2026-10-24), which this script cannot stop without sudo and which may itself be the caller (its memory guard), and
# its crash path waits 20 minutes down (DOWN_LIMIT 40 x 30 s), far longer than a restart, so it never races one. Until
# 2026-11-01 this script stopped and started the retired USER unit glm-watchdog.service, which paused nothing and
# started a second supervisor beside the system unit after every restart (running from 2026-10-29 13:18 until
# 2026-11-01: two wedge recoveries racing, two hygiene passes); the user unit is masked now.
# Log: ~/prof/restart-<label>.log. An idle gate is a window, not a lock: a request arriving in the ~1 s between the
# last sample and the stop is cut off (its client sees a dropped connection and retries).
set -u
LABEL=${1:?label}; MAXWAIT=${2:-1800}; shift; [ $# -gt 0 ] && shift
. ~/.config/glm-stack.env
export PATH="$HOME/.local/bin:$PATH"       # spark-model; a setsid/nohup shell has no login PATH
LOG=~/prof/restart-$LABEL.log; mkdir -p ~/prof
H=http://127.0.0.1:${GLM_PORT}/health
exec >>"$LOG" 2>&1
say() { echo "$(date '+%F %T') $*"; }
# idle: no request running - or nothing listening on the port at all (curl 7): a down serve has nothing to cut off.
# (2026-10-08: a serve left down by a failed start made this wait out its whole max_wait and change nothing.)
idle() {
  local body rc
  body=$(curl -s -m 3 "$H"); rc=$?
  [ $rc -eq 7 ] && return 0
  [ $rc -eq 0 ] || return 1
  printf '%s' "$body" | python3 -c 'import json,sys
d = json.load(sys.stdin); sys.exit(0 if not d.get("busy") and not d.get("requests_running") else 1)' 2>/dev/null
}
say "restart $LABEL: waiting up to ${MAXWAIT}s for an idle serve"
end=$((SECONDS + MAXWAIT)); run=0
while [ $run -lt 3 ]; do
  [ $SECONDS -ge $end ] && { say "no idle window in ${MAXWAIT}s: nothing changed"; exit 1; }
  if idle; then run=$((run + 1)); else run=0; fi
  sleep 5
done
if ! idle; then say "a request arrived: nothing restarted"; exit 1; fi
say "idle: stopping"
if ! spark-model glm stop; then say "stop failed"; exit 3; fi
for _ in $(seq 60); do curl -s -m 2 -o /dev/null "$H" || break; sleep 2; done    # the old serve must be gone first
if curl -s -m 2 -o /dev/null "$H"; then say "serve still answers after stop"; exit 3; fi
say "starting ($GLM_START)"
if ! spark-model glm start; then say "start failed: the watchdog retries with the same launcher"; exit 2; fi
end=$((SECONDS + 900))
until curl -s -m 3 -o /dev/null -w '%{http_code}' "$H" | grep -q 200; do
  [ $SECONDS -ge $end ] && { say "no health 200 in 900 s: the watchdog retries with the same launcher"; exit 2; }
  sleep 5
done
say "health 200 after $((SECONDS - end + 900)) s"
say "watchdog: $(systemctl is-active glm-watchdog-system)"
if [ $# -gt 0 ]; then say "post-check: $*"; "$@"; say "post-check exit $?"; fi
say "done"
