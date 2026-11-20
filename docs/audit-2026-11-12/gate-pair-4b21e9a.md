# Gate pair, pristine main `4b21e9ade` against the solo-to-start tree (2026-11-20)

This is a transcription, not the original log. The run was `sg-20261120-205747` on the gate host (`scripts/spark-gates.py gates --tree base --tree sts=<patch dir>`, pin `4b21e9adee1da175c0b8e352adbbefcb13943cef`, solo-to-start tree id `9884959483a89547b541c986a2e62cbc1230d029`, started 20:57 UTC, done 21:52 UTC). Its run directory, including `run.log`, was deleted by mistake during a cleanup of the gate host (the convention there is to keep every run's log and remove only its trees and home); the lines below are the ones read from `run.log` before that, copied from the session's tool output.

What the run was for: the rebased solo-to-start tree had failed one timing-sensitive disk test in an earlier run (the test is `kept states written to disk read back byte-equal after a restart, sharing blocks; a cut or flipped file is refused`, which exists once in the tree, in `zig/src/families/qwen3_5/cuda_disk_test.zig`, and is listed under two names), and the question was whether the pristine base fails it too.

```
[base gates] test-cuda-host rc=1 | Build Summary: 436/438 steps succeeded (1 failed); 7794/7838 tests passed (43 skipped, 1 failed)
[base gates] error: 'cuda_disk_test.test.kept states written to disk read back byte-equal after a restart, sharing blocks; a cut or flipped file is refused' failed:
[base gates] compile-cuda-tests rc=0 | Build Summary: 10/10 steps succeeded
[base gates] test-glm-ring-host rc=0 | Build Summary: 4/4 steps succeeded; 2/2 tests passed
[base gates] test-glm-logprobs-host rc=0 | Build Summary: 4/4 steps succeeded; 10/10 tests passed
[base gates] test-rows-host rc=0 | Build Summary: 3/3 steps succeeded
[base gates] test-glm-pdl-scan rc=0 | Build Summary: 4/4 steps succeeded; 3/3 tests passed
[base gates] test-kernel-contract rc=0 | Build Summary: 38/38 steps succeeded; 264/264 tests passed
[base gates] fmt rc=0
[verdict] verdict                      reference     PASS
[verdict] test-cuda-host failing names, as gates.sh listed them:
[verdict]   base: 1 listed
[verdict]     cuda_disk_test.test.kept states written to disk read back byte-equal after a restart, sharing blocks; a cut or flipped file is refused
[verdict]   sts: none listed, none new
[verdict] lean sts: base 7144 files 168 problems, head 7145 files 168 problems, 0 new
[verdict] VERDICT PASS: sts pass against base
SPARK-GATES-DONE 2026-11-20T21:52:22Z verdict=PASS
```

Reading: the pristine base fails that one test on this host under load, and the solo-to-start tree listed no failing name, so the test is a timing flake of the host and not a defect of the change. The head-skip tree's first `test` run (head `0e9ed5e91`, base `9f904af48`) failed the same single test and its rerun on the warm cache passed 438 of 438 steps.
