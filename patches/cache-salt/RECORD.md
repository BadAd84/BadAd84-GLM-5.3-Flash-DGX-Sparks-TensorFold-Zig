# RECORD.md - patches/cache-salt

## Current base (re-seated 2026-11-20)

This package applies to upstream TensorFold main `1ece6e6dbbc073582d50738ce8e73e3c3261a73b` (1.3.0) with the packages before it in the order engine, pr1411, cache-salt, learn-starts,
solo-cuts, disk-any-position, restore-held: it takes the tree `7ddf34d11e9578140fbb37fe544b4d3353c417e6` to `fd6d279df5e17e1d0f817b8dc16545b2075797e1` (2 patches, 42 in all; both ids are
`git write-tree` on the tree built with `scripts/apply.sh` and the packages' `apply.sh` in that order). What each patch needed is in `docs/audit-2026-11-12/reseat-main-1ece6e6.md`.

Gate: full run `sg-20261120-165217` on the gate host, the pristine main (tree `3a37e287fb1c`) against this series (47 patches in the seven packages, tree `5ae4bbe5e418`, the id the run expected): `check-native-cuda-host`, `compile-cuda-tests` (10 of 10 steps), `test-glm-ring-host`, `test-glm-logprobs-host`, `test-rows-host`, `test-glm-pdl-scan` (3 of 3 tests), `test-kernel-contract` (258 of 258 tests) and `fmt` rc 0 on both, `test-glm-onepass-order-host` rc 0 on the stack (not a step of the base); `test-cuda-host` rc 1 on both with the base's one failing name, `cli_config_test`'s `serve --config` case (7,903 of 7,947 tests passed on the stack, 43 skipped, 1 failed; 7,687 of 7,731 on the base); no new failing name; lean base 6,993 files and 168 problems, head 7,063 files and 168 problems, 0 new. Verdict PASS. An earlier run of the same series (`sg-20261120-145609`) failed with 7 new failing names, every one an abort inside `cuLaunchKernelEx`: upstream's `7948cc42d` launches every GLM kernel through it and asks every fake test driver to forward it (`cuda_pdl.forwardEx`), and the fakes in tests our patches add (`cuda_mla_ovn_test`, the latent-rows test in `cuda_latent`, `cuda_disk_ranks_test`) did not. The lanes' quick checkpoints had not run the host test step, so only the full gate saw it; each of the five fakes now carries the line, inside the patch that owns the test (23, 36 and the `pr1411` package).

The text below was written for the v1.2.9 series (base `6b9de695104b6b8b30c20458da87ac06c9480289`): its file and line references, tree ids and measurements are to that base.

What it is: upstream PR ashhart/TensorFold#3222 (prompt cache salts: `cache_salt` and `serve --cache-salt-per-key` keep
kept prompt states apart), by Ash, on the recipe's engine series after `patches/pr1411`. A request's salt masks the
first four words of the lane host's cache key with high-bit words, so a kept state is resumed only by a request of the
same salt; the rows writer, the rows reader and `--learn` already refuse high-bit words (`cache_images.diskSafe`), so the
GLM disk tier of `patches/pr1411` never writes a salted state or reads one for a salted request. Retire the package when
the pin moves past #3222's landing on upstream main.

Source: repository `ashhart/TensorFold`, branch `lead/cache-salt`, head `2a870a8b0508e06362224de64fdbefc3bb43062b`
(2 commits) on upstream main `d6c4cce602eef4aff235625a5325bb617a9674ff`; checked 2026-11-15 with `gh pr view 3222 -R
ashhart/TensorFold --json state,mergedAt,headRefOid`: OPEN, not merged, the same head.

Base it applies to: v1.2.9 `6b9de695104b6b8b30c20458da87ac06c9480289` + the engine series (tree `e02b8a89c2ccbb7fe67e42fb4bf300bec1a5f2c3`) +
`patches/pr1411`, tree `3b06d167fd742683f210ffc7f69eef5199640664`. Final tree, the whole stack: `27a87244e7dca097007c8b086b7c49a76a8e69d2`.

