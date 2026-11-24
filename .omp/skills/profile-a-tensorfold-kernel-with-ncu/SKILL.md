---
name: profile-a-tensorfold-kernel-with-ncu
description: "Profile one kernel of a TensorFold serve on the Sparks with ncu: WRAP0/XRUN0, launcher variables, metrics that a capture or kernel filter needs."
---

# profile-a-tensorfold-kernel-with-ncu

one skill: ncu-profile one kernel of the TensorFold serve

Merged from 4 skill(s): profile-a-serve-kernel-with-ncu-on-the-spark, profile-a-spark-serve-with-ncu, profile-a-tensorfold-kernel-with-ncu, profile-one-kernel-with-ncu-on-a-spark.

# Profiling one kernel of the serve with ncu, via the launcher

Measured 2026-11-22 on spark1-3, image `glm53-zig:m130a`, TP=3 serve.

## The launcher takes numbered variables, not bare ones

`zig-tp3.sh` forwards `WRAP0`/`XRUN0` to rank 0 only (`WRAP1`/`XRUN1`, `WRAP2`/`XRUN2` for the workers). A bare `WRAP=...` is silently ignored and the container comes up with only `tensorfold-native serve`, so the request succeeds and no profile appears. Verify with `docker inspect glm53-zig-r0 --format '{{.Args}}'`: the first word must be `ncu`.

## What works

WRAP0="ncu --target-processes all --replay-mode kernel --launch-count 1 -k regex:tf_exl3_prompt_gu --metrics dram__bytes_read.sum,lts__t_bytes.sum,gpu__time_duration.sum -o /out/prompt" \
    XRUN0="-v /tmp/ncu-exl3:/out --cap-add SYS_ADMIN" \
    IMAGE=glm53-zig:m130a KNOBS=dev bash zig-tp3.sh 4

`ncu` exists INSIDE the image at `/usr/local/bin/ncu`, not on the host, so the profile is written by the container and read with `docker run --rm -v /tmp/ncu-exl3:/out --entrypoint ncu IMAGE --import /out/prompt.ncu-rep --print-units base`.

`--cap-add SYS_ADMIN` in `XRUN0` is what lets the performance counters open.

## Metric availability on GB10 (sm_121)

- `dram__bytes_read.sum` / `dram__bytes_write.sum` come back `(!) n/a` for the EXL3 prompt kernels: the DRAM byte counters are not exposed here. Do not design a question that needs them.
- `lts__t_bytes.sum` and `gpu__time_duration.sum` work (measured 462,528 bytes and 14,048 ns on one launch).
- `ncu --query-metrics` returns nothing from inside the container, GPU attached or not, so availability is learned from a real profile.

## Two traps that cost a run each

- `-k regex:tf_exl3_prompt_` matches the FIRST kernel whose name matches, which was `tf_exl3_prompt_rotate` at 14 us, not `gu`. Anchor the pattern (`regex:tf_exl3_prompt_gu$`).
- A profiled boot is counters only: ncu serialises and replays kernels, so its timings and reply digests are not measurements. Take digests from an unprofiled boot beside it.

## The cold request that triggers the kernels

Upstream's `tools/bench_cache.py` takes `--prompt-file` (a JSON array of raw token ids) and `--expected-prompt-tokens`, not a size:

python3 -c "import json;d=json.load(open('prose33.json'));b=list(d[0]['ids']);i=list(b)
    while len(i)<8192: i.extend(b)
    json.dump(i[:8192],open('ids-8192.json','w'))"
    python3 tools-up/tools/bench_cache.py http://127.0.0.1:8300 MODEL --prompt-file ids-8192.json \
        --expected-prompt-tokens 8192 --require-cold --tokens 8 --repeats 1

The ids file from `prose33.json` has the key `ids` (not `prompt`); repeating it to the target length is fine for a counter run.

# Profiling a Spark serve with ncu

Measured 2026-11-22 on spark1 (GB10, sm_121, kindling spark-os), image `glm53-zig:m130a`, TP=3 serve on :8300.

## Launch

1. `ncu` is inside the image, not on the host: the wrap runs in the container, the report is imported with `docker run --rm -v OUT:/out --entrypoint ncu IMG --import /out/x.ncu-rep`.
2. The TP3 launcher reads `WRAP0`/`XRUN0` for rank 0. A plain `WRAP`/`XRUN` is ignored **silently**: the boot succeeds unprofiled and the output dir stays empty. Verify with `docker inspect glm53-zig-r0 --format '{{.Args}}'` before concluding anything.
3. `XRUN0` needs `-v HOST_OUT:/out --cap-add SYS_ADMIN` for the counters.
4. Anchor the kernel selection: `-k regex:tf_exl3_prompt_gu$`. A bare `-k regex:tf_exl3_prompt_` profiles the FIRST match, which was `rotate` at 14 us.
5. A profiled boot is counters only. `--replay-mode kernel` serialises kernels, so reply digests must come from an unprofiled boot beside it, and multi-rank boots may hit NCCL timeouts because rank 0 is slowed.

## What can actually be measured on this hardware

