# v127-drift.md - what upstream did under each of our 68 patches, pin `9c9bf542` to `v1.2.7`

Lane `V127Drift`, 2026-11-12. Read-only. Scratch in `work/v127drift/`; nothing outside this file and that
directory was written.

## What was measured, and with what

- Base: `9c9bf542cc87ec21f44cee720fc4f1c056f8c905` (`v1.2.4-242`, 2026-11-08 12:21:32 +0000).
- Target: `v1.2.7` = `93a2e93ecebff8aa52b88e58c5dd222516e69c5f` (2026-11-11 10:47:25 +0000).
- `git rev-list --count 9c9bf542..v1.2.7` = **600** commits; `git diff --stat 9c9bf542..v1.2.7 -- zig tools
  build.zig build.zig.zon` = **917 files changed, 50262 insertions, 4761 deletions**.
- Object store: `work/parity/tree` (nothing checked out there, nothing reset).
- Text survey: `work/v127/survey.tsv` (the repo's own `scripts/reseat-survey.sh` run). I re-ran the same
  decision tree in `work/v127drift/` keeping every `.rej` and every apply log (`work/v127drift/rejects.sh`,
  `work/v127drift/survey2.tsv`, `work/v127drift/rej/`). It reproduces the repo's verdict and rejected-hunk
  count on all 68 patches once one disk-full cell is discounted; that cell is explained from its own log in
  "Nothing left undetermined".
- Per-file upstream history: `work/v127drift/patch-upstream.txt` (every patch, every file it touches, every
  commit in the range that touched that file) and `work/v127drift/file-info.tsv`.
- Line-count headroom against the 600-line lean rule: `work/v127drift/headroom.tsv`.

**The series is 70 patch files but 68 patches.** `patches/engine/` now holds `0001..0044`, and `work/final/`
holds `0043..0068`; `0043-lean-comments.patch` and `0044-exl3-decode-items.patch` exist in both and are
byte-identical (sha256 `093ba2aa...` and `a965fb49...` on both copies). Any re-seat driver must de-duplicate
by name, or it applies those two twice (my re-run scored the second copy of each as `absorbed`, which is the
harmless case, but only because the first copy had already gone on).

## Table: all 68 patches

Survey verdict is `work/v127/survey.tsv`'s. "Upstream commits" names the commits in the range that rewrote the
code the patch sits on, not every commit that touched the file.

| # | patch | survey | verdict | upstream commits involved | what the re-seat must do |
|---|---|---|---|---|---|
| 0001 | ovn-knob-registry | clean | CHANGED UNDER IT | lean rule `tools/zig/lean_check.py` +44/-2 in range; `a0ffd7ef7`, `1aa85eed9`, `ce95ae966` | `getenv("TF_GLM_OVN_"...)` is now a lean finding; register the knobs as `.glm` rows in `platform/environment.zig` or read them through `core.profile.lookup` |
| 0002 | ovn-knobs-own-cache | clean | CHANGED UNDER IT | same | `getenv(S.key)` is a non-literal name: the new `HIDDEN_GETENV` rule fires on it |
| 0003 | kda-pad-one-width | partial 2 | CHANGED UNDER IT | `5b80e93ac`, `6d4191a95`, `a0ffd7ef7` | the KDA chain moved to `zig/src/cuda/kda.zig` + `common/kda.cuh`; re-express the pad against `cuda.kda`, and `cuda_engine.zig`'s region moved |
| 0004 | draft-knobs | partial 4 | CHANGED UNDER IT | `cc2fa8d23`, `55a95af06`, `d7d559944`, `6d4191a95`, `c632a57f0`, `72a28dd66`, `a0ffd7ef7`, `c5d45eee8` | `facts()` rewritten, `Kept` gained `below`, `cuda_snapshot_pages` is on `core/state_walk.zig`, `dflash.zig`'s confidence read is now a registry row |
| 0005 | index-decode-windows | clean | UNTOUCHED | none (`cuda_index.zig` 131 lines both refs, 0 commits) | nothing |
| 0006 | kept-walk-prefix-helper | partial 8 | CHANGED UNDER IT | `e5f75e8be`, `dec37f8f7`, `07ef4b385`, `9c4150079`, `1ae0ca34e`, `b41a6bb32`, `917a745ad`, `f6831ae49`, `d75e82932`, `50af2b71b` | `prompt_cache.zig` went 600 -> 525 lines over 8 commits; re-derive the walk gate against the new admission/eviction code |
| 0007 | resume-any-row | partial 5 | CONTRADICTED | `9347a8a7d`, `f3988faa7`, `c5d45eee8`, `3464a7d44` | upstream solved the same problem differently (`cuda_prompt_cuts.zig`); re-express on it rather than re-applying our rewrite |
| 0008 | reply-prefill | partial 6 | CHANGED UNDER IT | `9347a8a7d`, `6d4191a95`, `a0ffd7ef7`, `d8f95f4ea`, `dec37f8f7`, `07ef4b385` | the hook points in `cuda.zig`, `cuda_follow.zig`, `cuda_lanes.zig`, `cuda_native.zig` all moved |
| 0009 | index-sched-decode-pools32 | clean | UNTOUCHED | `5b80e93ac` touched `cuda_forward.zig` elsewhere | nothing textual; `cuda_forward.zig` is at 600 lines at the tag |
| 0010 | index-regroup | clean | UNTOUCHED | none | nothing |
| 0011 | one-chunk | partial 2 | CHANGED UNDER IT | `eb29a68a5`, `7547c99c2`, `a0ffd7ef7`, `5b80e93ac` (`cuda.zig` +7 lines, 7 commits), 13 commits on `cuda_native.zig` | re-place the module registration in `cuda.zig` and the open-path hook in `cuda_native.zig` |
| 0012 | plain-margin | partial 2 | CHANGED UNDER IT, partly MOVED | `562b333d1`, `2b5258b39`, `63be446c8`, `d7d559944`, `6d4191a95` | `Constants.plain_margin` moved `depth.zig:13` -> `depth_constants.zig:9`; `config.zig` went 209 -> 230 lines; `facts()` rewritten |
| 0013 | exchange-kb | clean | UNTOUCHED | none (`cuda_relay.zig` 0 commits) | nothing |
| 0014 | router-warm | partial 1 | CHANGED UNDER IT | `cuda.zig` 7 commits | only the import/registration block in `cuda.zig` moved |
| 0015 | win-free | partial 3 | CHANGED UNDER IT | `6d4191a95`, `d7d559944`, `c8bc0a602`, `780020231`, `09dc2a15a` | `free_shared` exists in neither ref, so it is still ours; both its anchors (`config.zig` `Model`/`Config`, `facts()`) moved |
| 0016 | sparse-onepass | partial 1 | CHANGED UNDER IT | `5b80e93ac` (`cuda_forward.zig`), `c0f8e1c4c`, `b3a68c565` | one hunk in `cuda_forward.zig`; the rest is ours |
| 0017 | onepass-pipe | clean | UNTOUCHED | `f35900e60`, `42735f94f`, `f1ab10fe9` added neighbours in `kernels.zig` | nothing textual |
| 0018 | shared-drafts | refused 2/2 | ABSORBED (partly) and CONTRADICTED | `cc2fa8d23`, `d7d559944`, `55a95af06` | upstream's own default is now `drafting and !block`; the drafter case the knob existed for is already off, the head case is on and capped at 3 |
| 0019 | kda-chunked | partial 2 | CHANGED UNDER IT | `5b80e93ac` | `cuda_kda_block.zig` and `cuda.zig` moved under the shared KDA module |
| 0020 | mm-knobs | partial 5 | CHANGED UNDER IT and MOVED | `c0f8e1c4c`, `88267c063`, `5d380e4ee`, `a0ffd7ef7`, `1aa85eed9` | GLM's SwiGLU rows moved out of `glm_glue_moe.cuh` into `glm_swiglu.cuh`; `glm_glue_bmm.cuh` lost the router tile; `cuda_mm.zig`'s env read is now a registry read |
| 0021 | mla-knobs | clean | MOVED (semantic) | `42735f94f`, `b3a68c565` | text applies, but the chunk bodies our `glm_glue_attn_ovn.cuh` mirrors moved to `zig/kernels/cuda/common/mla.cuh`; re-derive the OVN variants from the new home |
| 0022 | glue-fuse | partial 10 | CHANGED UNDER IT and MOVED | `88267c063`, `5d380e4ee`, `c0f8e1c4c`, `5b80e93ac`, `6d4191a95` | same two headers as 0020 plus `cuda_state.zig`/`cuda_shared.zig` under the KDA move |
| 0023 | shared-round-era | partial 10 | CHANGED UNDER IT, partly CONTRADICTED | `6d4191a95`, `cc2fa8d23`, `55a95af06`, `d7d559944`, `c5d45eee8`, `9347a8a7d`, `a0ffd7ef7`, `16287f6b1` | the 55-hunk, 28-file patch; upstream now has its own load-time cost timing (`cuda_lane_costs.zig`, `cuda_lane_cost_measure.zig`) that replaces our `cuda_cost_time.zig` |
| 0024 | test-cuda-host-repairs | partial 6 | CHANGED UNDER IT | `cc2fa8d23`, `c5d45eee8`, `6d4191a95`, `d8f95f4ea` | it repairs our own port; recompute it after the re-seat rather than re-applying it |
| 0025 | warm-wait-wiring | partial 1 | CHANGED UNDER IT | 9 commits on `zig/src/native/cuda.zig` (548 -> 587), `d8f95f4ea` | re-place the wait call |
| 0026 | glm-knob-wiring | refused 1/1 | CHANGED UNDER IT | `6d4191a95`, `cc2fa8d23`, `55a95af06`, `d7d559944`, `c632a57f0` | `facts()` is a different literal: new `costs`, `shared_step_ms`, `window_costs_lone`, `shared_drafts`; add the three knob lines to upstream's form |
| 0027 | shared-drafts-gating | refused 3/3 | CONTRADICTED | `cc2fa8d23`, `55a95af06` | upstream set `allocate_shared_drafts = drafting and !block` itself and fixed `copy_drafts_cuda_test`'s literal with it; our correction has no target |
| 0028 | pin-test-adaptations | partial 1 | CHANGED UNDER IT | `6d4191a95`, `cc2fa8d23`, `63be446c8`, `5151f19f3` | `cuda_zero_budget_test.zig` was rewritten by `cc2fa8d23` (+99/-11) |
| 0029 | dsa-double-launch | clean | UNTOUCHED | none | nothing |
| 0030 | draft-confidence | refused 1/1 | ABSORBED | n/a; the line is upstream's own | `.draft_confidence = if (block) null else self.mtp_confidence` is at `cuda_lanes.zig:115` at v1.2.7 and at the pin; the patch only restored what our own port dropped |
| 0031 | head-block-rule | clean | UNTOUCHED | none | nothing |
| 0032 | fatbin-catalog | clean | UNTOUCHED | `e32de56c6`, `7b3e2d76a`, `42735f94f`, `f1ab10fe9`, `f35900e60` added rows elsewhere | keep our four rows without `.native_fp`: a new upstream test asserts exactly `fp8_experts`, `qmmf`, `prompt16` are native_fp |
| 0033 | draft-onepass-shadow | clean | UNTOUCHED | none | nothing |
| 0034 | tap-prefillchunk-arity | clean | CONTRADICTED | `9347a8a7d` kept `prefillChunk`'s 7-argument shape | it exists only to follow 0007's extra `rows` argument; if 0007 re-seats on `prompt_cuts`, drop it |
| 0035 | top1-sums | clean | UNTOUCHED | none | nothing |
| 0036 | chunk-step-start-len | refused 1/1 | ABSORBED | n/a; the fields are upstream's own | upstream's chunk send carries `.depth = start, .top_k = ids.len` at `cuda_follow.zig:234` (pin) and `:250` (tag); fold into the re-seated 0007 and drop |
| 0037 | kda-fill | clean | UNTOUCHED | `5b80e93ac` touched the file elsewhere | nothing textual |
| 0038 | router16-kernel | clean | CHANGED UNDER IT | `c0f8e1c4c`, `42735f94f`, `0924d298d` | the device helpers survive (`glm_router::mma16816` moved to `glm_router_mma.cuh`, reached through a 4-line `glm_glue_router.cuh` shim) but `Kernels.router_part` is gone, the unaligned branch is now `error.RowShape`, and the tile launch needs the new `.shared = router_tile_smem`; our `router16` and `router_tile_pdl` branches must be re-placed in upstream's `router()` |
| 0039 | glue-type-guard | clean | UNTOUCHED | `c0f8e1c4c`, `b3a68c565` touched the file elsewhere | nothing textual |
| 0040 | kda-pad-common-width | clean | MOVED | `5b80e93ac`, `6d4191a95` | same shared-KDA move as 0003; verify the restored width against `cuda.kda`'s copy of the chain |
| 0041 | restore-pin-forms | partial 9 | CHANGED UNDER IT | the whole `6d4191a95` / `9347a8a7d` / `5b80e93ac` / `c0f8e1c4c` set | it restores the pin's own lines; most of it disappears if the re-seat starts from upstream's text instead of re-applying the fork's |
| 0042 | pair-fits-rings | clean | UNTOUCHED | `9347a8a7d` added `if (e.cur.cuts.items.len > 0) return false;` to `pairedAt` | nothing textual; the refusal sits beside upstream's new one |
| 0043 | lean-comments | clean | UNTOUCHED | lean rule changed (new getenv rules) | recompute: it fixes multi-line comments our own 0032/0038/0042 add, and the new getenv rules add findings of their own |
| 0044 | exl3-decode-items | clean | UNTOUCHED | `edc16dfe9` added `Layer.after` | nothing; PR #2044 is **not** in v1.2.7 (see Q5) |
| 0045 | chunk-grid-end | clean | CONTRADICTED | `9347a8a7d`, `c5d45eee8` | the defect it repairs is unreachable in upstream's design (resumes only at cold cuts); if 0007 re-seats on `prompt_cuts`, drop it, but note upstream pays for that by refusing pairing whenever cuts exist |
| 0046 | head-flag | clean | UNTOUCHED | `6d4191a95`, `9347a8a7d`, `a0ffd7ef7` touched the files elsewhere | nothing textual |
| 0047 | whole-pass-steps | partial 2 | CHANGED UNDER IT | `9347a8a7d`, `c5d45eee8`, `3464a7d44`, `6d4191a95` | the whole-pass step loop is now `prompt_cuts.nextCut`; re-express the test against `leaderRows`/`stepRows` |
| 0048 | batch-mark-inside | refused 2/2 | CHANGED UNDER IT | `9347a8a7d` | `canBatch` gained `and s.chunks.len == 0` (`cuda_lanes.zig:599`); add our marks loop to upstream's line, not to the pin's |
| 0049 | follower-disk-bind | refused 1/1 | CHANGED UNDER IT | `9347a8a7d`, `3464a7d44` | the exclusion chain gained `kind != .form` and `Kind` gained `form`, `cuts`; `.disk` is ours, so the chain must be upstream's plus `.disk` |
| 0050 | one-chunk-wiring | partial 2 | CHANGED UNDER IT | `9347a8a7d`, `72abee671`, `94b0605dc`, `5b80e93ac`, `16287f6b1` on `zig/build/glm_family_host.zig`; 13 on `cuda_native.zig` | re-place the build step and the engine hooks |
| 0051 | fp8-tile-ahead | partial 5/6 | MOVED | `42735f94f` | `glm_glue_attn.cuh` lost 208 lines to `zig/kernels/cuda/common/mla.cuh`: the FP8 latent key fetch now lives there, shared with the new `tf_mla_*` entries |
| 0052 | exl3-chunk-rows | clean | UNTOUCHED | none (`cuda_exl3.zig` 206 lines both refs, 0 commits) | nothing |
| 0053 | exl3-dec-order | clean | UNTOUCHED | `edc16dfe9` (+1 line in `exl3_experts.cu`, +2 in `exl3_experts.zig`) | nothing textual; `Layer` gained `after: bool` |
| 0054 | logit-gather-blocks | clean | UNTOUCHED | `9347a8a7d` touched the host stub elsewhere | nothing |
| 0055 | reply-prefill-spares | partial 6 | CHANGED UNDER IT | `e5f75e8be`, `dec37f8f7`, `07ef4b385`, `9c4150079`, `917a745ad`, `d8f95f4ea`, 9 commits on `native/cuda.zig` | the eviction guard must be re-derived against the rewritten `prompt_cache.zig` / `prompt_cache_policy.zig` |
| 0056 | register-gpu-checks | clean | UNTOUCHED | 4 commits on `zig/tests/cuda/main.zig` | text applies; `main.zig` is 595 at v1.2.7 and the series pushes it to 606 (see "Lean limits") |
| 0057 | onepass-pipe-scale | partial 1 | CHANGED UNDER IT | 7 commits on `zig/build/glm_family_host.zig` | re-place the build step registration |
| 0058 | draft-edge-noise | clean | UNTOUCHED | none (`dflash_select.zig` 64 lines both refs, 0 commits) | nothing |
| 0059 | df-sumw-record | clean | UNTOUCHED | `c0f8e1c4c` added a router record to the same file | nothing textual |
| 0060 | ring-past-refusal-test | clean | UNTOUCHED | none | nothing |
| 0061 | shared-window-width | clean | UNTOUCHED | `6d4191a95` raised `window_rows` 8 -> 32 | text applies, and the patch becomes **more** load-bearing: a literal 4 would now be wrong by 8x |
| 0062 | rows-worker-and-quiesce-drain | clean | UNTOUCHED | 18 commits on `zig/src/server/root.zig` | nothing textual |
| 0063 | snapshot-past-rings | clean | UNTOUCHED | `6d4191a95` | nothing textual |
| 0064 | memo-equal-strindex | partial 2 | CHANGED UNDER IT | `6ed8a455a`, `81d2a912c`, `a56c63daf` on `tokenizer/memo.zig` | the two rejects are `zig/build/cuda.zig:340` and `memo.zig:5`, where our `pub const min_bytes = 1024;` was replaced by `a56c63daf` ("keep segments of 64 bytes or more, not 1,024"); hunks 2 and 3 still apply at +3 and +2 |
| 0065 | prompt-bench | partial 2 | CHANGED UNDER IT | `fca7fc945`, `33d5c7dbf`, `f8571b9b4`, 18 commits on `server/root.zig`, 6 on `build.zig` | the two rejects are `build.zig:245` (the step list upstream grew) and `zig/src/server/root.zig:15` (the `pub const` plus `test` block); the `zig/build/server.zig` hunk applies at +4 |
| 0066 | render-once-host-once | clean | UNTOUCHED | 2 commits on `tokenizer.zig`, 18 on `server/root.zig` | text applies; `tokenizer.zig` is 595 at v1.2.7 and the series pushes it to 615 (see "Lean limits") |
| 0067 | glue-fuse-last-layer | clean | UNTOUCHED | `5b80e93ac` touched `cuda_forward.zig` elsewhere | nothing textual |
| 0068 | pieces-resume-keepwin | clean | UNTOUCHED | none (the file is ours) | nothing |

Counts: UNTOUCHED 30, CHANGED UNDER IT 27, MOVED 3 (0021, 0040, 0051), CONTRADICTED 4 (0007, 0027, 0034,
0045), ABSORBED 2 (0030, 0036), plus 0018 which is both absorbed in part and contradicted in part.

## Evidence, patch by patch (every non-UNTOUCHED verdict)

### 0001, 0002 - the OVN knob registry: the gate under it changed, and upstream built its own

Two independent facts.

**The lean rule changed inside the range.** `git diff 9c9bf542 v1.2.7 -- tools/zig/lean_check.py` is
+44/-2 (`work/v127drift/lean_check.diff`). Its first line now reads "600-line files, one-line comments within
120 columns, **no direct getenv of a setting**", and it adds:

```
DIRECT_GETENV = re.compile(r'\bgetenv\(\s*"((?:TF|TENSORFOLD)_[A-Za-z0-9_]*)"')
HIDDEN_GETENV = re.compile(r'(?<!fn )\bgetenv\(\s*[^"\s)]')
NAME_READERS = ("zig/src/platform/environment.zig", "zig/src/core/profile.zig", "zig/src/platform/sys.zig",
                "zig/src/platform/win_c.zig")
```

Patch 0001 writes `std.c.getenv("TF_GLM_OVN_" ++ name)`, which `DIRECT_GETENV` matches on the literal prefix
`TF_GLM_OVN_`. Patch 0002 replaces it with `std.c.getenv(S.key)`, which `HIDDEN_GETENV` matches because the
argument is not a literal and `zig/src/cuda/ovn.zig` is not in `NAME_READERS`. Either way the re-seated 0001
and 0002 are **new lean findings** on a gate our own `scripts/lean.sh` runs base-against-head, so the
re-seat fails that gate as it stands.

**Upstream now has a registry for exactly this.** `zig/src/platform/environment.zig` went 320 -> 364 lines and
gained a `.glm` scope with nine rows (lines 68-76 at the tag):

```
.{ .name = "TF_GLM_HOST_CACHE", .scope = .glm, .kind = .flag, .forms = "0 or 1" },
...
.{ .name = "TF_GLM_DRAFT_CONFIDENCE", .scope = .glm, .kind = .real, .max = 1, .forms = "a finite chain-chance cut from 0 to 1 (default 0.7)" },
```

and a new `zig/src/families/glm/cuda_env.zig` (20 lines) whose `startup()` calls
`environment.checkScope(.glm, environment.Process{})`. Commits: `a0ffd7ef7` "the 0/1 switches and the DFlash2
log count as glm rows of the shared table", `1aa85eed9` "register GLM's seven 0/1 switches as identical, read
through the registry", `ce95ae966` "TF_GLM_PROF and TF_GLM_LINK_WAIT stay outside the registry",
`c632a57f0` "TF_GLM_DRAFT_CONFIDENCE as a glm row". `git grep -c TF_GLM_OVN v1.2.7 -- zig tools docs` = 0, so
none of our knob names exist upstream.

Re-seat: either add every `TF_GLM_OVN_*` as a `.glm` row and read it with `environment.read` /
`core.profile.lookup` (the shape upstream will accept), or keep `ovn.zig` and add it to the local
`lean_check.py`'s `NAME_READERS` (which upstream would not take, and which hides future findings). The first
is the only option that also keeps the `scripts/lean.sh` gate green.

### 0003, 0019, 0037, 0040 - the KDA chain moved into shared CUDA

`5b80e93ac` (2026-11-04) "CUDA: share KDA chain and saved-row replay", 14 files, +710/-405:

```
zig/kernels/cuda/common/kda.cuh                    | 383 ++++++
zig/kernels/cuda/glm_kda.cu                        | 385 +------
zig/src/cuda/kda.zig                               | 155 +++++
.../cuda_kda.zig => cuda/kda_pre_shared_test.zig}  |  18 +-
zig/src/cuda/kda_test.zig                          | 122 +++
zig/src/families/glm/{cuda,cuda_forward,cuda_kda_block,cuda_shared,cuda_state,cuda_tile}.zig
```

`zig/src/families/glm/cuda_kda.zig` is **gone** at v1.2.7: `git log --follow --name-status` shows
`D zig/src/families/glm/cuda_kda.zig` in that commit, with its content renamed to
`zig/src/cuda/kda_pre_shared_test.zig`. Our tree still carries `cuda_kda.zig`
(`work/v127drift/glmfiles-final.txt`). Two later review commits tighten it: `658f38236` "refuse a model's KDA
shape other than the kernels' before launch" and `72abee671` "dk, dv and taps held to kda.cuh's DK, DV and
TAPS by a host test".

0003's two rejected hunks are in `cuda_engine.zig` and `cuda_kda_block.zig`; 0040 touches
`cuda_kda_block.zig`, `cuda_state.zig` and `cuda_tile.zig`, all three re-pointed by that commit; 0019 adds a
chunked KDA kernel beside the one that moved.

### 0007, 0034, 0036, 0045, 0047, 0048, 0049 - upstream built prompt cuts

Four commits, in order: `9347a8a7d` (2026-11-08) "opt-in message-start prompt cuts", `f3988faa7` (request
starts keep a 256-token minimum), `c5d45eee8` (2026-11-09) "a kept state carries the chunk starts below it,
and rank 0's step rows are the followers'", `3464a7d44` (2026-11-09) (moves the refusal into `cuda_env.zig`
and the check into `prompt_cuts.resumes` to keep both files under 600 lines).

