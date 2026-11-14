#!/usr/bin/env bash
# mailbox-fatbin.sh UPSTREAM_CLONE OUT.fatbin - the kernel image TF_GLM_ROCE_MULTI loads (TF_TP_KERNEL_IMAGE): fabric/tp's
# mailbox.cu at the pinned TF_REF, built for sm_121 the way zig/build/tp.zig builds it. The engine image does not install it, so
# put the output at ~/.cache/huggingface/tp_mailbox.fatbin on every host (serve.sh mounts that directory and looks for the file).
# NVCC defaults to nvcc on PATH; the build used CUDA 13.3 (13.1's crt headers clash with some glibc versions' rsqrt).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
. "$here/config.sh"
SRC=${1:?upstream clone}; OUT=$(realpath -m "${2:?output fatbin}")
NVCC=${NVCC:-nvcc}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/fabric/tp"
for f in mailbox.cu roce_device.cuh; do git -C "$SRC" show "$TF_REF:zig/src/fabric/tp/$f" > "$tmp/fabric/tp/$f"; done
"$NVCC" --version | tail -1
( cd "$tmp" && "$NVCC" -fatbin -O3 -std=c++17 -gencode=arch=compute_121,code=sm_121 -o "$OUT" fabric/tp/mailbox.cu )
sha256sum "$OUT"
