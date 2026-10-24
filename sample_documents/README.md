# Test document set

One example of every supported input path, with planted issues so each
pipeline stage has something to find. Regenerate with
`python sample_documents/generate_samples.py`.

| File | Format path | Expected type | Planted issues (Stage 3) |
|---|---|---|---|
| `01_contract_acme_msa.pdf` | Digital PDF (headings preserved) | contract | 10-day termination notice (warning); $50,000 vs $1,000,000 liability caps (critical asymmetry); payment terms 30 days |
| `02_invoice_acme_inv1001.docx` | DOCX with table | invoice | Duplicate "Warehouse handling" line item; **Net 60** |
| `03_invoice_acme_inv1002.xlsx` | XLSX: `Cover` metadata sheet skipped, `LineItems` data sheet parsed below a metadata preamble | invoice | Due date 2025-03-01 already past; Net 30 |
| `04_financial_statement_fy2025.pdf` | Digital PDF, comparative FY2025/FY2024 columns | financial_statement | Liabilities exceed assets; debt-to-assets out of range; YoY changes > 35% (revenue, liabilities, gross profit) |
| `05_nda_scanned.pdf` | Image-only PDF, 1.8° skew → OCR + deskew | nda | 2-year confidentiality; no payment/liability clause (informational) |
| `06_invoice_acme_inv1003_photo.jpg` | JPG → OCR | invoice | Clean scan, should pass the confidence threshold |
| `07_rfp_freight.png` | PNG → OCR | rfp | 45-day payment terms |
| `08_low_quality_scan.jpg` | JPG, blurred, noisy, 4° skew | — | Should trip the low-quality OCR warning |

## Cross-document contradictions (Stage 5)

Upload files 01–04 into one project. Three contradictions are expected:

1. **Contract vs invoice payment term**: the contract says 30 days, INV-1001 says Net 60 (shared party: Acme Supplies Inc.).
2. **Invoice vs invoice payment term**: INV-1001 says Net 60, INV-1002 says Net 30 for the same vendor.
3. **Revenue vs invoice totals**: the financial statement reports revenue of 1,250,000, but the invoices in the project add up to about 11,700.

Files 01–04 were checked through Stages 0–5 with the real `en_core_web_sm`
model, and all of the above fired. Files 05–08 go through Tesseract, so
run them in the Docker image, which includes Tesseract.
