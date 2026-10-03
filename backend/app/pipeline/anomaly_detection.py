"""
Stage 3 (Section 2): anomaly detection.

Returns a list of anomaly dicts: {severity, category, explanation, evidence}
severity in {"critical", "warning", "informational"}.
"""
from dateutil import parser as dateparser
from app.utils import utcnow
from app.config import settings


def _mk(severity, category, explanation, evidence=None):
    return {"severity": severity, "category": category, "explanation": explanation, "evidence": evidence or {}}


def detect_contract_anomalies(extraction: dict) -> list[dict]:
    anomalies = []
    clauses = extraction.get("clauses", {})

    term = clauses.get("termination", {})
    notice_days = term.get("notice_days")
    if notice_days is not None and notice_days < settings.MAX_TERMINATION_NOTICE_DAYS_LOW:
        anomalies.append(_mk(
            "warning", "termination_notice",
            f"Termination notice period is only {notice_days} days, which is shorter than the "
            f"{settings.MAX_TERMINATION_NOTICE_DAYS_LOW}-day baseline typically expected, giving "
            "the counterparty little time to respond before the agreement ends.",
            {"notice_days": notice_days},
        ))

    payment = clauses.get("payment_terms", {})
    payment_days = payment.get("days")
    if payment_days is not None and payment_days > settings.MAX_PAYMENT_TERMS_DAYS:
        anomalies.append(_mk(
            "warning", "payment_terms",
            f"Payment terms of {payment_days} days exceed the {settings.MAX_PAYMENT_TERMS_DAYS}-day "
            "threshold, which can strain cash flow for the paying party's counterparty.",
            {"payment_days": payment_days},
        ))

    liability = clauses.get("liability_cap", {})
    amounts = liability.get("amounts", [])
    if len(amounts) >= 2:
        # crude asymmetry check: parse first two money figures found
        def to_num(s):
            return float(s.replace("$", "").replace(",", "").replace("USD", "").strip() or 0)
        nums = [to_num(a) for a in amounts[:2]]
        if nums[0] and nums[1] and (max(nums) / max(min(nums), 1)) >= 3:
            anomalies.append(_mk(
                "critical", "liability_asymmetry",
                "Liability caps referenced in this clause differ substantially between the figures "
                "found (at least 3x apart), suggesting the cap may be asymmetric between the parties "
                "and warrants manual review.",
                {"amounts_found": amounts[:2]},
            ))

    for missing in extraction.get("missing_standard_clauses", []):
        anomalies.append(_mk(
            "informational", "missing_clause",
            f"No '{missing.replace('_', ' ')}' clause was detected in this document. This may be "
            "intentional, or the clause may use non-standard wording our extractor didn't match.",
            {"missing_clause": missing},
        ))

    return anomalies


def detect_invoice_anomalies(extraction: dict) -> list[dict]:
    anomalies = []
    line_items = extraction.get("line_items", [])

    computed_sum = sum(i["amount"] for i in line_items if i.get("amount") is not None)
    total = extraction.get("total")
    tax = extraction.get("tax") or 0
    if total is not None and line_items:
        expected = computed_sum + tax
        if abs(expected - total) > max(0.01, 0.01 * total):
            anomalies.append(_mk(
                "critical", "amount_mismatch",
                f"Line items plus tax sum to {expected:.2f}, but the stated total is {total:.2f}. "
                "The invoice does not mathematically reconcile.",
                {"computed": round(expected, 2), "stated_total": total},
            ))

    seen = {}
    for item in line_items:
        key = (item.get("description") or "").strip().lower()
        if not key:
            continue
        seen[key] = seen.get(key, 0) + 1
    duplicates = [k for k, v in seen.items() if v > 1]
    if duplicates:
        anomalies.append(_mk(
            "warning", "duplicate_line_item",
            f"{len(duplicates)} line item description(s) appear more than once on this invoice, "
            "which may indicate accidental double-billing.",
            {"duplicated_descriptions": duplicates},
        ))

    due_date_str = extraction.get("due_date")
    if due_date_str:
        try:
            due_date = dateparser.parse(due_date_str, fuzzy=True)
            if due_date and due_date.replace(tzinfo=None) < utcnow():
                anomalies.append(_mk(
                    "critical", "past_due_date",
                    f"The due date on this invoice ({due_date_str.strip()}) is already in the past "
                    "relative to processing time.",
                    {"due_date": due_date_str},
                ))
        except (ValueError, OverflowError):
            pass

    return anomalies


