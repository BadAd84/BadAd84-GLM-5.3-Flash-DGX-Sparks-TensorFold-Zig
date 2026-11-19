# RECORD.md - patches/learn-starts

What it is: our own change (not an upstream commit), on this repo's engine stack, that lets
`TF_GLM_REQUEST_STARTS=1` run together with `--learn-conversations`, and makes a state kept at a request start
survive the disk round trip with the one thing its resumption checks. Upstream's #2404 refused the two settings
together "until the disk image takes off-grid rows"; this package is that work for our serve: the image still holds
exactly the rows the state holds, and now also carries the digest of the pass's chunk starts below the state's
position (`cuda_prompt_cuts.below`), which `cuda_prompt_cuts.resumes` compares before a resume. Upstream's
`TF_KV_SHARE` refusal stays (its kept state's prefix pages are outside the lease a disk image reads).

The path, before this package (file:line on the tree it applies to):

- live keep: `zig/src/families/glm/cuda_native.zig:438` (`snap_save`) builds `Kept{ .id, .at, .below }` with
  `below = cuda_prompt_cuts.below(e.cur.cuts.items, at)`; `cuda_snapshots.zig:99` (`keepAs`) copies the state into
  its lease, and the digest was not recorded anywhere else.
- save: the prompt store gathers the image with `cuda_glm_disk.zig:48` (`gather`), whose words piece comes from
  `cuda_disk_ranks.zig:22` (`wordsOf`) reading the engine's snapshot: position, head rows, ring bases, copy bits,
  world, layout. The digest was lost at this step.
- restore: `rows_read.zig:23` calls `cuda_glm_disk.zig:69` (`blank`), which makes a `Kept` with the default
  `below = 0`; `cuda_glm_disk.zig:80` (`scatter`) decodes the file's words and seals each rank's snapshot
  (`cuda_disk_ranks.zig:187`), and the restored `Kept` kept `below = 0`.
- resume: `cuda_lanes.zig:355` (`resumeFrom`) refuses a state unless
  `cuda_prompt_cuts.resumes(len, s.chunks, k.at, k.below)` (`cuda_prompt_cuts.zig:36`): a cold cut at `at` over the
  same chunks below it. A state kept at a request start has `below != 0`, so every read back state was refused,
  and a grid state read back with `below = 0` was refused by any pass that cut a start below it.

The on-disk form: the image's words gain a tenth word, the digest, and the words' format rises to 2
(`cuda_disk_image.zig:9`, `Words`). The alternatives and why not: a field of the store's own file trailer (`rows_file.zig`)
is shared by every family and would hold a per-state GLM fact the store cannot check; recomputing the digest from
the store's index `starts` is not possible because those are kept for a planned family and GLM's store is not
planned. Format 1 (nine words) is refused by name: `Words.decode` returns `error.DiskWords`, which `rows_read.zig`
treats as a failed check and deletes, and the store's identity hashes the load probe's image, words included, so a
directory written by the previous build differs and is never read. A state on the plain grid carries a zero digest
and resumes exactly as before. A state whose position is not a whole number of pooled rows (the image's `parts`
refuse it, `cuda_disk_image.zig:116`) is not written: the store counts the save skipped and the request is
unaffected, so such a start keeps its state in RAM only. That held for this package alone: its GPU check (OVERNIGHT
section 51) found that three request starts in four were such states, and `patches/disk-any-position` lifts the rule.

What it edits (all on the tree it applies to):

| file | change |
|---|---|
| `zig/src/families/glm/cuda_disk_image.zig` | `Words.below` (tenth word), format 2, encode and decode carry it |
| `zig/src/families/glm/cuda_engine_types.zig` | `Snap.below`: the digest the engine holds for a kept state |
| `zig/src/families/glm/cuda_snapshots.zig` | `keepAs` records the digest; `seal` takes it and seals it on the state |
| `zig/src/families/glm/cuda_disk_ranks.zig` | `wordsOf` writes it into the words; `unseal` decodes it onto the `Kept` and seals; both `seal` paths pass it |
| `zig/src/native/cuda_glm_disk.zig` | `scatter` restores the digest through `ranks.unseal` |
| `zig/src/families/glm/cuda_env.zig` | the `--learn-conversations` refusal lifted; the `TF_KV_SHARE` one kept |
| `zig/src/families/glm/cuda_native.zig` | the unreachable refusal's text removed; the option comment |
| `zig/src/families/glm/cuda_request_starts_test.zig` | the refusal test now expects the open to pass that check |
| `zig/src/families/glm/cuda_disk_image_test.zig` | the words tests for ten words and format 1; the seal tests carry the digest |
| `zig/src/families/glm/cuda_disk_ranks_test.zig` | the keep, the read back and `resumes` tests for the digest |
| `docs/recipes/glm-5.3-flash-cuda.md` | the request starts row: the pair is served, the digest is on disk |

Base it applies to: the stack at the pin `6b9de695104b6b8b30c20458da87ac06c9480289` (v1.2.9) plus
`patches/engine` (35 patches, series tree `2af443845021d4b310032b3e51d81c38d6059df4`), `patches/pr1411` (2) and
`patches/cache-salt` (2), tree `5137a5ef75ab14cbe0a83ba34511523e2322795c` (39 patches). This package makes tree
`7c8a05f9cf726ee971e6e2775fe993f881525ab9` (40 patches). Both ids are `git write-tree` on the tree built from the
pin by `scripts/apply.sh`, `patches/pr1411/apply.sh` and `patches/cache-salt/apply.sh`, with this package's
`apply.sh --check` giving the second.

With `patches/engine/0036` in the series (2026-11-19) the base is `33247f87b97b2762424a0e5390cf86044be13268` (40
patches) and this package applies to it unchanged and makes `85d45758d73b66f75f6fbe38b0c58a9cde586008` (41 patches).

With `patches/engine/0037` as well (2026-11-19) the base is `4a72871f89fac64631c9b6701d0d121ed8dde79a` (41 patches) and this
package applies to it unchanged and makes `098a8968dc83c191e71c67bc3a9a13da9545a52c` (42 patches).

Apply after the other three: `bash patches/learn-starts/apply.sh --check WORK/tree` writes nothing and prints the
tree it would make; without `--check` it applies the patch to the tree. Hashes: `SHA256SUMS`.

Source: ours, written on the trees named above; no upstream commit corresponds to it, and no upstream PR exists
for it. Retire the refusal half of it if upstream lands a request-start disk image of its own; the digest word is
compatible with any image that keeps the rows as this one does.

## Gate

Measured on the shared gate host (x86_64, 16 threads) with `scripts/spark-gates.py`, pin `6b9de695104b`, Zig 0.17.0.

- The first fast loop did not compile: `cuda_disk_ranks.zig:187` named `Engine.Kept`, and `Kept` is `cuda_engine.zig`'s
  module-level re-export (`pub const Kept = types.Kept`), not a member of `Engine`. The patch now imports it as
  `cuda_glm_disk.zig` does, `@import("cuda_engine.zig").Kept`, in `cuda_disk_ranks.zig` and its test.
- Fast loop on `patches/engine,patches/pr1411,patches/cache-salt,patches/learn-starts` (tree `7c8a05f9cf72`):
  `check-native-cuda-host` and `zig fmt` rc 0; lean 341 problems against 341 on the pristine pin, 0 new;
  `test-cuda-host` 3,142 of 3,164 passed, 21 skipped, 1 failed, `cli_config_test`'s `serve --config` case, which fails
  on the pristine v1.2.9 itself.
- Full run `sg-20261118-224955`, the pristine pin (tree `4be51cc6beef`) against the stack (tree `7c8a05f9cf72`):
  `check-native-cuda-host`, `compile-cuda-tests`, `test-glm-ring-host`, `test-glm-logprobs-host`, `test-rows-host` and
  `fmt` rc 0 on both, `test-glm-onepass-order-host` rc 0 on the stack (not a step of the base); `test-cuda-host` rc 1 on
  both with the same one failing name, 0 new; lean base 6,454 files and 341 problems, head 6,516 files and 341 problems,
  0 new. Verdict PASS.
- Mutants, each the patch with one change (`work/LearnStarts/mk-mutants.py` anchors every change once in the clean
  patch), through the fast loop's `test-cuda-host`: each failed exactly one test beyond the pristine `cli_config_test`,
  the test written for it.

| mutant | the change | the test that failed |
|---|---|---|
| m1 | the restore no longer sets the file's digest on the state read back | `GLM disk ranks: a state read back keeps its file's digest, and resumes only a pass that cuts alike` |
| m2 | the `--learn-conversations` refusal put back | `glm request starts: --learn-conversations starts beside the switch, past the startup check` |
| m3 | `keepAs` no longer records the digest | `GLM disk ranks: a kept state's words carry the digest of the cuts its pass kept it under` |
| m4 | `wordsOf` no longer writes the digest into the words | the same test as m3 |
| m5 | the words' format number back to 1 | `GLM disk image: the words' digest round-trips, and a nine-word format 1 image is refused by name` |

Not yet run: the GPU. Its check is a served one: `LEARN=1` with `TF_GLM_REQUEST_STARTS=1` through
`scripts/queue-disk-tier.sh`, every resumed reply equal to a cold server's.
