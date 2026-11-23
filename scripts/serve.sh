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
#   LEARN     1 (default; promoted 2026-11-23, the tier production runs) or 0: conversation states kept on disk, every
#             rank's part (upstream PR #1411, patches/pr1411): adds
#             --learn-conversations --learn-dir /root/.cache/huggingface/glm53-zig-learn/$LEARN_NAME (a subdirectory of the mounted cache,
#             so each rank writes its own host's disk) with --learn-gib $LEARN_GIB (128), --learn-daily-gib $LEARN_DAILY_GIB (512) and
#             --learn-min-free-gib $LEARN_MIN_FREE_GIB (40); LEARN_NAME defaults to serve. Left alone when XSERVE already names
#             --learn-conversations, as scripts/queue-disk-tier.sh does.
#   WRAP      command words run in front of the engine (a profiler: "nsys profile -o /out/r0 --trace=cuda
#             --sample=none"); XRUN extra docker run arguments (the profiler's output mount)
#   KNOBS    off (default), measured (also prod, all) or dev: which environment file to apply (scripts/env/prod.env, scripts/env/dev.env)
#   DRYRUN   1 prints the docker command and exits, starting nothing
#
# The runtime section of both environment files mirrors the production stack's shape (ai-engine serve4.sh measured set: P2P and
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
XSERVE=${XSERVE:-}
[[ $WORLD = 1 || -n "${COMM_ID:-}" ]] || { echo "COMM_ID is required for WORLD>1" >&2; exit 1; }

KVFLAG=(--kv-cache fp8)
# The values of the serve's environment are two complete files: scripts/env/prod.env (production: a runtime section, then the adopted recipe)
# and scripts/env/dev.env (production plus the candidates under test). KNOBS picks the file and how much of it: off is the runtime section of
# prod.env alone (an arm that names its own knobs through XENV), measured (or prod, or all) is prod.env whole, dev is dev.env whole. Only what
# depends on the boot is set here: the memory reserve, rank, world and NCCL_COMM_ID. A name the caller passes through XENV wins over its line
# in the file, so an A/B arm can change or turn off any setting without editing a file; a caller's own NCCL_IB_HCA or NCCL_SOCKET_IFNAME in
# the launching environment wins as well.
ENV=(-e TENSORFOLD_MEMORY_RESERVE_GIB=$RES -e TF_GLM_RANK=$RANK -e TF_GLM_WORLD=$WORLD)
[[ -n "${COMM_ID:-}" ]] && ENV+=(-e NCCL_COMM_ID=$COMM_ID)
CALLER_WINS=" NCCL_IB_HCA NCCL_SOCKET_IFNAME "
# envfile ENV SECTION...: `-e NAME=value` onto ENV for each line of scripts/env/ENV.env's named sections (runtime, recipe, candidates); a section
# starts at its `# --- NAME` line. A line is NAME=value with no space in the value, or blank, or a # comment.
envfile() {
  local f="$here/env/$1.env" sec=runtime want=" ${*:2} " line name val
  [[ -r $f ]] || { echo "serve.sh: no $f" >&2; exit 2; }
  while IFS= read -r line || [[ -n $line ]]; do
    line=${line#"${line%%[![:space:]]*}"}
    if [[ $line =~ ^"# --- "(runtime|recipe|candidates)([[:space:]]|$) ]]; then sec=${BASH_REMATCH[1]}; continue; fi
    [[ -z $line || $line == \#* ]] && continue
    [[ $want == *" $sec "* ]] || continue
    line=${line%% #*}; line=${line%"${line##*[![:space:]]}"}
    [[ $line =~ ^([A-Za-z_][A-Za-z0-9_]*)=([^[:space:]]*)$ ]] || { echo "serve.sh: bad line in $f: $line" >&2; exit 2; }
    name=${BASH_REMATCH[1]}; val=${BASH_REMATCH[2]}
    # A blank value is a decision, never an omission: it is the row's own "no value" default (prod.env's header), so nothing is
    # passed and the engine sees the setting absent exactly as the row documents. It must not become `-e NAME=`, a present empty
    # setting, which would also override the rank, world and memory reserve this script computes above.
    [[ -z $val ]] && continue
    [[ " ${XENV:-} " == *" -e $name="* ]] && continue
    if [[ $CALLER_WINS == *" $name "* && -n "${!name:-}" ]]; then val=${!name}; fi
    ENV+=(-e "$name=$val")
  done < "$f"
}
case "${KNOBS:-off}" in
  off) envfile prod runtime ;;
  measured|prod|all) envfile prod runtime recipe ;;
  dev) envfile dev runtime recipe candidates ;;
  *) echo "KNOBS must be off, measured (or prod, all) or dev" >&2; exit 2 ;;
