#!/bin/bash
# prepare_kcache.sh <kit dir> <image> [source label]   (EVERY serve node, serve DOWN; the kit dir holds kcplan.py,
# prebuild.py, kcache-label and kcache-drop.txt from mkkit.py)
# The hunt image's compiled-kernel folder ~/.cache/tensorfold-glm53/<its tf.patches label>, then every GLM extension
# built or loaded in it through the image's own loaders (prebuild.py), so the first serve boot compiles nothing:
#   1. the label read from the image must be the kit's kcache-label and must differ from the source label (default
#      c2154670148a, v110sync6's): two images with different CUDA sources under one name in one folder load each
#      other's builds (torch rebuilds by file times alone);
#   2. seeded ONCE (marker .seeded-from-<source>): torch_extensions/ and triton/ of the source folder copied (nothing
#      else: the folder may also hold a KV tier), then every extension in kcache-drop.txt deleted from the copy (its
#      sources changed under the same name: the source folder's build is of the OLD sources), and any torch build
#      `lock` deleted from the copy (no build runs in a folder that does not exist yet). The folders are root-owned:
#      all of it runs in a throwaway container. A folder already there without the marker stops the script;
#   3. prebuild.py in the image (GPU) at /cache = that folder: READY / FAILED a line, exit 1 on any FAILED.
set -u
KIT=$(cd "${1:?kit dir}" && pwd) || exit 1
IMG=${2:?image}
SRC=${3:-c2154670148a}
KC=$HOME/.cache/tensorfold-glm53
die() { echo "FAIL $*"; exit 1; }
LABEL=$(docker image inspect -f '{{index .Config.Labels "tf.patches"}}' "$IMG") || die "no image $IMG"
KITLABEL=$(tr -d '\r\n' < "$KIT/kcache-label")
# the recipe's start.sh mounts ~/.cache/tensorfold-glm53/<tf.patches> only for a label of exactly 12 lowercase hex
# digits (anything else: the image id's folder), so a folder prepared under any other label is never used
[[ "$LABEL" =~ ^[0-9a-f]{12}$ ]] || die "$IMG's tf.patches label '$LABEL' is not 12 hex digits: start.sh would not use \
its folder (it falls back to the image id's); rebuild the image with the kit's label"
[[ "$KITLABEL" =~ ^[0-9a-f]{12}$ ]] || die "the kit's kcache-label '$KITLABEL' is not 12 hex digits (an old kit?)"
[ "$LABEL" = "$KITLABEL" ] || die "$IMG's label $LABEL is not the kit's $KITLABEL"
[ "$LABEL" != "$SRC" ] && [ "$LABEL" != c2154670148a ] || die "$IMG uses the base's label $LABEL itself"
[ -d "$KC/$SRC" ] || die "no source folder $KC/$SRC"
[ -z "$(docker ps -q --filter 'name=^glm53-flash-tf$')" ] || die "a serve is up (glm53-flash-tf): stop it first"
DROP=$(grep -v '^#' "$KIT/kcache-drop.txt" | tr -d '\r' | tr '\n' ' ')
for n in $DROP; do [[ "$n" =~ ^[A-Za-z0-9_]+$ ]] || die "bad extension name in kcache-drop.txt: $n"; done
echo "=== $(hostname): $IMG label $LABEL, seeded from $SRC, drop: ${DROP:-none}"
if [ ! -e "$KC/$LABEL/.seeded-from-$SRC" ]; then
  [ ! -e "$KC/$LABEL" ] || die "$KC/$LABEL exists but was not seeded by this script (a boot of $IMG before the seed?);
  remove it: docker run --rm -v $KC:/c --entrypoint rm $IMG -rf /c/$LABEL"
  docker run --rm --network none -v "$KC":/c --entrypoint sh "$IMG" -c "
    set -e
    echo 'source folder:'; du -sh /c/$SRC/* 2>/dev/null | sed 's/^/  /'
    rm -rf /c/$LABEL.seeding && mkdir /c/$LABEL.seeding
    for d in torch_extensions triton; do [ -d /c/$SRC/\$d ] && cp -a /c/$SRC/\$d /c/$LABEL.seeding/; done
    for n in $DROP; do
      if [ -d /c/$LABEL.seeding/torch_extensions/\$n ]; then rm -rf /c/$LABEL.seeding/torch_extensions/\$n; echo \"dropped \$n\"
      else echo \"drop \$n: not in the source folder (nothing to drop)\"; fi
    done
    find /c/$LABEL.seeding/torch_extensions -mindepth 2 -maxdepth 2 -name lock -print -delete 2>/dev/null | sed 's/^/removed stale lock /'
    touch /c/$LABEL.seeding/.seeded-from-$SRC
    mv /c/$LABEL.seeding /c/$LABEL
    echo 'seeded:'; ls /c/$LABEL/torch_extensions 2>/dev/null | sed 's/^/  /'" || die "seeding $KC/$LABEL"
else
  echo "already seeded from $SRC (marker present): prebuild only"
fi
docker run --rm --gpus all --network none -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$KC/$LABEL":/cache -v "$KIT":/kit:ro --entrypoint python3 "$IMG" /kit/prebuild.py
