#!/bin/bash
# glm-disk-guard: keep EVERY GLM node above MIN_FREE_GB by pruning the throwaway persistent-KV
# cache. On 2026-09-20 the volume hit 0 bytes on both nodes: the serve died AND the watchdog went
# blind for 12h because it could not append its own log - a full disk removes your observability
# along with your service. Nothing pruned it, because the boot prune is AGE-based (14d, now 3d)
# and ~200GB had accumulated in under a day.
#
# MIN_FREE_GB default 50, deliberately NOT 10: the serve's own KV capacity gate refuses to boot
# with less than GLM53_KVCACHE_CAPACITY_BYTES (40GiB) free, so a guard that settled at 10GB would
# trade a full disk for an unbootable one. 50GB = 10GB headroom above that gate.
#
# ALL-NODE pruning (enforced after the 2026-09-22 crash). The offload tier is per-rank: a block's KV
# exists as r<rank>/<hash>.bin on EVERY node (r0 head, r1/r2 the TP=3 workers), and the scheduler decides a
# cache HIT from ITS OWN rank-0 files alone (`NvmeDirectManager.lookup` stats only the scheduler's
# dir). Pruning one node while the other keeps a block therefore produces a HIT that cannot be
# served. Worse, the manager caches every positive exists() it has ever seen (`_exists`), which is
# exactly the state the spec's own comment assumes away ("Files are never evicted while the server
# runs; nothing to pin") - so a deleted file still looks like a HIT, the load job reads it, gets
# ENOENT, and `get_finished` RAISES for a failed load: the engine dies and every in-flight session
# with it (measured 2026-09-22 05:30 BST: the worker's own timer pruned r1 at 05:08 while the head
# kept r0, and the next request for that prefix killed the engine). Two consequences, enforced here:
#   1. NEVER prune a subset of the nodes while the engine runs. One cutoff, applied to every
#      node, chosen from the LOWEST free space across them - a node with space is pruned anyway,
#      so the ranks stay in step. Workers come from ~/.config/glm-stack.env (GLM_WORKERS).
#   2. While the engine is UP, clear its in-memory existence cache BEFORE deleting (our
#      [glm53-cache-reset] patch exposes POST /reset_prefix_cache?reset_external=true ->
#      connector.reset_cache() -> manager._exists.clear()), and again afterwards. If the reset
#      cannot be confirmed we DEFER the prune: a stale HIT is a fatal crash, and the floor sits
#      10GB above the boot gate, so waiting a 60s tick is cheap. Below EMERGENCY_GB we prune
#      regardless - a full disk is worse (it kills the serve AND the watchdog's logging), and the
#      overlay re-verifies existence on lookup, so a deleted file is a MISS not a crash.
#
# WHEN it runs (the space fills WHILE the model serves - the NVMe offload tier writes KV blocks
# for every session and has no internal eviction: 200GB accumulated in under a day):
#   PRIMARY: glm-disk-guard.timer (systemd --user, every 60s) on the HEAD only, in all-node mode. A
#            multi-node serve cannot run on one node, so the head can always guard every rank; the
#            workers carry no timer, so nodes can never prune independently.
#   BELT:    spark-model `glm start` (--both) and glm-watchdog's recover/DOWN paths, so no boot or
#            restart ever begins on a full volume.
# Deletion itself lives in glm-kv-prune.sh - one implementation, shipped to every node.
#
# Usage: glm-disk-guard.sh [--both|--local-only]   (default and --both are the all-node mode)
set -u
MIN_FREE_GB="${GLM_WD_MIN_FREE_GB:-50}"
# EMERGENCY must sit ABOVE the serve's 40 GiB boot gate, not below it: below the gate the box is
# already in the 2026-09-20 outage class (unbootable), so a threshold of 25 would only fire once the
# damage was done. 42 leaves the handshake an 8 GB band to keep retrying in, and the fallback prune
# is safe because the overlay re-validates existence on lookup (see patch_lookup_reverify.py).
EMERGENCY_GB="${GLM_WD_EMERGENCY_GB:-42}"
# Nodes and serve come from the stack definition (same file the watchdog and spark-model read), so
# the guard covers every rank of whichever stack is live: TP=3 = head + spark3 + spark2.
STACK_ENV="${GLM_STACK_ENV:-$HOME/.config/glm-stack.env}"
# shellcheck disable=SC1090
[ -f "$STACK_ENV" ] && . "$STACK_ENV"
WORKERS="${GLM_WORKERS:-}"
PRUNE="$HOME/.local/bin/glm-kv-prune.sh"
LOG="$HOME/glm-disk-guard.log"
SERVE="${GLM_SERVE_URL:-http://127.0.0.1:${GLM_PORT:-8888}}"
RESET_TRIES="${GLM_RESET_TRIES:-8}"
MODE_LOCAL_ONLY=0
[ "${1:-}" = "--local-only" ] && MODE_LOCAL_ONLY=1
# Self-role safety net. A multi-node run ON A WORKER could resolve a peer to ITSELF and prune a
# subset of the nodes - the exact asymmetry that killed the engine on 2026-09-22. So on a worker we
# drop to local mode, which (below) can only prune while the engine is DOWN.
case "$(hostname)" in
  spark2*|spark3*) MODE_LOCAL_ONLY=1 ;;
esac

log(){ echo "$(date '+%F %T') $*" >> "$LOG"; }
free_gb(){ df -Pk / | awk 'NR==2 {printf "%d", $4/1048576}'; }
# free space as seen by one worker (its cache is per-node too); $1 = user@host
free_gb_remote(){ ssh -o ConnectTimeout=10 -o BatchMode=yes "$1" \
  "df -Pk / | awk 'NR==2 {printf \"%d\", \$4/1048576}'" 2>/dev/null; }
