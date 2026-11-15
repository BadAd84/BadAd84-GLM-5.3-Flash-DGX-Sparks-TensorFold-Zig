#!/usr/bin/env bash
# gate-names.sh BASE HEAD - compare the failing test NAME sets of two gates.sh runs (~/gates/<NAME>-test-cuda-host.log).
# Prints the counts, the names only HEAD fails (regressions) and the names only BASE fails. Exit 1 if HEAD fails a
# name BASE does not, and exit 1 if HEAD's log holds a compile error: a build that fails before any test runs has no
# failing test names, and "0 failing names" then means nothing.
set -uo pipefail
B=${1:?usage: gate-names.sh BASE HEAD}; H=${2:?head}
names() { grep -E "^error: '" "$HOME/gates/$1-test-cuda-host.log" | sed "s/' failed:.*//; s/' exited.*//; s/^error: '//" | sort -u; }
names "$B" > "/tmp/gate-names-$B.txt"; names "$H" > "/tmp/gate-names-$H.txt"
echo "$B: $(wc -l < "/tmp/gate-names-$B.txt") failing names | $(grep -E 'tests passed' "$HOME/gates/$B-test-cuda-host.log" | tail -1 | sed 's/.*; //')"
echo "$H: $(wc -l < "/tmp/gate-names-$H.txt") failing names | $(grep -E 'tests passed' "$HOME/gates/$H-test-cuda-host.log" | tail -1 | sed 's/.*; //')"
new=$(comm -13 "/tmp/gate-names-$B.txt" "/tmp/gate-names-$H.txt"); gone=$(comm -23 "/tmp/gate-names-$B.txt" "/tmp/gate-names-$H.txt")
echo "only $H fails: ${new:-none}"
echo "only $B fails: ${gone:-none}"
cerr=$(grep -cE '\.zig:[0-9]+:[0-9]+: error:' "$HOME/gates/$H-test-cuda-host.log")
if [ "$cerr" -gt 0 ]; then echo "$H: BUILD FAILED, $cerr compile error lines in its log (no test ran, its failing names are not a result)"; exit 1; fi
if [ "$(grep -cE '\.zig:[0-9]+:[0-9]+: error:' "$HOME/gates/$B-test-cuda-host.log")" -gt 0 ]; then echo "$B: warning, the base log has compile errors"; fi
[ -z "$new" ]
