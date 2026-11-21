# RECORD.md - patches/engine

## Base: upstream main `fa13df5dd1fdd23ada775510a464c9aa03a39e09` (re-seated 2026-11-21, lane reseat2)

Source: the same package of the series on the tip `46c6ee229d2ea28bde8b273381c0f0443861cdd6` (`archive/reseat-tip-46c6ee2-patches.tar`, tree `1fd680b2b681e80d1e40492f881b444602a5bc89`), each patch's own delta played onto `fa13df5dd1fdd23ada775510a464c9aa03a39e09` by a chain of three-way merges (`work/reseat2/series.py`); a patch that merged clean keeps its header and every added and removed line, only offsets and context moved. Hand resolutions in this package: 0006 (OVERLAP 1: upstream's `draftWide()` line kept, our `Knobs.read` after it), 0007 (OVERLAP 2: `cuda_index.zig` rewritten from the base plus our `all`, `decode`, `decode_from`, `decodeFrom()`, doc lines and tests; `tileLoop` and the decode grid expectations dropped as duplicates of upstream's adopted decode path), 0012 (upstream's `takesDecode` and `dscore` kept, our split, sched and POOLS32 alongside), 0013 (our `scorer` on upstream's `scoresTiles` arguments), 0019, 0020, 0023, 0024 (both-sides-added rows; `Forward.set()` carries upstream's `.dscore` with ours). Every decision, with the upstream commits, is in `work/reseat2/DECISIONS.md`.

This package applies to `fa13df5dd1fdd23ada775510a464c9aa03a39e09` with the packages before it in the order engine, pr1411, cache-salt, learn-starts, solo-cuts, disk-any-position, restore-held: it takes the tree `efd5bccea8b50fc9c98966f4a9f4161d2a6864d7` to `9d18692091aac67443466401195d4aae73fa79ca` (38 patches, 38 in all; ids are `git write-tree` on the tree built in that order). The base tree is `efd5bccea8b50fc9c98966f4a9f4161d2a6864d7`; the whole stack's tree is `19c545b35927ecbf59924852e6d5d07465c2bfe7`.

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
- `0013-index-regroup.patch`
- `0014-lanes-step-split.patch`
- `0015-plain-margin.patch`
- `0016-exchange-kb.patch`
- `0017-router-warm.patch`
- `0018-win-free.patch`
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
- `0039-glm-piece-kda.patch`
