# GLM conversation states on disk at TP=3 (--learn-conversations): resumes against cold replies

## Disk tier checks failed: 0


## Rejected rows: 0


## Boots

| boot | arm | P | context | image | boot s | store: states, MiB of cap | ranks' parts | a save stages up to | store directory | MemAvailable GiB spark1 / 2 / 3 |
|---|---|---:|---:|---|---:|---|---:|---:|---|---|
| k1 | learn | 4 | 1,048,576 | glm53-zig:rs2x3d | 118.0 | 0, 0 of 131,072 | 3 | 7,429 MiB | ~/.cache/huggingface/glm53-zig-learn/rs2x3da/600547e0f61e1c84 | 32.6 / 45.4 / 46.1 |
| k2 | learn | 4 | 1,048,576 | glm53-zig:rs2x3d | 120.0 | 7, 8,520 of 131,072 | 3 | 7,429 MiB | ~/.cache/huggingface/glm53-zig-learn/rs2x3da/600547e0f61e1c84 | 32.9 / 45.5 / 46.1 |
| k3 | learn | 4 | 1,048,576 | glm53-zig:rs2x3d | 119.5 | 10, 11,189 of 131,072 | 3 | 7,429 MiB | ~/.cache/huggingface/glm53-zig-learn/rs2x3da/600547e0f61e1c84 | 32.9 / 45.3 / 46.1 |
| ref | ref | 4 | 1,048,576 | glm53-zig:rs2x3d | 120.0 | - | - | - | - | 42.0 / 54.3 / 55.1 |

## Turns: what each resumed from, and its reply against a cold server's

| boot | turn | case | expected | resumed from | prompt tokens | cached | newest kept | first token s | server prefill s | disk read MiB in ms | saves written (MiB, write ms, drain s) | token_sha | cold reference | gate |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|
| k1 | M32000/t1 | cold | cold | cold | 32,023 | 0 | 0 | 18.16 | 18.16 | - | - | 568c5dc36654 | 568c5dc36654 | equal |
| k1 | M32000/t2 | from RAM | ram | ram | 32,059 | 30,720 | 30,720 | 0.95 | 0.88 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k1 | M120000/t1 | cold | cold | cold | 120,611 | 0 | 0 | 68.07 | 68.06 | - | - | 568c5dc36654 | 568c5dc36654 | equal |
| k1 | M120000/t2 | from RAM | ram | ram | 120,647 | 118,784 | 118,784 | 1.33 | 1.14 | - | - | 759afd450e25 | 759afd450e25 | equal |
| k1 | L/t1 | cold | cold | cold | 596,183 | 0 | 0 | 375.62 | 375.58 | - | - | 9d6b2bd1976d | 9d6b2bd1976d | equal |
| k1 | L/t2 | from RAM | ram | ram | 619,444 | 595,968 | 595,968 | 15.04 | 15.02 | - | - | 7214c22af414 | 7214c22af414 | equal |
| k1 | M32000/t3 | after eviction | disk | disk | 32,136 | 30,720 | 30,720 | 1.74 | 0.93 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k1 | M120000/t3 | after eviction | disk | disk | 120,719 | 118,784 | 118,784 | 3.40 | 1.20 | - | - | 759afd450e25 | 759afd450e25 | equal |
| k2 | L/t3 | after SIGKILL of every rank | disk | disk | 642,700 | 618,496 | 618,496 | 25.97 | 15.18 | - | - | 434d55ddde0b | 434d55ddde0b | equal |
| k2 | L/t3q | quote probe | ram | ram | 642,870 | 641,024 | 641,024 | 1.41 | 1.39 | - | - | 37b39020c37a | 37b39020c37a | equal |
| k2 | M32000/t4 | after SIGKILL of every rank | disk | disk | 32,213 | 30,720 | 30,720 | 1.63 | 0.95 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k2 | M120000/t4 | after SIGKILL of every rank | disk | disk | 120,791 | 118,784 | 118,784 | 3.40 | 1.22 | - | - | 759afd450e25 | 759afd450e25 | equal |
| k2 | S120000/t1 | flush | cold | cold | 120,363 | 0 | 0 | 68.05 | 68.04 | - | - | 568c5dc36654 | 568c5dc36654 | equal |
| k3 | L/t4 | after a clean restart | disk | disk | 665,918 | 641,024 | 641,024 | 29.52 | 17.56 | - | - | 21db7b121860 | 21db7b121860 | equal |
| k3 | S120000/t2 | flushed | disk | disk | 120,399 | 118,784 | 118,784 | 3.56 | 1.03 | - | - | 92adf79eca95 | 92adf79eca95 | equal |
| k3 | M32000/t5 | after a clean restart | disk | disk | 32,290 | 30,720 | 30,720 | 1.79 | 1.00 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k3 | M120000/t5 | after a clean restart | disk | disk | 120,863 | 118,784 | 118,784 | 3.82 | 1.40 | - | - | 759afd450e25 | 759afd450e25 | equal |

Cold references (a boot without the disk tier and with --prompt-cache-gib 0, the same messages):

