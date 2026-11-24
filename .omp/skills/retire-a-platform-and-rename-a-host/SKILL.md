---
name: retire-a-platform-and-rename-a-host
description: "Retire an installed platform from a fleet box and rename that box, without losing its data or breaking the other roles: archive before delete, then fan the new name out to repo docs, fleet facts, skills, DNS and SSH keys."
---

# Retire a platform from a box and rename the box

Owner-directed, e.g. "remove paperclip entirely and rename the box to orca". The box usually runs OTHER roles, so
this is a surgical sweep, not a wipe. Measured on 192.168.99.50, 2026-11-23.

## 1. Survey before touching anything

```bash
ssh -A -tt <box> 'sudo docker ps -a --format "{{.Names}}|{{.Image}}|{{.Status}}"; sudo ls -d /opt/*; \
  sudo du -sh /opt/<platform> /srv/<platform> 2>/dev/null; df -h / | tail -1'
```
Name every other container/service explicitly (ph, Thermite, rgs-dev, auth2api, adam-style, Caddy) and keep them.
A "remove X entirely" never means "remove the neighbours".

## 2. Archive, then delete, then report the space

- Tar `/opt/<platform>` and `/srv/<platform>` to a big scratch filesystem (`/srv/ssd/archive/`), `chmod 600`,
  sha256 beside it. Data first, delete second - one command after the other, never the reverse.
- `zstd` may fail on a root-owned target (`Permission denied`); fall back to gzip and say so.
- Delete the platform's images too: those are usually the space (four images were 44 GB; the disk went 96% -> 88%).
- Rewrite the box's `~/INVENTORY.md` to CURRENT STATE: drop the platform section, add the archive path and the
  hostname change, keep every surviving role.

## 3. Rename the host

```bash
sudo hostnamectl set-hostname <new>
sudo sed -i 's/^127\.0\.1\.1.*/127.0.1.1 <new>/' /etc/hosts
grep -n preserve_hostname /etc/cloud/cloud.cfg   # must be true or cloud-init reverts it
```
DNS is the owner's: UniFi reservation/DNS still points the OLD name at the IP, so everything keeps working by IP or
old name; ask for the new record. Never claim the rename is done while DNS still only has the old name.

## 4. Fan the name out (the part that gets missed)

Grep, do not remember: `grep -rli <oldname> <repo> --include=*.md --include=*.sh --include=*.py` in the infra repo, the
per-repo `AGENTS.md`, `~/.omp/agent/AGENTS.md`, and `~/.omp/agent/managed-skills/`. Expect three classes:

1. **Host references** -> rewrite to the new name (careful: `<old>.ots-int.net` -> `<new>.ots-int.net`, and
   "the X box" -> "the new box").
2. **History/evidence** (measured logs, "in November 208 GB was X's dumps") -> LEAVE; falsifying a record is worse
   than an old name in it. Add one line saying the box is now called <new>.
3. **Obsolete platform skills** -> delete them (`manage_skill delete`); a skill for a platform that no longer exists
   will fire and mislead.

Also: delete the platform's deploy tree from the repo but rescue anything generic (a `build_pam_rssh.sh` living in a
`paperclip/` folder is still the YubiKey-sudo build script) into `scripts/hosts/`.

## 5. Keys: a platform's private key dies with its container

If the box had a fleet key inside the platform's home, the private half is gone and the public half sits dead in
`~adam/.ssh/authorized_keys` on every target. Replace, do not leave dead lines:

```bash
# on the box
ssh-keygen -q -t ed25519 -N "" -C "<new>-spark-fleet-<date>" -f ~/.ssh/<new>-spark-fleet
# on every target, from a host that can already log in
sed -i "/<old>-spark-fleet/d" ~/.ssh/authorized_keys
grep -q <new>-spark-fleet ~/.ssh/authorized_keys || printf 'from="<box ip>" %s\n' "$(cat)" >> ~/.ssh/authorized_keys
```

**THE TRAP: ssh only offers `~/.ssh/id_*` by default.** A key named `<new>-spark-fleet` is never offered, so the
box reports `Permission denied (publickey)` while the authorised_keys line is perfectly correct. Add a config entry:

```
Host spark1 ... spark6 <ips>
  IdentityFile ~/.ssh/<new>-spark-fleet
  IdentitiesOnly yes
```

Then prove it from the box by IP: `ssh <ip> 'hostname; docker --version'`. Hostnames may not resolve on that box.

## 6. Verify and report

- platform: no containers, no images, archive present with a sha256, disk figure before/after;
- neighbours: every other service still active (list them with their status);
- rename: `hostname`, `/etc/hosts`, what DNS still says;
- keys: one line per target in authorised_keys plus a live `ssh` from the box;
- docs: the commit hash, and the one thing still on the owner (usually the DNS record).

## Honesty rules that this sweep tested

- Deleting a directory before copying its content out destroys it; a `cp` to `/tmp` on Windows can silently not
  happen, so copy inside the repo's `work/` or use `install`. If it is lost, rewrite from the description and SAY so.
- `sudo` over a non-`-tt` ssh prints "A terminal is required to authenticate"; use `ssh -A -tt ... 'sudo <cmd> </dev/null'`.