- `dram__bytes_read.sum` and `dram__bytes_write.sum` report `(!) n/a` on the GB10 for these kernels: a DRAM-vs-L2 question cannot be settled with a DRAM counter here. Use `lts__t_bytes.sum` (works) plus a plan-order argument.
- `ncu --query-metrics` returns nothing from inside a container, with or without `--gpus`; learn metric availability from a real profile.
- `gpu__time_duration.sum` works and is the launch's own duration.

## Client

A cold long-prompt request needs `bench_cache.py --prompt-file IDS.json` where IDS is a JSON array of token ids (not a size). Build one by repeating a bench prompt's `ids` array to the target length: `prose33.json` entries are `{name, ids, rendering}`. `--require-cold` proves the request was not a cache hit.

# Profile one TensorFold kernel with ncu on a Spark

Use when a kernel ranking needs its own counter (DRAM bytes against the HBM ceiling), not when a timing table will do.

1. **Rank-0 only.** `zig-tp3.sh` reads `WRAP0`/`XRUN0` for rank 0 and `WRAP1`/`XRUN1`, `WRAP2`/`XRUN2` for the workers. A plain `WRAP`/`XRUN` is ignored without a warning.
2. **Wrap the kernel by regex**, one launch, one output: `WRAP0="ncu --target-processes all --replay-mode kernel --launch-count 1 -k regex:<kernel> --metrics dram__bytes_read.sum,dram__bytes_write.sum,lts__t_bytes.sum,gpu__time_duration.sum -o /out/<name>"` and `XRUN0="-v /tmp/<dir>:/out --cap-add SYS_ADMIN"`. `ncu` lives in the image (/usr/local/bin/ncu), not on the host; the capability is what lets it read counters.
3. **Prove the wrap reached the container before sending a request:** `docker inspect glm53-zig-r0 --format '{{.Args}}'` must show `ncu` first. Without this check a run looks successful and leaves no report.
4. **Drive one cold request** with upstream's client: `python3 tools-up/tools/bench_cache.py http://127.0.0.1:8300 <model> --prompt-file ids.json --expected-prompt-tokens N --require-cold --tokens 8 --repeats 1`. Build `ids.json` as a JSON array of raw token ids of the wanted length (the bench prompt files are dicts with `name`, `ids`, `rendering`).
5. **Never take digests from a profiled boot:** `--replay-mode kernel` serialises kernels. Digests come from the unprofiled boot beside it.
6. Read the report with `ncu --import <dir>/<name>.ncu-rep --print-units base` and compare `dram__bytes_read.sum` against the bytes the kernel should move; a figure near the weights-once size means the second read was an L2 hit.

# Profile one kernel of the Zig GLM serve on a DGX Spark

Take a counter reading before writing a kernel against a cost story. Every step below cost a round trip the first time.

1. **The per-rank variables are `WRAP0`/`XRUN0` (and `WRAP1`/`XRUN1`, `WRAP2`/`XRUN2`).** `serve.sh` reads `WRAP`/`XRUN`, but `zig-tp3.sh` forwards only the numbered ones, so a bare `WRAP=` is silently ignored and the container comes up as `tensorfold-native serve`, which looks like a successful profile with no output. Verify by `docker inspect <container> --format '{{.Args}}'`: the `ncu ...` words must be there.

2. **`ncu` is inside the image, not on the host** (`/usr/local/bin/ncu`). Import a report with `docker run --rm -v <dir>:/out --entrypoint ncu <image> --import /out/x.ncu-rep --print-units base`.

3. **Counters need `--cap-add SYS_ADMIN` in the rank-0 docker args**, so `XRUN0="-v <hostdir>:/out --cap-add SYS_ADMIN"`.

4. **`-k regex:NAME` takes the FIRST matching kernel**, not the one you meant: `regex:tf_exl3_prompt_` profiled `tf_exl3_prompt_rotate` at 14 us. Anchor it (`regex:tf_exl3_prompt_gu$`) or accept whatever launches first.

5. **DRAM byte counters read `n/a` on the GB10 (sm_121)** for these kernels while `lts__t_bytes.sum` and `gpu__time_duration.sum` work. `ncu --query-metrics` returns nothing from inside the container with or without `--gpus all`, so availability is learned from a real profile only. A question phrased as "DRAM or L2" is therefore not answerable with a counter on this hardware; answer it from the placement code instead (see item 6).

6. **Placement beats counters for an L2 question.** Whether an expert's second weight block is an L2 hit is decided by reading the plan kernel: `place_items` writes items as `items + 3 * (ioff + j)` with experts ascending, so one expert's items are adjacent in the plan and CTAs dispatch x-fastest, putting them a few column blocks apart with megabytes between them.

7. **A profiled boot cannot produce digests.** `ncu` serialises and replays kernels, so exactness comes from an unprofiled boot beside it; say so in the receipt's header.

8. **Rank 0 profiling on a TP=3 serve works** as long as the request does not depend on the other ranks finishing: one cold prompt completed with qualified true under `--replay-mode kernel --launch-count 1`. Build the cold prompt as a JSON array of token ids (`--prompt-file`) and pass `--expected-prompt-tokens`; upstream's `bench_cache.py` takes no size argument.
