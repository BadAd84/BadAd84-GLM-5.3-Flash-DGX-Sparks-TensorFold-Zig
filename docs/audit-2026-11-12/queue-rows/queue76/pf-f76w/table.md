# Long prompts and resumed conversations: this serve against production/SPEED-TARGET.md

## Rejected rows: 0


## Boot facts (a fresh boot an arm; production serves one shape: P=4, ctx 1,048,576)

| arm (boot shape) | boot s (to /health 200) | up s (zig-tp3) | MemAvailable GiB spark1 / 2 / 3 (after boot) | prompt cache GiB | stream windows, tokens | kept states the cache holds, tokens (derived) | production |
|---|---:|---:|---|---:|---:|---:|---|

Kept states: the prompt cache budget over 6,380 bytes a token a rank (the layout's arithmetic, every rank a full copy). This engine's /health has no pool_tokens: its KV is P windows of the context each plus that cache.

## First token (client time to first token; server prefill seconds; against production (P=4, ctx 1,048,576))

| arm (boot shape) | case | size | load | n | prompt tokens (median) | cached (median) | TTFT s median | p90 | prefill s median | production s | ours / production |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pf-f76w (P=4, ctx ?) | cold | 4096 | idle | 1 | 4,095 | 0 | 2.118 | 2.118 | 2.117 | not measured | - |
| pf-f76w (P=4, ctx ?) | cold | 8192 | idle | 1 | 8,197 | 0 | 3.772 | 3.772 | 3.771 | not measured | - |
| pf-f76w (P=4, ctx ?) | cold | 32768 | idle | 1 | 32,794 | 0 | 14.568 | 14.568 | 14.566 | not measured | - |

## Long conversation (production tier_chain.sh's turns; server prefill seconds; against production (P=4, ctx 1,048,576))

| arm (boot shape) | turn | how | prompt tokens | cached | new | resumed at (log) | TTFT s | prefill s | production turn | production prefill s | ours / production |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|---:|---:|

Production has a disk tier (turns 3 and 4 resume from it); a turn this serve could not resume shows its cached tokens as 0 and its prefill as a cold pass.

