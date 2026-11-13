#!/bin/bash
# glm-watchdog v15: the periodic memory hygiene pass (glm-mem-hygiene.sh: drop_caches + compact_memory on every node,
#   every 20 ticks, ~16-18 min) waits while a benchmark asks it to: when the file GLM_WD_HYGIENE_PAUSE (default
#   ~/.glm-hygiene-pause) exists and is younger than GLM_WD_HYGIENE_PAUSE_MAX_S (default 43200 s, so a run that dies
#   without removing it holds the pass back for at most 12 h), the tick skips the pass and logs it. The recovery
#   path's hygiene is unchanged. Measured by lane DrafterBuckets (2026-11-01): a pass landed in 41 of 212 per-patch
#   boots, and a boot it hit decoded the forks probe a median 0.61% slower (1.03% at P4, 31 of 40 hit boots slower
#   than the unhit boots of the same run and level), the size of the effects the A/Bs measure. The per-patch
#   harness (perpatch_run.sh) holds the file for its run.
# glm-watchdog v14: the pre-OOM memory guard. On a GB10 the GPU pool is unified memory: a long busy day of
#   prefills grows driver + host memory that does not come back (upstream #197/#143/#154), and at zero the
#   kernel OOM-kills the serve AND the user's systemd session (spark2, 2026-10-25 10:23, NV_ERR_NO_MEMORY from
#   the driver first). So every tick the head's MemAvailable is read, and every node (ssh) too; any node below
#   GLM_WD_MEMGIB (default 6 GiB) for GLM_WD_MEM_STREAK ticks (default 3 = 90 s; a prefill burst's dip is one
#   tick) triggers a PLANNED restart through restart_when_idle.sh (label memguard-<ts>): waits for idle, no
#   capture and no kill - a 2-minute restart instead of the wedge's 25-minute one. Cooldown
#   GLM_WD_MEM_COOLDOWN_S (default 2700 s) after a trigger. Skipped while metrics are down (the crash path owns
#   that). The wedge/unreachable logic is unchanged. One-shot read: glm-watchdog.sh --check-mem.
#   Same version, two crash-path hardenings (today the serve died ~14:27 and the watchdog hung silently in
#   recovery for three hours): a "serve unreachable: N/40" log line every 10 DOWN samples, and timeouts on the
#   capture's unbounded calls (df, du, dmesg, nvidia-smi, ip).
# glm-watchdog v13: adds the disk-pressure check to the v12 slow cycle (same tick as the link check).
#   / , /home and the NVMe KV tier are checked every GLM_WD_LINK_EVERY ticks; crossing GLM_WD_DISK_PCT
#   (default 85%) logs "DISK PRESSURE ..." once, and clearing logs "disk pressure cleared" once. Alert-only,
#   never feeds the wedge streak. Forwarded to the Telegram status topic by the CT106 glm_link_alert cron.
# glm-watchdog v12: adds the fabric link-speed check (alert-only). Every fabric NIC (names ending np0/np1) must be
#   UP at >= GLM_WD_LINK_MIN_MBPS (default 100000; production links read 200000). The owner-measured CX7 failure
#   mode - links silently dropping into a 13 Gb/s post-hotplug mode - shows here as a low sysfs speed, and it
#   measurably slows the serve (interconnect is load-bearing at production depths/chunk sizes). The check runs on
#   the head and every worker every GLM_WD_LINK_EVERY ticks (default 20 = ~10 min), logs CRITICAL on any bad link,
#   and NEVER feeds the wedge streak: a restart cannot fix a link. One-shot: glm-watchdog.sh --check-links.
# glm-watchdog v11: GLM_API=tensorfold judges a wedge by /health's iteration_s (how long rank 0's current round has
#   run; 0 between rounds; TensorFold v0.6.0 / recipe v1.4+), not by counters. Every prompt chunk and decode round is
#   one round of ~0.1-3 s, so a live server keeps resetting it; a stalled one grows it without bound. v10's counter rule
#   killed a healthy serve on 2026-10-03 15:05: four 500k-token agent prompts filling at once moved neither the token
#   counters (they advance when a prefill completes) nor pool_free_tokens (extents are reserved up front). A sample
#   is wedged when requests are in flight and iteration_s >= GLM_WD_ITER_S (60); 10 in a row (5 min) recover.
# glm-watchdog v10: GLM_API=tensorfold (glm-stack.env) supervises the TensorFold TP=3 stack from its JSON /health:
#   P = prompt_tokens_total, G = completion_tokens_total (counts live replies' tokens), R = requests_running, and
#   K = pool_free_tokens, the shared pool --parallel prompts fill in 2,048-token extents chunk by chunk - the
#   signal that moves DURING a long prefill, as kv_cache_usage_perc does for vLLM. Unset/vllm: v9 unchanged.
# v9: a live chunked prefill counts as progress. vLLM only bumps prompt_tokens_total
#   when a prefill COMPLETES, so a 650k-token prompt (~13 min at ~850 tok/s) froze both counters
#   and v8 killed it as a wedge after 5 min (2026-09-29 14:46 and 16:48). Blocks are allocated per
#   scheduled chunk, so kv_cache_usage_perc rises every sample while a prefill runs (measured:
#   +0.00226 per 15 s on a 113,781-token prompt); a sample is frozen only if P, G AND that gauge
#   are all unchanged.
# v8: stack-driven. Port, containers and the worker set come from
#   ~/.config/glm-stack.env (override GLM_STACK_ENV), so the same watchdog supervises the TP=2
#   or the TP=3 stack; capture and recovery cover EVERY worker, not one hardcoded host.
#   v7 disk guard: runs glm-disk-guard.sh --both before restarts when GLM_DISK_GUARD=1 (the stack
#   runs the NVMe KV tier the guard prunes - TP=3 since 2026-09-30; a full disk blinds this watchdog).
#   v6: wedge+CRASH detect + forensic capture before the restart destroys evidence (docker
#   inspect exit/OOMKilled every node + the previous boot's glm53_start.log); capture dirs are
#   labelled wedge-/crash-/manual-capture-<ts>.
#   v5 capture: process names DISCOVERED per node (workers run Worker_TP<N>); gdb native
#   all-thread bt (py-spy --native fails on this aarch64 kernel with UNW_EBADREG); nvidia-smi -q
#   Xid/ECC; live /metrics + last requests; MANIFEST with line counts so an empty artifact shows.
#   Test with: glm-watchdog.sh --capture-now  (read-only, no kill).
#   detection = (running+waiting > 0) AND (prompt+generation counters AND kv_cache_usage_perc
#   frozen) for 10x30s;
#   also (re)starts after 20 min of unreachable metrics.
STACK_ENV="${GLM_STACK_ENV:-$HOME/.config/glm-stack.env}"
# shellcheck disable=SC1090
. "$STACK_ENV" || { echo "$(date '+%F %T') watchdog: cannot read $STACK_ENV" >> "$HOME/glm-watchdog.log"; exit 1; }
API="${GLM_API:-vllm}"
if [ "$API" = tensorfold ]; then M="http://127.0.0.1:$GLM_PORT/health"; else M="http://127.0.0.1:$GLM_PORT/metrics"; fi
LOG="$HOME/glm-watchdog.log"
VERSION="v15"
ITER_S="${GLM_WD_ITER_S:-60}"
# v14: pre-OOM memory guard config (see header)
MEMGIB="${GLM_WD_MEMGIB:-6}"
MEM_STREAK="${GLM_WD_MEM_STREAK:-3}"
MEM_COOLDOWN_S="${GLM_WD_MEM_COOLDOWN_S:-2700}"
MEMSTREAK=0; MEM_COOLDOWN=0; MEM_SSH_LOGGED=0
MEM_SNIP='awk "/^MemAvailable:/{print \$2}" /proc/meminfo'   # kB
# v12/v13: link check + disk pressure config (alert-only - see header)
LINK_EVERY="${GLM_WD_LINK_EVERY:-20}"
LINK_MIN="${GLM_WD_LINK_MIN_MBPS:-100000}"
DISK_PCT="${GLM_WD_DISK_PCT:-85}"
DISK_LAST=0
LINK_SNIP='for i in $(ls /sys/class/net 2>/dev/null | grep -E "np0$|np1$"); do st=$(cat "/sys/class/net/$i/operstate" 2>/dev/null); sp=$(cat "/sys/class/net/$i/speed" 2>/dev/null); case "$sp" in ""|*[!0-9]*) sp=0;; esac; if [ "$st" != up ] || [ "$sp" -lt '"$LINK_MIN"' ]; then echo "CRIT $i=$sp state=$st"; else echo "OK $i=$sp"; fi; done'
LINK_COUNT=0; LINK_LAST_OK=""
PYSPY=/usr/local/bin/py-spy
DISK_GUARD="$HOME/.local/bin/glm-disk-guard.sh"
STREAK=0; LAST_P="-1"; LAST_G="-1"; LAST_K="-1"; DOWN=0; HYG=0
FROZEN_LIMIT=10
DOWN_LIMIT=40
log(){ echo "$(date '+%F %T') $*" >> "$LOG"; }
wssh(){ local w="$1"; shift; ssh -o ConnectTimeout=10 -o BatchMode=yes "$w" "$@"; }
guard(){ [ "${GLM_DISK_GUARD:-0}" = 1 ] && [ -x "$DISK_GUARD" ] && "$DISK_GUARD" --both >/dev/null 2>&1; }
# v15: the periodic hygiene pass, held back while a fresh pause file exists (see header)
HYG_PAUSE="${GLM_WD_HYGIENE_PAUSE:-$HOME/.glm-hygiene-pause}"
HYG_PAUSE_MAX_S="${GLM_WD_HYGIENE_PAUSE_MAX_S:-43200}"
hygiene_paused(){   # 0 (paused) while $HYG_PAUSE exists and is younger than HYG_PAUSE_MAX_S
  local m
  m=$(stat -c %Y "$HYG_PAUSE" 2>/dev/null) || return 1
  [ $(( $(date +%s) - m )) -lt "$HYG_PAUSE_MAX_S" ]
}
periodic_hygiene(){   # every 20 ticks: drop_caches + compact_memory on the head and every worker, unless paused
  if hygiene_paused; then
    log "memory hygiene skipped: $HYG_PAUSE is held (a benchmark run; ignored once older than ${HYG_PAUSE_MAX_S}s)"
    return 0
  fi
  sudo -n /usr/local/bin/glm-mem-hygiene.sh
  for w in $GLM_WORKERS; do wssh "$w" 'sudo -n /usr/local/bin/glm-mem-hygiene.sh' >/dev/null 2>&1; done
}
# every container of this stack on the local node (head)
stack_containers(){ docker ps -a --format '{{.Names}}' 2>/dev/null | grep "^$GLM_CONTAINER_PREFIX"; }

