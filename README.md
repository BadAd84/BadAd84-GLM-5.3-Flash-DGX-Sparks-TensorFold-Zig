# GLM-5.3-Flash on DGX Sparks, TensorFold Zig engine

OTS recipe for serving GLM-5.3-Flash (Mia-AiLab EXL3 4bpw checkpoint) with the TensorFold
Zig engine on the DGX Spark fleet. Gitea is the home of this repo; GitHub carries a public mirror.

- `scripts/config.sh` pins the engine commit the recipe builds against.
- `patches/engine/` holds numbered engine patches, applied in filename order at image build.
  Each patch is one change, default-off or behaviour-identical until A/B'd at every stream
  count, with its measurement receipt in the header. A proven patch graduates to the
  `BadAd84/TensorFold` fork as a single-commit branch and goes upstream by PR; after it merges,
  the patch here is deleted and the pin advances past the merged commit.
- The `candidates/` directory holds unproven leads not in the applied stack.

Skeleton created at the reorganisation (2026-11-08); the OTS series re-cut from the ai-engine
trunk lands here as the numbered patches, with the tree-identity gate against `ovn-up` as the
first check.
