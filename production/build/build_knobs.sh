#!/usr/bin/env bash
# build_knobs.sh [base image] [tag] [patch folder] (each Spark): build the image the two rebased knobs need, by applying
# every patch in the folder to the base image's site-packages.
#
# A Dockerfile, not docker commit: commit records the CONTAINER's config, so a container started with --entrypoint sh
# produces an image whose entrypoint is sh, and the serve then runs the console script through a shell ("import: command
# not found", 2026-11-04). FROM the base keeps its entrypoint and command exactly as published.
set -eu
BASE=${1:-tensorfold-glm53:v110sync6}
TAG=${2:-tensorfold-glm53:v110sync6-knobs}
DIR=${3:-/home/adam/knob-patches}
[ -d "$DIR" ] || { echo "no patch folder $DIR"; exit 1; }
n=$(ls "$DIR"/*.patch 2>/dev/null | wc -l)
[ "$n" -gt 0 ] || { echo "no patches in $DIR"; exit 1; }
CTX=$(mktemp -d)
trap 'rm -rf "$CTX"' EXIT
cp "$DIR"/*.patch "$CTX"/
{
  # Stage 1, the check: the patched tree must not use a name it lacks (a ported hunk that calls a helper another lane
  # patch defines: copy_taps, 2026-11-04). pyflakes lives in this stage only, so the served image carries nothing extra
  # and its layer commands stay the ones already built (the cache gives the same image id).
  echo "FROM $BASE AS check"
  echo "COPY *.patch /p/"
  echo 'RUN cd /usr/local/lib/python3.12/dist-packages \'
  echo ' && for p in /p/*.patch; do patch -p0 --forward < "$p" > /dev/null; done \'
  echo ' && files=$(grep -hE "^\+\+\+ " /p/*.patch | awk "{print \$2}" | grep "\.py$" | sort -u) \'
  echo ' && (python3 -m pyflakes --version > /dev/null 2>&1 || pip install -q pyflakes) \'
  echo ' && if python3 -m pyflakes $files | grep -E "undefined name|syntax error"; then echo "a ported hunk uses a name this tree lacks"; exit 1; fi \'
  echo ' && echo "names ok: $(echo $files | wc -w) files"'
  # Stage 2, the image: the same layers as before the check existed, so a rebuild with the same patches yields the same
  # image id (the chain may be booting it).
  echo "FROM $BASE"
  echo "COPY *.patch /p/"
  echo 'RUN cd /usr/local/lib/python3.12/dist-packages \'
  echo ' && for p in /p/*.patch; do echo "applying $p"; patch -p0 --forward < "$p"; done \'
  echo ' && python3 -c "from tensorfold.families.glm5_next.cuda import dflash2_multi as m; from tensorfold.cuda import geometry; print(\"imports ok\", m.DRAFT_WIDE, geometry.pooled_pack())" \'
  echo ' && rm -rf /p'
} > "$CTX/Dockerfile"
echo "base $BASE, $n patches, tag $TAG"
docker build -q --target check -t "$TAG-check" "$CTX" > /dev/null || { echo "CHECK FAILED: the patched tree uses a name it lacks (docker build --target check $CTX for the lines)"; exit 1; }
docker rmi -f "$TAG-check" > /dev/null 2>&1
docker build -q -t "$TAG" "$CTX" > /dev/null
echo "built $TAG: $(docker images --format '{{.ID}}' "$TAG" | head -1), entrypoint $(docker inspect --format '{{.Config.Entrypoint}}' "$TAG")"
