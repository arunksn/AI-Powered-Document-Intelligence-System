"""
Stage 4 (Section 2): risk scoring.

Produces an overall 0-100 risk score plus a breakdown by category, derived
from the anomalies found in Stage 3 weighted by severity.
"""
SEVERITY_WEIGHTS = {"critical": 30, "warning": 12, "informational": 3}

CATEGORY_GROUPS = {
    "financial": {"amount_mismatch", "past_due_date", "liabilities_exceed_assets", "net_income_exceeds_revenue", "yoy_change", "industry_ratio_out_of_range"},
    "contractual": {"termination_notice", "payment_terms", "liability_asymmetry", "missing_clause"},
    "data_quality": {"duplicate_line_item"},
}


def _categorize(anomaly_category: str) -> str:
    for group, members in CATEGORY_GROUPS.items():
        if anomaly_category in members:
            return group
    return "other"


def run_stage4(anomalies: list[dict]) -> dict:
    breakdown: dict[str, float] = {"financial": 0, "contractual": 0, "data_quality": 0, "other": 0}
    for a in anomalies:
        weight = SEVERITY_WEIGHTS.get(a["severity"], 0)
        group = _categorize(a["category"])
        breakdown[group] += weight

    raw_total = sum(breakdown.values())
    # Diminishing returns curve so 10 minor issues don't outscore 1 critical
    # issue by simple addition -- cap at 100, compress with sqrt-like curve.
    score = min(100, round(raw_total ** 0.85, 1)) if raw_total > 0 else 0.0

    return {
        "risk_score": score,
        "breakdown": {k: round(v, 1) for k, v in breakdown.items()},
        "anomaly_counts": {
            "critical": sum(1 for a in anomalies if a["severity"] == "critical"),
            "warning": sum(1 for a in anomalies if a["severity"] == "warning"),
            "informational": sum(1 for a in anomalies if a["severity"] == "informational"),
        },
    }
