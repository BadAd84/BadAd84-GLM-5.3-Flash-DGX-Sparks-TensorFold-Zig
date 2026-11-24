---
name: extend-ots-invoicing-xero-touch-bills
description: "Use when building/extending ots-invoicing Xero touch bill-creation (itemisation, matching, filing); not for reconcile-only or scraper work."
---

# Extending the ots-invoicing Xero touch bill-creation pipeline

The "Dext replacement": create populated Xero DRAFT bills from invoices via the reverse-engineered
Xero mobile (touch) API, device-free. This skill is the workflow + the traps hit building it.

## Architecture (where things live)
- `scrapers/xero_touch.py` - `XeroTouchClient` (headless login mints token from stored creds;
  plain Bearer, no DPoP), `create_bill_from_draft` (resolve contact/account -> POST /apiv2/v2/bill
  -> attach PDF), `create_contact` (needs a CLIENT-minted uppercase GUID `id` or Xero 400s "Id can
  not be empty"), `upload_attachment`+`associate_file` (Files/File/Upload then AssociateWithObject
  {fileIds:[...],objectId,associateWithType}).
- `bill_draft.py` - `extract_bill_draft(pdf, settings=)` -> BillDraft; `build_bill_payload` (emits
  itemised net lines when `draft.line_items`, else single line).
- `line_items.py` - LLM itemisation via local GLM (spark1:8888, owned hardware); self-grades.
- `review.py` - `_create_xero_bill` (orchestrates), `approve`, `_find_sum_group`, `_autofile_credit_terms`,
  `file_inbox_item`. All three filing paths route through `_create_xero_bill` when `file_bills_via_touch`.
- `config.py` - flags: `file_bills_via_touch` ([xero_touch] file_bills), `extract_line_items`
  ([line_items] enabled), `reconcile_source` ([reconcile] source), `xero_touch_org_id`.

## Wire format (all LIVE-captured; docs/re-xero-touch-api.md)
Every enum is DOMAIN-PREFIXED: status INVOICESTATUS/DRAFT|AUTHORISED|DELETED, invoiceType
INVOICETYPE/ACCPAY|ACCPAYCREDIT, gstType TAX/INCLUSIVE|EXCLUSIVE|NONE, currency CURR/GBP, line
gstCode GST/INPUT2. Path lowercase /apiv2/v2/bill. Dates midnight-UTC ISO (2026-10-05T00:00:00Z).
Amounts JSON numbers. Delete a bill = re-POST /v2/bill with id + status INVOICESTATUS/DELETED + a
valid body (contactId, lineItems). Bills NOT readable via Invoices/GetInvoice (403, that's sales
invoices); read drafts via Dashboard/GetBillSummary, list via SourceDocuments/GetAll?type=INVOICETYPE/ACCPAY.

## Hard-won traps
- MIXED-RATE VAT: an itemised tax-EXCLUSIVE bill applies ONE rate to all lines, so an invoice with
  mixed rates (some 20%, some zero-rated) totals WRONG (cef: 66.20 net -> 79.44 not 69.14). Only
  itemise when a UNIFORM rate reproduces the exact total: net*1.2==total ("standard", EXCLUSIVE 20%)
  or net==total ("zero", gstType NONE). Mixed -> flag for review + single-line fallback.
- Reconcile-or-review safety: a bad extraction must become a review item, never a wrong bill. Guard on
  sanity (<=50 items, no negatives) AND total reconcile.
- pdfplumber (pdf_text_layout), NOT pypdf, for extraction - pypdf mangles ~1/3 of invoices
  (vertical/run-together text).
- Courier labels: Interparcel sends Receipt + Label + Address Label (+ Customs Invoice) per order;
  filter "label" as a WHOLE WORD (not when doc also says invoice/receipt) + "customs invoice".
- Sum-group (Biffa): 2+ invoices on one email summing to one charge. pick_attachment takes only ONE
  per email - use _find_sum_group to emit all, file as SEPARATE bills each at its own total.

## Validate live BEFORE trusting (never hammer the API)
1. Mint a token from the container: docker exec invoicing-web-1 python - <<'EOF' calling
   xero_touch.access_token(store, store_path=..., allow_login=True); print it.
2. Target the owner-authorised Retro Gamer Stuff org (9ee5cd04-7468-440a-9ece-4d00e08053c1), NEVER OTS
   (3fd82dda-...). Assert org != OTS in the script.
3. Create as DRAFT, read back via Dashboard/GetBillSummary (expect count/total), then DELETE. One
   create+delete cycle per thing validated - not a loop.

## Deploy
Push to main -> Gitea CI ~9 min builds the image. Then on CT108:
`docker pull 10.20.0.107:3000/ots/ots-invoicing:latest && cd /opt/invoicing && docker compose up -d
--force-recreate`. Verify flags: `python -c "from ots_invoicing.config import load_settings;..."`.
Rapid successive pushes get CI-cancelled and NOT re-queued - push once, or an empty commit re-triggers.
GPG-sign commits; commit messages via `git commit -F <winpath>` (backticks/`-` in msg + CRLF traps).

## Corpus / oracle
300 real invoice fixtures in tests/fixtures/invoices/ (GITIGNORED, local-only, no git backup);
expected.json has 241 verified totals = a free grading oracle (extracted lines +VAT must == total).
Run extraction concurrently (4 workers = the serve's streams) to measure coverage.
