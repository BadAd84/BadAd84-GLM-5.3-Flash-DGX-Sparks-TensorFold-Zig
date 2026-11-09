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
- `scripts/serve.sh <rank> <parallel> [ctx]` boots one rank of the serve from that image. It
  is rank-local by design: rank, world size and the NCCL bootstrap address are parameters, so
  fleet orchestration stays outside this repo. It adds the recipe's knob set (the ones the
  patches implement) unless `XENV` already names a knob, so an A/B arm can turn any of them
  off without editing the script.
- `scripts/streams.py <port> <n> --kind prose|code` is the measurement instrument: N concurrent
  streams against the serve, reporting per-stream and aggregate decode plus each reply's sha256.
  A run that does not cover 1, 2, 4, 6 and 8 streams is not a verdict on a change.
- `PORT-LEDGER.md` records what is landed, what is parked and why, and the gates each patch
  was proved with.

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
