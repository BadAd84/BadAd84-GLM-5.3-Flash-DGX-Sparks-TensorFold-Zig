#!/usr/bin/env bash
# test_zig_tp3_prod_wait.sh - zig-tp3.sh's wait for production's ranks, without a GPU or the Sparks: zig-tp3.sh runs against
# stubs (docker, ssh, scp, nohup, curl, sleep) that record a sequence log. spark2 reports production's container for its first
# three probes, as production's rank 1 does for about two minutes after its head is removed. Expected: no rank boots before
# the probe that finds no production; a box that never clears gives exit 1, the refusal line and no boot; a rank 0 container
# that runs and is then removed is reported as exited, not as never created.
# Pass a zig-tp3.sh path as the first argument to test a mutated copy. Run from anywhere with bash (WSL is fine).
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tp3="${1:-$here/../zig-tp3.sh}"  # an argument, not an env var: a VAR= prefix does not cross into this bash from the Windows shell
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/home/.cache/huggingface/hub/models--Mia-AiLab--GLM-5.3-Flash-EXL3-4bpw-TensorFold/snapshots/078455ffe6472f9a52fbc1139f58b9db2881b25c"
cat > "$tmp/bin/ssh" <<'EOF'
#!/usr/bin/env bash
host=""; for a in "$@"; do case $a in adam@*) host=$a ;; esac; done
cmd="${*: -1}"
case $cmd in
  *"docker ps --format"*)
    n=$(( $(cat "$STUB_DIR/n-$host" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$STUB_DIR/n-$host"
    if [[ $host == *spark2* && ( "$STUB_BUSY" = always || $n -le "$STUB_BUSY" ) ]]; then echo "probe $host busy" >> "$STUB_LOG"; echo glm53-flash-tf
    else echo "probe $host clear" >> "$STUB_LOG"; fi ;;
  *"docker ps -a"*) echo "no container" ;;
  *) : ;;
esac
exit 0
EOF
cat > "$tmp/bin/docker" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  ps) echo "probe spark1 clear" >> "$STUB_LOG" ;;
  inspect)
    if [ "$STUB_R0" = vanish ]; then
      n=$(( $(cat "$STUB_DIR/inspect" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$STUB_DIR/inspect"
      if [ "$n" -le 2 ]; then [[ "$*" == *State.Running* ]] && echo true; exit 0; fi
      exit 1
    fi
    exit 1 ;;
esac
exit 0
EOF
cat > "$tmp/bin/nohup" <<'EOF'
#!/usr/bin/env bash
echo "boot" >> "$STUB_LOG"
exit 0
EOF
cat > "$tmp/bin/curl" <<'EOF'
#!/usr/bin/env bash
[ "$STUB_R0" = up ] && grep -q '^boot' "$STUB_LOG" && exit 0
exit 7
EOF
printf '#!/usr/bin/env bash\nexit 0\n' > "$tmp/bin/scp"
printf '#!/usr/bin/env bash\nexit 0\n' > "$tmp/bin/sleep"
chmod +x "$tmp/bin/"*
fail=0
run() { # run BUSY R0 -> rc (BUSY: spark2's probes that find production, or always); the log in $tmp/log, stdout in $tmp/out
  rm -f "$tmp"/n-* "$tmp/inspect"; : > "$tmp/log"
  env -i PATH="$tmp/bin:$PATH" HOME="$tmp/home" STUB_DIR="$tmp" STUB_LOG="$tmp/log" STUB_BUSY="$1" STUB_R0="$2" IMAGE=fake:1 \
    bash "$tp3" 4 65536 > "$tmp/out" 2>&1
}
check() { # check NAME CONDITION...
  local name=$1; shift
  if "$@"; then echo "ok   $name"; else echo "FAIL $name"; sed 's/^/     log: /' "$tmp/log" | head -12; sed 's/^/     out: /' "$tmp/out" | head -6; fail=1; fi
}
boots_after_clear() { # every boot line comes after the first round of probes in which spark2 is clear
  local first_boot clear
  first_boot=$(grep -n '^boot' "$tmp/log" | head -1 | cut -d: -f1)
  clear=$(grep -n '^probe adam@spark2.ots-int.net clear' "$tmp/log" | head -1 | cut -d: -f1)
  [ -n "$first_boot" ] && [ -n "$clear" ] && [ "$first_boot" -gt "$clear" ] && ! sed -n "${clear},\$p" "$tmp/log" | grep -q 'busy'
}
run 3 up; rc=$?
check "production on spark2 for three probes: the boot waits, then comes up" [ "$rc" = 0 ]
check "no rank boots while spark2 runs production" boots_after_clear
check "the busy probes were seen" grep -q 'probe adam@spark2.ots-int.net busy' "$tmp/log"
check "the wait is reported" grep -q "still runs on: spark2; waiting" "$tmp/out"
run always up; rc=$?
check "production that never leaves: exit 1" [ "$rc" = 1 ]
check "production that never leaves: no rank boots" bash -c "! grep -q '^boot' '$tmp/log'"
check "production that never leaves: the refusal names the box" grep -q "production still runs on: spark2 after 240 s" "$tmp/out"
run 0 vanish; rc=$?
check "rank 0's container removed after it ran: exit 1" [ "$rc" = 1 ]
check "rank 0's container removed after it ran: reported as exited" grep -q "rank 0's container exited after" "$tmp/out"
check "rank 0's container removed after it ran: not reported as never created" bash -c "! grep -q 'never created' '$tmp/out'"
[ "$fail" = 0 ] && echo "test_zig_tp3_prod_wait: PASS" || echo "test_zig_tp3_prod_wait: FAIL"
exit "$fail"
