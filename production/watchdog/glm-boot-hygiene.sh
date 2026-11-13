#!/bin/bash
# glm-boot-hygiene: during the boot window the page cache refills fast and MemFree
# collapses to ~1GB, which starves the NVRM driver allocator (_memdescAllocInternal
# OOM -> engine wedge). Run drop_caches + compact every 20s on the head AND every worker
# until the serve reports healthy, so the driver always has honest free memory while
# loading/capturing. Started by glm-watchdog before each `spark-model glm start`; exits on
# its own. Port and workers come from ~/.config/glm-stack.env.
STACK_ENV="${GLM_STACK_ENV:-$HOME/.config/glm-stack.env}"
# shellcheck disable=SC1090
. "$STACK_ENV" || { echo "$(date '+%F %T') boot-hygiene: cannot read $STACK_ENV"; exit 1; }
for i in $(seq 1 90); do   # up to ~30 min
  if curl -sf -o /dev/null -m 5 "http://127.0.0.1:$GLM_PORT/health" 2>/dev/null; then
    echo "$(date '+%F %T') boot-hygiene: serve healthy after $i passes, stopping"
    exit 0
  fi
  sudo -n /usr/local/bin/glm-mem-hygiene.sh
  for w in $GLM_WORKERS; do
    ssh -o ConnectTimeout=6 -o BatchMode=yes "$w" 'sudo -n /usr/local/bin/glm-mem-hygiene.sh' >/dev/null 2>&1
  done
  sleep 20
done
echo "$(date '+%F %T') boot-hygiene: 30min elapsed without health, stopping"
