#!/usr/bin/env python3
"""Fail when any row of the served engine's settings table is not set, or not recorded, in our env.

The rule (owner 2026-11-23): no setting of the engine's table is left unset. Every row whose scope this serve
reads is SET in scripts/env/prod.env and scripts/env/dev.env, at a measured value or at the engine's own
default, and scripts/env/register.env records one verdict per row:

  measured NAME=VALUE   a measurement chose the value (its cells are in docs/KNOBS.md) or it was verified
                        equal to the engine's own computed answer;
  debt NAME=VALUE       set to the engine's own default and not measured on this stack: a lead, not permission;
  candidate NAME=VALUE  dev.env's candidates override the value prod.env keeps at the engine's default (or name a
                        setting prod.env does not carry); the value must be dev.env's.

A name our env files set that the table has no row for needs a `raw NAME=VALUE` line instead (it is read
through a raw getenv, which check-env.py rule 5 covers; a table row is the ideal). The retired `default-ok`
verdict, an unset row, a verdict whose value differs from the files', a duplicate verdict and a stale name all
fail: a base that adds a table row is a hard stop until its value is chosen. Every value prod.env sets is also run
through a mirror of the row's own parser, so a text the engine would refuse is caught here and not at a boot.

Portable across the serve repos: the table path, both env files, the register and the scopes are arguments.
"""
import argparse
import re
import sys
from pathlib import Path

ROW = re.compile(r'\.\{ \.name = "([A-Z0-9_]+)"')  # a row starts here; fields are read independently
SCOPE = re.compile(r"\.scope = \.(\w+)")
FORMS = re.compile(r'\.forms = "([^"]*)"')
KIND = re.compile(r"\.kind = \.(\w+)")
NUM = {k: re.compile(r"\.%s = (\d+)" % k) for k in ("min", "max", "base")}
WORDS = re.compile(r"\.words = &\.\{([^}]*)\}")
ONLY = re.compile(r"\.only = &\.\{([^}]*)\}")
FLAGS = {k: re.compile(r"\.%s = (\w+)" % k) for k in ("first_digit", "blank_default")}
LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
VERDICT = re.compile(r"^#\s*(measured|debt|default-ok|unreachable|raw|candidate)\s+([A-Z0-9_]+)=(\S*): (.*)$")  # values hold no space
CITE = re.compile(r"(work/[A-Za-z0-9_./-]+|docs/[A-Za-z0-9_./-]+|int-docs/[A-Za-z0-9_./-]+|scripts/[A-Za-z0-9_./-]+)")
EXTERNAL = re.compile(r"^(NCCL_|HF_HUB_OFFLINE$)")


def table(path: Path, scopes: set[str]) -> dict[str, tuple[str, str, dict]]:
    """Read a row per line, field by field: optional fields (trim, no_word, ...) must not hide a setting. The spec is
    what the engine's own parser reads (platform/environment.zig's parse), so a value can be checked before a boot."""
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW.search(line)
        if not m:
            continue
        scope = SCOPE.search(line)
        if not scope or scope.group(1) not in scopes:
            continue
        forms = FORMS.search(line)
        kind = KIND.search(line)
        spec = {"kind": kind.group(1) if kind else "?"}
        for k, rx in NUM.items():
            mm = rx.search(line)
            if mm:
                spec[k] = mm.group(1)
        for k, rx in FLAGS.items():
            mm = rx.search(line)
            if mm:
                spec[k] = mm.group(1) == "true"
        mm = WORDS.search(line)
        if mm:
            spec["words"] = [w.strip().strip('"') for w in mm.group(1).split(",") if w.strip()]
        mm = ONLY.search(line)
        if mm:
            spec["only"] = [int(x) for x in mm.group(1).replace("_", "").split(",") if x.strip().isdigit()]
        rows[m.group(1)] = (scope.group(1), (forms.group(1) if forms else spec["kind"]) or "?", spec)
    return rows


