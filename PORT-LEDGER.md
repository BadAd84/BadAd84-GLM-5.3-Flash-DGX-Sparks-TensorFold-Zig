# PORT-LEDGER.md - engine patches ported from ai-engine into this recipe

Current state only. The applied stack is `patches/engine/0001` .. `0023`, applied in
order onto the pin in `scripts/config.sh` (9c9bf542cc87ec21f44cee720fc4f1c056f8c905).
Every landed patch was proven by a fresh application in order onto a clean pin
checkout, with these gates: `zig build check-native-cuda-host`, whole-tree
`zig fmt --check zig/`, `lean_new.py` base-vs-head (0 new), and fatbins for any
patch touching `.cu`.

## Landed

| patch | knob / change | source commit | gates |
|---|---|---|---|
| 0001 | TF_GLM_OVN knob registry (`cuda/ovn.zig`, root.zig) | c60ce5fd1 | compile, fmt, lean |
| 0002 | every knob its own cache statics | 32989e34f | compile, fmt, lean |
| 0003 | TF_GLM_KDA_PAD at one width (nine-commit series squashed) | 917575463..e796315f3 | compile, fmt, lean |
| 0004 | DFlash2 TF_GLM_OVN_DRAFT_* knobs (onepass, down4, mlpsplit, edge, noisy, noise, keepwin, cuts) | 39304587f, 0f4b0ed85 | compile, fmt, lean, fatbins |
| 0005 | TF_GLM_INDEX_CUDA / _INDEX_DECODE_FROM (decode windows through the index kernels) | ab3009315, 868689925 | compile, fmt, lean |
| 0006 | TF_GLM_OVN_KEPT_WALK (kept-state walks gated by the last id, one prefix helper) | e9bc5dc54 | compile, fmt, lean, test-lane-api-host |
| 0007 | prompt states keep and resume at any row (snap grid removed) | f53c4ded2 | compile, fmt, lean, test-lane-api-host |
| 0008 | TF_GLM_OVN_REPLY_PREFILL (capped, yielding background prefill) + cuda_kda_chunk | 4c877aac0 | compile, fmt, lean, test-lane-api-host |
| 0009 | TF_GLM_OVN_DECODE_INDEX, _INDEX_SCHED, _POOLS32 | 94b93e567 | compile, fmt, lean, fatbins |
| 0010 | TF_GLM_OVN_INDEX_REGROUP (reduce-scatter head sum) | 5da368af1 | compile, fmt, lean, fatbins |
| 0011 | TF_GLM_OVN_ONE_CHUNK (marks kept from inside a prompt chunk) | 083da32bb, 7d01784c3 | compile, fmt, lean, test-lane-api-host |
| 0012 | TF_GLM_OVN_PLAIN_MARGIN (the draft-over-plain margin) | 59604d959 | compile, fmt, lean, test-lane-api-host |
| 0013 | TF_GLM_OVN_EXCHANGE_KB (a direct exchange posted in pieces) | 35b9011e0 | compile, fmt, lean, test-lane-api-host |
| 0014 | TF_GLM_OVN_ROUTER_WARM (router kernels warmed at boot) | e3492ca82 | compile, fmt, lean, test-lane-api-host |
| 0015 | TF_GLM_OVN_WIN_FREE (shared rounds fill with no cost model) | a55671a7c | compile, fmt, lean, test-lane-api-host |
| 0016 | TF_GLM_OVN_SPARSE_ONEPASS (production prompt sparse attention) | f2ffea045 | compile, fmt, lean, test-lane-api-host, fatbins |
| 0017 | TF_GLM_OVN_ONEPASS_PIPE (one-pass pipeline, bit-exact switches) | a63e56649 | compile, fmt, lean, test-lane-api-host, fatbins |
| 0018 | TF_GLM_OVN_SHARED_DRAFTS (shared rounds on the core allocator) | 7b41f0d26 | compile, fmt, lean, test-lane-api-host |
| 0019 | TF_GLM_OVN_KDA_CHUNKED (production chunked KDA prompt kernel) | f2e093ca9 | compile, fmt, lean, test-lane-api-host, fatbins |
| 0020 | TF_GLM_OVN_MM_WIDE / _SWIGLU_REDUCE / _MM_CLUSTER / _MM_DECTILE (bf16 matmul) | cbf94fde5 | compile, fmt, lean, test-lane-api-host, fatbins |
| 0021 | TF_GLM_OVN_MLA_FUSEMERGE / _ABSORB_VEC / _KVB8 (MLA attention) | 436970264 | compile, fmt, lean, test-lane-api-host, fatbins |
| 0022 | TF_GLM_OVN_GLUE_FUSE / _GLUE_ROW / _PDL_EARLY (glue fuse) | 3423859e7 | compile, fmt, lean, test-lane-api-host, fatbins |
| 0023 | the shared-round era: prof, draw1, cost_time, fills, segments, disk tier | 32060d706 | compile, fmt, lean, test-lane-api-host, fatbins |

## Parked - blocked on a structural port, not a knob

