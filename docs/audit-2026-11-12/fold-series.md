# fold-series.md - the 68-patch series folded into 35 coherent levers (2026-11-12)

What this is: the engine series as it stands (`patches/engine/0001..0044` plus `work/final/0045..0068`, 68 patches, base `9c9bf542cc87ec21f44cee720fc4f1c056f8c905`) read patch by patch, classified, and re-cut so that every patch is one lever that is correct on its own. The folded series is `work/fold/0001..0035-*.patch`; the per-hunk map is `work/fold/MAP.tsv` (359 rows) and the per-patch table is `work/fold/SERIES.md`. No commit was made in any clone; everything below is index and tree objects.

The series moved under this lane while it ran: another lane committed `0043-lean-comments.patch` and `0044-exl3-decode-items.patch` into `patches/engine/` from `work/final/`. The two copies are byte-identical (`cmp`), so the series is still the same 68 patches; the tooling de-duplicates by file name.

## 1. What came out

| | old | new |
|---|---|---|
| patches | 68 | 35 |
| hunks | 714 | 618 |
| added lines | 13,481 | 13,149 |
| removed lines | 1,403 | 1,104 |

The 96 hunks, 332 added and 299 removed lines that disappear are pure accretion: a line written by one patch and rewritten by a later one, both of which now land in the same patch. The clearest case is the KDA-pad lever: patch 0003 replaced `prompt_pair.wanted(o.settings.pair, o.settings.solo, world)` with `..., false, ...` and patch 0041 put it back, so the folded `0006-kda-pad-one-width.patch` does not touch `zig/src/families/glm/cuda_engine.zig` at all.

## 2. Classification of all 68

Class (a) a lever, (b) a repair of an earlier series patch, (c) a repair of the pin itself, (d) tests or tools only. The full per-file, per-hunk assignment with one reason a line is `work/fold/MAP.tsv`.

### (a) levers, 30 of them

