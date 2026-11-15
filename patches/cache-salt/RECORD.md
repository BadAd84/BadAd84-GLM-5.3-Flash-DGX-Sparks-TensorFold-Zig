# RECORD.md - patches/cache-salt

What it is: upstream PR ashhart/TensorFold#3222 (prompt cache salts: `cache_salt` and `serve --cache-salt-per-key` keep
kept prompt states apart), by Ash, re-seated on this recipe's engine after `patches/pr1411`, plus one test file of ours.
A request's salt masks the first four words of the lane host's cache key with high-bit words, so a kept state is resumed
only by a request of the same salt; the rows writer, the rows reader and `--learn` already refuse high-bit words
(`cache_images.diskSafe`), so the GLM disk tier of `patches/pr1411` never writes a salted state or reads one for a salted
request. Retire the package when the pin moves past #3222's landing on upstream main.

Source: repository `ashhart/TensorFold`, branch `lead/cache-salt`, head `2a870a8b0508e06362224de64fdbefc3bb43062b` (2 commits)
on upstream main `d6c4cce602eef4aff235625a5325bb617a9674ff`; fetched as `pull/3222/head` on 2026-11-15, open, GitHub's
base `2ba55ec7d32d0bec446bb012678550be7ef52895` (the diff against it is the same 49 files, +743/-76).

Base it applies to: `93a2e93ecebff8aa52b88e58c5dd222516e69c5f` (v1.2.7) plus `patches/engine/` 0001-0036 plus
`patches/pr1411/` 0001-0013, tree `e8f7f3c74548a445c98da58910aa13a7f1c6ee88`; final tree `a3ed3b7a85f3cfaf86ec2e99d6623637883fbeec`
(with pr1411 0001-0012 alone: tree `e567d98959661da15d756103cc2d59051cacb78b`, final `25cefd706dc3741584b0cab4d6b216ed24d752bc`;
on that base: after 0001 `6506ffb2dc946d794c5a08890514bde56f961af6`, after 0002 `b520e775f8ddfd3942f20500a4df557336e2205e`, after 0003
`2dba226410de6993854f11ec5b86f6594e7eebb7`).

How it was made (`work/SaltCarry/package.py`): 0001 is the first commit merged three-way onto the base (its parent as the
merge base) and re-emitted as `git diff-tree -p --full-index` under its own author, date and message; every line it adds
or removes is one the commit adds or removes. 0002 is the second commit redone on our goldens. 0003 and 0004 are ours. Then every
patch is applied with plain `git apply --cached` from the base and the final tree compared with the one built.

| patch | source | how |
|---|---|---|
| 0001 | `33ec18b31` | three-way; three conflicts resolved by the edits below; `zig/src/server/private_files_test.zig` left out (v1.2.7 has no such file; 11 of the commit's changed lines are in it) |
| 0002 | `2a870a8b0` | redone: in our 17 goldens (the commit's files) `"cache_salt": false, ` follows `"prompt_cache": false, ` in each /v1/models capabilities object (34) and each such reply's Content-Length grows by 21 an object; the same edit made on the commit's parent gives the commit's own 17 files byte for byte |
| 0003 | ours | the PR's salted-note assertions (from its `private_files_test.zig` hunk) in `zig/src/server/compact_mem_salt_test.zig`, imported from `root.zig` |
| 0004 | ours | `core/engine_api.zig` is 600 lines on the base and 0001 adds five (a new lean problem, over 600): the doc comments of `Request.cache_key`, `Request.salted`, `Info.prompt_logprobs`, `Info.prompt_cache` and `Info.cache_salt` move onto their fields' lines; no code changes |

The conflicts in 0001, each checked by the builder before it edits:
- `docs/api.md`: main has a paragraph on connection limits where the PR adds its section; v1.2.7 has neither. The section
  "Prompt cache salts" is carried, the paragraph is not.
- `zig/src/server/cli.zig`: the PR adds `else if (is(name, "--cache-salt-per-key")) out.cache_salt_per_key = true` after
  `--prompt-seed` on one long line, the next line of which v1.2.7 writes differently (`--compact-at`). The clause goes into
  our line; the commit's own change to that line is the clause alone.
- `zig/src/server/openai.zig`: main registers the request for `POST /v1/requests/{id}/cancel` above the PR's line; v1.2.7
  has no such registry. Only the PR's line `p.input.cache_salt = ...ofRequest(...)` is carried.

Apply after the series and pr1411: `scripts/apply.sh WORK`, `patches/pr1411/apply.sh WORK/tree`, then
`patches/cache-salt/apply.sh WORK/tree` (`--check` writes nothing and prints the tree it would make). With the sliced disk
reads (`patches/pr1411/` 0013, checked together in both orders with `apply.sh --check`) it shares `core/lane_host.zig` (its hunk in `run()`, ours in
`infoFn` and the repeat note) and `docs/environment.md` (another row); check both orders with `apply.sh --check`.
Hashes: `SHA256SUMS`.