They add `zig/src/families/glm/cuda_prompt_cuts.zig` (111 lines in the first commit, 86 more in the third),
with:

```
pub fn nextCut(len: usize, cuts: []const u32, at: usize) usize
pub fn coldCut(len: usize, cuts: []const u32, pos: usize) bool
pub fn below(cuts: []const u32, at: u32) u64
pub fn resumes(len: usize, cuts: []const u32, at: u32, kept_below: u64) bool
pub fn leaderRows(len: usize, cuts: []const u32, start: usize, wide: bool) usize
pub fn stepRows(len: usize, cuts: []const u32, start: usize, part_len: usize) !usize
```

and wire them through: `cuda_engine.zig:342` `const end = prompt_cuts.nextCut(ids.len, e.cur.cuts.items,
start);`, `:352` `if (r.at == 0 or r.at >= len or !prompt_cuts.coldCut(len, e.cur.cuts.items, r.at)) return
error.BadResume;`, `:363` `const rows = try prompt_cuts.stepRows(len, e.cur.cuts.items, start, part.len);`,
`cuda_follow.zig:247` `const n = prompt_cuts.leaderRows(ids.len, x.e.cur.cuts.items, start, wide);`,
`cuda_lanes.zig:385` `... or !engine.prompt_cuts.resumes(len, s.chunks, k.at, k.below) ...`,
`cuda_native.zig:441` `k.* = .{ ..., .below = ...below(e.cur.cuts.items, at) };`, and
`cuda_engine_types.zig:14` `pub const Kept = struct { id: u64, at: u32, below: u64 = 0 };`.

