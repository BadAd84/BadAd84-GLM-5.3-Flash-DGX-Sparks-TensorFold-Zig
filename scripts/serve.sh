#!/usr/bin/env bash
# serve.sh RANK P [CTX] - boot one rank of this recipe's serve from the image build-image.sh made.
#
# Rank-local on purpose: it starts one container on the host it runs on, with the rank, world
# size and NCCL bootstrap address given as parameters. Fleet orchestration (which host is which
# rank, and the inter-rank fabric) is a separate driver (zig-tp3.sh on the head).
#
# Env:
#   IMAGE     image to run (default glm53-zig:<short pin> as build-image.sh tags it)
#   PORT      rank 0's API port (default 8300)
#   WORLD     rank count (default 3)
#   COMM_ID   NCCL bootstrap host:port for rank 0 (required when WORLD > 1)
#   MODEL     model path INSIDE the container (default the EXL3 4bpw snapshot; the whole HF cache
#             is mounted at /root/.cache/huggingface, so snapshots' blob symlinks resolve)
#   DRAFTER   1 (default) loads the DFlash2 drafter at 4 bits; 0 runs the MTP head instead
#   RES       memory reserve GiB (default: 12.5 at P1, 14.5 at P2, 13.0 at P4, 6.5 above)
#   XSERVE    extra serve arguments; XENV extra -e arguments
#   KNOBS    off (default), measured or all: which of the recipe's knobs to enable
#
# The env block mirrors the production stack's shape (ai-engine serve4.sh measured set: P2P and
# SHM off, 4 channels, cross-NIC routing, LAN socket name) so a Zig boot and a production boot are
# comparable; the drafter default does the same. The knob set is the one this recipe's patches
# implement, each proved default-off until its own A/B; per-knob overrides go through XENV.
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
MODEL=${MODEL:-/root/.cache/huggingface/hub/models--Mia-AiLab--GLM-5.3-Flash-EXL3-4bpw-TensorFold/snapshots/078455ffe6472f9a52fbc1139f58b9db2881b25c}
DFLASH=/root/.cache/huggingface/hub/models--incoai--GLM-5.3-Flash-DFlash2/snapshots/bf582e4eacc1810f76656d1811693ff6c6737d2a
XENV=${XENV:-}
[[ $WORLD = 1 || -n "${COMM_ID:-}" ]] || { echo "COMM_ID is required for WORLD>1" >&2; exit 1; }

KVFLAG=(--kv-cache fp8)
ENV=(-e HF_HUB_OFFLINE=1 -e TENSORFOLD_NO_UPDATE_CHECK=1 -e TENSORFOLD_MEMORY_RESERVE_GIB=$RES
 -e TF_GLM_RANK=$RANK -e TF_GLM_WORLD=$WORLD -e TF_GLM_COPY_MAX=15 -e TF_GLM_COPY_REPLY_MATCH=16
 -e TF_GLM_HEAD_BITS=8 -e TF_GLM_DENSE_BITS=4)
[[ -n "${COMM_ID:-}" ]] && ENV+=(-e NCCL_COMM_ID=$COMM_ID)
# The proven production/ai-engine NCCL shape (same HCA names and GID 3 on spark1-3, from
# start-tp3.sh's own launcher output): P2P and SHM off, 4 channels, cross-NIC, subnet-aware
# routing, all four RoCE HCAs, LAN bootstrap.
ENV+=(-e NCCL_P2P_DISABLE=1 -e NCCL_SHM_DISABLE=1 -e NCCL_MIN_NCHANNELS=4 -e NCCL_MAX_NCHANNELS=4
 -e NCCL_CROSS_NIC=1 -e NCCL_IB_SUBNET_AWARE_ROUTING=1 -e NCCL_IB_GID_INDEX=3
 -e NCCL_IB_HCA="${NCCL_IB_HCA:-roceP2p1s0f0,roceP2p1s0f1,rocep1s0f0,rocep1s0f1}"
 -e NCCL_SOCKET_IFNAME=${NCCL_SOCKET_IFNAME:-enP7s7})
# NCCL_DEBUG is deliberately NOT set: with it unset the engine captures NCCL's own INFO into a private
# file and parses it for its transport report. A user value still wins (pass it through XENV).
[[ -n "${NCCL_DEBUG:-}" ]] && ENV+=(-e NCCL_DEBUG=$NCCL_DEBUG)

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
 -v "$HOME/.cache/huggingface:/root/.cache/huggingface")
[[ $WORLD > 1 ]] && RUN+=(--device /dev/infiniband)

SERVE=(tensorfold-native serve "$MODEL" --context "$CTX" --parallel "$P" --max-tokens 32768
 --top-k 20 --backend cuda "${KVFLAG[@]}")
[[ "${DRAFTER:-1}" = 1 && "$XSERVE" != *--drafter* ]] && SERVE+=(--drafter "$DFLASH" --drafter-bits 4)
read -r -a XS <<< "${XSERVE:-}"; SERVE+=("${XS[@]}")
[[ $RANK = 0 ]] && SERVE+=(--host 0.0.0.0 --port "$PORT" --name GLM-5.3-Flash-EXL3)

echo "[serve] $(date -Is) $IMAGE rank=$RANK world=$WORLD P=$P ctx=$CTX res=$RES"
echo "[serve] exec docker run ${RUN[*]} ${ENV[*]} $IMAGE ${SERVE[*]}"
# Detached on purpose: an attached `docker run` ties the engine's stdout to this shell, and when the
# launching session ends the broken pipe stops every rank (measured: "rank 0: rank N stopped"). With -d the
# log goes to the docker log driver and the serve outlives every session. Logs: docker logs glm53-zig-r$RANK.
RM=(--rm); [[ "${KEEP:-0}" = 1 ]] && RM=()  # KEEP=1 keeps the container and its docker log after a crash
docker run -d "${RM[@]}" --name "glm53-zig-r$RANK" "${RUN[@]}" "${ENV[@]}" "$IMAGE" "${SERVE[@]}" >/dev/null
echo "[serve] glm53-zig-r$RANK started (docker logs glm53-zig-r$RANK)"
