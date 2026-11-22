# RECORD.md - patches/engine

## Base: upstream main `fa13df5dd1fdd23ada775510a464c9aa03a39e09` (re-seated 2026-11-21, lane reseat2)

Source: the same package of the series on the tip `46c6ee229d2ea28bde8b273381c0f0443861cdd6` (`archive/reseat-tip-46c6ee2-patches.tar`, tree `1fd680b2b681e80d1e40492f881b444602a5bc89`), each patch's own delta played onto `fa13df5dd1fdd23ada775510a464c9aa03a39e09` by a chain of three-way merges (`work/reseat2/series.py`); a patch that merged clean keeps its header and every added and removed line, only offsets and context moved. Hand resolutions in this package: 0006 (OVERLAP 1: upstream's `draftWide()` line kept, our `Knobs.read` after it), 0007 (OVERLAP 2: `cuda_index.zig` rewritten from the base plus our `all`, `decode`, `decode_from`, `decodeFrom()`, doc lines and tests; `tileLoop` and the decode grid expectations dropped as duplicates of upstream's adopted decode path), 0012 (upstream's `takesDecode` and `dscore` kept, our split, sched and POOLS32 alongside), 0013 (our `scorer` on upstream's `scoresTiles` arguments), 0019, 0020, 0023, 0024 (both-sides-added rows; `Forward.set()` carries upstream's `.dscore` with ours). Every decision, with the upstream commits, is in `work/reseat2/DECISIONS.md`.

This package applies to `fa13df5dd1fdd23ada775510a464c9aa03a39e09` with the packages before it in the order engine, pr1411, cache-salt, learn-starts, solo-cuts, disk-any-position, restore-held: it takes the tree `efd5bccea8b50fc9c98966f4a9f4161d2a6864d7` to `9d18692091aac67443466401195d4aae73fa79ca` (38 patches, 38 in all; ids are `git write-tree` on the tree built in that order). The base tree is `869f42e353f1a2334e015f9a696dc62b0d3748a7`; the whole stack's tree is `869f42e353f1a2334e015f9a696dc62b0d3748a7`.

Gate: [stack gates] GATES-DONE sg-20261121-100241-stack bad=0
SG gates stack rc=0
== gate-names base stack 10:50:23
[stack names] sg-20261121-100241-base: 0 failing names | 7869/7912 tests passed (43 skipped)
[stack names] sg-20261121-100241-stack: 0 failing names | 8087/8130 tests passed (43 skipped)
[stack names] only sg-20261121-100241-stack fails: none
[stack names] only sg-20261121-100241-base fails: none
SG names stack rc=0
== lean base stack 10:50:23
[stack lean] base ~/spark-gates/sg-20261121-100241/trees/base: 7306 files, 168 problems
[stack lean] head ~/spark-gates/sg-20261121-100241/trees/stack: 7376 files, 168 problems
[stack lean] lean: 168 problems, 168 on the base, 0 new
SG lean stack rc=0
== verdict 10:50:30
[verdict] run sg-20261121-100241; pin fa13df5dd1fdd23ada775510a464c9aa03a39e09 commit=fa13df5dd1fdd23ada775510a464c9aa03a39e09 tree=efd5bccea8b50fc9c98966f4a9f4161d2a6864d7 zig=0.17.0 sha256=f0dadfe4d23a0e63055ce9560ffe2f81a313af8697492bcd8c23a41f028d483a
[verdict]                              base          stack
[verdict] patches                      0/0           47/47
[verdict] tree id                      efd5bccea8b5  19c545b35927
[verdict] expected                     match         match
[verdict] check-native-cuda-host       0             0
[verdict] test-cuda-host               0             0
[verdict] compile-cuda-tests           0             0
[verdict] test-glm-ring-host           0             0
[verdict] test-glm-logprobs-host       0             0
[verdict] test-glm-onepass-order-host  n/a           0
[verdict] test-rows-host               0             0
[verdict] test-glm-pdl-scan            0             0
[verdict] test-kernel-contract         0             0
[verdict] fmt                          0             0
[verdict] gate-names                   -             0
[verdict] lean new                     -             0
[verdict] verdict                      reference     PASS
[verdict] rc per step from scripts/gates.sh (n/a: not a step of that tree, -: no result); test-cuda-host at rc 1 passes only when gate-names finds every failing name in base's set
[verdict] test-cuda-host failing names, as gates.sh listed them:
[verdict]   base: none listed
[verdict]   stack: none listed, none new
[verdict] lean stack: base 7306 files 168 problems, head 7376 files 168 problems, 0 new
[verdict] VERDICT PASS: stack pass against base
SG verdict rc=0
SPARK-GATES-DONE 2026-11-21T10:50:30Z verdict=PASS

