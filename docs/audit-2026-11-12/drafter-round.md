# DrafterRound, 2026-11-14: the two drafter-side items at 2 and 4 streams, bounded; nothing built

CPU only. Inputs: rank 0's exports of the recipe at 1, 2 and 4 streams (`spark1:~/nsys/rec-p{1,2,4}.sqlite`, queue17,
image `glm53-zig:rs2`, tree `4ed20ea3d175`, `KNOBS=measured`), copied here read-only and deleted after the run (restore:
`scp adam@spark1:'nsys/rec-p*.sqlite' spark1/nsys/`). The capture predates 0034 (the X3 set), which touches the
routed experts only, not the keep, the follower protocol or the drafter. Production's drafter numbers:
`GLM-5.3-Flash-DGX-Sparks-TensorFold-Python-TP3/int-docs/notes/drafter-pass-DrafterFable.md` (DF:). MIA 0031:
`work/profile-root-2026-11-12/beside-clones/work-recon/GLM-5.3-Flash-DGX-Sparks-1104/patches/engine/0031-*.patch`.
Every probe prints its SQL; outputs are kept beside it (`*.out`).

Decision (owner's rule via Main: a bound under about 0.5 ms a round at 4 streams after its own costs is not a patch):
**neither item clears it; nothing was built.** Item 2 clears 0.5 ms only against the 273 GB/s peak, which no kernel
on the GB10 reaches; at production's measured efficiency on our bytes, and for the one bit-exact mechanism buildable
here, it does not.

| ms a round | P2 | P4 | what it assumes |
|---|---:|---:|---|
| item 1, ceiling: the drafter's whole first-gather wait above its transfer | 0.53 | 0.57 | followers never late |
| item 1, all keeps folded into the block step (header first) | 0.18-0.40 | 0.29-0.38 | the block step's own receive stays |
| item 1, MIA 0031 as written | -0.05 | -0.03 | a loss: see 1.3 |
| item 2, against bytes / 273 GB/s | 0.65 | 0.94 | every launch at the LPDDR5X peak |
| item 2, against bytes / 239 GB/s (production's measured achievable) | 0.44 | 0.73 | every launch at it, 2.4 MB ones too |
| item 2, at production's measured per-shape efficiency on our bytes | 0.25 | 0.35-0.48 | DF 2.1 |
| item 2, the buildable bit-exact mechanism (shared-panel row tiles) | 0 | 0.29 | the second row tile's whole measured cost |

## 1. Item 1: keep steps folded into the drafter step, followers skip the draw read

### 1.1 The wait it targets

At S streams a round sends the followers 1 + S + 1 steps (the shared verify, one keep a stream, the block step;
`cuda_lanes.zig:177-183,512-529`, `cuda_follow.zig:288-292,309-316`), each a broadcast, a synchronize and a 256-byte
read on every follower (`cuda_follow.zig:117-130`). Rank 0 never waits for them until the first collective that needs
their data: the drafter's first MLP-split gather. `tl.py` / `line.py` (rank 0's main stream from T = the end of the
verify's last draw gather):

| median, us | P1 (1 keep) | P2 (2 keeps) | P4 (4 keeps) |
|---|---:|---:|---:|
| T to the first keep's put_words (rank 0's draw read and acceptance) | 17 | 14 | 18 |
| rank 0's keep steps, rounds with no KDA replay | 32 | 50 | 97 |
| drafter put_words to its first MLP gather (rank 0's own work) | 838 | 872 | 983 |
| that gather's duration, no replay | 252 | 719 | 712 |
| floor: the step's MLP gathers 2-5 (transfer only) | 35 | 60 | 81 |

`lag.py` / `bound1.py` over 572 rounds, lag = the first gather's duration less the floor (rank 0 waiting for the last of
ranks 1 and 2): mean 209 / 532 / 566 us at P1 / P2 / P4 (p10 100 / 227 / 290, p90 381 / 897 / 900). The ceiling of
item 1 is that whole wait: **0.53 ms at P2, 0.57 at P4**. Least squares (every round keeps one step a stream, so keeps
equal streams):

    pooled: lag = 223.9 + 129.9 * keeps - 92.2 * replays us (residual sd 206, n 572)
    P2:     lag = 136.1 + 247.2 * keeps - 115.9 * replays (sd 203, n 210)
    P4:     lag = 277.1 +  99.6 * keeps -  74.2 * replays (sd 211, n 213)

A keep's KDA replay (0.42 ms of GPU work on every rank) shortens the wait: the follower's next receive runs behind its
own replay instead of in the open. That is why the fold must send its header before the keeps' GPU work (1.4).

### 1.2 The bound after its own costs

Folded, a follower receives one step a round before the keeps: its lag is the fit's a (no keep receive left, and no
replay left to hide one), so a round saves b * S + c * R (R = replays a round: 0.85 at P2, 1.50 at P4):

    P2: pooled 130 * 2 - 92 * 0.85 = 0.181 ms   P2 fit 247 * 2 - 116 * 0.85 = 0.396 ms   (wait left 0.35 / 0.14)
    P4: pooled 130 * 4 - 92 * 1.50 = 0.381 ms   P4 fit 100 * 4 -  74 * 1.50 = 0.287 ms   (wait left 0.18 / 0.28)

