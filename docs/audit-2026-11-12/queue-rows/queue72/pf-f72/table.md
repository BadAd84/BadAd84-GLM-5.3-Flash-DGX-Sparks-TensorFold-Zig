# Long prompts and resumed conversations: this serve against production/SPEED-TARGET.md

## Rejected rows: 0


## Boot facts (a fresh boot an arm; production serves one shape: P=4, ctx 1,048,576)

| arm (boot shape) | boot s (to /health 200) | up s (zig-tp3) | MemAvailable GiB spark1 / 2 / 3 (after boot) | prompt cache GiB | stream windows, tokens | kept states the cache holds, tokens (derived) | production |
|---|---:|---:|---|---:|---:|---:|---|

Kept states: the prompt cache budget over 6,380 bytes a token a rank (the layout's arithmetic, every rank a full copy). This engine's /health has no pool_tokens: its KV is P windows of the context each plus that cache.

## First token (client time to first token; server prefill seconds; against production (P=4, ctx 1,048,576))

| arm (boot shape) | case | size | load | n | prompt tokens (median) | cached (median) | TTFT s median | p90 | prefill s median | production s | ours / production |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pf-f72 (P=4, ctx ?) | cold | 4096 | idle | 2 | 4,086 | 0 | 2.225 | 2.278 | 2.224 | not measured | - |
| pf-f72 (P=4, ctx ?) | cold | 8192 | idle | 2 | 8,192 | 0 | 4.069 | 4.177 | 4.066 | not measured | - |
| pf-f72 (P=4, ctx ?) | cold | 32768 | idle | 2 | 32,765 | 0 | 15.596 | 16.111 | 15.594 | not measured | - |

## Long conversation (production tier_chain.sh's turns; server prefill seconds; against production (P=4, ctx 1,048,576))

| arm (boot shape) | turn | how | prompt tokens | cached | new | resumed at (log) | TTFT s | prefill s | production turn | production prefill s | ours / production |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|---:|---:|

Production has a disk tier (turns 3 and 4 resume from it); a turn this serve could not resume shows its cached tokens as 0 and its prefill as a cold pass.

