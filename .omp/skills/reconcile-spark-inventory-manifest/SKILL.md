---
name: reconcile-spark-inventory-manifest
description: "Use when images, tarballs or caches were added to spark1-3 by queues or builds and each box's ~/INVENTORY.md must match what is installed; not for first-time baseline provisioning."
---

Fleet rule: every Spark's `~/INVENTORY.md` is a current-state teardown manifest (what WE put on the box, exact removal command, no history). Queues build and copy docker images without touching it, so it drifts (measured 2026-11-21: each box held 20 `glm53-zig` images, the manifest listed 6). Reconcile like this.

1. Measure the drift. Per box: `docker images --format '{{.Repository}}:{{.Tag}}' | grep glm53-zig | sort` against `grep -o -E 'glm53-zig:[a-z0-9]+' ~/INVENTORY.md | sort -u`. Read sizes from the box, never from memory: `du -sh ~/work/glm53-zig ~/bench`, `docker system df` (an image's "25 GB" is virtual, layers are shared: quote the df totals and the build cache, which exists on the build host spark1 only), `date -u` for the reading time.
2. Describe each tag only from the repo's records (`grep -l -r -F 'glm53-zig:TAG' docs scripts`; the queue log or the section that built it). Where the record only shows a queue used it, write "used by queueNN", never an invented purpose.
3. Work on a local copy inside the repo's `work/inv/` (never the profile root): `scp adam@<box>:INVENTORY.md work/inv/sparkN.md`. The edit tool refuses to anchor on long lines it has not shown in full: take the file tag from a short non-raw `read` of neighbouring lines, then `read path:A-B:raw` the long lines, then `PUT A.=B:` the whole entry (bullet plus its "built by ... Remove:" line). One entry, replaced in place; the Remove line lists every tag in one `docker rmi`, plus `docker builder prune -af` for the build host.
4. Before pushing, re-fetch the remote copy and `diff remote local`: only the lines you replaced may differ and the line counts must be equal, because other sessions append to these files. If anything else differs, merge instead of overwriting.
5. Push atomically: `scp local adam@<box>:INVENTORY.md.new && ssh <box> 'mv ~/INVENTORY.md.new ~/INVENTORY.md'`. Verify `sha256sum` equals the local file and the number of tags the manifest names equals the images present. Delete `work/inv/` afterwards.
6. Do not prune the docker build cache or remove image tags while queued builds in the chain still reuse them; put "prune cache and update the manifest for the new images" on the end-of-campaign list and do it once, together.
