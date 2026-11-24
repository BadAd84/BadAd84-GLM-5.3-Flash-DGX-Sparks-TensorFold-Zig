---
name: deploy-litellm-router-on-proxmox-lxc
description: "Stand up and operate the LiteLLM router on a Proxmox LXC: free-tier multi-provider routing, no-train data guard, prisma/IPv6 gotchas, alias wiring."
---

# deploy-litellm-router-on-proxmox-lxc

one skill: stand up the LiteLLM free-tier router on a Proxmox LXC

Merged from 5 skill(s): build-free-llm-router-notrain-guard, build-litellm-free-tier-router-notrain-guard, deploy-litellm-free-tier-router-proxmox, deploy-litellm-free-tier-router-proxmox-lxc, deploy-litellm-router-on-proxmox-lxc.

Deploy or extend a LiteLLM router that muxes many free/no-train LLM API tiers behind ONE
OpenAI-compatible endpoint, as a backup/quota-saver for the DGX Sparks + a code-review pool.
Canonical instance: `ots/ots-infra` repo, `router/` dir; runs on Proxmox **CT 105
`litellm-router`** at `http://192.168.99.105:4000` (`/ui` Admin console). It is a BACKUP tier,
NEVER a replacement for the RULES §10 deep-review engines (deepseek-flash-max + glm-max).

## The data-policy guard (the whole point - design around this FIRST)
Split every provider by its training policy; fallbacks NEVER cross the boundary:
- `review-fast` / `review-deep` -> **NO-TRAIN providers ONLY** = SAFE for proprietary OTS code.
- `free-train` -> providers that MAY TRAIN on inputs = OSS/public/non-sensitive code ONLY.
Tag each model `model_info: {data_policy: no-train|MAY-TRAIN|owned|no-train-paid, tier: free|paid}`.
`router_settings.fallbacks` must keep no-train groups falling back only to other no-train/owned/paid,
never into `free-train`.

## Vetting a NEW free provider (do this EVERY time - catalogs churn quarterly)
1. Confirm it's genuinely free (perpetual vs credit-trial vs "free tier removed"). SambaNova's
   "free" is now a $5/3-month credit; OVH is a $200 trial - document those as optional, not core.
2. **Read its data/training policy** (web_search "<provider> data policy train on prompts 2026").
   Confirmed no-train -> review tiers. Trains-on-input/uncertain -> free-train (OSS only) or skip.
   This is load-bearing: a train-on-input provider in a review tier leaks proprietary code.
3. Confirm LiteLLM wiring: native prefix (`github/`, `sambanova/`, `together_ai/`, `cloudflare/`,
   `groq/`, `nvidia_nim/`, `cerebras/`, `mistral/`, `cohere/`) or OpenAI-compatible via
   `openai/<model>` + `api_base` (Scaleway `https://api.scaleway.ai/v1`, model `provider/name:quant`).