def parses(spec: dict, text: str) -> str | None:
    """None when the engine's parse(name, text) accepts this text, else why (a mirror of platform/environment.zig's
    parse for the text forms this serve writes; blank is handled by the caller because serve.sh never passes it)."""
    kind = spec["kind"]
    try:
        if kind == "word":
            return None if text in spec.get("words", []) else f"not one of {spec.get('words')}"
        if kind == "toggle":
            return None if text.lower() in ("0", "false", "off", "1", "true", "on", "yes") else "not a toggle"
        if kind == "path":
            return None if all(0x20 <= ord(c) < 0x7f or ord(c) > 0x7f for c in text) else "control character"
        if kind == "flag":
            return None if text in ("0", "1") else "not 0 or 1"
        if kind == "bit_width":
            return None if text in ("4", "8") else "not 4 or 8"
        if kind == "parallel":
            if text.lower() == "auto":
                return None
            n = int(text, 10)
            lo, hi = int(spec.get("min", 1)), int(spec.get("max", 4096))
            return None if lo <= n <= hi else f"outside {lo}..{hi}"
        if kind in ("real", "positive_real", "signed_real"):
            x = float(text)
            if x != x or x in (float("inf"), float("-inf")):
                return "not finite"
            if kind == "real" and x < 0:
                return "below 0"
            if kind == "positive_real" and x <= 0:
                return "not above 0"
            hi = int(spec.get("max", 0))
            return None if not hi or x <= hi else f"above {hi}"
        if kind == "range":
            lo, _, hi = text.partition("-")
            return None if int(lo) <= int(hi) else "lo above hi"
        n = int(text, int(spec.get("base", 10)))
        cap = {"u32": 2**32 - 1, "positive": 2**32 - 1, "device": 2**32 - 1, "percent": 100,
               "segments": 4, "mib": 2**64 - 1, "size": 2**64 - 1}.get(kind, 2**64 - 1)
        if not 0 <= n <= cap or n > int(spec.get("max", 2**64 - 1)) or n < int(spec.get("min", 0)):
            return "outside its bounds"
        if spec.get("only") and n not in spec["only"]:
            return f"not one of {spec['only']}"
        if kind in ("positive", "segments", "mib") and n == 0:
            return "is zero"
        if kind == "prompt" and (n < 128 or n > 2048 or n % 16):
            return "not a prompt width"
        return None
    except ValueError:
        return "not a number of its kind"


