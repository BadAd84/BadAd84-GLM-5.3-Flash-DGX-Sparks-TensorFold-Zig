# Report: LANE `host-once`, fork commit `ef81b4a49`

Three patches, cut, gated and verified. Everything the commit contains is ported; nothing is left out.

```
work/ports/host-once/01-memo-equal-strindex.patch      8875caedc86ef931  4 files,  7 hunks
work/ports/host-once/02-prompt-bench.patch             1c045c1d3c2a321a  4 files,  4 hunks
work/ports/host-once/03-render-once-host-once.patch    ca7b1314128adbf8 19 files, 49 hunks
```

## Per port

### 01 `01-memo-equal-strindex.patch`

Fork sha `ef81b4a49`. Files: `zig/build/cuda.zig`, `zig/src/core/template/access.zig`, `zig/src/core/template/template.zig`, `zig/src/core/tokenizer/memo.zig`.

- `memo.zig`: the fork's hunk **applied clean** (`git apply`), its lines unchanged, including the measured comment "indexOfDiff took 0.23 ms where mem.eql took 2.1 on 1.4 MB".
- `access.zig`: **hand-ported**. The fork's hunk is refused because `getitem`'s list arm reads `l.items.len` / `l.items[k]` there and `l.count()` / `l.at(k)` here. `strIndex` and its 2,000-case fuzz test are the fork's lines verbatim; only the `.str` arm's call site changed.
- Wiring, **mine**: the fuzz test needs a binary that runs it, so `template.zig`'s test block gains `_ = @import("access.zig")` and `zig/build/cuda.zig` puts the template module into the host-test module list (the fork's change to that line; our tree builds the module in `cuda_server_host.zig` and returns it, so the list is the only edit). Before this the chat template's own tests ran only in the macOS build.
- Gate: the template module ran 36 tests before and 37 after, all passing. Whole-gate result below.

### 02 `02-prompt-bench.patch`

Files: `build.zig`, `zig/build/server.zig`, `zig/src/server/root.zig`, `zig/tests/server/prompt_bench.zig` (new).

- `zig/build/server.zig`: **hand-ported**. The fork's `promptBench` builds the lanes / engine_api / tokenizer / template modules itself; our tree has `plain`, which builds that set plus `core` (our server root needs it) and runs `addTo` and `testImports`. Step name, description and executable are the fork's.
- `prompt_bench.zig`: the fork's file with the eight new-path rows removed, because they call `Rendered.keep`, `Rendered.pieces` and `messages.toolArgumentsWith`, none of which exist before 03. Patch 03 restores the fork's eighteen rows. The helper `render`, the local `problem` and the local `user_at` went with them. Two site labels lost the fork's chat.zig line numbers (`(chat 154)`, `(chat 177)`; 163 and 186 here) and read `(chat.zig)`.
- `root.zig`: the fork's four exports. `prompt`, `chat`, `openai` are what the bench imports at this point; `messages` is used by the rows 03 restores.
- Gate: builds and runs; `zig build prompt-bench` rc=0.

### 03 `03-render-once-host-once.patch`

Files touched (19): `zig/build/cuda_server_host.zig`, `core/template/{eval,template}.zig` + new `generation.zig`, `generation_test.zig`, `watch.zig`, `core/tokenizer/tokenizer.zig` + new `kept.zig`, `kept_test.zig`, `server/{hf_text,messages,model_text,prompt,root,server}.zig` + new `hf_text_kept.zig`, `prompt_once_test.zig`, `fixtures/glm53/chat_template.jinja`, and `zig/tests/server/prompt_bench.zig`.

Applied clean from the fork (its own lines, `git apply`): `generation.zig`, `generation_test.zig`, `watch.zig`, `kept.zig`, `kept_test.zig`, `prompt_once_test.zig`, `fixtures/glm53/chat_template.jinja`, `hf_text.zig`, `messages.zig`, `server.zig`.

Hand-ported, and exactly what changed:

