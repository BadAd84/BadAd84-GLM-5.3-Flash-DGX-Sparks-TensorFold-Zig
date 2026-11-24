---
name: wire-claude-max-credits-into-litellm-router
description: "Serve Claude to third-party orchestrators (Paperclip/opencode) via Anthropic Max monthly API credits on the OTS LiteLLM router (CT105) - the sanctioned no-spoof, no-ban path; not the omp gateway spoof."
---

# Wire Claude Max API credits into the OTS LiteLLM router

Use when serving Claude to a third-party orchestrator (Paperclip, opencode, etc.) without identity-spoof/ban risk. The omp auth-gateway spoofs the Claude Code identity for omp's OWN traffic, but forwarding a third-party client's system prompt trips Anthropic's 'extra usage' billing classifier (it inspects the top-level system[] for non-Claude-Code content). The sanctioned fix is a real API key funded by the Max plan's monthly credits.

## Why credits beat the gateway-spoof
- A real Console API key is Anthropic's recommended third-party auth: no spoof, the 'extra usage' classifier never fires, and commercial terms mean no training on inputs (safer than the consumer sub).
- The owner's Claude ban was for RE/cyber CONTENT, not harness/spoofing - but strengthening the spoof to route a 3rd-party client's traffic against the sub is what Anthropic's policy enforces against. Credits sidestep it entirely.
- RE work still routes to GLM/MiMo/local, never Claude.

## Owner-only steps (Console, their logins)
1. Per Max account: claude.ai > Settings > Billing > 'API credits' > Link organization > create a DEDICATED Console org (ONE org per plan, IRREVERSIBLE without support; sign into Console with the SAME email). Max5x=$100/mo, Max20x=$200/mo.
2. In each org, mint an API key that is WORKSPACE-SCOPED (an org-level/unscoped key returns 400 'not scoped to a workspace' and needs an anthropic-workspace-id header - just re-mint it scoped). Leave auto-reload OFF and add no card -> hard fail-closed ceiling (requests stop when credits exhausted, never charge).
3. Drop keys into /etc/litellm/.env as ANTHROPIC_CREDIT_KEY_1/2 (never paste in chat).

## Router wiring (CT105 /etc/litellm/config.yaml)
- Query real model IDs: `curl https://api.anthropic.com/v1/models -H "x-api-key: $KEY" -H 'anthropic-version: 2023-06-01'` (IDs differ from gateway aliases; some like sonnet-4.5 are retired from the direct API).
- For each Claude model, define TWO deployments with the SAME model_name (one per key) to pool both accounts' credits:
  `- model_name: opus-5.5-api`
  `  litellm_params: {model: anthropic/claude-opus-5-5, api_key: os.environ/ANTHROPIC_CREDIT_KEY_1}`  (+ a 2nd with _KEY_2)
  `  model_info: {data_policy: commercial-api-credit, tier: paid}`
- model_info.tier ONLY accepts 'free'|'paid' (a custom value fails validation and silently drops the deployment); put real policy in free-form data_policy.
- Add fallback in router_settings.fallbacks: each -api model -> ['glm5.3-local'] so orchestration degrades to free local when credits run dry.
- After `systemctl restart litellm`, WAIT ~20s before testing (Prisma reconnect) or calls return empty.

## OTS naming scheme (suffix by backend)
-api = Claude via credits (anthropic/); -sub = Claude via omp gateway :8766 (flat sub); -local = owned Sparks (glm5.3-local@192.168.99.11:8888, qwen3.8-local@192.168.99.16:8888, model openai/<id>, api_key none); -OR = OpenRouter paid; -free = genuinely free (Cloudflare/Together). Confirm free-vs-paid from OpenRouter /api/v1/models pricing before labelling -free.

## Flat-sub headroom
-sub 429 'rate_limit_error' with a multi-day retry-after = that account's 7-day cap, not a wiring fault (gateway still reaches Anthropic). Log a 2nd account into the broker via the CT105 login GUI (https://apiauth.ots-int.net, incognito so OAuth picks the 2nd account); the broker pool auto-skips the rate-limited credential.

## Paperclip downstream
After renaming router models, Paperclip's connection picker (static config.ai.routing.models in its embedded Postgres) AND each agent's model field reference the OLD names and break - refresh both. Repoint orchestrator agents to -api (credit) models; keep a cross-family reviewer (-OR/-local).
