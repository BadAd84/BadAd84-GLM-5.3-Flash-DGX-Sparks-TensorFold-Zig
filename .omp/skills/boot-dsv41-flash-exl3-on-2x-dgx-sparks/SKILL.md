---
name: boot-dsv41-flash-exl3-on-2x-dgx-sparks
description: "Boot the MiaAI-Lab DeepSeek-v4.1-Flash-EXL3-2x-DGX-Sparks recipe on the OTS 2x DGX Sparks past the three walls the stock recipe hits on our kit (NFS overlayfs export, pre-staged-vs-fresh-copy preflight, missing engram config.json), using local-copy-both-nodes rsync. Use to serve/restore DSV4.1 on spark1:8888 (mutually exclusive with GLM on 8889)."
---

Serve MiaAI-Lab **DeepSeek-v4.1-Flash-EXL3** (stock 2.9bpw) on the OTS 2x DGX Sparks (spark1 head `192.168.99.101` / mesh `192.168.100.10`; spark2 worker mesh `192.168.100.11`). Repo: `~/dsv41-flash-2spark` on spark1. Serves `DeepSeek-v4.1-Flash-EXL3` on **spark1:8888**, TP=2, kv=native-fp4, DSpark spec k=3.

**Mutually exclusive with GLM** (both need TP=2 across both GB10s). SSH is flaky — use tmux scripts on the box; `export SSH_AUTH_SOCK=C:/Users/Adam/AppData/Local/gnupg/agent-gui/S.gpg-agent.ssh.cyg`.

## The three walls (stock recipe fails on our kit)

**1. NFS default fails — use rsync (local copy on BOTH nodes).** `WEIGHT_SYNC=nfs` reuses a *live* kernel-nfsd exporter (`vllm-fn-nfs`/`glm53-nfs`) exporting the ext4 HF cache. We run none, so `start.sh` stands up its own `dsv41-exl3-nfs` container that only bind-mounts `/export/<subdir>` and exports the **overlayfs** parent `/export` → `exportfs: /export does not support NFS export`, crash-loop. Fix: set `WEIGHT_SYNC=rsync` **in `.env`** (it is sourced FROM `.env`, so it CANNOT be overridden on the command line). Worker gets a local copy at `~/.cache/dsv41-flash-exl3/{model,engram-src}`. Needs ~387 G free on spark2 — clean old model weights first (`~/INVENTORY.md`).

**2. Preflight demands 385 G *free* even when weights are pre-staged.** The rsync preflight (`start.sh`, the `rsync)` case in `preflight()`) computes `need_b = du(MODEL_HOST)+engram` and dies if worker free < that, without crediting already-present weights. Fix: pre-stage, then boot with `SKIP_SYNC=1`, AND wrap that space-check block in a `SKIP_SYNC` guard (`if [ "${SKIP_SYNC:-0}" != "1" ]; then … fi`; backup `start.sh.orig-preflight`). The auto "already in sync — rsync skipped" detector then no-ops the transfer.

**3. Missing engram `config.json`.** `download.sh` fetches only engram shards 47+48 from `deepseek-ai/DeepSeek-V4.1-Flash`, NOT its `config.json`. The backend `/opt/dsv41/engram_file_backend.py` reads it for `engram_layer_ids`/`engram_num_embeddings` → worker dies `FileNotFoundError`. Fix:
```
CFG=$(python3 -c "from huggingface_hub import hf_hub_download; print(hf_hub_download('deepseek-ai/DeepSeek-V4.1-Flash','config.json'))")
cp "$CFG" ~/.cache/vllm-dsv41-flash-exl3/engram-src/config.json          # head bind (prepared slim dir)
scp "$CFG" adam@192.168.100.11:~/.cache/dsv41-flash-exl3/engram-src/config.json  # worker copy
```
(engram_layer_ids=[1,14], engram_num_embeddings=[384006168,384016682]). The full 7.4 MB or the slim 403-byte index both work — only config.json is missing.

## Pre-stage (no GLM downtime)
rsync while GLM still serves — pure file copy over the fabric (~500 MB/s):
```
rsync -a --partial --inplace ~/dsv41-flash-2spark/model/       adam@192.168.100.11:~/.cache/dsv41-flash-exl3/model/
rsync -a --partial --inplace ~/dsv41-flash-2spark/engram-src/  adam@192.168.100.11:~/.cache/dsv41-flash-exl3/engram-src/
```

## Boot
Stop GLM + disable its watchdog first (else it fights the boot for the GPUs):
```
systemctl --user disable --now glm-watchdog
docker rm -f glm53-exl3-head; ssh spark2 'docker rm -f glm53-exl3-worker'
sudo -n /usr/local/bin/glm-mem-hygiene.sh
cd ~/dsv41-flash-2spark && SKIP_SYNC=1 SKIP_BUILD=1 ./start.sh   # in tmux; ~7 min load + graph capture
```
`SKIP_BUILD=1` is required (repo stamp != image stamp `8c01a8543ff7`, else it recompiles the SM121 ext).
Then `docker update --restart unless-stopped dsv41-exl3-head` (+worker) for overnight recovery.

## Verify
```
curl -s spark1:8888/v1/models                       # -> DeepSeek-v4.1-Flash-EXL3
curl -s spark1:8888/v1/chat/completions -d '{"model":"DeepSeek-v4.1-Flash-EXL3","max_tokens":16,"messages":[{"role":"user","content":"17*19="}]}'  # 323
```
Log root cause on failure: `~/dsv41-flash-2spark/logs/worker.log` (worker/rank1 crash) + `head.log`.

## omp wiring
Provider `ots-dsv41` in `~/.omp/agent/models.yml`: baseUrl `http://spark1.ots-int.net:8888/v1`, id `DeepSeek-v4.1-Flash-EXL3`, contextWindow 600000, reasoning:false, `extraBody.chat_template_kwargs.thinking:false` (tool-clean). Thinking defaults ON server-side; flip to true to try its reasoning.

## Restore GLM
```
cd ~/dsv41-flash-2spark && ./start.sh stop
systemctl --user enable --now glm-watchdog; SKIP_BUILD=1 spark-model glm start
```