- **`prompt.zig`** is the big one. The pin's `renderIds` is a thin call to `renderRequest`, which carries a Kimi bypass, a native-DeepSeek bypass, `tool_choice` / `response_format` / `images` options, MiniMax-M3's own closing token, the `templateClosed` test and the explicit-thinking-off refusal. None of that exists in the fork's base. The fork's `Once` / `Probe` / `rendered` / `closer` / `failed` are ported onto it: `renderText` returns the `model_text.Rendered` (the pin's private `render` and `RenderedIds` go, since both the old path and `Once` want the render itself), `closer` returns the one id a thinking-off generation prompt ends with and carries both of the pin's cases in the pin's order, and `offRefusal` is the pin's refusal lifted out so the prompt render inside `Once` runs it too. `Once.prompt` therefore takes a `require_off` the fork's version has no notion of. `renderText` is the fork's `rendered`, renamed: the pin's `templateClosed` takes a parameter called `rendered` and Zig refuses the shadow. Every probe's scratch `Cx` still carries `cx.template_fields`.
- **`model_text.zig`**: `Rendered.keep` also falls back to a whole `encode` when the render carries Kimi release segments. Our `Rendered` has a `segments` field the fork's has not, and with segments present `encode` is a sequence of per-segment encodes rather than `encodeMasked(text, spans)`, so a kept state over it would be wrong. The fallback leaves `state` null, which is what makes `pieces` and `prefixPieces` take their own null-state paths.
- **`hf_text_kept.zig` is mine**: the fork's `keepFn`, `piecesFn`, `prefixFn` and `masked` sit inside `hf_text.zig`, which is 600 lines here and would be 626 with them, over the lean limit. Same bodies, tokenizer reached through one helper, `hf_text.zig`'s vtable points straight at them. `hf_text.zig` ends at 597 lines.
- **`cuda_server_host.zig`**: the fork registers `test-prompt-once-host` in `zig/build/cuda.zig`; here the server host steps live in `cuda_server_host.zig`, where `server_tests`, `mods.tokenizer` and `template` are all in scope. Step unchanged otherwise.
- **`tokenizer.zig`**: the fork's split of `encodeMaskedCounted` into `checkSpans` + `encodeSegments` + `segments`, its lines, onto a file whose `Segment` declaration had no doc comment. The unmasked `splitAdded` path is untouched.
- **`prompt_bench.zig`**: the eight rows back, the fork's; its `render` helper passes our `srv.media()` where the fork writes `.of(srv.info.vision)`.

The fork's own equality tests all came with it and all run under `test-cuda-host`: `kept_test` (4), `generation_test` (2), `prompt_once_test` (3), plus the fork's `test-prompt-once-host` step which runs the three sets alone (`rc=0`, 22/22).

## Gates

| step | baseline `fix6` | `host-once` |
|---|---|---|
| `zig build check-native-cuda-host` | rc=0 | **rc=0**, 7/7 steps |
| `zig build test-cuda-host` | rc=1, 5553/5606 passed, **26 failing names** | rc=1, 5601/5654 passed, **26 failing names** |
| `zig fmt --check zig/` | rc=0 | **rc=0** |
| `zig build compile-cuda-tests` | not in baseline | **rc=0**, 10/10 steps |
| lean base vs head | base `work/f5/tree`: 5991 files, 127 problems | head: 5999 files, 127 problems, **0 new** (`lean_new.py` rc=0) |

`scripts/gate-names.sh fix6 host-once` prints `only host-once fails: none` / `only fix6 fails: none`, rc=0. The 26 are the baseline's file-permission / symlink / FIFO set. Test count rose by 48, all passing: the template module's own suite entering the gate (patch 01's wiring) plus the nine new tests.

Not compiled by any host gate, so read twice and stated plainly: nothing in this port touches `.cu`/`.cuh`. `zig/tests/cuda` is untouched too, and `compile-cuda-tests` compiles it anyway (rc=0).

## Verify tree

`scripts/arm-tree.sh 42 work/ports/host-once-verify`, then `git apply` of `01`, `02`, `03` in order: all three applied, and `diff -rq --exclude=.git --exclude=.zig-cache --exclude=zig-out` against the lane tree gives **0 differing paths**. Verify tree deleted.

## Bench, before and after

No GLM-5.3 checkpoint is on this machine. What is: `models--zai-org--GLM-4.6`'s `tokenizer.json` (151,329 vocab, 36 added tokens, which include every word the GLM-5.3 template writes: `<|user|>`, `<|assistant|>`, `<think>`, `</think>`, `<|observation|>`, `<|system|>`, `<tool_response>`, `<arg_key>`, `[gMASK]`, `<sop>`, `<tool_call>` and the rest), and the GLM-5.3 `chat_template.jinja` this very commit adds as a server fixture. The bench model directory is that pair. Prompt texts are not the parity probe's (`c0.txt` and friends are not in this repo or on this box): they are this tree's own zig sources, fixed order, sized so the two agent turns land near 215k and 637k ids. The two arms are separate trees (`b2` = 42 + 01 + 02, lane tree = 42 + 01 + 02 + 03), ReleaseFast, 5 rounds, run back to back on an idle machine.

BEFORE, verbatim (`bench/pair-before-glm.txt`):

```
r2: 223956 prompt ids, digest 394b7eb0150d713e, history 223953, rewind 208164, user_end 223953
cold boot: body to chat.prepare        91.08
first warm turn: chat.prepare           8.11
site                                  median       min (5 rounds)
parse body                              0.79      0.76
plan (openai.chatInput)                 0.01      0.01
chat.prepare                            3.54      3.31
  prompt.prepare                        3.05      2.88
  systemPrefixLen (chat.zig)            0.03      0.03
  replySpans (chat.zig)                 0.16      0.14
old: renderIds prompt                   0.56      0.51
old: renderIds history                  0.54      0.47
old: renderIds continued probe          1.36      1.29
old: rewindLen (full encode)            0.56      0.54

r2m (masked): 224381 prompt ids, digest 559d3280b4462284, history 224378, rewind 208164, user_end 224378
cold boot: body to chat.prepare        78.74
first warm turn: chat.prepare           7.51
site                                  median       min (5 rounds)
parse body                              0.79      0.77
plan (openai.chatInput)                 0.01      0.01
chat.prepare                            4.03      3.40
  prompt.prepare                        3.04      2.98
  systemPrefixLen (chat.zig)            0.04      0.03
  replySpans (chat.zig)                 0.15      0.14
old: renderIds prompt                   0.56      0.52
old: renderIds history                  0.56      0.50
old: renderIds continued probe          1.37      1.29
old: rewindLen (full encode)            0.61      0.57

agent ~200k, ends on a tool result: 215115 prompt ids, digest 4b75930d2cfbd710, history 215112, rewind 171, user_end 0
cold boot: body to chat.prepare        81.16
first warm turn: chat.prepare          20.68
site                                  median       min (5 rounds)
parse body                              1.04      0.82
plan (openai.chatInput)                 0.08      0.06
chat.prepare                           20.72     19.53
  prompt.prepare                       20.04     19.58
  systemPrefixLen (chat.zig)            0.13      0.13
  replySpans (chat.zig)                 0.09      0.08
old: renderIds prompt                   4.63      4.31
old: renderIds history                  4.46      4.42
old: renderIds continued probe          5.95      5.61
old: rewindLen (full encode)            5.24      4.61

agent ~650k, ends on a tool result: 636930 prompt ids, digest 2beacc0a2dddbe64, history 636927, rewind 171, user_end 0
cold boot: body to chat.prepare       300.68
first warm turn: chat.prepare          72.25
site                                  median       min (5 rounds)
parse body                              2.48      2.43
plan (openai.chatInput)                 0.22      0.18
chat.prepare                           63.35     60.14
  prompt.prepare                       67.41     66.48
  systemPrefixLen (chat.zig)            0.20      0.17
  replySpans (chat.zig)                 0.22      0.18
old: renderIds prompt                  18.64     18.06
old: renderIds history                 16.90     16.57
old: renderIds continued probe         20.92     20.68
old: rewindLen (full encode)           18.25     17.75
```

AFTER, verbatim (`bench/pair-after-glm.txt`):

```
r2: 223956 prompt ids, digest 394b7eb0150d713e, history 223953, rewind 208164, user_end 223953
cold boot: body to chat.prepare       105.60
first warm turn: chat.prepare           7.50
site                                  median       min (5 rounds)
parse body                              0.81      0.77
plan (openai.chatInput)                 0.01      0.01
chat.prepare                            1.31      1.28
  prompt.prepare                        1.03      0.87
  systemPrefixLen (chat.zig)            0.04      0.02
  replySpans (chat.zig)                 0.14      0.13
  render prompt                         0.09      0.08
  keep prompt                           0.41      0.37
  render history probe                  0.10      0.09
  pieces history probe                  0.19      0.18
  render continued probe                0.00      0.00
  pieces continued probe                0.00      0.00
  render rewind probe                   0.09      0.07
  pieces rewind probe                   0.17      0.17
old: renderIds prompt                   0.50      0.48
old: renderIds history                  0.51      0.46
old: renderIds continued probe          1.36      1.31
old: rewindLen (full encode)            0.57      0.52

r2m (masked): 224381 prompt ids, digest 559d3280b4462284, history 224378, rewind 208164, user_end 224378
cold boot: body to chat.prepare        84.84
first warm turn: chat.prepare           8.69
site                                  median       min (5 rounds)
parse body                              0.78      0.77
plan (openai.chatInput)                 0.01      0.01
chat.prepare                            1.33      1.25
  prompt.prepare                        0.91      0.88
  systemPrefixLen (chat.zig)            0.02      0.02
  replySpans (chat.zig)                 0.14      0.13
  render prompt                         0.09      0.08
  keep prompt                           0.42      0.37
  render history probe                  0.13      0.11
  pieces history probe                  0.20      0.18
  render continued probe                0.00      0.00
  pieces continued probe                0.00      0.00
  render rewind probe                   0.10      0.08
  pieces rewind probe                   0.18      0.17
old: renderIds prompt                   0.54      0.51
old: renderIds history                  0.49      0.47
old: renderIds continued probe          1.34      1.28
old: rewindLen (full encode)            0.54      0.53

agent ~200k, ends on a tool result: 215115 prompt ids, digest 4b75930d2cfbd710, history 215112, rewind 171, user_end 0
cold boot: body to chat.prepare        77.43
first warm turn: chat.prepare          11.85
site                                  median       min (5 rounds)
parse body                              0.85      0.82
plan (openai.chatInput)                 0.06      0.05
chat.prepare                           11.57     11.25
  prompt.prepare                       11.38     10.45
  systemPrefixLen (chat.zig)            0.15      0.12
  replySpans (chat.zig)                 0.10      0.08
  render prompt                         2.57      2.39
  keep prompt                           1.84      1.79
  render history probe                  2.67      2.38
  pieces history probe                  0.44      0.43
  render continued probe                2.44      2.34
  pieces continued probe                0.47      0.45
  render rewind probe                   2.52      2.43
  pieces rewind probe                   0.69      0.67
old: renderIds prompt                   4.65      4.09
old: renderIds history                  4.57      4.20
old: renderIds continued probe          5.78      5.56
old: rewindLen (full encode)            4.77      4.41

agent ~650k, ends on a tool result: 636930 prompt ids, digest 2beacc0a2dddbe64, history 636927, rewind 171, user_end 0
cold boot: body to chat.prepare       293.94
first warm turn: chat.prepare          38.83
site                                  median       min (5 rounds)
parse body                              2.48      2.40
plan (openai.chatInput)                 0.22      0.19
chat.prepare                           35.89     35.82
  prompt.prepare                       35.72     35.61
  systemPrefixLen (chat.zig)            0.15      0.14
  replySpans (chat.zig)                 0.18      0.18
  render prompt                         8.54      8.25
  keep prompt                           5.25      5.16
  render history probe                  8.44      8.21
  pieces history probe                  1.57      1.56
  render continued probe                8.71      8.52
  pieces continued probe                1.64      1.60
  render rewind probe                   8.52      8.29
  pieces rewind probe                   2.10      2.06
old: renderIds prompt                  15.86     15.51
old: renderIds history                 16.52     16.17
old: renderIds continued probe         20.34     20.28
old: rewindLen (full encode)           16.55     16.42
```

Median `chat.prepare`: 3.54 -> 1.31, 4.03 -> 1.33, 20.72 -> 11.57, 63.35 -> 35.89 ms. Prompt digest and all three marks identical in every case, which the bench asserts itself each round (`IdsDiffer`, `MarksDiffer`). A second configuration, DeepSeek-V3.2's self-consistent tokenizer and template (where the template writes none of that tokenizer's added tokens, so only the history mark and the memo help): r2 at 240,781 ids reads 387.33 -> 144.74 ms, same digest.

Note these are my corpus and my tokenizer pair, not the fork's 91 -> 41 ms at 650k. The shape agrees; the numbers are not the fork's and are not comparable to them.

## Doubts, stated plainly

1. **`Once.prompt`'s refusal ordering.** The pin refuses an explicit thinking-off request that the template cannot express. In `Once.prompt` that refusal now happens after `keep` has run, where the pin refused right after the encode. Same inputs, same verdict, wasted work on the refusal path only. I am confident, but it is a reordering I introduced rather than took.
2. **The MiniMax-M3 arm of `closer` has no test here.** `prompt_once_test` drives a GLM-shaped template. The pin's own `test "thinking request: ..."` covers `templateClosed`, not the `</mm:think>` append. I preserved the pin's branch order exactly (mm marker first, `tokenId` null falls through to `<think>`), and the refusal is skipped whenever a close id exists, which is what the pin's early return did. A MiniMax serve is the only place this is exercised.
3. **The DeepSeek bench arm refuses its two agent cases** (`error: Refused`) before and after, identically. It is that template refusing the bench's synthetic tool conversation, not a regression; I did not chase the message because the arm is only a second data point.
4. **The `args` memo is keyed on `*const json.Object`.** Correct only because every message object a request touches is allocated from the request arena and never freed, so a pointer cannot be reused for a different message within a request. That is the fork's design and it holds here, but it is a property of the allocator, not of the code.
5. **`history 0` would silently disable the history-mark path.** On a tokenizer whose added tokens the template does not write, BPE merges across the `<|assistant|>` boundary and the history render stops being a prefix of the prompt; our GLM pair does not have that problem (`history 223953`), and the first bench model I tried did. Worth knowing before reading any future bench on a mismatched pair.

## What each patch needs from a GPU run

- **01**: nothing for correctness. Host-side, input-identical, proven by the tokenizer and template host tests.
- **02**: nothing. `prompt-bench` is a host tool in no default step, no gate and no serve image; it builds only when named.
- **03**: the host saving is measured above and needs no GPU. A serve has to show that nothing moved underneath it: the same reply digests as the stack through 0042 at 1 / 2 / 4 / 6 / 8 streams with every knob off, the same again with `TF_GLM_OVN_HOST_ONCE=1`, and a long agent turn (the 650k shape, ending on a tool result, which is the only path where the rewind probe's early stop fires) returning the pin's digest with the knob both ways. Because `history_len`, `rewind_len` and `user_end` decide prompt-cache reuse, the run should also confirm a resumed conversation still restores what it restored before, read from the serve's own restore line rather than from the three numbers alone.