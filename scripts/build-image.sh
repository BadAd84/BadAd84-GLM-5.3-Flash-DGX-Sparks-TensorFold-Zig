#!/usr/bin/env bash
# build-image.sh TAG SRC.tar   (on a dev Spark)
# Recipe: the tree is what scripts/apply.sh produced; pack it with
#   tar -C <work-dir>/tree --exclude .git -cf <work-dir>/src.tar .
# Migrated from the ai-engine engine build script (same Dockerfile, same compile flags); the
# image namespace is this recipe's and the input tree is apply.sh's output.
# It takes the GPU lock on the dev Sparks as the original does, because a build shares their
# memory bandwidth with running benchmarks.
#
# Build glm53-zig:TAG from this recipe's source tree (made by apply.sh, packed with `tar -C ARM -cf SRC.tar .`):
# the PyTorch image's CUDA toolchain + Zig, `zig build fatbins install native` into /opt/tensorfold, the engine
# binaries and fatbins only (model kits, weights and launchers come from the model's serve config).
# Takes the GPU lock like every job on spark4-6, although the build itself runs no GPU work: it shares the
# boxes' memory bandwidth with benchmarks. Log: build-TAG.log beside SRC.tar.
set -euo pipefail
TAG=${1:?usage: build-image.sh TAG SRC.tar}; SRC=$(readlink -f "${2:?usage: build-image.sh TAG SRC.tar}")
BASE_IMAGE=${BASE_IMAGE:-nvcr.io/nvidia/pytorch:26.07-py3}
ZIG_VERSION=${ZIG_VERSION:-0.17.0}
ZIG_SHA256=${ZIG_SHA256:-9e8d11661d4ae3bd57702a3832781e23ad151dde5798e16a5ccd503f65234ff8}  # aarch64-linux
OPTIMIZE=${OPTIMIZE:-fast}
ctx=$(mktemp -d "$(dirname "$SRC")/ctx.XXXXXX"); trap 'rm -rf -- "$ctx"' EXIT
cp "$SRC" "$ctx/src.tar"
exec > >(tee "$(dirname "$SRC")/build-$TAG.log") 2>&1
src_sha=$(sha256sum < "$SRC" | cut -d' ' -f1)
echo "glm53-zig:$TAG src.tar sha256 $src_sha (label glm53-zig.src-sha256=${src_sha:0:16}) from $SRC"
mkdir -p ~/work
flock -o ~/work/gpu.lock docker build -t "glm53-zig:$TAG" --label "glm53-zig.src-sha256=${src_sha:0:16}" \
  --build-arg BASE_IMAGE="$BASE_IMAGE" --build-arg ZIG_VERSION="$ZIG_VERSION" --build-arg ZIG_SHA256="$ZIG_SHA256" \
  --build-arg OPTIMIZE="$OPTIMIZE" -f - "$ctx" <<'DOCKERFILE'
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS build
ARG ZIG_VERSION
ARG ZIG_SHA256
RUN curl -fsSL -o /tmp/zig.tar.xz "https://ziglang.org/download/${ZIG_VERSION}/zig-aarch64-linux-${ZIG_VERSION}.tar.xz" && \
    echo "${ZIG_SHA256}  /tmp/zig.tar.xz" | sha256sum -c - && \
    mkdir -p /opt/zig && tar -xJf /tmp/zig.tar.xz -C /opt/zig --strip-components=1 && rm /tmp/zig.tar.xz
COPY src.tar /tmp/src.tar
RUN mkdir /tensorfold && tar -xf /tmp/src.tar -C /tensorfold && rm /tmp/src.tar
ARG OPTIMIZE
RUN cd /tensorfold && /opt/zig/zig build -Dnvcc=/usr/local/cuda/bin/nvcc -Dsm=121 -Doptimize=${OPTIMIZE} \
      --prefix /opt/tensorfold -j"$(nproc)" fatbins install native && test -x /opt/tensorfold/native/bin/tensorfold-native
FROM ${BASE_IMAGE}
COPY --from=build /opt/tensorfold /opt/tensorfold
ENV PATH=/opt/tensorfold/native/bin:/opt/tensorfold/bin:${PATH}
DOCKERFILE
echo "BUILT glm53-zig:$TAG"
