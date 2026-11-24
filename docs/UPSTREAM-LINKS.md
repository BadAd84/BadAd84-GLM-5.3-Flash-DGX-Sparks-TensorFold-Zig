# Patch to upstream link

`main` accumulates every lever as a numbered patch under `patches/engine/`; that is the branch that becomes production.
A lever is ALSO cut as a branch from upstream `main` when we open it there, because upstream cannot take a patch series -
they take one behaviour a pull request. The branch is transport, not a second source of truth: it is cut from upstream's
tree, never merged back into this one, and the two are tied together by this table.

When upstream lands a lever, the PATCH is retired here (deleted from the series, with the upstream commit recorded), so
this repo's main and upstream's main converge on the same behaviour from opposite directions.

Every patch needs a row. `-` in the pull-request column means it has not been opened upstream yet; the state column says
whether it is planned, blocked (with why) or not upstreamable (with why).

| patch | subject | pull request | branch | state | retirement |
|---|---|---|---|---|---|
| `0001` | [PATCH] glm tests: the shared-window check sizes its rows from the eng | - | - | not opened | - |

## Candidate order for the upstream queue (assessed 2026-11-24)

`0001` is ready: one file, one behaviour, a latent defect, branch `lanes-test-window-rows` at `d16df9218`, fmt-green.

The next candidates are not equals, and this is what the series looks like when read for upstream shape:

| patch | shape | note |
|---|---|---|
| `0001` | one test file | a latent sizing defect; the clearest candidate |
| `0002` | three test files plus `server/root.zig` | mostly tests, but the `root.zig` hunk makes it a core and server change, so it needs its own one-behaviour argument |
| `0003` | host prompt-bench step | a tool addition, likely acceptable on its own |
| `0005`, `0019`, `0020`, `0022` | knobs with kernels | each needs the five settings places, a kernel-contract entry and a GPU receipt |
| `0032` | already up as pull request 4809 | in review |

