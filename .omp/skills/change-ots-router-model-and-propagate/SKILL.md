---
name: change-ots-router-model-and-propagate
description: "Add/rename/retire a model behind the OTS LiteLLM router (CT105) and fan the change out to omp, reviewer agents, Gitea bots, and docs with verification; includes the -ZDR/-NOZDR alias convention, omp's litellm discovery (no hand list), the OpenRouter account ZDR guardrail, the flex service tier, and the route for a model whose own provider account is unusable."
---

# Changing a model behind the OTS LiteLLM router

Changing any model behind the OTS LiteLLM router (CT105, `litellm.ots-int.net:4000`) is a FAN-OUT, not a
one-file edit. Miss a consumer and it silently keeps the old model.

## Since 2026-11-21: omp discovers the list, so most renames need no omp edit

`~/.omp/agent/models.yml` no longer carries a hand-written `router:` block. The provider is `ots-litellm`:

```yaml
  ots-litellm:
    baseUrl: http://litellm.ots-int.net:4000/v1
    api: openai-completions
    auth: apiKey
    apiKey: "!C:/Users/Adam/tools/secret.cmd OMP_OTS_ROUTER_KEY"
    discovery:
      type: litellm
    modelOverrides:      # display names only, for cryptic ids
      ds4.1f-ZDR:
         name: "DeepSeek V4.1 Flash (ZDR)"
```

omp then reads `/model_group/info` (falling back to `/v2/model/info`, `/model/info`, `/v1/models`); the
ordinary router key is authorised for all of them, so no `allowed_routes` change is needed. Add, rename or
retire an alias on CT105 and it appears/disappears in omp with no config edit. Agent profiles still pin
`ots-litellm/<alias>:max`, so a RENAME still needs those updated (grep `agents/` + `WATCHDOG.yml`).

## The alias convention (owner, 2026-11-21)

The suffix names the data policy, not the vendor:
- `<model>-ZDR` - OpenRouter route with ZDR enforced on the account AND per request: `ds4.1f`, `mimo2.6`,
  `glm5.3f`, `gpt6.1`, `gemini3.8`, `grok4.7`, `kimi3.1`.
- `<model>-NOZDR` - the second OpenRouter account, no ZDR guardrail, open-source and already-public work
  only. While its `OPENROUTER_OPEN_KEY` in `/etc/litellm/.env` is empty it still bills the ZDR account, and
  the config comment says so.
- `-OR` and `-open` are retired names; never reintroduce them.
- `-local` (owned Sparks), `-api`/`-sub` (first-party API vs Claude Max subscription) keep their meaning.

## OpenRouter provider selection: two filters that decide the price

- **Service tier.** The cheap providers sit on the `flex` tier, filtered out of the default standard tier
  ("Filter by Tier Endpoint Rows removed ... flex"). Send `extra_body: {service_tier: flex}`; litellm passes
  it straight through.
- **The account-level ZDR guardrail.** OpenRouter refuses non-ZDR hosts with "ZDR violation (account
  settings)" for Baidu, StreamLake, Novita, Alibaba, SiliconFlow. No per-request flag overrides it; only a
  second account (or changing the account setting, which affects every route) reaches the $0.001/M cache host.
  Measured on the fleet's cache-heavy mix, that provider choice is the difference between about $200/week
  (flex + DeepInfra, ZDR) and $76/week (Baidu, no ZDR).

## Where a model lives (the full propagation list)

1. **Router config** - BOTH `~/Gitea/ots-infra/router/litellm-config.yaml` (repo) AND
   `/etc/litellm/config.yaml` (live on CT105). Keep them byte-identical (`sha256sum` both, strip CR).
2. **omp** - `~/.omp/agent/models.yml`: only `modelOverrides` names now, plus agent profiles
   (`~/.omp/agent/agents/*.md`, `model: ots-litellm/<alias>:max`) and `WATCHDOG.yml`.
3. **RULES.md** - S9/S10 if the alias is named there (historical measurement text stays as written).
4. **Gitea PR bots** - CT107 `/root/pr-review/docker-compose.yml` `CONFIG__MODEL: openai/<alias>`; recreate
   with `docker compose up -d --no-deps reviewN` and mirror the redacted repo export.
5. **Docs** - `router/README.md` (its convention table documents every suffix), `router/omp-models.snippet.yaml`,
   `docs/FREE-LLM-ROUTES.md` (cost comparisons), `docs/AI-MODEL-ACCESS-ARCHITECTURE.md`, `docs/gitea-pr-reviewer.md`.

## Procedure

1. Edit the repo `litellm-config.yaml` with a STAGED python script (see traps), assert the model list via `yaml.safe_load`.
2. `scp` the script or the config to CT105, back up (`cp ...bak-<reason>-<ts>`, record in `/root/INVENTORY.md`),
   validate with `yaml.safe_load`, `systemctl restart litellm`, wait for `/health/liveliness` == 200.
3. VERIFY: `curl /v1/models` lists the new alias and not the old; probe each changed alias (`17*23` -> 391).
4. Propagate per the list above; grep for the old name afterwards, excluding `work/` and `router/litellm-config.yaml` history.
5. GPG-sign commit, push.

## Traps that cost real time

- **Deleting a YAML provider block by line numbers eats the next block's comment header** (the block ends at the
  next `  <key>:` line, and the comment above that key belongs to it). Anchor on the previous and next keys, diff
  against a backup afterwards - this clipped `hunch`'s comment and had to be restored from the backup.
- **CRLF after `git checkout`/`git restore`**: every edit script must `replace("\r\n", "\n")` and write `newline="\n"`.
- **Never inline-quote through nested ssh/heredocs.** Stage a script as a FILE, `scp`, run it.
- **Partial block removal corrupts YAML** - remove the whole block, assert one anchor match.
- **Secrets never printed**: keys live in `/etc/litellm/.env`; `agent.db` tables hold live keys, never dump them.
- **Local Spark-serve aliases fail when those serves are down** (`glm5.3-local`, `qwen3.8-local`); expected, not a config fault.
- **A live config that grows an alias the repo never got is a defect, not noise** - diff the two alias lists with `comm`.

## Cheap verification of a new model's fitness

Benchmarks pick candidates; capability is proven by running the REAL agent on a small graded task (a 20-byte
binary parse with byte-exact self-verification caught refusals and correctness for MiMo vs DeepSeek).
Refusal behaviour is PER-MODEL, not per-storefront: Anthropic weights filter cyber tasks at the provider on
OpenRouter too (Opus 5.5 blocks; Opus 4.8 / GPT-6.1 Sol / MiMo pass the same brief).
