# RECORD.md - patches/pr1411

## Base: upstream main `fa13df5dd1fdd23ada775510a464c9aa03a39e09` (re-seated 2026-11-21, lane reseat2)

Source: the same package of the series on the tip `46c6ee229d2ea28bde8b273381c0f0443861cdd6` (`archive/reseat-tip-46c6ee2-patches.tar`, tree `1fd680b2b681e80d1e40492f881b444602a5bc89`), each patch's own delta played onto `fa13df5dd1fdd23ada775510a464c9aa03a39e09` by a chain of three-way merges (`work/reseat2/series.py`); a patch that merged clean keeps its header and every added and removed line, only offsets and context moved. Hand resolutions in this package: none. Every decision, with the upstream commits, is in `work/reseat2/DECISIONS.md`.

This package applies to `fa13df5dd1fdd23ada775510a464c9aa03a39e09` with the packages before it in the order engine, pr1411, cache-salt, learn-starts, solo-cuts, disk-any-position, restore-held: it takes the tree `ad9faacc3b9d` to `0b0849f5b784` (2 patches, 34 in all; ids are `git write-tree` on the tree built in that order). The base tree is `efd5bccea8b5`; the whole stack's tree is `b7f4d6f53f78`.

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

- `0001-pr1411-on-the-v129-engine-series.patch`
- `0002-pr1411-disk-read-rows-in-one-step.patch`
 This line was rewritten 2026-11-21 by the retirement lane: the package was applied again on the engine series
after its dead switches came out (engine tree `a12524ae144f47d41a977728b64b608359e62cc4`). The package's own hunks
are unchanged; only context lines that named removed engine fields moved (`Snap.win_from`, the dead `Marks.win_from`,
the `dr.restart` call behind the kept-window resume, the dflash window fields), so its behaviour is the same.

Gate: [stack gates] sg-20261121-233942 PASS on the whole stack (41 patches: engine 32, then pr1411, cache-salt,
learn-starts, solo-cuts, disk-any-position, restore-held) against the base of the same run. base tree
`efd5bccea8b5`, stack tree `b7f4d6f53f78`; every step rc 0 on both sides; gate-names 0 failing names on each
(base 7869/7912, stack 8073/8116); lean 7306 files 168 problems on the base against 7366 files 168 here, 0 new;
test-cuda-host and compile-cuda-tests 0. The engine half alone passed `sg-20261121-230313` on tree `ad9faacc`.
Re-seated 2026-11-22 on the engine tree `a12524ae144f47d41a977728b64b608359e62cc4` after the five dead switches' rows left `0020`; the
whole stack is `3845fe57f51997ea7cd24ce5da8d0aea077b8f53` and its gate run is `sg-20261122-222645`. Package behaviour unchanged.

Withdrawn 2026-11-22 (second pass): SPARSE_ONEPASS's last comment, ROUTER16's dead field and its two unlaunched
entry points, and INDEX_SCHED and POOLS32's rows, readers and doc rows left the series at their owning patches
(`0020`, `0022`, `0012`). DECODE_INDEX and the whole index path stay. Engine tree `a12524ae144f47d41a977728b64b608359e62cc4`, whole stack `3845fe57f51997ea7cd24ce5da8d0aea077b8f53`
(gate run sg-20261122-222645, PASS).

2026-11-22: `tf_glm_hc_partial8_pdl` now instantiates `partial8<true>` (it launched `<false>`, so the PDL_EARLY arm's
dependent wait never existed). Default path untouched. Engine tree `a12524ae144f47d41a977728b64b608359e62cc4`, whole stack `3845fe57f51997ea7cd24ce5da8d0aea077b8f53`, gate run sg-20261122-222645 PASS.

2026-11-22 (second pass): `0023` had its identity tile block removed (byte-identical by construction) and `0024` now
instantiates `partial8<true>`. Engine tree `a12524ae144f47d41a977728b64b608359e62cc4`, whole stack `3845fe57f51997ea7cd24ce5da8d0aea077b8f53`, gate run sg-20261122-222645 PASS.

2026-11-22 (third pass): patches 0019 and 0020 skip the speculative next-tile QK block on the last tile (low-value
speed candidate, receipts in their headers). Engine tree `a12524ae144f47d41a977728b64b608359e62cc4`, whole stack `3845fe57f51997ea7cd24ce5da8d0aea077b8f53`, gate run sg-20261122-222645 PASS.

2026-11-22 (fourth pass): `0025` bounds the dense call to the rows the select leaves alone (a 4,096-row first
chunk no longer runs dense attention over the 2,045 rows the sparse pass rewrites). Engine tree
`a12524ae144f47d41a977728b64b608359e62cc4`, whole stack `3845fe57f51997ea7cd24ce5da8d0aea077b8f53`, gate run sg-20261122-222645 PASS.

2026-11-22 (fifth pass): `0036` gates ABSORB_VEC to prompt rows and adds `tf_glm_absorb_q_vec_x2` /
`tf_glm_expand_v_vec_x2` behind it (16-byte loads with the two-row step), default off. Engine tree
`a12524ae144f47d41a977728b64b608359e62cc4`, whole stack `3845fe57f51997ea7cd24ce5da8d0aea077b8f53`, gate run sg-20261122-222645 PASS.