| old | lever | new patch |
|---|---|---|
| 0001 | the TF_GLM_OVN knob registry (infrastructure) | 0005 |
| 0003 | TF_GLM_KDA_PAD | 0006 |
| 0004 | the DFlash2 draft knobs | 0007 |
| 0005 | TF_GLM_INDEX_CUDA decode windows | 0008 |
| 0006 | kept-state walks on one prefix helper | 0009 |
| 0007 | prompt states keep and resume at any row | 0010 |
| 0008 | TF_GLM_OVN_REPLY_PREFILL | 0012 |
| 0009 | DECODE_INDEX, INDEX_SCHED, POOLS32 | 0013 |
| 0010 | INDEX_REGROUP | 0014 |
| 0011 | ONE_CHUNK (the module) | 0015 |
| 0012 | PLAIN_MARGIN | 0016 |
| 0013 | EXCHANGE_KB | 0017 |
| 0014 | ROUTER_WARM | 0018 |
| 0015 | WIN_FREE | 0019 |
| 0016 | SPARSE_ONEPASS | 0020 |
| 0017 | ONEPASS_PIPE | 0021 |
| 0018 | SHARED_DRAFTS | 0022 |
| 0019 | KDA_CHUNKED | 0023 |
| 0020 | MM_WIDE, SWIGLU_REDUCE, MM_CLUSTER, MM_DECTILE (and ROUTER16, see F10) | 0024 |
| 0021 | MLA_FUSEMERGE, ABSORB_VEC, KVB8 | 0025 |
| 0022 | GLUE_FUSE, GLUE_ROW, PDL_EARLY | 0026 |
| 0023 | the shared-round era | 0027 |
| 0031 | the head-block rule (the source tree's, not the pin's) | 0029 |
| 0044 | the EXL3 16-pair decode item plan (upstream PR #2044) | 0011 |
| 0046 | the MTP head absorbs nothing with a drafter loaded | 0030 |
| 0051 | FP8 latent keys fetched a tile ahead | 0031 |
| 0052 | the EXL3 prompt experts take a whole chunk | 0032 |
| 0053 | TF_EXL3_DEC_ORDER | 0033 |
| 0064 | memo.equal by indexOfDiff, access.strIndex | 0034 |
| 0066 | render and tokenize a request once, TF_GLM_OVN_HOST_ONCE | 0035 |

0031 is a lever, not a repair: `docs/PATCH-AUDIT.md` records that the head-block rule it installs is the source tree's and not the pin's (at TP=3's 21 or 22 heads a launch of 5 to 63 rows takes the 32-head tile where the pin takes the 16-head one), and it is not gated.

### (b) repairs of an earlier series patch, 34 of them

| old | repairs | folded into |
|---|---|---|
| 0002 | 0001 (the registry's cache key) | 0005 |
| 0024 | 0001, 0003, 0004, 0007, 0008, 0015, 0018 (split seven ways, by file and once by hunk) | 0005, 0006, 0007, 0010, 0012, 0019, 0022 |
| 0025 | 0008 (its header says 0014; see F2) | 0012 |
| 0026 | 0023 (the facts() rewrite dropped three knob reads 0012, 0015 and 0018 had wired) | 0027 |
| 0027 | 0018 and 0023 (split: the gating line to the era, the tests to shared-drafts) | 0022, 0027 |
| 0028 | 0007, 0017, 0018 (split three ways) | 0010, 0021, 0022 |
| 0029 | 0016 (the duplicated sparse launches) | 0021 |
| 0030 | 0023 (facts() lost draft_confidence) | 0027 |
| 0032 | 0016, 0017, 0019 (the catalog hunk split by line, glm_l2pf.cu to 0019) | 0020, 0021, 0023 |
| 0033 | 0004 (its own test shadowed a capture) | 0007 |
| 0034 | 0007 (prefillChunk's rows argument) | 0010 |
| 0035 | 0023 (it renamed the top1 template away) | 0027 |
| 0036 | 0007 (the chunk step's start and length) | 0010 |
| 0037 | 0019 (the dropped kda_block.fill) | 0026 |
| 0038 | 0022 (its graft deleted the router16 kernel 0020 added) | 0026 |
| 0039 | 0021 (its loop rewrite dropped the @FieldType guard 0020 had) | 0025 |
| 0040 | 0003 and 0024 | 0006 |
| 0041 | 0003, 0004, 0006, 0007, 0008, 0016, 0017, 0021, 0022, 0023 (split ten ways) | 0006, 0007, 0009, 0010, 0012, 0020, 0021, 0025, 0026, 0027 |
| 0042 | 0007 (ringsAgree and State.ready left in the pin's form) | 0010 |
| 0043 | 0032, 0038, 0042 (split three ways) | 0023, 0026, 0010 |
| 0045 | 0007 and 0042 | 0010 |
| 0047 | 0008 (its prefillFn) and 0007 | 0012 |
| 0048 | 0007 (the grid removal made canBatch unsafe) | 0010 |
| 0049 | 0023 (the follow loop's exclusion list) | 0027 |
| 0050 | 0011 (the whole wiring) | 0028, as its own patch (J2) |
| 0055 | 0008 and 0025 | 0012 |
| 0056 | 0008, 0009, 0010 (split three ways, including a hand-built three-step file) | 0012, 0013, 0014 |
| 0057 | 0017 (split: the kernel fix and reset check with it, the base check held back, J15) | 0021, 0025 |
| 0058 | 0004 (the selector kept the pin's form) | 0007 |
| 0059 | 0004 (the kernel came without its contract record) | 0007 |
| 0060 | 0042 (the refusal had no unit test) | 0010 |
| 0063 | 0042 (the snapshot side had no case) | 0010 |
| 0067 | 0022 (post kept the pin's signature) | 0026 |
| 0068 | 0023 (the MULTI_FILL path never took resumeDrafter) | 0027 |

### (c) repairs of the pin itself, 3, each an upstream candidate

| old | what | new patch |
|---|---|---|
| 0054 | a logit gather posts one NCCL broadcast a row a rank; at three ranks a prompt-logprobs pass past about 100 rows never leaves ncclGroupEnd. Its header states the three source files are byte-identical to the pin before it | 0001 |
| 0061 | the shared-window check sizes its buffers from a literal 4 where the engine's ceiling is forward.window_rows | 0002 |
| 0062 | the disk grid round trip never covered the I/O worker, and nothing proved quiesce waits | 0003 |

### (d) tests or tools of the pin, 1

| old | what | new patch |
|---|---|---|
| 0065 | the prompt-bench step, the instrument 0066 was measured with | 0004 |

The other test-only patches are not in this class because each tests one of our levers, and class (d)'s rule is to attach those to the lever they test. Where each went: 0060 (the error.PastRing unit test) and 0063 (a kept state past the index rings) to 0010; 0033 (the DOWN4 check's shadowed capture) to 0007; 0034 (glm_tap_tests' arity) to 0010; 0056 (the three GPU checks) split to 0012, 0013 and 0014; 0028 (three pin tests adapted to our semantics) split to 0010, 0021 and 0022.

## 3. The new series

`work/fold/SERIES.md` has the full table (number, name, class, the knobs each patch is the first to read, the old patches folded in, and what measurement exists with its doc). The shape:

- 0001 to 0004: the pin's own defects and gates, so they apply to a pristine `9c9bf542` and can be taken upstream without any of our levers.
- 0005 to 0035: our levers in dependency order, each with its repairs folded in and its tests behind it.
- 0028 `one-chunk-wiring` is the one class (b) patch that could not be folded (J2).

Every knob still defaults off. 1,159 KB of patch text in 35 files.

## 4. The equality proof

Three runs, all from one `--shared` clone of `work/parity/tree` at `work/fold/scratch`. `work/parity/tree` was never written to and nothing was ever checked out anywhere.

1. The old series rebuilt, to have its intermediate trees: `python3 work/fold/build_old.py` applies the 68 patches in order to the pin's tree in a scratch index with `git apply --cached`. All 68 applied plainly, none needed `--3way` (`grep -c 3way work/fold/rebuild.log` -> 0), and the last tree is `582f1c62d6107fb1f5917a332de73cb7b541ae95`.

2. `python3 work/fold/cmp_final.py 582f1c62d6107fb1f5917a332de73cb7b541ae95` hashes `work/final/tree`'s working tree into a tree object through the scratch clone's object store (`git --work-tree=... add -A` into my own index file, after `read-tree` of the pin so the pin's tracked `*.log` files are not skipped by `.gitignore`):

```
work/final/tree hashed  : 582f1c62d6107fb1f5917a332de73cb7b541ae95
tree under test         : 582f1c62d6107fb1f5917a332de73cb7b541ae95
differing paths         : 0
```

   That is the CRLF-safe comparison: both sides are git blob ids, never raw bytes on `/mnt/c`. `work/final/tree`'s own `core.autocrlf` is `false` and its files are LF on disk.

3. `python3 work/fold/verify.py` applies the 35 folded patches, in file-name order, to a fresh index seeded from the pin's tree, each preceded by a plain `git apply --cached --check` (no `-C`, no `--3way`, no fuzz), then hashes `work/final/tree` again and diffs. `work/fold/verify.log`:

```
pin tree                 3066649baaa6a47d869a54b5cc4ef13d2165f5a3
apply --check ok, applied  0001-logit-gather-blocks.patch     -> 1bd2fd759b7651e8e2e40675b7b5df13d4fec531
apply --check ok, applied  0002-shared-window-width.patch     -> 8735940aacf5bed5fc7bad2051cec409f8ae3e94
... 35 lines, one a patch ...
apply --check ok, applied  0035-render-once-host-once.patch   -> 582f1c62d6107fb1f5917a332de73cb7b541ae95

work/final/tree hashed   582f1c62d6107fb1f5917a332de73cb7b541ae95
folded series tree       582f1c62d6107fb1f5917a332de73cb7b541ae95
differing paths          0
failures                 0
```

   `grep -c "apply --check ok" work/fold/verify.log` -> 35.

Two self-checks inside `build_new.py` (`work/fold/build_new.log`):

- **claim gaps: 0** - every one of the 68 old patches' (file, hunk) groups is claimed by exactly one folded patch. A dropped or twice-claimed hunk fails this.
- **no deferrals** - every hunk group landed in the folded patch the plan names for it, so nothing sits in a patch chosen by the tooling rather than by the classification.

The patch files carry full blob ids in their `index` lines (`git diff-tree -p --full-index`), which the next step's `git apply --3way` onto v1.2.7 needs.

## 5. Judgement calls

- **J1. ROUTER16 stays inside the mm-knobs lever.** Patch 0020's subject names four knobs and its diff adds a fifth, TF_GLM_OVN_ROUTER16: the kernel (`glm_glue_bmm.cuh`, one hunk), the `router16: ?cuda.Function` field with its guarded loader, and the launch in `router()` (two hunks in `cuda_glue.zig`). Those hunks separate cleanly and could have become their own lever. They did not, because 0022 deletes the kernel and the launch and 0041 moves the whole OVN field block, so an extracted ROUTER16 lever placed after 0022 would need 0041's field-move hunk split by line around a struct member that is not there yet. Cost: ROUTER16 still spans three folded patches (0024 knob, 0025 loader guard, 0026 kernel and launch), though it is never broken at any prefix, which it was in the old series.
- **J2. 0050 stays its own patch rather than folding into the ONE_CHUNK lever.** It is the wiring that makes the knob switchable, so it belongs with 0011, but three of its hunks edit `cuda_engine_ovn.zig`, a file 0023 creates, and its `cuda_follow.chunkOf` hunks sit on the form 0036, 0041, 0045, 0047 and 0049 give that function. Moving the whole ONE_CHUNK lever after 0023 was tried and abandoned: 0011 removes `pub const row_step = 128` from `cuda_forward.zig`'s `ranges`, and 0016 moves `ranges` into `cuda_forward_pair.zig`, so after 0016 there is no text for 0011's hunk.
- **J3. 0029 folds into onepass-pipe, not sparse-onepass.** Its hunks' context is the DSA block as 0017 leaves it. Its defect is 0016's and the map says so; the tree carries the double launch for one patch.
- **J4. 0037 folds into glue-fuse, not kda-chunked.** The line it restores sits beside `f.l2pfFor()`, which `trace_line.py` shows first appears at step 22. Its defect is 0019's.
- **J5. 0041's `cuda_follow.chunkOf` hunk folds into reply-prefill.** The line it edits reads `a_end`, which is `capEnd(...)` from 0008.
- **J6. 0041's `snapGridNow`/`snap_tail` hunk folds into reply-prefill.** `snapGrid()` lives in `cuda_kda_chunk.zig`, which 0008 creates.
- **J7. 0041's KVB8 term folds into glue-fuse.** `cuda_glue.zig` carries two identical `read`/`wanted` pairs; the term belongs on the one inside `Kernels`, which 0022 adds (F9). This is the one place the tooling seated a hunk wrongly: `git apply` matched the first of two identical regions, the final tree came out one hunk different, and the fix is an explicit edit asserting there are exactly two copies and taking the second.
- **J8. 0041's L2-prefetch fork reorder folds into kda-chunked, not kda-pad.** It repairs 0003 (`trace_line` shows the fork moving above `project` at step 3), but 0019's three `cuda_kda_block.zig` hunks are written against the moved form.
- **J9. 0068 folds into the shared-round era, not draft-knobs.** It repairs DRAFT_KEEPWIN (0004) on the MULTI_FILL path, but the line is in `cuda_prompt_pieces.zig`, which 0023 creates.
- **J10. 0053 is a lever, not a repair of 0019** (its header's claim is false, F7).
- **J11. 0065 (prompt-bench) stays its own patch in front of 0066.** Folding the instrument into the lever it measures makes the before tree unmeasurable, which is how 0066's own numbers were taken.
- **J12. 0056 is split three ways and one file is built in three steps.** `zig/tests/cuda/glm_ovn_checks.zig` holds all three checks and is new; folding it to one lever leaves the other two shipping an unregistered, uncompiled check, which is the defect 0056 fixes. It is created at 0012 with the reply-prefill command only and extended at 0013 and 0014. Every line is 0056's; the only non-verbatim text is the first line of the two intermediate versions, where the doc comment names the commands the file actually has. Step 3 is byte-identical to 0056's file.
- **J13. 0032's catalog hunk is split by line.** Its one hunk adds four entries belonging to three levers; each is inserted after a named anchor so the final order is `glm_kda`, `glm_kda_chunk`, `glm_l2pf`, `glm_onepass`, `glm_onepass_pipe`. A lever that adds a `.cu` and its embed without a catalog entry cannot build an image (0032's header quotes the error).
- **J14. 0003's three DFlash2 lines move to the draft-knobs lever** (F1). A move the fold makes rather than preserves: the alternative is a prefix that cannot compile.
- **J15. 0057 is split.** The kernel fix and the reset test ride with onepass-pipe; `glm_onepass_exact_check.zig` calls `glue.Kernels.loadOvn`, which 0021 adds, so it rides with mla-knobs.
- **J16. The pin's own repairs go first** (0054, 0061, 0062, 0065 as 0001 to 0004), so they can be cut for upstream without re-seating anything.
- **J17. 0027 is split by file**: the `cuda_lanes.zig` gating line corrects 0026's line and goes to the era patch; its test edits go with the SHARED_DRAFTS lever whose test block they trim.
- **J18. 0044 is placed before reply-prefill**: 0056's `main.zig` registration sits on top of 0044's dispatch line, and 0044 needs only 0004's and 0007's lines in that file.
- **J19. 0047 and 0048 are separated**: 0048 reads only 0007's code, 0047 rewrites 0008's `prefillFn`.
- **J20. SERIES.md's knob column names the patch that first reads a switch, not the one that acts on it.** Four switches in the 0021 row (DECODE_SHARD, LATENT_MMA, PK8, SEG_PASS) belong to levers never ported; 0017 brought `cuda_glue.Mla` whole and reads them (F9).

## 6. Can each prefix compile

`python3 work/fold/prefix_symbols.py` walks the 35 trees: for each patch it takes every added line, finds identifiers only a LATER patch defines, then asks the tree after this patch whether anything defines them (`git grep -E "(fn|const|var)[ \t]+<name>"` over the tree object); separately it resolves every `@import("x.zig")` an added line makes. Output: `work/fold/prefix_symbols.log`.

Before the fold's last two moves (J14, J15) the walk found three real forward references. After them:

| patch | flagged | verdict |
|---|---|---|
| 0005, 0007 | `knob` | false positive: a word in doc comments and test names |
| 0006 | `compares` | false positive: a word in a comment |
| 0007 | `onepass` | false positive: a field of `dflash_ovn.Knobs`, declared in the same patch |
| 0010, 0012 | `differed` | false positive: a word inside a `check.pass` string |
| 0012, 0023 | `b_off` | false positive: a field of the pin's `row_projection` (`zig/src/core/row_projection.zig:31`) and a C parameter name in `glm_kda_chunk.cu` |
| 0012 | `glm_kda_chunk` | REAL but unreachable, below |

The only true forward reference left is `cuda.kernels.glm_kda_chunk`, inside `zig/src/families/glm/cuda_kda_chunk.zig:57`, the module patch 0008 ships. The constant is added to `zig/src/cuda/kernels.zig` by patch 0019 = folded patch 0023:

```
git grep -c glm_kda_chunk <tree@0012> -- zig/src/cuda/kernels.zig   -> 0 hits
git grep -c glm_kda_chunk <tree@0023> -- zig/src/cuda/kernels.zig   -> 1 hit
```

It cannot be moved: patch 0008's reply-prefill row validation reads that module's `sub_rows`, so the module must exist at 0012, while the constant it names is the fatbin of a `.cu` that only arrives with the kda-chunked lever. The tree still compiles, with a mechanism rather than a hope: nothing in the tree at 0012 references `kda_chunk.open`, `kda_chunk.Kernel` or `kda_chunk.prompt` (`git grep -E "kda_chunk\.(open|Kernel|prompt)\(" <tree@0012> -- zig/` returns nothing), and Zig analyses a `pub fn` only where it is referenced. The honest fix is F12.

Every other prefix is free of forward references. Nothing here was built: no `zig build` was run.

## 7. What the old series got wrong, found while reading it

- **F1. Patch 0003 (TF_GLM_KDA_PAD) ships three lines of patch 0004's work, so the stack at 0003 cannot compile.** `cuda.zig`'s test block gains `_ = @import("dflash_ovn.zig");`, and `cuda_engine.zig` gains `snapshots.resumeDrafter` (prefillStart) and `dflash.located` (draftBlock). All three name code that only arrives in 0004: `git ls-tree <tree@0003> -- zig/src/families/glm/dflash_ovn.zig` returns nothing and `<tree@0004>` returns the blob. A test block's `_ = @import(...)` is analysed, so `zig build test-cuda-host` on pin+0001..0003 cannot start. The fold moves the three lines (J14).
- **F2. 0025's header names the wrong patch**: "0014 ported TF_GLM_OVN_REPLY_PREFILL". REPLY_PREFILL is 0008; 0014 is router-warm.
- **F3. 0024's header credits the `Lanes.prefillStep` shim to "0022 (glue fuse)".** `grep -l prefillStep patches/engine/*.patch work/final/*.patch` returns 0008 and 0024 only; `cuda_lanes_step.zig` is created by 0008.
- **F4. 0024's header credits the warm-serve test arity fix to "0014 (router warm)".** `zig/src/native/cuda_warm_serve_test.zig` is a new file in 0008.
- **F5. 0031's header repeats F3**: "0022 moved the stepped pass into `cuda_lanes_step.zig`".
- **F6. 0032's header says 0008 added the `.cu` file for `cuda_kda_chunk`.** 0008 adds the Zig module; `glm_kda_chunk.cu` and the `kernels.zig` embed are 0019's.
- **F7. 0053's header claims it completes 0019** "the patch that owns our `exl3_experts.cu` and `exl3_grouped.cuh` lines". 0019 touches neither file; both are pin files only 0044 and 0053 touch here.
- **F8. TF_GLM_OVN_KEPT_WALK is not a knob.** There is no `ovn.on("KEPT_WALK")` anywhere in the 68 patches; the only read is `const knob = "TF_GLM_OVN_KEPT_WALK";` in `zig/src/core/prompt_prefix_bench.zig`. Patch 0006 changes every kept-state walk on the default path unconditionally. Its property and count tests are the right defence, but the subject advertising a switch is wrong and upstream's "anything new defaults off behind a switch" is not met.
- **F9. `cuda_glue.zig` carries two identical `read`/`wanted` pairs, and the dead one reads four unported knobs.** `trace_line.py` on `pub fn wanted() bool` shows one copy at step 17 and a second at step 22. The live copy is in `Kernels` (0041's KVB8 term lands there); the copy in `Mla`, brought whole by 0017, reads MLA_FUSEMERGE, ABSORB_VEC, KVB8, DECODE_SHARD, LATENT_MMA, PK8 and SEG_PASS, the last four belonging to levers never ported. `docs/PATCH-AUDIT.md` lists the duplicate as dead code; new here is that it made 0041's hunk ambiguous to `git apply`, which seated the KVB8 term on the wrong copy until the fold's explicit edit fixed it.
- **F10. Patch 0020 mixes five knobs**: its subject names four, its diff also adds ROUTER16's kernel, field, loader and launch (J1).
- **F11. ROUTER16 was broken twice by later patches in the same series.** 0021's loader rewrite dropped the `@FieldType(Kernels, name) == cuda.Function` guard that 0020 itself had (restored by 0039), and 0022's graft of `glm_glue_bmm.cuh` deleted the kernel and `router()`'s launch (restored by 0038 and 0041). Both are knob-on defects only a `KNOBS=measured` boot would show.
- **F12. The KDA_CHUNKED knob is split across two levers.** The module rides with reply-prefill because that patch reads its `sub_rows`; the kernel, the fatbin embed and the catalog entry ride with 0019 and 0032. Between them the tree names a fatbin constant that does not exist (section 6). The host gates never saw it because Zig does not analyse an unreferenced `pub fn`; a full image build would.
- **F13. 0057's base check depends on a later patch** (`glue.Kernels.loadOvn`, added by 0021). Harmless in the old order, and the reason the fold holds that file back (J15).
- **F14. Twelve of the 35 folded levers carry no measurement at all**: 0012 reply-prefill, 0016 plain-margin, 0018 router-warm, 0019 win-free, 0020 sparse-onepass, 0021 onepass-pipe, 0023 kda-chunked, 0024 mm-knobs, 0025 mla-knobs, 0026 glue-fuse, 0027 shared-round-era, 0028 one-chunk-wiring. Three more carry only the fork's figure and not ours (0014 index-regroup, 0017 exchange-kb, 0033 exl3-dec-order), which `docs/PORT-LEFTOVER.md` already flags as needing our A/B before being quoted as ours.
- **F15. 0024 introduced a duplicate `padKdaInputs` call** in `cuda_tile.tileLinears`, removed by 0040; both now land in the KDA-pad patch, so the duplicate never exists.
- **F16. 0041's header does not name every patch it repairs.** `trace_line.py zig/src/families/glm/cuda_forward.zig "m.tiled = false"` shows both that line and `m.* = undefined` leaving the tree at step 17, so they are 0017's; 0019's header is what claims the `m.tiled` drop, and it is wrong.

## 8. What to do with this

- The next step re-seats `work/fold/0001..0035` onto v1.2.7 with `git apply --3way`; full blob ids are in place. `work/v127/survey.tsv` was taken on the 68 and should be retaken on the 35: five of its seven refusals (0018, 0026, 0027, 0030, 0036) are now single hunks inside a larger lever rather than patches of their own.
- The four class (c)/(d) patches at the head are the upstream candidates; 0001 is a real default-path defect at TP=3 and the strongest.
- Three things are worth fixing before the re-seat, because each is a split behaviour the re-seat would carry twice: F10/F11 (ROUTER16 as its own lever), F12 (`cuda_kda_chunk.zig` into the kda-chunked lever) and F8 (give KEPT_WALK a real switch, or change the subject and say it is an unconditional rewrite with a property test behind it).

## 9. The tooling

Under `work/fold/`, index-and-tree-only, no commits: `lib.py`, `build_old.py` -> `old_trees.txt`, `cmp_final.py`, `attrib.py`/`attrib_all.py` -> `attrib.txt`, `trace_line.py`, `plan.py` (the assignment table, the single source of the fold), `build_new.py` (cuts the 35 patches with claim accounting and the deferral check), `verify.py` -> `verify.log`, `map_series.py`/`series_md.py` -> `MAP.tsv`, `SERIES.md`, `prefix_symbols.py` -> `prefix_symbols.log`.

Note for whoever reruns this: never `git gc --prune=now` in `work/fold/scratch`. The old series' intermediate blobs are unreachable from any ref, so a gc deletes them and `build_new.py` then silently builds wrong trees; rerun `build_old.py` first if it happens.

---

Two incidents during the run, both reported to Main at the time: C: filled twice (the second time to 0 bytes), and a `git gc` of my own scratch destroyed the old series' intermediate blobs once. Everything above was re-run and re-verified after the last incident, on the current patch files - the `verify.log` quoted in section 4 is from the final state.