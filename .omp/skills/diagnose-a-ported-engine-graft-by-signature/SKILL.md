---
name: diagnose-a-ported-engine-graft-by-signature
description: "Match an engine port's runtime signature (token salad, PromptTooLong, FileNotFound, kernel-symbol NotFound) to its defect class and run the digest/knob gates"
---

# Diagnosing a ported engine graft by its signature

When a patch series grafts an older engine's code onto a pinned upstream, the same defect classes recur and each has a runtime signature. Name the signature first; it usually tells you the defect class in minutes.

| signature | defect class | measured instance |
|---|---|---|
| replies are token salad, all ranks healthy, prompt_tokens correct | a dropped compute call in the forward path | 0019's port deleted the `kda_block.fill(...)` line beside a replaced body call, so the KDA block never wrote its output; restoring the line fixed it |
| every chat kills the ensemble with `PromptTooLong`, `/v1/models` and idle fine | a dropped wire field in a step header | 0007's ported chunk step stopped setting `.depth` (start) and `.top_k` (prompt length), so the follower's prefill saw len=0 and its guard fired |
| build: `failed opening "fatbin_X": FileNotFound`; boot: `kernel symbol not in module: X` | the kernel or its fatbin catalog entry was never ported | catalog entries for glm_kda_chunk/onepass (0032), the router16 kernel block in glm_glue_bmm.cuh (0038) |
| boot requests a symbol only under a knob | a port dropped a type guard in a kernel-load loop | `@FieldType(Kernels, name) == cuda.Function` guard lost, so an optional `?cuda.Function` field (`router16`) was requested as `tf_glm_<field>` (0039) |

## Reading the errors precisely

- The message `kernel symbol not in module: X` prints the LITERAL string passed to the loader. A bare `tf_glm_router16` where the call sites use `_s3`/`_s4` proves a DIFFERENT requester than the one you are reading.
- If `strings` on the built binary shows no such literal at all, the name is built with string concatenation (`"tf_glm_" ++ name`) or formatting, so grep the source for the pieces, not the whole name.
- `strings` on the FATBIN (`/opt/tensorfold/fatbin/<image>.fatbin`) is the quickest way to confirm whether a kernel actually made it into the image.

## Instruments, in order

1. A chat reply is the correctness instrument: `/v1/models` answering and the stack idling clean proves nothing. Read the reply text every time. If the reply is empty, check finish_reason before blaming the engine (a thinking block can eat a tiny max_tokens).
2. Bisect arms: build pin + the first half of the patches, boot, ask the same prompt. Halve until one patch is implicated; make each arm include the minimum other patches it needs to compile.
3. Instrument the raise sites: add `std.log.err` prints of the guard's operands, then read them (values like `len=29 window_rows=8 capacity=262208` clear a suspect instantly). Remove the prints before cutting the patch.
4. A periodic or idle death: check who else can touch the box (a watchdog restarting a production serve is a classic; a stale flock holder from a finished campaign blocks builds and looks like a hung build whose log stops after its first line).

## Gates for any ported knob or patch

- Bit-exactness: bench at 1/2/4/6/8 streams with reply digests (a `streams.py <port> <P> --kind prose --max-tokens 400 --rounds 3` style instrument). Equal digests across arms = the same tokens; any differing digest is a numerics change and is NOT a gated win.
- Halving with `knob-digest.sh <image> <tag> "<env list>"`: boot P=1 with an explicit knob subset, run one cell, compare its digest to the stock digest. Halve until one knob is named (measured: of a 13-knob set only `TF_GLM_KDA_PAD` changed the bits, via the 4-bit pack path).
- Compile the full image per arm: repo gates like a host test suite can be green while the full build (fatbins, native, test binaries) still fails; the image build is the only gate that runs the whole graph.
- Contract-symbol scan: for every kernel name the runtime requests, check it exists as a substring in the kernel sources. Anything absent will boot straight into cuModuleGetFunction NOT_FOUND under the knob that requests it.
