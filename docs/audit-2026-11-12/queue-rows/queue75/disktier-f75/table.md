# GLM conversation states on disk at TP=3 (--learn-conversations): resumes against cold replies

## Disk tier checks failed: 2

- k1 M32000/t3 evicted: SOURCE expected disk, resumed from ram
- k1 M120000/t3 evicted: SOURCE expected disk, resumed from ram

## Rejected rows: 0


## Boots

| boot | arm | P | context | image | boot s | store: states, MiB of cap | ranks' parts | a save stages up to | store directory | MemAvailable GiB spark1 / 2 / 3 |
|---|---|---:|---:|---|---:|---|---:|---:|---|---|
| k1 | learn | 4 | 1,048,576 | glm53-zig:v129za | 121.5 | 0, 0 of 131,072 | 3 | 7,429 MiB | /root/.cache/huggingface/glm53-zig-learn/f75/4f58791fab8c6602 | 33.0 / 46.0 / 46.2 |
| k2 | learn | 4 | 1,048,576 | glm53-zig:v129za | 123.5 | 7, 8,580 of 131,072 | 3 | 7,429 MiB | /root/.cache/huggingface/glm53-zig-learn/f75/4f58791fab8c6602 | 33.0 / 45.6 / 46.1 |
| k3 | learn | 4 | 1,048,576 | glm53-zig:v129za | 119.0 | 10, 11,266 of 131,072 | 3 | 7,429 MiB | /root/.cache/huggingface/glm53-zig-learn/f75/4f58791fab8c6602 | 32.9 / 45.8 / 46.3 |
| ref | ref | 4 | 1,048,576 | glm53-zig:v129za | 118.0 | - | - | - | - | 41.2 / 53.8 / 53.8 |

## Turns: what each resumed from, and its reply against a cold server's

| boot | turn | case | expected | resumed from | prompt tokens | cached | newest kept | first token s | server prefill s | disk read MiB in ms | saves written (MiB, write ms, drain s) | token_sha | cold reference | gate |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|
| k1 | M32000/t1 | cold | cold | cold | 32,038 | 0 | 0 | 14.86 | 14.86 | - | - | 568c5dc36654 | 568c5dc36654 | equal |
| k1 | M32000/t2 | from RAM | ram | ram | 32,074 | 32,035 | 30,720 | 0.22 | 0.14 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k1 | M120000/t1 | cold | cold | cold | 120,604 | 0 | 0 | 55.66 | 55.65 | - | - | 568c5dc36654 | 568c5dc36654 | equal |
| k1 | M120000/t2 | from RAM | ram | ram | 120,640 | 120,601 | 118,784 | 0.35 | 0.15 | - | - | 759afd450e25 | 759afd450e25 | equal |
| k1 | L/t1 | cold | cold | cold | 596,176 | 0 | 0 | 334.71 | 334.64 | - | - | d6df00924459 | d6df00924459 | equal |
| k1 | L/t2 | from RAM | ram | ram | 619,437 | 595,968 | 595,968 | 12.74 | 12.72 | - | - | 625091ff9968 | 625091ff9968 | equal |
| k1 | M32000/t3 | after eviction | disk | ram | 32,151 | 32,035 | 30,720 | 0.23 | 0.23 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k1 | M120000/t3 | after eviction | disk | ram | 120,712 | 120,601 | 118,784 | 0.24 | 0.23 | - | - | 759afd450e25 | 759afd450e25 | equal |
| k2 | L/t3 | after SIGKILL of every rank | disk | disk | 642,693 | 619,434 | 618,496 | 14.93 | 12.41 | - | - | a256ed41e4fd | a256ed41e4fd | equal |
| k2 | L/t3q | quote probe | ram | ram | 642,863 | 642,690 | 641,024 | 0.34 | 0.32 | - | - | 17f7ec3a2857 | 17f7ec3a2857 | equal |
| k2 | M32000/t4 | after SIGKILL of every rank | disk | disk | 32,228 | 32,035 | 30,720 | 0.57 | 0.28 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k2 | M120000/t4 | after SIGKILL of every rank | disk | disk | 120,784 | 120,601 | 118,784 | 0.93 | 0.28 | - | - | 759afd450e25 | 759afd450e25 | equal |
| k2 | S120000/t1 | flush | cold | cold | 120,356 | 0 | 0 | 55.81 | 55.81 | - | - | 568c5dc36654 | 568c5dc36654 | equal |
| k3 | L/t4 | after a clean restart | disk | disk | 665,911 | 642,690 | 641,024 | 18.89 | 14.84 | - | - | f4f1199f1f3b | f4f1199f1f3b | equal |
| k3 | S120000/t2 | flushed | disk | disk | 120,392 | 120,353 | 118,784 | 0.81 | 0.15 | - | - | 92adf79eca95 | 92adf79eca95 | equal |
| k3 | M32000/t5 | after a clean restart | disk | disk | 32,305 | 32,035 | 30,720 | 0.67 | 0.38 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k3 | M120000/t5 | after a clean restart | disk | disk | 120,856 | 120,601 | 118,784 | 1.00 | 0.32 | - | - | 759afd450e25 | 759afd450e25 | equal |

Cold references (a boot without the disk tier and with --prompt-cache-gib 0, the same messages):