How it was made (`work/V129B/recut_combined.py`): lane V129B's per-commit package on pristine v1.2.9
(`work/V129B/package/patches/cache-salt/`, gated on spark5; its RECORD.md has the details) applied to the tree above and
re-emitted with `git diff-tree -p --full-index`; each patch adds and removes exactly the lines of its pristine
counterpart (checked by the builder), only index lines and offsets differ.

| patch | source | how |
|---|---|---|
| 0001 | `33ec18b31` | merged three-way on v1.2.9; one conflict (`zig/src/server/errors.zig`: upstream's `skip_request_log` and the PR's `cache_salt` at one anchor, both kept); edited by us: the comment above `var asked` in `zig/src/server/openai.zig` moved onto that line, so the file stays at 600 lines |
| 0002 | `2a870a8b0` | the PR's golden edit redone on v1.2.9's goldens (the same 17 files, 34 `/v1/models` capability bodies, each Content-Length 21 more an object) |
| 0003 | ours | retired: v1.2.9 has `zig/src/server/private_files_test.zig` and 0001's own hunk carries the PR's salted-note assertions |
| 0004 | ours | 0004 (ours: five field comments of `core/engine_api.zig` moved onto their fields' lines) is not carried: that file is 595 lines after 0002 here, inside the lean gate's 600 |

Apply after the series and pr1411: `scripts/apply.sh WORK`, `patches/pr1411/apply.sh WORK/tree`, then
`patches/cache-salt/apply.sh WORK/tree` (`--check` writes nothing and prints the tree it would make). Hashes: `SHA256SUMS`.

## Gate (spark5, 2026-11-15T17:28:49Z; `python work/V129B/recut_combined.py SERIES_DIR --gate`)

```
v129b-comb base tree 4be51cc6beefee860f611b5bb928dd06a4f3c72c
v129b-comb tree id 27a87244e7dca097007c8b086b7c49a76a8e69d2 (35 patches)
v129b-comb check rc=0 | 
v129b-comb fmt rc=0
[v129b-comb gates] check-native-cuda-host rc=0 | Build Summary: 7/7 steps succeeded
[v129b-comb gates] test-cuda-host rc=1 | Build Summary: 410/412 steps succeeded (1 failed); 6850/6885 tests passed (33 skipped, 2 failed)
[v129b-comb gates] compile-cuda-tests rc=0 | Build Summary: 10/10 steps succeeded
[v129b-comb gates] test-glm-ring-host rc=0 | Build Summary: 4/4 steps succeeded; 3/3 tests passed
[v129b-comb gates] test-glm-logprobs-host rc=0 | Build Summary: 4/4 steps succeeded; 10/10 tests passed
[v129b-comb gates] test-glm-onepass-order-host rc=0 | Build Summary: 3/3 steps succeeded
[v129b-comb gates] test-rows-host rc=0 | Build Summary: 3/3 steps succeeded
[v129b-comb gates] fmt rc=0 
[v129b-comb gates] GATES-DONE v129b-comb bad=1
[v129b-comb gates] rc=1
[v129b-comb names] v129-base: 2 failing names | 3836/3852 tests passed (14 skipped, 2 failed)
[v129b-comb names] v129b-comb: 2 failing names | 6850/6885 tests passed (33 skipped, 2 failed)
[v129b-comb names] only v129b-comb fails: none
[v129b-comb names] only v129-base fails: none
[v129b-comb names] rc=0
[v129b-comb lean] base /home/adam/v129/trees/base: 6454 files, 341 problems
[v129b-comb lean] head /home/adam/v129/trees/v129b-comb: 6512 files, 341 problems
[v129b-comb lean] lean: 341 problems, 341 on the base, 0 new
[v129b-comb lean] rc=0
[v129b-comb gates] error: 'cli_config_test.test.serve --config: expand reads the file, passes other commands through and names what it cannot read' failed:
[v129b-comb gates] error: 'listener.test.accepted IPv4 and IPv6 TCP streams disable Nagle for incremental responses' failed:
```
