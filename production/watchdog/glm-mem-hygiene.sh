#!/bin/bash
LOG="${GLM_HYGIENE_LOG:-/var/log/glm-mem-hygiene.log}"
before_free=$(awk '/MemFree/{print $2}' /proc/meminfo)
sync
echo 3 > /proc/sys/vm/drop_caches
echo 1 > /proc/sys/vm/compact_memory
after_free=$(awk '/MemFree/{print $2}' /proc/meminfo)
echo "$(date '+%F %T') memfree ${before_free}kB -> ${after_free}kB (drop_caches+compact)" >> "$LOG"
