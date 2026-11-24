---
name: deploy-and-serve-models-via-router
description: "Wire and serve models through the OTS LiteLLM router into omp/Hermes/Letta: alias pinning, thinking-off variants, agentic tool-loop quirks, Claude Max bridging."
---

# deploy-and-serve-models-via-router

one skill: wire models through the OTS LiteLLM router

Merged from 7 skill(s): add-fixed-parameter-llm-alias, add-litellm-model-alias-with-fallbacks, pick-and-wire-router-models, serve-claude-max-to-agents-via-litellm, serve-models-to-agent-clients-via-litellm-router, wire-agents-to-litellm-router-agentic-quirks, wire-ots-router-models-into-omp-hermes.

Use when a model served through the OTS LiteLLM router (CT 105, 192.168.99.105:4000) hangs, loops "in circles", or 500s for an agent client (omp, Hermes, an n8n AI-agent node). Two recurring non-obvious causes; both cost a debug cycle on 2026-09-05.

## 1. Client sends ARRAY content; the backend wants STRING
- omp/agent clients send `messages[].content` as an array of content-parts `[{type:text,text:...}]`. **Cloudflare Workers AI's OpenAI endpoint** (`api.cloudflare.com/.../ai/v1`) REJECTS arrays ("oneOf ... 'string' not in 'array'") -> 400 -> LiteLLM retries + fails over -> 500 -> the client loops/hangs. NIM/Groq/OpenRouter accept arrays; Cloudflare is the strict one.
- **Fix: a LiteLLM pre-call hook that flattens content lists to a joined string.** `ots-infra/router/content_flatten.py` is a `CustomLogger` with `async_pre_call_hook(self,user_api_key_dict,cache,data,call_type)` that rewrites `data["messages"][*]["content"]`. Register: `litellm_settings.callbacks: content_flatten.proxy_handler_instance`. It MUST be importable -> add `Environment=PYTHONPATH=/etc/litellm` to the systemd unit (LiteLLM only inserts `../..` into sys.path, never the config dir). String content is universal, so flatten globally (the router is text-only).

## 2. Reasoning model as a tool-agent loops "in circles"
- A reasoning model (GLM-5.3-Flash, Qwen3.8) driven as a TOOL-AGENT with thinking ON emits a `<think>`/`reasoning_content` block and EMPTY `content`; the client sees nothing actionable, injects a "you stopped, continue" nudge, and loops forever. Same failure whether the client is omp or Hermes.
- **Fix: force thinking OFF. The knob differs by family** - GLM: `chat_template_kwargs.thinking:false`; Qwen: `chat_template_kwargs.enable_thinking:false`.
  - Router-side (serves it OFF to every client incl. Hermes): add to the deployment `litellm_params: extra_body: {chat_template_kwargs: {thinking: false}}`. `extra_body` IS forwarded into the upstream vLLM body (proven - same path as the panel OpenRouter ZDR `provider:{}` block; `drop_params:true` does NOT strip extra_body contents).
  - Client-side (omp): `models.yml` provider `extraBody.chat_template_kwargs.<knob>:false`.

## 3. Context-size rule for omp/agent tool-agents
- omp's per-agent system-prompt baseline is ~27k tokens (RULES.md alone ~51KB ~= 13k tokens, + AGENTS.md + skills list + tool schemas). A 32k-context model OVERFLOWS before it can answer. Do NOT use small-context models as omp reviewer/agent roles; use >=128k context. (This is why the Cloudflare panel slot moved off `qwen2.5-coder-32b` (32k).)

## Router facts / deploy
- The router fronts the Sparks as `spark-ds4` (spark1:8888) and `spark-glm` (spark1:8889). Sparks serve ONE big model at a time (GB10 UMA), so a `spark-*` route only works when that model is loaded; the fallback chain covers a swap.
- Deploy a config/hook/unit change: base64-push the file to `/etc/litellm/` on CT 105 via `pct exec 105` (from Proxmox host `root@192.168.99.100`, pw <KEY-AUTH: the fleet is KEY-ONLY: connect with the YubiKey SSH agent (see AGENTS.md 'Credential rule'), no password>), `systemctl daemon-reload` (only if the unit changed) + `systemctl restart litellm`, then poll `http://localhost:4000/health/liveliness` (200 in ~28s = config valid). Master/router key lives in `/etc/litellm/.env`.

