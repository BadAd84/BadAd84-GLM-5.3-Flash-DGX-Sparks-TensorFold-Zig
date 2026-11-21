# RECORD.md - patches/disk-any-position

## Base: upstream main `fa13df5dd1fdd23ada775510a464c9aa03a39e09` (re-seated 2026-11-21, lane reseat2)

Source: the same package of the series on the tip `46c6ee229d2ea28bde8b273381c0f0443861cdd6` (`archive/reseat-tip-46c6ee2-patches.tar`, tree `1fd680b2b681e80d1e40492f881b444602a5bc89`), each patch's own delta played onto `fa13df5dd1fdd23ada775510a464c9aa03a39e09` by a chain of three-way merges (`work/reseat2/series.py`); a patch that merged clean keeps its header and every added and removed line, only offsets and context moved. Hand resolutions in this package: none. Every decision, with the upstream commits, is in `work/reseat2/DECISIONS.md`.

This package applies to `fa13df5dd1fdd23ada775510a464c9aa03a39e09` with the packages before it in the order engine, pr1411, cache-salt, learn-starts, solo-cuts, disk-any-position, restore-held: it takes the tree `c80bf1cfe48715f2143ae91df0d7f054ee29fd10` to `2bf5025c155d91270afb1a6d2a77fa59965cf25f` (1 patch, 46 in all; ids are `git write-tree` on the tree built in that order). The base tree is `efd5bccea8b50fc9c98966f4a9f4161d2a6864d7`; the whole stack's tree is `19c545b35927ecbf59924852e6d5d07465c2bfe7`.

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

- `0001-glm-disk-state-at-any-position.patch`