The comparison with our 0007, from `work/v127drift/rej/0007-*cuda_engine.zig.rej`:

| | our 0007 | v1.2.7 |
|---|---|---|
| where a step's rows come from | a new `rows` argument on `prefillChunk` (8 args) | `prompt_cuts.stepRows`, signature unchanged at 7 args |
| what a resume is allowed to be | any row (`r.at % prefill_rows` check deleted) | any **cold cut** (`coldCut`), plus a digest match (`below`) |
| what drives the cut points | prompt-cache marks, on by default | the request's message starts, `TF_GLM_REQUEST_STARTS=1`, off by default |
| pairing after an off-grid start | our 0045 returns the chunk end to the grid | `pairedAt` refuses outright while any cut exists (`cuda_prompt_pair.zig:66`) |
| staleness of a kept state | position only | position plus `below`, refused as `SnapshotOutOfStep` |

Consequences, each a separate decision for the re-seat:

- **0034 and 0036 lose their reason.** `prefillChunk` keeps 7 arguments upstream, so there is no arity to
  repair (0034). The chunk send at `cuda_follow.zig:250` already reads
  `... .depth = @intCast(start), .top_k = @intCast(ids.len) }, part);` - the two fields 0036 restores were
  never missing upstream; our 0007 dropped them when it moved the row count into `flags` bits 16+.
