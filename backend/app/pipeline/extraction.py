"""
Stage 2 (Section 2): entity and clause extraction.

Branches by document_type (set in Stage 1). Each branch is rule/regex
based, tuned to the vocabulary of that document type -- deliberately not
relying purely on a generic NER model, since clause *values* (a 45-day
notice period, a liability cap of $2M) are highly structured and regex
extracts them far more reliably than a general-purpose NER model would.
"""
import re

MONEY_RE = r"\$\s?[\d,]+(?:\.\d{2})?|\bUSD\s?[\d,]+(?:\.\d{2})?"
DAYS_RE = r"(\d{1,4})\s*(?:calendar\s+|business\s+)?days?"


def _find_clause_window(text: str, keywords: list[str], window: int = 400) -> str | None:
    """Returns a window of text starting at the keyword match, running
    forward. Deliberately does NOT look backward from the match: clause
    headings often sit close together in real documents (a termination
    clause a line or two after a payment-terms clause), and pulling in
    preceding characters risks bleeding a neighboring clause's numbers
    (e.g. "45 days" from Payment Terms) into this clause's extraction."""
    lower = text.lower()
    for kw in keywords:
        idx = lower.find(kw)
        if idx != -1:
            return text[idx:idx + window]
    return None


def _first_number(pattern: str, text: str):
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1) if m else None


NAMED_CLAUSE_PATTERNS = {
    "payment_terms": ["payment terms", "payment conditions", "shall pay", "invoice within"],
    "termination": ["termination", "terminate this agreement", "termination for convenience", "termination for cause"],
    "liability_cap": ["limitation of liability", "liability cap", "liable", "total liability"],
    "ip_assignment": ["intellectual property", "work product", "assignment of ip", "intellectual property rights"],
    "non_compete": ["non-compete", "noncompete", "restraint of trade", "non-solicitation", "nonsolicitation"],
    "confidentiality": ["confidentiality", "confidential information", "confidentiality period", "non-disclosure"],
    "governing_law": ["governing law", "laws of", "choice of law"],
    "dispute_resolution": ["dispute resolution", "arbitration", "mediation", "jurisdiction and venue"],
    "indemnification": ["indemnification", "indemnify", "hold harmless"],
    "insurance": ["insurance", "commercial general liability", "professional liability"],
    "force_majeure": ["force majeure", "act of god"],
    "assignment": ["assignment", "assign this agreement", "assign its rights"],
    "renewal": ["renewal", "automatic renewal", "renew automatically"],
    "warranty": ["warranty", "warranties", "warrants that"],
    "audit": ["audit rights", "right to audit", "inspection rights"],
}


def _extract_generic_clause_values(name: str, window: str) -> dict:
    values = {}
    days = _first_number(DAYS_RE, window)
    years = _first_number(r"(\d{1,2})\s*years?", window)
    amounts = re.findall(MONEY_RE, window)
    if days:
        values["days"] = int(days)
    if years:
        values["years"] = int(years)
    if amounts:
        values["amounts"] = amounts[:8]
    return values


def extract_contract_or_nda(raw_text: str) -> dict:
    clauses = {}

    for name, keywords in NAMED_CLAUSE_PATTERNS.items():
        window = _find_clause_window(raw_text, keywords)
        if not window:
            continue
        values = _extract_generic_clause_values(name, window)
        values["found"] = True
        values["excerpt"] = window.strip()
        clauses[name] = values

    # Preserve the existing specialised field names consumed by anomaly/risk
    # logic while also exposing richer generic values above.
    if "termination" in clauses:
        clauses["termination"]["notice_days"] = clauses["termination"].get("days")
    if "confidentiality" in clauses:
        clauses["confidentiality"]["period_days"] = clauses["confidentiality"].get("days")
        clauses["confidentiality"]["period_years"] = clauses["confidentiality"].get("years")

    required_clauses = ["payment_terms", "termination", "liability_cap", "confidentiality"]
    missing = [c for c in required_clauses if c not in clauses]

    return {
        "clauses": clauses,
        "named_clauses_detected": sorted(clauses.keys()),
        "missing_standard_clauses": missing,
    }


SUMMARY_ROW_LABELS = {"tax", "total", "subtotal", "sub-total", "shipping", "discount", "grand total"}


