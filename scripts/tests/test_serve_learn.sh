#!/usr/bin/env bash
# test_serve_learn.sh - serve.sh's LEARN switch, without a GPU: serve.sh runs against a `docker` that records its argument list.
# Expected: LEARN unset turns the tier on, the promoted default (the tier production runs); LEARN=0 turns it off; LEARN=1 adds the five disk-tier flags with the defaults of scripts/queue-disk-tier.sh;
# Pass a serve.sh path as the first argument to test a mutated copy (config.sh beside it).
# LEARN=1 with XSERVE already naming --learn-conversations adds nothing twice; LEARN=2 is refused. Run from anywhere with bash (WSL is fine).
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
serve="${1:-$here/../serve.sh}"  # an argument, not an env var: a VAR= prefix does not cross into this bash from the Windows shell
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/home/.cache/huggingface"
cat > "$tmp/bin/docker" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
exit 0
EOF
chmod +x "$tmp/bin/docker"
fail=0
run() { # run NAME ENV... -> the recorded docker argument line (or REFUSED)
  shift
  : > "$tmp/log"
  if env -i PATH="$tmp/bin:$PATH" HOME="$tmp/home" FAKE_DOCKER_LOG="$tmp/log" WORLD=1 IMAGE=fake:1 DRAFTER=0 "$@" bash "$serve" 0 1 65536 > "$tmp/out" 2> "$tmp/err"; then
    grep -a "run -d" "$tmp/log" | head -1
  else
    echo "REFUSED: $(head -1 "$tmp/err")"
  fi
}
expect() { # expect NAME PATTERN LINE [want|none]
  local name=$1 pat=$2 line=$3 want=${4:-want}
  # a "none" check only counts when a docker command was recorded at all: a refused or empty run holds it trivially
  if [[ "$want" = none && "$line" != *"--name glm53-zig-r0"* ]]; then echo "FAIL $name: no docker command recorded: ${line:0:200}"; fail=1; return; fi
  if [[ "$want" = want && "$line" == *$pat* ]] || [[ "$want" = none && "$line" != *$pat* ]]; then echo "ok   $name"; else echo "FAIL $name: $want '$pat' in: ${line:0:300}"; fail=1; fi
}
l=$(run unset)
expect "unset turns the tier on, the promoted default" "--learn-conversations --learn-dir /root/.cache/huggingface/glm53-zig-learn/serve --learn-gib 128 --learn-daily-gib 512 --learn-min-free-gib 40" "$l"
l=$(run zero LEARN=0)
expect "LEARN=0 adds no learn flag" "--learn" "$l" none
l=$(run one LEARN=1)
expect "LEARN=1 names the flag" "--learn-conversations --learn-dir /root/.cache/huggingface/glm53-zig-learn/serve --learn-gib 128 --learn-daily-gib 512 --learn-min-free-gib 40" "$l"
l=$(run named LEARN=1 LEARN_NAME=prod LEARN_GIB=64 LEARN_DAILY_GIB=100 LEARN_MIN_FREE_GIB=20)
expect "LEARN=1 takes its settings" "--learn-dir /root/.cache/huggingface/glm53-zig-learn/prod --learn-gib 64 --learn-daily-gib 100 --learn-min-free-gib 20" "$l"
l=$(run xserve LEARN=1 "XSERVE=--learn-conversations --learn-dir /x --learn-gib 1")
n=$(grep -o -e "--learn-conversations" <<< "$l" | wc -l)
if [ "$n" = 1 ] && [[ "$l" == *"--learn-dir /x"* ]]; then echo "ok   XSERVE naming the tier wins and it is not doubled"; else echo "FAIL XSERVE doubled or lost: ${l:0:300}"; fail=1; fi
l=$(run bad LEARN=2)
expect "LEARN=2 is refused" "REFUSED: serve.sh: LEARN must be 0 or 1" "$l"
[ "$fail" = 0 ] && echo "test_serve_learn: OK" || echo "test_serve_learn: FAIL"
exit "$fail"
