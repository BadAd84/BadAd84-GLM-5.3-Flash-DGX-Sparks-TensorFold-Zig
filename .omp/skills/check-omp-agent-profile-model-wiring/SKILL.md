---
name: check-omp-agent-profile-model-wiring
description: "Verify an omp sub-agent profile actually runs: does its declared model id resolve to a configured provider and a live endpoint, before dispatching it anything."
---

# Check an omp agent profile's model wiring

Use when asked whether an agent profile works ("does the X sub-agent work?", "can I dispatch to X?"), or before
dispatching to a profile that has not been exercised. A profile is a markdown file in `~/.omp/agent/agents/<name>.md`
whose frontmatter names a model as `provider/model[:thinking]`.

## Procedure

1. Read the profile's model id:
   ```
   sed -n '1,10p' ~/.omp/agent/agents/<name>.md      # frontmatter: model: provider/model:max
   ```
2. Resolve `provider/model` against `~/.omp/agent/models.yml`. Providers are the top-level keys under
   `providers:`; models are the entries under each provider. A quick map (provider, then matching lines):
   ```
   python - <<'EOF'
   import re
   text = open(r"<home>/.omp/agent/models.yml", encoding="utf-8").read().splitlines()
   provider = None
   for i, line in enumerate(text, 1):
       if re.match(r"^  [A-Za-z0-9_.-]+:\s*$", line):
           provider = line.strip().rstrip(":")
       if "<search term>" in line.lower():
           print(i, f"[{provider}]", line.strip())
   EOF
   ```
3. If the provider name in the profile appears nowhere in `models.yml`, the profile cannot start: the model id
   resolves to nothing. That is the usual failure - a profile written against a provider that was later renamed,
   removed, or never added.
4. Check the alias actually exists at the far end. Router aliases live on CT105
   (`ssh root@192.168.99.105 'grep -n -A6 "model_name: <alias>" /etc/litellm/config.yaml'`); a local
   `ots-glm`/`ots-qwen38`/`ots-ds41` serve is called directly at `spark<N>.ots-int.net:8888`.
5. Check the endpoint is live before believing a dispatch will work - for a direct serve,
   `curl -s -m 5 http://spark1.ots-int.net:8888/v1/models`; for the router, the same on
   `litellm.ots-int.net:4000`.
6. Fix by pointing the profile at a provider+alias that exists (e.g. `model: ots-litellm/<alias>`), then confirm
   with a single cheap dispatch.

## Traps

- A profile that reads plausibly is still broken if its provider is not in `models.yml`: the failure appears at
  dispatch time as a model-resolution error, not as a profile error.
- Do not assume a vendor CLI exists because a vendor-named directory does (`~/.kimi-webbridge`,
  `~/.kimi-work` hold a webbridge daemon and bundled tools, not credentials and not an account login).
- Check the model, not the description: descriptions drift (a profile describing "Kimi K3" may be the only place
  K3 is named, while the configured alias is K3.1 Pro).
- Owner policy can forbid a model even when it is wired: check the standing rules for the engine before
  reporting a profile as usable.
