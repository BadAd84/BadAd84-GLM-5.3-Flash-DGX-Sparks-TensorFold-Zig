# GLM conversation states on disk at TP=3 (--learn-conversations): resumes against cold replies

## Disk tier checks failed: 15

- k1 M32000/t3 evicted: SOURCE expected disk, resumed from cold
- k1 M32000/t3 evicted: SHORT cached 0 below the newest kept state 30720
- k1 M120000/t3 evicted: SOURCE expected disk, resumed from cold
- k1 M120000/t3 evicted: SHORT cached 0 below the newest kept state 118784
- k2 L/t3 kill: SHORT cached 595968 below the newest kept state 618496
- k2 M32000/t4 kill: SOURCE expected disk, resumed from cold
- k2 M32000/t4 kill: SHORT cached 0 below the newest kept state 30720
- k2 M120000/t4 kill: SOURCE expected disk, resumed from cold
- k2 M120000/t4 kill: SHORT cached 0 below the newest kept state 118784
- k3 L/t4 restart: SHORT cached 595968 below the newest kept state 641024
- k3 S120000/t2 flushed: SHORT cached 116736 below the newest kept state 118784
- k3 M32000/t5 restart: SOURCE expected disk, resumed from cold
- k3 M32000/t5 restart: SHORT cached 0 below the newest kept state 30720
- k3 M120000/t5 restart: SOURCE expected disk, resumed from cold
- k3 M120000/t5 restart: SHORT cached 0 below the newest kept state 118784

## Rejected rows: 0


## Boots

| boot | arm | P | context | image | boot s | store: states, MiB of cap | ranks' parts | a save stages up to | store directory | MemAvailable GiB spark1 / 2 / 3 |
|---|---|---:|---:|---|---:|---|---:|---:|---|---|
| k1 | learn | 4 | 1,048,576 | glm53-zig:v129w | 119.5 | 0, 0 of 131,072 | 3 | 7,429 MiB | /root/.cache/huggingface/glm53-zig-learn/f73/0eaaa32a3be0f838 | 32.6 / 45.9 / 46.3 |
| k2 | learn | 4 | 1,048,576 | glm53-zig:v129w | 121.5 | 3, 5,303 of 131,072 | 3 | 7,429 MiB | /root/.cache/huggingface/glm53-zig-learn/f73/0eaaa32a3be0f838 | 33.0 / 45.2 / 46.2 |
| k3 | learn | 4 | 1,048,576 | glm53-zig:v129w | 118.9 | 4, 6,519 of 131,072 | 3 | 7,429 MiB | /root/.cache/huggingface/glm53-zig-learn/f73/0eaaa32a3be0f838 | 33.0 / 45.8 / 46.2 |
| ref | ref | 4 | 1,048,576 | glm53-zig:v129w | 119.5 | - | - | - | - | 40.9 / 53.2 / 54.0 |

## Turns: what each resumed from, and its reply against a cold server's

