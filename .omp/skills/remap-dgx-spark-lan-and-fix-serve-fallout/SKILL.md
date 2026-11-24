---
name: remap-dgx-spark-lan-and-fix-serve-fallout
description: "Use when OTS DGX Spark LAN reservations are renumbered: reboot, repoint serve to names, fix known_hosts/state/docs/review-bot fallout."
---

# Remap DGX Spark LAN IPs and fix the fallout

When the owner renumbers the Spark LAN reservations (they did `.10x` -> `.11-.15` on 2026-10-06 to free
`.105-.109` for the CTs, because the growing Spark count collided with CT1xx IPs), the reboots are easy;
the fallout is not. Work this checklist.

## Apply the new IPs
- New reservations take effect on the box's next DHCP lease -> **reboot each Spark**
  (`ssh -A adam@<old-ip> 'sudo reboot </dev/null'`). It returns on the new IP.
- Find Sparks by NIC OUI from the Proxmox host (`ip neigh | grep -i a0:ad:9f`) - BUT spark5+ may ship a
  different Realtek OUI (spark5 = `30:c5:99`), so also scan by reachability (ping sweep + port 22).
- **A serve-head whose engine wedged refuses SSH** (connect times out) yet still pings. It's
  intermittently reachable - just retry `ssh -A ... sudo reboot` a few times; one attempt gets in.
- `*.ots-int.net` DNS follows the reservations automatically (UniFi), so NAME-based configs heal
  themselves; only RAW-IP configs break. (My own workstation can't resolve `.ots-int.net` - use IPs
  for the outer ssh hop; the head resolves names fine for the inner worker hops.)

## Repoint the serve to NAMES, not new IPs (remap-proof)
Switch every worker ssh target to `spark{N}.ots-int.net`. On spark1 (head): `~/.config/glm-stack.env`
(`GLM_WORKERS`), `~/glm-v15-start.sh` (gpuclk loop), `~/mia15/scripts/local.sh` (`WORKER`/`WORKER2`).
In the glm5.3-flash-dev repo: `scripts/glm53/glm-stack.env`, `scripts/glm53/v15/glm-v15-start.sh`, and the
`scripts/glm53/tp3/*` + `v15/*` bench scripts. The `10.0.0.x` fabric (NCCL master) is unchanged - leave it.

## THE serve-killer: the head's known_hosts
After the remap spark1's `~/.ssh/known_hosts` still has the workers' OLD IPs, so the launcher's
`ssh -o BatchMode=yes adam@spark2.ots-int.net` fails `Host key verification failed` and the serve won't
start. The recipe's error `start.sh: cannot ssh to adam@sparkN ... without a password` is really a
host-key failure, NOT an auth one. Fix on spark1:
```
ssh-keyscan -T5 spark1.ots-int.net spark2.ots-int.net spark3.ots-int.net 192.168.99.11 192.168.99.12 192.168.99.13 >> ~/.ssh/known_hosts
printf '\nHost spark* 192.168.99.1?\n    StrictHostKeyChecking accept-new\n' >> ~/.ssh/config   # future-proof
```
Then `spark-model glm start` (run via `bash -lc` - it's in `~/.local/bin`, not the non-interactive PATH).
Verify: `spark-model glm status` prints SERVING AND a real `/v1/chat/completions` round-trips.

## Regenerate spark-live-state.json (glm5.3-flash-dev)
`scripts/refresh-spark-state.sh` CANNOT run as a harness script-child (hermetic msys, no agent socket).
Run its probe inline from a top-level `ssh -A adam@192.168.99.11` (IP, not name) and regenerate the JSON
with a local python helper mirroring the script's JSON block (preserve `_comment` + the deleted-images
history). `scripts/check-doc-inventory.sh` must then be CLEAN.

## Sweep docs for BOTH forms
`grep '192\.168\.99\.10[1-4]'` MISSES **shorthand** `.10x` refs - a full sweep also needs `\.10[1-4]\b`
(it caught `.101/.102/.103` in a stack table and the last-octet convention). Fix ots-infra INFRA-LAYOUT.md and NEW-SPARK-SETUP.md,
glm5.3-flash-dev GLM53-FLASH-PRODUCTION-STACK.md, and EVERY AGENTS.md naming a Spark (`~/.omp/agent/AGENTS.md`,
ots-infra's, glm5.3-flash-dev's and qwen3.8-flash-next-dev's). While there, delete stale duplicate tables (a 2026-09-28 "what runs on them" table still
named the retired container + watchdog version) in favour of a pointer to the SSOT production doc.

## The baked review-bot env
The CT107 pr-agent `review1` bakes `OPENAI__API_BASE` (the GLM serve URL) into its container. Fixing the
repo copy is not enough - edit `/root/pr-review/docker-compose.yml` on CT107 (`pct exec 107`) and
`docker compose up -d review1` to re-bake; the running container keeps the dead `.101` until recreated.

## Owner-absent credential steps (if provisioning a new Spark in the same pass)
When the owner must do a one-time password step but can't stay, or copy-pasting a long key breaks lines:
**stage a tiny script on a box they already key-access** (`/root/x.sh` on the Proxmox host) that pulls
the PUBLIC key from `/root/.ssh/authorized_keys` - they run `bash /root/x.sh` and type only the password.
For the pam_rssh sudo switch, arm a **systemd safety-net** BEFORE removing the temp foothold so a PAM slip
can't lock out sudo: `sudo systemd-run --on-active=180 --unit=NAME bash -c '<re-add the NOPASSWD foothold>'`,
then remove the foothold, verify `sudo true </dev/null` works via the forwarded agent, then
`sudo systemctl stop NAME.timer` to cancel. Copy `libpam_rssh.so` + `/etc/security/sudo_authorized_keys`
from spark1 via base64 pipe (`ssh -A spark1 'base64 -w0 <file>' | ssh -A spark5 'base64 -d | sudo tee <file>'`)
and sha256-verify both ends. Clean up the staging scripts afterward.