Patches, in file-name order:

- `0001-shared-window-width.patch`
- `0002-rows-worker-and-quiesce-drain.patch`
- `0003-prompt-bench.patch`
- `0004-ovn-knob-registry.patch`
- `0005-kda-pad-one-width.patch`
- `0006-draft-knobs.patch`
- `0007-index-decode-windows.patch`
- `0008-kept-walk-prefix-helper.patch`
- `0009-ring-past-refusal.patch`
- `0010-ovn-check-table.patch`
- `0012-index-sched-decode-pools32.patch`
- `0014-lanes-step-split.patch`
- `0019-sparse-onepass.patch`
- `0020-onepass-pipe.patch`
- `0021-kda-chunked.patch`
- `0022-mm-knobs.patch`
- `0023-mla-knobs.patch`
- `0024-glue-fuse.patch`
- `0025-head-block-rule.patch`
- `0026-head-flag.patch`
- `0027-exl3-dec-order.patch`
- `0028-memo-equal-strindex.patch`
- `0029-fp8-tile-ahead.patch`
- `0030-render-once-host-once.patch`
- `0031-glm-exl3-x3-decode.patch`
- `0032-glm-keep-seqs.patch`
- `0033-glm-off-effort-line.patch`
- `0034-glm-no-copy.patch`
- `0035-glm-mm-ovn-check.patch`
- `0036-glm-latent-rows.patch`
- `0037-glm-side-prio.patch`
- `0038-glm-piece-front.patch`

## Retired 2026-11-21 (lane retire; docs/KNOB-PROVENANCE.md class A)

Six patches left the series and four kept patches lost their dead switches, so this package is 32 patches and its
tree is `869f42e353f1a2334e015f9a696dc62b0d3748a7` (rebuilt patch by patch in `work/retire/chain`, branch `new`; every
earlier tree id in the list above moved where a retirement precedes it). Retired whole, numbers never reused:
`0013` INDEX_REGROUP, `0015` PLAIN_MARGIN, `0016` EXCHANGE_KB, `0017` ROUTER_WARM, `0018` WIN_FREE, `0039` PIECE_KDA.
Switches removed from patches that stay: `0006` DRAFT_KEEPWIN and DFLASH2_WIN, `0019` SPARSE_ONEPASS (kernel, image row
and `takes` kept: `glm-onepass-exact-check` compares the active pipe's off variant against the kernel), `0021`
KDA_CHUNKED (the L2PF file the fold brought in is what stays; the bodyProfile call shape is kept), `0022` MM_CLUSTER and
ROUTER16. Still to come: `0023`'s KVB8 and `0038`'s FRONT_ROWS (both measured short, s61), the router16 kernels in
`glm_glue_bmm.cuh`, and nothing else from this lane.

Gate: [stack gates] sg-20261121-230313 PASS against the base of the same run (`python scripts/spark-gates.py wait --run
sg-20261121-230313`). Every step rc 0 on both trees; gate-names 0 failing names on each (base 7869/7912, ret 7988/8031);
lean 7306 files 168 problems on the base against 7352 files 168 problems here, 0 new; test-cuda-host and
compile-cuda-tests 0. Before the full run the same tree passed `iter ... check fmt test ctest` (rc 0 each).

The same tree inside the whole stack (41 patches) was gated again as `sg-20261121-233942`: PASS, stack tree
`b55af74859677c243aee957d0e88d488885f6c9c`, every step rc 0, gate-names 0 failing names each side (base 7869/7912,
stack 8073/8116), lean 7306 files 168 problems against 7366 files 168, 0 new.

The five switches with no reader left - WIN_FREE, PLAIN_MARGIN, EXCHANGE_KB, ROUTER_WARM and INDEX_REGROUP - lost
their registry rows and doc rows at `0020` on 2026-11-22, so a boot no longer accepts a name nothing reads; every
prefix of the series builds (`iter check fmt test ctest`). The engine tree is now `869f42e353f1a2334e015f9a696dc62b0d3748a7` and the whole stack
`b55af74859677c243aee957d0e88d488885f6c9c`; gate run `sg-20261122-041555`.

Withdrawn 2026-11-22 (second pass): SPARSE_ONEPASS's last comment, ROUTER16's dead field and its two unlaunched
entry points, and INDEX_SCHED and POOLS32's rows, readers and doc rows left the series at their owning patches
(`0020`, `0022`, `0012`). DECODE_INDEX and the whole index path stay. Engine tree `869f42e353f1a2334e015f9a696dc62b0d3748a7`, whole stack `b55af74859677c243aee957d0e88d488885f6c9c`
(gate run sg-20261122-041555, PASS).