| boot | turn | case | expected | resumed from | prompt tokens | cached | newest kept | first token s | server prefill s | disk read MiB in ms | saves written (MiB, write ms, drain s) | token_sha | cold reference | gate |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|
| k1 | M32000/t1 | cold | cold | cold | 32,038 | 0 | 0 | 15.92 | 15.92 | - | - | 568c5dc36654 | 568c5dc36654 | equal |
| k1 | M32000/t2 | from RAM | ram | ram | 32,074 | 32,035 | 30,720 | 0.15 | 0.14 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k1 | M120000/t1 | cold | cold | cold | 120,604 | 0 | 0 | 59.86 | 59.85 | - | - | 568c5dc36654 | 568c5dc36654 | equal |
| k1 | M120000/t2 | from RAM | ram | ram | 120,640 | 120,601 | 118,784 | 0.16 | 0.15 | - | - | 759afd450e25 | 759afd450e25 | equal |
| k1 | L/t1 | cold | cold | cold | 596,176 | 0 | 0 | 334.20 | 334.18 | - | - | d6df00924459 | d6df00924459 | equal |
| k1 | L/t2 | from RAM | ram | ram | 619,437 | 595,968 | 595,968 | 13.52 | 13.49 | - | - | 625091ff9968 | 625091ff9968 | equal |
| k1 | M32000/t3 | after eviction | disk | cold | 32,151 | 0 | 30,720 | 16.30 | 16.30 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k1 | M120000/t3 | after eviction | disk | cold | 120,712 | 0 | 118,784 | 60.53 | 60.52 | - | - | 759afd450e25 | 759afd450e25 | equal |
| k2 | L/t3 | after SIGKILL of every rank | disk | disk | 642,693 | 595,968 | 618,496 | 28.73 | 26.30 | - | - | a256ed41e4fd | a256ed41e4fd | equal |
| k2 | L/t3q | quote probe | ram | ram | 642,863 | 642,690 | 641,024 | 0.34 | 0.32 | - | - | 17f7ec3a2857 | 17f7ec3a2857 | equal |
| k2 | M32000/t4 | after SIGKILL of every rank | disk | cold | 32,228 | 0 | 30,720 | 16.18 | 16.18 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k2 | M120000/t4 | after SIGKILL of every rank | disk | cold | 120,784 | 0 | 118,784 | 59.95 | 59.94 | - | - | 759afd450e25 | 759afd450e25 | equal |
| k2 | S120000/t1 | flush | cold | cold | 120,356 | 0 | 0 | 60.03 | 60.03 | - | - | 568c5dc36654 | 568c5dc36654 | equal |
| k3 | L/t4 | after a clean restart | disk | disk | 665,911 | 595,968 | 641,024 | 46.67 | 42.83 | - | - | f4f1199f1f3b | f4f1199f1f3b | equal |
| k3 | S120000/t2 | flushed | disk | disk | 120,392 | 116,736 | 118,784 | 2.67 | 2.08 | - | - | 92adf79eca95 | 92adf79eca95 | equal |
| k3 | M32000/t5 | after a clean restart | disk | cold | 32,305 | 0 | 30,720 | 16.30 | 16.30 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k3 | M120000/t5 | after a clean restart | disk | cold | 120,856 | 0 | 118,784 | 60.11 | 60.11 | - | - | 759afd450e25 | 759afd450e25 | equal |

Cold references (a boot without the disk tier and with --prompt-cache-gib 0, the same messages):

| case | prompt tokens | cached | first token s | token_sha | reply sha |
|---|---:|---:|---:|---|---|
| M32000/t2 | 32,074 | 0 | 16.24 | 96807cf020c1 | d3bb61f6b44f |
| M32000/t3 | 32,151 | 0 | 16.54 | 96807cf020c1 | d3bb61f6b44f |
| M32000/t4 | 32,228 | 0 | 16.47 | 96807cf020c1 | d3bb61f6b44f |
| M32000/t5 | 32,305 | 0 | 16.68 | 96807cf020c1 | d3bb61f6b44f |
| M120000/t2 | 120,640 | 0 | 61.10 | 759afd450e25 | 594294b6016f |
| M120000/t3 | 120,712 | 0 | 61.34 | 759afd450e25 | 594294b6016f |
| M120000/t4 | 120,784 | 0 | 61.38 | 759afd450e25 | 594294b6016f |
| M120000/t5 | 120,856 | 0 | 61.41 | 759afd450e25 | 594294b6016f |
| S120000/t2 | 120,392 | 0 | 60.97 | 92adf79eca95 | b474a8b2191f |
| L/t3 | 642,693 | 0 | 338.88 | a256ed41e4fd | c8a2e266d545 |
| L/t3q | 642,863 | 0 | 339.01 | 17f7ec3a2857 | d99ae1ed0e5f |
| L/t4 | 665,911 | 0 | 352.28 | f4f1199f1f3b | 314b3386a2c9 |
| L/t2 | 619,437 | 0 | 325.73 | 625091ff9968 | 309d9eb04ac9 |
| M32000/t1 | 32,038 | 0 | 16.13 | 568c5dc36654 | c2e3ac47f4a3 |
| M120000/t1 | 120,604 | 0 | 60.32 | 568c5dc36654 | c2e3ac47f4a3 |
| S120000/t1 | 120,356 | 0 | 60.24 | 568c5dc36654 | c2e3ac47f4a3 |
| L/t1 | 596,176 | 0 | 312.12 | d6df00924459 | eec71d35f8e6 |

