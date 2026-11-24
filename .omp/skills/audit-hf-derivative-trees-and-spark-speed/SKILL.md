---
name: audit-hf-derivative-trees-and-spark-speed
description: "Audit HuggingFace finetune/quant/merge trees of candidate models via the HF API to find use-case-aligned variants (coding/uncensored/cyber), verify them, and estimate their decode speed on the DGX Sparks from active-params + MTP. Use for model-selection sweeps for the Spark fleet."
---

# Audit HF derivative trees + estimate Spark decode speed

Use when picking a model to run on Adam's 2xDGX Spark fleet, or asked 'is there a
finetune/gem of X aligned to what we do' (RE/coding/cyber/uncensored). Runs
entirely from the harness via the public HF API (no auth for public repos).
Do it in `eval` with urllib; the API is reachable from Adam's Windows box.

## 1. Resolve base repos (names are often post-cutoff)
`GET https://huggingface.co/api/models?search=<name>&sort=downloads&direction=-1&limit=8`
-> read `id`,`downloads`,`likes`. Confirm the canonical repo (e.g. `Qwen/Qwen3.8-27B`,
`zai-org/GLM-5.3-Flash`, `deepseek-ai/DeepSeek-V4-Flash-0731`). Note which requested
names DON'T exist (e.g. no `GLM-5.3-Flash-Next`).

## 2. Enumerate the derivative tree (the model-tree API works)
Validate the filter on a KNOWN model first, then per base repo pull all of:
`?filter=base_model:finetune:<repo>`, `:quantized:`, `:merge:`, `:adapter:` (limit=1000,
paginate via the `Link` rel="next" header) PLUS a broad `?search=<basename>` to catch
untagged derivatives. Dedupe by id, track which relation(s) each came from.

## 3. Score by use-case keywords, split real-models vs quants
Id+tags keyword buckets: CODE(coder/code/coding/swe), UNCAP(abliterat/uncensor/heretic/
decensor/derefus), SEC-RE(reverse/malware/exploit/ctf/pentest/hack/cyber/ghidra/redteam),
AGENT(agent/toolcall/function), REASON(reason/think/distill). A repo is a real new model
if its relation set has finetune/merge/adapter (not just a quant). Rank aligned ones by
downloads. NOTE false positives: 'binary' quant naming, and 'DFlash2'/'DSpark-Agentic'
names are MTP DRAFTERS/adapters (~1.9B), not coding models - verify via safetensors.total.

## 4. VERIFY every finalist (names lie - never report a card's claim as fact)
`GET /api/models/<id>?full=true` -> downloads, likes, lastModified, gated, cardData.license,
cardData.base_model, safetensors.total (param count), siblings (files). Fetch the README
(`/<id>/raw/main/README.md`, strip YAML frontmatter) to read what it actually is +
license + method. Quality claims in cards are the AUTHOR'S - label them unverified; the
gate is Adam's agentic oracle-bench on real tasks.

## 5. Active params + MTP + Spark speed
- Fetch `config.json` (multimodal wrappers nest real config under `text_config`).
- **Active params drive decode speed.** TRUST the card's '# Activated params', NOT a
  config hand-calc (it under-counts: Flash-Next card=6B vs calc ~3.3B).
- **MTP head key varies by arch:** scan for {mtp, mtp_num_hidden_layers,
  num_nextn_predict_layers, nextn, draft, eagle}. qwen4_exp->mtp; glm5_next->
  num_nextn_predict_layers; qwen3_moe/qwen3_next coders -> none.
- **Spark decode estimate** (calibrated off measured DSv4 = 30 tok/s raw TP2):
  `tok/s ~= 0.36 * BW / (active_B * bytes_per_param)`. 1 Spark ~273 GB/s; 2x TP2
  ~546 GB/s; NVFP4/4-bit=0.5 B/param. MTP(1-layer) x~1.4-1.7. Fit: total_B*0.5 vs
  128 GB/Spark. Dense models are bandwidth-punished on the low-BW Spark.

## 6. Benchmarks to compare capability (not just speed)
Primary = official HF card eval tables (parse the HTML `<table>`: header row = the
comparison models). Same-harness only WITHIN one card. Cross-card SWE-bench Pro deltas
<3-4 pts = noise (different harness/scaffold). Independent cross-check = Artificial
Analysis Intelligence Index. Key 2026 finding: newer GENERAL models out-code older
dedicated coders on agentic SWE-bench Pro - verify, don't assume specialist>general.

## Gotchas
- Reuse ONE urllib helper; don't reconnect per call.
- config-derived active params under-count; card figure wins.
- single-key MTP check = false negatives (keys differ by arch).
- 'DFlash2'/'-Agentic' repos are drafters/adapters, not models.
- vendor cards self-grade competitors with weak harnesses; trust AA Index + own bench.
