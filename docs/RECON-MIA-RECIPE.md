# RECON: the MiaAI-Lab recipes, what they carry, what it means for us

Reconnaissance of the public recipe family, done 2026-11-11 against the live repos.

## The repos

| repo | engine base | patches | pushed |
|---|---|---|---|
| [MiaAI-Lab/GLM-5.3-Flash-DGX-Sparks-1104](https://github.com/MiaAI-Lab/GLM-5.3-Flash-DGX-Sparks-1104) | TensorFold **1.1.9** at `f350cd3e` | **121 engine patches** | 2026-11-11 (active today) |
| MiaAI-Lab/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold | TensorFold (pair launcher lineage) | its own | 2026-11-04 |
| MiaAI-Lab/DeepSeek-v4.1-Flash-1017-2x/4x... | TensorFold | its own | 2026-11-09 |
| jayleaton/glm53-tensorfold-spark, Elevatormusic, bertholomus, plotarmordev/drama-tensorfold | various | independent takes | active |

The whole family is **Apache-2.0**, including the 1104 recipe's `patches/engine/`. Its CREDITS.md names the
upstream authors. That matters: patch content can be adopted with attribution instead of being re-derived.

## Where our engine sits

Our pin is `v1.2.4-242-g9c9bf542c` (the upstream changelog at #2558). The 1104 recipe is on **1.1.9** plus its
121 patches, i.e. **older** than our base. Their patch series is the historical path toward where we already
are, not a superset of it. Their own README says the two stacks are a "different engine lineage" with
"different numbers".

So the useful question is not "what do they carry" but "which of their features does our pin still lack".
Measured by grepping both trees:

| feature | their patch | in our pin |
|---|---|---|
| `CACHE_FIRST` (`TF_PROMPT_CACHE_FIRST`) | 0112 | **absent** |
| `KV_SHARD` (`TF_GLM_KV_SHARD`, TP=2) | 0114 | **absent** |
| DFlash2 window rules by expected tokens, tpm seeds | 0036, 0038 | **absent** |
| kept prompt states spill into pinned host memory | 0015 | **absent** |
| 16-row / 32-row decode window geometry | 0039, 0119 | **absent** |
| `THINK_OFF_SPLIT`, `EXTRA_EOS`, tool-call guard | 0121, 0120, 0111 | **absent** |
| fused EXL3 decode in a window's MoE glue | 0030 | absent by that name (our 0022 carries a fuse; unverified equivalence) |
| follower step in one broadcast | 0031, 0032 | absent by that name |
| `CHUNK_SOLO` | 0109/0110 family | **present** |
| `L2PF_MB` tuning | 0117 family | **present** (`L2PF` too) |
| `ld.global.nc` trellis reads (`EXL3_LOADS=nc`) | 0028 | **present** |

## Clues that change our plan

0. **The `CACHE_FIRST` port is not needed at all.** Our 1.2.4-era `kv_pool.windows()` already carries
   `b.asked`: an EXPLICIT `--prompt-cache-gib` sets the cache aside before the room is counted in whole
   windows, which is exactly what Mia's 0112 adds behind `TF_PROMPT_CACHE_FIRST`. Our serve.sh has never
   passed `--prompt-cache-gib`, so every boot ran with the default, unasked cache. The cheap experiment is
   therefore a flag plus their reserve value (`TENSORFOLD_MEMORY_RESERVE_GIB=6.5 --prompt-cache-gib 8`), not
   a port. Confirmed by reading both trees; the batch joins the phase-2 queue as B4.

1. **Adopt rather than re-derive.** With Apache-2.0 patches, the shortlist above can be ported from their
   diffs against a near-contemporary base, with CREDITS attribution, instead of RE'd from behaviour. That is
   the fastest route for `CACHE_FIRST`, the DFlash2 window rules and the window geometries.
2. **They shipped `CACHE_FIRST=1` as a default TODAY** (`MEMORY_RESERVE_GIB=6.5 CACHE_FIRST=1`,
   `PROMPT_CACHE_GIB` 5/8/4). Their own note says cache-first changed the memory split enough that a lower
   reserve funds a real prompt cache; production's Python stack also runs a cache. Our stack's reserve at P=1
   is 12.5 GiB with no cache-first, so this is a direct, cheap experiment for the low-stream shape.
3. **Their measurement record tracks what ours does not.** `docs/speed/AGREEMENT.md` and the handoffs record
   per-trial tok/s and spread, `token_sha`, `tokens_per_round`, and **`acceptance_rate`** with
   accepted/offered. Our benches record decode tok/s, TTFT and the reply sha only, so our drafter's +5% is
   unexplained while their records show 60-64% drafts landing at one stream. Adding acceptance and
   tokens/round to the harness is the cheapest way to see whether our drafter is underperforming or the
   knob set around it is.
4. **Their decode campaign's own headline**: 1 stream prose ~38-40 tok/s on a TP=2 pair with 60% draft
   acceptance; a later ring change bought +1-2% at one stream and +5-7% at four. Their numbers are on two
   Sparks, ours on three, so only the deltas and the method transfer, never the absolute cells.
5. **Their README's per-knob evidence is the pattern we should copy**: every knob row carries a measured
   delta and an exactness statement ("offs: replies byte-identical", "exact"), and the L2PF row records
   +2% at one stream and flat at 4/8. Our own L2PF cell measured neutral, which is a fact to reconcile
   against their method (their L2PF carries `L2PF_MB/_CTAS/_PACE_GBPS`; ours ran with defaults only).

## Next actions this recon implies

- Port `CACHE_FIRST` (their 0112) and the `PROMPT_CACHE_GIB` plumbing as the next patch, then A/B at
  1/2/4/6/8: it is the cheapest candidate for the one-to-four-stream gap and it is already their default.
- Add `acceptance_rate`, `accepted/offered` and `tokens_per_round` to the streams harness, then re-read the
  drafter's worth at one stream.
- Shortlist the window-geometry patches (0039/0119) and the DFlash2 window rules (0036/0038) behind them.