The waits left match the best rounds (p10 227 / 290 us). The fold's own costs: none on the GPU (the same kernels,
arguments and order on every rank); rank 0 drops S put_words + broadcast pairs (12-15 us a keep, `line.out`: four keeps
with no replay span 120-145 us), which does not shorten the round while followers are late; the block header grows by
S words. **Bound 0.18-0.40 ms at P2, 0.29-0.38 at P4.**

The followers' draw read: zero on the critical path. Rank 0 reads the same draws (one synchronize and read a stream,
`cuda_engine_pick.zig:15-41`) and needs them for acceptance; its first keep header leaves 14-18 us after T, and a
follower's read ends with rank 0's (rank 0's last read returns at T + 6-12 us, `line.out`), so a follower is already
waiting in its next receive when that header arrives. MIA 0048 adds that a follower which skips the read must still
call `checkGathers` (no synchronize) or a failed RoCE gather goes unseen.

### 1.3 MIA 0031 as written is a loss here

`Leader.keep` (patch lines 261-270) launches rank 0's commit at once and parks the header; it leaves with the next
step's `put_words` (`Leader.send`, lines 247-252), which is queued on rank 0's stream after the commit's KDA replay.
The followers therefore receive it only when rank 0's replay has finished, and then run their own replay before the
step: the replay serializes across ranks instead of overlapping. It also folds one keep only ("two keeps in a row:
the first goes alone", lines 264-267). Net a round = one receive saved less the riding keep's replay probability
times 0.42 ms:

    P1 130 - 0.47 * 420 = -0.067 ms    P2 130 - (0.85 / 2) * 420 = -0.049 ms    P4 130 - (1.50 / 4) * 420 = -0.028 ms

### 1.4 The fold, specified for a later build (default off; not built)

- Rank 0, `Lanes.draftBlock` (`cuda_lanes.zig:512-540`): for each request read the stream's keep rows as `bind` does
  (`kept orelse pending_rows`, 0 when none; clear `pending_rows`) without calling `x.keep`; then one Leader call
  (`blockKept`): `flush()`; send ONE block step carrying 4 words a stream (slot, n, anchor, keep rows), told apart
  from today's 3-word block by a header field the block step leaves unused (`a = 1`); then, on rank 0, for each stream
  with rows > 0: `e.bind(slot)`, `e.keep(rows)`; then `e.draftBlock(reqs)`. The header goes out BEFORE rank 0's
  replays, so each follower's replays run one receive behind rank 0's, as today, not after them (1.3).
- Followers, `follow` `.block` (`cuda_follow.zig:421-427`): with `a = 1`, for each stream with rows > 0 `e.bind(slot)`
  then `e.keep(rows)`, then decode the requests and `e.draftBlock` as today.
- Every rank's GPU order is unchanged: [rank 0: put_words, broadcast] keep 1 .. keep S (replay when kept < pending, conv
  shift, setPos), ingest, block pass. Replies and drafts are bit-identical by construction.
- 4 x S words fit the first broadcast's 48 inline ids (`cuda_follow.zig:42`) up to 12 streams; 13 to 16
  (`dflash.MAX_S`) take the second broadcast, as any longer step does today. `n` cannot stand in for the keep rows: a
  request without rows keeps `pending_rows` with n = 0.
- Unchanged: `keepFn` (a keep with no draft, `cuda_lanes.zig:481-488`), the MTP `draftFn` (490-509) and the verify
  paths' binds still send the keep alone.
- Host tests: the 4-word record round trip at S = 1, 12, 13, 16; the follower commits before `draftBlock` and only rows
  > 0; rank 0 sends before its first commit (a recording fake Link and Engine). Mutants: keeps after the block, rows
  from n, the header after the commits, a rows-0 stream committed, S > 12 cut at 48 words.
- Receipts: rank 0 nsys at P2 and P4, `d.mlp_gather_first` from 0.592 / 0.647 toward 0.14-0.28 ms; `dflash2 round`
  lines (TF_GLM_DFLASH2_LOG) equal knob off and on; reply digests equal at 1/2/4/6/8; ABBA cells.

## 2. Item 2: the drafter's 4-bit linears and head at production's efficiency

### 2.1 Our bytes and times

`lin.py` / `bound2.py`: the drafter step's 31 block-pass launches (5 layers of a_proj, qkv, o, m_proj, the MLP slice's
gate/up and DOWN4 down, then the head; MLPSPLIT=4), median a launch. Weight bytes as the loader stores them
(`cuda_q4.bytes`: npad * k / 2 + 2 * (k / 64) * npad * 2): a_proj and m_proj 2.36 MB, qkv 14.16, o 9.44, gate/up 18.87,
down 9.44, head 119.14 (51,627 vocabulary rows): **402.3 MB a pass a rank**.

