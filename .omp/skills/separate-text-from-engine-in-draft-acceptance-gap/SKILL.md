---
name: separate-text-from-engine-in-draft-acceptance-gap
description: "Two engines or arms differ in tokens a round or tok/s on speculative decoding: tell text luck from drafter, cut rule, copies or round time."
---

# Separate text from engine in a draft-acceptance or decode gap

Use when two serves of the same checkpoint (or two arms) differ by a few percent in tok/s or tokens a round and each writes its own reply text. A handful of bench prompts cannot decide it: tokens kept a round depend on the reply.

Tools that implement this (repo GLM-5.3-Flash-DGX-Sparks-TensorFold-Zig, `scripts/`): `per_prompt.py` (step 1), `per_prompt_table.py` (step 2), `make_prompt_ids.py` and `prompts24.json` (the 24-prompt set as ids), `forced-arm.sh`, `teacher_forced.py`, `forced_score.py`, `chain_log.py` (step 6), `live_vs_forced.py` (step 7).

## Order of work (each step is cheap and closes one explanation)

1. **One request at a time, many prompts.** Send each prompt alone (greedy, fixed max tokens, the SAME token ids to both engines via /v1/completions) and difference the serve's draft counters around the request, so a row is one reply's rounds, drafted, accepted, span. Use 20+ prompts of mixed kinds (prose, code, JSON, shell, arithmetic). Check determinism with two reps. Only load a live serve while it is idle.
2. **Pair by prompt and bootstrap.** Per-prompt ratios of tokens a round, ms a round and tok/s; geometric mean with a bootstrap interval over prompts; count how many prompts favour each side. Prove the analysis on a fixture with a planted difference first. Split by kind (prose-like vs code-like by drafted a round): a deficit confined to one kind has a mechanism.
3. **Round time controlled for draft length.** Fit ms a round = a + b x drafted a round over the prompts for each engine; compare intercepts (fixed cost) and slopes. A raw ms-a-round ratio is confounded by how much each engine drafts.
4. **Solo sum against concurrency.** Sum each engine's solo rounds for the prompts a concurrent wave uses and compare with the wave's rounds. Equal: rounds are a property of the reply. More rounds with byte-identical replies: the engine drafts differently under load (shared-window allocation).
5. **Two arms that draft very differently give the round's real price.** An arm that verifies every draft against the default gives two points per stream count: fit fixed ms + ms a draft row, then compute what any other drafting policy would cost before building it.
6. **Teacher-force on the other engine's reply.** For each position, prompt + the first p tokens of the other engine's reply, log the drafter's picks: reach by depth and rounds if every correct draft were kept, beside the other engine's live rounds. Equal: the drafter's picks are not behind. Reproduce an earlier control exactly before trusting new texts.
7. **Live against forced on the engine's OWN reply.** A forced run only sees the first round after a prompt pass. Log one unforced run and force the same text: identical first picks and chains mean mid-stream drafting equals after-prompt drafting, so forced numbers describe the live drafter.
8. **Read the live log round by round.** Per round: the chain's correct lead L and what was kept K. Cuts before the first miss (K < L) that cluster on one kept count are structural, not confidence. Cross-tabulate cut rounds against a candidate trigger computed from the tokens (for example: do the last 8 tokens occur earlier in the context?) and predict K from the mechanism; an exact prediction confirms it. On GLM-5.3-Flash it was the lanes core's default context copies (a 4-row first copy window) replacing a correct DFlash2 chain; switching them off measured +3.6% on code-like prompts.

## Traps met

- A request's first decode round can be narrower than later ones (depth from a prior): first-round kept counts are a floor, never the live rule.
- A knob that changes reply digests changes numerics; its tok/s belongs to another text.
- A switch's metadata class (a registry's 'arithmetic' or 'numerics' label) is not a measurement: compare reply digests with and without it before excluding it as numerics-changing.
- Two reps of one prompt can give the same reply text with rounds differing by one or two (a depth rule that prices depths by measured round times lets timing move a round): treat a per-prompt difference of 1-2 rounds as noise and read effects over the whole set.
- A mechanism that looks wasteful (a trim, a cut rule) can still be near its optimum: removing it wholesale (verify every draft) lost 21-31% on GLM; price the alternative with step 5 first.
- Boot-to-boot spread of 1 to 3% hides a 1% effect: use alternating pairs (4 or more) and read each arm beside its adjacent control, not against a pooled mean when controls drift.
- Equal reply digests are a served check, not a byte-level kernel check.
- Verify a prefilter or guard on a REAL saved output of the tool it parses, not a hand-written fixture.