- **0045's defect is unreachable upstream**, because a resume can only land on a cold cut, so with no cuts
  every start is on the 2,048 grid. Upstream pays for that with a blanket pairing refusal when cuts exist,
  which is a measured loss for us (`docs/PORT-LEFTOVER.md` S6: pairing is 1.6-2.6% of a cold pass).
- **0048 must be rebuilt on upstream's line.** v1.2.7 `cuda_lanes.zig:599`:
  `return s.prompt_logprobs == null and s.images.len == 0 and s.reuse.saved == null and s.prompt_len <=
  engine.prompt_rows and s.chunks.len == 0; // a batched pass keeps nothing at a request start` - the same
  class of bug, guarded only for request starts, not for cache marks.
- **0049 must be rebuilt on upstream's chain.** `cuda_follow.zig:358` at the tag ends
  `... and kind != .pool and kind != .form`, and `Kind` is
  `{ begin, prefill, verify, keep, draft, end, drop, release, chunk, shared, image, block, many, redraw, idle,
  snapshots, pool, form, cuts }`. There is no `.disk` upstream; ours comes from 0023.

### 0012, 0015, 0018, 0023, 0026, 0027, 0030 - `facts()` and the lanes cost model were rewritten

Pin `cuda_lanes.zig` `facts()` (lines 94-118) against v1.2.7's (lines 96-125):

```
pin                                             v1.2.7
.allocate_shared_drafts = drafting,             .allocate_shared_drafts = drafting and !block,
.first_copy_rows = mtp_rows,                    .first_copy_rows = 4,
.mtp_step_ms = if (block) 1.6/max_held else 0,  .mtp_step_ms = if (costs) |c| c.step_ms else if (block) ...
(absent)                                        .shared_step_ms = if (costs == null) null else 0,
.window_costs = if (block) &copy_policy...      .window_costs = if (costs) |c| &c.window else if (block) ...
(absent)                                        .window_costs_lone = costs != null,
(absent)                                        .shared_drafts = if (block) 0 else shared_head_drafts,
```

plus a new `const costs = if (block) null else if (self.costs) |*c| c else null;` and a three-argument
`copy_policy.apply(self.facts(), enabled, self.x.e.drafter == null and self.costs != null)`.

