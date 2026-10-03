"""
Stage 5 (Section 2): cross-document contradiction detection.

Runs at the project level (only meaningful with >1 document). Compares
extracted fields across every pair of documents in the project and flags
mismatches: e.g. a contract's payment_terms.days vs an invoice's explicit
payment term ("Net 30"), or a financial statement's revenue vs the sum of
invoice totals in the project.

Returns a list of dicts matching the Contradiction model shape.
"""


def _normalise_party(value: str) -> str:
    import re
    value = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
    stop = {"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co", "company", "the"}
    return " ".join(token for token in value.split() if token not in stop)


def _party_set(document: dict) -> set[str]:
    entities = document.get("extracted_entities") or {}
    values = list(document.get("primary_parties") or [])
    vendor = entities.get("vendor")
    if vendor:
        values.append(vendor)
    result = set()
    for value in values:
        norm = _normalise_party(value)
        if norm:
            result.add(norm)
            # Also keep distinctive tokens for cases like "Acme Manufacturing"
            # vs "Acme Manufacturing Inc.".
            result.update(t for t in norm.split() if len(t) >= 4)
    return result


def _shares_party(a: dict, b: dict) -> bool:
    pa, pb = _party_set(a), _party_set(b)
    return bool(pa and pb and pa & pb)


def find_contradictions(documents: list[dict]) -> list[dict]:
    """
    `documents` is a list of dicts: {id, document_type, extracted_entities,
    primary_parties}
    """
    contradictions = []

    invoices = [d for d in documents if d["document_type"] == "invoice"]
    statements = [d for d in documents if d["document_type"] == "financial_statement"]

    # Financial statement revenue vs sum of invoice totals in project
    for statement in statements:
        revenue = (statement["extracted_entities"].get("metrics", {}) or {}).get("revenue")
        if revenue is None or not invoices:
            continue
        invoice_sum = sum(
            (inv["extracted_entities"].get("total") or 0) for inv in invoices
        )
        if invoice_sum <= 0:
            continue
        diff_pct = abs(revenue - invoice_sum) / max(revenue, invoice_sum) * 100
        if diff_pct > 15:
            contradictions.append({
                "document_a_id": statement["id"],
                "document_b_id": invoices[0]["id"],
                "field": "revenue_vs_invoice_total",
                "value_a": f"{revenue:,.2f}",
                "value_b": f"{invoice_sum:,.2f}",
                "explanation": (
                    f"The financial statement reports revenue of {revenue:,.2f}, but the sum of "
                    f"invoice totals in this project is {invoice_sum:,.2f} -- a {diff_pct:.1f}% "
                    "difference, which may indicate missing invoices, unrecorded revenue, or a "
                    "reporting-period mismatch."
                ),
            })

    # Payment-term day mismatches between any two documents that share a
    # party and each explicitly state a numeric payment term -- this is
    # what catches the spec's core example: a contract's 30-day payment
    # clause vs. an invoice stating "Net 60" for the same counterparty.
    numeric_term_docs = []
    for d in documents:
        entities = d["extracted_entities"]
        days = None
        if d["document_type"] == "contract":
            days = (entities.get("clauses", {}) or {}).get("payment_terms", {}).get("days")
        elif d["document_type"] == "invoice":
            days = entities.get("payment_terms_days")
        if days is not None:
            numeric_term_docs.append((d, days))

    for i in range(len(numeric_term_docs)):
        for j in range(i + 1, len(numeric_term_docs)):
            doc_a, days_a = numeric_term_docs[i]
            doc_b, days_b = numeric_term_docs[j]
            if not _shares_party(doc_a, doc_b):
                continue  # only compare documents that share a counterparty/vendor
            if days_a != days_b:
                contradictions.append({
                    "document_a_id": doc_a["id"],
                    "document_b_id": doc_b["id"],
                    "field": "payment_terms_days",
                    "value_a": f"{days_a} days",
                    "value_b": f"{days_b} days",
                    "explanation": (
                        f"Document {doc_a['id'][:8]} specifies a payment term of {days_a} days while "
                        f"document {doc_b['id'][:8]}, which shares a named party, specifies "
                        f"{days_b} days for the same relationship."
                    ),
                })

    return contradictions
