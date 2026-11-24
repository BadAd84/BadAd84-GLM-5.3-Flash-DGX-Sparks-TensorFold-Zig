---
name: mint-fleet-service-ssh-key
description: "Mint and install a source-restricted fleet SSH service key (Proxmox + CTs + Sparks) from a service host like the Omnigent box - covers the proxmox pve-symlink, spark2 interlink, and quoting traps"
---

## When
Any OTS fleet service needs passwordless SSH across Proxmox + CTs + Sparks without the YubiKey (e.g. a service runner like the Omnigent host on CT106). Fleet is key-only; this mints a dedicated, source-restricted service key instead of sharing Adam's YubiKey key.

## Procedure

1. **Generate on the service host** (the box that will originate SSH - private half never leaves it):
   `ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519 -N "" -C "<service>-fleet-YYYYMMDD"`
   Add `/root/.ssh/config`: `Host *.ots-int.net 192.168.99.* 10.20.0.*` + `IdentitiesOnly yes` + `IdentityFile /root/.ssh/id_ed25519` + `StrictHostKeyChecking accept-new`.
2. **Write the installer as a FILE, scp it, run it** - never inline the command through ssh layers (nested-quoting syntax errors; bare `key(s)` parens in echo break remote bash). Script body (works for root and adam):
   ```sh
   #!/bin/sh
   mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
   LINE='from="<service-host-ips>" ssh-ed25519 AAAA... <comment>'
   touch "$HOME/.ssh/authorized_keys"
   [ -L "$HOME/.ssh/authorized_keys" ] || chmod 600 "$HOME/.ssh/authorized_keys"
   grep -qF "<comment>" "$HOME/.ssh/authorized_keys" || echo "$LINE" >> "$HOME/.ssh/authorized_keys"
   echo "installed: $(grep -c <comment> "$HOME/.ssh/authorized_keys")"
   ```
   scp to each target, then `ssh <target> "sh /tmp/omnikey_install.sh"`.
3. **`from=` restriction**: set it to the service host's LAN+mesh IPs. Even a leaked key only works from there. Rotating the service to another host = reissue.
4. **Targets** (from Adam's box with the YubiKey, `StrictHostKeyChecking=accept-new`): Proxmox host `root@proxmox.ots-int.net` (authorized_keys is a SYMLINK to `/etc/pve/priv/authorized_keys` - do NOT chmod through it), `root@192.168.99.105-109` (current CTs - run `pct list`, CT101 no longer exists), `adam@spark1/spark2.ots-int.net`.
5. **spark2 asymmetry gotcha**: spark2 never had the YubiKey key - laptop→spark2 is `Permission denied`. Install there via the spark1 interlink (`ssh adam@spark1 "ssh adam@spark2 ..."`), base64 the line to survive double-hop quoting.
6. **Verify**: from the service host, `ssh -o BatchMode=yes <target> hostname` to EVERY target - all must return hostnames with zero prompts.
7. **Document in the same action**: target machines' `~/INVENTORY.md` (authorized_keys line + removal), the service host's INVENTORY (private key + removal), and the credential-rule section in `~/.omp/agent/AGENTS.md`.

## Revoke/rotate
Delete the comment-keyed line from authorized_keys on every machine + remove the private key from the service host. Key comment doubles as the grep anchor.
