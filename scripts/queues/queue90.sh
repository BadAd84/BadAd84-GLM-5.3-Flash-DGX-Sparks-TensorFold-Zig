#!/bin/bash
# queue90.sh - on spark1, detached, after queue89 and before queue77: patches/restore-held's TF_GLM_OVN_RESTORE_HELD. A warm turn restores its kept prompt state into a sequence and a pass later keeps it again, a copy
# of the whole state each way (queue85's capture of a ~113k conversation: 850 MiB in 10.8 ms and 858 MiB in 10.3 ms on rank 0, 2.5% of an 822 to 838 ms first token). A restore into the sequence that kept the state, or
# last restored it, and has only added rows since, leaves the latent rows, their scales and the whole pools below the state's position where they are and copies what a sequence rewrites. Expected: the restore's copy
# falls to about a tenth of its bytes, about 1.2% of a warm turn at ~113k and about 2% at ~250k, with every reply equal. It builds glm53-zig:v129zg from stage/src-v129zg.tar (the 48-patch stack: patch 0039, solo-cuts 0001
# and 0002, disk-any-position and this package) and copies it to the other two ranks, runs tf-cuda-test glm-restore-held-check on one GPU on glm-synth's 2-layer checkpoint with the switch off and on (the sequence that
# kept a state resumes it, another sequence resumes it whole, a third runs the request cold: every planned byte and twelve greedy steps equal, with a planted control each; both must pass or no boot is measured), then
# eight boots, h0a h1a h1b h0b h0c h1c h1d h0d (h0: the recipe with request starts; h1: the same with TF_GLM_OVN_RESTORE_HELD=1), each with the cold first token at 8k / 32k / 120k (two requests), the ~113k
# conversation (salt c74, 8 turns), the ~250k one (salt c250, 6 turns) and greedy decode at 1 client. Replies must be one digest across the eight boots. decide84.py's held block reads them (rule 7, written before
# these rows): the c74 turns 2 to 8 at least 0.8% faster than the controls' mean, the cold mean not over by more than 0.3%, equal replies, no boot over the slower control by 1.0%, decode not more than 1.0% under.
# A last boot with the switch on runs nsys-prefill.sh's capture (the cold 8k and 32k prompts and three warm turns), where prefill_passes.py copies lists the restore's bytes and time beside queue85's 850 MiB in 10.8 ms.
# queue90.env: IMG, WORKERS, HOURS, NEWX. Production is down for the campaign and stays down. QUEUE90-DONE.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue90.env
IMG=glm53-zig:v129zg
HOURS=4 # the image, the check, eight boots of about nine minutes and a capture
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=${IMG:?set IMG}
NEWX=${NEWX:-}
RSX="-e TF_GLM_REQUEST_STARTS=1"
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE90-DONE $(date -u +%T)"; }
DEADLINE=$(( $(date +%s) + ${HOURS:-5} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
trap finish EXIT
echo "[q90] $(date -u +%T) start; IMG=$IMG; NEWX='$NEWX'; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
# the image: built on this box (no serve is up, nothing else uses the GPUs or the memory bandwidth), then copied to the workers
TAG=${IMG#glm53-zig:}
if ! docker images --format '{{.ID}}' "$IMG" | grep -q .; then
  bash build-image.sh "$TAG" "stage/src-$TAG.tar" > "stage/build-$TAG.out" 2>&1 || { echo "[q90] BUILD FAILED: $(tail -3 "stage/build-$TAG.out" | tr '\n' ' ' | cut -c1-300)"; exit 1; }
  echo "[q90] $(date -u +%T) built $IMG: $(docker images --format '{{.ID}}' "$IMG" | head -1)"
  bash dist-image.sh "$TAG" > "stage/dist-$TAG.out" 2>&1
  echo "[q90] $(date -u +%T) distributed: $(tail -1 "stage/dist-$TAG.out" | cut -c1-200)"
fi
ids=$( { docker images --no-trunc --format '{{.ID}}' "$IMG" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $IMG | head -1"; done; } )
echo "[q90] $IMG ids: $(echo $ids)"
{ [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; } || { echo "[q90] IMAGE $IMG IS NOT THE SAME ON ALL THREE RANKS"; exit 1; }
echo "[q90] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12) $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W1" "sha256sum $G/serve.sh | cut -c1-12") $(ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$W2" "sha256sum $G/serve.sh | cut -c1-12")"
bash prod-stop.sh || { echo "[q90] PRODUCTION DID NOT STOP"; exit 1; }
stop
DEFS=$(awk '/^DEFS="/{f=1} f{print} f&&/"$/{exit}' serve.sh | tr '\n' ' ' | sed 's/^DEFS="//; s/" *$//')
[ "$(echo $DEFS | wc -w)" -ge 20 ] || { echo "[q90] serve.sh's DEFS did not parse: '$DEFS'"; exit 1; }
RECIPE="$(for kv in $DEFS; do printf -- '-e %s ' "$kv"; done)$NEWX"
TEST=/opt/tensorfold/bin/tf-cuda-test
passed() { # passed LOG TEXT: the log's one PASS line holds TEXT and no line says FAIL
  [ "$(grep -c '^PASS' "$1")" = 1 ] && [ "$(grep -c 'FAIL' "$1")" = 0 ] && grep -q "^PASS.*$2" "$1"
}
SYN="$OUT/f90-check/synth"; mkdir -p "$SYN"
docker run --rm --gpus all -v "$SYN:/s" --entrypoint $TEST "$IMG" glm-synth /s/ckpt > "$SYN/synth.log" 2>&1; echo "[q90] $(date -u +%T) glm-synth rc=$?: $(grep -a '^PASS' "$SYN/synth.log" | head -1 | cut -c1-160)"
held() { # held NAME TEXT XENV: glm-restore-held-check at one rank on the synthetic checkpoint; 0 when it passes with TEXT in its PASS line
  docker run --rm --gpus all --ipc=host -v "$SYN:/s" -e TF_GLM_LAYERS=2 $3 --entrypoint $TEST "$IMG" glm-restore-held-check /s/ckpt "/s/id-$1" > "$SYN/$1.log" 2>&1; local rc=$?
  echo "[q90] $(date -u +%T) glm-restore-held-check, $1: rc=$rc, $(grep -c '^PASS' "$SYN/$1.log") PASS, $(grep -c 'FAIL' "$SYN/$1.log") FAIL lines; $(grep -a '^PASS' "$SYN/$1.log" | head -1 | cut -c1-140)"
  [ "$rc" = 0 ] && passed "$SYN/$1.log" "$2"
}
bad=0
held off "RESTORE_HELD off: every restore is whole" "" || bad=1
held on "RESTORE_HELD=1: a state resumed by the sequence that kept it" "-e TF_GLM_OVN_RESTORE_HELD=1" || bad=1
docker run --rm -v "$SYN:/s" --entrypoint rm "$IMG" -rf /s/ckpt > /dev/null 2>&1
[ "$bad" = 0 ] || { echo "[q90] GLM-RESTORE-HELD-CHECK DID NOT PASS: no boot with TF_GLM_OVN_RESTORE_HELD is measured"; exit 1; }
echo "[q90] $(date -u +%T) glm-restore-held-check passed with the switch off and on"
boot() { # boot LABEL XENV [P [CTX]]: the Zig serve up on :8300, 0 when it is
  local label=$1 xenv=$2 p=${3:-4} ctx=${4:-1048576}; mkdir -p "$OUT/f90-boots"; stop
  if [ "$p" = 4 ]; then IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh 4 "$ctx" > "$OUT/f90-boots/$label.log" 2>&1
  else IMAGE=$IMG KNOBS=measured XENV="$xenv" bash zig-tp3.sh "$p" > "$OUT/f90-boots/$label.log" 2>&1; fi && return 0
  echo "[q90] BOOT FAILED $label: $(tail -3 "$OUT/f90-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q90] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q90] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q90] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS [ADD]
  local dir=$1 salt=$2 t1=$3 turns=$4 add=${5:-1000} st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add "$add" --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q90] $salt turn $k FAILED"; return; }
  done
  echo "[q90] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL XENV: longctx facts row for the boot just made
  local label=$1 xenv=$2
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$IMG" "--xenv=$xenv" --out "$OUT/f84-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f84-c/$label-facts.out" 2>&1
}
mkdir -p "$OUT/f84-c"
unit() { # unit LABEL XENV [LEVELS]: a P=4 boot, the cold probe, the growing conversation and greedy decode at LEVELS clients (default 1 and 4)
  local label=$1 xenv=$2 levels=${3:-1 4}
  room || return
  boot "c90-$label" "$xenv" || return
  facts "$label" "$xenv"
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f84-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f84-c/$label-probe.out" 2>&1
  echo "[q90] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f84-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f84-c/$label" "c74" 100000 8
  chain "$OUT/f84-c/$label" "c250" 250000 6
  greedy "$OUT/f84-c/dec-$label" $levels
  keeplog "$OUT/f84-c/r0-$label.log"
}
B="$NEWX $RSX"
H="$B -e TF_GLM_OVN_RESTORE_HELD=1"
unit h0a "$B" "1"
unit h1a "$H" "1"
unit h1b "$H" "1"
unit h0b "$B" "1"
unit h0c "$B" "1"
unit h1c "$H" "1"
unit h1d "$H" "1"
unit h0d "$B" "1"
room || { echo "[q90] out of time before the capture"; exit 0; }
mkdir -p "$OUT/f90-n"; stop
IMAGE=$IMG KNOBS=measured XENV="$H" PHASES="nsys" SIZES="8192 32768" WARMCHAIN=3 CTX=1048576 bash nsys-prefill.sh ph90 > "$OUT/f90-n/prefill.out" 2>&1
echo "[q90] $(date -u +%T) nsys prefill with the switch on (cold 8k, 32k, three warm turns): $(tail -3 "$OUT/f90-n/prefill.out" | tr '\n' ' ' | cut -c1-200)"
exit 0