esac
# NCCL_DEBUG is deliberately NOT set: with it unset the engine captures NCCL's own INFO into a private
# file and parses it for its transport report. A user value still wins (pass it through XENV).
[[ -n "${NCCL_DEBUG:-}" ]] && ENV+=(-e NCCL_DEBUG=$NCCL_DEBUG)
# TF_GLM_ROCE_MULTI: v1.2.7's own three-rank RoCE wire for the small all-gathers (ports paired by shared subnet). Measured against the
# same image without it, order ctl, on, on, ctl: +1.8 / +1.4 / +1.6% at 1 / 2 / 4 streams, +0.1% at 6, -0.5% at 8
# (docs/OVERNIGHT-2026-11-12.md section 21), so it comes with the measured set only up to 4 streams, which is a boot-time setting.
# It needs the mailbox kernel image on every host (scripts/mailbox-fatbin.sh builds it); without it the boot stays on NCCL.
if [[ "${KNOBS:-off}" != off && $WORLD -gt 1 && $P -le 4 && " ${XENV:-} " != *" -e TF_GLM_ROCE_MULTI="* ]]; then
  if [[ -f "$HOME/.cache/huggingface/tp_mailbox.fatbin" ]]; then
    XENV="${XENV:-} -e TF_GLM_ROCE_MULTI=1 -e TF_TP_MASTER=${COMM_ID%%:*} -e TF_TP_KERNEL_IMAGE=/root/.cache/huggingface/tp_mailbox.fatbin"
  else
    echo "serve.sh: no ~/.cache/huggingface/tp_mailbox.fatbin on this host (scripts/mailbox-fatbin.sh builds it): booting on NCCL" >&2
  fi
fi
read -r -a XE <<< "${XENV:-}"; ENV+=("${XE[@]}")

RUN=(--gpus all --ipc=host --network host --shm-size 16g --cap-add IPC_LOCK
 --ulimit memlock=-1 --ulimit stack=67108864
 -v "$HOME/.cache/huggingface:/root/.cache/huggingface")
[[ $WORLD > 1 ]] && RUN+=(--device /dev/infiniband)

SERVE=(tensorfold-native serve "$MODEL" --context "$CTX" --parallel "$P" --max-tokens 32768
 --top-k 20 --backend cuda "${KVFLAG[@]}")
[[ "${DRAFTER:-1}" = 1 && "$XSERVE" != *--drafter* ]] && SERVE+=(--drafter "$DFLASH" --drafter-bits 4)
if [[ "${LEARN:-1}" = 1 && "${XSERVE:-}" != *--learn-conversations* ]]; then
  SERVE+=(--learn-conversations --learn-dir "/root/.cache/huggingface/glm53-zig-learn/${LEARN_NAME:-serve}"
    --learn-gib "${LEARN_GIB:-128}" --learn-daily-gib "${LEARN_DAILY_GIB:-512}" --learn-min-free-gib "${LEARN_MIN_FREE_GIB:-40}")
elif [[ "${LEARN:-1}" != 0 && "${LEARN:-1}" != 1 ]]; then
  echo "serve.sh: LEARN must be 0 or 1, got '${LEARN}'" >&2; exit 2
fi
read -r -a XS <<< "${XSERVE:-}"; SERVE+=("${XS[@]}")
[[ $RANK = 0 ]] && SERVE+=(--host 0.0.0.0 --port "$PORT" --name GLM-5.3-Flash-EXL3)
read -r -a XR <<< "${XRUN:-}"; RUN+=("${XR[@]}")
read -r -a WR <<< "${WRAP:-}"

echo "[serve] $(date -Is) $IMAGE rank=$RANK world=$WORLD P=$P ctx=$CTX res=$RES"
echo "[serve] exec docker run ${RUN[*]} ${ENV[*]} $IMAGE ${SERVE[*]}"
[[ "${DRYRUN:-0}" = 1 ]] && exit 0
# Detached on purpose: an attached `docker run` ties the engine's stdout to this shell, and when the
# launching session ends the broken pipe stops every rank (measured: "rank 0: rank N stopped"). With -d the
# log goes to the docker log driver and the serve outlives every session. Logs: docker logs glm53-zig-r$RANK.
RM=(--rm); [[ "${KEEP:-0}" = 1 ]] && RM=()  # KEEP=1 keeps the container and its docker log after a crash
docker run -d "${RM[@]}" --name "glm53-zig-r$RANK" "${RUN[@]}" "${ENV[@]}" "$IMAGE" "${WR[@]}" "${SERVE[@]}" >/dev/null
echo "[serve] glm53-zig-r$RANK started (docker logs glm53-zig-r$RANK)"
