#!/bin/bash
# test_queue92_funcs.sh: queue92.sh's cenv, readback and effect against stubbed docker and ssh, no GPU; run from the repo root with bash (Q92=path tests another copy of the script).
set -u
ROOT=$(pwd)
OUT=$(mktemp -d "$ROOT/work/q101fn.XXXXXX"); mkdir -p "$OUT/f92-c"
trap 'rm -rf "$OUT"' EXIT
W1=h1; W2=h2
# fixtures: ENV_<container> is the container's environment, LOG is rank 0's log
eval "$(sed -n '/^cenv() {/,/^greedy() {/p' "${Q92:-$ROOT/scripts/queues/queue92.sh}" | sed '$d')"
docker() {
  case "$1" in
    inspect) eval "printf '%s\n' \"\${ENV_${2//-/_}:-}\"" ;;
    logs) printf '%s\n' "${LOG:-}" ;;
  esac
}
ssh() { local cmd="${*: -1}"; local c; c=$(printf '%s' "$cmd" | sed -E 's/.*docker inspect ([a-z0-9-]+) .*/\1/'); eval "printf '%s\n' \"\${ENV_${c//-/_}:-}\""; }
base="TF_GLM_RANK=0
PATH=/usr/bin"
set_env() { ENV_glm53_zig_r0="$base"$'\n'"$1"; ENV_glm53_zig_r1="TF_GLM_RANK=1"$'\n'"$2"; ENV_glm53_zig_r2="TF_GLM_RANK=2"$'\n'"$3"; }
pass=0; fail=0
check() { # check NAME EXPECTED_RC CMD...
  local name=$1 want=$2; shift 2
  out=$( ( "$@" ) 2>&1 ); rc=$?
  if [ "$rc" = "$want" ]; then pass=$((pass + 1)); printf 'ok   %-60s rc=%s\n' "$name" "$rc"; else fail=$((fail + 1)); printf 'FAIL %-60s rc=%s want %s\n%s\n' "$name" "$rc" "$want" "$out"; fi
  LAST="$out"
}
set_env "" "" ""
check "control arm, nothing set anywhere" 0 readback ut2a ""
case "$LAST" in *"read back on all three ranks"*) echo "ok   control arm prints the read-back line" ;; *) echo "FAIL no read-back line: $LAST"; fail=$((fail + 1)) ;; esac
set_env "TF_GLM_DRAFT_SPLIT=1" "TF_GLM_DRAFT_SPLIT=1" "TF_GLM_DRAFT_SPLIT=1"
check "split arm, set on all three ranks" 0 readback ut2s "-e TF_GLM_DRAFT_SPLIT=1"
set_env "TF_GLM_DRAFT_SPLIT=1" "TF_GLM_DRAFT_SPLIT=1" ""
check "split arm, rank 2 lacks it: queue stops" 1 readback ut2s "-e TF_GLM_DRAFT_SPLIT=1"
set_env "TF_GLM_DSCORES=0" "TF_GLM_DSCORES=0" "TF_GLM_DSCORES=0"
check "dscores arm, set on all three ranks" 0 readback ut2d "-e TF_GLM_DSCORES=0"
set_env "TF_GLM_DSCORES=0" "" "TF_GLM_DSCORES=0"
check "dscores arm, rank 1 lacks it: queue stops" 1 readback ut2d "-e TF_GLM_DSCORES=0"
set_env "" "TF_GLM_DSCORES=0" ""
check "control arm, rank 1 carries a leaked DSCORES=0: queue stops" 1 readback ut2a ""
set_env "TF_GLM_DRAFT_SPLIT=1" "" ""
check "control arm, rank 0 carries a leaked DRAFT_SPLIT=1: queue stops" 1 readback ut2b ""
set_env "TF_GLM_DSCORES=1" "TF_GLM_DSCORES=1" "TF_GLM_DSCORES=1"
check "dscores arm needs =0 but ranks carry =1: queue stops" 1 readback ut2d "-e TF_GLM_DSCORES=0"
ENV_glm53_zig_r0="PATH=/usr/bin"; ENV_glm53_zig_r1="TF_GLM_RANK=1"; ENV_glm53_zig_r2="TF_GLM_RANK=2"
check "rank 0's environment unreadable: queue stops" 1 readback ut2a ""
# effect
LOG='info: boot line
info: dflash2: drafter from /x (Apache-2.0), linears at 4 bits, 0.44 GiB on the device
warn: TF_GLM_DSEL=0: a decode window'"'"'s DSA select keeps one 1,024-thread CTA a row
warn: TF_GLM_DSCORES=0: a decode window'"'"'s index scores keep tf_glm_scores
info: dflash2: drafter from /y (Apache-2.0), linears at 4 bits, 0.93 GiB on the device
info: other'
effect t1
[ "$(cat "$OUT/f92-c/t1-drafter.txt")" = "info: dflash2: drafter from /x (Apache-2.0), linears at 4 bits, 0.44 GiB on the device" ] && { echo "ok   effect keeps the drafter line"; pass=$((pass + 1)); } || { echo "FAIL drafter file: $(cat "$OUT/f92-c/t1-drafter.txt")"; fail=$((fail + 1)); }
grep -q 'TF_GLM_DSCORES=0' "$OUT/f92-c/t1-dscores.txt" && [ "$(wc -l < "$OUT/f92-c/t1-dscores.txt")" = 1 ] && { echo "ok   effect keeps the one DSCORES line"; pass=$((pass + 1)); } || { echo "FAIL dscores file: $(cat "$OUT/f92-c/t1-dscores.txt")"; fail=$((fail + 1)); }
LOG='info: boot line only'
effect t2
[ "$(cat "$OUT/f92-c/t2-drafter.txt")" = MISSING ] && [ "$(cat "$OUT/f92-c/t2-dscores.txt")" = NONE ] && { echo "ok   effect writes MISSING and NONE when the log has neither"; pass=$((pass + 1)); } || { echo "FAIL t2: $(cat "$OUT/f92-c/t2-drafter.txt") / $(cat "$OUT/f92-c/t2-dscores.txt")"; fail=$((fail + 1)); }
# unit's split check, with every other function stubbed: facts leaves a marker, so a skipped arm is the absence of the marker
eval "$(sed -n '/^unit() {/,/^}/p' "${Q92:-$ROOT/scripts/queues/queue92.sh}")"
room() { return 0; }; boot() { return 0; }; readback() { :; }; effect() { :; }; python3() { :; }
chain() { :; }; greedy() { :; }; sampled() { :; }; prompts() { :; }; keeplog() { :; }
facts() { : > "$OUT/f92-c/$1-facts-ran"; }
ZLOG=x; HAVE=" ut2 "; N=0
unit_case() { # unit_case NAME DRAFTER_FILE_TEXT SPLIT_ARG EXPECT_RAN(1 or 0)
  local name=$1 text=$2 split=$3 want=$4 label; N=$((N + 1)); label="uc$N"
  printf '%s\n' "$text" > "$OUT/f92-c/$label-drafter.txt"
  unit "$label" glm53-zig:ut2 off "" "" "$split" > "$OUT/unit-$label.out" 2>&1
  local ran=0; [ -f "$OUT/f92-c/$label-facts-ran" ] && ran=1
  if [ "$ran" = "$want" ]; then pass=$((pass + 1)); printf 'ok   %s\n' "$name"; else fail=$((fail + 1)); printf 'FAIL %s (facts ran=%s, wanted %s)\n' "$name" "$ran" "$want"; fi
}
line() { printf 'info: dflash2: drafter from /x (Apache-2.0), linears at 4 bits, %s GiB on the device' "$1"; }
unit_case "split arm, drafter 0.44 GiB: the arm runs" "$(line 0.44)" 1 1
unit_case "split arm, drafter 0.59 GiB: the arm runs" "$(line 0.59)" 1 1
unit_case "split arm, drafter 0.60 GiB: skipped" "$(line 0.60)" 1 0
unit_case "split arm, drafter 0.73 GiB: skipped" "$(line 0.73)" 1 0
unit_case "split arm, drafter 0.93 GiB: skipped" "$(line 0.93)" 1 0
unit_case "split arm, drafter line MISSING: skipped" "MISSING" 1 0
grep -q 'did not take effect' "$OUT/unit-uc5.out" && { pass=$((pass + 1)); echo "ok   a skipped split arm says the switch did not take effect"; } || { fail=$((fail + 1)); echo "FAIL skip message: $(cat "$OUT/unit-uc5.out")"; }
unit_case "ordinary arm, drafter 0.93 GiB: runs" "$(line 0.93)" "" 1
unit_case "ordinary arm, drafter line MISSING: runs" "MISSING" "" 1
echo "passed $pass, failed $fail"
[ "$fail" = 0 ]
