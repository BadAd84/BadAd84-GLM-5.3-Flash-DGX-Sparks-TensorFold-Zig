#!/bin/bash
# glm-kv-prune <mmin>: on THIS node, delete persistent-KV-cache *.bin files older than <mmin>
# minutes and report what is left. The one place that knows how to delete the throwaway cache
# (files are root-owned, so a container does the work; --network none because docker's own
# netns setup fails on a full volume - measured 2026-09-20 on spark2).
#
#   $1  find -mmin expression, e.g. +360 (6h), +15, +0 (everything). Required.
#   env GLM53_KVCACHE_DIR (default ~/.cache/vllm-glm53-flash/kv-nvme)
#       IMAGE override optional; otherwise read from ~/glm53-current/.env
# Prints: "<deleted_ok> <files_left> <free_gb>"
#
# DO NOT RUN THIS BY HAND AGAINST A LIVE SERVE. The engine caches positive file-existence results,
# so deleting a block's files underneath a running engine still reads as a HIT and the load job's
# failure RAISES, killing EngineCore (measured 2026-09-22). glm-disk-guard.sh is the only safe
# caller: it pairs the prune across BOTH ranks and clears the engine's cache around it. Use this
# directly only while the engine is stopped (the boot belt) or on a node whose rank is not serving.
set -u
MMIN="${1:?usage: glm-kv-prune <mmin-expr, e.g. +360>}"
CACHE_DIR="${GLM53_KVCACHE_DIR:-$HOME/.cache/vllm-glm53-flash/kv-nvme}"
IMG=$(grep -m1 '^IMAGE=' "$HOME/glm53-current/.env" 2>/dev/null | cut -d= -f2)
[ -z "${IMG:-}" ] && IMG=glm53-flash-sm121:local

left=$(docker run --rm --network none -v "$CACHE_DIR":/kv --entrypoint sh "$IMG" \
  -c "find /kv -name '*.bin' -mmin $MMIN -delete 2>/dev/null; find /kv -type f -name '*.bin' 2>/dev/null | wc -l" \
  2>/dev/null | tail -1)
free=$(df -Pk / | awk 'NR==2 {printf "%d", $4/1048576}')
echo "ok ${left:-?} ${free:-?}"
