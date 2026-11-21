#!/bin/bash
# bootfix-probe.sh - why does a boot on a newer base refuse on this hardware? One recorded ladder: snapshot the three boxes, boot, and if rank 0 refuses with
# "the checkpoint's W GiB of weights do not fit the B GiB the CUDA memory budget grants (F GiB free less a R GiB reserve)", record F and R, then try the next rung:
# wait 60 s, wait 180 s, drop the page cache, then drop it and compact. The rung that boots wins, and every attempt keeps an idle snapshot of all three boxes, so
# the drain curve is in the files rather than in a guess. It starts and stops the Zig serve and nothing else.
#
# Env: IMG (required, e.g. glm53-zig:m140a), KNOBS (default off), WORKERS ("adam@spark2... adam@spark3..."), OUT (default $HOME/bench/bootfix),
#      XENV (extra -e settings), HOURS (default 2), BOOTFIX_DRYRUN=1 to print the plan and touch nothing.
# Writes: $OUT/attempts.tsv (one row an attempt) and $OUT/<n>-<level>.txt (the three boxes' raw numbers).
set -u
IMG=${IMG:?set IMG to the image under test}
KNOBS=${KNOBS:-off}
WORKERS=${WORKERS:?set WORKERS to the two worker hosts}
OUT=${OUT:-$HOME/bench/bootfix}
XENV=${XENV:-}
HOURS=${HOURS:-2}
DRY=${BOOTFIX_DRYRUN:-0}
W1=${WORKERS%% *}; W2=${WORKERS##* }
mkdir -p "$OUT"
TSV="$OUT/attempts.tsv"
[ -s "$TSV" ] || printf 'attempt\tlevel\tboot_rc\tfree_gib\treserve_gib\tavail_gib\tparked_gib\tverdict\n' > "$TSV"
say() { echo "[bootfix] $(date -u +%T) $*"; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
nap() { [ "$DRY" = 1 ] || sleep "$1"; }

# raw numbers from one box: "<host> <MemAvailable kB> <Cached kB> <MemFree kB> <parked pages> <page bytes>". Quoted so nothing expands locally.
RAWCMD='echo "$(hostname) $(awk "/^MemAvailable:/{print \$2}" /proc/meminfo) $(awk "/^Cached:/{print \$2}" /proc/meminfo) $(awk "/^MemFree:/{print \$2}" /proc/meminfo) $(awk "/^ *count:/{s+=\$2} END{print s+0}" /proc/zoneinfo) $(getconf PAGESIZE)"'
boxraw() { if [ "$1" = - ]; then bash -c "$RAWCMD"; else ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$1" "$RAWCMD" 2>/dev/null || echo "unreachable - 0 0 0 0"; fi; }

snap() { # snap N LEVEL: keep the three boxes' raw lines and print one summary line "<avail> <parked>" in GiB for spark1
  local f="$OUT/$1-$2.txt" line avail=0 parked=0
  { echo "== $(date -u +%FT%TZ) attempt $1 level $2 image $IMG"; boxraw -; boxraw "$W1"; boxraw "$W2"; } > "$f" 2>&1
  while read -r host a c fr p ps; do
    [ "$host" = "==" ] && continue
    awk_line=$(awk -v a="${a:-0}" -v c="${c:-0}" -v f="${fr:-0}" -v p="${p:-0}" -v ps="${ps:-1}" -v h="$host" \
      'BEGIN{printf "   %-8s avail=%.2f cached=%.2f free=%.2f parked=%.2f GiB\n", h, a/1048576, c/1048576, f/1048576, p*ps/1073741824}')
    echo "$awk_line" >> "$f"
    say "${awk_line#   }"
    if [ "$host" = "spark1" ] || [ "$avail" = 0 ]; then avail=$(awk -v a="${a:-0}" 'BEGIN{printf "%.2f", a/1048576}'); parked=$(awk -v p="${p:-0}" -v ps="${ps:-1}" 'BEGIN{printf "%.2f", p*ps/1073741824}'); fi
  done < "$f"
  echo "$avail $parked"
}

free_of() { # free_of LOG: "free<TAB>reserve" from the refusal, empty when there is none
  grep -a -o -E "\([0-9.]+ GiB free less a [0-9.]+ GiB reserve\)" "$1" 2>/dev/null | tail -1 | sed -E 's/\(([0-9.]+) GiB free less a ([0-9.]+) GiB reserve\)/\1\t\2/'
}
refused() { grep -a -q "the CUDA memory budget grants" "$1" 2>/dev/null; }

privileged() { # privileged WHAT: run one privileged shell line in a throwaway container from the same image, on all three boxes
  local what=$1 h
  local cmd="docker run --rm --privileged --entrypoint sh $IMG -c '$what'"
  if [ "$DRY" = 1 ]; then say "DRYRUN would run on all three boxes: $cmd"; return 0; fi
  for h in - "$W1" "$W2"; do
    if [ "$h" = - ]; then eval "$cmd" > /dev/null 2>&1 || say "failed on spark1: $what"
    else ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "$cmd" > /dev/null 2>&1 || say "failed on $h: $what"; fi
  done
  say "done on all three boxes: $what"
}
cachedrop() { privileged 'sync; echo 3 > /proc/sys/vm/drop_caches'; }
compact() { privileged 'sync; echo 3 > /proc/sys/vm/drop_caches; echo 1 > /proc/sys/vm/compact_memory'; }

attempt() { # attempt N LEVEL: snapshot, boot, read the refusal, one row
  local n=$1 lvl=$2 log="$OUT/boot-$1-$2.log" mm avail parked row verdict rc
  mm=$(snap "$n" "$lvl"); avail=${mm%% *}; parked=${mm##* }
  [ "$DRY" = 1 ] || { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; }
  if [ "$DRY" = 1 ]; then say "DRYRUN would boot IMAGE=$IMG KNOBS=$KNOBS XENV=$XENV bash zig-tp3.sh 4 1048576"; return 1; fi
  timeout 900 env IMAGE=$IMG KNOBS=$KNOBS XENV="$XENV" bash zig-tp3.sh 4 1048576 > "$log" 2>&1; rc=$?
  if [ "$rc" = 0 ]; then
    local code; code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8300/health 2>/dev/null || echo 000)
    row="- -"; verdict="BOOTED health=$code"; say "level $lvl BOOTED (health $code)"
  elif refused "$log"; then
    row=$(free_of "$log"); [ -n "$row" ] || row="- -"; verdict="REFUSED"
    say "level $lvl refused: free ${row%%	*} GiB, reserve ${row##*	} GiB"
  else
    row="- -"; verdict="OTHER: $(tail -2 "$log" | tr '\n' ' ' | cut -c1-140)"
    say "level $lvl failed for another reason: $verdict"
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$n" "$lvl" "$rc" "${row%%	*}" "${row##*	}" "$avail" "$parked" "$verdict" >> "$TSV"
  case "$verdict" in BOOTED*) return 0;; esac
  return 1
}

[ "$DRY" = 1 ] || bash prod-stop.sh || { say "PRODUCTION DID NOT STOP"; exit 1; }
say "start: image $IMG knobs $KNOBS; rungs snap, wait60, wait180, drop, compact; rows in $TSV"
attempt 1 snap && { say "no fix needed: the image boots as it is"; exit 0; }
nap 60;  attempt 2 wait60  && exit 0
nap 180; attempt 3 wait180 && exit 0
cachedrop; attempt 4 drop && exit 0
compact; attempt 5 compact && exit 0
say "no rung booted; the ladder's rows are in $TSV, and the next question is what the numbers show, not another rung"
[ "$DRY" = 1 ] || stop