def env(path: Path) -> tuple[dict[str, str], dict[str, dict[str, str]], set[str]]:
    """(every NAME=value, {section: {name: value}}, the completeness block's names): the last line of a name wins, as
    serve.sh passes sections in order and the later -e is the value a boot runs."""
    out: dict[str, str] = {}
    secs: dict[str, dict[str, str]] = {}
    complete: set[str] = set()
    sec, block = None, None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        m = re.match(r"# --- (runtime|recipe|candidates)\s*$", line)
        if m:
            sec, block = m.group(1), None
            secs.setdefault(sec, {})
            continue
        if line.startswith("# --- completeness"):
            block = "completeness"
            continue
        if not line or line.startswith("#"):
            continue
        line = re.split(r"\s#", line)[0].strip()
        m = LINE.match(line)
        if not m:
            continue
        out[m.group(1)] = m.group(2)
        if sec:
            secs[sec][m.group(1)] = m.group(2)
        if sec == "recipe" and block == "completeness":
            complete.add(m.group(1))
    return out, secs, complete


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True, help="the served tree's zig/src/platform/environment.zig")
    ap.add_argument("--prod", required=True, help="the production env file")
    ap.add_argument("--dev", required=True, help="the development env file")
    ap.add_argument("--register", required=True, help="register.env holding the verdict lines")
    ap.add_argument("--scopes", required=True, help="comma list of the table scopes this serve reads")
    args = ap.parse_args()

    scopes = {s.strip() for s in args.scopes.split(",") if s.strip()}
    rows = table(Path(args.table), scopes)
    if not rows:
        print(f"coverage: no settings parsed from {args.table} for scopes {sorted(scopes)}: the table format or scopes moved")
        return 2

    prod, prod_secs, complete = env(Path(args.prod))
    dev, dev_secs, _ = env(Path(args.dev))
    problems: list[str] = []

    verdicts: dict[str, tuple[str, str, str]] = {}
    raw: dict[str, str] = {}
    candidates: dict[str, tuple[str, str]] = {}
    reg = Path(args.register)
    section = False  # the header's examples are not records: only lines under a `# ---` marker count
    for line in reg.read_text(encoding="utf-8").splitlines():
        if line.startswith("# ---"):
            section = True
            continue
        m = VERDICT.match(line) if section else None
        if not m:
            continue
        kind, name, value, rest = m.groups()
        if kind in ("default-ok", "unreachable"):
            problems.append(f"{reg.name}: {name} uses the retired verdict {kind}: every row is now set, so the verdict is "
                            f"measured or debt")
            continue
        if kind == "raw":
            raw[name] = value
            continue
        if kind == "candidate":
            if name in candidates:
                problems.append(f"{reg.name}: {name} has two candidate lines")
            if not CITE.search(rest):
                problems.append(f"{reg.name}: candidate {name} cites no evidence path")
            candidates[name] = (value, rest)
            continue
        if name in verdicts:
            problems.append(f"{reg.name}: {name} has two verdicts")
        if not CITE.search(rest):
            problems.append(f"{reg.name}: {name} ({kind}) cites no evidence path")
        verdicts[name] = (kind, value, rest)

    silent = sorted(n for n in rows if n not in prod or n not in dev)
    for name in silent:
        scope, forms, _ = rows[name]
        missing = " and ".join(f for f, d in (("prod.env", prod), ("dev.env", dev)) if name not in d)
        problems.append(f"UNSET {name} ({scope}, forms {forms}): not set in {missing}; every row is set or the rebase stops here")
    for sec in ("runtime", "recipe"):
        for name, value in sorted(prod_secs.get(sec, {}).items()):
            dev_value = dev_secs.get(sec, {}).get(name)
            if dev_value != value:
                problems.append(f"DIFFERS {sec} {name}: prod.env has {value!r}, dev.env {dev_value!r}")
    unrecorded = sorted(n for n in rows if n not in verdicts)
    for name in unrecorded:
        problems.append(f"UNRECORDED {name}: set in the env files but {reg.name} has no measured or debt line")
    stale = sorted(n for n in verdicts if n not in rows)
    for name in stale:
        problems.append(f"STALE {name}: the register names a setting this table does not have")
    for name, (kind, value, _) in sorted(verdicts.items()):
        if name in prod and prod[name] != value:
            problems.append(f"VALUE {name}: the register says {value!r}, prod.env sets {prod[name]!r}")
    for name, value in sorted(prod.items()):
        if name not in rows:
            continue
        if value == "":
            if not rows[name][2].get("blank_default", True):
                problems.append(f"BLANK {name}: the row refuses a blank value, so its line cannot be blank")
            continue
        why = parses(rows[name][2], value)
        if why:
            problems.append(f"REFUSED {name}={value}: the row's own parser refuses it ({why}), so the boot would stop")
    extra = sorted(n for n in set(prod) | set(dev) if n not in rows and not EXTERNAL.match(n))
    for name in extra:
        if name not in raw:
            problems.append(f"UNREAD {name}: set in an env file with no table row and no raw line in {reg.name}")
        elif raw[name] != prod.get(name, dev.get(name, "")):
            problems.append(f"VALUE {name}: the raw line says {raw[name]!r}, the env file sets "
                            f"{prod.get(name, dev.get(name))!r}")
    for name in sorted(raw):
        if name in rows:
            problems.append(f"RAW {name}: the table has a row for it, so it is a measured/debt verdict, not raw")
        if name not in prod and name not in dev:
            problems.append(f"STALE {name}: a raw line for a setting no env file sets")

    dev_cand = dev_secs.get("candidates", {})
    for name in sorted(dev_cand):
        if name not in candidates:
            problems.append(f"UNRECORDED candidate {name}: a dev.env candidates line with no candidate line in {reg.name}")
    for name, (value, _) in sorted(candidates.items()):
        if name not in dev_cand:
            problems.append(f"STALE candidate {name}: the register names a candidate dev.env does not set")
        elif dev_cand[name] != value:
            problems.append(f"VALUE candidate {name}: the register says {value!r}, dev.env sets {dev_cand[name]!r}")
    for name, value in sorted(dev_cand.items()):
        if name in rows and value != "":
            why = parses(rows[name][2], value)
            if why:
                problems.append(f"REFUSED candidate {name}={value}: the row's own parser refuses it ({why})")
        if name in rows:
            if name not in complete:
                problems.append(f"CANDIDATE {name}: overrides a measured recipe line; a candidate may only raise a row prod keeps at "
                                f"its engine default (prod.env's completeness block)")
            if prod.get(name) == value:
                problems.append(f"CANDIDATE {name}: repeats prod.env's value, so it decides nothing")
    measured = sum(1 for n in rows if verdicts.get(n, ("",))[0] == "measured")
    debt = sum(1 for n in rows if verdicts.get(n, ("",))[0] == "debt")
    print(f"coverage: {len(rows)} rows in scope, set {len(rows) - len(silent)}, measured {measured}, debt {debt}, "
          f"raw {len(raw)}, candidates {len(dev_cand)}, unset {len(silent)}, unrecorded {len(unrecorded)}")
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
