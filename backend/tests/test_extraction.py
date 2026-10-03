"""
Regression tests for the invoice line-item extraction bugs found during
manual testing: once the header row was correctly detected (see
test_ingestion.py), trailing Tax/Total/Subtotal rows were being misread
as line items, inflating the reconciliation math.
"""
from app.pipeline import extraction


def test_invoice_line_items_extracted_correctly():
    tables = [{
        "sheet": "Invoice",
        "rows": [
            ["Description", "Qty", "Unit Price", "Amount"],
            ["Widget A", 10, 25.00, 250.00],
            ["Widget B", 5, 40.00, 200.00],
        ],
    }]
    result = extraction.extract_invoice("Vendor: Blue Ridge Supply Co.\nTotal: 450.00", tables)
    assert len(result["line_items"]) == 2
    assert result["line_items"][0]["description"] == "Widget A"
    assert result["line_items"][0]["amount"] == 250.00


def test_summary_rows_excluded_from_line_items():
    """Regression test: Tax/Total/Subtotal rows must not appear as line
    items, since they previously corrupted the reconciliation sum."""
    tables = [{
        "sheet": "Invoice",
        "rows": [
            ["Description", "Qty", "Unit Price", "Amount"],
            ["Widget A", 10, 25.00, 250.00],
            ["Tax:", "", "", 36.00],
            ["Total:", "", "", 286.00],
        ],
    }]
    result = extraction.extract_invoice("", tables)
    descriptions = [li["description"] for li in result["line_items"]]
    assert "Tax:" not in descriptions
    assert "Total:" not in descriptions
    assert len(result["line_items"]) == 1


def test_invoice_total_tax_due_date_vendor_regex():
    raw_text = (
        "Invoice Number: INV-2044\n"
        "Vendor: Blue Ridge Supply Co.\n"
        "Due Date: March 15, 2024\n"
        "Tax: 36.00\n"
        "Total: 999.00\n"
    )
    result = extraction.extract_invoice(raw_text, [])
    assert result["invoice_number"] == "INV-2044"
    assert result["vendor"] == "Blue Ridge Supply Co."
    assert result["total"] == 999.00
    assert result["tax"] == 36.00
    assert "March 15, 2024" in result["due_date"]


def test_contract_clause_extraction(sample_contract_text):
    result = extraction.extract_contract_or_nda(sample_contract_text)
    clauses = result["clauses"]
    assert clauses["payment_terms"]["days"] == 45
    assert clauses["termination"]["notice_days"] == 10
    assert "$50,000" in clauses["liability_cap"]["amounts"]
    assert clauses["confidentiality"]["period_years"] == 3
    assert result["missing_standard_clauses"] == []


def test_contract_missing_clauses_are_reported():
    text = "This is a short agreement with no standard clauses of any kind mentioned."
    result = extraction.extract_contract_or_nda(text)
    assert "payment_terms" in result["missing_standard_clauses"]
    assert "termination" in result["missing_standard_clauses"]


def test_financial_statement_metric_extraction():
    text = (
        "ANNUAL FINANCIAL STATEMENT\n"
        "For the year ended December 31, 2025\n"
        "Total Revenue: 2400000\n"
        "Net Income: 310000\n"
        "Total Assets: 1800000\n"
        "Total Liabilities: 2100000\n"
    )
    result = extraction.extract_financial_statement(text, [])
    assert result["metrics"]["revenue"] == 2400000
    assert result["metrics"]["net_income"] == 310000
    assert result["metrics"]["total_assets"] == 1800000
    assert result["metrics"]["total_liabilities"] == 2100000


def test_named_clause_inventory_includes_common_contract_sections():
    text = """Governing Law: Delaware. Arbitration applies. Seller shall indemnify Buyer.
    The parties shall maintain insurance. This agreement renews automatically for one year."""
    result = extraction.extract_contract_or_nda(text)
    assert {"governing_law", "dispute_resolution", "indemnification", "insurance", "renewal"}.issubset(set(result["named_clauses_detected"]))
