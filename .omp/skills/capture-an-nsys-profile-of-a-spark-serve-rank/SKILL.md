---
name: capture-an-nsys-profile-of-a-spark-serve-rank
description: "Use when taking an nsys capture of one rank of the TensorFold serve on a DGX Spark: WRAP0/XRUN0, --trace=cuda-sw, cache drop before the boot, and the StringIds join every per-kernel query needs."
---

# Taking an nsys capture of one rank of the TensorFold serve

## Wrap only rank 0

The TP3 launcher passes per-rank profiler variables: `WRAP0` and `XRUN0` for rank 0 (`WRAP1`/`XRUN1`, `WRAP2`/`XRUN2` for the others). A plain `WRAP`/`XRUN` is silently ignored by `zig-tp3.sh` and the boot comes up unprofiled, which looks like a capture that produced nothing. Verify with `docker inspect glm53-zig-r0 --format '{{.Args}}'`: it must begin with the wrapper.

## Software CUDA tracing, always

Use `--trace=cuda-sw`. The default hardware trace fails inside this container (CUPTI privilege) and the capture then contains no `CUPTI_ACTIVITY_KIND_KERNEL` at all, with a diagnostic that says `Hardware tracing used for CUDA tracing` and about ten CUPTI events. The repo's own `scripts/nsys-rank.sh` and `scripts/nsys-rank0.sh` record the same failure; `scripts/nsys-prefill.sh` is the prefill driver and already does it right.

## Drop the page cache before the boot

A boot after a boot refuses the checkpoint on the memory preflight. Run `docker run --rm --privileged --entrypoint sh IMAGE -c 'sync; echo 3 > /proc/sys/vm/drop_caches'` on all three boxes first and confirm `MemAvailable` rose.

## Start and stop inside the container

    WRAP0="nsys launch --session-new=pf --trace=cuda-sw" XRUN0="-v $HOME/nsys:/out" IMAGE=... KNOBS=... bash zig-tp3.sh 4 1048576
    docker exec glm53-zig-r0 nsys start --session=pf --sample=none --cpuctxsw=none -o /out/pf --force-overwrite=true
    ... the work to capture ...
    docker exec glm53-zig-r0 nsys stop --session=pf

`nsys stop` is the flush. Stopping or removing the container instead leaves an empty or absent report.

## Export and query

    docker run --rm -v <dir>:/out --entrypoint nsys IMAGE export --type sqlite --force-overwrite true -o /out/r.sqlite /out/r.nsys-rep

Then, and this is the query that silently fails: `shortName` is a foreign key into `StringIds`.

    select s.value, count(*), sum(k.end-k.start)/1e6 as ms
    from CUPTI_ACTIVITY_KIND_KERNEL k join StringIds s on s.id = k.shortName
    group by s.value order by ms desc limit 16

Without the join the names come back as bare integers and any `like '%absorb%'` filter matches nothing while looking like a finding.

## Compare only matched workloads

The capture is only comparable with another taken at the same sizes and the same warm-chain settings. `scripts/nsys-prefill.sh`'s `SIZES` and `WARMCHAIN` change the total kernel time by several seconds, so check both before putting two tables side by side.

## Directory ownership

A container that creates the mount directory makes it root-owned, and the host account then cannot delete or replace files in it. Create it as the host account first, and use a fresh directory per attempt.
