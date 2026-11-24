---
name: serve-dense-instruct-model-on-dgx-spark
description: "Serve an ordinary HuggingFace dense/instruct model (DeepSeek-R1 distill, Qwen3.x, Llama - NOT the DSV4 MoE) on a single DGX Spark/GB10 via vLLM, past the four traps that each crash the boot: the transformers-5.9.0 detok bug, the FLASH_ATTN PTX crash, the vision-ViT PTX crash, and the bandwidth-bound slow decode. Use when standing up any non-DSV4 checkpoint on a Spark for the RE base bake-off."
---

# Serve a dense/instruct model on a DGX Spark (GB10/sm_121)

SSOT: `ots-infra/docs/SPARK-DENSE-MODEL-SERVING.md`. Companion to `DGX-SPARK-DSV4.md` (that's the MoE).
Orchestrate via **CT106 `agent-stack`** (`pct exec 106 -- su - adam -c '...ssh adam@spark1.ots-int.net...'`;
CT106 has omp + a Spark SSH key). Helper: `work/spark.py` (`spark.on(host, cmd)`).

## The four traps (all crash the boot; all hit 2026-09-06)

1. **Detok bug (Ġ/Ċ for spaces).** transformers 5.9.0 in the bjk110 image mis-builds the pre-tokenizer
   for **2025-era** tokenizers (Qwen2/Qwen3/Llama). Diagnose: `AutoTokenizer.decode` drops spaces but
   `tokenizers.Tokenizer.from_file(...).decode` is correct -> it's the transformers wrapper.
   Fix: build `vllm-spark-tok457` once per box:
   ```Dockerfile
   FROM ghcr.io/bjk110/vllm-spark:latest
   RUN /opt/env/bin/python3 -m pip install --no-cache-dir transformers==4.57.1
   ```
   Use tok457 for 2025 models. Use the **base** image (tf 5.9) for **2026** models (e.g. Qwen3.8-27B
   `Qwen3_5ForConditionalGeneration`) - 4.57.1 lacks the arch, and their 5.x-native tokenizer is fine.

2. **FLASH_ATTN PTX crash** (`cudaErrorUnsupportedPtxVersion` from `flash_attn_varlen_func`). The
   `VLLM_ATTENTION_BACKEND` env is IGNORED; pass the CLI flag **`--attention-backend TRITON_ATTN`**.

3. **Vision ViT PTX crash** (multimodal models, from `mm_encoder_attention.py`/`vit_flash_attn`).
   `--attention-backend` only covers the LM. Add **`--mm-encoder-attn-backend TORCH_SDPA`**.

4. **Slow decode** (~15 tok/s dense bf16; CUDA graphs don't help - bandwidth-bound, ~273 GB/s LPDDR5X).
   Add **`--quantization fp8`** (dynamic Cutlass FP8) -> ~2x. 32B bf16 is ~4 tok/s (impractical).

## Launch template
```
docker run -d --name bake --gpus all --ipc=host --network host \
  -v /home/adam/.cache/huggingface:/hf --entrypoint /opt/env/bin/vllm <IMG> \
  serve <snapshot_path> --served-model-name <name> --host 0.0.0.0 --port 8891 \
  --max-model-len 40960 --gpu-memory-utilization 0.6 \
  --attention-backend TRITON_ATTN --quantization fp8 [multimodal: --mm-encoder-attn-backend TORCH_SDPA]
```
- R1-distill/Qwen3-8B (2025) -> IMG `vllm-spark-tok457`, NO tool parser (they don't tool-call), request
  temp 0.6/top_p 0.95 (greedy loops; they never emit `stop`). Reasoning is in `message.reasoning`.
- Qwen3.8-27B (2026) -> IMG base bjk110, `--mm-encoder-attn-backend TORCH_SDPA --enable-auto-tool-choice
  --tool-call-parser qwen3_xml`, and request `chat_template_kwargs:{enable_thinking:false}` (thinking-on
  suppresses the tool call; the tool format is `<function=name><parameter=x>` = qwen3_xml, NOT hermes).

## Verify
`curl :8891/v1/completions` detok clean (no Ġ); for agents, a tool-call probe returns `tool_calls`.
Update `~/INVENTORY.md` on the box (standing rule) with the image + `docker rm -f bake` teardown.
