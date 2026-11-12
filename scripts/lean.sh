#!/usr/bin/env bash
# lean.sh BASE_TREE HEAD_TREE [NAME] - the lean gate as upstream's CI runs it: base against head, 0 new problems.
# Each side runs ITS OWN copy of tools/zig/lean_check.py from inside its own tree (the script takes its root from its
# own path, so one copy run twice scans one tree twice and always reports 0 new), then HEAD's lean_new.py diffs the
# two lists. Prints both sides' file and problem counts: two identical file counts mean the same tree was scanned
# twice. Lists in ~/gates/lean-NAME-{base,head}.txt. Exit: lean_new.py's (1 if any problem is new).
set -uo pipefail
BASE=$(cd "${1:?usage: lean.sh BASE_TREE HEAD_TREE [NAME]}" && pwd); HEAD=$(cd "${2:?head tree}" && pwd); NAME=${3:-lean}
mkdir -p "$HOME/gates"
b="$HOME/gates/lean-$NAME-base.txt"; h="$HOME/gates/lean-$NAME-head.txt"
( cd "$BASE" && python3 tools/zig/lean_check.py > "$b" 2>&1 )
( cd "$HEAD" && python3 tools/zig/lean_check.py > "$h" 2>&1 )
echo "base $BASE: $(tail -1 "$b")"
echo "head $HEAD: $(tail -1 "$h")"
python3 "$HEAD/tools/zig/lean_new.py" "$b" "$h"
