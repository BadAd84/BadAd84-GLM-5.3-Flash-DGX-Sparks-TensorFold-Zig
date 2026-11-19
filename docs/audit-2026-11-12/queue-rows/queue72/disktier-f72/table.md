# GLM conversation states on disk at TP=3 (--learn-conversations): resumes against cold replies

## Disk tier checks failed: 0


## Rejected rows: 0


## Boots

| boot | arm | P | context | image | boot s | store: states, MiB of cap | ranks' parts | a save stages up to | store directory | MemAvailable GiB spark1 / 2 / 3 |
|---|---|---:|---:|---|---:|---|---:|---:|---|---|
| k1 | learn | 4 | 1,048,576 | glm53-zig:v129v | 121.0 | 0, 0 of 131,072 | 3 | 7,429 MiB | /root/.cache/huggingface/glm53-zig-learn/f72/368725c62d68e05f | 33.0 / 45.7 / 45.6 |
| k2 | learn | 4 | 1,048,576 | glm53-zig:v129v | 120.0 | 7, 8,520 of 131,072 | 3 | 7,429 MiB | /root/.cache/huggingface/glm53-zig-learn/f72/368725c62d68e05f | 32.6 / 45.8 / 45.9 |
| k3 | learn | 4 | 1,048,576 | glm53-zig:v129v | 121.5 | 10, 11,189 of 131,072 | 3 | 7,429 MiB | /root/.cache/huggingface/glm53-zig-learn/f72/368725c62d68e05f | 32.9 / 45.6 / 45.6 |
| ref | ref | 4 | 1,048,576 | glm53-zig:v129v | 119.9 | - | - | - | - | 41.7 / 53.9 / 54.4 |

## Turns: what each resumed from, and its reply against a cold server's

| boot | turn | case | expected | resumed from | prompt tokens | cached | newest kept | first token s | server prefill s | disk read MiB in ms | saves written (MiB, write ms, drain s) | token_sha | cold reference | gate |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|
| k1 | M32000/t1 | cold | cold | cold | 32,038 | 0 | 0 | 14.86 | 14.86 | - | - | 568c5dc36654 | 568c5dc36654 | equal |
| k1 | M32000/t2 | from RAM | ram | ram | 32,074 | 30,720 | 30,720 | 0.85 | 0.79 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k1 | M120000/t1 | cold | cold | cold | 120,604 | 0 | 0 | 55.66 | 55.66 | - | - | 568c5dc36654 | 568c5dc36654 | equal |
| k1 | M120000/t2 | from RAM | ram | ram | 120,640 | 118,784 | 118,784 | 1.19 | 1.02 | - | - | 759afd450e25 | 759afd450e25 | equal |
| k1 | L/t1 | cold | cold | cold | 596,176 | 0 | 0 | 333.85 | 333.82 | - | - | d6df00924459 | d6df00924459 | equal |
| k1 | L/t2 | from RAM | ram | ram | 619,437 | 595,968 | 595,968 | 12.71 | 12.69 | - | - | 625091ff9968 | 625091ff9968 | equal |
| k1 | M32000/t3 | after eviction | disk | disk | 32,151 | 30,720 | 30,720 | 1.14 | 0.83 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k1 | M120000/t3 | after eviction | disk | disk | 120,712 | 118,784 | 118,784 | 1.73 | 1.06 | - | - | 759afd450e25 | 759afd450e25 | equal |
| k2 | L/t3 | after SIGKILL of every rank | disk | disk | 642,693 | 618,496 | 618,496 | 15.74 | 12.81 | - | - | a256ed41e4fd | a256ed41e4fd | equal |
| k2 | L/t3q | quote probe | ram | ram | 642,863 | 641,024 | 641,024 | 1.16 | 1.15 | - | - | 17f7ec3a2857 | 17f7ec3a2857 | equal |
| k2 | M32000/t4 | after SIGKILL of every rank | disk | disk | 32,228 | 30,720 | 30,720 | 1.17 | 0.85 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k2 | M120000/t4 | after SIGKILL of every rank | disk | disk | 120,784 | 118,784 | 118,784 | 1.72 | 1.08 | - | - | 759afd450e25 | 759afd450e25 | equal |
| k2 | S120000/t1 | flush | cold | cold | 120,356 | 0 | 0 | 55.98 | 55.98 | - | - | 568c5dc36654 | 568c5dc36654 | equal |
| k3 | L/t4 | after a clean restart | disk | disk | 665,911 | 641,024 | 641,024 | 19.73 | 15.79 | - | - | f4f1199f1f3b | f4f1199f1f3b | equal |
| k3 | S120000/t2 | flushed | disk | disk | 120,392 | 118,784 | 118,784 | 1.51 | 0.91 | - | - | 92adf79eca95 | 92adf79eca95 | equal |
| k3 | M32000/t5 | after a clean restart | disk | disk | 32,305 | 30,720 | 30,720 | 1.18 | 0.90 | - | - | 96807cf020c1 | 96807cf020c1 | equal |
| k3 | M120000/t5 | after a clean restart | disk | disk | 120,856 | 118,784 | 118,784 | 1.87 | 1.25 | - | - | 759afd450e25 | 759afd450e25 | equal |

Cold references (a boot without the disk tier and with --prompt-cache-gib 0, the same messages):