def extract_invoice(raw_text: str, tables: list[dict]) -> dict:
    line_items = []
    for table in tables:
        rows = table["rows"]
        if not rows:
            continue
        header = [str(c).strip().lower() for c in rows[0]]
        col_idx = {name: i for i, name in enumerate(header)}
        desc_col = next((col_idx[c] for c in col_idx if "desc" in c or "item" in c), None)
        qty_col = next((col_idx[c] for c in col_idx if "qty" in c or "quantity" in c), None)
        price_col = next((col_idx[c] for c in col_idx if "price" in c or "rate" in c or "unit" in c), None)
        amount_col = next((col_idx[c] for c in col_idx if "amount" in c or "total" in c), None)
        if desc_col is None and amount_col is None:
            continue
        for row in rows[1:]:
            if len(row) <= (desc_col or 0):
                continue
            desc_value = str(row[desc_col]).strip().lower().rstrip(":") if desc_col is not None and desc_col < len(row) else ""
            if desc_value in SUMMARY_ROW_LABELS:
                continue  # this is the invoice's own Tax/Total/Subtotal row, not a line item
            def parse_amount(v):
                if v is None:
                    return None
                v = re.sub(r"[^\d.\-]", "", str(v))
                try:
                    return float(v) if v else None
                except ValueError:
                    return None
            item = {
                "description": row[desc_col] if desc_col is not None and desc_col < len(row) else None,
                "quantity": parse_amount(row[qty_col]) if qty_col is not None and qty_col < len(row) else None,
                "unit_price": parse_amount(row[price_col]) if price_col is not None and price_col < len(row) else None,
                "amount": parse_amount(row[amount_col]) if amount_col is not None and amount_col < len(row) else None,
            }
            if item["description"] or item["amount"] is not None:
                line_items.append(item)

    total_match = re.search(r"total[:\s]*\$?\s?([\d,]+\.?\d*)", raw_text, re.IGNORECASE)
    tax_match = re.search(r"tax[:\s]*\$?\s?([\d,]+\.?\d*)", raw_text, re.IGNORECASE)
    due_date_match = re.search(r"due\s*date[:\s]*([A-Za-z0-9,/\- ]{6,25})", raw_text, re.IGNORECASE)
    vendor_match = re.search(r"(?:from|vendor|remit to)[:\s]*([A-Z][A-Za-z0-9&.,'\- ]{2,60})", raw_text, re.IGNORECASE)
    invoice_num_match = re.search(r"invoice\s*(?:#|no\.?|number)\s*[:\s]*([A-Za-z0-9\-]{3,20})", raw_text, re.IGNORECASE)

    # Explicit payment term in days, e.g. "Net 30" or "Payment terms: 45 days".
    # This is what Stage 5 needs to compare an invoice's stated term against
    # a related contract's payment_terms clause.
    payment_terms_days = None
    net_match = re.search(r"\bnet\s*(\d{1,3})\b", raw_text, re.IGNORECASE)
    if net_match:
        payment_terms_days = int(net_match.group(1))
    else:
        terms_match = re.search(r"payment\s*terms?[:\s]*(\d{1,3})\s*(?:calendar\s+|business\s+)?days?", raw_text, re.IGNORECASE)
        if terms_match:
            payment_terms_days = int(terms_match.group(1))

    def to_float(s):
        if not s:
            return None
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return None

    return {
        "line_items": line_items,
        "total": to_float(total_match.group(1)) if total_match else None,
        "tax": to_float(tax_match.group(1)) if tax_match else None,
        "due_date": due_date_match.group(1).strip() if due_date_match else None,
        "vendor": vendor_match.group(1).strip() if vendor_match else None,
        "invoice_number": invoice_num_match.group(1).strip() if invoice_num_match else None,
        "payment_terms_days": payment_terms_days,
    }


FINANCIAL_METRIC_PATTERNS = {
    # [:\s|]* handles both prose ("Revenue: $50,000") and the pipe-joined
    # cell rendering our XLSX ingestion produces ("Total Revenue | 50000").
    "revenue": r"(?:total\s+)?revenue[s]?[:\s|]*\$?\s?([\d,]+\.?\d*)",
    "net_income": r"net\s+income[:\s|]*\$?\s?\(?([\d,]+\.?\d*)\)?",
    "total_assets": r"total\s+assets[:\s|]*\$?\s?([\d,]+\.?\d*)",
    "total_liabilities": r"total\s+liabilities[:\s|]*\$?\s?([\d,]+\.?\d*)",
    "operating_expenses": r"operating\s+expenses[:\s|]*\$?\s?([\d,]+\.?\d*)",
    "gross_profit": r"gross\s+profit[:\s|]*\$?\s?([\d,]+\.?\d*)",
    "cash_flow": r"(?:net\s+)?cash\s+flow[:\s|]*\$?\s?\(?([\d,]+\.?\d*)\)?",
}


def extract_financial_statement(raw_text: str, tables: list[dict]) -> dict:
    metrics = {}
    for name, pattern in FINANCIAL_METRIC_PATTERNS.items():
        m = re.search(pattern, raw_text, re.IGNORECASE)
        if m:
            try:
                metrics[name] = float(m.group(1).replace(",", ""))
            except ValueError:
                pass

    period_match = re.search(
        r"(?:fiscal\s+year|period\s+ended|for\s+the\s+year\s+ended)[:\s]*([A-Za-z0-9,\- ]{6,30})",
        raw_text, re.IGNORECASE,
    )

    return {
        "metrics": metrics,
        "reporting_period": period_match.group(1).strip() if period_match else None,
        "source_tables_count": len(tables),
    }


def run_stage2(document_type: str, raw_text: str, tables: list[dict]) -> dict:
    if document_type in ("contract", "nda", "rfp"):
        return {"type": document_type, **extract_contract_or_nda(raw_text)}
    if document_type == "invoice":
        return {"type": "invoice", **extract_invoice(raw_text, tables)}
    if document_type == "financial_statement":
        return {"type": "financial_statement", **extract_financial_statement(raw_text, tables)}
    return {"type": "other", "note": "No structured extraction rules for this document type."}
