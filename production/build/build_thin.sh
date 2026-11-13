#!/bin/bash
# build_thin.sh <tag> <base image> <files.tgz> <kcache label> [paths to remove ...]   (run on EVERY node of the serve)
# A thin image: <base> with the package files in <files.tgz> (paths relative to the tensorfold package) laid over its
# installed tensorfold, the listed package paths removed and their bytecode dropped, and tf.patches=<kcache label> so
# start.sh mounts the compiled-kernel folder of that key (the CUDA extension sources must be the base's). Prints the
# sha256 of every laid file inside the built image, for comparing the nodes.
set -u
TAG=${1:?tag} BASE=${2:?base} TGZ=${3:?files.tgz} LABEL=${4:?kcache label}
shift 4
CTX=$(mktemp -d "$HOME/work/thin.XXXXXX") || exit 1
trap 'rm -rf "$CTX"' EXIT
mkdir -p "$CTX/files" && tar xzf "$TGZ" -C "$CTX/files" || exit 1
RM="$*"
FILES=$(cd "$CTX/files" && find . -type f | sed 's#^\./##' | sort | tr '\n' ' ')
cat > "$CTX/Dockerfile" <<EOF
FROM $BASE
COPY files/ /usr/local/lib/python3.12/dist-packages/tensorfold/
RUN cd /usr/local/lib/python3.12/dist-packages/tensorfold && \\
    for p in $RM; do rm -f "\$p"; done && \\
    for p in $FILES $RM; do d=\$(dirname "\$p"); b=\$(basename "\$p" .py); rm -f "\$d/__pycache__/\$b".*.pyc; done && \\
    python -c "import tensorfold.cuda.server, tensorfold.families.glm5_next.cuda.engine, tensorfold.families.glm5_next.cuda.verify"
LABEL tf.patches=$LABEL
EOF
docker build -q -t "$TAG" "$CTX" >/dev/null || { echo "BUILD FAILED $TAG on $(hostname)"; exit 1; }
echo "built $TAG on $(hostname): $(docker image inspect -f '{{.Id}}' "$TAG" | cut -c8-19) label $(docker image inspect -f '{{index .Config.Labels "tf.patches"}}' "$TAG")"
docker run --rm --entrypoint sh "$TAG" -c "cd /usr/local/lib/python3.12/dist-packages/tensorfold && sha256sum $FILES | awk '{print substr(\$1, 1, 16), \$2}' && for p in $RM; do [ -e \"\$p\" ] && echo \"STILL THERE \$p\"; done; true"