Commits: `6d4191a95` (the load-time timing and `cuda_lane_costs.zig`, 210 new lines), `d7d559944`
(`Model.shared_drafts`, GLM sets 3 for the MTP head), `55a95af06` (`window_costs_lone`: timed prices are one
stream's), `cc2fa8d23` (`drafting and !block`), `c632a57f0` (the confidence row). Core side,
`zig/src/core/lanes/config.zig` went 209 -> 230 lines and gained `shared_drafts:u32` (line 35),
`window_costs_lone:bool` (34) and `shared_step_ms:?f64` (37).

What this means per patch:

- **0018 / 0027 are superseded in the case that mattered.** Their point was to stop a DFlash2 block's shared
  rounds going through the core allocator. `cc2fa8d23` does exactly that upstream, by default, and rewrote
  `copy_drafts_cuda_test` with it (+99/-11 in `cuda_zero_budget_test.zig`, and `copy_drafts_cuda_test.zig`
  changed in `55a95af06`, `d7d559944` and `cc2fa8d23`). The MTP-head half of our knob is contradicted:
  upstream keeps the allocator on for the head and caps it at three drafts instead.
- **0030 is absorbed.** Its line is upstream's own at `cuda_lanes.zig:115`, and was the pin's own at
  `cuda_lanes.zig:111`. It only ever repaired a line our own port had dropped.
- **0026 needs rewriting, not re-applying**: the three fields it adds (`free_shared`, `allocate_shared_drafts`,
  `plain_margin`) sit in a literal that now has four new neighbours.
- **0015's `free_shared` is still ours**: `git grep free_shared` finds nothing at either ref outside our tree.
- **0012's `plain_margin` moved**: `depth.zig:13` at the pin, `depth_constants.zig:9` at the tag, with
  `depth.zig` keeping only the two use sites (161, 163).
- **0023 is the one to redesign.** Upstream now times window and shared-row prices at load
  (`cuda_lane_costs.zig`, `cuda_lane_cost_measure.zig`), which is what our `cuda_cost_time.zig` and the
  `TF_GLM_OVN_COST_TIME` knob do. Keeping both means two cost tables in one `facts()`.

### 0020, 0022, 0038 - the glue headers were split and the router moved

- `88267c063` "GLM's SwiGLU rows in their own header (glm_swiglu.cuh)": `glm_glue_moe.cuh` -53 lines, new
  `glm_swiglu.cuh` +63, with `AFTER` as a macro parameter; `5d380e4ee` follows up on the comments.
- `c0f8e1c4c` "run the router's K slices on the shared mma tiles": `glm_glue_bmm.cuh` -68,
  `glm_glue_router.cuh` -29, `cuda_glue.zig` 12 lines changed, new contract test. `glm_glue_bmm.cuh` is 400
  lines at the pin and 340 at the tag.
- `0924d298d` created `zig/kernels/cuda/common/router_mma.cuh`; `42735f94f` created
  `zig/kernels/cuda/glm_router_mma.cuh` and left `glm_glue_router.cuh` as a four-line shim:

```
// GLM's router mma helpers for the glue image: the m16n8k16 wrapper and register pairs from glm_router_mma.cuh.
#pragma once

#include "glm_router_mma.cuh"
```

`tf_glm_router_part` exists at the pin (`glm_glue_router.cuh:24`) and nowhere at the tag. `glm_router::pair`
and `glm_router::mma16816` are at `glm_router_mma.cuh` and still reachable from `glm_glue_bmm.cuh`, which
includes both `glm_glue_router.cuh` and `common/router_mma.cuh` (lines 4-5). The host side changed too:

```
zig/src/families/glm/cuda_glue.zig:168  pub fn router(set: Set, stream, x, x_stride, w, out, part, m, d, ne) !void {
:169    if (d % (router_ks * 64) != 0) return error.RouterWidth;
:170    if (x % 16 != 0 or x_stride % 8 != 0 or w % 16 != 0) return error.RowShape;
:173    try cuda.launch.launch(set.glue.router_tile, .{ .grid = .{ .x = cdiv(m, 64), .y = cdiv(ne, 32), .z = router_ks }, ... });
```

Three host-side symbols our stack uses break. The pin's `router()` branches between two kernels and our
`work/final/tree` copy adds a third branch:

```
work/final/tree/zig/src/families/glm/cuda_glue.zig:55   router_part: cuda.Function,
:253   if (set.glue.router16) |f| if (m <= 16) { // TF_GLM_OVN_ROUTER16: 16-row tiles, each warp 8 experts
:257   const tile = if (set.pdl_early) set.glue.router_tile_pdl else set.glue.router_tile;
:260   try cuda.launch.launch(set.glue.router_part, .{ .grid = .{ .x = cdiv(m, 16), ... } }, stream, &a);
```

At v1.2.7 `Kernels` has no `router_part` field (it is `router_tile` alone, `cuda_glue.zig:35`), the unaligned
branch is a flat `return error.RowShape`, and the tile launch now passes an explicit
`.shared = router_tile_smem` where `router_tile_smem = 2 * (64 + 32) * (64 + 8) * 2` (`:165`), a constant the
pin did not have. Our tree also still defines `tf_glm_router_part` in `glm_glue_router.cuh`, the file upstream
reduced to the include shim.

So 0038's device function still compiles in place and `glm_router::mma16816` is still reachable; what has to
be rebuilt is the host body: re-place the `router16` branch into upstream's new `router()`, decide whether to
keep our `router_part` kernel and its unaligned branch at all (upstream dropped both, saying no caller passes
unaligned rows), and re-derive 0022's `router_tile_pdl` twin from `common/router_mma.cuh` rather than from the
hand-written tile that no longer exists. The alignment refusal at `:170` does not block our 16-row path: it is
about pointer and stride alignment, not row count.

### 0021, 0051 - the MLA chunk bodies moved to `common/mla.cuh`

`42735f94f` (2026-11-06) "a shared MLA image for 64 roped columns and 128-wide heads, on GLM's chunk bodies":
`glm_glue_attn.cuh` -208 lines, new `common/mla.cuh` +342, new `mla.cu` +54, new `cuda/mla.zig` +156, plus
`b3a68c565` as its review follow-up. The commit says GLM's entries instantiate the defaults so `glm_glue`'s
bytes are unchanged.

0021 applies clean because it edits `glm_glue.cu` and two headers of our own
(`glm_glue_attn_ovn.cuh`, `glm_glue_latent_ovn.cuh`) rather than `glm_glue_attn.cuh`. 0051 does edit
`glm_glue_attn.cuh` and loses 5 of its 6 hunks there. The FP8 latent key fetch that 0051 ports (fork
`450b9519c`, about 220 ms of a 2,048-row chunk per `docs/PORT-LEFTOVER.md` S4) now has to be written against
`common/mla.cuh`'s chunk template, where it will also be shared with the new `tf_mla_*` launches.

`glm_glue_attn.cuh` is 356 lines at the pin and 150 at the tag: everything inside `namespace glm_attn`
(`quad_sum`, `quad_max`, `cp16`, `ldm4`, `wide`, `narrow`, `wide_smem`, `chunks_wide`) moved, and what is left
is the `extern "C"` entries plus the merge and index-score kernels. The tag's `glm_glue_attn.cuh` includes
`common/mla.cuh`, so our `#include "glm_glue_attn.cuh"` still brings `glm_attn::` into scope.

Our `glm_glue_attn_ovn.cuh` is a hand-copied variant of that body ("glm_attn::chunks_wide with the tile loop
bounded", its own comment at line 14), and the body it copies has grown:

```
pin   template <int HB, bool FP8 = false>
      __device__ void chunks_wide(qa, lc, pos, tok, cnt, po, pm, pl, rows, heads, w, scale, sparse, pt, pstep,
                                  scales = nullptr)
      template <int HB> constexpr int wide_smem() { return (HB*LW + 2*KT*LW + HB*KT)*2 + (HB*4 + 2*HB)*4; }

tag   template <int HB, bool FP8 = false, int RW = 0, bool SPLIT = false>
      __device__ void chunks_wide(... same 15 ..., scales = nullptr, int sw = 1, int sr = 0)
        static_assert(!(FP8 && RW != 0)); static_assert(!(SPLIT && FP8)); constexpr int MT = HB/16, KW = LW+RW;
      template <int HB, int RW = 0> constexpr int wide_smem() { return (HB*(LW+RW) + 2*KT*(LW+RW) + HB*KT)*2 + ... }
```

Both new template parameters default, so 0021 very likely still compiles; what it stops being is a faithful
copy. The re-seat should re-derive `glm_attn_ovn::chunks` from `common/mla.cuh`'s body at its new shape, or
better add the bounded tile loop as one more parameter on the shared template, which is also the form upstream
would take.

`glm_glue_latent_ovn.cuh` is the same situation one level down: its `glm_latent_ovn::absorb<F8>` and
`expand<F8>` now have shared counterparts in `common/mla.cuh` as `tf_mla::absorb_q<D>` (line 258) and
`tf_mla::expand_v<DV>` (line 288), described by `42735f94f` as "tf_glm_absorb_q/expand_v's arithmetic".
`glm_glue_latent.cuh` itself was not gutted: its `extern "C"` kernels are still at lines 9 and 39.

### 0004, 0006, 0008, 0011, 0024, 0025, 0028, 0050, 0055, 0057, 0064, 0065 - regions rewritten under them

Shortest form, each with the file that rejected and the commit that rewrote it:

- 0004: `cuda_lanes.zig` (11 commits), `cuda_engine_types.zig` (`c5d45eee8` adds `Kept.below`),
  `dflash_load.zig` (`a0ffd7ef7` turns the env read into a registry read).
- 0006: `prompt_cache.zig` 600 -> 525 lines over `d75e82932 9c4150079 07ef4b385 b41a6bb32 f6831ae49 1ae0ca34e
  dec37f8f7 e5f75e8be`; `prompt_cache_policy.zig` over four of those; `zig/build/lane_halt_host.zig` over
  `1ae0ca34e e5f75e8be`.
- 0008: `cuda.zig` (`eb29a68a5 9347a8a7d 63be446c8 6d4191a95 5b80e93ac a0ffd7ef7 7547c99c2`),
  `cuda_follow.zig`, `cuda_lanes.zig`, `cuda_native.zig`.
- 0011: `cuda.zig` and `cuda_native.zig` (581 -> 599 lines, 13 commits).
- 0024: `cuda_lanes_test.zig` (`c5d45eee8` +38), `cuda_pages_test.zig` (`d8f95f4ea`).
- 0025: `zig/src/native/cuda.zig` 548 -> 587, nine commits including `ca83a689a` "scale kept-state budgets
  after streams are counted" and `edeae56b3` "groups sized by bytes a row".
- 0028: `cuda_zero_budget_test.zig` rewritten by `cc2fa8d23` (+99/-11).
- 0050: `zig/build/glm_family_host.zig`, seven commits.
- 0055: `lane_host.zig` 585 -> 591 (`d8f95f4ea` among five), `prompt_cache*.zig` as 0006, `native/cuda.zig`
  as 0025.
- 0057: `zig/build/glm_family_host.zig` again.
- 0064: `zig/src/core/tokenizer/memo.zig` over `a56c63daf` "keep segments of 64 bytes or more, not 1,024",
  `81d2a912c`, `6ed8a455a`.
- 0065: `build.zig` (6 commits), `zig/build/server.zig` (`fca7fc945 33d5c7dbf f8571b9b4`), `server/root.zig`
  (18 commits, 257 -> 285).

## Lean limits: four files pass 600 lines if the series goes on as it is

`work/v127drift/headroom.tsv` takes, per file, the pin's line count, our final tree's, v1.2.7's, and projects
v1.2.7 plus the net lines our series adds. Four files pass 600, which is a hard failure of
`scripts/lean.sh` and of upstream's own CI rule:

| file | pin | ours | v1.2.7 | our net | projected |
|---|---|---|---|---|---|
| `zig/src/families/glm/cuda_follow.zig` | 509 | 594 | 533 | +85 | **618** |
| `zig/src/families/glm/cuda_native.zig` | 581 | 599 | 599 | +18 | **617** |
| `zig/src/core/tokenizer/tokenizer.zig` | 575 | 595 | 595 | +20 | **615** |
| `zig/tests/cuda/main.zig` | 589 | 600 | 595 | +11 | **606** |

Four more are at the line with no room at all at v1.2.7: `zig/src/server/hf_text.zig` 600,
`zig/src/families/glm/cuda_lanes.zig` 600, `zig/src/families/glm/cuda_forward.zig` 600,
`zig/src/core/rows_store.zig` 600. Upstream hit this itself and solved it by splitting
(`3464a7d44`: "Main's window and link changes grew cuda_native.zig to 589 lines and cuda_lanes.zig to 599, so
the switch's startup refusal moves beside GLM's other startup checks (cuda_env.zig)"). The re-seat has to do
the same, and the split is work that belongs **before** the conflicted patches, not after.

**Which patch spends the lines.** `git apply --numstat` on each patch, added minus removed, for the four GLM
files, applied in series order to v1.2.7's starting count (every column sums to the net above):

| file | v1.2.7 | the patches that move it (added - removed) | peak | end |
|---|---|---|---|---|
| `cuda_follow.zig` | 533 | 0007 +13, 0008 +4, **0023 +62**, 0036 0, 0041 0, 0047 0, 0049 0, 0050 +6 | **618** | 618 |
| `cuda_native.zig` | 599 | 0007 -2, 0008 +9, 0023 +7, 0041 +4, 0055 0 | **617** | 617 |
| `cuda_lanes.zig` | 600 | 0004 +1, 0008 -14, 0012 +2, 0015 +2, 0023 -11, 0024 +2, 0026 +6, 0030 +1, 0047 -5, 0048 +2 | **601** (after 0004, before 0008) | 586 |
| `cuda_forward.zig` | 600 | 0009 +1, 0016 -5, 0017 -1, 0019 +3, 0021 +2, 0022 -7, 0037 +1, 0041 -3, 0050 +1, 0067 +1 | **601** (after 0009, before 0016) | 593 |

So `cuda_follow.zig` is one patch's problem: 0023 alone spends 62 of its 85 lines, and splitting that file is
part of re-seating 0023, not a separate chore. `cuda_lanes.zig` and `cuda_forward.zig` end under the limit but
break it in the middle of the stack, by one line each, because upstream left them at exactly 600: a per-patch
gate run (which is how `scripts/gates.sh` is used on arm trees) fails there even though the final tree passes.
Reordering within each cluster fixes both: put 0008 before 0004 for `cuda_lanes.zig`, and 0016 before 0009 for
`cuda_forward.zig`.

## The five cross-cutting answers

### Q1. Upstream commits in the range that touch GLM decode or prompt speed

From `git log 9c9bf542..v1.2.7 -- zig/src/families/glm zig/kernels/cuda/glm_* zig/kernels/cuda/exl3*` (47
commits, `work/v127drift/q1-glm-files.tsv`) plus `zig/src/cuda` (14) and `zig/kernels` (29). The ones that are
levers rather than review follow-ups:

| sha | date | subject | files | what it does |
|---|---|---|---|---|
| `6d4191a95` | 2026-11-05 | glm cuda: windows to 32 rows, priced by rounds timed at load | 21 | the biggest one: decode windows 8 -> 32 rows, MTP chains 3 -> 15 drafts, load-time timing of real rounds per build/GPU/checkpoint/settings in the new `cuda_lane_costs.zig`, and a race between the classic and factored NVFP4 expert kernels keeping the faster |
| `d7d559944` | 2026-11-07 | a shared round drafts each MTP stream three at most | 5 | caps the above: without it two streams verified 32 rows a round where main verified 8, 19-50% under main on two GB10s |
| `55a95af06` | 2026-11-08 | DFlash2's shared rounds keep main's prices | 2 | `window_costs_lone`; two-stream chat was 12% under main before it |
| `cc2fa8d23` | 2026-11-10 | DFlash2's shared rounds keep the budgets rule | 3 | #2793: four-stream decode 3.7% faster greedy, 3.5% at 0.7, at TP=2 on two GB10s |
| `9347a8a7d` `f3988faa7` `c5d45eee8` `3464a7d44` | 2026-11-08/09 | opt-in message-start prompt cuts | 17+3+6+6 | `TF_GLM_REQUEST_STARTS=1`: a 58.7K chat resumed later turns at 58,735 instead of 57,344 at TP=2 |
| `7547c99c2` `e229a6196` `f34b97085` `7d09470ec` | 2026-11-02..09 | `TF_GLM_KV_LIVE_HALF=1` | 7+ | a kept state drops the dead half of the double-buffered KDA state: 71 MB a rank at TP=2 |
| `16287f6b1` `2c4900374` | 2026-11-06/08 | four-rank RoCE ring relay | 16+ | `TF_TP_ROCE_RELAY=1` relays gathers through both neighbours on a ring with no opposite links, 64 KiB ceiling; `TF_TP_ROCE_RELAY` count 0 at the pin, 22 at the tag |
| `73609402a` | 2026-11-07 | the gather prefill warms its all-gather | 4 | start-up only: removes a send/receive storm that could hang a four-rank ring |
| `eb29a68a5` | 2026-11-10 | `TF_GLM_LAYERS` memory check counts tensors | 7 | a 20-layer thin load counts 66.6 GiB instead of 163.6 GiB |
| `edc16dfe9` `39a25e22b` `3184d127f` | 2026-11-06/08 | exl3 experts: the SwiGLU clamp on silu's output | 5 | adds `tf_exl3_plan_finish_after` and `Layer.after`; GLM's own order is unchanged |
| `c0f8e1c4c` `0924d298d` | 2026-11-08 | the router's K slices on shared mma tiles | 10+3 | refactor; every partial keeps its bytes, prompt and decode at TP=2 unchanged |
| `42735f94f` `b3a68c565` | 2026-11-06/08 | a shared CUDA MLA image | 9+ | refactor; GLM's SASS identical on all five SMs |
| `5b80e93ac` `658f38236` `72abee671` | 2026-11-04/06/08 | share the KDA chain and saved-row replay | 14+ | refactor; the GLM image ABI and arithmetic retained |
| `88267c063` `5d380e4ee` | 2026-11-08/09 | GLM's SwiGLU rows in their own header | 2+ | refactor; same entry names, bounds, arithmetic |
| `72a28dd66` `4a68dfd36` | 2026-11-04 | one core walk for kept prompt states | 4+ | GLM CUDA's snapshot pages move onto `core/state_walk.zig`; same copies, same order |
| `5fdcadcaa` | 2026-11-09 | key persisted prompt states by what they were computed with | - | disk-tier and `--learn-conversations` keys change |
| `d8f95f4ea` `edeae56b3` `4a0e38afd` `949ae97fe` `ca83a689a` | 2026-11-08/09 | kv pool: reclaim hooks, groups sized by bytes a row, budgets after streams | - | the start-up pool plan and its printed line change |
| `e32de56c6` `7b3e2d76a` | 2026-11-09 | qmmf FP4 decode on the shared e2m1 pair decode | - | behind `-Dnative-fp-decode`; the default build's 113 fatbins are byte-identical |
| `2cf13abcf` | 2026-11-09 | skip GLM lane cost caching when its identity exceeds the buffer | - | guard on `6d4191a95`'s cache |
| `5151f19f3` | 2026-11-10 | a prompt chunk sends the tower only images that end after its start | 5 | vision only |

The review follow-ups on `6d4191a95`'s series, which carry no independent lever but do move code:
`63be446c8`, `27e1c0057`, `b38343644`, `577e41c98`, `2b5258b39`, `a093eee12`, `8e758b69f`, `6aaed8bb4`,
`562b333d1`.

**The three we do not have and should want**: `6d4191a95`'s whole package (32-row windows plus load-time
pricing), `cc2fa8d23`'s budgets rule, and `TF_GLM_KV_LIVE_HALF`. The first subsumes a good deal of what our
0023 and `TF_GLM_OVN_COST_TIME` were built for.

### Q2. Did default GLM behaviour change in a way that moves output tokens or the boot pool?

Yes, in four ways, all default-path.

1. **Decode windows and chain depth.** `zig/src/families/glm/cuda_state.zig:21` is
   `pub const window_rows = 8;` at the pin and `pub const window_rows = 32;` at v1.2.7;
   `zig/src/families/glm/cuda_engine.zig:26` is `pub const max_drafts = 3;` and `= 15`. Commit `6d4191a95`.
   CHANGELOG 1.2.7 does not carry a bullet for this one; the commit message does: "Decode windows reach 32
   rows and MTP chains 15 drafts... prices lone windows, drafts and DFlash2's shared rows by them... No GPU
   kernel changes." It also records two faults wider windows exposed: a shared window's KDA projection buffer
   sized only when a stream's rows were under the shared rows ("at 32 rows it shrank to 4 bytes and overwrote
   its neighbours"), and `TF_GLM_KV_HOST`'s row cache forgetting its list past 16 rows. Tokens a round change;
   the replies are verified, so token identity is claimed, but every window-sized buffer at boot is 4x.
2. **Shared-round draft allocation.** `allocate_shared_drafts` went `drafting` -> `drafting and !block`
   (`cc2fa8d23`), and `Model.shared_drafts` caps the MTP head's shared rounds at 3 (`d7d559944`,
   `cuda_lanes.zig:119` `.shared_drafts = if (block) 0 else shared_head_drafts`). CHANGELOG 1.2.7: "shared
   rounds size each stream's drafts by its last grant plus the slack again, trimmed at verify... one stream,
   the MTP head and every reply's tokens are unchanged (#2793, fixes #2720)."
3. **Kept-state identity.** `7547c99c2` and `e229a6196` take the GLM rank fingerprint to layout 20;
   `5fdcadcaa` keys persisted states by what the run computed with. A kept state written by the pin is not
   readable by v1.2.7, so every warm-resume measurement has to be taken on one side or the other.
4. **The boot pool plan.** `edeae56b3` "groups sized by bytes a row, padding reported at load (#2444 C2)",
   `ca83a689a` "scale kept-state budgets after streams are counted", `4a0e38afd`/`949ae97fe` on naming a
   `--prompt-cache-gib`, and `eb29a68a5` for `TF_GLM_LAYERS` loads. The printed start-up line changes.

What did **not** change: `TF_GLM_DENSE_BITS`' default is `16` (bf16) at both refs
(`cuda_ranks.zig:25` both sides); `prefill_rows` stays 2,048; `shared_rows` stays 32 and `max_shared` 16.

### Q3. The test and gate machinery

`scripts/gates.sh` runs seven `zig build` steps plus `zig fmt --check zig/`. At v1.2.7
(`git grep '"<step>"' v1.2.7 -- build.zig zig/build`):

| step | at the pin | at v1.2.7 | where |
|---|---|---|---|
| `check-native-cuda-host` | yes | yes | `zig/build/cuda.zig` |
| `test-cuda-host` | yes | yes | `zig/build/cuda.zig`, `zig/build/flashnext_proposal_host.zig` |
| `compile-cuda-tests` | yes | yes | `zig/build/cuda.zig` |
| `test-glm-ring-host` | yes | yes | `zig/build/glm_family_host.zig`, `zig/build/host_ci.zig` |
| `test-glm-logprobs-host` | yes | yes | `zig/build/glm_contracts.zig`, `zig/build/host_ci.zig` |
| `test-glm-onepass-order-host` | **absent** | **absent** | ours: added by patch 0057 through `zig/build/glm_family_host.zig` |
| `test-rows-host` | yes | yes | `zig/build/rows_host.zig` |

So six of the seven survive by name and the seventh was never upstream's. `zig/build/` gained eight files and
lost none: `cache_index_timing.zig`, `cache_replay.zig`, `env_defaults.zig`, `locate_host.zig`,
`release_paths_dispatch.zig`, `release_paths_walk.zig`, `sessions_writes.zig`, `stream_scan_bench.zig`.
`zig/build/glm_family_host.zig` took seven commits in the range, which is why 0050 and 0057 both conflict
there.

Lean: `tools/zig/lean_check.py` is +44/-2 and gains the two getenv rules quoted under 0001 above, plus a new
`tools/zig/lean_check_test.py`. `tools/zig/lean_new.py` and `tools/pr_check.py` are **byte-identical**
(`git diff 9c9bf542 v1.2.7 --` on each produced 0 lines). The 600-line and one-line-comment rules are
unchanged in substance; what changed is the new finding class, and `docs/environment.md` now carries an
"Existing lenient switches" list that `lean_check.py` parses to exempt named settings.

### Q4. Zig version

Unchanged. `git show 9c9bf542:.zig-version` = `0.17.0`, `git show v1.2.7:.zig-version` = `0.17.0`.

### Q5. PR #2044 (our patch 0044)

**Not in v1.2.7.** Evidence, all against `9c9bf542..v1.2.7` or the tag's tree:

- `git log --grep='2044'` over the range: 0 commits.
- `git log -S` over the range for `decodeItems`, `decode_items`, `ItemPlan`, `exl3_items`, `glm-exl3-items`,
  `fusedScratch`, `fusedBytes`: 0 commits each.
- `git grep -c -F` at `v1.2.7` over `zig/` for the same seven strings: 0 each.
- `zig/src/cuda/exl3_experts.zig` at the tag exposes `plan`, `Scratch`, `scratchBytes`, `scratch`, `Experts`,
  `load`, `unload`, `runSlots`, `run` and nothing resembling an item plan; its only change in the range is
  `edc16dfe9`, +2 lines (`Layer.after`).
- `zig/src/families/glm/cuda_exl3.zig` is 206 lines at both refs with 0 commits in the range.

0044 therefore re-seats unchanged (the survey confirms: clean, 17 hunks, 0 rejects), and the upstream PR is
still open work.

## Recommended order of work for the re-seat

The dependencies are real: five patches sit on `facts()`, seven sit on the prompt-cut machinery, four sit on
the KDA chain, and four files are over the lean limit before any of them lands.

**Stage 0 - decisions that cost nothing to take now.**

1. De-duplicate `0043` and `0044` (identical files in `patches/engine/` and `work/final/`).
2. Drop, with the evidence above: **0030** (absorbed), **0036** (absorbed), **0034** (contradicted: its
   arity never existed upstream). Each is a repair of our own port, not of upstream.
3. Decide **0018 / 0027**: upstream's `drafting and !block` is our knob's behaviour for the drafter case.
   Recommended: retire both and keep only a knob for the MTP-head half if a measurement still wants it.

**Stage 1 - the structural work, before any conflicted patch.** Nothing else can be measured until these are
settled, and three of them are splits upstream itself had to do.

4. Split `cuda_follow.zig` (projected 618), `cuda_native.zig` (617), `tokenizer.zig` (615) and
   `zig/tests/cuda/main.zig` (606) so the series fits under 600. `cuda_lanes.zig` and `cuda_forward.zig` are
   at exactly 600 upstream and have no room for even one added line.
5. Re-home the OVN knob registry (0001, 0002) onto `platform/environment.zig`'s `.glm` scope and
   `core/profile.zig`, or the lean gate fails on the first commit. Everything from 0003 on reads
   `cuda.ovn.*`, so this is the true root of the stack.

**Stage 2 - the two rewrites, each of which unblocks a cluster.**

6. **Prompt cuts.** Re-express **0007** on `cuda_prompt_cuts.zig`: feed prompt-cache marks into the same
   `cuts` list, keep `prefillChunk` at seven arguments, keep `Kept.below`. Then **0047**, **0048**, **0049**
   fall out as small edits to upstream's lines, and **0045** is re-decided (upstream refuses pairing whenever
   cuts exist, which costs us the 1.6-2.6% pairing win; if we want it back it is a new, measured change, not
   a re-seat). **0042** stays as is. Dependents that must wait: 0011, 0050, 0046, 0063, 0068.
