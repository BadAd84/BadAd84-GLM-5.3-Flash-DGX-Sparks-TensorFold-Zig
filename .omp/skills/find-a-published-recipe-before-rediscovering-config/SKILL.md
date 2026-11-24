---
name: find-a-published-recipe-before-rediscovering-config
description: "Before deriving a serving config or concluding a capability is missing, find an existing published recipe for the same engine by searching its engine-specific env var names, then read its base config and patches."
---

# Find a published recipe before rediscovering a config

Use when a model+engine combination needs tuning (streams, context, KV pool, drafts) or when a capability looks
missing. Someone else usually runs it already, with a config you can copy instead of deriving.

## 1. Search by ENGINE-SPECIFIC env var names, not product names

Product-name searches return blog posts and the wrong lineage. Engine env vars are unique fingerprints:

- TensorFold **Zig** engine: `TF_GLM_WORLD`, `TF_GLM_RANK`, `TF_GLM_*` families
- TensorFold **Python** lineage (v0.6.x recipes): `--tp`, `--rank`, `--master`
- vLLM: `VLLM_*`; llama.cpp: `LLAMA_*`

```sh
gh search code "TF_GLM_WORLD" --limit 20 --json repository,path \
  --jq '.[] | "\(.repository.nameWithOwner) \(.path)"'
```

`gh search code` field is `repository.nameWithOwner`; `fullName`/`full_name` return null and look like a failed search.

## 2. Read the config, not the prose

Recipes hide the real defaults in a sourced config file. Fetch the file that sets them:

```sh
gh api repos/<owner>/<repo>/contents/<dir>/scripts/config.sh --jq .content | base64 -d
gh api repos/<owner>/<repo>/contents/<dir>/patches --jq '.[].name'
```

Look for: parallel/stream count, context, KV pool size, prompt-cache size, drafts on/off, max tokens, and the
pinned engine commit. List any `patches/` directory - it is the other author's equivalent of your own patch series.

## 3. Separate what is portable from what is not

Portable: configuration (streams, context, pool sizing, flags), patch ideas, and the harness shape.
NOT portable: throughput/timing numbers when the checkpoint (quant), rank count or engine lineage differs. Say which
is which before quoting anything - a 2.05bpw TP=1 recipe's tok/s says nothing about a 4bpw TP=3 serve.

## 4. Then diff against your own config

Put their defaults beside yours in a table, and treat every difference as either a deliberate choice or a defect.
A number that is 1 where a published recipe uses 4 is not a design decision, it is a knob somebody forgot.

## Why this is step one

Measured 2026-10-27: a whole session was spent tracing whether cross-stream batching existed in a Zig engine, when
`gh search code "TF_GLM_WORLD"` returned the only published Zig GLM recipe and its `scripts/config.sh` answered the
adjacent question directly (`PARALLEL=4`, against our `1`). Ten minutes of searching would have preceded, and
redirected, an hour of source archaeology.
