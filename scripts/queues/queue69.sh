#!/bin/bash
# queue69.sh - on spark1, detached, after queue68. Image glm53-zig:v129v, the recipe (KNOBS=measured). Three switches the recipe does not set yet:
#  A  --parallel 4 --context 1048576, boots rec solo pipe pipe solo rec (each arm's mean centred on the same point):
#     solo = TF_GLM_CHUNK_SOLO=4096 (two grid chunks a prompt pass while no stream decodes: upstream's form of production's 4,096-row pass);
#     pipe = TF_GLM_OVN_ONEPASS_PIPE=1 (the DSA block's prompt rows on the one-pass pipeline; cold first token -4.6 / -5.6% at 8k / 32k on v1.2.7,
#     section 31, never given its decode cells). Each boot: longctx.py facts (pool and memory at boot), cold 8k / 32k / 120k twice, then the
#     prose and code ids at 1 2 4 clients (3 waves): ~/bench/pf69/rows.jsonl and ~/bench/a69-<arm><n>/{P,C}<n>.jsonl
#  B  pipe at 6 and 8 streams, fresh --parallel 6 and 8 boots, rec pipe pipe rec: ~/bench/b69-*
#  C  TF_GLM_OVN_HOST_ONCE=1 (the rewind probe's render stops early) on an agent's warm turn, both arms with TF_GLM_REQUEST_STARTS=1, boots
#     rec host host rec: longctx.py probe, a ~250k conversation +600 tokens, idle and beside three decoding streams: ~/bench/wt69-<arm><n>/rows.jsonl
# Production stopped on every rank (prod-stop.sh), KEEP=1 on every boot, production restored at the end. QUEUE69-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
WORKERS=${WORKERS:?set WORKERS to the ssh targets of ranks 1 and 2, space separated}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=glm53-zig:v129v
OUT=$HOME/bench/pf69; mkdir -p "$OUT"
LOGCMD='docker logs --since {since} glm53-zig-r0'
until grep -q QUEUE68-DONE queue68.log 2>/dev/null; do sleep 30; done
bash prod-stop.sh || { echo "[q69] PRODUCTION DID NOT STOP"; setsid nohup bash ~/glm-v110-start.sh > "$HOME/bench/prod-restore-q69.log" 2>&1 < /dev/null & echo "QUEUE69-DONE $(date -u +%T)"; exit 1; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
measure() { # measure DIR LEVELS...: prose and code ids, 3 waves each
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q69] $(date -u +%T) $tag $N streams prose rc=$r1 $(tail -1 "$dir/P$N.out" | grep -o '"agg_tok_s": [0-9.]*') code rc=$r2 $(tail -1 "$dir/C$N.out" | grep -o '"agg_tok_s": [0-9.]*')"
  done
}
armA() { # armA LABEL XENV
  local label=$1 xenv=$2 t0 tu rc
  stop; t0=$(date +%s.%N)
  IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/boot-$label.log" 2>&1; rc=$?; tu=$(date +%s.%N)
  local args=(--tag "$label" --n 4 --ctx 1048576 --boot-start "$t0" --boot-rc "$rc" --image "$IMG" "--xenv=$xenv")
  if [ "$rc" = 0 ]; then args+=(--up-at "$tu"); else args+=("--error=$(tail -4 "$OUT/boot-$label.log" | tr '\n' ' ' | cut -c1-400)"); fi
  python3 longctx.py facts 8300 "${args[@]}" --out "$OUT/rows.jsonl" --log-cmd "$LOGCMD" > "$OUT/$label-facts.out" 2>&1
  [ "$rc" = 0 ] || { echo "[q69] BOOT FAILED $label: $(tail -3 "$OUT/boot-$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1; }
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/rows.jsonl" --log-cmd "$LOGCMD" --seed "pf69-$label" --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/$label-probe.out" 2>&1
  echo "[q69] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  measure "$HOME/bench/a69-$label" 1 2 4
  docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 600 > "$OUT/r0-$label.log"
}
SOLO="-e TF_GLM_CHUNK_SOLO=4096"
PIPE="-e TF_GLM_OVN_ONEPASS_PIPE=1"
armA rec1 ""; armA solo1 "$SOLO"; armA pipe1 "$PIPE"; armA pipe2 "$PIPE"; armA solo2 "$SOLO"; armA rec2 ""
for a in r1:"" p1:"$PIPE" p2:"$PIPE" r2:""; do
  tag="b69-${a%%:*}"; xenv="${a#*:}"
  for N in 6 8; do
    stop
    if IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh "$N" > "$HOME/bench/$tag-boot-P$N.log" 2>&1; then measure "$HOME/bench/$tag" "$N"
    else echo "[q69] BOOT FAILED $tag P=$N: $(tail -3 "$HOME/bench/$tag-boot-P$N.log" | tr '\n' ' ' | cut -c1-300)"; fi
  done
done
RS="-e TF_GLM_REQUEST_STARTS=1"
for a in r1:"$RS" h1:"$RS -e TF_GLM_OVN_HOST_ONCE=1" h2:"$RS -e TF_GLM_OVN_HOST_ONCE=1" r2:"$RS"; do
  tag="wt69-${a%%:*}"; xenv="${a#*:}"; mkdir -p "$HOME/bench/$tag"
  stop
  if IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$HOME/bench/$tag/boot.log" 2>&1; then
    python3 longctx.py probe 8300 --tag "$tag" --n 4 --out "$HOME/bench/$tag/rows.jsonl" --log-cmd "$LOGCMD" --seed wt250 --cold-sizes '' --warm-base 250000 --warm-add 600 --reps 3 --load 0 > "$HOME/bench/$tag/idle.out" 2>&1
    python3 longctx.py probe 8300 --tag "$tag-L" --n 4 --out "$HOME/bench/$tag/rows.jsonl" --log-cmd "$LOGCMD" --seed wt250 --cold-sizes '' --warm-base 250000 --warm-add 600 --reps 3 --load 3 > "$HOME/bench/$tag/load.out" 2>&1
    echo "[q69] $(date -u +%T) $tag warm turns rc=$? $(grep -o '"case": "warm".*"ttft_ms": [0-9]*' "$HOME/bench/$tag/rows.jsonl" | grep -o '"ttft_ms": [0-9]*' | cut -d' ' -f2 | tr '\n' ' ')"
  else echo "[q69] BOOT FAILED $tag: $(tail -3 "$HOME/bench/$tag/boot.log" | tr '\n' ' ' | cut -c1-300)"; fi
done
stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1
curl -sf localhost:8888/health > /dev/null 2>&1 || {
  setsid nohup bash ~/glm-v110-start.sh > "$HOME/bench/prod-restore-q69.log" 2>&1 < /dev/null &
  for i in $(seq 1 90); do curl -sf localhost:8888/health > /dev/null 2>&1 && break; sleep 10; done; }
curl -sf localhost:8888/health > /dev/null 2>&1 && echo "[q69] production healthy" || echo "[q69] PRODUCTION NOT HEALTHY"
echo "QUEUE69-DONE $(date -u +%T)"
