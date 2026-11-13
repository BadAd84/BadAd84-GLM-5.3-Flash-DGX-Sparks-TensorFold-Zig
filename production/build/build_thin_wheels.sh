#!/bin/bash
# build_thin_wheels.sh <tag> <base image> <files.tgz> <kcache label> <wheels dir> [paths to remove ...]   (EVERY node)
# scripts/glm53/v110/sync/build_thin.sh plus Python wheels: <wheels dir> (its *.whl checked against its SHA256SUMS
# first) is copied into the build context and installed into the image's Python with pip --no-index --no-deps, and
# `import orjson` must work, before the package import check. Everything else is build_thin.sh's: the files laid over
# the installed tensorfold, the paths removed, tf.patches=<kcache label>, and the same sha256 lines of every laid
# file (the installed wheel versions go on the "built ..." line, which the chain's comparison drops).
set -u
TAG=${1:?tag} BASE=${2:?base} TGZ=${3:?files.tgz} LABEL=${4:?kcache label} WHEELS=${5:?wheels dir}
shift 5
# the recipe's start.sh uses tf.patches as the kernel folder only when it is 12 lowercase hex digits (else the image
# id's folder): refuse any other label before building, and check the built image carries exactly this one
[[ "$LABEL" =~ ^[0-9a-f]{12}$ ]] || { echo "BUILD FAILED $TAG on $(hostname): label '$LABEL' is not 12 hex digits \
(start.sh would ignore it)"; exit 1; }
[ "$LABEL" != c2154670148a ] || { echo "BUILD FAILED $TAG on $(hostname): label $LABEL is the base's own folder"; exit 1; }
( cd "$WHEELS" && ls ./*.whl > /dev/null && sha256sum -c --quiet SHA256SUMS ) ||
  { echo "BUILD FAILED $TAG on $(hostname): wheels in $WHEELS do not match their SHA256SUMS"; exit 1; }
CTX=$(mktemp -d "$HOME/work/thin.XXXXXX") || exit 1
trap 'rm -rf "$CTX"' EXIT
mkdir -p "$CTX/files" && tar xzf "$TGZ" -C "$CTX/files" || exit 1
mkdir -p "$CTX/wheels" && cp "$WHEELS"/*.whl "$CTX/wheels/" || exit 1
RM="$*"
FILES=$(cd "$CTX/files" && find . -type f | sed 's#^\./##' | sort | tr '\n' ' ')
cat > "$CTX/Dockerfile" <<EOF
FROM $BASE
COPY files/ /usr/local/lib/python3.12/dist-packages/tensorfold/
COPY wheels/ /tmp/wheels/
RUN PIP_BREAK_SYSTEM_PACKAGES=1 python -m pip install --no-index --no-deps --no-cache-dir /tmp/wheels/*.whl && \\
    rm -rf /tmp/wheels && python -c "import orjson" && \\
    cd /usr/local/lib/python3.12/dist-packages/tensorfold && \\
    for p in $RM; do rm -f "\$p"; done && \\
    for p in $FILES $RM; do d=\$(dirname "\$p"); b=\$(basename "\$p" .py); rm -f "\$d/__pycache__/\$b".*.pyc; done && \\
    python -c "import tensorfold.cuda.server, tensorfold.families.glm5_next.cuda.engine, tensorfold.families.glm5_next.cuda.verify"
LABEL tf.patches=$LABEL
EOF
docker build -q -t "$TAG" "$CTX" >/dev/null || { echo "BUILD FAILED $TAG on $(hostname)"; exit 1; }
WV=$(docker run --rm --entrypoint python "$TAG" -c "import orjson; print('orjson', orjson.__version__)") ||
  { echo "BUILD FAILED $TAG on $(hostname): orjson does not import"; exit 1; }
GOT=$(docker image inspect -f '{{index .Config.Labels "tf.patches"}}' "$TAG")
[ "$GOT" = "$LABEL" ] && [[ "$GOT" =~ ^[0-9a-f]{12}$ ]] ||
  { echo "BUILD FAILED $TAG on $(hostname): the built image's tf.patches is '$GOT', not $LABEL"; exit 1; }
echo "built $TAG on $(hostname): $(docker image inspect -f '{{.Id}}' "$TAG" | cut -c8-19) label $GOT $WV"
docker run --rm --entrypoint sh "$TAG" -c "cd /usr/local/lib/python3.12/dist-packages/tensorfold && sha256sum $FILES | awk '{print substr(\$1, 1, 16), \$2}' && for p in $RM; do [ -e \"\$p\" ] && echo \"STILL THERE \$p\"; done; true"
