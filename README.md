# GLM-5.3-Flash on DGX Sparks, TensorFold Zig engine

OTS recipe for serving GLM-5.3-Flash (Mia-AiLab EXL3 4bpw checkpoint) with the TensorFold
Zig engine on the DGX Spark fleet. Gitea is the home of this repo; GitHub carries a public mirror.

## Layout

- `scripts/config.sh` pins the engine commit the recipe builds against (`TF_REF`).
- `scripts/apply.sh <work-dir> [engine-src]` builds the tree: clones or copies the engine,
  checks out the pin, and applies every patch in `patches/engine/` in filename order. It
  refuses a tree that is not at the pin and prints which patches were already applied.
- `patches/engine/` holds the numbered engine patches. Each is one change, default-off or
  behaviour-identical until A/B'd at every stream count, with its measurement receipt in the
  header. A proven patch graduates to the `BadAd84/TensorFold` fork as a single-commit branch
  and goes upstream by PR; after it merges, the patch here is deleted and the pin advances.
- `scripts/build-image.sh <tag> <src.tar>` builds the serve image: a PyTorch CUDA base plus
  Zig, compiling the applied tree for `sm_121a` into `/opt/tensorfold` (binaries and fatbins
  only; weights and launchers come from the serve config). Pack the tree first:
  `tar -C <work-dir>/tree --exclude .git -cf <work-dir>/src.tar .`
- `scripts/serve.sh <rank> <parallel> [ctx]` boots one rank of the serve from that image, detached
  (`docker run -d`; logs via `docker logs glm53-zig-r<rank>`). It is rank-local by design: rank, world
  size and the NCCL bootstrap address are parameters. `scripts/zig-tp3.sh P [CTX]` boots the whole
  TP=3 on spark1-3 from the head (r0 spark1, r1 spark2, r2 spark3) and waits for `/v1/models`;
  `scripts/zig-tp3-stop.sh` stops all three. Production and both GLM watchdogs must be stopped for a
  window (the watchdog restarts production under the boot). The recipe's knob set is opt-in (`KNOBS=measured`), because this stack has
  not been A/B'd here yet and the rule is default-off until it is; any knob can still be
  overridden through `XENV`.
- `scripts/streams.py <port> <n> --kind prose|code` is the measurement instrument: N concurrent
  streams against the serve, reporting per-stream and aggregate decode plus each reply's sha256.
  A run that does not cover 1, 2, 4, 6 and 8 streams is not a verdict on a change.
- `PORT-LEDGER.md` records what is landed, what is parked and why, and the gates each patch
  was proved with.

## Patch packages

- **Everything external arrives as .patch files (owner 2026-11-11).** A contributor's branch, an upstream PR's
  commits or our own delta against a pin is carried as numbered `.patch` files in a package under ``patches/` and `candidates/``, applied to
  a pristine checkout at a recorded base sha. Each package carries `RECORD.md` (repository, branch, sha, the base it
  applies to, and whether we edited the text), `SHA256SUMS`, and `apply.sh` whose `--check` writes nothing. Someone
  else's commits come from `git format-patch` verbatim, ours from `git diff`; never merge, rebase or cherry-pick into
  the base tree, and never edit it in place, so the gates and any A/B run against upstream's own source. A measurement
  taken on a patched tree names the base sha and the patches applied.

- `scripts/check-patch-packages.sh` - every package dir that carries `.patch` files (walked to depth 3 under the
  roots in `scripts/patch-packages.list`) has `RECORD.md` and `SHA256SUMS`, and the hashes match. Packages written
  before the rule are listed in `scripts/patch-packages.allow` and skipped; `--strict` shows that debt, and each is
  brought up to the rule the next time it is touched.

## Gates

Run these on the applied tree, in this order. `test-cuda-host` is the gate that matters for
any patch touching the GLM family: `check-native-cuda-host` and `test-lane-api-host` do not
compile the family's host tests, so a patch can be green in them and still break the suite.

    zig build check-native-cuda-host
    zig build test-cuda-host
    zig fmt --check zig/
    python tools/zig/lean_check.py            # base and head lists, diffed with lean_new.py

## State

31 patches applied, all gates green on a fresh application onto the pin: compile, whole-tree
fmt, lean base-versus-head 0 new, and `test-cuda-host` at rc=0 with no named failures, which
is what a clean pin checkout gives.

The OTS series is not fully re-cut: the committed patch set covers the knobs that plug into
the pin's own structures, and `PORT-LEDGER.md` lists the commits parked on modules the pin
does not carry (`cuda_disk_image`, `cuda_forward_fronts`, `roce_rails`, `exl3_ovn`, the
32060d706 era layout) plus the A/B each still needs.