| case | prompt tokens | cached | first token s | token_sha | reply sha |
|---|---:|---:|---:|---|---|
| M32000/t2 | 32,074 | 0 | 14.88 | 96807cf020c1 | d3bb61f6b44f |
| M32000/t3 | 32,151 | 0 | 15.12 | 96807cf020c1 | d3bb61f6b44f |
| M32000/t4 | 32,228 | 0 | 15.10 | 96807cf020c1 | d3bb61f6b44f |
| M32000/t5 | 32,305 | 0 | 15.26 | 96807cf020c1 | d3bb61f6b44f |
| M120000/t2 | 120,640 | 0 | 55.57 | 759afd450e25 | 594294b6016f |
| M120000/t3 | 120,712 | 0 | 55.86 | 759afd450e25 | 594294b6016f |
| M120000/t4 | 120,784 | 0 | 56.02 | 759afd450e25 | 594294b6016f |
| M120000/t5 | 120,856 | 0 | 56.15 | 759afd450e25 | 594294b6016f |
| S120000/t2 | 120,392 | 0 | 55.90 | 92adf79eca95 | b474a8b2191f |
| L/t3 | 642,693 | 0 | 314.65 | a256ed41e4fd | c8a2e266d545 |
| L/t3q | 642,863 | 0 | 314.87 | 17f7ec3a2857 | d99ae1ed0e5f |
| L/t4 | 665,911 | 0 | 327.12 | f4f1199f1f3b | 314b3386a2c9 |
| L/t2 | 619,437 | 0 | 301.64 | 625091ff9968 | 309d9eb04ac9 |
| M32000/t1 | 32,038 | 0 | 15.04 | 568c5dc36654 | c2e3ac47f4a3 |
| M120000/t1 | 120,604 | 0 | 55.90 | 568c5dc36654 | c2e3ac47f4a3 |
| S120000/t1 | 120,356 | 0 | 55.77 | 568c5dc36654 | c2e3ac47f4a3 |
| L/t1 | 596,176 | 0 | 289.77 | d6df00924459 | eec71d35f8e6 |

## The long conversation (L, production's tier_chain text) beside production and our earlier window

| turn | case | prompt tokens | cached | server prefill s | production (how) | production prefill s | ours / production | this serve without a disk tier (section 29) |
|---:|---|---:|---:|---:|---|---:|---:|---:|
| 1 | cold, beside 3 decoding streams | 596,176 | 0 | 334.64 | cold at ~596k tokens | 224.68 | 1.49x | 346.04 |
| 2 | from RAM | 619,437 | 595,968 | 12.72 | from the pool | 12.54 | 1.01x | 14.78 |
| 3 | after SIGKILL of every rank | 642,693 | 619,434 | 12.41 | after every rank was SIGKILLed, from the spill tier (619,392 cached) | 12.80 | 0.97x | 377.76 |
| 4 | after a clean restart, beside 3 decoding streams | 665,911 | 642,690 | 14.84 | after a clean restart | 12.90 | 1.15x | - |

Production's turn 3 follows a SIGKILL and turn 4 a clean restart; this window keeps that order.

## Production's tier behaviours

| behaviour | production | here | evidence |
|---|---|---|---|
| a request of another cache_salt (#144) | resumes nothing of another salt | honoured | salted: cached 0 of 32,228; control without a salt: cached 32,035 |
| a save in flight at a clean stop (SIGTERM, #125) is written | written | written: resumed from disk | S120000/t2 cached 120,353, newest kept 118,784 |

## A save beside decoding streams: the other streams' decode in four windows

| turn | window | seconds | chunk gap median ms | p99 ms | max ms | deltas a second | saved MiB | write ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| L/t1 | base | 15.00 | 70 | 87 | 165 | 43.45 |  |  |
| L/t1 | prefill | 334.71 | 1,144 | 1,408 | 1,618 | 2.62 |  |  |
| L/t1 | reply | 6.50 | 96 | 1,102 | 1,102 | 26.76 |  |  |
| L/t1 | save | 0.00 | - | - | - | 0.00 | - | - |
| L/t4 | base | 15.01 | 69 | 86 | 632 | 44.38 |  |  |
| L/t4 | prefill | 18.89 | 75 | 3,072 | 3,072 | 8.26 |  |  |
| L/t4 | reply | 2.31 | 102 | 261 | 261 | 28.53 |  |  |
| L/t4 | save | 0.00 | - | - | - | 0.00 | - | - |

The base window is the decode before the request; a pause the save adds shows as a max gap in the reply or save window well past the base window's.

## Rank logs: the disk tier's lines

| boot | rank | staging_full | save_skipped | write_failed | restore_failed | check_failed | unwritten_at_stop | ranks_differ | disk_world | disk_layout | disk_words | snapshot_size | ranks_not_asleep | error_lines |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| k1 | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k1 | r1-k1.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k1 | r2-k1.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after k1: 8,580 MiB in 3,058 files (~/.cache/huggingface/glm53-zig-learn/f75).
| k2 | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k2 | r1-k2.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k2 | r2-k2.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after k2: 9,521 MiB in 3,150 files (~/.cache/huggingface/glm53-zig-learn/f75).
| k2 stop | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k3 | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k3 | r1-k3.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k3 | r2-k3.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after k3: 12,680 MiB in 3,716 files (~/.cache/huggingface/glm53-zig-learn/f75).
| ref | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ref | r1-ref.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ref | r2-ref.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after ref: 12,680 MiB in 3,716 files (~/.cache/huggingface/glm53-zig-learn/f75).

