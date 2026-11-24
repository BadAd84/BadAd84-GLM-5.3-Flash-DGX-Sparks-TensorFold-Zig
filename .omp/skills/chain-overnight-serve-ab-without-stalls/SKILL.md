---
name: chain-overnight-serve-ab-without-stalls
description: "Use when queueing several unattended serve A/B chains on the Spark triangle overnight: marker discipline, duplicate launches, two-image code A/Bs, and putting the decisive arm first."
---

# Chaining overnight serve A/Bs on the Spark triangle

When several A/Bs must run unattended (spark4-6, TP=3, `serve4.sh`, GPU lock `~/work/gpu.lock`), the failure modes
are all in the ORCHESTRATION, not the measurement. Every one below happened in a single night.

## Marker discipline: a waiter must grep a file the producer WRITES
`wait for X-CHAIN-DONE` only works if the producing chain actually writes that string. One chain waited on
`logs/DEFX3-CHAIN-DONE`, a file nothing ever created (the flipper touched `logs/FLIP-ITEMS-DONE` instead), so it would
have waited forever. Rule: for every waiter, open the producer and confirm the exact marker line, in the same pass.
Prefer `touch`ed marker files (`touch logs/FLIP-ITEMS-DONE`) over grepping a log's last echo, and grep with
`grep -q` on a file that exists (`2>/dev/null`), never on a glob.

## Launch exactly once, and verify by full command line
`(setsid nohup bash ./x-chain.sh > logs/x-chain.out 2>&1 &)` can run twice when the session shell is busy (the same
command line executed in a temporary shell). Two copies then both race the same marker. Always verify with
`pgrep -fax 'bash ./x-chain.sh'` (exact full command line) - `pgrep -f x-chain.sh` matches your own `bash -c` wrapper
and reports the launcher as a second copy.

## A code A/B needs a two-image runner
`pp-chain-ab.sh` takes ONE image and two XENV strings: it can only A/B a knob. For a code change, copy it to
`pp-img-ab.sh` with `IMG_A IMG_B` (and optional per-arm `XSERVE` extras), same ABBA cells. Comparing two arms of one
image after a code change silently measures nothing.

## Inspect the container while it is UP
`dec()`/`cell()` helpers stop the serve at the end (`stop3.sh`). A post-hoc
`docker inspect glmperf3-r0` then reports "no such object" and a grep of its env reads as "knobs MISSING" when they
were present. Check container state inside the boot window, or read the boot log's `[serve3] ... xenv=` line, which
prints the composed environment.

## Order by what decides the decision, not by what was queued first
A long serial accumulates: build -> gates -> A/B per chain. The last-queued chain can sit 10+ hours behind reference
boots and upstream verifications. Put the arm that decides the current release FIRST (kill and requeue its waiter
with an earlier marker); park nice-to-have proofs at the tail.

## Never flip a default mid-serial
A flip (`serve4.sh` DEFS sed) changes the base every later boot sees. Queue it behind a marker that only appears after
the whole serial (`QUEUE-CHAIN-DONE`, or the last two chains' DONE markers), then verify on each box with a `grep -c`
of the new knob in `~/glmperf/serve4.sh`.

## Keep disk ahead of the builds
Each image build plus a `docker pull` of a 25 GB reference image can take /home to zero; a 0-byte write then looks
like a probe failure. Check `df -h /home` before a build chain, prune `docker builder prune -f` (52 GB of cache was
recoverable in one call), and run `~/glmperf/diskguard.sh` (16 h) while chains are in flight.

## Read with the archiver, not the log tail
Every cell's numbers live in `~/perpatch-ai/run-*-<tag>/L*.json`; read them with `prod/perpatch_report.py --ref b`
(for an arm-on arm b: "+ = better with the arm"), and treat impossible percentages (-8,087%, -56,946%) as FAILED
CELLS, not speed. In one night that shape meant pad-off broke kept-state resume, not that the run was noisy.
