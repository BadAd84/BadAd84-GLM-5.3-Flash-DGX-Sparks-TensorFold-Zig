---
name: install-kindling-spark-os-on-dgx-spark
description: "Move an OTS DGX Spark from DGX OS to kindling spark-os (64K kernel + dispram) with YubiKey sudo intact: site layer, trial boot, verify, promote, fabric."
---

# Install kindling spark-os on a DGX Spark (OTS fleet)

The canonical recipe is glm5.3-flash-dev `docs/GLM53-TENSORFOLD-TP3-PORT.md` section 2.0. Scripts: ots-infra `scripts/sparks/make_kindling_site.sh` and `verify_kindling_boot.sh`.

## Steps (one Spark at a time; stop any serve on it first)
1. Upload the script with `tr -d '\r' < make_kindling_site.sh | ssh adam@<spark> 'cat > ~/make_kindling_site.sh'`.
   - Check that the md5 on the box matches the local copy. A stale copy on spark1 once rebuilt the broken layer.
2. **Prereq for a box that never ran the GLM serve** (e.g. a Qwen/Clef box): `make_kindling_site.sh` copies `/usr/local/bin/glm-mem-hygiene.sh`, `/usr/local/bin/py-spy` and `/etc/sysctl.d/95-glm53-uvm.conf` into the layer and `exit 1`s with "missing ..." if absent. Copy them from spark1 first (spark-to-spark over the forwarded agent: `ssh -A adam@<box> 'scp -o StrictHostKeyChecking=accept-new adam@spark1:...'` then `sudo install -m755`). pam_rssh files are already in the fleet baseline.
3. Place the mentat key: `~/.config/kindling/cluster.key` (mode 600), the SAME key on every box. Reuse spark1's by spark-to-spark scp over the forwarded agent (never echo it; compare md5 to confirm).
4. Over `ssh -A -tt` (pam_rssh sudo), run `sudo bash ~/make_kindling_site.sh`. It builds `/etc/kindling-spark-os/site` (pam_rssh, the helpers above, swappiness 0, IPv6 off, adam lingering, Europe/London). libpam_rssh.so must land in the `readlink -f` path (usr/lib/...), never a real `/lib`.
5. Clone with `git clone --branch stable https://github.com/kindlingai/kindling-spark-os`; `git checkout 73ff3ae` to pin the same 0.9.5 commit as production (stable's tip is 73ff3ae as of 2026-10).
6. Run `./setup.sh --yes --secret "$(cat ~/.config/kindling/cluster.key)"` over `ssh -A -tt` (the `$(...)` expands ON the box, keeping the key off the harness). ~3-4 min; builds the image in docker and queues a one-shot next boot.
   - **`--check` FALSELY reports "sudo is not available without a password" under pam_rssh** - it only tries `sudo -n`, which pam_rssh (needs the PAM conversation) cannot satisfy. `--yes` PASSES because it falls back to interactive `sudo -v` (works with the tty + forwarded agent). So run `--yes` directly; do not be blocked by the `--check` sudo FAIL. The build itself takes ~3 min, so run it foreground with a long timeout or detached.
7. `sudo systemctl reboot`, then poll until `grep -q sparkos= /proc/cmdline` (about 2 minutes).
8. `sudo touch /run/sparkos-confirmed` and `bash ~/verify_kindling_boot.sh` over `ssh -A -tt`.
   - **On a freshly-converted box the GLM-config checks FAIL as expected**: "docker images kept", "rank folder on /home", "fabric: 4 CX7 addresses", "RDMA devices with IPv4 GIDs" - these need the GLM image/weights/fabric, not the OS install. The ~15 CORE checks (spark-os, 64K pages, kernel, driver, GPU, YubiKey sudo, dispramd, IPv6 off, timezone, swappiness, lingering, py-spy/gdb) passing is enough to promote; the GLM checks clear in the weights/fabric phases.
9. `sudo sparkos-promote` within 10 minutes, or the box reverts by itself (`/run/sparkos-confirmed` present makes the trial-revert service skip; a box past 10 min still on sparkos has held). `sparkos-rollback` to go back to DGX OS.
10. Update `~/INVENTORY.md` with the image, `/swap-64k.img`, GRUB files and the docker image `kindling-spark-os`. Removal commands come from the undo lines in `~/kindling-spark-os-setup.log`.

## Fabric on kindling (ConnectX-7 rails)
- **Persistence is netplan, mirrored from the host disk.** kindling rebuilds `/etc/netplan` from `/run/sparkos/host/etc/netplan/` at boot, so write the fabric YAML to BOTH `/etc/netplan/95-fabric-tp2.yaml` and that host-disk path (verified: survives a reboot). The LAN (enP7s7) is usually NM default DHCP, not netplan-managed, so an additive fabric file does not risk it.
- The GB10's cabled CX7 port (physical port 0) exposes TWO PCIe functions = two rails: `enp1s0f0np0` (rocep1s0f0) and `enP2p1s0f0np0` (roceP2p1s0f0). Give each a static /24, MTU 9000, ipv6 off. The RoCE v2 IPv4 GID appears at index 3 (scan sysfs `gids/*` for the ffff-mapped one whose `gid_attrs/types/*` is "RoCE v2"; never hardcode).
- **NEVER use `sudo shutdown -r +N` as a lockout safety net** - it creates `/run/nologin` which then blocks your own cancel ssh. Use a detached guard instead: `sudo bash -c 'setsid sh -c "sleep 120; ip -4 addr show enP7s7 | grep -q 192.168.99 || systemctl reboot" &'` (reboots only if the LAN actually drops; the /etc-only fabric file is wiped on that reboot, restoring the LAN).
- **kindling has no apt and no perftest.** To run `ib_write_bw`, `curl` the perftest .deb from ports.ubuntu.com and `dpkg-deb -x` it (libibverbs/libmlx5/librdmacm are already on the image); run it ephemerally, then remove. Healthy CX7 is ~109 Gb/s per rail; ~13 Gb/s = the hot-plug low-power state, fixed by a reboot WITH the cable connected (the kindling reboot does this).
- Factory boxes can carry broken WiFi netplan profiles (unused wlP9s9/OobeHotspot with YAML anchors) that fail `netplan generate`; remove them from `/etc/netplan` + the host-disk path.

## Traps
- **A site layer must never contain a real `/lib`, `/bin` or `/sbin`.**
  - Ubuntu's `/lib` is a symlink to `usr/lib`. A real directory in the layer replaces it, and the build then fails with `chroot: failed to run command '/bin/bash'` / `update-initramfs`.
  - Copy files into `readlink -f` of the target directory.
  - A failed build changes nothing except the built docker images and the mentat key files.
- **kindling does not carry pam_rssh or `/etc/pam.d/sudo` over.** Users, `sudoers.d`, ssh host keys and NetworkManager/netplan profiles do carry over (the latter via the host-disk `/etc` mirror).
- **Never pass `-c` / `--create` to re-open; never confuse `/etc` with the host-disk mirror.** After the switch, `/` is a RAM overlay. Only `/home`, `/srv`, `/var/lib/docker`, `/var/lib/containerd` and `/var/log` persist. System changes go through the site layer and an image rebuild, or the host-disk `/run/sparkos/host/etc/...` mirror.
- **The `glm53-nfs` container crash-loops under spark-os** with "Statd service already running". It has been stopped with restart=no; nothing uses it.
- **TensorFold weight loads work on the 64K kernel**: 8 GiB of weights loaded to the GPU at 1.4 GiB/s.
- **The first full serve start after the reboots exceeded the bench harness's 15-minute health window**, probably because the disk cache was cold. Verify load time before trusting a benchmark arm.
- **dispramd needs driver 580.178.04.** Its client is mounted into containers at run time; it is never vendored (AGPL/GPL).