| us a launch | P1 (8 rows) | P2 (16) | P4 (32, two row tiles) |
|---|---:|---:|---:|
| a_proj / m_proj | 19.8 / 20.2 (117-119 GB/s) | 20.8 / 20.3 | 29.0 / 27.6 (81-85 GB/s) |
| qkv | 66.1 (214) | 64.5 (220) | 70.6 (201) |
| o | 49.1 (192) | 48.4 (195) | 56.0 (168) |
| gate/up | 95.0 (199) | 107.8 (175) | 119.9 (158) |
| down (fp32 out) | 47.4 (199) | 47.0 (201) | 55.2 (171) |
| head | 482.6 (247) | 499.1 (239) | 542.5 (220) |
| a pass, + 30 df_gsum | 2.056 ms | 2.126 | 2.416 |

### 2.2 The bound against each floor

    floor at 273 GB/s: 402.3 MB / 273 = 1.473 ms -> bound 0.583 / 0.652 / 0.942 ms at P1 / P2 / P4
    floor at 239 GB/s: 402.3 MB / 239 = 1.683 ms -> bound 0.373 / 0.443 / 0.733

Production's matmuls on the GB10 (DF 2.1, one stream): head 226 GB/s, gate/up 206, down 206, qkv 212, o_proj 205, the
1024 x 4096 conv projections 200, group sums 15 x 1.1 us a pass; at 32 rows 77-85% of 239. Its "~1.55 ms" is 1.546 ms
on 328.5 MB: its attention is split by KV heads (qkv 2304 x 4096, o_proj 4096 x 1536 on rank 0), 74 MB a rank fewer
than ours, so ours (2.21 / 2.52 ms) against 1.65-1.75 mixes bytes with efficiency. At production's efficiency on OUR
bytes (a class already faster counts zero):

    P1 0.191 ms = a_proj 40 + o 15 + m_proj 42 + gate/up 17 + down 8 + gsum 69 us (qkv and head: ours faster)
    P2 0.253 ms = a_proj 45 + o 12 + m_proj 43 + gate/up 81 + down 6 + gsum 66 us
    P4 0.350 (77%) to 0.479 ms (85%) = a_proj 81-87 + o 24-48 + m_proj 74-80 + gate/up 87-135 + down 20-44 + head 0-15
       + qkv 0-4 + gsum 66 us