| case | prompt tokens | cached | first token s | token_sha | reply sha |
|---|---:|---:|---:|---|---|
| M32000/t2 | 32,074 | 0 | 14.69 | 96807cf020c1 | d3bb61f6b44f |
| M32000/t3 | 32,151 | 0 | 14.94 | 96807cf020c1 | d3bb61f6b44f |
| M32000/t4 | 32,228 | 0 | 14.83 | 96807cf020c1 | d3bb61f6b44f |
| M32000/t5 | 32,305 | 0 | 15.00 | 96807cf020c1 | d3bb61f6b44f |
| M120000/t2 | 120,640 | 0 | 55.79 | 759afd450e25 | 594294b6016f |
| M120000/t3 | 120,712 | 0 | 56.02 | 759afd450e25 | 594294b6016f |
| M120000/t4 | 120,784 | 0 | 56.23 | 759afd450e25 | 594294b6016f |
| M120000/t5 | 120,856 | 0 | 56.33 | 759afd450e25 | 594294b6016f |
| S120000/t2 | 120,392 | 0 | 56.10 | 92adf79eca95 | b474a8b2191f |
| L/t3 | 642,693 | 0 | 316.67 | a256ed41e4fd | c8a2e266d545 |
| L/t3q | 642,863 | 0 | 315.59 | 17f7ec3a2857 | d99ae1ed0e5f |
| L/t4 | 665,911 | 0 | 327.48 | f4f1199f1f3b | 314b3386a2c9 |
| L/t2 | 619,437 | 0 | 303.17 | 625091ff9968 | 309d9eb04ac9 |
| M32000/t1 | 32,038 | 0 | 14.89 | 568c5dc36654 | c2e3ac47f4a3 |
| M120000/t1 | 120,604 | 0 | 56.09 | 568c5dc36654 | c2e3ac47f4a3 |
| S120000/t1 | 120,356 | 0 | 56.03 | 568c5dc36654 | c2e3ac47f4a3 |
| L/t1 | 596,176 | 0 | 291.26 | d6df00924459 | eec71d35f8e6 |

## The long conversation (L, production's tier_chain text) beside production and our earlier window

| turn | case | prompt tokens | cached | server prefill s | production (how) | production prefill s | ours / production | this serve without a disk tier (section 29) |
|---:|---|---:|---:|---:|---|---:|---:|---:|
| 1 | cold, beside 3 decoding streams | 596,176 | 0 | 333.82 | cold at ~596k tokens | 224.68 | 1.49x | 346.04 |
| 2 | from RAM | 619,437 | 595,968 | 12.69 | from the pool | 12.54 | 1.01x | 14.78 |
| 3 | after SIGKILL of every rank | 642,693 | 618,496 | 12.81 | after every rank was SIGKILLed, from the spill tier (619,392 cached) | 12.80 | 1.00x | 377.76 |
| 4 | after a clean restart, beside 3 decoding streams | 665,911 | 641,024 | 15.79 | after a clean restart | 12.90 | 1.22x | - |

Production's turn 3 follows a SIGKILL and turn 4 a clean restart; this window keeps that order.

## Production's tier behaviours

| behaviour | production | here | evidence |
|---|---|---|---|
| a request of another cache_salt (#144) | resumes nothing of another salt | honoured | salted: cached 0 of 32,228; control without a salt: cached 30,720 |
| a save in flight at a clean stop (SIGTERM, #125) is written | written | written: resumed from disk | S120000/t2 cached 118,784, newest kept 118,784 |

## A save beside decoding streams: the other streams' decode in four windows

| turn | window | seconds | chunk gap median ms | p99 ms | max ms | deltas a second | saved MiB | write ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| L/t1 | base | 15.01 | 69 | 86 | 709 | 43.98 |  |  |
| L/t1 | prefill | 333.85 | 1,145 | 1,245 | 1,564 | 2.62 |  |  |
| L/t1 | reply | 6.62 | 95 | 1,142 | 1,142 | 26.75 |  |  |
| L/t1 | save | 0.00 | - | - | - | 0.00 | - | - |
| L/t4 | base | 15.01 | 70 | 85 | 1,206 | 43.98 |  |  |
| L/t4 | prefill | 19.73 | 77 | 3,008 | 3,008 | 7.91 |  |  |
| L/t4 | reply | 2.17 | 102 | 519 | 519 | 27.66 |  |  |
| L/t4 | save | 0.00 | - | - | - | 0.00 | - | - |

The base window is the decode before the request; a pause the save adds shows as a max gap in the reply or save window well past the base window's.

## Rank logs: the disk tier's lines

| boot | rank | staging_full | save_skipped | write_failed | restore_failed | check_failed | unwritten_at_stop | ranks_differ | disk_world | disk_layout | disk_words | snapshot_size | ranks_not_asleep | error_lines |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| k1 | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k1 | r1-k1.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k1 | r2-k1.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after k1: 8,521 MiB in 3,034 files ($HOME/.cache/huggingface/glm53-zig-learn/f72).
| k2 | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k2 | r1-k2.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k2 | r2-k2.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after k2: 9,455 MiB in 3,123 files ($HOME/.cache/huggingface/glm53-zig-learn/f72).
| k2 stop | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k3 | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k3 | r1-k3.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| k3 | r2-k3.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after k3: 12,671 MiB in 3,695 files ($HOME/.cache/huggingface/glm53-zig-learn/f72).
| ref | r0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ref | r1-ref.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ref | r2-ref.log | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The store on disk after ref: 12,671 MiB in 3,695 files ($HOME/.cache/huggingface/glm53-zig-learn/f72).

