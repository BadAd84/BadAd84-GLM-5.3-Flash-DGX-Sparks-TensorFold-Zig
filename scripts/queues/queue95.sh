#!/bin/bash
# queue95.sh - on spark1, detached, after queue92: the T/X split of scripts/env/dev.env's ten candidates on the stack re-seated on upstream main (image m130a). No build and no
# GPU device check: m130a and v129zg already exist on all three ranks, and the same-image-id check below skips any arm whose image is not identical everywhere, with a line saying
# so. Production is down for the campaign and stays down. QUEUE95-DONE.
# queue95.env: IMG (m130a), IMGO (v129zg) and WORKERS, the names queue91.sh requires from queue91.env, plus HOURS (default 4) and WAIT_FOR (default queue92.sh); those two
# have defaults, so a file that omits them still runs.
#
#   images: IMG m130a (the re-seated 47-patch stack, the tree the full gate passed) and IMGO v129zg (the v1.2.9 stack). Each image must be ONE id on all three ranks; an arm
#     whose image is absent or differs is skipped with a line saying so. Nothing is built here.
#   units, in this order (the T and X pairs sit first and second half around mo4, so a drifting box shows in them):
#     mn3  IMG,  KNOBS=prod, no XENV                       the stack as committed, the third boot of queue91's N group (mn1 mn2)
#     mt1  IMG,  KNOBS=prod, XENV=T                        the four decode-capable candidates
#     mx1  IMG,  KNOBS=prod, XENV=X                        the six prompt-only candidates
#     mo4  IMGO, KNOBS=prod, -e TF_GLM_OVN_EXL3_ITEMS=1    the old stack, its own item plan switch (queue91's mo3, one more boot of the O group)
#     mx2  IMG,  KNOBS=prod, XENV=X                        the second X boot
#     mt2  IMG,  KNOBS=prod, XENV=T                        the second T boot
#   T (the four that can touch decode): TF_GLM_OVN_MM_WIDE=1, TF_GLM_OVN_SIDE_PRIO=1, TF_GLM_OVN_LATENT_ROWS=2 and NCCL_NCHANNELS_PER_NET_PEER=4.
#   X (the six prompt-only ones): TF_GLM_OVERLAP_PIECES=4, TF_GLM_OVN_PIECE_FRONT=1, TF_GLM_OVN_PIECE_FFN=1, TF_GLM_OVN_PIECE_MLA=1, TF_GLM_OVN_SOLO_TO_START=1 and
#   TF_GLM_OVN_RESTORE_HELD=1. Both sets are passed through XENV on top of KNOBS=prod: serve.sh skips a file line whose name XENV names and appends XENV after the file's own
#   lines, so the XENV value is the boot's value. Together they are exactly dev.env's ten candidate lines.
#   every unit is a fresh boot at --parallel 4 --context 1048576 and runs queue91's cells exactly: the cold first token at 8k / 32k / 120k (two requests, seed pf74), the growing
#     conversation (salt c74: a 100k first turn and seven turns of about 1,300 rows), greedy and sampled decode at 1, 2, 4, 6 and 8 clients, and the 24 prompts one at a time.
#     Rows go to $HOME/bench/f95-c in queue91's f91-c layout (<label>/, dec-<label>/, rows.jsonl), so score91.py's readers and queue95's scorer apply unchanged.
#   scripts/queue-scores/score95.py reads the rows; its rules were written before they existed.
set -u
G=$HOME/work/glm53-zig; cd "$G" || exit 1
. ./queue95.env
WORKERS=${WORKERS:?set WORKERS}; export WORKERS
W1=${WORKERS%% *}; W2=${WORKERS##* }
LONGCTX_WORKERS=${LONGCTX_WORKERS:-${WORKERS// /,}}; export LONGCTX_WORKERS
export KEEP=1
IMG=${IMG:?set IMG}; IMGO=${IMGO:?set IMGO}
WAIT_FOR=${WAIT_FOR:-queue92.sh}
T="-e TF_GLM_OVN_MM_WIDE=1 -e TF_GLM_OVN_SIDE_PRIO=1 -e TF_GLM_OVN_LATENT_ROWS=2 -e NCCL_NCHANNELS_PER_NET_PEER=4"
X="-e TF_GLM_OVERLAP_PIECES=4 -e TF_GLM_OVN_PIECE_FRONT=1 -e TF_GLM_OVN_PIECE_FFN=1 -e TF_GLM_OVN_PIECE_MLA=1 -e TF_GLM_OVN_SOLO_TO_START=1 -e TF_GLM_OVN_RESTORE_HELD=1"
ZLOG='docker logs --since {since} glm53-zig-r0'
OUT=$HOME/bench
agg() { tail -1 "$1" | grep -o '"agg_tok_s": [0-9.]*'; }
stop() { bash zig-tp3-stop.sh > /dev/null 2>&1; sleep 10; }
finish() { stop; docker rm -f glm53-zig-r0 > /dev/null 2>&1; echo "QUEUE95-DONE $(date -u +%T)"; }
echo "[q95] $(date -u +%T) start; waiting for $WAIT_FOR"
while pgrep -f "$WAIT_FOR" > /dev/null; do sleep 60; done
trap finish EXIT
DEADLINE=$(( $(date +%s) + ${HOURS:-4} * 3600 ))
room() { [ "$(date +%s)" -lt "$DEADLINE" ]; }
mkdir -p "$OUT"
echo "[q95] $(date -u +%T) $WAIT_FOR is done; IMG=$IMG IMGO=$IMGO; deadline $(date -u -d @$DEADLINE +%T); $(df -h /home | tail -1 | awk '{print $4}') free"
ids_of() { { docker images --no-trunc --format '{{.ID}}' "$1" | head -1; for h in "$W1" "$W2"; do ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "docker images --no-trunc --format '{{.ID}}' $1 | head -1"; done; }; }
HAVE=" "
for image in "$IMG" "$IMGO"; do
  if ! docker images --format '{{.ID}}' "$image" | grep -q .; then echo "[q95] IMAGE $image IS ABSENT on spark1: its arms are skipped (nothing is built here)"; continue; fi
  ids=$(ids_of "$image")
  if [ "$(echo "$ids" | grep -c .)" = 3 ] && [ "$(echo "$ids" | sort -u | wc -l)" = 1 ]; then
    HAVE="$HAVE$image "; echo "[q95] $image ids: $(echo $ids | cut -c1-80)"
  else
    echo "[q95] IMAGE $image IS NOT THE SAME ON ALL THREE RANKS: its arms are skipped (ids: $(echo $ids | tr '\n' ' '))"
  fi
done
case "$HAVE" in *" $IMG "*) ;; *) echo "[q95] the stack's image $IMG is not usable on all three ranks: nothing to measure"; exit 1 ;; esac
echo "[q95] images in the window:$HAVE"
echo "[q95] serve.sh sha256 (first 12): $(sha256sum serve.sh | cut -c1-12); env: $(cat env/prod.env env/dev.env | sha256sum | cut -c1-12)"
python3 check-env.py --env-dir env > "$OUT/f95-check-env.log" 2>&1; echo "[q95] check-env rc=$?: $(tail -1 "$OUT/f95-check-env.log")"
split=$(printf '%s\n' "$T" "$X" | grep -o -- '-e [A-Za-z_][A-Za-z0-9_]*=[^ ]*' | sed 's/^-e //' | sort)
cand=$(bash env/words.sh dev candidates | tr ' ' '\n' | sort)
if [ "$split" = "$cand" ]; then
  echo "[q95] the T and X sets are exactly dev.env's $(echo "$cand" | grep -c .) candidates (T $(( $(printf '%s\n' "$T" | grep -o -- '-e ' | wc -l) )), X $(( $(printf '%s\n' "$X" | grep -o -- '-e ' | wc -l) )))"
else
  echo "[q95] THE T/X SETS AND DEV.ENV'S CANDIDATES DIFFER, so this window would measure a split dev.env does not carry: nothing is measured"
  diff <(echo "$cand") <(echo "$split") | sed 's/^/[q95]   /'
  exit 1
fi
bash prod-stop.sh || { echo "[q95] PRODUCTION DID NOT STOP"; exit 1; }
stop
boot() { # boot LABEL IMAGE KNOBS XENV: the Zig serve up on :8300 at --parallel 4 --context 1048576, 0 when it is
  local label=$1 image=$2 knobs=$3 xenv=$4; mkdir -p "$OUT/f95-boots"; stop
  IMAGE=$image KNOBS=$knobs XENV="$xenv" bash zig-tp3.sh 4 1048576 > "$OUT/f95-boots/$label.log" 2>&1 && return 0
  echo "[q95] BOOT FAILED $label: $(tail -3 "$OUT/f95-boots/$label.log" | tr '\n' ' ' | cut -c1-300)"; return 1
}
mem() { # mem FILE: what the three boxes and rank 0's container hold now
  { echo "== $(date -u +%T) spark1"; free -m | sed -n 2p; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' glm53-zig-r0 2> /dev/null
    for h in "$W1" "$W2"; do echo "== $h"; ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$h" "free -m | sed -n 2p; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' 2>/dev/null | head -2"; done; } > "$1" 2>&1
}
keeplog() { docker logs glm53-zig-r0 2>&1 | grep -a -E "^(info|warn|error)" | tail -n 800 > "$1"; }
greedy() { # greedy DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_ids.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-P$N" --out "$dir/P$N.jsonl" > "$dir/P$N.out" 2>&1; local r1=$?
    python3 streams_ids.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-C$N" --out "$dir/C$N.jsonl" > "$dir/C$N.out" 2>&1; local r2=$?
    echo "[q95] $(date -u +%T) $tag $N greedy prose rc=$r1 $(agg "$dir/P$N.out") code rc=$r2 $(agg "$dir/C$N.out")"
  done
}
sampled() { # sampled DIR LEVELS...
  local dir=$1 tag; tag=$(basename "$1"); shift; mkdir -p "$dir"
  for N in "$@"; do
    python3 streams_sampled.py 8300 "$N" --ids prose33.json --max-tokens 400 --rounds 3 --tag "$tag-SP$N" --out "$dir/SP$N.jsonl" > "$dir/SP$N.out" 2>&1; local r1=$?
    python3 streams_sampled.py 8300 "$N" --ids code_ids.json --max-tokens 400 --rounds 3 --tag "$tag-SC$N" --out "$dir/SC$N.jsonl" > "$dir/SC$N.out" 2>&1; local r2=$?
    echo "[q95] $(date -u +%T) $tag $N sampled prose rc=$r1 $(agg "$dir/SP$N.out") code rc=$r2 $(agg "$dir/SC$N.out")"
  done
}
prompts() { mkdir -p "$1"; python3 per_prompt.py 8300 --ids prompts24.json --reps 1 --out "$1/pp.jsonl" > "$1/pp.out" 2>&1; echo "[q95] $(date -u +%T) $(basename "$1") 24 prompts rc=$?"; }
chain() { # chain DIR SALT T1 TURNS [ADD]
  local dir=$1 salt=$2 t1=$3 turns=$4 add=${5:-1000} st; st="$1/chain-$2.json"; mkdir -p "$dir"; rm -f "$st"
  for k in $(seq 1 "$turns"); do
    python3 longctx.py chain 8300 "$st" --t1 "$t1" --add "$add" --salt "$salt" --tag "$salt" --n 4 --out "$dir/chain.jsonl" --log-cmd "$ZLOG" > "$dir/chain-$salt-$k.out" 2>&1 || { echo "[q95] $salt turn $k FAILED"; return; }
  done
  echo "[q95] $(date -u +%T) $(basename "$dir") chain: $(python3 -c "
import json
r = [json.loads(l) for l in open('$dir/chain.jsonl') if l.strip()]
print(' '.join(str(x['ttft_ms']) for x in r if x.get('tag') == '$salt'))" 2>/dev/null)"
}
facts() { # facts LABEL IMAGE XENV: longctx facts row for the boot just made
  local label=$1 image=$2 xenv=$3
  python3 longctx.py facts 8300 --tag "$label" --n 4 --ctx 1048576 --boot-rc 0 --image "$image" "--xenv=$xenv" --out "$OUT/f95-c/rows.jsonl" --log-cmd "$ZLOG" > "$OUT/f95-c/$label-facts.out" 2>&1
}
SMOKED=0
smoke() { # the first boot only: each of THIS queue's instruments once, tiny, so one that cannot talk to the serve stops the queue before a unit is spent on it
  local d="$OUT/smoke95" a b c e f; mkdir -p "$d"
  python3 -c "import json; d=json.load(open('prompts24.json')); json.dump(d[:2], open('$d/ids-smoke.json', 'w'))"
  python3 longctx.py probe 8300 --tag smoke --n 4 --out "$d/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000 --warm-base 0 --reps 1 --load 0 > "$d/probe.out" 2>&1; a=$?
  python3 longctx.py chain 8300 "$d/chain.json" --t1 8000 --add 500 --salt smk --tag smk --n 4 --out "$d/chain.jsonl" --log-cmd "$ZLOG" > "$d/chain.out" 2>&1; b=$?
  python3 streams_ids.py 8300 1 --ids prose33.json --max-tokens 32 --rounds 1 --tag smoke-P1 --out "$d/P1.jsonl" > "$d/P1.out" 2>&1; c=$?
  python3 streams_sampled.py 8300 1 --ids prose33.json --max-tokens 32 --rounds 1 --tag smoke-SP1 --out "$d/SP1.jsonl" > "$d/SP1.out" 2>&1; e=$?
  python3 per_prompt.py 8300 --ids "$d/ids-smoke.json" --max-tokens 32 --reps 1 --out "$d/pp.jsonl" > "$d/pp.out" 2>&1; f=$?
  echo "[q95] $(date -u +%T) smoke: longctx probe rc=$a chain rc=$b, streams_ids rc=$c, streams_sampled rc=$e, per_prompt rc=$f"
  if [ "$a" != 0 ] || [ "$b" != 0 ] || [ "$c" != 0 ] || [ "$e" != 0 ] || [ "$f" != 0 ]; then
    for n in probe chain P1 SP1 pp; do echo "[q95] smoke $n.out: $(tail -4 "$d/$n.out" | tr '\n' ' ' | cut -c1-400)"; done
    echo "[q95] THE QUEUE'S INSTRUMENTS DO NOT RUN AGAINST THIS SERVE: nothing is measured"; exit 1
  fi
}
mkdir -p "$OUT/f95-c"
unit() { # unit LABEL IMAGE KNOBS XENV: a P=4 boot and everything the queue measures on it
  local label=$1 image=$2 knobs=$3 xenv=$4
  room || return
  case "$HAVE" in *" $image "*) ;; *) echo "[q95] $label: image $image is not the same on all three ranks (absent, or a different id on a rank): skipped"; return ;; esac
  boot "c95-$label" "$image" "$knobs" "$xenv" || return
  facts "$label" "$image" "$xenv"
  mem "$OUT/f95-c/$label-mem-idle.txt"
  echo "[q95] $(date -u +%T) $label up (image $image, KNOBS=$knobs, XENV='$xenv'); $(grep -a -m1 -E 'CUDA sm_|streams at once' "$OUT/f95-c/$label-facts.out" 2>/dev/null | cut -c1-120)"
  if [ "$SMOKED" = 0 ]; then SMOKED=1; smoke; fi
  python3 longctx.py probe 8300 --tag "$label" --n 4 --out "$OUT/f95-c/rows.jsonl" --log-cmd "$ZLOG" --seed pf74 --cold-sizes 8000,32000,120000 --warm-base 0 --reps 2 --load 0 > "$OUT/f95-c/$label-probe.out" 2>&1
  echo "[q95] $(date -u +%T) $label cold rc=$? $(grep -o '"ttft_ms": [0-9]*' "$OUT/f95-c/$label-probe.out" | cut -d' ' -f2 | tr '\n' ' ')"
  chain "$OUT/f95-c/$label" "c74" 100000 8
  greedy "$OUT/f95-c/dec-$label" 1 2 4 6 8
  sampled "$OUT/f95-c/dec-$label" 1 2 4 6 8
  prompts "$OUT/f95-c/dec-$label"
  keeplog "$OUT/f95-c/r0-$label.log"
  mem "$OUT/f95-c/$label-mem-after.txt"
}
unit mn3 "$IMG" prod ""
unit mt1 "$IMG" prod "$T"
unit mx1 "$IMG" prod "$X"
unit mo4 "$IMGO" prod "-e TF_GLM_OVN_EXL3_ITEMS=1"
unit mx2 "$IMG" prod "$X"
unit mt2 "$IMG" prod "$T"
exit 0
