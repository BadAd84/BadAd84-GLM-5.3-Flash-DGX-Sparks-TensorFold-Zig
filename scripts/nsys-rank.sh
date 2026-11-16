#!/usr/bin/env bash
# nsys-rank.sh RANK TAG [P] - one decode cell with worker RANK (1 or 2) under Nsight Systems, then its per-kernel GPU time table.
# Same method as nsys-rank0.sh for the head: the serve boots through zig-tp3.sh with the profiled rank under `nsys launch` (WRAP<RANK>, XRUN<RANK>), one short warm cell,
# then one measured cell between `nsys start` and `nsys stop` run in that rank's container over ssh. The report is built on the worker (the image is there) and copied to the head.
# A GPU clock, power and temperature sample of the worker is taken once a second during the measured cell (nvidia-smi, first 12 seconds) into ~/nsys/TAG_smi.csv on the head.
# Output on the head: ~/nsys/<TAG>_cuda_gpu_kern_sum.csv and the ranked table on stdout. Env: IMAGE, KNOBS, DRAFTER, XENV, XSERVE as zig-tp3.sh; CTX (default 262144); TOKENS (default 400); KIND (default prose).
set -uo pipefail
RANK=${1:?usage: nsys-rank.sh RANK TAG [P]}; TAG=${2:?usage: nsys-rank.sh RANK TAG [P]}; P=${3:-1}
case $RANK in 1|2) ;; *) echo "nsys-rank.sh: RANK is 1 or 2 (rank 0 is nsys-rank0.sh)"; exit 2;; esac
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE=${IMAGE:?IMAGE is required}
host="adam@spark$((RANK + 1)).ots-int.net"
ctr="glm53-zig-r$RANK"
mkdir -p "$HOME/nsys"
ssh -n -o BatchMode=yes "$host" 'mkdir -p "$HOME/nsys"' || { echo "[nsys-rank] ssh to $host failed"; exit 1; }
export IMAGE
# cuda-sw: the default hardware trace fails in a container with CUPTI_ERROR_INSUFFICIENT_PRIVILEGES (no events)
export "WRAP$RANK=nsys launch --session-new=tf --trace=cuda-sw"
export "XRUN$RANK=-v $HOME/nsys:/out"
bash "$here/zig-tp3.sh" "$P" "${CTX:-262144}" || { echo "[nsys-rank] boot failed"; exit 1; }
cell() { python3 "$here/streams.py" 8300 "$P" --kind "${KIND:-prose}" --max-tokens "$1" --rounds 1 --tag "$2" 2>/dev/null | tail -1 | cut -c1-200; }
cell 64 "warm-$TAG" > /dev/null
ssh -n -o BatchMode=yes "$host" "docker exec $ctr nsys start --session=tf --sample=none --cpuctxsw=none -o /out/$TAG --force-overwrite=true" 2>&1 | tail -2
ssh -n -o BatchMode=yes "$host" "timeout 12 nvidia-smi --query-gpu=clocks.sm,clocks.mem,power.draw,temperature.gpu --format=csv,noheader -l 1" > "$HOME/nsys/${TAG}_smi.csv" 2>&1 &
smi=$!
cell "${TOKENS:-400}" "nsys-$TAG"
ssh -n -o BatchMode=yes "$host" "docker exec $ctr nsys stop --session=tf" 2>&1 | tail -2
wait "$smi" 2>/dev/null || true
echo "[nsys-rank] clock, power, temperature of rank $RANK during the cell (sm MHz, mem MHz, W, C): $(sort "$HOME/nsys/${TAG}_smi.csv" | uniq -c | sort -rn | head -3 | tr '\n' ';')"
bash "$here/zig-tp3-stop.sh" > /dev/null 2>&1 || true
ssh -n -o BatchMode=yes "$host" "docker run --rm --entrypoint nsys -v \$HOME/nsys:/out $IMAGE stats --report cuda_gpu_kern_sum --format csv -o /out/$TAG /out/$TAG.nsys-rep" > /dev/null 2>&1
scp -q -o BatchMode=yes "$host:nsys/${TAG}_cuda_gpu_kern_sum.csv" "$HOME/nsys/${TAG}_cuda_gpu_kern_sum.csv" < /dev/null
python3 "$here/nsys-kern.py" "$HOME/nsys/${TAG}_cuda_gpu_kern_sum.csv" 45
echo NSYS-DONE
