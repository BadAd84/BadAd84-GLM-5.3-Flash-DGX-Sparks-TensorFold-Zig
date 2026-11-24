---
name: curate-llm-classified-regression-fixtures
description: "Curate a trustworthy regression-fixture set (invoices/receipts/docs) from a harvested email/document corpus using dual-LLM classification + a verified golden master, without over-pruning. Use when building or repairing test fixtures from real financial/document corpora (e.g. ots-invoicing)."
---

# Curating LLM-classified regression fixtures from a corpus

Goal: turn a messy harvested corpus into a small, TRUSTWORTHY, correctly-labelled regression set, and a guard test that stops future rules silently rejecting known-good items.

## Hard-won rules (each cost a cycle)
1. **Never curate with a precision-tuned pipeline gate.** A classifier like `looks_like_invoice_text` (strict marker-phrase gate) is for pipeline precision, NOT fixture curation - terrible recall (collapsed 1060 fixtures to 20). Text-regex on extracted PDF text is unreliable: text layers are sparse/jumbled (only ~5% contained the word 'invoice').
2. **Never delete before validating + backing up.** `Path.unlink()` bypasses the Recycle Bin; if the source corpus is also gone, it's unrecoverable. ALWAYS copy the set to a scratch backup first, build the keep/drop list NON-destructively, get approval, then prune. (Also: watch filename collisions when copying a review subset with short-hash names - use a long hash, or you silently lose files.)
3. **The email/subject is a stronger signal than the attachment text - but it classifies the MESSAGE, not the ATTACHMENT.** One email carries many attachments (invoice + delivery note + CoC). Fuse: email subject + sender + attachment filename + PDF content. Join fixtures to the corpus index by sha256 (copies are byte-identical).
4. **Separate 'received' from 'sent'.** Harvests pull sent items; filter to external senders (own identity = internal X.500 DN with no '@', or own domain). The same attachment can appear sent AND received - dedup by hash, keep if ANY occurrence is external.
5. **Direction matters** (payable vs receivable): exclude the org's OWN outgoing invoices (often a distinct number series, e.g. INV-OTS-####) from an accounts-payable set; a text model guesses direction unreliably, so use a deterministic rule on the number series where one exists.
6. **Image-only PDFs need OCR, not vision**, when the downstream extractor is text-based - a vision model can label them but can't feed the text extractor.

## Workflow
1. Backup fixtures to scratch; build a non-destructive manifest (text_len, extracted_total, signals) per item.
2. Stage1: received-only + dedup(sha256) + exclude own-series + bucket by external sender + template-cluster (skeleton Jaccard) -> one representative per template.
3. Stage2: classify representatives with an LLM, direction-aware, fusing subject+sender+filename+content. Use local DSV4-Flash (spark1.ots-int.net:8888, OpenAI-compatible, response_format json_object, concurrency~16, resumable, checkpoint every 100) - it matched Opus 4.8 at 95.4%.
4. Cross-check two models: keep where they agree; if the owner declares one model authoritative, use its labels (union in its favour). Preserve disagreements (with PDFs) for human review BEFORE deleting the corpus.
5. Golden master totals: assert only where the text extractor AGREES with the LLM-read total (verified:true); otherwise total=null + record both + flag - never self-referential.
6. Materialize: clear old fixtures (backup exists), copy kept items, write expected.json WITH orig_filename per entry.
7. **Add a recall-guard test**: assert every known-good item survives the pipeline's ACTIVE-DROP filters (e.g. `looks_like_non_invoice(orig_filename)` + extension gate). Prove it's load-bearing (a too-broad hint must fail it). This catches mislabels (a statement Opus mis-kept) AND future over-broad rules.
8. Gitignore the fixture dir entirely if expected.json carries sensitive data (emails, totals).

## Eval/Windows notes
- Case-sensitivity: `os.listdir` returns real-case names; filter with `.lower().endswith('.pdf')` or you'll "miss" `.PDF` files.
- JSON dumps on Windows: write with `encoding='utf-8', ensure_ascii=False` (default cp1252 raises on non-latin chars).
- A Hidden file attribute (`attrib +H`, often from a copy) blocks the edit tool with EPERM - clear with `attrib -H`.