# Wire Letta / Letta Code / omp to a LiteLLM router (+ agentic backend quirks)

Architecture (the right design): make the **LiteLLM router the single base provider** for every engine. Sparks and free tiers are just MODELS on the router. Then you never re-point an engine - only change the model handle. OTS router = CT 105 `http://192.168.99.105:4000/v1` (master key in CT105 `/etc/litellm/.env`). Sparks on it: `spark-glm`->spark1:8889, `spark-ds4`->spark1:8888.

## Agentic-backend quirk matrix (the crown jewel - cost the most cycles)
For TOOL-LOOP agents (Letta, omp), the backend must accept OpenAI multi-step tool-call message format. A one-shot reply working proves NOTHING - **test with a real tool loop** (ask it to run a shell tool and report). Findings via the router:
- **Cloudflare Workers AI** (`panel-mistral`, qwen): rejects Letta's `user`-after-`tool` role ordering -> `AiError: Unexpected role 'user' after role 'tool'`. FAILS agentic.
- **Groq** (`panel-gptoss`, `panel-deepseek`): rejects `reasoning_content` on the echoed assistant turn -> `property 'reasoning_content' is unsupported`; also 32k context cap (too small for omp's big prompt). FAILS agentic.
- **NVIDIA NIM** (`panel-nemotron`): OpenAI-compliant, survives the tool loop, 128k, free/no-train. WORKS - use this as the free interim.
- **Spark vLLM** (`spark-glm`/`spark-ds4`): fully compliant, cleanest. WORKS. (Reasoning models: disable thinking or they loop.)

## Letta Python App Server (0.16.8) model re-point mechanics
- Systemd env `OPENAI_API_BASE`/`OPENAI_API_KEY` seed the base `openai` provider, but already-synced models keep a STALE endpoint and the agent's baked `llm_config` wins. Authoritative fix is per-agent.
- Update method is `c.agents.update` (NOT `.modify`, which doesn't exist). There is NO `c.providers` API in the SDK.
- Set the endpoint via the WRITE ALIAS `model_endpoint`. The dumped field name `api_model_endpoint` is read-only serialization; passing it is silently ignored. Correct:
  ```python
  a=c.agents.retrieve(agent_id=aid); d=a.llm_config.model_dump(by_alias=True)
  d['model']='panel-nemotron'; d['handle']='openai-proxy/panel-nemotron'
  d['model_endpoint']='http://192.168.99.105:4000/v1'   # ALIAS, not api_model_endpoint
  d['context_window']=100000; d['max_tokens']=4000
  c.agents.update(agent_id=aid, llm_config=d)
  ```
- Health: `curl localhost:8283/v1/health/` (trailing slash). Letta needs asyncpg+pgvector, an `alembic upgrade head` from the matching source tag (pip wheel ships no migrations dir), pg8000, Redis, and a Fernet `LETTA_ENCRYPTION_KEY`.

## Letta Code (the full TUI) = the npm package, not Python
- `@letta-ai/letta-code` (npm) provides the `letta` binary (App Server + Claude-Code-style TUI). Python `letta server --type websocket` (0.16.8) is a deprecated stub (`NotImplementedError: WS support deprecated`).
- `letta backend local`; then `letta setup` must run ONCE - it's interactive; drive over SSH with a PTY and send Enter to accept 'Proceed locally' (else `letta connect` errors `Settings not initialized`).
- `letta connect llama-cpp --base-url <router> --api-key <key>` discovers models from `/v1/models` -> handle `llama-cpp/<model>`. The `openai` provider only accepts its built-in catalog (gpt-*) and REJECTS arbitrary model ids, so use llama-cpp for custom endpoints.
- Change an existing agent's model (persists): `letta -a <id> -m llama-cpp/<model> -p '...'`. Pin a default: `letta agents create --name X --model <handle> --personality letta-code --pinned` and set `~/.letta/settings.json` `lastAgent`. Config dir `~/.letta` (shared with Python letta - messy but works).

## letta-client streaming CLI + interrupt
`c.agents.messages.create(agent_id, messages=[...], streaming=True, stream_tokens=True)` yields chunks by `.message_type`: `reasoning_message`(.reasoning), `tool_call_message`(.tool_call.name/.arguments), `tool_return_message`(.tool_return), `assistant_message`(.content), `usage_statistics`(.prompt_tokens/.completion_tokens/.total_tokens/.reasoning_tokens/.step_count), plus `ping`/`stop_reason`. Mid-run interrupt: catch KeyboardInterrupt, `c.runs.cancel(run_id)` (run_id from `chunk.run_id`).

## Verify a rich TUI layout headlessly
`Console(record=True).export_text()` renders the box layout as clean text (no ANSI) - eyeball panel formatting without a real tty. Live() renders only the final frame in non-tty capture, which is enough to confirm structure.

# Wire OTS-router models into omp / Hermes

Serve a Spark-hosted or free-tier model through the OTS LiteLLM router and make it usable by omp/Hermes - including the diverse review panel. Complements `wire-local-model-into-omp-via-models-yml` (models.yml basics) and the litellm-router-build skills; this one is the model-wiring + gotchas layer.

## Access + deploy (do this first)
- Router = LiteLLM 1.99 native venv on **Proxmox CT 105** (192.168.99.105:4000). Config `/etc/litellm/config.yaml`, keys in `/etc/litellm/.env`, unit `/etc/systemd/system/litellm.service`.
- Repo source of truth: `ots-infra/router/` (litellm-config.yaml, content_flatten.py, systemd/litellm.service). Edit repo -> deploy.
- Deploy from laptop: paramiko to Proxmox host **192.168.99.100 root/<KEY-AUTH: the fleet is KEY-ONLY: connect with the YubiKey SSH agent (see AGENTS.md 'Credential rule'), no password>**, base64-push the file (`pct exec 105 -- bash -c 'echo <b64> | base64 -d > /etc/litellm/config.yaml'`), then `systemctl restart litellm` (slow SIGTERM stop-phase; ~28s to health 200). Health: `curl localhost:4000/health/liveliness`.
- NEVER paramiko the Sparks cross-subnet (UniFi IDS); the router HTTP is reachable from the laptop directly.

## Force reasoning OFF (the #1 recurring bug)
A reasoning model driven as a tool-agent (omp subagent, Hermes) LOOPS: it emits a think block, the client sees no actionable content, injects 'you stopped, continue', repeat. Disable thinking per family:
- **GLM / DSV4**: `chat_template_kwargs.thinking: false`
- **Qwen (3.x)**: `chat_template_kwargs.enable_thinking: false`

Two places:
- **omp client-side** (per provider in ~/.omp/agent/models.yml): `compat.extraBody.chat_template_kwargs: {thinking: false}`.
- **Router-side** (forces it for EVERY client incl. Hermes, which sends no thinking field): on the LiteLLM deployment add `litellm_params.extra_body: {chat_template_kwargs: {thinking: false}}`. This is forwarded to the vLLM body (same path as panel-* OpenRouter `provider:{zdr}`); `drop_params: true` does NOT strip extra_body contents. To hard-override a client that explicitly sends thinking:true, add it in the pre-call hook instead.

## Cloudflare array-content 500
Cloudflare's OpenAI-compat `ai/v1` rejects omp's array `messages[].content` ('string' not in 'array') -> 500 + client hang. Fix = the LiteLLM pre-call hook `ots-infra/router/content_flatten.py` (a `CustomLogger` with `async_pre_call_hook` joining content parts to a string), wired via `litellm_settings.callbacks: content_flatten.proxy_handler_instance` and **`Environment=PYTHONPATH=/etc/litellm`** in the unit (LiteLLM only adds `../..` to sys.path, not the config dir). NIM/Groq/OpenRouter accept array content natively.

## Context sizing
omp injects RULES.md (~51KB/~13k tok) + AGENTS.md + skills + tool schemas into EVERY subagent = ~27k-token baseline, with NO per-agent opt-out. So a 32k-ctx model can't be an omp agent (overflows on a tiny task). Reviewer/agent models need **>=128k context**. Prefer NON-reasoning instruct models for reviewers (avoids the loop). Cloudflare big-ctx options: `@cf/mistralai/mistral-small-3.1-24b-instruct` (128k, non-reasoning), `@cf/qwen/qwen3.8-27b` (256k, reasoning).

## Wire into omp (review panel)
- models.yml `router` provider: `auth: apiKey` (NOT bearer - omp rejects it), api: openai-completions, models list of `panel-<lab>` etc. Startup-registry: a running session won't see a new provider, but task-dispatched SUBAGENTS do re-resolve it.
- Reviewer profiles `~/.omp/agent/agents/reviewer-<lab>.md`: `model: router/panel-<lab>`, `tools: [read, grep, glob]`, read-only, independent-perspective prompt.
- `review-lead.md` orchestrator: `model: [ots/dsv4-flash-abliterated, router/panel-nemotron]` (list = fallback order; add the router fallback so it still runs when the Spark is mid-swap), `tools: [task, read, grep, glob, bash]`. Protocol = round-1 independent parallel fan-out -> reconcile/dedup -> round-2 cross-check the MERGED list (never let reviewers see each other in round 1 - anchoring kills diversity). Nested review-lead run is slow (~15 min) but works.
- Hermes: point it at `http://192.168.99.105:4000/v1` + router master key + the model name (e.g. `spark-glm`).

## Sync omp-config
Repo is `ots/omp-config` on Gitea (ssh://git@gitea.ots-int.net:2222) - NOT BadAd84 GitHub. omp-sync tracks models.yml now. Sync reliably by MIRRORING in Python (shutil copy of FILES + rm+copytree of DIRS) then committing with WINDOWS git via subprocess (`env SSH_AUTH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg`, `HOME=C:/Users/Adam`) - the bash tool alternates msys/WSL and WSL gpg lacks the YubiKey key so `omp-sync backup` can't sign there. Commits MUST be GPG-signed; if pinentry times out, the owner isn't at the desktop - defer + flag, never --no-gpg-sign.

## Verify
- Router: health 200 after restart = config valid; `curl /v1/models` (Bearer master key) lists the new model.
- End-to-end: dispatch the reviewer/model via `task` on a real diff and confirm real output (routing + hook + context all exercised). For a reasoning model, confirm the response carries NO reasoning block and the agent doesn't loop.

# Pick and wire new models into the OTS LiteLLM router

When swapping/adding models on the CT105 LiteLLM router (repo: ots-infra/router/litellm-config.yaml), follow this measured sequence:

1. **Pick candidates from an independent benchmark, not vibes.** artificialanalysis.ai/leaderboards/models (rendered page; parse bodyText rows: model, ctx, creator, Intelligence Index, cost-per-task). Match to model ids via OpenRouter GET /api/v1/models (gives context_length, max_completion_tokens, modalities, pricing incl. input_cache_read).
2. **Enforce the no-train constraint.** Free/trial endpoints of NVIDIA NIM train (s3.3(iv) of NVIDIA API Trial Terms) - banned. DeepSeek first-party API trains - banned. OpenRouter: require ZDR hosts via GET /api/v1/endpoints/zdr (per model_id -> provider set), and set the per-request filter on EVERY OpenRouter entry:
   `extra_body: {provider: {data_collection: "deny", zdr: true, quantizations: ["fp8","bf16","fp16"], sort: "price"}}`
   (quantizations excludes fp4 hosts; sort: price picks the cheapest qualifying host; glm-5.3-flash has four non-ZDR hosts so the filter matters even with account-wide ZDR on).
3. **model_info limits** come from OpenRouter's top_provider (context_length, max_completion_tokens), not guesses.
4. **Edit atomically:** python script with count==1 asserts per substitution; run against the repo copy AND /etc/litellm/config.yaml (same script, sys.argv[1]); back up the live file first (config.yaml.bak-<tag>-<ts>); add a one-line note to /root/INVENTORY.md about the backup.
5. **Verify:** systemctl restart litellm; wait for /health/liveliness 200; then a table-driven probe that calls EVERY model with a fixed arithmetic question and prints answer/model/latency/usage. Diff sha256 of repo vs live config - they must match exactly.
6. **Wire omp (~/.omp/agent/models.yml)** router provider ids to the same model set (atomic script, yaml round-trip check), and keep reviewer agent files' "voice" lines in sync with the actual model name.
7. **Commit signed** (git commit -S -F msgfile), push, run scripts/check-python.sh first.

Traps learned: sed -i on the repo copy only desyncs repo vs live (always run the same script on both); task subagents default to the session model - create a dedicated agent file per model under test and dispatch with that agent name, else you benchmark the wrong model; omp reviewer agents need bash in tools: [...] if the test requires running commands.

# Add a fixed-parameter LLM alias (LiteLLM router + omp profile)

Use when a sub-agent must hit a route with one parameter forced (thinking disabled, a concrete provider order, a service tier) and a model-name suffix cannot guarantee it.

## Why not the omp suffix
omp's `:off`/`:low`/`:max` effort suffix is not reliably transmitted through an OpenAI-compatible proxy: measured 2026-11-23 on `ots-litellm/ds4.1f-NOZDR:off`, the canary still spent 38 reasoning tokens and the session logged the thinking level as unset. Enforce the parameter server-side.

## Procedure
1. Read the block to copy on the router host (CT105): `ssh root@192.168.99.105`, block in `/etc/litellm/config.yaml` starting `- model_name: <existing alias>`.
2. Back up first: `cp /etc/litellm/config.yaml /root/config.yaml.bak-<tag>`.
3. Insert ONE new block with a script (never hand-edit in two passes: a duplicate `model_name` or a transform that replaces instead of appends silently removes the original alias). The script must: copy the original block verbatim, append a transformed COPY after it, and keep the original.
4. In the copy set: `model_name: <alias>-<tag>`; inside `extra_body` the fixed parameter (e.g. `reasoning: {enabled: false}`); `provider.order` as a LIST of cheap hosts with `allow_fallbacks: true`; `num_retries: 2`. Compare edits against `l.strip()` but build inserted lines from the original line's own indentation - comparing padded literals to stripped text is how the edits silently no-op.
5. Validate before restarting: `python3 -c` with `yaml.safe_load`, assert exactly one alias of each name, print the new block's `litellm_params` (mask the key).
6. `systemctl restart litellm; sleep 8; systemctl is-active litellm`.
7. Prove the parameter over the wire with an authenticated POST to `http://litellm.ots-int.net:4000/v1/chat/completions` (key from the env by name): the fixed alias must show the parameter's effect (e.g. `completion_tokens_details.reasoning_tokens == 0`) on the same prompt where the plain alias shows it non-zero; use a multi-thousand-token prompt too, because a pin that works on a short probe can still 429 on a long one.
8. Wire omp: a NEW alias is not in the discovery snapshot, so add an explicit `models:` entry under the provider in `~/.omp/agent/models.yml` (`id`, `name`, `reasoning: false`, `input`, `contextWindow`, `maxOutputTokens`), back the file up first, then point the sub-agent profile's `model:` at `ots-litellm/<alias>` with NO effort suffix.
9. Canary the profile with a one-line tool task, then confirm from the agent's session jsonl that `provider`/`model` are the new ones and `usage.reasoningTokens` is absent or 0.
10. Record the route's data policy and real fallback order in the profile's route notes; the router log (`journalctl -u litellm | grep <alias>`) names the upstream error when a request fails.

## Pitfalls measured in one sitting
- Two inserts produced two blocks with the same `model_name`, and one attempt deleted the original alias entirely (a transform that replaced instead of appended). Always assert both names exist exactly once after writing.
- `allow_fallbacks: false` with a single cheap host turns OpenRouter's `429 ... temporarily rate-limited upstream` into a stalled agent lane with no assistant messages; order 2-3 cheap hosts and keep fallbacks on.
- omp shows `cost 0` for proxied calls (the proxy sends no cost field); judge spend from the provider's credits endpoint, not omp's column.

# Add a LiteLLM alias that pins the request body and cheap providers

Use when a route needs a fixed `extra_body` (thinking disabled, a service tier, a provider order) that every caller gets whatever it asks for, or when an existing alias answers `429 ... temporarily rate-limited upstream` on long prompts.

## 1. Write a script on CT105 that edits the config, never edit it by hand

`/etc/litellm/config.yaml` is a YAML list under `model_list`, and hand edits have produced two blocks with the same `model_name` (LiteLLM then serves whichever it parsed; the parent's `yaml.safe_load` assertion is what catches it). Copy the template below to `/root/`, run it there, and keep the backup it makes:

```python
import yaml, shutil
p='/etc/litellm/config.yaml'
base='/root/config.yaml.bak-<name>'          # state BEFORE any new block
shutil.copyfile(base, p)                     # re-runnable: always start from the pre-change file
lines=open(p,encoding='utf-8').read().split('\n')
starts=[i for i,l in enumerate(lines) if l.strip().startswith('- model_name:')]
assert [lines[i].strip() for i in starts].count('- model_name: <source alias>')==1
s=[i for i in starts if lines[i].strip()=='- model_name: <source alias>'][0]
nxt=[i for i in starts if i>s]; e=nxt[0] if nxt else len(lines)
orig=lines[s:e]; new=[]
def ind(l): return l[:len(l)-len(l.lstrip())]
for l in orig:
    t=l.strip(); pad=ind(l)                  # compare STRIPPED text, insert with the line's own indent
    if t=='- model_name: <source alias>': new.append(f'{pad}- model_name: <new alias>')
    elif t=='api_key: os.environ/OPENROUTER_OPEN_KEY': new.append(l); new.append(f'{pad}num_retries: 2')
    elif t=='service_tier: flex':
        new += [f'{pad}reasoning:', f'{pad}  enabled: false', l]
    elif t=='- baidu': new += [l, f'{pad}- alibaba', f'{pad}- deepinfra/fp8/flex']
    elif t=='allow_fallbacks: false': new.append(f'{pad}allow_fallbacks: true')
    else: new.append(l)
res=lines[:s]+orig+['']+new+lines[e:]        # keep the source alias AND the new one
open(p,'w',encoding='utf-8',newline='\n').write('\n'.join(res))
cfg=yaml.safe_load(open(p,encoding='utf-8')); ns=[m['model_name'] for m in cfg['model_list']]
assert ns.count('<source alias>')==1 and ns.count('<new alias>')==1, ns
b=[m for m in cfg['model_list'] if m['model_name']=='<new alias>'][0]
print({k:(v if k!='api_key' else '<env>') for k,v in b['litellm_params'].items()})
```

The comparison must be against `l.strip()`: padded patterns silently match nothing, which leaves the block looking edited while the parsed params are unchanged. Always print the parsed block and check it.

## 2. Restart and verify

`systemctl restart litellm`, wait ~20-60 s (43 aliases take a while to load), then probe through the LAN with the client key from the environment:

- small prompt: expect a normal answer;
- 4k-token prompt: it must answer (this is the case that exposes a Baidu-only pin: `429 deepseek/deepseek-v4.1-flash is temporarily rate-limited upstream`);
- `usage.completion_tokens_details.reasoning_tokens` must be 0 when the body pins `reasoning.enabled: false`;
- a control call through the plain source alias should still show reasoning tokens, proving the pin does something.

## 3. Expose it to omp when the alias postdates discovery

omp discovers a litellm provider's models at session start. A new alias is invisible to an existing session (a subagent then fails with `No model selected`), so add an explicit entry under the provider in `~/.omp/agent/models.yml`:

```yaml
    models:
      - id: <new alias>
        name: "<human name>"
        reasoning: false           # true only if the alias still thinks
        input: [text, image]
        contextWindow: 1000000
        maxOutputTokens: 32768
```

Then a profile can use `model: ots-litellm/<new alias>` (no effort suffix: `:off` was measured NOT to reach this provider - a canary spent 38 reasoning tokens with it).

## 4. Policy line

When the alias points at a non-ZDR account, write the data policy into both places a caller looks: the alias comment in `config.yaml` and the profile that uses it (public/already-public material only).

# Serve a Claude Max sub to agent clients via the OTS LiteLLM router (CT105)

Two ways to give LiteLLM clients (Paperclip/opencode, n8n, etc.) Claude, and the gotcha that bites the flat-sub one.

## The 'extra usage' third-party classifier (why opencode-on-sub fails)
Anthropic inspects the TOP-LEVEL `system[]` of an OAuth request. First-party = system is the Claude Code identity (`You are Claude Code, Anthropic's official CLI for Claude.`) -> draws from the plan's full limits. Third-party = a client left its OWN identity in system[] (opencode's `You are opencode...`) -> drawn from a small third-party allowance, then HTTP 400 `Third-party apps now draw from your extra usage, not your plan limits`. omp's own traffic is shaped right so it never trips; any third-party client served through the omp auth-gateway leaks and trips it. Industry-wide (CLIProxyAPI #6432/#5934, 9router #4353, Hermes #79760, oh-my-pi #12487).

Diagnose by capturing the client's exact request (point it at a tiny logging HTTP server as a fake OpenAI backend) and bisecting the trigger: replace system with exactly-CC => OK; remove system => OK (gateway injects CC); move client system into a USER message => OK; leave any client text in system[] (even with CC prepended, or as a 2nd system block) => EXTRA-USAGE. So the fix is: client system must LEAVE system[] entirely.

## Fix A (flat-sub path, -sub models): local LiteLLM system-fold hook
`/etc/litellm/sub_normalize.py` = a `CustomLogger` whose `async_pre_call_hook` only touches `data['model']` ending in `-sub`: collect every `role=='system'` message's text (handle string OR content-parts array), fold it into the first user turn (prepend `folded + '\n\n' + user`), drop the system messages. Wrap in try/except returning data unchanged on error. Register as a LIST: `litellm_settings.callbacks: [content_flatten.proxy_handler_instance, sub_normalize.proxy_handler_instance]` (needs `PYTHONPATH=/etc/litellm` in the systemd unit). Unit-test the transform with `/opt/litellm/bin/python` (import the module, feed sample dicts, assert system removed + folded, -api untouched). Then restart litellm (wait ~22s; Prisma reconnect makes it slow to serve - a test at 10-13s gives false failures). Prove live with the client's REAL system prompt: `-sub` returns clean + journal shows the fold at debug level; the same system on an `-api`/non-sub model shows NO fold.

## Fix B (clean, no spoof): Claude Max API credits (-api models)
Max plans include claimable monthly API credit (Max5x $100, Max20x $200). Owner claims at claude.ai Settings>Billing > API credits > Link organization -> ONE Console org per plan (irreversible without support, same email), mints a WORKSPACE-SCOPED key (org-level keys 400 'not scoped to a workspace'), leaves auto-reload off / no card => hard fail-closed ceiling. LiteLLM uses `model: anthropic/<real-id>` + `api_key: os.environ/ANTHROPIC_CREDIT_KEY_N` straight to api.anthropic.com (NO omp). Pool N accounts by declaring each `-api` model_name once per key (LiteLLM load-balances the deployments). Get real model IDs from `GET api.anthropic.com/v1/models` (x-api-key + anthropic-version: 2023-06-01) - some gateway aliases (e.g. sonnet-4-5) are retired from the direct API.

## Naming scheme + chain
`-api` (credits, direct), `-sub` (flat sub via omp gateway :8766 + the hook), `-local` (Sparks), `-OR` (OpenRouter paid), `-free` (Cloudflare/Together free). `-sub` still routes through omp (broker :8765 holds the OAuth + 2 accounts, pools/rotates to the healthy one past a 7-day rate cap); `-api` bypasses omp. Fallback chain degrades `-sub -> -api -> glm5.3-local`.

## Config edits are live on CT105
Back up config.yaml first; edit with `/opt/litellm/bin/python` + yaml (model_info.tier only accepts 'free'/'paid' - a custom value 400s the whole deployment; use a free-form `data_policy` field instead). Resolve the master key from `general_settings.master_key` -> `/etc/litellm/.env`. Commit new hooks/config into `ots-infra/router/`.

## Risk framing (owner-confirmed)
The -sub hook is still the spoof; it works while requests are CC-shaped and Anthropic doesn't tighten the classifier (an arms race). -api credits have no such fragility. The owner's Claude ban was RE CONTENT not the harness (appealed once, spent), so the spoof itself is tolerated - but keep RE/cyber work OFF Claude entirely (route to local GLM/MiMo/DeepSeek).