7. **Lanes and costs.** Re-express **0023** against `cuda_lane_costs.zig` / `cuda_lane_cost_measure.zig`
   rather than carrying `cuda_cost_time.zig` beside them, then re-write **0012**, **0015**, **0026** into the
   new `facts()` literal, and re-check **0024** and **0028** (their targets were rewritten by `cc2fa8d23`).

**Stage 3 - the moved code.**

8. **KDA**: 0003, 0019, 0037, 0040 against `zig/src/cuda/kda.zig` and `common/kda.cuh`; our `cuda_kda.zig`
   has no upstream counterpart any more.
9. **Glue headers**: 0020, 0022 against `glm_swiglu.cuh` and the shrunken `glm_glue_bmm.cuh`; 0038 needs a
   new host entry or retirement.
10. **MLA**: 0051 against `common/mla.cuh`; re-read 0021's OVN headers against the same file.

**Stage 4 - the independents, in any order.** These apply as text today and need only their gates:
0005, 0010, 0013, 0029, 0031, 0032, 0033, 0035, 0039, 0044, 0052, 0053, 0054, 0058, 0059, 0060, 0061, 0062,
0066, 0067, 0068. Two notes: 0032 must not mark its four rows `.native_fp` (a new upstream test asserts
exactly three such units), and 0061 becomes more load-bearing now that `window_rows` is 32.