4. Pin CURRENT model IDs (verify live; NIM EOL'd gpt-oss-120b 2026-09-03). Add a comment to
   re-verify the id at the provider console.
5. Keyless entries load fine and just fail-and-retry until the user adds the account key - wire them
   config-ready + document signup in `.env.example`; do NOT block on a key you can't create.
Known good no-train free: NVIDIA NIM (build.nvidia.com, 10k RPD, big catalog - the backbone),
Groq, GitHub Models (free GPT-4o/DeepSeek-V3, zero-retention Azure), Cloudflare Workers AI
(~10k neurons/day), Together AI (`Llama-3.3-70B-Turbo-Free`), Cerebras (needs billing activated).
Free-train pool: OpenRouter `:free`, Gemini (AI Studio), Mistral codestral, Cohere trial.

## Deploy on the LXC (what actually runs)
```bash
apt-get install -y python3-venv python3-pip curl postgresql
python3 -m venv /opt/litellm
/opt/litellm/bin/pip install 'litellm[proxy]' prisma
su - postgres -c "psql -c \"CREATE USER litellm WITH PASSWORD 'litellm'; CREATE DATABASE litellm OWNER litellm;\""
mkdir -p /etc/litellm         # config.yaml + .env (chmod 600)
echo 'precedence ::ffff:0:0/96 100' >> /etc/gai.conf      # IPv4-first (see gotcha 5)
# generate prisma client FROM A SCRIPT (see gotcha 1):
PATH=/opt/litellm/bin:$PATH prisma generate --schema=/opt/litellm/lib/python3.12/site-packages/litellm/proxy/schema.prisma
cp systemd/litellm.service /etc/systemd/system/ && systemctl enable --now litellm
```
systemd unit MUST have: `After=network-online.target postgresql.service`,
`Environment=PATH=/opt/litellm/bin:/usr/local/sbin:...`, `ExecStart=... --num_workers 1`,
`Restart=always`. Enable BOTH litellm and postgresql; set CT `onboot=1`.

## Gotchas (each cost a cycle)
1. **prisma:** `litellm[proxy]` does NOT pull `prisma`; auth middleware imports it on EVERY chat
   call (500s without it, even with no DB). And `prisma generate` mangles/silently fails through an
   inline `bash -c` (quoting) and needs `/opt/litellm/bin` on PATH -> **run it from a pushed script,
   capture to a file with `; echo EXIT=$?`** to see the real result.
2. **PATH in unit:** without `Environment=PATH=/opt/litellm/bin:...`, litellm's own `prisma migrate`
   subprocess can't find the tools -> "Unable to find Prisma binaries" -> startup fails.
3. **num_workers 1:** multi-worker + DB races crash-loops on startup ("child failed to start").
4. **ModelInfo enum:** `tier:` only accepts `free`/`paid` (not `local`); a bad value drops the entry
   with a pydantic validation error.
5. **IPv4-only ISP:** provider hosts return AAAA but there's no IPv6 route; `curl` happy-eyeballs
   past it but litellm's httpx tries AAAA first and HANGS. Fix `/etc/gai.conf` precedence (above).
   So a direct `curl` test can pass while the router hangs - test through the router.

## Proxmox/paramiko driving (this box)
Proxmox host `root/<KEY-AUTH: the fleet is KEY-ONLY: connect with the YubiKey SSH agent (see AGENTS.md 'Credential rule'), no password>` @192.168.99.100; CTs via `pct exec 105 -- ...` (runs as root).
Cross-subnet paramiko from the laptop is flaky (UniFi IDS resets, blocking reads hang the kernel):
use ONE connection per short command with a hard channel timeout
(`ch=c.get_transport().open_session(); ch.settimeout(t); ch.exec_command(cmd)` then recv-loop
catching `socket.timeout`), and run long calls in the background (`nohup ... >log 2>&1 &`) then poll
the log with short reads. `pct push` files via `/tmp` on the host then `pct push 105 /tmp/x /root/x`.

## Verify
Config: `yaml.safe_load` + count entries per group. Deploy: health `curl :4000/health/liveliness`
-> 200, `systemctl is-active`, `NRestarts 0`. E2E: POST `/v1/chat/completions` with the master key
to each group (expect 200). UI: `/ui/` 200 + login 303 `login=success`. DB logging: SpendLogs rows.
Commit `router/` ONLY (never `-A`; leave sibling in-flight work untouched), GPG-signed, push.

Stand up a LiteLLM proxy on a dedicated Proxmox LXC fronting free-tier LLM APIs + owned endpoints as one OpenAI-compatible endpoint - a backup for the DGX Sparks / to spare API quota. Reference deploy: OTS CT 105 litellm-router @ 192.168.99.105:4000; artifacts in ots-infra/router/.

## Dedicated LXC, not the orchestrator CT
The router must stay up when other things go down - isolate it from the churny crackme-farm CT so a farm restart/OOM can't take it down. Tiny: 2 vCPU / 2 GB / 8 GB.

## Free-tier landscape (2026) - DATA POLICY is the design axis
Reviewing proprietary code on a train-on-your-data tier leaks it. Split providers into two group families; fallbacks NEVER cross:
- NO-TRAIN (safe for proprietary): NVIDIA NIM (build.nvidia.com; 40 RPM / 10k RPD; catalog is publicly listable at https://integrate.api.nvidia.com/v1/models WITHOUT a key), Groq (fast LPU, no-train), Cerebras. Strong review models: openai/gpt-oss-120b, nvidia/nemotron-3-super-120b-a12b, moonshotai/kimi-k3, mistralai/codestral-22b. OpenRouter PAID also defaults to no-logging.
- TRAIN-ON-INPUT (OSS/public code ONLY): OpenRouter :free (nvidia/nemotron-3-ultra-550b-a55b:free, minimax/minimax-m3:free - 1M ctx; ~50/day, 1000 with $10 credit), Gemini free (aistudio; 1M ctx). OpenRouter :free requires opting into training.
Name groups by intent (review-fast/review-deep = no-train; free-train = trains). It's opt-in: nothing hits the train pool unless you explicitly call that group.

## Build the CT
- `pct list` shows LXC CTs only; `qm list` shows VMs. If `pct create` says 'VM <id> already exists' but the config doesn't, it's an orphaned/other-owner vm-<id>-disk (check `lvs`, `qm list`) - pick a different free ID rather than lvremove.
- `pct create <id> local:vztmpl/ubuntu-24.04-standard_*.tar.zst --hostname litellm-router --cores 2 --memory 2048 --swap 512 --rootfs local-lvm:8 --net0 name=eth0,bridge=vmbr0,firewall=1,ip=dhcp --features nesting=1,keyctl=1 --unprivileged 1 --onboot 1 --start 1`
- `pct exec <id> -- bash -c 'echo root:PW | chpasswd'`; IP via `pct exec <id> -- hostname -I` (wait a few s for DHCP).

## Deploy LiteLLM (native venv+systemd - simpler than docker-in-LXC)
- `apt-get install -y python3-venv python3-pip curl; python3 -m venv /opt/litellm`
- `/opt/litellm/bin/pip install 'litellm[proxy]' prisma`  <- **prisma is REQUIRED and litellm[proxy] does NOT pull it.** The auth middleware `import prisma` on EVERY /v1/chat/completions; without it every call 500s ('No module named prisma' / 'No connected db') even with no DB. With prisma present, master-key auth works with NO database. Add DATABASE_URL + Postgres only for virtual keys/budgets/logging.
- Put config -> /etc/litellm/config.yaml, .env (chmod 600) -> /etc/litellm/.env, unit -> /etc/systemd/system/litellm.service; `systemctl enable --now litellm` (ExecStart: /opt/litellm/bin/litellm --config /etc/litellm/config.yaml --port 4000 --num_workers 2, EnvironmentFile=/etc/litellm/.env, Restart=always).
- Get files onto the CT: sftp to the Proxmox host /tmp then `pct push <id> /tmp/x /etc/litellm/x` - avoids nested-quoting through paramiko/pct exec.
- LONG pip installs: run `nohup ... >log 2>&1 & echo $!` then POLL a marker (`test -x /opt/litellm/bin/litellm`); a foreground install read through paramiko/eval hangs and can kill the kernel. Same for any long remote curl (bound with `timeout N`).

## LiteLLM config gotchas
- `model_info.tier` is a strict enum: only 'free' or 'paid'. A custom value (e.g. tier: local) throws ModelInfo ValidationError and SILENTLY DROPS that deployment ('Error creating deployment ... ignoring and continuing'). Use free/paid or omit tier; put custom metadata in other keys (data_policy, notes).
- `/v1/models` lists loaded groups; a group missing there failed validation at load - grep journal for 'Error creating deployment' / literal_error.
- Same model_name across entries = a load-balanced group; router_settings.fallbacks map group -> [groups]. Keep every fallback inside the data-policy boundary.
- LAN-only trusted CT: master-key auth (no DB) is enough. Verify: health/liveliness 200, /v1/models 200 with the master key, 401 without.

## Verify without provider keys
You cannot test a real completion without a valid provider key. The correct ceiling: health 200, all groups load, 401 without master key, and a chat call returns a PROVIDER 401 (not a prisma/DB 500) = plumbing works, awaiting key. (Beware: a chat call with all-placeholder keys will 'hang' up to the curl timeout because it retries every dead provider/fallback - use a no-fallback group to isolate.)

## omp wiring
providers.router: baseUrl http://<ct-ip>:4000/v1, api openai-completions, auth bearer, apiKey = LITELLM_MASTER_KEY from /etc/litellm/.env. Model ids = the group names (default a review agent to the no-train review-deep; switch to free-train only for OSS code).

# Deploy a LiteLLM router on a Proxmox LXC (free-tier + Spark backup gateway)

Goal: one OpenAI-compatible endpoint (`http://<ct-ip>:4000/v1`) that unifies free LLM tiers
(NVIDIA NIM, Groq, Cerebras, OpenRouter, Gemini) + owned Sparks, with a data-policy guard and
fallback chains, so omp has a Spark-independent, quota-saving backup path. Reference deploy:
OTS `ots-infra/router/` (CT 105, 192.168.99.105:4000).

## Why a dedicated LXC (not the orchestrator CT)
The router must stay up when other things go down, so it can't share a fate with a heavy/churny
CT (e.g. a crackme farm). Small dedicated CT, `vmbr0` DHCP (LAN + internet), `onboot=1`.

## Create the CT (Proxmox host = root@192.168.99.100 / <KEY-AUTH: the fleet is KEY-ONLY: connect with the YubiKey SSH agent (see AGENTS.md 'Credential rule'), no password>)
- Check free VMID: `pct list` shows only LXC CTs; `qm list` shows VMs (sandbox VMs 102/103/104
  are QEMU - a stale `vm-102-disk-0` LVM volume with no `lxc/102.conf` = a VM, not a free CT).
  Pick an ID with no `vm-<id>-disk` in `lvs` (105 was clean).
- `pct create <id> local:vztmpl/ubuntu-24.04-standard_*_amd64.tar.zst --hostname litellm-router
  --cores 2 --memory 2048 --swap 512 --rootfs local-lvm:8 --net0 name=eth0,bridge=vmbr0,firewall=1,ip=dhcp
  --features nesting=1,keyctl=1 --unprivileged 1 --onboot 1 --start 1`
- Drive it via `pct exec <id> -- ...` from the host (no CT SSH needed). Get IP: `pct exec <id> -- hostname -I`.

## Install LiteLLM (native venv+systemd - simpler than docker-in-LXC for one service)
```
apt-get update && apt-get install -y python3-venv python3-pip curl
python3 -m venv /opt/litellm
/opt/litellm/bin/pip install 'litellm[proxy]' prisma      # prisma REQUIRED - gotcha 1
echo 'precedence ::ffff:0:0/96 100' >> /etc/gai.conf      # prefer IPv4 - gotcha 2
mkdir -p /etc/litellm                                     # config.yaml + .env (chmod 600)
```
Long pip installs: background + poll (`nohup ... & echo $!`; poll for `/opt/litellm/bin/litellm`)
so the paramiko/eval kernel can't hang. Push config/.env via sftp to the HOST /tmp then
`pct push <id> /tmp/x /etc/litellm/x` (avoids nested-quote hell of writing files through pct exec).

## systemd unit
`ExecStart=/opt/litellm/bin/litellm --config /etc/litellm/config.yaml --port 4000 --num_workers 2`,
`EnvironmentFile=/etc/litellm/.env`, `Restart=always`. `systemctl enable --now litellm`.

## config.yaml pattern (data-policy guard)
- Group naming = the guard: `review-*` groups list ONLY no-train providers (nvidia_nim/, groq/,
  cerebras/, the Sparks as `openai/` + api_base, openrouter/ PAID); a separate group (e.g.
  `free-train`) holds the train-on-input free tiers (openrouter :free, gemini/) and has NO
  fallback in/out of the no-train groups. Never let a proprietary path reach a training provider.
- `router_settings`: `routing_strategy: simple-shuffle` (or `latency-based-routing` to prefer the
  fastest healthy provider), `num_retries: 2`, `fallbacks:` stay inside the no-train boundary.
- Sparks/no-auth endpoints: `api_key: "none"`.

## The three gotchas (each cost a debug cycle)
1. **prisma missing**: `litellm[proxy]` does NOT install `prisma`, but LiteLLM's auth middleware
   `import prisma` on EVERY `/v1/chat/completions` (even open/no-auth) -> every call 500s
   (`ModuleNotFoundError: prisma` / `No connected db`). `pip install prisma` fixes it; master-key
   auth then works with NO database. (`/v1/models` + `/health` work without it - misleading.)
2. **IPv6 on an IPv4-only ISP**: provider hosts return AAAA first with no IPv6 route. `curl`
   happy-eyeballs past it, but LiteLLM's httpx tries the AAAA and HANGS -> chat calls stall while a
   direct curl looks fine. Fix: `/etc/gai.conf` -> `precedence ::ffff:0:0/96 100` (+ optionally
   `sysctl -w net.ipv6.conf.all.disable_ipv6=1`). A passing curl test can mislead you here.
3. **ModelInfo.tier enum**: `model_info.tier` only accepts `free`/`paid`; a custom value (e.g.
   `local`) throws a pydantic literal_error and LiteLLM SILENTLY DROPS that deployment (it vanishes
   from `/v1/models`). Use custom keys other than `tier` (e.g. `data_policy`) for your own metadata.

## Verify (test the clean way - from a real consumer, in Python, not shell-quoted curl)
Hit `http://<ct-ip>:4000/v1/chat/completions` from the laptop with urllib/json (no bash quoting):
`{"model":"review-fast",...,"max_tokens":200}` (>=~100 tokens - gpt-oss are reasoning models and
return content=None if max_tokens is too small). Expect a real completion; a group with placeholder
keys returns a provider 401 (= plumbing OK, awaiting key). `/v1/models` with the master key = 200,
without = 401 (after prisma fix).

## omp wiring
`~/.omp/agent/models.yml` provider -> `baseUrl: http://<ct-ip>:4000/v1`, `auth: bearer`,
`apiKey: <LITELLM_MASTER_KEY from /etc/litellm/.env>`, list the group ids (review-deep default for
proprietary; free-train only for OSS). Point a review agent at `router/review-deep`.

## Web UI / advanced routing
`/ui` loads but virtual keys, usage/spend dashboards, budgets, logs, and edit-models-in-browser all
need a Postgres/Prisma DB (set `DATABASE_URL` + it runs `prisma` migrations on boot). No-DB deploy =
YAML-config-driven (edit config.yaml + `systemctl restart litellm`). Routing is NOT task-semantic:
the caller picks the group; `routing_strategy` picks the provider within it.

## Secrets
Provider keys live in `/etc/litellm/.env` on the CT (chmod 600); commit only `.env.example`
(`.env` gitignored). Write keys via sftp file content, not shell command line (keeps them out of
ps/journal).

# LiteLLM free-tier router with a no-train data-policy guard

Goal: one OpenAI-compatible endpoint that pools free LLM tiers + owned local models, with a guard so PROPRIETARY code never reaches a train-on-your-input provider. Deploy on always-on infra INDEPENDENT of what it backs up (e.g. a Proxmox LXC when backing up DGX Sparks).

## 1. Pin current free model IDs (catalogs churn — do this live, re-verify quarterly)
- OpenRouter: `GET https://openrouter.ai/api/v1/models` (public, no key). Free = `pricing.prompt==0 && pricing.completion==0`, or id ends `:free`.
- NVIDIA NIM: `GET https://integrate.api.nvidia.com/v1/models` is PUBLICLY listable WITHOUT a key (inference needs a free build.nvidia.com Developer key). 40 RPM / 10k RPD, NO-TRAIN — the backbone.
- Groq/Cerebras: `/models` needs a key. Cross-check `github.com/mnfst/awesome-free-llm-apis` (maintained IDs + limits + data policy per provider).

## 2. The data-policy split (the guard)
- NO-TRAIN (safe for proprietary): NVIDIA NIM, Groq, Cerebras, OpenRouter PAID (defaults to no-logging providers), owned local endpoints.
- TRAINS-ON-INPUT (OSS/public ONLY): OpenRouter `:free` variants, Gemini free, Mistral free.
- Design: one LiteLLM `model_name` group PER policy. No-train review groups fall back only among no-train + owned + paid. The train group has NO fallback in OR out (one-directional isolation) and a self-warning name (e.g. `free-train`). Caller picks the group that matches the material.

## 3. litellm-config.yaml essentials
- Multiple `model_list` entries sharing a `model_name` = a load-balanced group.
- `router_settings.fallbacks: [{"grpA": ["grpB", ...]}]` — keep every chain inside the no-train boundary.
- Provider prefixes: `nvidia_nim/<model>` (api_base https://integrate.api.nvidia.com/v1), `groq/<model>`, `cerebras/<model>`, `openrouter/<model>`, `gemini/<model>`, `openai/<model>` (+ api_base for custom/local endpoints; api_key: "none" for auth-less LAN endpoints).
- `api_key: os.environ/KEY` (never inline). `general_settings.master_key: os.environ/LITELLM_MASTER_KEY`. `litellm_settings.drop_params: true`.

## 4. Deploy (Proxmox LXC, dual-homed on LAN)
- `docker compose` with `image: ghcr.io/berriai/litellm:main-stable`, `env_file: .env`, mount config to /app/config.yaml, `command: [--config, /app/config.yaml, --port, 4000]`, port 4000. `.env` gitignored (keys stay on the box; config commits env-var refs only).
- Verify: `curl -s http://localhost:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"`.

## 5. omp wiring
- models.yml provider: `baseUrl: http://<ct-ip>:4000/v1`, `api: openai-completions`, `auth: bearer` + apiKey=master key (or `auth: none` for a trusted LAN CT). List the group names as model `id`s.

## 6. Validate + gotchas
- `yaml.safe_load` the config; assert no-train groups contain zero `openrouter/...:free` or `gemini/` entries.
- A naive `openrouter/` substring check false-flags PAID OpenRouter as a trainer — paid OR defaults to no-logging; only `:free` trains.
- NIM `/models` is public but inference needs the free key. Groq deprecated two llamas Aug 2026 — the catalog is volatile.
- Frame it as a BACKUP/quota-saver tier, not a replacement for deep review engines.

# Free-LLM LiteLLM router with a no-train data-policy guard

Build a local LiteLLM proxy that unifies FREE LLM tiers + owned inference (DGX Sparks) behind
one OpenAI-compatible endpoint, as a Spark-independent, quota-saving backup for omp work
(code review especially). The whole point is the **data-policy guard**: reviewing proprietary
code on a train-on-your-data free tier leaks it, so no-train and trains-on-input providers are
kept in separate model groups whose fallbacks NEVER cross.

Lives at `ots-infra/router/` (committed, signed). Deploy on a Proxmox LXC.

## 1. Pin the free catalog LIVE (it churns - re-verify quarterly)
- **NVIDIA NIM** model list is PUBLIC/keyless: `GET https://integrate.api.nvidia.com/v1/models`
  (no auth to LIST; a free build.nvidia.com Developer key is needed to RUN). 40 RPM / 10,000 RPD,
  NO-TRAIN. Best free backbone. Strong coders: `openai/gpt-oss-120b`,
  `nvidia/nemotron-3-super-120b-a12b` (1M), `moonshotai/kimi-k3`, `mistralai/codestral-22b-instruct-v0.1`.
- **OpenRouter**: `GET https://openrouter.ai/api/v1/models` (public). Free = pricing.prompt==0 &&
  completion==0, or id ends `:free`. These generally TRAIN on input. Big-ctx: `nvidia/nemotron-3-ultra-550b-a55b:free`, `minimax/minimax-m3:free` (1M). Rate ~50/day (1000 w/ $10 credit).
- **Groq/Cerebras**: `/models` needs a key (401/403). Get current free IDs from
  `github.com/mnfst/awesome-free-llm-apis` (maintained). Groq `openai/gpt-oss-120b` 30 RPM/1k RPD
  no-train; Cerebras `gpt-oss-120b` ~3000 tok/s no-train.

## 2. Data-policy split (the organizing principle)
| No-train (proprietary-safe) | Trains-on-input (OSS/public ONLY) |
|---|---|
| NVIDIA NIM, Groq, Cerebras, Cloudflare Workers AI, owned Sparks, OpenRouter-paid no-log | OpenRouter :free, Gemini free, Mistral free (unless opt-out), Cohere trial (also non-commercial) |

## 3. LiteLLM config pattern (`litellm-config.yaml`)
- One `model_name` group per data policy: `review-fast`/`review-deep` (no-train only) and
  `review-oss` (trains). Multiple entries with the SAME model_name form a load-balanced pool.
- Provider prefixes: `nvidia_nim/<id>` (+ api_base https://integrate.api.nvidia.com/v1),
  `groq/<id>`, `cerebras/<id>`, `openrouter/<id>`, `gemini/<id>`, and `openai/<id>` for the
  Sparks (api_base http://spark1...:8888/v1, api_key "none").
- Keys as `os.environ/NAME`. Per-entry `rpm:` so the router respects free limits + rotates.
- `router_settings.fallbacks` keep the boundary: `review-fast -> review-deep -> spark-* -> paid`;
  review-oss has NO fallback into review-* (one-directional). `routing_strategy: simple-shuffle`,
  `num_retries: 2`. `general_settings.master_key: os.environ/LITELLM_MASTER_KEY`.
- VERIFY the guard programmatically after writing: assert no review-* (except review-oss) entry's
  model string contains `openrouter/` or `gemini/`.

## 4. Deploy (Proxmox LXC)
- `docker-compose.yml`: `image: ghcr.io/berriai/litellm:main-stable`, `-p 4000:4000`,
  `env_file: .env`, mount config to `/app/config.yaml`, `command: [--config,/app/config.yaml,--port,4000,--num_workers,2]`, healthcheck `/health/liveliness`.
- Small dedicated LXC, dual-homed on the LAN (internet for providers + intra-subnet to the Sparks,
  which also dodges the UniFi IDS on cross-subnet hops). Always-on = the point.
- `.env.example` committed; real `.env` in `router/.gitignore` (NEVER commit keys).

## 5. omp wiring + framing
- `omp-models.snippet.yaml`: a `router` provider (baseUrl http://<ct-ip>:4000/v1, auth bearer =
  master key, or auth:none for LAN-only) exposing `review-deep`/`review-fast`/`review-oss`. Default
  a review agent to `router/review-deep` (no-train); only use `router/review-oss` for OSS code.
- RULES §10: this is a BACKUP/first-pass/quota-saver tier, NOT the terminating clean-review gate
  (that stays on the deep non-Anthropic engines).

## Gotchas
- YAML: a display `name:` containing `': '` breaks the parser - reword or quote. Validate every
  YAML with yaml.safe_load before committing.
- Free catalogs churn (Groq deprecated two llamas Aug 2026); NIM list is public but per-model RPD.
- Commit to ots-infra Gitea = GPG-signed; stage ONLY your files (other agents' REAP work is often
  dirty in the tree - never `git add -A`).