Each of these was attempted on the 0001..0010 stack and reset clean. The evidence
is the same in every case: the source commit edits files whose pin versions are a
different era at the same sites, so applying it means re-authoring that era rather
than grafting a knob.

| source | why parked |
|---|---|
| 1a89c3e82 PK8 (pooled keys as production kv8 rows) | touches cuda_disk_image, cuda_dsa_seg, cuda_index_shard, native/cuda_glm_disk: none exist at the pin. Its cuda_state hunk conflicts. |
| 08330f951 DISK_BCAST / _DISK_PUMP / _SNAP_GATHER / _DROP_MTP | needs cuda_disk_image.zig and cuda_disk_ranks.zig (absent at the pin); rows_store/rows_write hunks conflict. |
| 3cceb587d PEER_FIRST / _FRONTS / _SIDE_PRIO | needs cuda_forward_fronts.zig / cuda_forward_pieces.zig and rewrites cuda_forward's peer paths. |
| c920d6e5a ROCE_RAILS / _LINK1 / _ROCE_ILP / _ROCE_CPU | needs cuda/roce_rails.zig and rewrites roce.zig's rail setup. |
| e95d31f81 ITEMS (16-pair item plan) | needs kernels/cuda/exl3_ovn.cuh and rewrites exl3_experts' dispatch. |

| PRX / fill-slice family, SEG_KDA/SEG_DSA, KDA_PIECES | sit on 32060d706's module layout: prompt_pieces, lanes_fill, lanes_shared, slices, and the Buffers.seg tables (cuda_kda_seg, cuda_dsa_seg, cuda_commit_seg), none of which the pin has. Porting that era is a project with its own A/B, not a patch. |

## Gate correction: test-cuda-host is the gate for family patches (measured 2026-11-09)

The gate column above is wrong for every family patch. `check-native-cuda-host` and
`test-lane-api-host` do not compile the GLM family's host tests, so a landed patch can
be green in those columns and still break `zig build test-cuda-host` - the step the pin
itself passes (rc=0 on a clean 9c9bf542 checkout).

Measured on pin+0001..0023: 9 failing test binaries, 27 named test failures the pin
does not have. Patch 0024 repairs most of them; measured on pin+0001..0024: 7 binaries,
11 named failures. The pin itself passes test-cuda-host (rc=0) on a clean 9c9bf542
checkout, and `glm_snapshot_host.zig` / `copy_drafts_cuda_test.zig` are both in its
gate, so these are regressions of the ports, not pre-existing upstream red. The classes, each a real defect in the landed set:

- 0001: the registry has no `fake`, so every knob test that drives a knob fails.
- 0003: `tileLinears` lost its `padKdaInputs` call in the port (the pad never ran), and
  the staged `cuda.memory.download` was replaced by a raw `cuMemcpyDtoH_v2` (an
  unstaged read on the default path).
- 0004: `windowBytes` dereferenced `e.drafter` before reading the KEEPWIN knob, so a
  host-test engine with an undefined field segfaulted.
- 0007: `snap_grid` was removed while three host adapters still re-export or expect it
  (`glm_image_cache_host.zig`, `glm_pages_host.zig`, `cuda_pages_test.zig`).
- 0014: the warm-serve test called `Host.serve` with the comptime family as an argument.
- 0015/0018: their own test files assert `config.Config.shared_depth_full` and
  `shared_copy_width`, which the port deliberately left out (unported levers).
- 0022: `prefillStep` moved to `cuda_lanes_step.zig` and its `Lanes` shim was missing.

Patch 0024 landed those repairs as one corrective patch with the owning patch named
per hunk. Still open after it (11 named failures): `copy_drafts_cuda_test` (2),
`cuda_lanes_test`'s knob assertions (3: DEPTH_FULL/SHARED_COPY, SHARED_DRAFTS,
WIN_FREE), `cuda_kv8_test`, `cuda_mla_ovn_test`, `cuda_onepass`, `cuda_zero_budget`,
`draft_sources_cuda_test`, `glm_snapshot_host`'s TF_KV_SHARE adapter test, and the
warm-serve plumbing test (0014's `warmQuiet` never reaches the host: the pin's
`cuda_startup_phase.serve` hardcodes the Nemotron constant, so TF_GLM_OVN_REPLY_PREFILL's
wait is inert in production until that wiring is carried through).

## What this means

The landed patches cover the knobs that plug into the pin's own structures, including
ONE_CHUNK, which turned out to be additive: its two modules import only modules the pin
already has, and the wiring is a field plus two hooks. What remains parked is the set
that genuinely needs the 32060d706 module layout (prompt_pieces, lanes_fill,
lanes_shared, slices, seg_kda, draw1, cost_time): those commits edit the pin's core at
sites where the pin took a different path (L2PF prefetch, mtp_confidence, templated
glm_top1), so each is a structural port with its own A/B, not a knob graft.

The production serve (spark1-3, glm53-flash-tf) still runs the Python TensorFold
stack with the full OTS patch set; nothing here changes it.
