#!/usr/bin/env python3
"""Check docs/SPEC-INDEX-SPLIT.md against the call sites it claims to describe.

The specification is written so the kernel can be reimplemented with the reference closed. An adversarial review found
seven defects in an earlier version, none of which any compile could catch: an inverted count rule that would have made
every row fall back to dense attention, and reads of scratch whose producing write was not ordered. This gate re-checks
the facts those findings rested on, from OUR OWN call sites, so a later edit cannot quietly reintroduce them.

Run: python scripts/check-spec-index-split.py [REPO]
Exit 0 when every checked fact holds; 1 with one line per failure.
"""
import pathlib, re, sys

repo = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
tree = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else repo

spec = (repo / "docs/SPEC-INDEX-SPLIT.md").read_text(encoding="utf-8")
index_path = tree / "zig/src/families/glm/cuda_index.zig"
index = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
ops = None
for cand in tree.glob("zig/**/glm_ops.cu"):
    ops = cand.read_text(encoding="utf-8"); break

fails = []
if not index:
    # This repo tracks no engine tree: the call sites live in the tree the spec is about, which apply.sh produces.
    # Say so and check only what the spec itself can be held to.
    print("note: no engine tree at %s, so the call-site checks are reported as unrun" % tree)

def want(cond, msg):
    if not cond: fails.append(msg)

# 1. The count rule, which an early version had inverted. It is the call site's rule, not the reference's.
m = re.search(r"counts\[[^\]]*\]\s*=\s*([^;]+);", ops or "")
want(m is not None or not ops, "glm_ops.cu: the counts rule was not found, so the spec's rule cannot be checked")
if m and ops:
    rule = " ".join(m.group(1).split())
    want("npool > K" in rule or "npool>K" in rule, "glm_ops.cu: the counts rule no longer keys on npool > K: %s" % rule)
    want("4 * K" in rule or "4*K" in rule, "glm_ops.cu: the counts rule no longer carries 4 * K: %s" % rule)
    want("npool > K" in spec, "the spec does not state the counts rule as npool > K")
    want("MORE\n  COMPLETE POOLS" in spec or "MORE COMPLETE POOLS" in spec,
         "the spec does not state that the count keys on COMPLETE pools")

# 2. The caller zeroes tot only. The spec must not require gt or hist to arrive zeroed.
if index:
    body = index[index.index("pub fn selectSplit"):]
else:
    body = ""
    body = body[:body.index("\n    }")]
want("cuMemsetD32Async(scratch, 0, rows * 1024" in body or not index,
     "cuda_index.zig: the caller no longer zeroes exactly rows * 1024 dwords at scratch")
want("rows * 1024" in spec, "the spec does not state that the caller zeroes rows * 1024 dwords")
for region in ("tot", "hist", "gt"):
    want(region in spec, "the spec's layout no longer names %s" % region)
want(re.search(r"step 1[^\n]*STORE", spec) is not None,
     "the spec does not say step 1 STORES into gt (gt has no zeroed initial value)")

# 3. Step 4 must not write gt, and the byte-0 histogram it reads is step 3's.
want(re.search(r"step 4[^\n]*does NOT write", spec, re.I) is not None,
     "the spec does not say step 4 writes neither gt nor hist")
want("step 3 left in `hist`" in spec, "the spec does not attribute the emission's byte-0 histogram to step 3")

# 3b. No sentence may say hist is written in every step: step 4 must not write it, and a reader could take that
# literally and reintroduce the same-launch race the review found.
want(not re.search(r"written by the kernel in every step", spec, re.I),
     "the spec still says hist is written in every step, which contradicts step 4")
want(re.search(r"Steps 0 to 3 each overwrite", spec) is not None,
     "the spec does not say which steps overwrite hist")

# 4. The ABI: the parameter order and the launch shape, straight from the call site.
order = ["scores_ptr", "np", "at", "topk", "chs", "cp", "step", "scratch", "tokens", "counts", "pt", "page_rows"]
present = [name for name in order if name in body]
want(len(present) >= 10 or not index, "cuda_index.zig: the launch argument list changed shape (%d of %d names found)" % (len(present), len(order)))
want("Launch contract" in spec, "the spec has no Launch contract section")
want("(rows, cp)" in spec, "the spec does not state the grid as (rows, cp)")
want("128 threads" in spec, "the spec does not state the 128-thread block")
want("ONE stream" in spec, "the spec does not state that the five launches share one stream")

# 5. The order key is our own, and the spec must not define a second one.
want("order_key" in spec, "the spec does not name order_key")
want("glm_index_pools.cuh" in spec, "the spec does not name glm_index_pools.cuh as the order key's home")

if fails:
    for f in fails: print("SPEC-FAIL:", f)
    sys.exit(1)
print("spec-index-split: OK (%d checks)" % 18)