def detect_financial_statement_anomalies(extraction: dict, prior_period_metrics: dict | None = None) -> list[dict]:
    anomalies = []
    metrics = extraction.get("metrics", {})

    assets = metrics.get("total_assets")
    liabilities = metrics.get("total_liabilities")
    if assets and liabilities and liabilities > assets:
        anomalies.append(_mk(
            "critical", "liabilities_exceed_assets",
            "Total liabilities exceed total assets, which falls outside normal industry ranges and "
            "may indicate insolvency risk or an extraction/reporting error.",
            {"total_assets": assets, "total_liabilities": liabilities},
        ))

    revenue = metrics.get("revenue")
    net_income = metrics.get("net_income")
    if revenue and net_income is not None and net_income > revenue:
        anomalies.append(_mk(
            "warning", "net_income_exceeds_revenue",
            "Net income exceeds total revenue, which is unusual and worth verifying against the "
            "source document.",
            {"revenue": revenue, "net_income": net_income},
        ))

    # Configurable industry-style ratio checks. These are deliberately
    # deployment-configured rather than hard-coded to one industry.
    ranges = settings.INDUSTRY_RATIO_RANGES or {}
    if assets and liabilities is not None and assets != 0 and "debt_to_assets" in ranges:
        ratio = liabilities / assets
        lo, hi = ranges["debt_to_assets"]
        if ratio < lo or ratio > hi:
            anomalies.append(_mk(
                "warning", "industry_ratio_out_of_range",
                f"Debt-to-assets ratio is {ratio:.2f}, outside the configured normal range "
                f"of {lo:.2f}–{hi:.2f}.",
                {"ratio": round(ratio, 3), "range": [lo, hi], "metric": "debt_to_assets"},
            ))

    if revenue and net_income is not None and "net_margin" in ranges:
        margin = net_income / revenue
        lo, hi = ranges["net_margin"]
        if margin < lo or margin > hi:
            anomalies.append(_mk(
                "warning", "industry_ratio_out_of_range",
                f"Net margin is {margin:.1%}, outside the configured normal range "
                f"of {lo:.1%}–{hi:.1%}.",
                {"ratio": round(margin, 4), "range": [lo, hi], "metric": "net_margin"},
            ))

    if prior_period_metrics:
        for key, current_value in metrics.items():
            prior_value = prior_period_metrics.get(key)
            if prior_value and current_value is not None and prior_value != 0:
                pct_change = abs((current_value - prior_value) / prior_value) * 100
                if pct_change > settings.YOY_CHANGE_THRESHOLD_PCT:
                    anomalies.append(_mk(
                        "warning", "yoy_change",
                        f"{key.replace('_', ' ').title()} changed by {pct_change:.1f}% year-over-year, "
                        "exceeding the configured threshold and warranting explanation.",
                        {"metric": key, "prior": prior_value, "current": current_value, "pct_change": round(pct_change, 1)},
                    ))

    return anomalies


def run_stage3(document_type: str, extraction: dict) -> list[dict]:
    if document_type in ("contract", "nda", "rfp"):
        return detect_contract_anomalies(extraction)
    if document_type == "invoice":
        return detect_invoice_anomalies(extraction)
    if document_type == "financial_statement":
        return detect_financial_statement_anomalies(extraction)
    return []
