---
name: build-headless-orchestrator-lxc-on-proxmox
description: "Stand up a headless omp orchestrator LXC container on Proxmox for 24/7 crackme/RE dispatch work - so the laptop can close. Unprivileged Ubuntu 26.04 LXC dual-homed on LAN (DHCP for reach to the Sparks) + internal sandbox bridge (static, for future memagent-driven sandbox VMs). Handles the non-obvious gotchas: curl not in base template, omp install one-liner is https://omp.sh/install (NOT the raw GitHub path), omp-sync does NOT track models.yml so must be pushed manually, omp -p reads stdin until EOF so needs /dev/null when driven non-interactively via runuser, and rapid paramiko sessions to Proxmox trigger the UniFi IDS block (ask owner to suppress the signature if SSH starts timing out while ping works)."
---

# Bring up an omp orchestrator LXC on Proxmox

Goal: a 24/7 headless Linux container that runs omp and dispatches work (crackme grind, RE fan-outs, whatever) against LAN-reachable model endpoints (typically the DGX Sparks). Laptop can close; the box keeps grinding.

## Prereqs

- Proxmox 8+ / 9+ with SSH-as-root working
- An Ubuntu LXC template already present under `/var/lib/vz/template/cache/` (verify with `pveam list local`)
- Model endpoint(s) reachable on the LAN (e.g. DSV4 on `spark1.ots-int.net:8888`)
- Gitea/GitHub-hosted omp-config repo (Adam's is `ots/omp-config` on Gitea)

## Step 1 - internal sandbox bridge (skippable if you don't want future sandbox VMs)

Add `vmbr1` with no physical port so future sandbox VMs can talk to the orchestrator without touching the LAN.

```bash
cat >> /etc/network/interfaces <<'EOF'

auto vmbr1
iface vmbr1 inet static
    address 10.66.0.1/24
    bridge-ports none
    bridge-stp off
    bridge-fd 0
EOF
ifreload -a
```

## Step 2 - create the CT

Unprivileged, features=nesting (in case Docker later), dual-homed. 4 cores / 8 GB / 100 GB is plenty; adjust for scale.

```bash
pct create 101 local:vztmpl/ubuntu-26.04-standard_26.04-1_amd64.tar.zst \
  --hostname orchestrator \
  --cores 4 --memory 8192 --swap 2048 \
  --rootfs local-lvm:100 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp,firewall=1 \
  --net1 name=eth1,bridge=vmbr1,ip=10.66.0.10/24,firewall=1 \
  --features nesting=1 \
  --unprivileged 1 --onboot 1 \
  --password 'CHANGE-ME'
pct start 101
```

## Step 3 - bootstrap essentials + create user

The standard Ubuntu LXC template ships without curl and only has root. Fix that.

```bash
pct exec 101 -- bash -c 'export DEBIAN_FRONTEND=noninteractive && apt-get update -q && apt-get install -y -q curl wget git python3 python3-pip python3-venv jq tmux nano rsync openssh-client build-essential unzip 7zip'
pct exec 101 -- bash -c 'id adam 2>/dev/null || useradd -m -s /bin/bash -G sudo adam && echo adam:<KEY-AUTH: the fleet is KEY-ONLY: connect with the YubiKey SSH agent (see AGENTS.md 'Credential rule'), no password> | chpasswd'
```

## Step 4 - install omp

One-liner from **`omp.sh/install`** (NOT `raw.githubusercontent.com/can1357/oh-my-pi/main/install/install.sh` - that URL 404s). Run as the target user.

```bash
pct exec 101 -- runuser -l adam -c 'curl -fsSL https://omp.sh/install | sh'
pct exec 101 -- runuser -l adam -c 'export PATH=$HOME/.local/bin:$PATH; omp --version'
```

## Step 5 - sync omp config from Gitea/GitHub

Generate SSH key on the CT, add it to the config-repo host, clone, restore.

```bash
pct exec 101 -- runuser -l adam -c 'ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -C "orchestrator@$(hostname)"'
pct exec 101 -- runuser -l adam -c 'cat ~/.ssh/id_ed25519.pub'
# Add the pubkey to Adam's Gitea/GitHub account. On OTS Gitea, generate a
# short-lived token then POST /api/v1/user/keys - see use-ots-selfhosted-gitea
# skill for the exact API dance.

pct exec 101 -- runuser -l adam -c 'mkdir -p ~/Github && cd ~/Github && GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new" git clone ssh://git@gitea.ots-int.net:2222/ots/omp-config.git'
pct exec 101 -- runuser -l adam -c 'mkdir -p ~/.omp/agent && cd ~/Github/omp-config && bash omp-sync restore'
```

## Step 6 - push models.yml separately (NOT in omp-sync tracked set)

**This is the gotcha** - the `omp-sync` script's FILES/DIRS arrays cover `config.yml`, `RULES.md`, `WATCHDOG.md`, `cyber_patch.ps1`, `agents/*.md`, `managed-skills/**` - but NOT `models.yml`. On a fresh machine, omp will error "Model not found" until models.yml lands separately.

```bash
# From your laptop:
scp /c/Users/Adam/.omp/agent/models.yml root@<proxmox-host>:/tmp/
# On the Proxmox host:
pct push 101 /tmp/models.yml /home/adam/.omp/agent/models.yml --user 1000 --group 1000
```

Or via paramiko + `pct push`. Either way, the file needs to end up owned by the adam user inside the CT.

## Step 7 - smoke test

omp `-p` (non-interactive) reads piped stdin until EOF. When invoked via `runuser` non-interactively, stdin stays open forever and omp hangs at "phase: readPipedInput". **Close stdin explicitly with `</dev/null`.**

```bash
pct exec 101 -- runuser -l adam -c 'export PATH=$HOME/.local/bin:$PATH; omp -p --model ots/dsv4-flash-abliterated "say hi in 3 words" </dev/null'
# expected: prints "Working..." then the model's reply, exit 0.
```

Also note the flag is `--model NAME`, NOT `-m NAME`. `-m` returns "unknown flag".

## Non-obvious gotchas seen in the wild

1. **Ubuntu LXC template lacks curl.** The omp install one-liner will fail with `curl: command not found`. Install curl (step 3) before running the omp install.
2. **omp install URL** - use `https://omp.sh/install` (per the README on `can1357/oh-my-pi`). The old-looking `raw.githubusercontent.com/.../install/install.sh` path is not the canonical one.
3. **`models.yml` isn't in omp-sync.** Push it manually or extend the `FILES` array in `omp-sync` and re-backup.
4. **omp `-p` reads stdin.** `</dev/null` in every non-interactive invocation, or omp hangs at `readPipedInput` for its full startup budget.
5. **`--model` not `-m`.** The short flag is not defined.
6. **UniFi IDS blocks rapid SSH.** Many quick paramiko sessions to a Proxmox host on 192.168.3.x from another subnet will trip the IDS signature; SSH starts timing out while ping still works. Ask the owner to suppress the signature or space out reconnects.
7. **Unprivileged LXC + Mnemopi.** The `fastembed` runtime module isn't in the omp bundle and needs `npm i fastembed` in the omp install root; log shows `mnemopi: fastembed not loadable, using on-demand runtime install`. Not fatal for basic use; needs a separate fix if you want Mnemopi semantic recall to work.
8. **Login-power-assertion warning is harmless.** LXC has no DBus/login1; the `Failed to acquire power assertion` warning at startup can be ignored.

## Result

A CT running as `adam` with omp installed, config synced, and end-to-end reach to the Spark model endpoint(s). Ready to drive `omp -p --model ...` or `omp` interactive from a tmux session for 24/7 dispatch work. Laptop can close.
