#!/usr/bin/env bash
# forced-arm.sh IMAGE TAG - one boot at one stream, teacher_forced.py over a reply of production's (FORCED, default forced.json beside this file), then rank 0's
# whole dflash2 round log (bench-arm.sh keeps only 800 lines; this run writes about 3 a position). Env as
# bench-arm.sh (KNOBS, DRAFTER, CTX, XENV); XENV must carry -e TF_GLM_DFLASH2_LOG=100000; LIVE=1 adds an unforced run of the prompt first (live.log, live.jsonl). The serve runs with
# --prompt-cache-gib 0: a request resumed from a kept state would restart the drafter's context at the resume point,
# and every position must draft from the whole forced prefix (forced_score.py checks the `prompt cache:` lines).
# A forced file is {prompt: ids, reply: ids, reply_sha12, prod: {rounds, drafted, accepted, tokens}}: production's prompt and its own reply to it, with its live counters
# (per_prompt.py --text gives both). On the head, beside zig-tp3.sh, with teacher_forced.py.
#   XENV="<cr-ctl's list> -e TF_GLM_DFLASH2_LOG=100000" KNOBS=off bash ~/work/glm53-zig/forced-arm.sh glm53-zig:rs2 tf-ctl
set -uo pipefail
IMAGE=${1:?usage: forced-arm.sh IMAGE TAG}; TAG=${2:?usage: forced-arm.sh IMAGE TAG}
OUT="$HOME/bench/$TAG"; mkdir -p "$OUT"
G="$HOME/work/glm53-zig"
case "${XENV:-}" in *TF_GLM_DFLASH2_LOG=*) ;; *) echo "XENV lacks TF_GLM_DFLASH2_LOG: the scorer needs every round"; exit 2 ;; esac
echo "[forced $TAG] boot at $(date +%T)"
XSERVE="${XSERVE:-} --prompt-cache-gib 0" IMAGE="$IMAGE" KNOBS="${KNOBS:-off}" DRAFTER="${DRAFTER:-1}" CTX="${CTX:-}" \
  bash "$G/zig-tp3.sh" 1 > "$OUT/boot-P1.log" 2>&1 \
  || { echo "[forced $TAG] BOOT FAILED"; bash "$G/zig-tp3-stop.sh" >/dev/null 2>&1; exit 1; }
SKIP=0
if [[ "${LIVE:-0}" == 1 ]]; then # the forced file's prompt once, unforced, first: its rounds (live.log) are the drafter mid-stream on the text the forced run then walks
  python3 -c 'import json,sys; json.dump([{"name": "live", "ids": json.load(open(sys.argv[1]))["prompt"]}], open(sys.argv[2], "w"))' "${FORCED:-$G/forced.json}" "$OUT/live-ids.json"
  python3 "$G/per_prompt.py" 8300 --ids "$OUT/live-ids.json" --out "$OUT/live.jsonl" --reps 1 --text > "$OUT/live.out" 2>&1 || echo "[forced $TAG] LIVE RUN FAILED"
  docker logs glm53-zig-r0 2>&1 | grep -a "dflash2 round" > "$OUT/live.log"; SKIP=$(wc -l < "$OUT/live.log")
fi
python3 "$G/teacher_forced.py" 8300 --forced "${FORCED:-$G/forced.json}" --out "$OUT/records.jsonl" > "$OUT/forced.out" 2>&1 \
  || echo "[forced $TAG] DRIVER FAILED"
docker logs glm53-zig-r0 2>&1 | grep -a "dflash2 round" | tail -n +$((SKIP + 1)) > "$OUT/rounds.log"
docker logs glm53-zig-r0 2>&1 | grep -a "prompt cache:" > "$OUT/cache.log"
docker logs glm53-zig-r0 2>&1 | grep -a "^info\|^warn\|^error\|^debug" | grep -av "dflash2 round\|prompt cache:" | tail -n 800 > "$OUT/r0-P1.log"
bash "$G/zig-tp3-stop.sh" >/dev/null 2>&1
echo "DONE $TAG at $(date +%T): $(wc -l < "$OUT/records.jsonl") records, $(wc -l < "$OUT/rounds.log") round lines"
