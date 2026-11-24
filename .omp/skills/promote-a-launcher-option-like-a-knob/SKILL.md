---
name: promote-a-launcher-option-like-a-knob
description: "Promote a measured launcher/command-line option into the default path the way env knobs are promoted, when the option only shows up as a per-arm flag and later tests do not inherit it"
---

# Promote a launcher option like a knob

Use when a serve repo measures a command-line/launcher option (a path, a tier switch, drafter bits, a parallel/context default) and the win exists only as a flag some queue remembers.

## The rule

A launcher option follows the same promotion rule as an env-table row: a measured winner becomes the launcher's DEFAULT in the commit that carries its cells. A promotion that sets the flag in a few queues is not a promotion. Cells measured before it and after it describe two different serves; a table that mixes them says so.

## Checklist

1. Clock the option over the full stream set (1, 2, 4, 6, 8; a fresh boot a level; interleaved arms). No level may regress. A gain somewhere with a loss elsewhere is a trade and goes to the owner with both sides.
2. Change the default in the launcher.
3. Change the default in EVERY driver that forwards the option. A wrapper that expands `VAR='${VAR:-0}'` into the launcher's environment silently overrides a new default of 1 - this is the trap that hid the disk tier.
4. Rewrite the launcher's own test: an assertion like "unset adds no flag" encodes the old default. After promotion it must assert the promoted value, with `VAR=0` as the off arm. Prove both arms.
5. Run the repo's sync gate (the box runs a copy of the repo's scripts) before the next GPU window.
6. Record the promotion: value, evidence, date, in the settings ledger. Re-measure any comparison table whose cells predate it.

## The worked example

The NVMe/disk KV tier in a Spark serve: production ran `--learn-conversations --learn-gib 128 --learn-daily-gib 512 --learn-min-free-gib 40`; the launcher kept it behind `LEARN=0` and only two purpose-built queues set it, so every screen and A/B described a serve nobody ships - comparable to production only at short prompts where nothing is kept, and not at long context, on a resume or across a restart. Promotion was the switch itself: default 1 in the launcher and in its forwarding driver, the launcher test rewritten, the sync gate green, an arm run with no override to capture the promoted shape.

## When writing the same rule into another repo

State the rule, the mechanics above, and the worked example; name the mechanisms (completeness, the verdict vocabulary, `dev.env` = `prod.env` plus candidates) rather than one repo's file paths, so an agent in a repo with a different layout can apply it without translating.