The mechanism buildable bit-exactly here: upstream's shared-panel tiles (`qmm_group.cu` verify32 / verify64 /
verify128, "decode()'s bits a row", used by the affine-4 verify on the GB10, `cuda/affine4_kernels.zig:253-294`;
`cuda/qlinear.zig:229` still calls verify32 "pending compiler and device qualification") for launches past 16 rows.
Its bound is the second row tile's measured cost, P4 less P2 a launch times count: a_proj 41 +
qkv 30 + o 38 + m_proj 36 + gate/up 60 + down 41 + head 43 us = **0.291 ms at P4, 0 at P2** (no fp32-out wide tile
exists, so the down's 41 us would need a new instantiation and contract records). Larger at 6 and 8 streams (three and
four row tiles), where the recipe already leads production.

### 2.3 The measurement that would settle item 2 against production

A same-bytes kernel timing on one quiet GB10 (a dev-ring box inside a GPU window), A B B A, the median of 50 CUDA-graph
replays a shape:

- Shapes, our pass's seven, with counts: a_proj and m_proj 1024 x 4096 (10), qkv 6144 x 4096 (5), o 4096 x 4096 bf16
  out (5), gate/up 8192 x 4096 (5), down 4096 x 4096 fp32 out (5), head 51,627 x 4096 (1); rows 8, 16 and 32.
- Production: in `tensorfold-glm53:v110hunt4-shard`, `dflash2._mm(x, dflash2._quantize4(W), xs, f32=...)` on random
  bf16 weights, timed as `draftbench.py`'s `graph_ms` does (`scripts/glm53/v110/lanes/DrafterFable/draftbench.py:156`,
  the call it labels at 235-237).
- Ours: in `glm53-zig:rs2x3`, `df_gsum` then `q4.matmulMany` (or `matmulF32` for the down) on weights from the loader's
  own path (`quant.q4`, `q4.pack`), timed with events around the same launches (a timing step in `tf-cuda-test`).
- Per shape: us and GB/s for each engine. Item 2's bound at each row count = sum of count x max(0, ours - production)
  + (our 30 `df_gsum` launches less production's group sums). At or above 0.5 ms at 32 rows, a kernel lever exists at
  equal bytes; below, item 2 is closed and the rest of the gap is production's attention split (74 MB a rank for five
  more gathers a pass; o_proj partials summed across ranks, so the drafts change), a separate lever.

DF's per-kernel figures were taken with synthetic weights on a shared spark5 in October (DF section 6) at production's
shapes, so they bound but do not settle this.

## 3. Files

`tl.py` (the round's timeline by replays, `tl.out`), `line.py` (single rounds with the host calls, `line.out`),
`lag.py` (lags and fits, `lag.out`), `bound1.py` (item 1, `bound1.out`), `lin.py` (per-launch medians and bandwidth,
`lin.out`), `bound2.py` (item 2, `bound2.out`), `setup.sh` (the series' tree `f5495931b233`, read for the code
citations; removed after the run by `clean.py`, which refuses if a reparse point is under it; `bash setup.sh`
rebuilds it). The probes read the exports from `spark1/nsys/` (restore command above). No patch, no gate run, no WSL
scratch.