**Stage 5 - the core and server tails, which are independent of the GLM work**: 0006 and 0055 against the
rewritten `prompt_cache.zig`; 0064 against the reworked `memo.zig`; 0065 and 0066 against `server/root.zig`;
0025 against `native/cuda.zig`. 0041 should be regenerated, not re-applied: it restores pin lines, and the
pin's lines are not v1.2.7's. 0043 likewise is recomputed from whatever comments the re-seated stack adds.

**Last**: re-cut 0024 (our own test repairs) and re-run `scripts/lean.sh` base against head with each side's
own `lean_check.py`, since the rule set changed.

## Nothing left undetermined

Every item that was open during the work is now closed, each in the section that owns it. The last one, the
survey cell, is resolved here because its answer is about the instrument rather than about upstream.

**The `0066` cell was my harness, and the repo's `clean` is right.** My re-run scored
`0066-render-once-host-once` as `partial`; `work/v127/survey.tsv` says `clean`. The apply logs
(`work/v127drift/rej/*.log`) name the cause outright. `0065`'s log ends:

```
Applying patch zig/src/server/root.zig with 1 reject...
error: failed to write to 'zig/tests/server/prompt_bench.zig': No space left on device
```

so `zig/tests/server/prompt_bench.zig`, which `0065` CREATES, was never written in my tree. `0066` edits that
same file, and its log then shows five `patch failed: zig/tests/server/prompt_bench.zig:` lines (at 78, 94,
152, 181, 197) before dying the same way on `zig/src/core/tokenizer/tokenizer.zig`. `git apply --check`
therefore failed on a file the previous patch had been unable to create, which is why the verdict read
`partial`, and the rejected hunks were not counted because copying their `.rej` files failed with the same
I/O error. Cross-checked the other way: no two patches in the series create the same path
(`awk` over every `new file mode` line), so there is no real collision; the only duplicate creation is
`zig/tests/cuda/glm_exl3_items_tests.zig` from the two byte-identical copies of `0044`, which is the
de-duplication point in Stage 0.