prune_local(){  "$PRUNE" "$1" 2>/dev/null; }
prune_remote(){ ssh -o ConnectTimeout=15 -o BatchMode=yes "$1" "'$PRUNE' '$2'" 2>/dev/null; }

SERVE_UP_CACHE=""   # probed once per run: the engine's liveness cannot change mid-tick
serve_up(){
  [ -n "$SERVE_UP_CACHE" ] && { [ "$SERVE_UP_CACHE" = yes ]; return; }
  # Probe the head's address (correct from EITHER node - localhost:8889 does not exist on the
  # worker), then fall back to localhost. A false "engine down" would authorise a prune without the
  # cache-reset handshake, which is the fatal path, so both are tried before giving up.
  local u
  for u in "$SERVE" "http://localhost:${GLM_PORT:-8888}"; do
    if [ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' "$u/health" 2>/dev/null)" = 200 ]; then
      SERVE_UP_CACHE=yes; return 0
    fi
  done
  SERVE_UP_CACHE=no
  return 1
}
# Drop the engine's in-memory file-existence cache so a deletion reads as a MISS, not a stale HIT.
serve_reset_cache(){
  local try out="" u
  for try in $(seq 1 "$RESET_TRIES"); do
    for u in "$SERVE" "http://localhost:${GLM_PORT:-8888}"; do
      out=$(curl -s -m 10 -X POST "$u/reset_prefix_cache?reset_external=true" 2>/dev/null)
      case "$out" in
        *'"success":true'*) return 0 ;;
      esac
    done
    sleep 3
  done
  log "serve: external prefix-cache reset NOT confirmed after ${RESET_TRIES} tries (last='${out:-no response}')"
  return 1
}

free_of(){ if [ "$1" = local ]; then free_gb; else free_gb_remote "$1"; fi; }
min_free(){
  local m="" v n
  for n in $NODES; do
    v=$(free_of "$n")
    [ -z "$v" ] && continue
    { [ -z "$m" ] || [ "$v" -lt "$m" ]; } && m="$v"
  done
  printf '%s' "$m"
}

guard_pair(){
  local where stage mmin out mm
  for stage in "stage1 +360 (>6h old)" "stage2 +15 (>15min old)" "stage3 +0 (all)"; do
    set -- $stage
    mmin="$2"
    mm=$(min_free)
    [ -z "$mm" ] && { log "free space unknown on every node - skipping"; return 0; }
    [ "$mm" -ge "$MIN_FREE_GB" ] && { [ "$mmin" != "+360" ] && log "${mm}G free (min of ${NODES// /+}) after $mmin prune"; return 0; }
    if [ "$NODES" != "$ALL_NODES" ] && [ "$mm" -ge "$EMERGENCY_GB" ] && serve_up; then
      # Only one node reachable while serving: deleting here alone would strand the other rank's
      # half of every pruned block. Wait for the peer to come back (engine down => no in-memory
      # existence state to go stale, so a one-sided prune is safe and proceeds).
      log "${mm}G free (< ${MIN_FREE_GB}G) but only '${NODES}' of '${ALL_NODES}' is reachable and a peer may still hold its part - deferring $stage"
      return 0
    fi
    # While the engine is up a stale HIT after a delete is FATAL, so the engine must drop its
    # existence cache first. Deferred prunes are safe to retry: the floor is 10GB above the gate.
    local handshake=""
    if serve_up; then
      if [ "$mm" -ge "$EMERGENCY_GB" ]; then
        if serve_reset_cache; then
          handshake=" (engine cache cleared first)"
        else
          log "${mm}G free (< ${MIN_FREE_GB}G) but the engine would not clear its cache - deferring $stage"
          return 0
        fi
      else
        log "CRITICAL: ${mm}G free is below the ${EMERGENCY_GB}G emergency floor and the engine could not clear its cache - pruning anyway (a full disk is worse; lookup() re-validates)"
      fi
    fi
    log "${NODES// /+}: ${mm}G free (< ${MIN_FREE_GB}G) -> prune $stage on ALL nodes${handshake}"
    for where in $NODES; do
      if [ "$where" = local ]; then out=$(prune_local "$mmin"); else out=$(prune_remote "$where" "$mmin"); fi
      log "$where: prune $mmin -> ${out:-FAILED}"
    done
    if serve_up && serve_reset_cache; then log "serve: external prefix-cache reset after prune OK"; fi
  done
  mm=$(min_free)
  log "guard finished with ${mm:-?}G free (min of ${NODES// /+})"
  [ -n "$mm" ] && [ "$mm" -lt "$MIN_FREE_GB" ] && \
    log "STILL BELOW ${MIN_FREE_GB}G after clearing the KV cache - free space elsewhere (docker images, other caches)"
  return 0
}

# Node coverage: this node always; each worker in GLM_WORKERS joins when it answers. ALL_NODES is the
# full set; if any worker does not answer, guard_pair either defers (engine up - pruning a subset is
# the crash) or proceeds (engine down - no in-memory existence state to go stale).
NODES="local"
ALL_NODES="local"
for w in $WORKERS; do ALL_NODES="$ALL_NODES $w"; done
if [ "$MODE_LOCAL_ONLY" = 1 ]; then
  # Local-only never covers every rank: on a worker there is no stack file (WORKERS is empty) and on
  # the head --local-only skips the peers, so while the engine is up this must always DEFER.
  ALL_NODES="$ALL_NODES +peers"
else
  for w in $WORKERS; do
    [ -n "$(free_gb_remote "$w")" ] && NODES="$NODES $w"
  done
fi
guard_pair
exit 0