capture(){
  # $1 = reason label: wedge (frozen counters) | crash (serve down/unreachable) | manual (--capture-now)
  local ts dir reason w i c
  reason="${1:-capture}"
  ts=$(date +%Y%m%d-%H%M%S)
  dir="$HOME/${reason}-capture-$ts"
  mkdir -p "$dir"
  log "capture[$reason] ($VERSION, stack=$GLM_STACK): stacks + logs + container/gpu state -> $dir"

  # --- head: python stacks (nonblocking) + native via gdb + driver Xid/ECC ---
  {
    for p in $(pgrep -f "[V]LLM::" 2>/dev/null); do
      nm=$(tr "\0" " " < /proc/$p/cmdline 2>/dev/null | grep -oE "VLLM::[A-Za-z0-9_]+" | head -1)
      [ -z "$nm" ] && continue
      echo "===== head ${nm:-pid$p} pid $p : py-spy (all threads, nonblocking) ====="
      timeout 25 sudo -n "$PYSPY" dump --pid "$p" --nonblocking 2>&1 | head -140
      echo "===== head ${nm:-pid$p} pid $p : gdb native (all threads) ====="
      timeout 25 sudo -n gdb -p "$p" -batch -ex "set pagination off" -ex "set print frame-arguments none" -ex "thread apply all bt" 2>&1 | head -170
    done
    echo "===== head container state (exit/OOMKilled) ====="
    for c in $(stack_containers); do
      docker inspect "$c" --format "$c Status={{.State.Status}} OOMKilled={{.State.OOMKilled}} ExitCode={{.State.ExitCode}} Error={{.State.Error}} Started={{.State.StartedAt}} Finished={{.State.FinishedAt}} Restarts={{.RestartCount}}" 2>&1
    done
    echo "===== head nvidia-smi -q (Xid/ECC/throttle) ====="
    nvidia-smi -q 2>&1 | grep -iE "Xid|ECC|Retired|Throttl|Processes" -A3 | head -50
  } > "$dir/head-pyspy.txt" 2>&1

  # --- head: host state, container log, live metrics, last requests ---
  { echo "== df -h =="; timeout 10 df -h / /home 2>/dev/null; echo "== kv cache =="; timeout 10 du -sh "$HOME/.cache/vllm-glm53-flash/kv-nvme" 2>/dev/null; timeout 20 sudo -n dmesg | tail -60; echo "== nvidia-smi (summary) =="; timeout 20 nvidia-smi 2>&1 | head -25; echo "== links =="; timeout 10 ip -s link show | grep -A6 -iE "roce|enp" | head -30; } > "$dir/head-sys.log" 2>&1
  timeout 15 docker logs --tail 400 "$GLM_HEAD_CONTAINER" > "$dir/head-docker.log" 2>&1
  if [ "$API" = tensorfold ]; then
    timeout 8 curl -s "$M" > "$dir/head-metrics.txt" 2>/dev/null
  else
    timeout 8 curl -s "$M" 2>/dev/null | grep -aE "num_requests_(running|waiting)|gpu_cache_usage|kv_offload|prefix_cache|spec_decode" | head -30 > "$dir/head-metrics.txt" 2>/dev/null
  fi
  grep -aE "POST /v1|GET /v1|prompt throughput" "$dir/head-docker.log" 2>/dev/null | tail -30 > "$dir/last-requests.txt"

  # --- every worker: SAME, with process names discovered (Worker_TP<N> - not hardcoded) ---
  i=0
  for w in $GLM_WORKERS; do
    i=$((i+1))
    timeout 70 ssh -o ConnectTimeout=8 -o BatchMode=yes "$w" '
      for p in $(pgrep -f "[V]LLM::" 2>/dev/null); do
        nm=$(tr "\0" " " < /proc/$p/cmdline 2>/dev/null | grep -oE "VLLM::[A-Za-z0-9_]+" | head -1)
        [ -z "$nm" ] && continue
        echo "===== worker ${nm:-pid$p} pid $p : py-spy (all threads, nonblocking) ====="
        timeout 25 sudo -n /usr/local/bin/py-spy dump --pid "$p" --nonblocking 2>&1 | head -140
        echo "===== worker ${nm:-pid$p} pid $p : gdb native (all threads) ====="
        timeout 25 sudo -n gdb -p "$p" -batch -ex "set pagination off" -ex "thread apply all bt" 2>&1 | head -170
      done
      echo "===== worker container state (exit/OOMKilled) ====="
      for c in $(docker ps -a --format "{{.Names}}" | grep "^'"$GLM_CONTAINER_PREFIX"'"); do
        docker inspect "$c" --format "$c Status={{.State.Status}} OOMKilled={{.State.OOMKilled}} ExitCode={{.State.ExitCode}} Error={{.State.Error}} Started={{.State.StartedAt}} Finished={{.State.FinishedAt}} Restarts={{.RestartCount}}" 2>&1
      done
      echo "===== worker nvidia-smi -q (Xid/ECC/throttle) ====="
      nvidia-smi -q 2>&1 | grep -iE "Xid|ECC|Retired|Throttl|Processes" -A3 | head -50
      echo "===== worker dmesg tail ====="
      sudo -n dmesg | tail -40
    ' > "$dir/worker$i-pyspy.txt" 2>&1
    timeout 15 ssh -o ConnectTimeout=8 -o BatchMode=yes "$w" \
      'for c in $(docker ps -a --format "{{.Names}}" | grep "^'"$GLM_CONTAINER_PREFIX"'"); do echo "== $c =="; docker logs --tail 200 "$c"; done' \
      > "$dir/worker$i-docker.log" 2>&1
    echo "$w" > "$dir/worker$i-host.txt"
  done

  # --- previous boot's launcher log (spark-model truncates it on the next start) ---
  [ -f "$HOME/glm53_start.log" ] && cp "$HOME/glm53_start.log" "$dir/glm53_start.log.prev"

  # --- manifest: makes an empty/missing artifact obvious next time ---
  { echo "capture $ts reason=$reason stack=$GLM_STACK"; ls -l "$dir"; echo "== line counts =="; wc -l "$dir"/* 2>/dev/null; } > "$dir/MANIFEST.txt" 2>&1
  log "capture done: $(wc -l "$dir"/* 2>/dev/null | tail -1)"
}

recover(){
  # a restart on a full volume cannot succeed: free space before anything else
  guard
  capture wedge
  log "recovery: docker kill every $GLM_STACK container on the head and all workers"
  for c in $(stack_containers); do docker kill "$c" >/dev/null 2>&1; done
  for w in $GLM_WORKERS; do
    wssh "$w" 'for c in $(docker ps --format "{{.Names}}" | grep "^'"$GLM_CONTAINER_PREFIX"'"); do docker kill "$c"; done' >/dev/null 2>&1
  done
  sleep 5
  log "recovery: cycling swap on every node"
  sudo -n /usr/sbin/swapoff -a && sudo -n /usr/sbin/swapon -a
  for w in $GLM_WORKERS; do wssh "$w" 'sudo -n /usr/sbin/swapoff -a && sudo -n /usr/sbin/swapon -a' >/dev/null 2>&1; done
  sleep 5
  log "recovery: memory hygiene every node (drop_caches+compact)"
  sudo -n /usr/local/bin/glm-mem-hygiene.sh
  for w in $GLM_WORKERS; do wssh "$w" 'sudo -n /usr/local/bin/glm-mem-hygiene.sh' >/dev/null 2>&1; done
  log "recovery: starting glm (+boot-window hygiene loop)"
  nohup "$HOME/.local/bin/glm-boot-hygiene.sh" >>"$LOG" 2>&1 &
  SKIP_BUILD=1 "$HOME/.local/bin/spark-model" glm start >>"$LOG" 2>&1
}

if [ "${1:-}" = "--capture-now" ]; then
  log "manual capture requested (--capture-now)"
  capture manual
  log "manual capture done"
  exit 0
fi

# v12: fabric link-speed check. Prints one line per host ("head ok=4/4" or "head ok=3/4 CRIT enP2p1s0f0np0=13000 ...").
check_links(){
  local host out crit total ok all="" r
  crit=0
  for host in head $GLM_WORKERS; do
    if [ "$host" = head ]; then
      r=$(bash -c "$LINK_SNIP" 2>/dev/null)
    else
      r=$(wssh "$host" "$LINK_SNIP" 2>/dev/null) || r="CRIT ssh=unreachable"
    fi
    total=$(grep -c '^OK' <<<"$r" 2>/dev/null); total=${total:-0}
    ok=$total
    crit=$(grep '^CRIT' <<<"$r" 2>/dev/null); crit=${crit:-}
    if [ -n "$crit" ]; then
      all="$all ${host}: ok=${ok}/4 $(echo "$crit" | tr '\n' ' ')"
    else
      all="$all ${host}: ok=${ok}/4"
    fi
  done
  echo "links:${all}"
}
if [ "${1:-}" = "--check-links" ]; then
  echo "link check ($VERSION, min=${LINK_MIN} Mb/s):"
  check_links
  exit 0
fi

# v14: one line per node ("head 6.2" = GiB free-ish now; "head -" = read failed; ssh on a worker
# fails once and is logged once, then counts as unreadable and is reported "-").
check_mem(){
  local host r all=""
  r=$(bash -c "$MEM_SNIP" 2>/dev/null)
  [ -n "$r" ] && r=$(awk -v k="$r" 'BEGIN{printf "%.1f", k/1048576}')
  all="head: ${r:--}"
  for host in $GLM_WORKERS; do
    r=$(wssh "$host" "$MEM_SNIP" 2>/dev/null)
    if [ -z "$r" ]; then
      if [ "$MEM_SSH_LOGGED" = 0 ]; then log "memguard note: MemAvailable unreadable on $host (ssh)"; MEM_SSH_LOGGED=1; fi
      all="$all ${host##*@}: -"
    else
      all="$all ${host##*@}: $(awk -v k="$r" 'BEGIN{printf "%.1f", k/1048576}')"
    fi
  done
  echo "$all"
}
if [ "${1:-}" = "--check-mem" ]; then
  echo "mem check ($VERSION, trigger <${MEMGIB} GiB for ${MEM_STREAK} ticks, cooldown ${MEM_COOLDOWN_S}s):"
  check_mem
  exit 0
fi
log "watchdog $VERSION started (pid $$; stack=$GLM_STACK port=$GLM_PORT workers=[$GLM_WORKERS])"
while true; do
  code=$(curl -s -o /tmp/.glm_m -m 8 -w '%{http_code}' "$M" 2>/dev/null)
  if [ "$code" != "200" ]; then
    DOWN=$((DOWN+1)); STREAK=0
    if [ $((DOWN % 10)) = 0 ]; then log "serve unreachable: $DOWN/$DOWN_LIMIT samples"; fi   # v14: silence can't hide the crash path (the 14:49 hang left three silent hours)
    if [ "$DOWN" -ge "$DOWN_LIMIT" ]; then
      log "metrics unreachable for $DOWN samples -> capture + starting glm (+boot hygiene)"
      guard
      capture crash
      nohup "$HOME/.local/bin/glm-boot-hygiene.sh" >>"$LOG" 2>&1 &
      SKIP_BUILD=1 "$HOME/.local/bin/spark-model" glm start >>"$LOG" 2>&1
      DOWN=0
    fi
    sleep 30; continue
  fi
  DOWN=0
  if [ "$API" = tensorfold ]; then
    # one line "P G R K" from /health, "-" for a missing field (read would shift an empty one; K is absent when
    # the serve runs without a shared pool, --parallel 1)
    read -r P G R K I < <(python3 -c 'import json,sys
h=json.load(open(sys.argv[1]))
print(*(h.get(k, "-") for k in ("prompt_tokens_total", "completion_tokens_total", "requests_running",
                                 "pool_free_tokens", "iteration_s")))' /tmp/.glm_m 2>/dev/null)
    [ "$P" = - ] && P=""; [ "$G" = - ] && G=""; [ "$R" = - ] && R=0; [ "$K" = - ] && K=""; [ "$I" = - ] && I=""
    Wq=0
  else
    P=$(grep -a '^vllm:prompt_tokens_total{' /tmp/.glm_m | grep -oE '[0-9.e+]+$' | head -1)
    G=$(grep -a '^vllm:generation_tokens_total{' /tmp/.glm_m | grep -oE '[0-9.e+]+$' | head -1)
  fi
  if [ -z "$P" ] || [ -z "$G" ]; then
    # metrics present but the counters were not parsed (fresh boot / scrape shape).
    # Never treat a parse failure as a frozen counter: skip this tick.
    log "note: token counters unparsed this tick (P='${P:-}' G='${G:-}') - skipping freeze check"
    STREAK=0; LAST_P="-1"; LAST_G="-1"; LAST_K="-1"; sleep 30; continue
  fi
  if [ "$API" != tensorfold ]; then
    R=$(grep -a '^vllm:num_requests_running{' /tmp/.glm_m | grep -oE '[0-9.]+' | tail -1)
    Wq=$(grep -a '^vllm:num_requests_waiting{' /tmp/.glm_m | grep -oE '[0-9.]+' | tail -1)
    # KV-block usage: the only /metrics signal that advances DURING a chunked prefill.
    K=$(grep -a '^vllm:kv_cache_usage_perc{' /tmp/.glm_m | grep -oE '[0-9.e+-]+$' | head -1)
  fi
  P=${P:-0}; G=${G:-0}; R=${R%%.*}; R=${R:-0}; Wq=${Wq%%.*}; Wq=${Wq:-0}
  inflight=$((R+Wq))
  if [ "$API" = tensorfold ] && [ -n "${I:-}" ]; then
    # v11: wedged = requests in flight and the current round has run >= ITER_S seconds
    if [ "$inflight" -gt 0 ] && [ "${I%%.*}" -ge "$ITER_S" ]; then STREAK=$((STREAK+1)); else STREAK=0; fi
  elif [ "$inflight" -gt 0 ] && [ "$P" = "$LAST_P" ] && [ "$G" = "$LAST_G" ] \
     && [ "${K:-}" = "$LAST_K" ] && [ "$P" != "0" ] && [ "$P" != "0.0" ]; then
    STREAK=$((STREAK+1))
  else
    STREAK=0
  fi
  LAST_P=$P; LAST_G=$G; LAST_K=${K:-}
  HYG=$((HYG+1))
  if [ "$HYG" -ge 20 ]; then
    HYG=0
    guard
    periodic_hygiene
  fi
  # v12: fabric link-speed check (alert-only, never touches the wedge streak)
  LINK_COUNT=$((LINK_COUNT+1))
  if [ "$LINK_COUNT" -ge "$LINK_EVERY" ]; then
    LINK_COUNT=0
    l=$(check_links)
    if printf '%s' "$l" | grep -q CRIT; then
      log "CRITICAL $l (alert-only: a restart cannot fix a link)"
      LINK_LAST_OK=""
    elif [ "$LINK_LAST_OK" != 1 ]; then
      log "links ok:$l"
      LINK_LAST_OK=1
    fi
    # v13: disk pressure (/ , /home, NVMe KV tier) - transition-logged, forwarded by the CT106 cron
    d=""
    for m in /home /; do
      u=$(df -P "$m" 2>/dev/null | awk 'NR==2{gsub("%","");print $5}')
      [ "${u:-0}" -ge "$DISK_PCT" ] && d="$d ${m}=${u}%"
    done
    tu=$(df -P "$HOME/cache/kvtier" 2>/dev/null | awk 'NR==2{gsub("%","");print $5}')
    [ "${tu:-0}" -ge "$DISK_PCT" ] && d="$d tier=${tu}%"
    if [ -n "$d" ]; then
      log "DISK PRESSURE:$d"
      DISK_LAST=1
    elif [ "$DISK_LAST" = 1 ]; then
      log "disk pressure cleared"
      DISK_LAST=0
    fi
  fi
  # v14: pre-OOM memory guard (skipped while metrics are down: the crash path owns that)
  if [ "$DOWN" = 0 ]; then
    [ "$MEM_COOLDOWN" -gt 0 ] && MEM_COOLDOWN=$((MEM_COOLDOWN-30))
    mem_low=""
    for pair in $(check_mem); do
      v=${pair#*:}
      [ "$v" = "-" ] && continue
      v=${v%.*}
      [ "$v" -lt "$MEMGIB" ] 2>/dev/null && mem_low="$mem_low $pair"
    done
    if [ -n "$mem_low" ]; then
      MEMSTREAK=$((MEMSTREAK+1))
      if [ "$MEMSTREAK" -ge "$MEM_STREAK" ] && [ "$MEM_COOLDOWN" -le 0 ]; then
        ts=$(date +%Y%m%d-%H%M%S)
        log "MEMGUARD: MemAvailable below ${MEMGIB} GiB for ${MEMSTREAK} ticks:$mem_low -> planned idle restart (label memguard-$ts; at idle, no capture/kill)"
        nohup "$HOME/restart_when_idle.sh" "memguard-$ts" </dev/null >>"$LOG" 2>&1 &
        MEMSTREAK=0
        MEM_COOLDOWN=$MEM_COOLDOWN_S
      fi
    else
      MEMSTREAK=0
    fi
  fi
  if [ "$STREAK" -ge "$FROZEN_LIMIT" ]; then
    log "WEDGE: running=$R waiting=$Wq frozen ${STREAK} samples (P=$P G=$G K=${K:-} iteration_s=${I:-}) -> capture+recovery"
    recover
    STREAK=0; LAST_P="-1"; LAST_G="-1"; LAST_K="-1"; DOWN=0
  fi
  sleep 30
done
