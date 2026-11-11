#!/usr/bin/env bash
# nsys-rank0.sh TAG [P] - one decode cell with rank 0 under Nsight Systems, then its per-kernel GPU time table.
# Boots through zig-tp3.sh (so the profiled rank has exactly the serve's env) with rank 0 under `nsys launch`,
# warms the serve with one short cell, then collects only one measured cell between `nsys start` and
# `nsys stop`: the stop is what flushes the CUDA trace (stopping the container instead leaves it empty).
# Output on the head: ~/nsys/<TAG>.nsys-rep, <TAG>_cuda_gpu_kern_sum.csv and the ranked table on stdout.
# Env: IMAGE, KNOBS, DRAFTER, XENV, XSERVE as zig-tp3.sh; TOKENS (default 400); KIND (default prose).
set -uo pipefail
TAG=${1:?usage: nsys-rank0.sh TAG [P]}; P=${2:-1}
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE=${IMAGE:-glm53-zig:fix4}
mkdir -p "$HOME/nsys"
export IMAGE
# cuda-sw: the default hardware trace fails in a container with CUPTI_ERROR_INSUFFICIENT_PRIVILEGES (no events)
export WRAP0="nsys launch --session-new=tf --trace=cuda-sw"
export XRUN0="-v $HOME/nsys:/out"
bash "$here/zig-tp3.sh" "$P" 262144 || { echo "[nsys] boot failed"; exit 1; }
cell() { python3 "$here/streams.py" 8300 "$P" --kind "${KIND:-prose}" --max-tokens "$1" --rounds 1 --tag "$2" 2>/dev/null | tail -1 | cut -c1-200; }
cell 64 "warm-$TAG" >/dev/null
docker exec glm53-zig-r0 nsys start --session=tf --sample=none --cpuctxsw=none -o "/out/$TAG" --force-overwrite=true 2>&1 | tail -2
cell "${TOKENS:-400}" "nsys-$TAG"
docker exec glm53-zig-r0 nsys stop --session=tf 2>&1 | tail -2
docker logs glm53-zig-r0 2>&1 | grep -a "ms a round\|tokens a round" | tail -3
bash "$here/zig-tp3-stop.sh" >/dev/null 2>&1 || true
docker run --rm --entrypoint nsys -v "$HOME/nsys:/out" "$IMAGE" stats --report cuda_gpu_kern_sum --format csv -o "/out/$TAG" "/out/$TAG.nsys-rep" >/dev/null 2>&1
python3 "$here/nsys-kern.py" "$HOME/nsys/${TAG}_cuda_gpu_kern_sum.csv" 45
echo NSYS-DONE
