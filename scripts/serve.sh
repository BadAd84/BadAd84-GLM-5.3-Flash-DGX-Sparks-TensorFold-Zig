#!/usr/bin/env bash
# serve.sh RANK P [CTX] - boot one rank of this recipe's serve from the image build-image.sh made.
#
# Rank-local on purpose: it starts one container on the host it runs on, with the rank, world
# size and NCCL bootstrap address given as parameters. Fleet orchestration (which host is which
# rank, and the inter-rank fabric) stays outside this repo until it is designed here.
#
# Env:
#   IMAGE     image to run (default glm53-zig:<short pin> as build-image.sh tags it)
#   PORT      rank 0's API port (default 8300)
#   WORLD     rank count (default 3)
#   COMM_ID   NCCL bootstrap host:port for rank 0 (required when WORLD > 1)
#   MODEL     model directory inside the container (default the recipe's EXL3 4bpw checkpoint)
#   RES       memory reserve GiB (default: 12.5 at P1, 14.5 at P2, 13.0 at P4, 6.5 above)
#   XSERVE    extra serve arguments; XENV extra -e arguments
#   KNOBS    off (default), measured or all: which of the recipe's knobs to enable
#
# The knob set is the one this recipe's patches implement, each of which was proved default-off
# and only becomes the recipe's default after its own A/B; NODEFS-style overrides are per knob
# through XENV, because every knob here is added only when XENV does not already name it.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
. "$here/config.sh"

RANK=${1:?rank}; P=${2:?parallel}; CTX=${3:-}
[[ -n "$CTX" ]] || { case $P in 1) CTX=1048576 ;; 8) CTX=196608 ;; *) CTX=262144 ;; esac; }
case $P in 1) RES=${RES:-12.5} ;; 2) RES=${RES:-14.5} ;; 4) RES=${RES:-13.0} ;; *) RES=${RES:-6.5} ;; esac

IMAGE=${IMAGE:-glm53-zig:${TF_REF:0:7}}
WORLD=${WORLD:-3}
PORT=${PORT:-8300}
MODEL=${MODEL:-/models/GLM-5.3-Flash-EXL3-4bpw-TensorFold}
XENV=${XENV:-}
[[ $WORLD = 1 || -n "${COMM_ID:-}" ]] || { echo "COMM_ID is required for WORLD>1" >&2; exit 1; }

KVFLAG=(--kv-cache fp8)
ENV=(-e HF_HUB_OFFLINE=1 -e TENSORFOLD_NO_UPDATE_CHECK=1 -e TENSORFOLD_MEMORY_RESERVE_GIB=$RES
 -e TF_GLM_RANK=$RANK -e TF_GLM_WORLD=$WORLD -e TF_GLM_COPY_MAX=15 -e TF_GLM_COPY_REPLY_MATCH=16
 -e TF_GLM_HEAD_BITS=8 -e TF_GLM_DENSE_BITS=4)
[[ -n "${COMM_ID:-}" ]] && ENV+=(-e NCCL_COMM_ID=$COMM_ID)
ENV+=(-e NCCL_P2P_DISABLE=1 -e NCCL_SHM_DISABLE=1 -e NCCL_MIN_NCHANNELS=4 -e NCCL_MAX_NCHANNELS=4
 -e NCCL_DEBUG=${NCCL_DEBUG:-WARN})

# The recipe's knobs: each patch in patches/engine/ adds one, and each is added only when XENV
# does not already name it, so an A/B arm can turn any of them off without editing this file.
DEFS="TF_GLM_KDA_PAD=1 TF_GLM_INDEX_CUDA=1 TF_GLM_OVN_ONE_CHUNK=1 TF_GLM_OVN_KEPT_WALK=1
 TF_GLM_OVN_DRAFT_ONEPASS=1 TF_GLM_OVN_DRAFT_DOWN4=1 TF_GLM_OVN_DRAFT_MLPSPLIT=4
 TF_GLM_OVN_REPLY_PREFILL=1 TF_GLM_OVN_MLA_FUSEMERGE=1 TF_GLM_OVN_GLUE_FUSE=1
 TF_GLM_OVN_INDEX_SCHED=1 TF_GLM_OVN_POOLS32=1 TF_GLM_OVN_INDEX_REGROUP=1
 TF_GLM_OVN_MM_WIDE=1 TF_GLM_OVN_SPARSE_ONEPASS=1 TF_GLM_OVN_ROUTER_WARM=1"
# Off by default: this recipe's own stack has not been A/B'd at 1/2/4/6/8 streams yet, and the
# rule here is that a knob is default-off until it is. KNOBS=measured opts into the set the
# source stack measured (ai-engine serve4.sh def17, production's probe, ABBA, every digest
# equal); KNOBS=all is the same list for an arm that means to test them all.
case "${KNOBS:-off}" in
  measured|all)
    for kv in $DEFS; do
      [[ " ${XENV:-} " == *" -e ${kv%%=*}="* ]] || XENV="${XENV:-} -e $kv"
    done ;;
  off) ;;
  *) echo "KNOBS must be off, measured or all" >&2; exit 2 ;;
esac
read -r -a XE <<< "${XENV:-}"; ENV+=("${XE[@]}")

RUN=(--gpus all --ipc=host --network host --shm-size 16g --cap-add IPC_LOCK
 --ulimit memlock=-1 --ulimit stack=67108864
 -v "$HOME/.cache/huggingface:/root/.cache/huggingface" -v "$(dirname "$MODEL"):$(dirname "$MODEL"):ro")
[[ $WORLD > 1 ]] && RUN+=(--device /dev/infiniband)

SERVE=(tensorfold-native serve "$MODEL" --context "$CTX" --parallel "$P" --max-tokens 32768
 --top-k 20 --backend cuda "${KVFLAG[@]}")
read -r -a XS <<< "${XSERVE:-}"; SERVE+=("${XS[@]}")
[[ $RANK = 0 ]] && SERVE+=(--host 0.0.0.0 --port "$PORT" --name GLM-5.3-Flash-EXL3)

echo "[serve] $(date -Is) $IMAGE rank=$RANK world=$WORLD P=$P ctx=$CTX res=$RES"
exec docker run --rm --name "glm53-zig-r$RANK" "${RUN[@]}" "${ENV[@]}" "$IMAGE" "${SERVE[@]}"