Conclusion: `0066` re-seats clean on v1.2.7, as the repo's survey says, and my re-run agrees on all 68 cells
once the disk-full run is discounted. No re-run is needed.

Two reject details worth carrying into the re-seat, read from the same logs:

- **0064**'s two rejects are `zig/build/cuda.zig:340` (the host-test registration block) and
  `zig/src/core/tokenizer/memo.zig:5`, and the second is exactly the constant upstream changed:
  our patch expects `pub const min_bytes = 1024;`, which `a56c63daf` ("keep segments of 64 bytes or more,
  not 1,024") replaced. Hunks 2 and 3 of that file applied at offsets +3 and +2.
- **0065**'s two rejects are `build.zig:245` (the step list, where upstream added `checkpoint_config.zig`
  and the new `zig/build/*.zig` steps) and `zig/src/server/root.zig:15` (the `pub const` and `test` block,
  18 commits in the range). Its `zig/build/server.zig` hunk applied at offset +4.

The remaining first-pass items are answered in the sections above:

- **Whether 0021's OVN headers still mirror a live body**: they do not. `glm_glue_attn.cuh` went 356 -> 150
  lines, `namespace glm_attn` moved whole into `common/mla.cuh`, and `chunks_wide` gained `RW`, `SPLIT`, `sw`
  and `sr` plus two `static_assert`s; `wide_smem` gained `RW`. Both defaults keep our copy compiling and stop
  it being faithful. Detail in the 0021/0051 section.

- **Per-patch line attribution** for the four tight files: measured with `git apply --numstat`, in "Lean
  limits". `cuda_follow.zig`'s overrun is 0023's alone (+62 of +85); `cuda_lanes.zig` and `cuda_forward.zig`
  each break the limit by one line mid-stack and end under it.
- **0038's reachability**: the `router16` field, its loader and its launch branch are ours, in
  `cuda_glue.zig` (lines 55, 112, 125-126, 253 of `work/final/tree`'s copy). Upstream dropped
  `Kernels.router_part`, turned the unaligned branch into `error.RowShape` and added
  `.shared = router_tile_smem` to the tile launch, so the branch has to be re-placed but is not refused by
  anything: `:170`'s check is about pointer and stride alignment, not the row count.
- **`request_min_chunk` and mark-driven cuts**: it does not constrain them.
  `zig/src/native/cuda_snaps.zig:34-38` makes `requestMinimum` the spacing the SERVER thins message starts to
  before sending them (`zig/src/native/cuda.zig:452` `.prefill_min_chunk = snaps.requestMinimum(F)`), and
  `cuda_native.zig:33` declares GLM's 256. `cuda_prompt_cuts.zig` itself takes any ascending list: its own
  test at line 110 uses `const cuts = [_]u32{ 1, 2, 1000, 1001, 1003 }; // closer than GLM's
  request_min_chunk asks for: the cuts still hold`. So feeding prompt-cache marks straight into `e.cur.cuts`
  is not blocked by the 256.