| case | prompt tokens | cached | first token s | token_sha | reply sha |
|---|---:|---:|---:|---|---|
| M32000/t2 | 32,059 | 0 | 18.09 | 96807cf020c1 | d3bb61f6b44f |
| M32000/t3 | 32,136 | 0 | 18.35 | 96807cf020c1 | d3bb61f6b44f |
| M32000/t4 | 32,213 | 0 | 18.28 | 96807cf020c1 | d3bb61f6b44f |
| M32000/t5 | 32,290 | 0 | 18.36 | 96807cf020c1 | d3bb61f6b44f |
| M120000/t2 | 120,647 | 0 | 67.96 | 759afd450e25 | 594294b6016f |
| M120000/t3 | 120,719 | 0 | 68.10 | 759afd450e25 | 594294b6016f |
| M120000/t4 | 120,791 | 0 | 68.23 | 759afd450e25 | 594294b6016f |
| M120000/t5 | 120,863 | 0 | 68.40 | 759afd450e25 | 594294b6016f |
| S120000/t2 | 120,399 | 0 | 68.13 | 92adf79eca95 | b474a8b2191f |
| L/t3 | 642,700 | 0 | 378.26 | 434d55ddde0b | c2dc06dec834 |
| L/t3q | 642,870 | 0 | 378.44 | 37b39020c37a | 72418d0bd77a |
| L/t4 | 665,918 | 0 | 393.11 | 21db7b121860 | 29cbc6e7d453 |
| L/t2 | 619,444 | 0 | 363.95 | 7214c22af414 | 1d508c094be6 |
| M32000/t1 | 32,023 | 0 | 18.32 | 568c5dc36654 | c2e3ac47f4a3 |
| M120000/t1 | 120,611 | 0 | 68.26 | 568c5dc36654 | c2e3ac47f4a3 |
| S120000/t1 | 120,363 | 0 | 68.20 | 568c5dc36654 | c2e3ac47f4a3 |
| L/t1 | 596,183 | 0 | 349.51 | 9d6b2bd1976d | 8c592225223a |

## The long conversation (L, production's tier_chain text) beside production and our earlier window

| turn | case | prompt tokens | cached | server prefill s | production (how) | production prefill s | ours / production | this serve without a disk tier (section 29) |
|---:|---|---:|---:|---:|---|---:|---:|---:|
| 1 | cold, beside 3 decoding streams | 596,183 | 0 | 375.58 | cold at ~596k tokens | 224.68 | 1.67x | 346.04 |
| 2 | from RAM | 619,444 | 595,968 | 15.02 | from the pool | 12.54 | 1.20x | 14.78 |
| 3 | after SIGKILL of every rank | 642,700 | 618,496 | 15.18 | after every rank was SIGKILLed, from the spill tier (619,392 cached) | 12.80 | 1.19x | 377.76 |
| 4 | after a clean restart, beside 3 decoding streams | 665,918 | 641,024 | 17.56 | after a clean restart | 12.90 | 1.36x | - |

Production's turn 3 follows a SIGKILL and turn 4 a clean restart; this window keeps that order.

## Production's tier behaviours

| behaviour | production | here | evidence |
|---|---|---|---|
| a request of another cache_salt (#144) | resumes nothing of another salt | IGNORED: another salt resumed this conversation's state | salted: cached 30,720 of 32,213; control without a salt: cached 30,720 |
| a save in flight at a clean stop (SIGTERM, #125) is written | written | written: resumed from disk | S120000/t2 cached 118,784, newest kept 118,784 |

## A save beside decoding streams: the other streams' decode in four windows

| turn | window | seconds | chunk gap median ms | p99 ms | max ms | deltas a second | saved MiB | write ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| L/t1 | base | 15.01 | 63 | 146 | 1,307 | 42.91 |  |  |
| L/t1 | prefill | 375.62 | 1,284 | 1,390 | 3,867 | 2.34 |  |  |
| L/t1 | reply | 5.40 | 91 | 1,105 | 1,106 | 26.49 |  |  |
| L/t1 | save | 0.00 | - | - | - | 0.00 | - | - |
| L/t4 | base | 15.00 | 63 | 116 | 1,280 | 44.12 |  |  |
| L/t4 | prefill | 29.52 | 73 | 10,851 | 10,851 | 6.00 |  |  |
| L/t4 | reply | 6.85 | 85 | 1,192 | 1,327 | 28.18 |  |  |
| L/t4 | save | 0.00 | - | - | - | 0.00 | - | - |

The base window is the decode before the request; a pause the save adds shows as a max gap in the reply or save window well past the base window's.

## Rank logs: the disk tier's lines

| boot | rank | staging_full | save_skipped | write_failed | restore_failed | check_failed | unwritten_at_stop | ranks_differ | disk_world | disk_layout | disk_words | snapshot_size | ranks_not_asleep | error_lines |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| k1 | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k1 | r1-k1.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k1 | r2-k1.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after k1: 8,521 MiB in 3,034 files (~/.cache/huggingface/glm53-zig-learn/rs2x3da).
| k2 | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k2 | r1-k2.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k2 | r2-k2.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after k2: 9,455 MiB in 3,123 files (~/.cache/huggingface/glm53-zig-learn/rs2x3da).
| k2 stop | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k3 | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k3 | r1-k3.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k3 | r2-k3.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after k3: 12,671 MiB in 3,695 files (~/.cache/huggingface/glm53-zig-learn/rs2x3da).
| ref | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ref | r1-ref.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ref | r2-ref.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after ref: 12,671 MiB in 3,695 files (~/.cache/huggingface/glm53-zig-learn/rs2x3da).