So after `0001` the queue is a choice between `0003` (a tool, low risk), `0002` (mostly tests but touches `root.zig`), and taking a kernel lever through the full recipe. That choice is the owner's, and it is worth making before a branch is cut for the wrong one.
| `0002` | [PATCH] core and server: the disk grid on the I/O worker, and a quiesc | - | - | not opened | - |
| `0003` | [PATCH] host: the prompt-bench step, so request preparation can be tim | - | - | not opened | - |
| `0004` | [PATCH] core: the TF_GLM_OVN knob registry | - | - | not opened | - |
| `0005` | [PATCH] glm: TF_GLM_KDA_PAD pads the KDA input stack at one width | - | - | not opened | - |
| `0006` | [PATCH] glm: the DFlash2 draft knobs (TF_GLM_OVN_DRAFT_*) | - | - | not opened | - |
| `0007` | [PATCH] glm cuda: the index kernels take decode windows (TF_GLM_INDEX_ | - | - | not opened | - |
| `0008` | [PATCH] core: kept-state walks gated by the last id (TF_GLM_OVN_KEPT_W | - | - | not opened | - |
| `0009` | [PATCH] glm cuda: a pass the rebased index ring cannot hold is refused | - | - | not opened | - |
| `0010` | [PATCH] glm checks: the OVN check commands in their own table beside m | - | - | not opened | - |
| `0012` | [PATCH] glm cuda: TF_GLM_OVN_DECODE_INDEX, _INDEX_SCHED, _POOLS32 | - | - | not opened | - |
| `0014` | [PATCH] glm lanes: the stepped prompt pass in its own file beside cuda | - | - | not opened | - |
| `0019` | [PATCH] glm cuda: TF_GLM_OVN_SPARSE_ONEPASS, production's prompt spars | - | - | not opened | - |
| `0020` | [PATCH] glm: TF_GLM_OVN_ONEPASS_PIPE, the one-pass pipeline with bit-e | - | - | not opened | - |
| `0021` | [PATCH] glm cuda: TF_GLM_OVN_KDA_CHUNKED, production's chunked KDA pro | - | - | not opened | - |
| `0022` | [PATCH] glm cuda: TF_GLM_OVN_MM_WIDE, _SWIGLU_REDUCE, _MM_CLUSTER, _MM | - | - | not opened | - |
| `0023` | [PATCH] glm cuda: TF_GLM_OVN_MLA_FUSEMERGE, _ABSORB_VEC, _KVB8 | - | - | not opened | - |
| `0024` | [PATCH] glm cuda: TF_GLM_OVN_GLUE_FUSE, _GLUE_ROW, _PDL_EARLY | - | - | not opened | - |
| `0025` | [PATCH] glm latent: the head block takes the head count back (test-cud | - | - | not opened | - |
| `0026` | [PATCH] glm cuda: the MTP head's own passes run only without a DFlash2 | - | - | not opened | - |
| `0027` | [PATCH] exl3: TF_EXL3_DEC_ORDER launches each k slice's blocks before  | - | - | not opened | - |
| `0028` | [PATCH] host: byte equality by indexOfDiff, and a string index that st | - | - | not opened | - |
| `0029` | [PATCH] glm cuda: FP8 latent keys fetched a tile ahead, in 8-byte load | - | - | not opened | - |
| `0030` | [PATCH] server: render and tokenize a request once, and TF_GLM_OVN_HOS | - | - | not opened | - |
| `0031` | [PATCH] glm exl3: TF_GLM_OVN_X3_NC, X3_XROW and X3_FUSEDOWN, productio | - | - | not opened | - |
| `0032` | [PATCH] glm cuda: TF_GLM_OVN_KEEP_SEQS, a released stream's sequence s | `#4809` | `keep-seqs` | open, renamed `TF_GLM_KEEP_SEQS` upstream | not landed |
| `0033` | [PATCH] server: TF_GLM_OVN_OFF_EFFORT_LINE, a thinking-off GLM-5.3 pro | - | - | not opened | - |
| `0034` | [PATCH] glm lanes: TF_GLM_OVN_NO_COPY, a DFlash2 drafter's windows wit | - | - | not opened | - |
| `0035` | [PATCH] glm cuda tests: glm-mm-ovn, the matmul launch variants against | - | - | not opened | - |
| `0036` | [PATCH] glm latent: TF_GLM_OVN_LATENT_ROWS, absorb_q and expand_v two  | - | - | not opened | - |
| `0037` | [PATCH] glm cuda: TF_GLM_OVN_SIDE_PRIO, the prompt exchanges' side str | - | - | not opened | - |
| `0038` | [PATCH] glm cuda: TF_GLM_OVN_PIECE_FRONT, _MLA and _FFN, the next bloc | - | - | not opened | - |

## #4809 on 2026-11-24: base merged, CI running

The pull request had gone `CONFLICTING` as main advanced (a conflicting pull request runs no checks at all), so main was
merged into `keep-seqs` twice: `9edf2f89d45b` first, then `0d8cbb26f` once upstream moved again inside the hour. Both
conflicts were the changelog alone, resolved as upstream's file plus our one bullet.

- Merge commits `35600b2b2` and `436ef4b5c`, gated on the gate host at the first: `zig fmt --check` rc 0 and
  `zig build test-glm-rev25-host` rc 0.
- With the conflict gone the checks run again: `fmt`, `zig`, `pytest`, `benchmark-clients` on both runners and the rest
  were queued at 2026-11-24.

## #4809's checks after the merges (2026-11-24)

Nine of the ten ran and passed. One fails: `benchmark-clients (ubuntu-latest)`, job "No GPU", in
`tools/tests/test_bench_prose.py::test_serialized_streams_measure_shared_interval`, asserting `draft_arm["overlapped"]` is
false when it came back true. Evidence that it is not ours: the branch touches only
`zig/src/families/glm/cuda_env_test.zig`, `zig/src/platform/environment.zig` and their test, and the failing test lives in
`tools/`, which the branch does not modify; its windows counterpart passes on the same head.

Not claimed: that it fails on upstream main. Main's runs of that workflow are being cancelled repeatedly, so its history
cannot settle it, and the honest statement is the one above rather than a guess.