## The long conversation (L, production's tier_chain text) beside production and our earlier window

| turn | case | prompt tokens | cached | server prefill s | production (how) | production prefill s | ours / production | this serve without a disk tier (section 29) |
|---:|---|---:|---:|---:|---|---:|---:|---:|
| 1 | cold, beside 3 decoding streams | 596,176 | 0 | 334.18 | cold at ~596k tokens | 224.68 | 1.49x | 346.04 |
| 2 | from RAM | 619,437 | 595,968 | 13.49 | from the pool | 12.54 | 1.08x | 14.78 |
| 3 | after SIGKILL of every rank | 642,693 | 595,968 | 26.30 | after every rank was SIGKILLed, from the spill tier (619,392 cached) | 12.80 | 2.05x | 377.76 |
| 4 | after a clean restart, beside 3 decoding streams | 665,911 | 595,968 | 42.83 | after a clean restart | 12.90 | 3.32x | - |

Production's turn 3 follows a SIGKILL and turn 4 a clean restart; this window keeps that order.

## Production's tier behaviours

| behaviour | production | here | evidence |
|---|---|---|---|
| a request of another cache_salt (#144) | resumes nothing of another salt | honoured | salted: cached 0 of 32,228; control without a salt: cached 32,035 |
| a save in flight at a clean stop (SIGTERM, #125) is written | written | LOST: disk | S120000/t2 cached 116,736, newest kept 118,784 |

## A save beside decoding streams: the other streams' decode in four windows

| turn | window | seconds | chunk gap median ms | p99 ms | max ms | deltas a second | saved MiB | write ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| L/t1 | base | 15.00 | 70 | 84 | 110 | 44.19 |  |  |
| L/t1 | prefill | 334.20 | 1,147 | 1,235 | 1,537 | 2.62 |  |  |
| L/t1 | reply | 6.57 | 94 | 1,092 | 1,092 | 26.79 |  |  |
| L/t1 | save | 0.00 | 98 | 98 | 98 | 570.97 | - | - |
| L/t4 | base | 15.00 | 70 | 85 | 120 | 43.79 |  |  |
| L/t4 | prefill | 46.67 | 82 | 2,907 | 2,907 | 4.89 |  |  |
| L/t4 | reply | 2.35 | 99 | 347 | 347 | 28.11 |  |  |
| L/t4 | save | 0.00 | - | - | - | 0.00 | - | - |

The base window is the decode before the request; a pause the save adds shows as a max gap in the reply or save window well past the base window's.

## Rank logs: the disk tier's lines

| boot | rank | staging_full | save_skipped | write_failed | restore_failed | check_failed | unwritten_at_stop | ranks_differ | disk_world | disk_layout | disk_words | snapshot_size | ranks_not_asleep | error_lines |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| k1 | r0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k1 | r1-k1.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k1 | r2-k1.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after k1: 5,304 MiB in 2,356 files (~/.cache/huggingface/glm53-zig-learn/f73).
| k2 | r0 | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k2 | r1-k2.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k2 | r2-k2.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after k2: 5,304 MiB in 2,356 files (~/.cache/huggingface/glm53-zig-learn/f73).
| k2 stop | r0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k3 | r0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k3 | r1-k3.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k3 | r2-k3.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after k3: 7,757 MiB in 3,087 files (~/.cache/huggingface/glm53-zig-learn/f73).
| ref | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ref | r1-ref.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ref | r2-ref.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after ref: 7,757 MiB in 3,087 files (~/.cache/huggingface/glm53-zig-learn/f73).

