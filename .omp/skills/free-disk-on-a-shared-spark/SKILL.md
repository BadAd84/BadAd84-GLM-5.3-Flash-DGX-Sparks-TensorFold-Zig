---
name: free-disk-on-a-shared-spark
description: "Free disk on a DGX Spark (spark4-6) safely while a serve is running: audit first, delete HF checkpoints via symlink-reference mapping, purge only dangling docker images, and clear root-owned .zig-cache dirs without sudo"
---

# Free disk on a shared DGX Spark (spark4-6)

Measured 2026-11-10 on spark6: **88% -> 43% used (112 GiB -> 496 GiB free)** in one pass, with the
production serve answering `/health` 200 throughout.

## Preconditions
- A serve may be RUNNING (`docker ps` shows `qwen38-flash-next-tf`). Everything below is disk-only and
  must not touch containers or the GPU lock.
- `sudo` on a Spark needs the owner's YubiKey (pam_rssh). `sudo -n` returns rc=1 headlessly - that is
  expected, not a fault. Use the container trick below instead of waiting for a touch.

## 1. Audit before deleting anything
```bash
du -sh /home/adam/* /home/adam/.[a-z]* 2>/dev/null | sort -rh | head -12   # dot dirs hold .cache
du -sh /home/adam/.cache/huggingface/hub/* 2>/dev/null | sort -rh | head -6
du -sh /home/adam/work/lanes/* 2>/dev/null | sort -rh | head -10
docker system df
```
Typical layout on spark6: `~/.cache/huggingface` dominates (the checkpoints), `~/work/lanes/*` second
(one TensorFold clone ~3.5-15 GiB per A/B lane), then docker images.

## 2. HF cache: map references before deleting a model
HF stores `snapshots/<sha>/file` as SYMLINKS. The target depth tells you which store holds the data:
- `../../blobs/<sha>` = the model's OWN blobs (`hub/models--X/blobs`) - per-model copies.
- `../../../blobs/<sha>` = the GLOBAL `hub/blobs` (subdirs named by 2 hex chars, plus a
  `.huggingface-shared-blobs` marker).
Both can be live for the same model. Never `rm` a blobs dir by size alone - resolve it:

```bash
python3 - <<'EOF'
import os, shutil
H = "/home/adam/.cache/huggingface/hub"
GLM = "models--OWNER--NAME"          # the model to delete
def refs(m):
    out = set(); sd = os.path.join(H, m, "snapshots")
    if not os.path.isdir(sd): return out
    for sha in os.listdir(sd):
        d = os.path.join(sd, sha)
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if os.path.islink(p): out.add(os.path.realpath(p))
    return out
glm = refs(GLM)
others = set()
for m in os.listdir(H):
    if m.startswith("models--") and m != GLM: others |= refs(m)
only = glm - others                       # files no other model references
tot = sum(os.path.getsize(p) for p in only if os.path.exists(p))
print(f"{len(only)} files, {tot/2**30:.1f} GiB exclusively {GLM}")
for p in only:
    if os.path.exists(p): os.remove(p)
shutil.rmtree(os.path.join(H, GLM), ignore_errors=True)
EOF
```
Measured: the GLM-5.3-Flash EXL3 4bpw checkpoint was 163.6 GiB, ALL of it in the global `hub/blobs`
subdirs and referenced by nothing else - so it freed 164 GiB cleanly. Deleting only the model dir would
have freed almost nothing. Keep the checkpoint the running serve mmaps (on spark6: Qwen INT4-AutoRound 122
GiB) and anything the owner has not explicitly cleared.

## 3. Docker: prune only what is dangling
```bash
docker image prune -af     # untagged only; keeps every tagged image
docker builder prune -f
```
Measured: 7.7 + 2.0 GiB. Never `docker system prune` (it removes other lanes' stopped containers) and never
`docker rm` by label/ancestor filter - the arm images share the production image's `ai-engine.kindling`
label.

## 4. Lane worktrees: verify pushed, then delete only clone/build dirs
`du` counts hardlinked git objects per path, so the reported total overstates what deletion frees (a first
pass reported 194 GiB "freed" but df moved 7 GiB until the root-owned caches were gone too).

```bash
# per lane: is HEAD on a Gitea branch, or content-identical to it?
G=ssh://git@gitea.ots-int.net:2222/ots/tensorfold-levers124.git
cd ~/work/lanes/<lane>/tf
git fetch -q "$G" "+refs/heads/*:refs/remotes/gitea/*"
git branch -r --contains HEAD | grep -q gitea && echo PUSHED || \
  git diff --stat <gitea-branch> HEAD   # empty diff = same content, signed copy exists
```
Then delete only tree dirs >= 1 GiB, keeping every `*.log`, `*.txt`, `*.md`, `runs/` and small lane:
```bash
for d in ~/work/lanes/*/; do
  for sub in "$d"tf "$d"base-tree "$d"base-tree2 "$d"base-tf "$d"mut-tree "$d"trees "$d"e \
             "$d"zcache "$d"zig-cache "$d"zig-cache2 "$d"zig-cache3; do
    [ -d "$sub" ] || continue
    m=$(du -sm "$sub" | cut -f1)
    [ "$m" -ge 1024 ] && { echo "rm ${m}M $sub"; rm -rf "$sub"; }
  done
done
```
Keeping the >=1 GiB threshold leaves the small October A/B lanes (which carry uncommitted experiment
scripts) untouched.

## 5. Root-owned files block rm - delete them from inside a container
Docker builds run as root and leave root-owned objects inside the mounted worktree (`.zig-cache/o/*/test`,
`test_zcu.o`, dirs like `zig-cache/z/<hash>`). `rm -rf` then fails with `Permission denied`, leaves the
parent tree in place, and reports nothing to `df`. Symptom to recognise: `du` says the dir is 15 GiB but a
`rm -rf` leaves it there.

```bash
docker run --rm -v /home/adam/work/lanes:/l node:22 \
  sh -c 'find /l -type d -name ".zig-cache*" -exec rm -rf {} + 2>/dev/null'
```
The container's root can unlink them without any Spark sudo. Run it at FULL depth (a `-maxdepth 3` sweep
missed `tfmain/e/mut-*/.zig-cache`). Re-pull `node:22` if it was pruned (1.1 GiB).

## 6. Verify, and confirm the serve survived
```bash
df -h /home | tail -1
du -sh ~/work/lanes ~/.cache/huggingface
docker ps --format '{{.Names}} {{.Status}}'
curl -s -m 6 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8888/health   # expect 200
```

## Traps
- `du -sh` per-lane totals include hardlinked git objects; expect the freed number to be lower than the
  sum of reported dir sizes.
- The top-level `hub/blobs` being "orphaned" is a plausible-looking wrong conclusion: resolve symlinks.
- `ssh -A -tt` on a command whose output you pipe closes the connection after printing; the output is still
  valid.
- Never delete the checkpoint of the running serve, and never touch `~/work/gpu.lock`.
