# DrafterLever lane, 2026-11-13: where one decode round goes, and one gated lever

CPU only. Sources: the two nsys exports on spark1 (`~/nsys/f5-pad-p1.sqlite`, `~/nsys/f5-pad-p4.sqlite`), the round
counters of the bench cells (`spark1/bench/<cell>/P<n>.jsonl`, copied here), our TF_GLM_PROF log
(`spark1/bench/v127-prof/r0-P1.log`), production's boot log (`spark1/bench/prodprof/log-P1.txt`) and its October
graph-level capture (spark1 `~/prof/night/dec35k.sqlite`). Scripts: `profile.py` (rounds cut into stages) and
`evidence.py` (the SQL lines) read the exports from `spark1/nsys/` (`scp adam@spark1:nsys/f5-pad-p{1,4}.sqlite
spark1/nsys/`; the copies were removed after the run). The scratch tree was removed too: `bash setup.sh`, then
`git -C w/tree apply ../../0034-draft-ingest-split.patch` (WSL) rebuilds it. Every number is measured (where), or
derived (how).

## 0. The captures predate the drafter knobs

Both exports are rank 0 of `fix5` (the OLD pin's stack through 0041) with `TF_GLM_KDA_PAD=1`, 2026-11-12 03:29 and
03:32, no other knob. Stale for the current set (pad + INDEX_CUDA + KEPT_WALK + DRAFT_ONEPASS + DRAFT_DOWN4 +
DRAFT_MLPSPLIT=4 + MLA_FUSEMERGE on v1.2.7 + 33 patches):

- the drafter pass (DOWN4, ONEPASS and MLPSPLIT all postdate it: its down is bf16 and full width, its gate/up full);
- the MLA mixer (MLA_FUSEMERGE, INDEX_CUDA), the routed experts (0012's item plan), the draw (v1.2.7 reads all rows
  once; the capture's stack drew row by row, 3.9 gathers and synchronizes a verify);
- at four streams, everything: upstream v1.2.7 alone is about 10% faster at P4 than the old pin.

Not changed since: the 90 layer all-gathers (NCCL, same sizes), the HC glue kernels, the KDA mixer, the keep's KDA
replay, the drafter's context ingest (no knob touches fc or k, v). The current set's stages below are the capture's
where unchanged, and the counters' deltas where a knob changed them.

## 1. One stream

Round: ours 38.0 to 39.7 ms (15 rounds of the five seven-knob cells `rs2-ctl`, `rs2-ctl-b`, `rs2-measured`, `rs2-s8`,
`rs2-s8-b`; MLPSPLIT=8 is the same configuration at one stream), 144 rounds a request, 2.72 drafts (391 to 393), 2.77
tokens, acceptance 0.651. Production 35.6 ms (its /health counters, `docs/OVERNIGHT-2026-11-12.md` section 15) to
36.8 ms (`prodwin`), 3.01 tokens, 2.92 drafts, acceptance 0.686.

| stage | ours, current set (ms a round) | basis | production (ms) | basis | ours minus production |
|---|---:|---|---:|---|---:|
| verify forward, whole | 34.6 to 36.6 at 3.72 rows | round less drafter and keep; capture 37.66 at 3.93 rows, less 0.21 rows at 4.47 ms, FUSEMERGE about 0.6, item plan about 0.6, one draw about 0.3 gives 35.2 | 32.4 at 3.72 rows | boot one-stream column 29.20 + 0.72 x 4.50 (the served round is within 0.9 of it, round-structure.md 1.3) | +2.2 to +4.2 |
| - routed experts (42) | 20.6 at 3.93 rows | capture | 17.9 to 20.6 | production roofline at D 21.6 to 24.9 | 0 to +2.7 (D is the text's) |
| - collectives: 90 layer all-gathers | 3.12 | capture (gather_a 1.85, gather_b 1.26) | 1.35 to 2.4 | 90 RoCE gathers in its graph (roofline note) | +0.7 to +1.8 |
| - main-stream idle | 1.34 (0.35 just before the gathers) | capture | 0.66 for the whole round | DecNsysFable | +0.7 |
| - HC glue (270 kernels) | 1.69 | capture | not measured (bytes floor 0.30) | roofline | up to +1.4 over the floor |
| - KDA mixer (34) | 4.41 | capture | floor 4.26 | roofline | +0.15 |
| - MLA mixer (11) | 2.93, about 2.3 with FUSEMERGE | capture, rs2-mla +1.4% | floor 1.75 | roofline | +0.55 |
| - shared expert (42) | 1.55 | capture | floor 0.93, on a side stream | roofline | +0.6 |
| - head and draw | 1.25, about 1.0 with one draw | capture | lm_head 0.91 | roofline | +0.1 |
| - router 0.47, dense 0.29, embed 0.01 | 0.77 | capture | floors 0.41 + 0.36 | roofline | 0 |
| keep (KDA replay 0.54 a round x 415 us, conv shift) | 0.26 | capture | the same replay (429 us, dec35k) in its commit graph | dec35k | about 0 |
| drafter step | 2.6 to 3.2 | capture 5.95 less the knobs: rs1-pad 42.3 to rs1-d4s 38.8 ms, less 0.38 for 0.084 fewer rows; the kernel model gives 3.0 | 2.3 | block 1.96 + 0.033 a tap row + taps 0.265 (boot calibration) | +0.3 to +0.9 |
| - context ingest (fc + 5 k, v) | 0.45 | capture: fc 0.233, each k, v 0.035, 18 kernels | inside the taps 0.265 | boot calibration | +0.18 |
| - first gather of the step | 0.35 (0.03 transfer, 0.32 waiting for ranks 1 and 2) | capture | one RoCE gather in the graph | | about +0.3 |
| host and step boundaries | about 0.2 | capture: drafter idle 0.16, keep 0.01 | 0.6 to 1.3 | message, sample, accept, commit | -0.4 to -1.1 |
| **tokens a round** | **2.77** | counters | **3.01** | counters | **-8%, worth 3.1 ms of our 38.2** |

Top three stages where we exceed production, with the evidence:

1. **Collectives, +0.7 to +1.8 ms.** `select count(*), sum(k.end - k.start) / 1e6 from CUPTI_ACTIVITY_KIND_KERNEL k
   join StringIds s on s.id = k.shortName where k.streamId = 18 and s.value like 'ncclDevKernel_AllGather%'` ->
   14,622 kernels, 569.1 ms over 154 verify steps: 94.9 gathers and 3.695 ms a round (the draw's and the drafter's
   included); cut by layer (`profile.py`): 3.12 ms over the 90 layer gathers, mean 32.6 us mid-verify against a 11.8 us
   p10, and the step's first gather 187 us (ranks 1 and 2 start late). Production: 1.35 to 2.4 ms.
2. **Drafter step, +0.3 to +0.9 ms.** `profile.py` d.* rows: span 5.953 ms a round (ingest 0.449, gate/up 1.271, bf16
   down 2.101, attention and norms 1.048, head 0.550, candidates gather 0.351, idle 0.159), stale for the knobs; with
   them 2.6 to 3.2. Production 2.3 (`drafter timings ... 'block': 1.96, 'taps': 0.265`).
3. **Main-stream idle in the verify, +0.7 ms.** `profile.py` v.IDLE 1.337 ms a round over 1,540 kernels; by the next
   kernel: 0.347 ms a round before AllGather kernels (3.7 to 3.9 us each). Production idles 0.66 ms a whole round.

The largest factor is not a stage: tokens a round, 2.77 against 3.01 (2.72 drafts at 0.651 against 2.92 at 0.686), worth
3.1 ms of our round. The two serves reply with different text (`323d3f5bcb55` against `8347edfe4ee6`), so the existing
data cannot split it between the drafter and the text.

## 2. Four streams

Ours, current set: stream 0 decodes at 29.0 to 31.1 tok/s at 2.26 tokens a stream-round (705 stream-rounds, 1,395 drafts,
acceptance 0.639), so a shared round is 72.7 to 78 ms over about 11.9 rows. Production: stream 0 at 37.3 tok/s, but its
P4 cell has no round counters, so its shared round cannot be split; at our 2.26 tokens it would be 60.6 ms.

The capture (stale; 10.78 rows, 84.4 ms a round): verify 75.2 (routed 50.7, KDA mixer 6.0, MLA mixer 5.5, gathers 4.8
plus 0.31 idle before them, HC glue 2.6, shared 1.8, head and 10.7 row draws 1.5, router 0.5, dense 0.3, idle 1.2),
keeps 1.0 (1.70 KDA replays a round at 417 us), drafter 8.2 (ingest 0.48, gate/up 2.65, bf16 down 2.20, attention 1.70,
head 1.10, candidates 0.14). With the knobs the drafter is about 2.6 to 3.4 ms (ONEPASS -2.2 to -3.0, DOWN4 -2.0,
MLPSPLIT -0.6) against production's 2.3 to 2.6 (one block pass, flat with streams, plus the tap rows), so at four
streams the drafter is at parity within half a millisecond and the gap is the verify and tokens a round.

## 3. What the profile supports

- Collectives (largest stage gap): no patch is needed. v1.2.7 carries upstream's TP=3 wire, `TF_GLM_ROCE_MULTI=1`
  (fabric/tp; at world 3 `roce_pick.choosePeers` takes one port a neighbour on a shared IPv4 /24, at the default
  `TF_TP_ROCE_HCAS=2`), never measured here. It needs `TF_TP_MASTER` (rank 0's address, `spark1's address`; the wire
  meets on port 29500/29507) and `TF_TP_KERNEL_IMAGE`, the mailbox fatbin, which the image does not install:
  `fatbin.sh` built it from v1.2.7's `mailbox.cu` for sm_121 (CUDA 13.3, rc 0) as `tp_mailbox.fatbin`, sha256
  `c3f526171160dbcf1150bbbe426d72a9a0853fb26129a62309feb0330b730d2f`. Its path in the arm is under the HF cache that
  serve.sh mounts on every rank. The fork's own three-rank RoCE gather measured -1.3 ms a round at one stream.
- Idle: `TF_GLM_OVN_PDL_EARLY=1` (0026: decode windows' glue kernels launched dependent-ready) is in the series and
  was never measured on rs1/rs2 (the fork: +1.5% at one stream); no patch needed.
- Both are ready as `arms-env.txt` (ABBA: env-ctl, env-roce, env-pdl, env-pdl-b, env-roce-b, env-ctl-b, the
  seven-knob set under each), on the series image `glm53-zig:rs2`. Before the window, the fatbin goes into the cache
  of every box: `for h in spark1 spark2 spark3; do scp work/drafter-lever/tp_mailbox.fatbin
  adam@$h:.cache/huggingface/; done`. A RoCE cell counts only if `r0-P*.log` holds `TF_GLM_ROCE_MULTI:
  gathers up to`; `NCCL keeps the small gathers` there means that cell measured NCCL.
- HC glue: `TF_GLM_OVN_GLUE_FUSE` measured neutral (section 17), and production's grid (`HC_DEC`) measured level at one
  stream on the fork. Not supported.
- Drafter: the knobs left the context ingest untouched; it is 0.449 ms a round on every rank, the same 71 MB of weights
  read on all three, against production's 0.265 for the whole update. That is the lever implemented. The other drafter
  gap, production's attention split (74 MB a pass), needs kernel changes and five more gathers a pass: about -0.2 ms
  at one stream and a loss at four on NCCL, not supported.
- Keep merged into the block step: at one stream rank 0's first drafter gather takes 0.35 ms a round (0.32 waiting for
  ranks 1 and 2), but at four streams, where a round sends two to four keep steps first, it takes 0.07 to 0.14 ms mean
  (0.41 in the rounds with one keep), so the followers' step receives are not what makes them late. Not supported.

## 4. The lever: `TF_GLM_OVN_DRAFT_INGEST_SPLIT`

`0034-draft-ingest-split.patch`, sha256 `773988ed1c05df7995916aa57ebf602a1e02be6825c25b8b90753c5cfe7c81c6` (525 lines,
LF, 19 hunks, 253 added, 25 removed; applies to the series, which is tree `4ed20ea3d175`). Default off. At two ranks or
more an ingest of a decode verify's tap rows
(32 or fewer) runs fc and every layer's k, v as this rank's 64-column share (fc 1408/1344/1344, k and v 384/320/320 at
TP=3), with the whole linear's K slices (`cuda_q4.Q4.sk`, `kSlices`), gathers the shares through the drafter's
partial-sums buffer and places them with `cuMemcpy2DAsync`; the five k, v matmuls take one launch of group sums. Drafts
equal the whole path's by construction (same rows quantized, same tile lanes, same K order and cluster sums); replies
cannot move. Prompt ingests keep the whole path.

Expected: 46 to 48 MB fewer weight bytes a round a rank, -0.1 to -0.25 ms a round at every stream count (+0.3 to
+0.6% at one stream, about +0.3% at four). Basis: the capture's fc 0.233 and k, v 5 x 0.035 ms; the shares hold 34% of
those bytes (fc about 0.08 to 0.11 ms on 88 blocks, each k, v share 0.01 to 0.015 ms), less two small gathers (11.5 to
26.8 us each, the capture's p10 to p50) and nine strided copies (2 to 4 us each). Under the box's 3% drift, so it is
measured ABBA and by `TF_GLM_DFLASH2_PROF`'s ingest phase (expected 0.48 to about 0.25 ms).

Arm lines for `scripts/arms-file.sh` (`arms-isplit.txt`), on an image of the series plus 0034:

    is-ctl|-e TF_GLM_KDA_PAD=1 -e TF_GLM_INDEX_CUDA=1 -e TF_GLM_OVN_KEPT_WALK=1 -e TF_GLM_OVN_DRAFT_ONEPASS=1 -e TF_GLM_OVN_DRAFT_DOWN4=1 -e TF_GLM_OVN_DRAFT_MLPSPLIT=4 -e TF_GLM_OVN_MLA_FUSEMERGE=1
    is-on|(is-ctl's list) -e TF_GLM_OVN_DRAFT_INGEST_SPLIT=1
    then is-on-b and is-ctl-b (ABBA), and is-prof-ctl / is-prof-on with -e TF_GLM_DFLASH2_PROF=1 -e TF_GLM_DFLASH2_LOG=300 at levels 1 4

Knob-on checks: reply digests equal to `is-ctl` at 1/2/4/6/8, the `dflash2 round` draft lines equal between the two
prof arms, and the boot line `dflash2: a decode ingest's fc in 1408 columns a rank and k, v in 2 x 384, gathered`.

## 5. Gates (on the final tree, WSL logs `~/gates/isplit2-*.log`, `~/gates/lean-isplit1-{base,head}.txt`)

- `scripts/gates.sh <lane tree> isplit2`: check-native-cuda-host rc 0 (7/7 steps); test-cuda-host rc 0 (383/383 steps,
  6280 of 6310 tests passed, 30 skipped); compile-cuda-tests rc 0 (10/10); test-glm-ring-host rc 0 (3/3);
  test-glm-logprobs-host rc 0 (7/7); test-glm-onepass-order-host rc 0; test-rows-host rc 0; fmt rc 0; `bad=0`.
- `scripts/gate-names.sh mlafix2 isplit2`: 0 failing names on both; only isplit2 fails: none.
- `scripts/lean.sh` base against head (each tree its own checker): base 6254 files, 386 problems; head 6255 files,
  386 problems; 0 new.
- `git apply --check` of the patch on the series rc 0; series + patch is the lane tree file for file (`diff -r`).
- Mutants (`mutants.sh`, the unmutated copy passing 13 of 13 first): 6 of 6 killed by an assertion of
  `test-glm-ingest-split-host` (kSlices ignoring sk; keepSlices taking the share's own slices; the extra tiles on the
  last ranks; fc placed at the widest pitch; v placed over k; a split at one rank).
- `.cu`: the patch changes none. `fatbin.sh` (for the RoCE arm, not the patch) compiles fabric/tp's mailbox.cu for
  sm_121 with CUDA 13.3 (rc 0); CUDA 13.1's headers fail on this WSL glibc (`rsqrt` exception specification).
- GPU check on the workstation's RTX 5070 (sm_120; not a Spark), `bash work/drafter-lever/gpu/run.sh`, receipt in
  `gpu/result.txt`. The harness copies the lane tree to WSL ext4, gives its copy exports of `dflash_ingest` and
  `dflash_block` and `pub` on `lin`, `gsum`, `mul4` and `place` (`harness.py`, six anchored edits; the patch is
  unchanged), and builds `tf-cuda-test` with the build's own nvcc flags for the four images the check loads
  (`nvcc-only.sh`: 4 real nvcc runs, 148 empty images). `tf-cuda-test glm-ingest-split` quantizes random bf16
  weights through the loader's own path (`quant.q4`, `q4.pack`). It then runs the engine's whole path (`lin`) against
  each rank's share (`gsum`, then `mul4` with `keepSlices`) at TP=3, for rows 1, 2, 3, 4, 7, 16, 17 and 32, through
  both 16-row and ONEPASS launches. Finally it places the rank-ordered slots with the patch's `placeFc` and `placeKv`
  through the real `cuMemcpy2DAsync`. Result, rc 0:
  - fc: whole sk 4; shares 1408/1344/1344 at col0 0/1408/2752, all sk 4. 0 of 671,744 words differ; placed rows
    0 of 671,744.
  - k, v: whole sk 8; shares 2 x 384/320/320, all sk 8. 0 of 1,679,360 words differ; placed 0 of 1,679,360.
  - Control: rank 1's fc share at its own shape's 8 K slices (`keepSlices` removed). 38 of 220,416 words differ, so
    the check sees a K-order change and `Q4.sk` is load-bearing.
